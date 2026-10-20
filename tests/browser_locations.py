"""Location reporting regression checks on a phone-sized real browser.

    python tests/browser_locations.py [screenshot_dir]

Uses an isolated database and mocks public map tiles / external address results.
Phone permission and position are provided by the browser test context.
"""
import base64
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from PIL import Image
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scripts import synthetic_photos  # noqa: E402

TILE = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")


def main():
    data = Path(tempfile.mkdtemp(prefix="tf_location_e2e_"))
    shots = Path(sys.argv[1]) if len(sys.argv) > 1 else data / "screenshots"
    shots.mkdir(parents=True, exist_ok=True)
    photos = synthetic_photos.write_demo(data / "photos")
    photo = photos / "case1_streetlight_main_boulevard" / "before_1.jpg"
    with Image.open(photo) as im:
        im.convert("RGB").save(data / "no_gps.jpg")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    env = {**os.environ, "TOWNSHIPFIX_DATA": str(data / "app"), "TOWNSHIPFIX_PRIVACY_DETECTION": "off"}
    server = subprocess.Popen([sys.executable, "run.py", "--port", str(port)], cwd=ROOT, env=env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    errors = []
    try:
        for _ in range(60):
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
                break
            except OSError:
                time.sleep(0.25)
        else:
            raise RuntimeError("Test server did not start")
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel=os.environ.get("TOWNSHIPFIX_TEST_BROWSER"))
            context = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True,
                has_touch=True, permissions=["geolocation"], geolocation={"latitude": 3.2, "longitude": 101.6, "accuracy": 12})
            context.route("https://tile.openstreetmap.org/**", lambda route: route.fulfill(content_type="image/png", body=TILE))
            context.route("https://fonts.googleapis.com/**", lambda route: route.abort())
            page = context.new_page()
            page.on("pageerror", lambda err: errors.append(str(err)))

            def fresh():
                page.goto(base)
                # Optional categories are collapsed in the simplified form.
                expect(page.locator("#zone option[value='Z1']")).to_be_attached()
                page.fill("#text", "Broken streetlight beside the bus stop")

            def submit():
                page.click("#confirm-location")
                page.click("#check")
                expect(page.locator("#step-confirm")).to_be_visible()
                expect(page.locator("#confirm-location-summary")).not_to_be_empty()
                with page.expect_request(lambda req: req.url.endswith("/api/reports") and req.method == "POST") as sent:
                    page.click("#send")
                expect(page.locator("#step-done")).to_be_visible()
                return sent.value.post_data_json

            # Photo GPS is suggested, but the resident must confirm it.
            fresh()
            page.set_input_files("#photo", str(photo))
            expect(page.locator("#photo-meta .tag.good")).to_be_visible()
            expect(page.locator("#loc-status")).to_have_text("Location from your photo")
            expect(page.locator("#location-map .report-pin")).to_be_visible()
            page.click("#check")
            expect(page.locator("#form-error")).to_contain_text("confirm where")

            # A one-shot phone reading includes accuracy and survives photo uploads.
            page.click("#use-gps")
            expect(page.locator("#loc-status")).to_have_text("Location from your phone")
            expect(page.locator("#location-coordinates")).to_contain_text("3.200000, 101.600000")
            expect(page.locator("#location-coordinates")).to_contain_text("12 m")
            page.set_input_files("#photo", str(photo))
            expect(page.locator("#photo-meta .tag.good")).to_be_visible()
            expect(page.locator("#loc-status")).to_have_text("Location from your phone")
            page.locator("#location-preview").screenshot(path=shots / "location-gps.png")
            body = submit()
            assert body["lat"] == 3.2 and body["lng"] == 101.6 and body["location_accuracy_m"] == 12, body
            code = page.inner_text("#done-code")
            saved = page.request.get(base + f"/api/staff/tickets/{code}", headers={"X-Staff-Pin": "1234"}).json()
            assert saved["reports"][0]["location_accuracy_m"] == 12

            # Switching from GPS to an area changes the submitted coordinates.
            fresh()
            page.click("#use-gps")
            expect(page.locator("#loc-status")).to_have_text("Location from your phone")
            page.select_option("#zone", "Z4")
            expect(page.locator("#location-coordinates")).to_contain_text("3.074400, 101.517400")
            page.set_input_files("#photo", str(photo))
            expect(page.locator("#photo-meta .tag.good")).to_be_visible()
            body = submit()
            assert body["location_source"] == "zone" and body["lat"] == 3.0744, body

            # Manual address lookup, keyboard correction and reconfirmation.
            fresh()
            page.route("**/api/locations/search?**", lambda route: route.fulfill(content_type="application/json", body=json.dumps({
                "items": [{"label": "Elmina Central Park, Shah Alam", "lat": 3.18, "lng": 101.51, "source": "address_search"}],
                "unavailable": False})))
            page.fill("#location-query", "Elmina Central Park")
            page.click("#search-location")
            page.locator("#location-results button").click()
            expect(page.locator("#location-label")).to_have_text("Elmina Central Park, Shah Alam")
            body = submit()
            assert body["location_source"] == "address_search" and body["lat"] == 3.18, body
            fresh()
            page.fill("#location-query", "Elmina Central Park")
            page.click("#search-location")
            page.locator("#location-results button").click()
            page.click("#confirm-location")
            pin = page.locator(".report-pin")
            pin.focus(); pin.press("ArrowRight")
            expect(page.locator("#confirm-location")).to_be_enabled()
            expect(page.locator("#loc-status")).to_have_text("Pin placed manually")
            page.locator("#location-map").click(position={"x": 220, "y": 140})
            page.fill("#landmark", "Opposite the bus stop")
            page.locator("#location-preview").screenshot(path=shots / "location-manual-pin.png")
            body = submit()
            assert body["location_source"] == "map_pin" and body["location_accuracy_m"] is None, body
            assert "Opposite the bus stop" in body["landmark"] and body["lng"] != 101.51, body
            page.unroute("**/api/locations/search?**")

            # A slow address response must not replace a newer manual choice.
            fresh()
            pending = []
            page.route("**/api/locations/search?**", lambda route: pending.append(route))
            page.fill("#location-query", "Elmina Central Park")
            page.click("#search-location")
            expect(page.locator("#location-search-status")).to_have_text("Searching…")
            page.select_option("#zone", "Z3")
            assert pending, "Search was not dispatched"
            with page.expect_response("**/api/locations/search?**"):
                pending[0].fulfill(content_type="application/json", body=json.dumps({"items": [
                    {"label": "Old search", "lat": 3.18, "lng": 101.51, "source": "address_search"}], "unavailable": False}))
            expect(page.locator("#location-label")).to_have_text("School & clinic area")
            expect(page.locator("#location-results button")).to_have_count(0)
            page.unroute("**/api/locations/search?**")

            # A late GPS callback cannot replace a manual selection.
            fresh()
            page.evaluate("""() => { navigator.geolocation.getCurrentPosition = (success) => {
                window.finishGps = () => success({coords:{latitude:3.2, longitude:101.6, accuracy:12}});
            }; }""")
            page.click("#use-gps")
            page.select_option("#zone", "Z2")
            page.evaluate("window.finishGps()")
            expect(page.locator("#location-label")).to_have_text("Community park")
            expect(page.locator("#location-coordinates")).to_contain_text("3.073450, 101.520100")

            # Permission failure and a GPS-free photo still allow a manual report.
            fresh()
            page.evaluate("() => { navigator.geolocation.getCurrentPosition = (ok, fail) => fail({code:1}); }")
            page.click("#use-gps")
            expect(page.locator("#loc-status")).to_contain_text("Couldn't get your location")
            page.set_input_files("#photo", str(data / "no_gps.jpg"))
            expect(page.locator("#photo-meta .tag.good")).to_be_visible()
            expect(page.locator("#location-preview")).to_be_hidden()
            page.fill("#location-query", "Community park")
            page.click("#search-location")
            page.locator("#location-results button").click()
            page.click(".lang button[data-lang=ms]")
            expect(page.locator("#confirm-location")).to_have_text("Ya, masalah ada di sini")
            body = submit()
            assert body["lang"] == "ms" and body["location_source"] == "zone", body

            # Map/address outages preserve the area and landmark fallback.
            fresh()
            page.click(".lang button[data-lang=en]")
            page.route("https://tile.openstreetmap.org/**", lambda route: route.abort())
            page.route("**/api/locations/search?**", lambda route: route.fulfill(content_type="application/json",
                body=json.dumps({"items": [], "unavailable": True})))
            page.fill("#location-query", "Elmina Central Park")
            page.click("#search-location")
            expect(page.locator("#location-search-status")).to_contain_text("unavailable")
            page.select_option("#zone", "Z2")
            expect(page.locator("#location-map-status")).to_contain_text("could not load")
            body = submit()
            assert body["location_source"] == "zone", body
            page.unroute("**/api/locations/search?**")
            page.unroute("https://tile.openstreetmap.org/**")

            # Changing a typed query invalidates a previously confirmed location.
            fresh()
            page.select_option("#zone", "Z1")
            page.click("#confirm-location")
            page.fill("#location-query", "Another place")
            page.click("#check")
            expect(page.locator("#step-confirm")).to_be_hidden()
            expect(page.locator("#location-preview")).to_be_hidden()
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "Mobile page overflows horizontally"
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)
    assert not errors, errors
    print(f"Location browser checks passed. Screenshots: {shots}")


if __name__ == "__main__":
    main()
