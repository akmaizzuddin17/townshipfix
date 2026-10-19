"""Store a photo safely and remember its visual fingerprint."""
import io
import secrets

import cv2
import numpy as np
from PIL import Image

from .. import config
from . import privacy, vision

ALLOWED = {"JPEG", "PNG", "WEBP", "HEIF", "MPO"}


class PhotoError(ValueError):
    pass


def store(data: bytes, prefix="r", detector=None):
    """Save a privacy-safe copy. Returns dict(name, exif, privacy)."""
    if not data:
        raise PhotoError("empty photo")
    if len(data) > config.MAX_UPLOAD_MB * 1024 * 1024:
        raise PhotoError(f"photo larger than {config.MAX_UPLOAD_MB} MB")
    try:
        probe = Image.open(io.BytesIO(data))
        fmt = probe.format
        probe.verify()
    except Exception:
        raise PhotoError("this file is not a readable image")
    if fmt not in ALLOWED:
        raise PhotoError(f"unsupported image type {fmt}; use JPG or PNG")
    exif = vision.exif_info(data)
    pil = vision.load_pil(data)
    clean, priv = privacy.sanitise(pil, detector=detector)
    config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    config.FEATURE_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{prefix}_{secrets.token_hex(6)}.jpg"
    (config.UPLOAD_DIR / name).write_bytes(clean)
    feats = vision.compute_features(load_cv(name))
    vision.save_features(config.FEATURE_DIR / (name + ".npz"), feats)
    return {"name": name, "exif": exif, "privacy": priv}


def load_cv(name):
    arr = cv2.imdecode(np.frombuffer((config.UPLOAD_DIR / name).read_bytes(), np.uint8), cv2.IMREAD_COLOR)
    h, w = arr.shape[:2]
    s = config.IMAGE_MAX_SIDE / max(h, w)
    if s < 1:
        arr = cv2.resize(arr, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
    return arr


def features(name):
    path = config.FEATURE_DIR / (name + ".npz")
    if not path.exists():
        vision.save_features(path, vision.compute_features(load_cv(name)))
    return vision.load_features(path)
