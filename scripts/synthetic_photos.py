"""Generate synthetic township photos for tests and for a demo before real photos exist.

Each 'place' has its own procedurally drawn background (buildings, windows,
trees, paving), so different places look different. Each 'problem' is drawn on
top in a broken state and a fixed state. 'Views' simulate different residents
photographing the same spot: a shifted camera, other lighting and phone noise.

    python scripts/synthetic_photos.py            # writes demo_photos/_synthetic/
"""
import io
import math
import sys
from datetime import datetime, timedelta
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

W, H = 1280, 960


def _background(seed):
    rng = np.random.default_rng(seed)
    img = np.zeros((H, W, 3), np.uint8)
    # sky
    top = np.array(rng.integers(150, 230, 3), np.float32)
    for y in range(int(H * 0.45)):
        img[y, :] = (top * (0.75 + 0.25 * y / (H * 0.45))).clip(0, 255)
    # buildings with windows (rich, place-specific detail)
    x = int(rng.integers(-40, 0))
    while x < W:
        bw, bh = int(rng.integers(120, 260)), int(rng.integers(180, 380))
        y0 = int(H * 0.55) - bh
        col = tuple(int(c) for c in rng.integers(70, 210, 3))
        cv2.rectangle(img, (x, y0), (x + bw, int(H * 0.55)), col, -1)
        cv2.rectangle(img, (x, y0), (x + bw, int(H * 0.55)), (40, 40, 40), 2)
        wc = tuple(int(c) for c in rng.integers(20, 255, 3))
        for wy in range(y0 + 15, int(H * 0.55) - 25, int(rng.integers(28, 42))):
            for wx in range(x + 12, x + bw - 20, int(rng.integers(24, 36))):
                if rng.random() < 0.85:
                    shade = tuple(int(c * rng.uniform(0.5, 1.0)) for c in wc)
                    cv2.rectangle(img, (wx, wy), (wx + 14, wy + 18), shade, -1)
        # signboard with text: strong place-specific features
        if rng.random() < 0.7:
            sx, sy = x + 10, y0 + 8
            cv2.rectangle(img, (sx, sy), (sx + bw - 20, sy + 26), (240, 240, 240), -1)
            txt = "".join(chr(int(c)) for c in rng.integers(65, 91, 7))
            cv2.putText(img, txt, (sx + 6, sy + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (20, 20, 120), 2)
        x += bw + int(rng.integers(0, 30))
    # trees
    for _ in range(int(rng.integers(3, 7))):
        tx, ty = int(rng.integers(0, W)), int(rng.integers(int(H * 0.35), int(H * 0.55)))
        for _ in range(25):
            r = int(rng.integers(12, 30))
            cv2.circle(img, (tx + int(rng.integers(-45, 45)), ty + int(rng.integers(-40, 30))), r,
                       (int(rng.integers(20, 70)), int(rng.integers(90, 170)), int(rng.integers(20, 70))), -1)
    # paving: tiles with speckle texture
    ground = img[int(H * 0.55):, :]
    base = np.array(rng.integers(110, 175, 3), np.int16)
    noise = rng.integers(-28, 28, ground.shape, dtype=np.int16)
    ground[:] = (base + noise).clip(0, 255).astype(np.uint8)
    ts = int(rng.integers(55, 85))
    for gx in range(0, W, ts):
        cv2.line(img, (gx, int(H * 0.55)), (gx, H), (60, 60, 60), 2)
    for gy in range(int(H * 0.55), H, ts):
        cv2.line(img, (0, gy), (W, gy), (60, 60, 60), 2)
    # kerb + stones
    cv2.rectangle(img, (0, int(H * 0.55)), (W, int(H * 0.57)), (180, 180, 180), -1)
    for _ in range(60):
        cx, cy = int(rng.integers(0, W)), int(rng.integers(int(H * 0.58), H))
        cv2.circle(img, (cx, cy), int(rng.integers(2, 6)), tuple(int(c) for c in rng.integers(30, 220, 3)), -1)
    return img


def _streetlight(img, broken, rng):
    x = int(W * 0.62)
    cv2.rectangle(img, (x, 180), (x + 18, int(H * 0.8)), (90, 90, 95), -1)
    cv2.rectangle(img, (x - 80, 170), (x + 18, 186), (90, 90, 95), -1)
    if broken:
        cv2.ellipse(img, (x - 80, 196), (46, 22), 0, 0, 360, (45, 45, 50), -1)
        for _ in range(6):
            a = rng.uniform(0, math.pi)
            cv2.line(img, (x - 80, 196), (x - 80 + int(40 * math.cos(a)), 196 + int(18 * math.sin(a))), (10, 10, 10), 2)
    else:
        glow = img.copy()
        cv2.circle(glow, (x - 80, 215), 120, (150, 230, 255), -1)
        cv2.addWeighted(glow, 0.45, img, 0.55, 0, img)
        cv2.ellipse(img, (x - 80, 196), (46, 22), 0, 0, 360, (170, 245, 255), -1)


def _pothole(img, broken, rng):
    cx, cy = int(W * 0.45), int(H * 0.8)
    if broken:
        pts = np.array([(cx + int(120 * math.cos(a) * rng.uniform(0.7, 1.1)),
                         cy + int(55 * math.sin(a) * rng.uniform(0.7, 1.1)))
                        for a in np.linspace(0, 2 * math.pi, 22, endpoint=False)], np.int32)
        cv2.fillPoly(img, [pts], (25, 28, 30))
        cv2.polylines(img, [pts], True, (5, 5, 5), 3)
        for _ in range(12):
            cv2.circle(img, (cx + int(rng.integers(-90, 90)), cy + int(rng.integers(-35, 35))), 4, (60, 60, 60), -1)
    else:
        cv2.ellipse(img, (cx, cy), (135, 65), 0, 0, 360, (70, 72, 75), -1)


def _bin(img, broken, rng):
    x, y = int(W * 0.25), int(H * 0.62)
    cv2.rectangle(img, (x, y), (x + 120, y + 170), (40, 120, 40), -1)
    cv2.rectangle(img, (x - 5, y - 12), (x + 125, y + 4), (30, 90, 30), -1)
    if broken:
        for _ in range(14):
            c = tuple(int(v) for v in rng.integers(10, 80, 3))
            cv2.ellipse(img, (x + int(rng.integers(-60, 180)), y + int(rng.integers(-40, 190))),
                        (int(rng.integers(20, 40)), int(rng.integers(15, 30))), float(rng.integers(0, 180)), 0, 360, c, -1)


def _walkway(img, broken, rng):
    if broken:
        for i in range(5):
            x, y = int(W * 0.3) + i * 70, int(H * 0.7) + (i % 2) * 60
            cv2.rectangle(img, (x, y), (x + 62, y + 58), (35, 30, 25), -1)
            cv2.line(img, (x, y), (x + 62, y + 58), (90, 80, 70), 2)


PROBLEMS = {"streetlight": _streetlight, "road_damage": _pothole, "waste_bin": _bin, "walkway": _walkway}


def scene(place_seed, problem, broken=True):
    img = _background(place_seed)
    PROBLEMS[problem](img, broken, np.random.default_rng(place_seed + 7))
    return img


def view(img, view_seed, strength=1.0):
    """Same spot, different phone/angle/light."""
    rng = np.random.default_rng(view_seed)
    j = 0.07 * strength
    src = np.float32([[0, 0], [W, 0], [W, H], [0, H]])
    dst = src + np.float32(rng.uniform(-j, j, (4, 2)) * [W, H])
    M = cv2.getPerspectiveTransform(src, dst)
    out = cv2.warpPerspective(img, M, (W, H), borderMode=cv2.BORDER_REFLECT)
    alpha, beta = rng.uniform(0.8, 1.2), rng.uniform(-25, 25)
    out = cv2.convertScaleAbs(out, alpha=alpha, beta=beta)
    noise = rng.normal(0, 6, out.shape)
    return np.clip(out.astype(np.float32) + noise, 0, 255).astype(np.uint8)


def to_jpeg(img_bgr, lat=None, lng=None, taken_at=None, quality=88):
    im = Image.fromarray(cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB))
    ex = Image.Exif()
    if lat is not None:
        def dms(v):
            v = abs(v)
            d = int(v)
            m = int((v - d) * 60)
            return (float(d), float(m), round((v - d - m / 60) * 3600, 4))
        ex.get_ifd(0x8825).update({1: "N" if lat >= 0 else "S", 2: dms(lat),
                                   3: "E" if lng >= 0 else "W", 4: dms(lng)})
    if taken_at is not None:
        ex.get_ifd(0x8769)[36867] = taken_at.strftime("%Y:%m:%d %H:%M:%S")
    b = io.BytesIO()
    im.save(b, "JPEG", quality=quality, exif=ex.tobytes())
    return b.getvalue()


