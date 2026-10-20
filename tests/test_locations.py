import unittest
from unittest import mock

import requests

from app import config, db
from app.services import locations
from tests.helpers import AppTestCase, PIN


class TestLocationSearch(AppTestCase):
    def setUp(self):
        super().setUp()
        locations._cache.clear()
        locations._last_request = float("-inf")

    def test_township_area_search_does_not_need_network(self):
        with mock.patch.object(locations.requests, "get") as get:
            result = self.c.get("/api/locations/search?q=community%20park")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json["items"][0]["zone"], "Z2")
        self.assertEqual(result.json["items"][0]["lat"], config.ZONES[1]["lat"])
        get.assert_not_called()

    def test_external_result_coordinates_are_in_lat_lng_order_and_cached(self):
        response = mock.Mock()
        response.json.return_value = {"features": [{"geometry": {"coordinates": [101.5, 3.1]},
            "properties": {"name": "Elmina Central Park", "city": "Shah Alam", "country": "Malaysia"}}]}
        with mock.patch.object(locations.requests, "get", return_value=response) as get:
            first = self.c.get("/api/locations/search?q=Elmina%20Central%20Park").json
            second = self.c.get("/api/locations/search?q=elmina%20%20central%20park").json
        self.assertEqual(first, second)
        self.assertEqual(first["items"][0]["lat"], 3.1)
        self.assertEqual(first["items"][0]["lng"], 101.5)
        self.assertEqual(first["items"][0]["source"], "address_search")
        get.assert_called_once()
        self.assertEqual(get.call_args.kwargs["timeout"], 15)

    def test_external_failure_keeps_manual_area_fallback_available(self):
        with mock.patch.object(locations.requests, "get", side_effect=requests.Timeout):
            self.assertTrue(self.c.get("/api/locations/search?q=Elmina").json["unavailable"])
            result = self.c.get("/api/locations/search?q=Block%20C").json
        self.assertEqual(result["items"][0]["zone"], "Z4")

    def test_provider_can_be_disabled(self):
        with mock.patch.object(config, "GEOCODER_URL", ""), mock.patch.object(locations.requests, "get") as get:
            self.assertEqual(self.c.get("/api/locations/search?q=Elmina").json["items"], [])
            get.assert_not_called()

    def test_throttle_does_not_queue_external_requests(self):
        locations._last_request = locations.time.monotonic()
        with mock.patch.object(locations.requests, "get") as get:
            self.assertTrue(self.c.get("/api/locations/search?q=Elmina").json["unavailable"])
            get.assert_not_called()

    def test_invalid_searches_are_rejected_without_network(self):
        for query in ("", "a", "x" * 161):
            self.assertEqual(self.c.get("/api/locations/search", query_string={"q": query}).status_code, 400)

    def test_invalid_provider_coordinates_are_skipped(self):
        response = mock.Mock()
        response.json.return_value = {"features": [
            {"geometry": {"coordinates": [181, 3]}, "properties": {"name": "Invalid"}},
            {"geometry": {"coordinates": [101, float("nan")]}, "properties": {"name": "Invalid"}},
        ]}
        with mock.patch.object(locations.requests, "get", return_value=response):
            self.assertEqual(self.c.get("/api/locations/search?q=Elmina").json["items"], [])

    def test_gps_accuracy_and_manual_coordinates_are_saved(self):
        result = self.c.post("/api/reports", json={"text": "Broken lamp", "lat": 3.12, "lng": 101.55,
            "location_source": "device_gps", "location_accuracy_m": 18.5, "landmark": "Opposite Block C"})
        self.assertEqual(result.status_code, 201, result.json)
        code = result.json["ticket"]["code"]
        report = self.c.get(f"/api/staff/tickets/{code}", headers=PIN).json["reports"][0]
        self.assertEqual(report["location_accuracy_m"], 18.5)
        self.assertEqual(result.json["ticket"]["lat"], 3.12)
        self.assertEqual(report["location_source"], "device_gps")

    def test_incomplete_coordinates_and_invalid_accuracy_are_rejected(self):
        for extra in ({"lat": 3.1}, {"lng": 101.5}, {"lat": 3.1, "lng": 101.5, "location_accuracy_m": -2}):
            result = self.c.post("/api/reports", json={"text": "Broken lamp", "zone": "Z1", **extra})
            self.assertEqual(result.status_code, 400)

    def test_upgrade_preserves_existing_reports(self):
        self.c.post("/api/reports", json={"text": "Broken lamp", "zone": "Z1"})
        db.ex("ALTER TABLE reports DROP COLUMN location_accuracy_m")
        db.reset_connection()
        self.assertEqual(db.q1("SELECT COUNT(*) AS n FROM reports")["n"], 1)
        self.assertIsNone(db.q1("SELECT location_accuracy_m FROM reports")["location_accuracy_m"])


if __name__ == "__main__":
    unittest.main()
