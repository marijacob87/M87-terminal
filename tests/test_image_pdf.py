import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import fitz
from PIL import Image

from core.image_pdf import ImagePdfError, images_to_pdf, is_supported_image


class ImagePdfTests(unittest.TestCase):
    def test_combines_images_in_drop_order_and_uses_embedded_dpi(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "primeira.png"
            second = root / "segunda.jpg"
            Image.new("RGB", (600, 300), "red").save(first, dpi=(300, 300))
            Image.new("RGB", (200, 400), "blue").save(second, dpi=(100, 200))

            output = images_to_pdf([first, second])
            try:
                with fitz.open(output) as document:
                    self.assertEqual(document.page_count, 2)
                    self.assertAlmostEqual(document[0].rect.width, 144, places=1)
                    self.assertAlmostEqual(document[0].rect.height, 72, places=1)
                    self.assertAlmostEqual(document[1].rect.width, 144, places=1)
                    self.assertAlmostEqual(document[1].rect.height, 144, places=1)
                    self.assertTrue(document[0].get_images(full=True))
                    self.assertTrue(document[1].get_images(full=True))
            finally:
                output.unlink(missing_ok=True)

    def test_uses_300_dpi_when_image_has_no_reliable_resolution(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "sem_dpi.png"
            Image.new("RGB", (300, 600), "white").save(source)

            output = images_to_pdf([source])
            try:
                with fitz.open(output) as document:
                    self.assertAlmostEqual(document[0].rect.width, 72, places=1)
                    self.assertAlmostEqual(document[0].rect.height, 144, places=1)
            finally:
                output.unlink(missing_ok=True)

    def test_rejects_non_image_files(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "texto.txt"
            source.write_text("não é uma imagem", encoding="utf-8")

            self.assertFalse(is_supported_image(source))
            with self.assertRaises(ImagePdfError):
                images_to_pdf([source])


if __name__ == "__main__":
    unittest.main()