def offset(lat, lng, north_m, east_m):
    return lat + north_m / 111_320, lng + east_m / (111_320 * math.cos(math.radians(lat)))


# Demo cases: place seed, problem, location
CASES = {
    "case1_streetlight_main_boulevard": (101, "streetlight", (3.07210, 101.51820)),
    "case2_pothole_school_area": (202, "road_damage", (3.07050, 101.51655)),
    "case3_bin_near_boulevard": (303, "waste_bin", offset(3.07210, 101.51820, 20, 15)),  # 25 m from case1
    "case4_walkway_block_c": (404, "walkway", (3.07440, 101.51740)),
    "case5_other_streetlight_30m": (505, "streetlight", offset(3.07210, 101.51820, -22, 20)),  # hard negative
}


def write_demo(out_dir: Path, report_time=datetime(2026, 10, 19, 9, 0)):
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, (seed, prob, (lat, lng)) in CASES.items():
        d = out_dir / name
        d.mkdir(exist_ok=True)
        broken = scene(seed, prob, True)
        fixed = scene(seed, prob, False)
        for i in range(1, 4):
            la, ln = offset(lat, lng, (i - 2) * 3, (i % 2) * 3)
            (d / f"before_{i}.jpg").write_bytes(
                to_jpeg(view(broken, seed * 10 + i), la, ln, report_time + timedelta(minutes=i * 7)))
        la, ln = offset(lat, lng, 2, -2)
        (d / "after.jpg").write_bytes(to_jpeg(view(fixed, seed * 10 + 9), la, ln, report_time + timedelta(days=1)))
        (d / "case.json").write_text(
            '{"category": "%s", "lat": %.6f, "lng": %.6f, "note": "synthetic test scene"}\n' % (prob, lat, lng))
    return out_dir


if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else root / "demo_photos" / "_synthetic"
    write_demo(out)
    print("wrote", out)
