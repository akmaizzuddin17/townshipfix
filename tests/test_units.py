"""Privacy, priority and the optional Claude vision provider."""
import io
import os
import unittest
from datetime import timedelta
from unittest import mock

import numpy as np
from PIL import Image

from app import clock, config
from app.services import classifier, privacy, priority, vision
from tests.helpers import START, photo_dir


class TestPrivacy(unittest.TestCase):
    def test_exif_removed_and_location_kept_separately(self):
        data = (photo_dir() / "case1_streetlight_main_boulevard" / "before_1.jpg").read_bytes()
        self.assertIsNotNone(vision.exif_info(data)["lat"])
        clean, info = privacy.sanitise(vision.load_pil(data), detector=lambda a: [])
        self.assertTrue(info["exif_removed"])
        self.assertIsNone(vision.exif_info(clean)["lat"])
        self.assertEqual(len(Image.open(io.BytesIO(clean)).getexif()), 0)

    def test_detected_faces_are_blurred(self):
        rng = np.random.default_rng(1)
        arr = rng.integers(0, 255, (400, 400, 3), dtype=np.uint8)
        im = Image.fromarray(arr)
        clean, info = privacy.sanitise(im, detector=lambda a: [("face", 100, 100, 80, 80)])
        out = np.asarray(Image.open(io.BytesIO(clean))).astype(float)
        self.assertEqual(info["blurred"], 1)
        # the face box became smooth, the rest kept its noise
        self.assertLess(out[110:170, 110:170].std(), 25)
        self.assertGreater(out[300:380, 300:380].std(), 50)

    def test_detectors_report_what_is_available(self):
        self.assertIsInstance(privacy.detectors_available(), list)


class TestPriority(unittest.TestCase):
    def setUp(self):
        clock.set_now(START)
        self.created = clock.iso(START)

    def tearDown(self):
        clock.set_now(None)

    def test_blocked_wheelchair_ramp_beats_full_bin(self):
        ramp = priority.compute("accessibility", ["wheelchair"], 1, self.created, False)
        bin_ = priority.compute("waste_bin", [], 1, self.created, False)
        self.assertGreater(ramp["score"], bin_["score"])
        self.assertEqual(ramp["band"], "P2")
        self.assertTrue(any("wheelchair" in r["why"] for r in ramp["reasons"]))

    def test_more_reporters_and_waiting_raise_priority(self):
        one = priority.compute("streetlight", [], 1, self.created, False)["score"]
        three = priority.compute("streetlight", [], 3, self.created, False)["score"]
        later = priority.compute("streetlight", [], 1, self.created, False, now=START + timedelta(days=3))["score"]
        self.assertGreater(three, one)
        self.assertGreater(later, one)

    def test_score_capped_and_bands(self):
        p = priority.compute("accessibility", list(config.IMPACT_FLAGS), 20, self.created, False)
        self.assertEqual(p["score"], 100)
        self.assertEqual(p["band"], "P1")
        self.assertEqual(clock.parse(p["sla_due_at"]) - START, timedelta(hours=24))

    def test_emergency(self):
        p = priority.compute("other", [], 1, self.created, True)
        self.assertEqual(p["band"], "P0")
        self.assertEqual(clock.parse(p["sla_due_at"]) - START, timedelta(hours=config.EMERGENCY_SLA_HOURS))


class FakeResponse:
    def __init__(self, text):
        self._t = text

    def raise_for_status(self):
        pass

    def json(self):
        return {"content": [{"type": "text", "text": self._t}]}


class TestClaudeProvider(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"})
        self.env.start()
        self.prov = mock.patch.object(config, "VISION_PROVIDER", "auto")
        self.prov.start()

    def tearDown(self):
        self.env.stop()
        self.prov.stop()

    def test_uses_vision_answer(self):
        sent = {}

        def post(url, **kw):
            sent.update(kw)
            return FakeResponse('{"category": "drain", "confidence": 0.9, "hazards": ["standing water"], '
                                '"description": "Clogged drain"}')
        r = classifier.classify("", b"\xff\xd8fake", post=post)
        self.assertEqual(r["category"], "drain")
        self.assertEqual(r["source"], "claude_vision")
        self.assertEqual(sent["headers"]["anthropic-version"], "2023-06-01")
        self.assertEqual(sent["json"]["messages"][0]["content"][0]["type"], "image")

    def test_falls_back_when_api_fails(self):
        def post(url, **kw):
            raise ConnectionError("offline")
        r = classifier.classify("tong sampah penuh", b"x", post=post)
        self.assertEqual(r["category"], "waste_bin")
        self.assertEqual(r["source"], "keywords")
        self.assertIn("warning", r)

    def test_bad_category_falls_back(self):
        r = classifier.classify("lampu jalan rosak", b"x",
                                post=lambda url, **kw: FakeResponse('{"category": "spaceship"}'))
        self.assertEqual(r["category"], "streetlight")

    def test_clear_words_win_over_disagreeing_photo(self):
        r = classifier.classify("lampu jalan rosak tak menyala", b"x",
                                post=lambda url, **kw: FakeResponse('{"category": "tree", "confidence": 0.7}'))
        self.assertEqual(r["category"], "streetlight")
        self.assertEqual(r["alternative"]["category"], "tree")

    def test_offline_by_default(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(classifier._provider(), "keywords")


if __name__ == "__main__":
    unittest.main()
