import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import fitz
import pikepdf
from PIL import ImageCms

from core.imposition import (
    MM_TO_PT,
    ImpositionError,
    _bleed_destination,
    build_custom_layout,
    calculate_layouts,
    calculate_plans,
    export_imposition,
    inspect_pdf,
)
from core.pdf_info import analisar_pdf
from core.pdf_preservation import PdfPreservationError
from scripts.convert_pdf_to_curves import _page_geometry, _validate_output


def mm(value: float) -> float:
    return value * MM_TO_PT


def create_pdf(
    path: Path,
    page_count: int = 2,
    second_trim_width_mm: float | None = None,
) -> Path:
    document = fitz.open()

    for index in range(page_count):
        page = document.new_page(width=mm(106), height=mm(56))
        trim_width = (
            second_trim_width_mm
            if index == 1 and second_trim_width_mm is not None
            else 100
        )
        page.set_cropbox(fitz.Rect(0, 0, mm(106), mm(56)))
        page.set_bleedbox(fitz.Rect(0, 0, mm(106), mm(56)))
        page.set_trimbox(fitz.Rect(mm(3), mm(3), mm(3 + trim_width), mm(53)))
        page.set_artbox(fitz.Rect(mm(4), mm(4), mm(102), mm(52)))
        page.draw_rect(
            fitz.Rect(0, 0, mm(106), mm(56)),
            color=(0, 0, 1),
            fill=(0, 0, 1),
        )
        page.draw_rect(
            fitz.Rect(mm(3), mm(3), mm(103), mm(53)),
            color=(1, 0, 0),
            fill=(1, 0, 0),
        )
        page.insert_text(
            fitz.Point(mm(10), mm(20)),
            f"Página {index + 1}",
            fontsize=14,
            color=(1, 1, 1),
        )

    document.set_metadata({"title": "PDF sintético M87", "author": "Testes"})
    document.save(path)
    document.close()
    return path


def add_prepress_features(path: Path) -> bytes:
    profile = ImageCms.ImageCmsProfile(
        ImageCms.createProfile("sRGB")
    ).tobytes()

    with pikepdf.Pdf.open(path, allow_overwriting_input=True) as pdf:
        profile_stream = pdf.make_stream(profile)
        profile_stream.N = 3
        profile_stream.Alternate = pikepdf.Name.DeviceRGB
        intent = pdf.make_indirect(
            pikepdf.Dictionary({
                "/Type": pikepdf.Name.OutputIntent,
                "/S": pikepdf.Name.GTS_PDFX,
                "/OutputConditionIdentifier": "M87 synthetic profile",
                "/DestOutputProfile": profile_stream,
            })
        )
        pdf.Root.OutputIntents = pikepdf.Array([intent])
        pdf.docinfo["/GTS_PDFXVersion"] = "PDF/X-4"

        page = pdf.pages[0].obj
        resources = page.get("/Resources", pikepdf.Dictionary())
        page.Resources = resources
        color_spaces = resources.get("/ColorSpace", pikepdf.Dictionary())
        resources.ColorSpace = color_spaces
        tint_function = pdf.make_indirect(
            pikepdf.Dictionary({
                "/FunctionType": 2,
                "/Domain": pikepdf.Array([0, 1]),
                "/C0": pikepdf.Array([0, 0, 0, 0]),
                "/C1": pikepdf.Array([0, 1, 0, 0]),
                "/N": 1,
            })
        )
        color_spaces.M87Spot = pikepdf.Array([
            pikepdf.Name.Separation,
            pikepdf.Name("/CutContour"),
            pikepdf.Name.DeviceCMYK,
            tint_function,
        ])

        ext_gstate = resources.get("/ExtGState", pikepdf.Dictionary())
        resources.ExtGState = ext_gstate
        ext_gstate.M87Alpha = pikepdf.Dictionary({
            "/Type": pikepdf.Name.ExtGState,
            "/ca": 0.5,
            "/CA": 0.5,
        })
        extra_content = pdf.make_stream(
            b"q /M87Alpha gs /M87Spot cs 1 scn 20 20 40 20 re f Q"
        )
        contents = page.get("/Contents")
        if contents is None:
            page.Contents = extra_content
        elif isinstance(contents, pikepdf.Array):
            contents.append(extra_content)
        else:
            page.Contents = pikepdf.Array([contents, extra_content])

        pdf.save(path)

    return profile


