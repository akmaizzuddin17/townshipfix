"""Photo understanding that runs fully offline (no model download).

* Same-scene matching: SIFT keypoints + ratio test + RANSAC homography.
  Two photos of the same broken lamp from different angles share many
  geometrically consistent keypoints; photos of different places do not.
* Colour histogram + difference hash give a coarse second opinion.
* Change detection (for repair verification): align the after photo onto the
  before photo, cancel lighting differences, then measure how much of the
  scene changed in brightness or colour.
"""
import io
from datetime import datetime
from zoneinfo import ZoneInfo

import cv2
import numpy as np
from PIL import Image, ImageOps

from .. import config

_sift = None


def _detector():
    global _sift
    if _sift is None:
        _sift = cv2.SIFT_create(nfeatures=1500) if hasattr(cv2, "SIFT_create") else cv2.ORB_create(2000)
    return _sift


# ----------------------------------------------------------------- loading
def load_pil(data: bytes) -> Image.Image:
    im = Image.open(io.BytesIO(data))
    im = ImageOps.exif_transpose(im)  # respect phone rotation
    return im.convert("RGB")


def to_cv(im: Image.Image, max_side=config.IMAGE_MAX_SIDE) -> np.ndarray:
    arr = cv2.cvtColor(np.asarray(im), cv2.COLOR_RGB2BGR)
    h, w = arr.shape[:2]
    s = max_side / max(h, w)
    if s < 1:
        arr = cv2.resize(arr, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
    return arr


# ------------------------------------------------------------------ EXIF
def _ratio(v):
    try:
        return float(v)
    except TypeError:
        return v[0] / v[1]


def exif_info(data: bytes):
    """GPS (lat, lng) and capture time from the original photo, if present."""
    out = {"lat": None, "lng": None, "taken_at": None}
    try:
        im = Image.open(io.BytesIO(data))
        ex = im.getexif()
    except Exception:
        return out
    try:
        gps = ex.get_ifd(0x8825)
        if gps and 2 in gps and 4 in gps:
            def dms(t):
                return _ratio(t[0]) + _ratio(t[1]) / 60 + _ratio(t[2]) / 3600
            lat, lng = dms(gps[2]), dms(gps[4])
            if gps.get(1, "N") in ("S", b"S"):
                lat = -lat
            if gps.get(3, "E") in ("W", b"W"):
                lng = -lng
            if -90 <= lat <= 90 and -180 <= lng <= 180 and not (lat == 0 and lng == 0):
                out["lat"], out["lng"] = round(lat, 6), round(lng, 6)
    except Exception:
        pass
    try:
        sub = ex.get_ifd(0x8769)
        raw = sub.get(36867) or ex.get(306)  # DateTimeOriginal, else DateTime
        if raw:
            dt = datetime.strptime(str(raw).strip(), "%Y:%m:%d %H:%M:%S")
            out["taken_at"] = dt.replace(tzinfo=ZoneInfo(config.LOCAL_TZ))
    except Exception:
        pass
    return out


# -------------------------------------------------------------- features
def compute_features(img_bgr: np.ndarray) -> dict:
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    kps, desc = _detector().detectAndCompute(gray, None)
    pts = np.array([k.pt for k in kps], dtype=np.float32) if kps else np.zeros((0, 2), np.float32)
    if desc is None:
        desc = np.zeros((0, 128), np.float32)
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1], None, [18, 8], [0, 180, 0, 256])
    hist = cv2.normalize(hist, None).flatten().astype(np.float32)
    small = cv2.resize(gray, (9, 8), interpolation=cv2.INTER_AREA)
    dhash = (small[:, 1:] > small[:, :-1]).flatten().astype(np.uint8)
    return {"pts": pts, "desc": desc, "hist": hist, "dhash": dhash,
            "shape": np.array(gray.shape, dtype=np.int32)}


def save_features(path, feats):
    np.savez_compressed(path, **feats)


def load_features(path):
    with np.load(path) as z:
        return {k: z[k] for k in z.files}


# ------------------------------------------------------------- matching
def _good_matches(fa, fb):
    if len(fa["desc"]) < 2 or len(fb["desc"]) < 2:
        return []
    if fa["desc"].dtype == np.uint8:
        matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
    else:
        matcher = cv2.BFMatcher(cv2.NORM_L2)
    pairs = matcher.knnMatch(fa["desc"], fb["desc"], k=2)
    good = []
    for p in pairs:
        if len(p) == 2 and p[0].distance < config.SIFT_RATIO * p[1].distance:
            good.append(p[0])
    return good


