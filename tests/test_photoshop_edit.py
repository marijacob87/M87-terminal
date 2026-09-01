import tempfile
import unittest
from pathlib import Path

import fitz
import pikepdf
from PIL import Image

from core.page_organizer import page_specs
from core.photoshop_edit import (
    DEFAULT_BLEED_MM, EDIT_DPI, edited_image_to_pdf,
    prepare_page_for_photoshop,
)


class PhotoshopEditTests(unittest.TestCase):
    def test_creates_three_mm_bleed_without_changing_trim_art(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pdf"
            document = fitz.open()
            page = document.new_page(width=200, height=300)
            page.set_trimbox(fitz.Rect(10, 20, 190, 280))
            page.draw_rect(page.trimbox, fill=(0, 1, 0), color=(1, 0, 0))
            document.save(source)
            document.close()

            image_path, template = prepare_page_for_photoshop(
                source,
                page_specs(source)[0],
                root / "bleed",
                bleed_mm=DEFAULT_BLEED_MM,
            )
            bleed_px = round(DEFAULT_BLEED_MM * EDIT_DPI / 25.4)
            with fitz.open(template) as pdf:
                original = pdf[0].get_pixmap(
                    dpi=EDIT_DPI,
                    colorspace=fitz.csCMYK,
                    alpha=False,
                    clip=pdf[0].trimbox,
                )
            with Image.open(image_path) as expanded:
                self.assertEqual(
                    expanded.size,
                    (original.width + 2 * bleed_px, original.height + 2 * bleed_px),
                )
                center = expanded.crop((
                    bleed_px,
                    bleed_px,
                    bleed_px + original.width,
                    bleed_px + original.height,
                ))
                self.assertEqual(center.tobytes(), original.samples)

            output = root / "with_bleed.pdf"
            edited_image_to_pdf(
                image_path,
                template,
                output,
                bleed_mm=DEFAULT_BLEED_MM,
            )
            bleed_pt = DEFAULT_BLEED_MM * 72 / 25.4
            with fitz.open(output) as pdf:
                page = pdf[0]
                self.assertAlmostEqual(page.rect.width, 180 + 2 * bleed_pt, places=2)
                self.assertAlmostEqual(page.rect.height, 260 + 2 * bleed_pt, places=2)
                self.assertAlmostEqual(page.trimbox.x0, bleed_pt, places=2)
                self.assertAlmostEqual(page.trimbox.y0, bleed_pt, places=2)
                self.assertAlmostEqual(page.trimbox.width, 180, places=2)
                self.assertEqual(page.bleedbox, page.mediabox)

    def test_exports_selected_page_and_rebuilds_it_after_save(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pdf"
            with pikepdf.Pdf.new() as pdf:
                page = pdf.add_blank_page(page_size=(200, 300))
                page.obj.TrimBox = pikepdf.Array([10, 20, 190, 280])
                pdf.save(source)

            image_path, template = prepare_page_for_photoshop(
                source,
                page_specs(source)[0],
                root / "edit",
            )
            with Image.open(image_path) as image:
                self.assertEqual(image.mode, "CMYK")
                self.assertEqual(image.info["dpi"], (EDIT_DPI, EDIT_DPI))
                edited = Image.new("CMYK", image.size, (100, 0, 0, 0))
                edited.save(
                    image_path,
                    format="TIFF",
                    compression="tiff_lzw",
                    dpi=(EDIT_DPI, EDIT_DPI),
                )

            output = root / "edited.pdf"
            edited_image_to_pdf(image_path, template, output)
            with fitz.open(output) as document:
                page = document[0]
                self.assertAlmostEqual(page.rect.width, 200, places=2)
                self.assertAlmostEqual(page.rect.height, 300, places=2)
                self.assertAlmostEqual(page.trimbox.x0, 10, places=2)
                self.assertAlmostEqual(page.trimbox.y0, 20, places=2)
                self.assertTrue(page.get_images(full=True))


if __name__ == "__main__":
    unittest.main()
