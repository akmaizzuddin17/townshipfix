import unittest

from app.services import text_nlp


class TestUnderstanding(unittest.TestCase):
    def cat(self, s):
        return text_nlp.suggest_category(s)[0]

    def test_english(self):
        self.assertEqual(self.cat("The streetlight outside block C is not working"), "streetlight")
        self.assertEqual(self.cat("big pothole on the road near the school"), "road_damage")
        self.assertEqual(self.cat("rubbish bin overflowing again"), "waste_bin")
        self.assertEqual(self.cat("drain is clogged and flooding"), "drain")

    def test_malay(self):
        self.assertEqual(self.cat("Lampu jalan rosak, tak menyala"), "streetlight")
        self.assertEqual(self.cat("tong sampah penuh dan melimpah"), "waste_bin")
        self.assertEqual(self.cat("longkang tersumbat, air bertakung"), "drain")
        self.assertEqual(self.cat("pokok tumbang dekat taman"), "tree")

    def test_manglish_mix(self):
        self.assertEqual(self.cat("ramp OKU kena block dengan motor, kerusi roda tak boleh lalu"), "accessibility")

    def test_electrical_hazard(self):
        self.assertEqual(self.cat("exposed wire sparking at the playground"), "electrical")
        self.assertEqual(self.cat("wayar terdedah dekat tiang"), "electrical")

    def test_unknown_and_empty(self):
        self.assertEqual(self.cat("something strange here"), "other")
        self.assertEqual(text_nlp.suggest_category("")[0], None)

    def test_evidence_words_returned(self):
        cat, conf, words = text_nlp.suggest_category("lampu jalan gelap")
        self.assertIn("lampu jalan", words)
        self.assertGreater(conf, 0.5)

    def test_emergency(self):
        self.assertTrue(text_nlp.detect_emergency("there is an exposed wire sparking near the playground"))
        self.assertTrue(text_nlp.detect_emergency("bau gas kuat dekat blok C"))
        self.assertFalse(text_nlp.detect_emergency("the light is broken"))
        # no false alarm from words merely containing 'api' or 'fire'
        self.assertFalse(text_nlp.detect_emergency("kapit and firefly"))

    def test_flags(self):
        f = text_nlp.detect_flags("my grandmother in a wheelchair fell here, it is dark at night")
        self.assertIn("wheelchair", f)
        self.assertIn("injury", f)
        self.assertIn("night", f)
        self.assertIn("school", text_nlp.detect_flags("depan sekolah"))

    def test_readback_languages(self):
        self.assertIn("Lampu jalan rosak", text_nlp.readback("streetlight", "Blok C", "ms", False))
        en = text_nlp.readback("streetlight", "Block C", "en", True)
        self.assertIn("Broken streetlight at Block C", en)
        self.assertIn("security", en)


if __name__ == "__main__":
    unittest.main()
