import unittest

from app.services import vision
from tests.helpers import photo_dir


def load(case, name):
    data = (photo_dir() / case / f"{name}.jpg").read_bytes()
    im = vision.to_cv(vision.load_pil(data))
    return im, vision.compute_features(im), data


LAMP = "case1_streetlight_main_boulevard"
POTHOLE = "case2_pothole_school_area"
OTHER_LAMP = "case5_other_streetlight_30m"


class TestVision(unittest.TestCase):
    def test_same_spot_from_different_phones_matches(self):
        _, a, _ = load(LAMP, "before_1")
        _, b, _ = load(LAMP, "before_3")
        self.assertGreater(vision.photo_similarity(a, b)["score"], 0.75)

    def test_different_places_do_not_match(self):
        _, a, _ = load(LAMP, "before_1")
        for case in (POTHOLE, OTHER_LAMP):
            _, b, _ = load(case, "before_1")
            self.assertLess(vision.photo_similarity(a, b)["score"], 0.3, case)

    def test_repair_is_detected_as_change(self):
        ib, fb, _ = load(LAMP, "before_2")
        ia, fa, _ = load(LAMP, "after")
        frac, info = vision.change_fraction(ib, ia, fb, fa)
        self.assertIsNotNone(frac)
        self.assertGreater(frac, 0.0075)
        self.assertIsNotNone(info["changed_box"])

    def test_no_repair_is_not_change(self):
        i1, f1, _ = load(POTHOLE, "before_1")
        i2, f2, _ = load(POTHOLE, "before_2")
        frac, _ = vision.change_fraction(i1, i2, f1, f2)
        self.assertLess(frac, 0.0075)

    def test_unrelated_photos_cannot_be_aligned(self):
        i1, f1, _ = load(LAMP, "before_1")
        i2, f2, _ = load(POTHOLE, "after")
        frac, info = vision.change_fraction(i1, i2, f1, f2)
        self.assertIsNone(frac)

    def test_exif_location_and_time(self):
        _, _, data = load(LAMP, "before_1")
        ex = vision.exif_info(data)
        self.assertAlmostEqual(ex["lat"], 3.0721, places=3)
        self.assertAlmostEqual(ex["lng"], 101.5182, places=3)
        self.assertIsNotNone(ex["taken_at"])

    def test_exif_missing_is_safe(self):
        self.assertEqual(vision.exif_info(b"not an image"), {"lat": None, "lng": None, "taken_at": None})


if __name__ == "__main__":
    unittest.main()
