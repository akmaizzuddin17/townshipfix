"""End-to-end: resident reports -> duplicate grouping -> staff -> verified repair -> metrics."""
import io
import unittest

from app import config
from tests.helpers import PIN, AppTestCase

LAMP = "case1_streetlight_main_boulevard"
POTHOLE = "case2_pothole_school_area"
BIN = "case3_bin_near_boulevard"
WALK = "case4_walkway_block_c"
LAMP2 = "case5_other_streetlight_30m"


class TestDemoScenario(AppTestCase):
    def test_three_photos_one_ticket_then_verified_repair(self):
        r1 = self.report(LAMP, 1, "Lampu jalan rosak, gelap waktu malam", "streetlight", lang="ms",
                         contact="012-1111111", client_duration_ms=48000)
        r2 = self.report(LAMP, 2, "streetlight broken near walkway", "streetlight", client_duration_ms=39000)
        r3 = self.report(LAMP, 3, "lamp post not working, elderly walk here", None, client_duration_ms=41000)
        code = r1["ticket"]["code"]
        self.assertFalse(r1["merged"])
        self.assertTrue(r2["merged"])
        self.assertTrue(r3["merged"])
        self.assertEqual({r2["ticket"]["code"], r3["ticket"]["code"]}, {code})
        self.assertEqual(r3["reporters"], 3)
        self.assertIn("photo match", r3["explanation"])
        # more residents -> higher priority
        self.assertGreater(r3["ticket"]["priority_score"], r1["ticket"]["priority_score"])

        t = self.c.get(f"/api/staff/tickets/{code}", headers=PIN).json
        self.assertEqual(t["team_id"], "electrical")
        self.assertEqual(len(t["reports"]), 3)
        self.assertIn("night", t["flags"])
        self.assertIn("vulnerable", t["flags"])

        self.assertEqual(self.c.post(f"/api/staff/tickets/{code}/assign", json={"assignee": "Ali"},
                                     headers=PIN).json["status"], "assigned")
        self.assertEqual(self.c.post(f"/api/staff/tickets/{code}/start", headers=PIN).json["status"], "in_progress")
        self.advance(hours=20)
        res = self.complete(code, self.photos / LAMP / "after.jpg")
        self.assertTrue(res["passed"], res)
        self.assertEqual(self.c.get(f"/api/tickets/{code}").json["status"], "awaiting_confirmation")

        # a stranger cannot confirm
        self.assertEqual(self.c.post(f"/api/tickets/{code}/confirm", json={"token": "nope"}).status_code, 403)
        ok = self.c.post(f"/api/tickets/{code}/confirm", json={"token": r2["report_token"]})
        self.assertEqual(ok.json["status"], "closed")
        self.assertEqual(ok.json["close_reason"], "resident_confirmed")

        m = self.c.get("/api/staff/metrics", headers=PIN).json
        self.assertEqual(m["reports"], 3)
        self.assertEqual(m["tickets"], 1)
        self.assertEqual(m["duplicates_merged"], 2)
        self.assertEqual(m["median_report_seconds"], 41.0)
        self.assertEqual(m["median_resolution_hours"], 20.0)
        self.assertEqual(m["closed_with_verified_evidence_pct"], 100)

        msgs = [o["message"] for o in self.c.get("/api/staff/outbox", headers=PIN).json["items"]]
        self.assertTrue(any("ditutup" in s for s in msgs), "Malay resident gets Malay message")
        self.assertTrue(any("3 residents" in s for s in msgs))