class PdfInspectionTests(unittest.TestCase):
    def test_reads_trim_bleed_and_page_count(self):
        with tempfile.TemporaryDirectory() as directory:
            source = create_pdf(Path(directory) / "source.pdf")
            geometry = inspect_pdf(source)

        self.assertEqual(geometry.page_count, 2)
        self.assertAlmostEqual(geometry.trim_width_mm, 100, places=2)
        self.assertAlmostEqual(geometry.trim_height_mm, 50, places=2)
        self.assertAlmostEqual(geometry.bleed_left_mm, 3, places=2)
        self.assertAlmostEqual(geometry.bleed_top_mm, 3, places=2)
        self.assertAlmostEqual(geometry.bleed_right_mm, 3, places=2)
        self.assertAlmostEqual(geometry.bleed_bottom_mm, 3, places=2)
        self.assertTrue(geometry.has_minimum_bleed)

    def test_rejects_different_trim_boxes(self):
        with tempfile.TemporaryDirectory() as directory:
            source = create_pdf(
                Path(directory) / "different.pdf",
                second_trim_width_mm=99,
            )
            with self.assertRaisesRegex(
                ImpositionError,
                "TrimBox diferentes",
            ):
                inspect_pdf(source)

    def test_geometry_validator_detects_box_change(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = create_pdf(root / "source.pdf", page_count=1)
            changed = create_pdf(root / "changed.pdf", page_count=1)
            document = fitz.open(changed)
            document[0].set_trimbox(
                fitz.Rect(mm(4), mm(3), mm(103), mm(53))
            )
            document.save(root / "changed-saved.pdf")
            document.close()

            valid, message = _validate_output(
                source,
                root / "changed-saved.pdf",
            )

        self.assertFalse(valid)
        self.assertIn("TrimBox", message)

    def test_geometry_reader_includes_all_prepress_boxes(self):
        with tempfile.TemporaryDirectory() as directory:
            source = create_pdf(Path(directory) / "source.pdf", page_count=1)
            geometry = _page_geometry(source)

        self.assertEqual(
            set(geometry[0]),
            {"/MediaBox", "/CropBox", "/TrimBox", "/BleedBox", "/ArtBox"},
        )
        self.assertTrue(all(value is not None for value in geometry[0].values()))

    def test_complete_analysis_reports_boxes_color_and_preview(self):
        with tempfile.TemporaryDirectory() as directory:
            source = create_pdf(Path(directory) / "source.pdf", page_count=1)
            info = analisar_pdf(str(source))

        self.assertEqual(info["paginas"], 1)
        self.assertEqual(info["medida_pdf"], "106.0 mm x 56.0 mm")
        self.assertEqual(info["medida_trim"], "100.0 mm x 50.0 mm")
        self.assertTrue(info["tem_trim"])
        self.assertTrue(info["tem_bleed"])
        self.assertTrue(info["cores"]["RGB"])
        self.assertTrue(info["preview_png"].startswith(b"\x89PNG"))


class LayoutTests(unittest.TestCase):
    def test_layouts_are_sorted_by_capacity(self):
        options = calculate_layouts(320, 450, 100, 50, 2, 10)
        self.assertTrue(options)
        self.assertGreaterEqual(options[0].total, options[-1].total)
        self.assertTrue(all(option.total > 0 for option in options))

    def test_custom_layout_rejects_grid_outside_paper(self):
        self.assertIsNone(
            build_custom_layout(210, 297, 100, 100, 5, 10, 3, 3, False)
        )

    def test_plan_rules_for_repeat_and_sequential_modes(self):
        self.assertEqual(calculate_plans("repeat", 10, 4, 101), 26)
        self.assertEqual(calculate_plans("sequential", 10, 4, 3), 9)

    def test_asymmetric_bleed_rotates_clockwise(self):
        trim = fitz.Rect(10, 20, 110, 70)
        bleed = fitz.Rect(9, 18, 113, 74)
        destination = fitz.Rect(200, 300, 250, 400)

        normal = _bleed_destination(destination, trim, bleed, False)
        rotated = _bleed_destination(destination, trim, bleed, True)

        self.assertEqual(tuple(normal), (199, 298, 253, 404))
        self.assertEqual(tuple(rotated), (196, 299, 252, 403))


class ExportTests(unittest.TestCase):
    def _layout(self, rotated=False):
        layout = build_custom_layout(
            paper_width_mm=210,
            paper_height_mm=297,
            trim_width_mm=100,
            trim_height_mm=50,
            gutter_mm=2,
            margin_mm=10,
            columns=1,
            rows=2,
            rotated=rotated,
        )
        self.assertIsNotNone(layout)
        return layout

    def test_sequential_export_has_expected_pages_and_sheet_size(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = create_pdf(root / "source.pdf", page_count=2)
            output = root / "output.pdf"

            summary = export_imposition(
                source,
                output,
                self._layout(),
                gutter_mm=2,
                mode="sequential",
                quantity_each=3,
                crop_marks=True,
                identify_sheets=True,
                sheet_label="Teste M87",
            )

            document = fitz.open(output)
            try:
                self.assertEqual(document.page_count, 1)
                self.assertAlmostEqual(
                    document[0].mediabox.width,
                    mm(210),
                    places=2,
                )
                self.assertAlmostEqual(
                    document[0].mediabox.height,
                    mm(297),
                    places=2,
                )
                self.assertEqual(document.metadata["title"], "PDF sintético M87")
                self.assertEqual(document.metadata["author"], "Testes")
                self.assertGreater(len(document[0].get_drawings()), 0)
            finally:
                document.close()

        self.assertEqual(summary.imposed_pages, 1)
        self.assertEqual(summary.plans, 3)
        self.assertEqual(summary.items_per_sheet, 2)

    def test_rotated_repeat_export_remains_vector_and_readable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = create_pdf(root / "source.pdf", page_count=1)
            output = root / "rotated.pdf"

            summary = export_imposition(
                source,
                output,
                self._layout(rotated=True),
                gutter_mm=2,
                mode="repeat",
                quantity_each=10,
                crop_marks=False,
                identify_sheets=False,
            )

            document = fitz.open(output)
            try:
                self.assertEqual(document.page_count, 1)
                self.assertIn("Página 1", document[0].get_text())
                self.assertEqual(len(document[0].get_images(full=True)), 0)
            finally:
                document.close()

        self.assertEqual(summary.plans, 5)

    def test_preserves_icc_spot_and_transparency_without_claiming_pdfx(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = create_pdf(root / "prepress.pdf", page_count=1)
            expected_profile = add_prepress_features(source)
            output = root / "prepress-imposed.pdf"

            summary = export_imposition(
                source,
                output,
                self._layout(),
                gutter_mm=2,
                mode="repeat",
                quantity_each=2,
                crop_marks=False,
                identify_sheets=False,
            )

            with pikepdf.Pdf.open(output) as document:
                profile = (
                    document.Root.OutputIntents[0]
                    .DestOutputProfile.read_bytes()
                )
                objects = "\n".join(str(item) for item in document.objects)
                self.assertEqual(profile, expected_profile)
                self.assertIn("/CutContour", objects)
                self.assertIn('"/ExtGState"', objects)
                self.assertIn("Decimal('.5')", objects)
                self.assertNotIn("/GTS_PDFXVersion", document.docinfo)

        self.assertTrue(summary.output_intent_preserved)
        self.assertEqual(summary.source_pdfx, "PDF/X-4")

    def test_discards_imposition_when_icc_preservation_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = create_pdf(root / "source.pdf", page_count=1)
            output = root / "output.pdf"

            with patch(
                "core.imposition.preserve_output_intents",
                side_effect=PdfPreservationError("falha ICC simulada"),
            ):
                with self.assertRaisesRegex(
                    ImpositionError,
                    "falha ICC simulada",
                ):
                    export_imposition(
                        source,
                        output,
                        self._layout(),
                        gutter_mm=2,
                        mode="repeat",
                        quantity_each=1,
                    )

            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
