"""Protect people who appear in photos before anything is stored.

* Always: re-encode the photo, which drops all EXIF metadata (GPS, phone model,
  owner name). We keep only the location we extracted, in the database.
* When OpenCV's face / number-plate detectors are available (the standard
  `opencv-python` wheel ships them), blur faces and plates.
"""
import io
import os

import cv2
import numpy as np
from PIL import Image

_cascades = None


def _load_cascades():
    global _cascades
    if _cascades is None:
        _cascades = {}
        base = getattr(getattr(cv2, "data", None), "haarcascades", "") or ""
        for name, fn in (("face", "haarcascade_frontalface_default.xml"),
                         ("plate", "haarcascade_russian_plate_number.xml")):
            path = os.path.join(base, fn)
            if os.path.exists(path):
                c = cv2.CascadeClassifier(path)
                if not c.empty():
                    _cascades[name] = c
    return _cascades


def detectors_available():
    return sorted(_load_cascades().keys())


def detect_sensitive(img_rgb: np.ndarray):
    from .. import config
    if config.PRIVACY_DETECTION == "off":
        return []
    boxes = []
    gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)
    for name, c in _load_cascades().items():
        found = c.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=6, minSize=(24, 24))
        boxes += [(name, int(x), int(y), int(w), int(h)) for (x, y, w, h) in found]
    return boxes


def blur_boxes(img_rgb: np.ndarray, boxes):
    out = img_rgb.copy()
    H, W = out.shape[:2]
    for _, x, y, w, h in boxes:
        pad = int(0.15 * max(w, h))
        x0, y0 = max(0, x - pad), max(0, y - pad)
        x1, y1 = min(W, x + w + pad), min(H, y + h + pad)
        roi = out[y0:y1, x0:x1]
        if roi.size:
            k = max(15, (max(x1 - x0, y1 - y0) // 3) | 1)
            out[y0:y1, x0:x1] = cv2.GaussianBlur(roi, (k, k), 0)
    return out


def sanitise(pil_img: Image.Image, detector=None, max_side=1600):
    """Return (jpeg_bytes_without_exif, info). detector lets tests inject boxes."""
    im = pil_img.convert("RGB")
    if max(im.size) > max_side:
        im.thumbnail((max_side, max_side))
    arr = np.asarray(im)
    boxes = (detector or detect_sensitive)(arr)
    if boxes:
        arr = blur_boxes(arr, boxes)
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, "JPEG", quality=88)  # no exif= -> metadata dropped
    info = {"exif_removed": True, "blurred": len(boxes),
            "blurred_kinds": sorted({b[0] for b in boxes}),
            "detectors": detectors_available() if detector is None else ["test"]}
    return buf.getvalue(), info
