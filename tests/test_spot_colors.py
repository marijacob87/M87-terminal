import unittest

from core.spot_colors import spot_srgb


class SpotColorTests(unittest.TestCase):
    def test_known_pantones_have_visual_equivalents(self):
        self.assertEqual(spot_srgb("PANTONE 2768 C"), "#071D49")
        self.assertEqual(spot_srgb("pantone   871 c"), "#84754E")

    def test_unknown_spot_uses_neutral_swatch(self):
        self.assertEqual(spot_srgb("COR ESPECIAL CLIENTE"), "#777777")


if __name__ == "__main__":
    unittest.main()