class TestDuplicates(AppTestCase):
    def test_nearby_different_problem_is_separate(self):
        a = self.report(LAMP, 1, "lampu rosak", "streetlight")
        b = self.report(BIN, 1, "tong sampah penuh", "waste_bin")  # ~25 m away
        self.assertNotEqual(a["ticket"]["code"], b["ticket"]["code"])
        self.assertFalse(b["merged"])

    def test_two_different_broken_lamps_30m_apart_stay_separate(self):
        a = self.report(LAMP, 1, "lampu rosak", "streetlight")
        b = self.report(LAMP2, 1, "lampu rosak juga", "streetlight")
        self.assertNotEqual(a["ticket"]["code"], b["ticket"]["code"])

    def test_wrong_category_tap_still_merges_when_photo_is_clearly_same(self):
        a = self.report(LAMP, 1, "lampu rosak", "streetlight")
        b = self.report(LAMP, 2, "", "vandalism")
        self.assertEqual(a["ticket"]["code"], b["ticket"]["code"])

    def test_far_apart_never_merge(self):
        a = self.report(LAMP, 1, "lampu rosak", "streetlight")
        b = self.report(WALK, 1, "jubin pecah", "walkway")
        self.assertNotEqual(a["ticket"]["code"], b["ticket"]["code"])

    def test_voice_only_reports_merge_when_very_close(self):
        body = {"text": "longkang tersumbat depan surau", "zone": "Z5", "lang": "ms"}
        a = self.c.post("/api/reports", json=body).json
        b = self.c.post("/api/reports", json={**body, "text": "drain clogged near the surau", "lang": "en"}).json
        self.assertEqual(a["ticket"]["code"], b["ticket"]["code"])
        self.assertEqual(a["ticket"]["landmark"], "Shoplots & surau")

    def test_staff_can_merge_a_possible_duplicate(self):
        a = self.report(LAMP, 1, "lampu rosak", "streetlight")
        b = self.report(LAMP2, 1, "lampu rosak", "streetlight")
        r = self.c.post(f"/api/staff/tickets/{b['ticket']['code']}/merge", json={"into": a["ticket"]["code"]},
                        headers=PIN)
        self.assertEqual(r.status_code, 200, r.json)
        self.assertEqual(r.json["reporters"], 2)
        # the resident's view of the old ticket follows the merge
        mine = self.c.post("/api/my", json={"tokens": [b["report_token"]]}).json["items"]
        self.assertEqual(mine[0]["ticket"]["code"], a["ticket"]["code"])
        m = self.c.get("/api/staff/metrics", headers=PIN).json
        self.assertEqual(m["tickets"], 1)
        self.assertEqual(m["duplicates_merged_by_staff"], 1)

    def test_analyze_without_location_still_suggests(self):
        r = self.c.post("/api/analyze", json={"text": "tong sampah penuh", "lang": "ms"})
        self.assertEqual(r.status_code, 200, r.json)
        self.assertEqual(r.json["suggestion"]["category"], "waste_bin")
        self.assertIsNone(r.json["match"]["distance_m"])

    def test_analyze_warns_before_submitting(self):
        self.report(LAMP, 1, "lampu rosak", "streetlight")
        u = self.upload(self.photos / LAMP / "before_2.jpg")
        a = self.c.post("/api/analyze", json={"text": "lampu jalan rosak", "lat": u["gps"]["lat"],
                                              "lng": u["gps"]["lng"], "photo_ref": u["ref"], "lang": "ms"}).json
        self.assertEqual(a["match"]["action"], "merge")
        self.assertTrue(a["match"]["same_type"])
        self.assertGreater(a["match"]["photo_match"], 75)
        self.assertEqual(a["category"], "streetlight")
        self.assertTrue(a["readback"].startswith("Saya faham"))


class TestVerification(AppTestCase):
    def _ready(self):
        code = self.report(POTHOLE, 1, "pothole depan sekolah", "road_damage")["ticket"]["code"]
        self.c.post(f"/api/staff/tickets/{code}/assign", json={}, headers=PIN)
        return code

    def test_photo_of_another_place_is_rejected(self):
        code = self._ready()
        res = self.complete(code, self.photos / WALK / "after.jpg")
        self.assertFalse(res["passed"])
        self.assertFalse(next(c for c in res["checks"] if c["id"] == "same_place")["ok"])
        self.assertEqual(self.c.get(f"/api/tickets/{code}").json["status"], "assigned")

    def test_reusing_the_residents_photo_is_rejected(self):
        code = self._ready()
        res = self.complete(code, self.photos / POTHOLE / "before_1.jpg")
        self.assertFalse(res["passed"])
        self.assertFalse(next(c for c in res["checks"] if c["id"] == "not_reupload")["ok"])

    def test_unrepaired_spot_from_new_angle_is_rejected(self):
        code = self._ready()
        res = self.complete(code, self.photos / POTHOLE / "before_3.jpg")
        self.assertFalse(res["passed"])
        self.assertFalse(next(c for c in res["checks"] if c["id"] == "changed")["ok"])

    def test_good_repair_then_auto_close_after_silence(self):
        code = self._ready()
        self.advance(hours=5)
        self.assertTrue(self.complete(code, self.photos / POTHOLE / "after.jpg")["passed"])
        self.advance(hours=config.AUTO_CLOSE_HOURS + 1)
        t = self.c.get(f"/api/tickets/{code}").json
        self.assertEqual(t["status"], "closed")
        self.assertEqual(t["close_reason"], "auto_after_verified")

    def test_resident_can_reopen(self):
        r = self.report(POTHOLE, 1, "pothole", "road_damage")
        code = r["ticket"]["code"]
        self.c.post(f"/api/staff/tickets/{code}/assign", json={}, headers=PIN)
        self.advance(hours=2)
        self.complete(code, self.photos / POTHOLE / "after.jpg")
        t = self.c.post(f"/api/tickets/{code}/reopen", json={"token": r["report_token"], "reason": "still a hole"}).json
        self.assertEqual(t["status"], "assigned")
        self.assertEqual(self.c.get("/api/staff/metrics", headers=PIN).json["reopened"], 1)

    def test_supervisor_override_needs_reason(self):
        code = self._ready()
        bad = self.c.post(f"/api/staff/tickets/{code}/override", json={"note": "done"}, headers=PIN)
        self.assertEqual(bad.status_code, 400)
        good = self.c.post(f"/api/staff/tickets/{code}/override",
                           json={"note": "Fixed at night, photo too dark; inspected in person"}, headers=PIN)
        self.assertEqual(good.json["status"], "closed")
        m = self.c.get("/api/staff/metrics", headers=PIN).json
        self.assertEqual(m["closed_with_verified_evidence_pct"], 0)

    def test_cannot_complete_before_assignment(self):
        code = self.report(POTHOLE, 1, "pothole", "road_damage")["ticket"]["code"]
        with open(self.photos / POTHOLE / "after.jpg", "rb") as f:
            r = self.c.post(f"/api/staff/tickets/{code}/complete", data={"photo": (f, "a.jpg")},
                            headers=PIN, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 400)