def scene_match(fa, fb) -> dict:
    """How confidently do two photos show the same place? (0..1 + details)"""
    good = _good_matches(fa, fb)
    result = {"good_matches": len(good), "inliers": 0, "geom": 0.0, "H": None}
    if len(good) < 8:
        return result
    src = fa["pts"][[m.queryIdx for m in good]].reshape(-1, 1, 2)
    dst = fb["pts"][[m.trainIdx for m in good]].reshape(-1, 1, 2)
    H, mask = cv2.findHomography(src, dst, cv2.RANSAC, 8.0)
    if H is None or mask is None:
        return result
    inl = int(mask.sum())
    # a degenerate homography (huge scale/flip) is not a real view change
    det = np.linalg.det(H[:2, :2])
    if not (0.15 < abs(det) < 7) or det < 0:
        return result
    lo, hi = config.GEOM_MIN_INLIERS, config.GEOM_FULL_INLIERS
    geom = 0.0 if inl < lo else min(1.0, (inl - lo) / float(hi - lo) * 0.85 + 0.15)
    result.update(inliers=inl, geom=round(geom, 3), H=H)
    return result


def hist_similarity(fa, fb) -> float:
    c = cv2.compareHist(fa["hist"], fb["hist"], cv2.HISTCMP_CORREL)
    return float(max(0.0, c))


def dhash_similarity(fa, fb) -> float:
    return 1.0 - float(np.count_nonzero(fa["dhash"] != fb["dhash"])) / fa["dhash"].size


def photo_similarity(fa, fb) -> dict:
    sm = scene_match(fa, fb)
    h = hist_similarity(fa, fb)
    d = dhash_similarity(fa, fb)
    # geometry dominates; colour/hash only help when geometry already agrees a bit
    score = sm["geom"] * 0.75 + (0.15 * h + 0.10 * d) * (1.0 if sm["geom"] > 0 else 0.4)
    return {"score": round(min(1.0, score), 3), "geom": sm["geom"], "inliers": sm["inliers"],
            "hist": round(h, 3), "dhash": round(d, 3)}


# -------------------------------------------------------- change detection
def change_fraction(before_bgr, after_bgr, fb, fa):
    """Fraction of the overlapping scene that changed between before and after.

    Returns (fraction or None, details). None means we could not align them.
    """
    sm = scene_match(fa, fb)  # maps after -> before
    if sm["H"] is None:
        return None, {"inliers": sm["inliers"], "reason": "could not align photos"}
    # features were computed on images resized the same way as these arrays
    h, w = before_bgr.shape[:2]
    warped = cv2.warpPerspective(after_bgr, sm["H"], (w, h))
    mask = cv2.warpPerspective(np.full(after_bgr.shape[:2], 255, np.uint8), sm["H"], (w, h))
    mask = cv2.erode(mask, np.ones((9, 9), np.uint8)) > 0  # ignore warped borders
    overlap = mask.mean()
    if overlap < 0.3:
        return None, {"inliers": sm["inliers"], "reason": "photos overlap too little"}
    a = cv2.GaussianBlur(cv2.cvtColor(before_bgr, cv2.COLOR_BGR2LAB).astype(np.float32), (7, 7), 0)
    b = cv2.GaussianBlur(cv2.cvtColor(warped, cv2.COLOR_BGR2LAB).astype(np.float32), (7, 7), 0)
    # cancel overall lighting/white-balance differences (different time of day, phone)
    for ch in range(3):
        ma, sa = a[..., ch][mask].mean(), a[..., ch][mask].std() + 1e-3
        mb, sb = b[..., ch][mask].mean(), b[..., ch][mask].std() + 1e-3
        b[..., ch] = (b[..., ch] - mb) * (sa / sb) + ma
    d_l = np.abs(a[..., 0] - b[..., 0])
    d_ab = np.sqrt((a[..., 1] - b[..., 1]) ** 2 + (a[..., 2] - b[..., 2]) ** 2)
    changed = ((d_l > config.VERIFY_DIFF_L) | (d_ab > config.VERIFY_DIFF_AB)) & mask
    k = np.ones((5, 5), np.uint8)
    changed = cv2.morphologyEx(changed.astype(np.uint8), cv2.MORPH_OPEN, k) > 0
    frac = float(changed.sum()) / float(mask.sum())
    ys, xs = np.nonzero(changed)
    box = [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())] if len(xs) else None
    return frac, {"inliers": sm["inliers"], "overlap": round(float(overlap), 3),
                  "changed_pixels": int(changed.sum()), "changed_box": box}
