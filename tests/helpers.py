"""Shared test setup: a throw-away data folder, synthetic photos, a frozen clock."""
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from app import clock, config, create_app, db
from scripts import synthetic_photos

_PHOTOS = None
START = datetime(2026, 10, 19, 2, 0, tzinfo=timezone.utc)  # 10:00 in Kuala Lumpur
PIN = {"X-Staff-Pin": config.STAFF_PIN}


def photo_dir() -> Path:
    """Synthetic demo photos, generated once per test run."""
    global _PHOTOS
    if _PHOTOS is None:
        _PHOTOS = Path(tempfile.mkdtemp(prefix="tf_photos_"))
        # residents shoot at 09:xx, contractor's after photo is the next day
        synthetic_photos.write_demo(_PHOTOS, report_time=datetime(2026, 10, 19, 10, 5))
    return _PHOTOS


class AppTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="tf_data_"))
        config.DATA_DIR = self.tmp
        config.UPLOAD_DIR = self.tmp / "uploads"
        config.FEATURE_DIR = self.tmp / "features"
        config.DB_PATH = self.tmp / "test.db"
        db.reset_connection()
        clock.set_now(START)
        self.app = create_app()
        self.c = self.app.test_client()
        self.photos = photo_dir()

    def tearDown(self):
        clock.set_now(None)
        db.reset_connection()
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ------------------------------------------------------------ helpers
    def upload(self, path):
        with open(path, "rb") as f:
            r = self.c.post("/api/photos", data={"photo": (f, path.name)}, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 200, r.json)
        return r.json

    def report(self, case, n=1, text="", category=None, **extra):
        u = self.upload(self.photos / case / f"before_{n}.jpg")
        body = {"text": text, "lat": u["gps"]["lat"], "lng": u["gps"]["lng"], "location_source": "photo_gps",
                "photo_ref": u["ref"], "category": category, "lang": "en"}
        body.update(extra)
        r = self.c.post("/api/reports", json=body)
        self.assertEqual(r.status_code, 201, r.json)
        return r.json

    def complete(self, code, path):
        with open(path, "rb") as f:
            r = self.c.post(f"/api/staff/tickets/{code}/complete", data={"photo": (f, "after.jpg")},
                            headers=PIN, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 200, r.json)
        return r.json["result"]

    def advance(self, **kw):
        from datetime import timedelta
        clock.set_now(clock.now() + timedelta(**kw))
