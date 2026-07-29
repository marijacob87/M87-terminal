import tempfile
import unittest
from pathlib import Path

import fitz
import pikepdf

from core.geometry import (
    MM_TO_PT,
    BoxSettings,
    CropMarkSettings,
    FormatSettings,
    GeometryError,
    GeometrySettings,
    apply_geometry,
    inspect_geometry,
)
from tests.test_pdf_preservation import add_output_intent, output_profile


def mm(value):
    return value * MM_TO_PT


def create_pdf(path: Path, pages=2):
    document = fitz.open()
    for index in range(pages):
        page = document.new_page(width=mm(106), height=mm(56))
        page.set_trimbox(fitz.Rect(mm(3), mm(3), mm(103), mm(53)))
        page.insert_text(fitz.Point(mm(10), mm(20)), f"Página {index + 1}")
        page.draw_rect(
            fitz.Rect(mm(8), mm(8), mm(30), mm(30)),
            color=(0, 0, 0, 1),
        )
    document.set_metadata({"title": "Geometria M87", "author": "Testes"})
    document.save(path)
    document.close()
    return path


class GeometryTests(unittest.TestCase):
    def test_inspects_media_and_trim_with_top_left_offsets(self):
        with tempfile.TemporaryDirectory() as directory:
            source = create_pdf(Path(directory) / "source.pdf", pages=1)
            info = inspect_geometry(source)

        self.assertEqual(info.page_count, 1)
        self.assertAlmostEqual(info.pages[0].media.width_mm, 106, places=2)
        self.assertAlmostEqual(info.pages[0].trim.x_mm, 3, places=2)
        self.assertAlmostEqual(info.pages[0].trim.y_mm, 3, places=2)
        self.assertAlmostEqual(info.pages[0].trim.width_mm, 100, places=2)
        self.assertAlmostEqual(info.pages[0].trim.height_mm, 50, places=2)

    def test_format_scales_only_selected_page_and_preserves_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = create_pdf(root / "source.pdf")
            output = root / "output.pdf"
            apply_geometry(
                source,
                output,
                GeometrySettings(
                    format=FormatSettings(212, 112, "center", False),
                ),
                [0],
            )
            info = inspect_geometry(output)
            with pikepdf.Pdf.open(output) as pdf:
                title = str(pdf.docinfo.get("/Title", ""))

        self.assertAlmostEqual(info.pages[0].media.width_mm, 212, places=2)
        self.assertAlmostEqual(info.pages[0].media.height_mm, 112, places=2)
        self.assertAlmostEqual(info.pages[0].trim.width_mm, 200, places=2)
        self.assertAlmostEqual(info.pages[1].media.width_mm, 106, places=2)
        self.assertEqual(title, "Geometria M87")

    def test_box_edit_does_not_transform_content_stream(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = create_pdf(root / "source.pdf", pages=1)
            output = root / "output.pdf"
            with pikepdf.Pdf.open(source) as pdf:
                before = b"".join(stream.read_bytes() for stream in pdf.pages[0].obj.Contents)
            apply_geometry(
                source,
                output,
                GeometrySettings(
                    trim=BoxSettings(5, 6, 90, 40),
                ),
                [0],
            )
            with pikepdf.Pdf.open(output) as pdf:
                after = b"".join(stream.read_bytes() for stream in pdf.pages[0].obj.Contents)
            info = inspect_geometry(output)

        self.assertEqual(before, after)
        self.assertAlmostEqual(info.pages[0].trim.x_mm, 5, places=2)
        self.assertAlmostEqual(info.pages[0].trim.y_mm, 6, places=2)
        self.assertAlmostEqual(info.pages[0].trim.width_mm, 90, places=2)

    def test_media_resize_keeps_existing_art_centered(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = create_pdf(root / "source.pdf", pages=1)
            output = root / "output.pdf"
            before_document = fitz.open(source)
            before_page = before_document[0]
            before_block = fitz.Rect(before_page.get_text("blocks")[0][:4])
            before_offset = (
                before_block.x0 + before_block.x1 - before_page.rect.width,
                before_block.y0 + before_block.y1 - before_page.rect.height,
            )
            before_document.close()

            apply_geometry(
                source,
                output,
                GeometrySettings(
                    media=BoxSettings(0, 0, 126, 76),
                ),
                [0],
            )
            after_document = fitz.open(output)
            after_page = after_document[0]
            after_block = fitz.Rect(after_page.get_text("blocks")[0][:4])
            after_offset = (
                after_block.x0 + after_block.x1 - after_page.rect.width,
                after_block.y0 + after_block.y1 - after_page.rect.height,
            )
            after_document.close()

        self.assertAlmostEqual(before_offset[0], after_offset[0], places=2)
        self.assertAlmostEqual(before_offset[1], after_offset[1], places=2)

    def test_rejects_trim_outside_media(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = create_pdf(root / "source.pdf", pages=1)
            with self.assertRaisesRegex(GeometryError, "TrimBox"):
                apply_geometry(
                    source,
                    root / "output.pdf",
                    GeometrySettings(trim=BoxSettings(20, 20, 100, 50)),
                    [0],
                )

    def test_crop_marks_can_expand_media_without_overwriting_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = create_pdf(root / "source.pdf", pages=1)
            original = source.read_bytes()
            output = root / "output.pdf"
            apply_geometry(
                source,
                output,
                GeometrySettings(crop_marks=CropMarkSettings(
                    enabled=True,
                    offset_mm=3,
                    length_mm=5,
                    thickness_pt=0.25,
                    auto_expand_media=True,
                )),
                [0],
            )
            info = inspect_geometry(output)
            self.assertEqual(source.read_bytes(), original)
            self.assertGreater(info.pages[0].media.width_mm, 106)
            self.assertGreater(info.pages[0].media.height_mm, 56)

    def test_cleanup_removes_only_content_whose_bounds_are_outside_trim(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pdf"
            document = fitz.open()
            page = document.new_page(width=mm(106), height=mm(56))
            page.set_trimbox(fitz.Rect(mm(10), mm(10), mm(96), mm(46)))
            page.insert_text(fitz.Point(mm(1), mm(5)), "FORA")
            page.insert_text(fitz.Point(mm(20), mm(25)), "DENTRO")
            document.save(source)
            document.close()
            output = root / "output.pdf"

            apply_geometry(
                source,
                output,
                GeometrySettings(remove_outside_trim=True),
                [0],
            )
            result = fitz.open(output)
            text = result[0].get_text()
            result.close()

        self.assertNotIn("FORA", text)
        self.assertIn("DENTRO", text)

    def test_preserves_icc_but_removes_unvalidated_pdfx_declaration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = create_pdf(root / "source.pdf", pages=1)
            profile = add_output_intent(source, "PDF/X-4")
            output = root / "output.pdf"

            apply_geometry(
                source,
                output,
                GeometrySettings(
                    format=FormatSettings(120, 70),
                ),
                [0],
            )

            self.assertEqual(output_profile(output), profile)
            with pikepdf.Pdf.open(output) as pdf:
                self.assertNotIn("/GTS_PDFXVersion", pdf.docinfo)
                self.assertNotIn("/GTS_PDFXConformance", pdf.docinfo)


if __name__ == "__main__":
    unittest.main()