class TestSafetyAndGuards(AppTestCase):
    def test_emergency_alerts_security_and_jumps_queue(self):
        normal = self.report(WALK, 1, "jubin pecah", "walkway")
        urgent = self.c.post("/api/reports", json={"text": "exposed wire sparking at the playground",
                                                   "zone": "Z2", "lang": "en"}).json
        self.assertTrue(urgent["ticket"]["urgent"])
        self.assertEqual(urgent["ticket"]["priority_band"], "P0")
        queue = self.c.get("/api/staff/tickets", headers=PIN).json["items"]
        self.assertEqual(queue[0]["code"], urgent["ticket"]["code"])
        self.assertNotEqual(queue[0]["code"], normal["ticket"]["code"])
        out = self.c.get("/api/staff/outbox", headers=PIN).json["items"]
        self.assertTrue(any(o["channel"] == "security" for o in out))

    def test_staff_endpoints_need_pin(self):
        self.assertEqual(self.c.get("/api/staff/tickets").status_code, 401)
        self.assertEqual(self.c.get("/api/staff/tickets", headers={"X-Staff-Pin": "0000"}).status_code, 401)

    def test_public_status_hides_private_details(self):
        r = self.report(LAMP, 1, "lampu rosak", "streetlight", contact="012-9999999", on_behalf_of="Mak Cik Siti")
        body = self.c.get(f"/api/tickets/{r['ticket']['code']}").get_data(as_text=True)
        self.assertNotIn("012-9999999", body)
        self.assertNotIn("Mak Cik", body)
        self.assertNotIn(r["report_token"], body)

    def test_report_for_a_neighbour_is_recorded(self):
        r = self.report(LAMP, 1, "lampu rosak", "streetlight", on_behalf_of="Mak Cik Siti (Blok C-3-2)")
        t = self.c.get(f"/api/staff/tickets/{r['ticket']['code']}", headers=PIN).json
        self.assertEqual(t["reports"][0]["on_behalf_of"], "Mak Cik Siti (Blok C-3-2)")

    def test_location_is_required(self):
        r = self.c.post("/api/reports", json={"text": "lampu rosak"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("Location", r.json["error"])

    def test_bad_inputs(self):
        r = self.c.post("/api/photos", data={"photo": (io.BytesIO(b"hello"), "x.jpg")},
                        content_type="multipart/form-data")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.c.post("/api/reports", json={"zone": "Z1", "photo_ref": "../../etc/passwd"}).status_code, 400)
        self.assertEqual(self.c.post("/api/reports", json={"zone": "Z1", "lat": "abc", "text": "x"}).status_code, 400)
        self.assertEqual(self.c.get("/media/../config.py").status_code, 404)
        self.assertEqual(self.c.get("/api/tickets/TF-9999").status_code, 404)

    def test_stored_photo_has_no_gps(self):
        u = self.upload(self.photos / LAMP / "before_1.jpg")
        self.assertIsNotNone(u["gps"])
        from app.services import vision
        resp = self.c.get(u["url"])
        stored = resp.data
        resp.close()
        self.assertIsNone(vision.exif_info(stored)["lat"])

    def test_pages_and_config_load(self):
        self.assertEqual(self.c.get("/").status_code, 200)
        self.assertEqual(self.c.get("/staff").status_code, 200)
        cfg = self.c.get("/api/config").json
        self.assertIn("streetlight", cfg["categories"])
        self.assertEqual(cfg["vision"], "keywords")


if __name__ == "__main__":
    unittest.main()
