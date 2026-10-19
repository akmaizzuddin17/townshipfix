"""Click through the real app in a headless browser and save screenshots.

    python tests/browser_e2e.py [screenshot_dir]

Starts its own server on a free port with a fresh data folder, so it never
touches your demo data. Fails loudly on any JavaScript error.
"""
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scripts import synthetic_photos  # noqa: E402

SHOTS = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs" / "screenshots"
SHOTS.mkdir(parents=True, exist_ok=True)


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def main():
    data = Path(tempfile.mkdtemp(prefix="tf_e2e_"))
    photos = synthetic_photos.write_demo(data / "photos")
    port = free_port()
    env = {**os.environ, "TOWNSHIPFIX_DATA": str(data / "app"), "TOWNSHIPFIX_PRIVACY_DETECTION": "off"}
    server = subprocess.Popen([sys.executable, "run.py", "--port", str(port)], cwd=ROOT, env=env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    errors = []
    try:
        for _ in range(60):
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
                break
            except OSError:
                time.sleep(0.25)
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            phone = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2,
                                        locale="en-MY", has_touch=True, is_mobile=True)
            page = phone.new_page()
            page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
            page.on("console", lambda m: m.type == "error" and "fonts.g" not in m.text and "ERR_" not in m.text
                    and errors.append(f"console: {m.text}"))

            lamp = photos / "case1_streetlight_main_boulevard"
            texts = ["Streetlight broken in front of the walkway, very dark at night",
                     "lampu jalan rosak, warga emas takut lalu waktu malam",
                     "lamp post not working near the boulevard"]
            codes = []
            for i in range(3):
                page.goto(base + "/")
                if i == 1:
                    page.click(".lang button[data-lang=ms]")
                    expect(page.locator("#step-form h1")).to_have_text("Apa yang perlu dibaiki?")
                elif i == 2:
                    page.click(".lang button[data-lang=en]")
                page.set_input_files("#photo", str(lamp / f"before_{i + 1}.jpg"))
                expect(page.locator("#photo-meta .tag.good")).to_be_visible(timeout=15000)
                page.fill("#text", texts[i])
                expect(page.locator("#loc-status")).to_have_class("tag good")
                expect(page.locator('#categories .chip[data-cat="streetlight"]')).to_have_attribute("aria-pressed", "true", timeout=8000)
                if i == 0:
                    page.screenshot(path=SHOTS / "01_resident_form.png", full_page=True)
                page.click("#check")
                expect(page.locator("#step-confirm")).to_be_visible()
                if i == 1:
                    expect(page.locator("#readback")).to_contain_text("Saya faham")
                    expect(page.locator("#confirm-notices .notice")).to_contain_text("TF-0001")
                    page.screenshot(path=SHOTS / "02_resident_readback_duplicate.png", full_page=True)
                page.click("#send")
                expect(page.locator("#step-done")).to_be_visible(timeout=15000)
                codes.append(page.inner_text("#done-code"))
                if i == 2:
                    expect(page.locator("#done-msg")).to_contain_text("3 residents")
                    page.screenshot(path=SHOTS / "03_resident_sent_merged.png", full_page=True)
            assert codes == ["TF-0001"] * 3, codes

            # a voice-only style report (no photo) by area, plus an emergency
            page.click("#new-report")
            page.fill("#text", "Ramp OKU di depan klinik dihalang motosikal, kerusi roda tak boleh lalu")
            page.select_option("#zone", "Z3")
            page.click("#check")
            page.click("#send")
            expect(page.locator("#step-done")).to_be_visible(timeout=15000)
            page.click("#new-report")
            page.fill("#text", "Exposed wire sparking at the playground")
            page.select_option("#zone", "Z2")
            page.click("#check")
            expect(page.locator(".notice.danger")).to_be_visible()
            page.click("#send")
            expect(page.locator("#step-done")).to_be_visible(timeout=15000)

            # staff
            desk = browser.new_context(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
            sp = desk.new_page()
            sp.on("pageerror", lambda e: errors.append(f"staff pageerror: {e}"))
            sp.goto(base + "/staff")
            sp.fill("#pin", "0000")
            sp.click("#gate button")
            expect(sp.locator("#gate-error")).to_have_text("That PIN is not right.")
            sp.fill("#pin", "1234")
            sp.click("#gate button")
            expect(sp.locator("#queue li")).to_have_count(3)
            first = sp.locator("#queue li .title").first.inner_text()
            assert "TF-0003 Exposed wiring" in first, f"emergency should be first, got {first}"
            sp.locator("#queue li button", has_text="TF-0001").click()
            expect(sp.locator("#detail h1")).to_have_text("Broken streetlight")
            expect(sp.locator("#detail .photos figure")).to_have_count(3)
            sp.screenshot(path=SHOTS / "04_staff_queue_detail.png", full_page=True)
            sp.fill("#assignee", "Ali (electrical crew 2)")
            sp.get_by_role("button", name="Assign").click()
            expect(sp.locator("#detail .tag").first).to_have_text("Assigned")
            sp.get_by_role("button", name="Start work").click()
            expect(sp.locator("#detail .tag").first).to_have_text("Being repaired")
            sp.set_input_files("#after", str(photos / "case4_walkway_block_c" / "after.jpg"))
            sp.get_by_role("button", name="Submit repair photo").click()
            expect(sp.locator("#detail h2", has_text="Last repair photo rejected")).to_be_visible(timeout=15000)
            sp.screenshot(path=SHOTS / "05_staff_wrong_photo_rejected.png", full_page=True)
            sp.set_input_files("#after", str(lamp / "after.jpg"))
            sp.get_by_role("button", name="Submit repair photo").click()
            expect(sp.locator("#detail h2", has_text="Repair evidence accepted")).to_be_visible(timeout=15000)
            sp.screenshot(path=SHOTS / "06_staff_repair_verified.png", full_page=True)

            # resident confirms
            page.click("#go-mine")
            expect(page.locator("#mine-list .card").first).to_be_visible()
            card = page.locator("#mine-list .card", has_text="TF-0001").first
            expect(card.get_by_role("button", name="Yes, it's fixed")).to_be_visible()
            card.scroll_into_view_if_needed()
            page.screenshot(path=SHOTS / "07_resident_check_repair.png", full_page=True)
            card.get_by_role("button", name="Yes, it's fixed").click()
            expect(page.locator("#mine-list .card", has_text="TF-0001").first).to_contain_text("Confirmed fixed", timeout=8000)

            # tracking by code
            page.click("#tab-track")
            page.fill("#track-code", "tf-0002")
            page.click("#track-form button")
            expect(page.locator("#track-result .card")).to_contain_text("TF-0002")
            page.screenshot(path=SHOTS / "08_resident_track.png", full_page=True)

            sp.reload()
            expect(sp.locator("#metrics .metric").first).to_be_visible()
            metrics = sp.inner_text("#metrics")
            assert "100%" in metrics, metrics
            sp.click('[data-filter="closed"]')
            expect(sp.locator("#queue li")).to_have_count(1)
            sp.click('[data-filter="active"]')
            sp.screenshot(path=SHOTS / "09_staff_metrics_after.png", full_page=True)
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)
    if errors:
        print("JS ERRORS:\n" + "\n".join(errors))
        sys.exit(1)
    print(f"Browser walkthrough passed. Screenshots in {SHOTS}")


if __name__ == "__main__":
    main()
