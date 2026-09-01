import tempfile
import unittest
from pathlib import Path

import fitz
import pikepdf

from core.geometry import (
    MM_TO_PT,
    ArtworkFitSettings,
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
    def test_format_distorts_art_and_boxes_to_exact_a3_plus_four(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "image.pdf"
            document = fitz.open()
            page = document.new_page(width=mm(86.7), height=mm(130.1))
            page.draw_rect(page.rect, color=(1, 0, 0), fill=(0, 1, 0))
            document.save(source)
            document.close()

            output = root / "a3_plus_four.pdf"
            apply_geometry(
                source,
                output,
                GeometrySettings(
                    format=FormatSettings(301, 424, "center", True),
                ),
                [0],
            )
            info = inspect_geometry(output)
            with fitz.open(output) as result:
                artwork_rect = result[0].get_drawings()[0]["rect"]

        self.assertAlmostEqual(info.pages[0].media.width_mm, 301, places=2)
        self.assertAlmostEqual(info.pages[0].media.height_mm, 424, places=2)
        self.assertAlmostEqual(info.pages[0].trim.width_mm, 301, places=2)
        self.assertAlmostEqual(info.pages[0].trim.height_mm, 424, places=2)
        self.assertAlmostEqual(artwork_rect.width * 25.4 / 72, 301, places=2)
        self.assertAlmostEqual(artwork_rect.height * 25.4 / 72, 424, places=2)

    def test_format_without_distortion_fits_proportionally_inside_a3_plus_four(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "image.pdf"
            document = fitz.open()
            page = document.new_page(width=mm(86.7), height=mm(130.1))
            page.draw_rect(page.rect, color=(1, 0, 0), fill=(0, 1, 0))
            document.save(source)
            document.close()

            output = root / "a3_plus_four_proportional.pdf"
            apply_geometry(
                source,
                output,
                GeometrySettings(
                    format=FormatSettings(301, 424, "center", False),
                ),
                [0],
            )
            info = inspect_geometry(output)
            with fitz.open(output) as result:
                artwork_rect = result[0].get_drawings()[0]["rect"]

        expected_scale = min(301 / 86.7, 424 / 130.1)
        expected_width = 86.7 * expected_scale
        self.assertAlmostEqual(info.pages[0].media.width_mm, 301, places=2)
        self.assertAlmostEqual(info.pages[0].media.height_mm, 424, places=2)
        self.assertAlmostEqual(info.pages[0].trim.width_mm, 301, places=2)
        self.assertAlmostEqual(info.pages[0].trim.height_mm, 424, places=2)
        self.assertAlmostEqual(
            artwork_rect.width * 25.4 / 72,
            expected_width,
            places=2,
        )
        self.assertAlmostEqual(artwork_rect.height * 25.4 / 72, 424, places=2)
        self.assertAlmostEqual(
            artwork_rect.x0 * 25.4 / 72,
            (301 - expected_width) / 2,
            places=2,
        )

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

    def test_rotates_only_selected_page_before_other_geometry_edits(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = create_pdf(root / "source.pdf")
            rotated = root / "rotated.pdf"
            resized = root / "resized.pdf"
            apply_geometry(
                source,
                rotated,
                GeometrySettings(rotation_degrees=90),
                [0],
            )
            rotated_info = inspect_geometry(rotated)
            apply_geometry(
                rotated,
                resized,
                GeometrySettings(format=FormatSettings(120, 220)),
                [0],
            )
            resized_info = inspect_geometry(resized)
            document = fitz.open(rotated)
            text = document[0].get_text()
            document.close()

        self.assertAlmostEqual(rotated_info.pages[0].media.width_mm, 56, places=2)
        self.assertAlmostEqual(rotated_info.pages[0].media.height_mm, 106, places=2)
        self.assertAlmostEqual(rotated_info.pages[1].media.width_mm, 106, places=2)
        self.assertAlmostEqual(rotated_info.pages[1].media.height_mm, 56, places=2)
        self.assertAlmostEqual(resized_info.pages[0].media.width_mm, 120, places=2)
        self.assertAlmostEqual(resized_info.pages[0].media.height_mm, 220, places=2)
        self.assertIn("Página 1", text)

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

    def test_fits_artwork_to_trim_proportionally_without_changing_boxes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = create_pdf(root / "source.pdf", pages=1)
            with pikepdf.Pdf.open(source, allow_overwriting_input=True) as pdf:
                page = pdf.pages[0]
                page.obj.BleedBox = pikepdf.Array(
                    [mm(1), mm(1), mm(105), mm(55)]
                )
                page.obj.ArtBox = pikepdf.Array(
                    [mm(4), mm(4), mm(102), mm(52)]
                )
                pdf.save(source)
            output = root / "output.pdf"
            before_info = inspect_geometry(source)
            with pikepdf.Pdf.open(source) as pdf:
                before_bleed = tuple(pdf.pages[0].obj.BleedBox)
                before_art = tuple(pdf.pages[0].obj.ArtBox)
            before_document = fitz.open(source)
            before_text = fitz.Rect(before_document[0].get_text("blocks")[0][:4])
            before_document.close()

            apply_geometry(
                source,
                output,
                GeometrySettings(
                    artwork_fit=ArtworkFitSettings(target="trim"),
                ),
                [0],
            )

            after_info = inspect_geometry(output)
            after_document = fitz.open(output)
            after_text = fitz.Rect(after_document[0].get_text("blocks")[0][:4])
            after_document.close()
            with pikepdf.Pdf.open(output) as pdf:
                after_bleed = tuple(pdf.pages[0].obj.BleedBox)
                after_art = tuple(pdf.pages[0].obj.ArtBox)

        expected_scale = 50 / 56
        self.assertEqual(before_info.pages[0].media, after_info.pages[0].media)
        self.assertEqual(before_info.pages[0].trim, after_info.pages[0].trim)
        self.assertEqual(before_bleed, after_bleed)
        self.assertEqual(before_art, after_art)
        self.assertAlmostEqual(
            after_text.width / before_text.width,
            expected_scale,
            places=2,
        )
        self.assertAlmostEqual(
            after_text.height / before_text.height,
            expected_scale,
            places=2,
        )

    def test_artwork_margin_is_validated(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = create_pdf(root / "source.pdf", pages=1)
            with self.assertRaisesRegex(GeometryError, "margem"):
                apply_geometry(
                    source,
                    root / "output.pdf",
                    GeometrySettings(
                        artwork_fit=ArtworkFitSettings(
                            target="trim",
                            margin_mm=25,
                        ),
                    ),
                    [0],
                )

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

    def test_crop_marks_use_trim_without_changing_page_boxes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = create_pdf(root / "source.pdf", pages=1)
            original = source.read_bytes()
            before = inspect_geometry(source)
            output = root / "output.pdf"
            apply_geometry(
                source,
                output,
                GeometrySettings(crop_marks=CropMarkSettings(
                    enabled=True,
                    offset_mm=3,
                    length_mm=5,
                    thickness_pt=0.25,
                )),
                [0],
            )
            info = inspect_geometry(output)
            self.assertEqual(source.read_bytes(), original)
            self.assertEqual(info.pages[0].media, before.pages[0].media)
            self.assertEqual(info.pages[0].trim, before.pages[0].trim)
            result = fitz.open(output)
            drawings = result[0].get_drawings()
            result.close()
            self.assertGreaterEqual(len(drawings), 9)

    def test_cleanup_removes_only_content_whose_bounds_are_outside_trim(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pdf"
            document = fitz.open()
            page = document.new_page(width=mm(106), height=mm(56))
            page.set_trimbox(fitz.Rect(mm(10), mm(10), mm(96), mm(46)))
            page.insert_text(fitz.Point(mm(20), mm(25)), "DENTRO")
            page.draw_line(
                fitz.Point(mm(20), mm(5)), fitz.Point(mm(30), mm(5))
            )
            page.draw_line(
                fitz.Point(mm(20), mm(51)), fitz.Point(mm(30), mm(51))
            )
            page.draw_rect(
                fitz.Rect(mm(20), mm(20), mm(30), mm(30))
            )
            document.save(source)
            document.close()
            output = root / "output.pdf"

            before_info = inspect_geometry(source)
            before = fitz.open(source)
            before_text = fitz.Rect(before[0].get_text("blocks")[0][:4])
            self.assertEqual(len(before[0].get_drawings()), 3)
            before.close()
            apply_geometry(
                source,
                output,
                GeometrySettings(remove_outside_trim=True),
                [0],
            )
            result = fitz.open(output)
            text = result[0].get_text()
            after_text = fitz.Rect(result[0].get_text("blocks")[0][:4])
            drawings = result[0].get_drawings()
            result.close()
            after_info = inspect_geometry(output)

        self.assertIn("DENTRO", text)
        self.assertEqual(len(drawings), 1)
        self.assertEqual(before_text, after_text)
        self.assertEqual(before_info.pages[0].media, after_info.pages[0].media)
        self.assertEqual(before_info.pages[0].trim, after_info.pages[0].trim)

    def test_cleanup_splits_grouped_crop_mark_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pdf"
            document = fitz.open()
            page = document.new_page(width=mm(106), height=mm(56))
            page.set_trimbox(fitz.Rect(mm(10), mm(10), mm(96), mm(46)))
            document.save(source)
            document.close()
            with pikepdf.Pdf.open(source, allow_overwriting_input=True) as pdf:
                page = pdf.pages[0]
                grouped_paths = pdf.make_stream(
                    (
                        "q 0 0 0 RG 0.25 w "
                        f"{mm(20)} {mm(5)} m {mm(30)} {mm(5)} l "
                        f"{mm(20)} {mm(51)} m {mm(30)} {mm(51)} l "
                        f"{mm(20)} {mm(20)} m {mm(30)} {mm(20)} l S Q\n"
                    ).encode("ascii")
                )
                page.obj.Contents = grouped_paths
                pdf.save(source)

            output = root / "output.pdf"
            apply_geometry(
                source,
                output,
                GeometrySettings(remove_outside_trim=True),
                [0],
            )
            result = fitz.open(output)
            line_items = [
                item
                for drawing in result[0].get_drawings()
                for item in drawing["items"]
                if item[0] == "l"
            ]
            result.close()

        self.assertEqual(len(line_items), 1)

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
