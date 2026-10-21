"""Live staff dashboard check: a phone report shows up on an open dashboard within seconds,
the map moves to show it, a duplicate shows as +1 report, and a stopped server is flagged.

    python tests/browser_live.py [screenshot_dir]
"""
import base64, os, socket, subprocess, sys, tempfile, time
from pathlib import Path
from playwright.sync_api import expect, sync_playwright
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from scripts import synthetic_photos
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp()); OUT.mkdir(parents=True, exist_ok=True)
TILE = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")
data = Path(tempfile.mkdtemp()); photos = synthetic_photos.write_demo(data / "photos")
photo = photos / "case1_streetlight_main_boulevard" / "before_1.jpg"
photo2 = photos / "case1_streetlight_main_boulevard" / "before_2.jpg"
s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
base = f"http://127.0.0.1:{port}"
env = {**os.environ, "TOWNSHIPFIX_DATA": str(data / "app"), "TOWNSHIPFIX_PRIVACY_DETECTION": "off"}
srv = subprocess.Popen([sys.executable, "run.py", "--port", str(port)], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(2.5); errs = []
def phone_report(b, img, text, lat, lng):
    ph = b.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True,
        permissions=["geolocation"], geolocation={"latitude": lat, "longitude": lng, "accuracy": 15})
    ph.route("https://**", lambda r: r.fulfill(content_type="image/png", body=TILE))
    p = ph.new_page(); p.on("pageerror", lambda e: errs.append("PHONE " + str(e)))
    p.goto(base); p.fill("#text", text)
    with p.expect_response(lambda r: "/api/photos" in r.url): p.set_input_files("#photo", str(img))
    p.wait_for_load_state("networkidle"); p.wait_for_timeout(300)
    p.click("#use-gps"); expect(p.locator("#loc-status")).to_have_text("Location from your phone")
    p.click("#confirm-location"); p.click("#check")
    try: expect(p.locator("#step-confirm")).to_be_visible()
    except AssertionError:
        print("FORM ERROR:", repr(p.inner_text("#form-error")), "text:", text); p.screenshot(path=str(OUT/"phone_fail.png"), full_page=True); raise
    p.click("#send"); expect(p.locator("#step-done")).to_be_visible()
    code = p.inner_text("#done-code"); ph.close(); return code, time.time()
try:
  with sync_playwright() as pw:
    b = pw.chromium.launch()
    sc = b.new_context(viewport={"width": 1300, "height": 900}); sc.route("https://**", lambda r: r.fulfill(content_type="image/png", body=TILE))
    st = sc.new_page()
    st.on("pageerror", lambda e: errs.append("STAFF " + str(e)))
    st.goto(base + "/staff"); st.fill("#pin", "1234"); st.press("#pin", "Enter")
    expect(st.locator("#live-text")).to_contain_text("Live")
    # 1) brand new problem, real KL GPS far from the sample township
    code, t0 = phone_report(b, photo, "Lampu jalan rosak depan surau", 3.1745, 101.7236)
    expect(st.locator("#queue li.is-new")).to_contain_text(code, timeout=10000)
    print(f"new ticket {code} on dashboard after {time.time()-t0:.1f}s")
    expect(st.locator(".toast")).to_contain_text(f"New report {code}")
    print("toast:", st.locator(".toast").first.inner_text().replace("\n"," "))
    print("queue row:", st.locator("#queue li").first.inner_text().replace("\n"," | "))
    # marker inside visible map?
    box = st.locator("#map").bounding_box(); mk = st.locator(".ticket-marker").first.bounding_box()
    inside = mk and box["x"] <= mk["x"] and mk["x"]+mk["width"] <= box["x"]+box["width"] and box["y"] <= mk["y"] and mk["y"]+mk["height"] <= box["y"]+box["height"]
    print("marker visible on map:", inside)
    st.screenshot(path=str(OUT/"live_new.png"))
    # 2) second resident, same problem -> merges, dashboard shows +1 report
    code2, t0 = phone_report(b, photo2, "streetlight not working near the surau", 3.17452, 101.72362)
    print("second report went to", code2)
    expect(st.locator("#queue li.is-new")).to_contain_text("2 reporters", timeout=10000)
    print(f"+1 report visible after {time.time()-t0:.1f}s")
    st.locator(".toast").first.click(); expect(st.locator("#detail")).to_contain_text("What residents said (2)")
    print("toast opens the ticket with both reports")
    st.screenshot(path=str(OUT/"live_merged.png"))
    # 3) server stops -> warning shows
    srv.terminate(); srv.wait()
    expect(st.locator("#live")).to_have_class("live is-down", timeout=10000)
    print("server down message:", st.inner_text("#live-text"))
    assert not errs, errs
    assert inside, "new marker not visible on map"
    print("Live dashboard check passed.")
finally:
  if srv.poll() is None: srv.terminate()
