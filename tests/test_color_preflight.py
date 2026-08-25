import tempfile
import unittest
import shutil
import subprocess
from unittest.mock import patch
from pathlib import Path

import fitz
import pikepdf
from PIL import Image, ImageChops
from io import BytesIO

from core.color_preflight import (
    FOGRA39_LABEL, PREVIEW_MAX_EDGE, ColorPreflightError, analyze_color_preflight,
    available_profiles, convert_pdf_to_cmyk,
    find_ghostscript, find_profile, render_separation_preview,
)
from core.color_preflight import _compose_psd_preview, _postscript_name


def create_preflight_pdf(path: Path) -> Path:
    document = fitz.open()
    page = document.new_page(width=300, height=200)
    page.insert_text((25, 35), "M87 COLOR")
    pixmap = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 20, 20), False)
    pixmap.clear_with(180)
    page.insert_image(fitz.Rect(25, 50, 169, 194), pixmap=pixmap)
    document.save(path)
    document.close()
    return path


def create_spot_pdf(path: Path) -> Path:
    document = fitz.open()
    document.new_page(width=200, height=120)
    document.save(path)
    document.close()
    with pikepdf.Pdf.open(path, allow_overwriting_input=True) as pdf:
        page = pdf.pages[0].obj
        resources = pikepdf.Dictionary()
        tint = pdf.make_indirect(pikepdf.Dictionary({
            "/FunctionType": 2,
            "/Domain": pikepdf.Array([0, 1]),
            "/C0": pikepdf.Array([0, 0, 0, 0]),
            "/C1": pikepdf.Array([0, 1, 0, 0]),
            "/N": 1,
        }))
        resources.ColorSpace = pikepdf.Dictionary({
            "/M87Spot": pikepdf.Array([
                pikepdf.Name.Separation,
                pikepdf.Name("/M87Spot"),
                pikepdf.Name.DeviceCMYK,
                tint,
            ])
        })
        page.Resources = resources
        page.Contents = pdf.make_stream(
            b"q /M87Spot cs 1 scn 40 30 120 60 re f Q"
        )
        pdf.save(path)
    return path


def create_multi_spot_pdf(path: Path) -> Path:
    document = fitz.open()
    document.new_page(width=320, height=160)
    document.save(path)
    document.close()
    specs = (
        ("COBRE", (0.0, 0.55, 0.8, 0.25)),
        ("PANTONE 116 C", (0.0, 0.2, 1.0, 0.0)),
        ("PANTONE 1795 C", (0.0, 0.95, 0.8, 0.0)),
        ("PANTONE 1807 C", (0.15, 0.9, 0.65, 0.25)),
    )
    with pikepdf.Pdf.open(path, allow_overwriting_input=True) as pdf:
        page = pdf.pages[0].obj
        spaces = pikepdf.Dictionary()
        commands = []
        for index, (name, cmyk) in enumerate(specs):
            function = pdf.make_indirect(pikepdf.Dictionary({
                "/FunctionType": 2,
                "/Domain": pikepdf.Array([0, 1]),
                "/C0": pikepdf.Array([0, 0, 0, 0]),
                "/C1": pikepdf.Array(cmyk),
                "/N": 1,
            }))
            resource = f"/Spot{index}"
            spaces[resource] = pikepdf.Array([
                pikepdf.Name.Separation, pikepdf.Name("/" + name),
                pikepdf.Name.DeviceCMYK, function,
            ])
            commands.append(
                f"q {resource} cs 1 scn {20 + index * 75} 40 55 80 re f Q"
            )
        page.Resources = pikepdf.Dictionary({"/ColorSpace": spaces})
        page.Contents = pdf.make_stream("\n".join(commands).encode("ascii"))
        pdf.save(path)
    return path


def create_process_plates_pdf(path: Path) -> Path:
    document = fitz.open()
    page = document.new_page(width=320, height=160)
    document.save(path)
    document.close()
    with pikepdf.Pdf.open(path, allow_overwriting_input=True) as pdf:
        pdf.pages[0].obj.Contents = pdf.make_stream(
            b"0 0 0 0 k 0 0 320 160 re f\n"
            b"1 0 0 0 k 20 40 55 80 re f\n"
            b"0 1 0 0 k 95 40 55 80 re f\n"
            b"0 0 1 0 k 170 40 55 80 re f\n"
            b"0 0 0 1 k 245 40 55 80 re f\n"
        )
        pdf.save(path)
    return path


def create_composite_black_pdf(path: Path) -> Path:
    document = fitz.open()
    document.new_page(width=160, height=100)
    document.save(path)
    document.close()
    with pikepdf.Pdf.open(path, allow_overwriting_input=True) as pdf:
        pdf.pages[0].obj.Contents = pdf.make_stream(
            b"0 0 0 0 k 0 0 160 100 re f\n"
            b"0.55 0.45 0.45 0.9 k 20 20 120 60 re f\n"
        )
        pdf.save(path)
    return path


class ColorPreflightTests(unittest.TestCase):
    def test_colorants_are_encoded_as_postscript_names(self):
        self.assertEqual(_postscript_name("Black"), "/Black")
        self.assertEqual(_postscript_name("PANTONE 116 C"), "(PANTONE 116 C) cvn")
        self.assertEqual(_postscript_name("COBRÉ"), r"(COBR\303\211) cvn")

    def test_unselected_spot_planes_returned_by_ghostscript_are_ignored(self):
        profile = find_profile(FOGRA39_LABEL)
        if profile is None:
            self.skipTest("Coated FOGRA39 não instalado")
        paper = Image.new("L", (8, 8), 255)
        ink = Image.new("L", (8, 8), 0)
        metadata = (
            (8, 8), [paper] * 4 + [ink, ink],
            ["PANTONE 2768 C", "PANTONE 871 C"],
            [(1.0, 0.8, 0.0, 0.2), (0.0, 0.3, 1.0, 0.2)],
            profile.read_bytes(),
        )
        with patch("core.color_preflight._read_raw_psd_planes", return_value=metadata):
            preview = _compose_psd_preview(
                Path("unused.psd"), set(), ["PANTONE 2768 C"],
            )

        self.assertNotEqual(preview.getpixel((4, 4)), (255, 255, 255))

    def test_colors_tab_uses_shared_preview_tools_and_folds_gray_into_k(self):
        source = (
            Path(__file__).parents[1] / "ui" / "colors_widget.py"
        ).read_text(encoding="utf-8")

        self.assertIn("ToolPreviewToolbar", source)
        self.assertIn('(channel, "CMYK") for channel in ("C", "M", "Y", "K")', source)
        self.assertNotIn('names.append(("Cinza", "CMYK"))', source)
        self.assertIn("spot/Pantone", source)
        self.assertIn("pdfDropped = Signal(object)", source)
        self.assertIn('QCheckBox("CMYK · TODAS")', source)
        self.assertIn("def _toggle_all_cmyk", source)

    def test_finds_homebrew_ghostscript_without_a_shell_path(self):
        homebrew = Path("/opt/homebrew/bin/gs")
        if not homebrew.is_file():
            self.skipTest("Ghostscript Homebrew não instalado")
        with patch("core.color_preflight.shutil.which", return_value=None):
            self.assertEqual(find_ghostscript(), str(homebrew))

    def test_reports_low_resolution_image_and_profile_state(self):
        with tempfile.TemporaryDirectory() as directory:
            source = create_preflight_pdf(Path(directory) / "source.pdf")
            report = analyze_color_preflight(source)

            self.assertEqual(report["pages"], 1)
            self.assertTrue(report["colors"]["RGB"])
            self.assertEqual(report["profile_name"], "Sem OutputIntent/ICC de saída")
            self.assertEqual(len(report["low_resolution"]), 1)
            self.assertAlmostEqual(report["low_resolution"][0]["dpi"], 10.0, places=1)
            self.assertEqual(report["low_resolution"][0]["page"], 1)

    def test_refuses_to_overwrite_source(self):
        with tempfile.TemporaryDirectory() as directory:
            source = create_preflight_pdf(Path(directory) / "source.pdf")
            with self.assertRaises(ColorPreflightError):
                convert_pdf_to_cmyk(source, source, FOGRA39_LABEL)

    def test_fogra39_profile_is_available_on_production_mac(self):
        profile = available_profiles()[FOGRA39_LABEL]
        if profile is not None:
            self.assertTrue(Path(profile).is_file())

    def test_output_boxes_are_read_without_mutating_source(self):
        with tempfile.TemporaryDirectory() as directory:
            source = create_preflight_pdf(Path(directory) / "source.pdf")
            before = source.read_bytes()
            analyze_color_preflight(source)
            self.assertEqual(source.read_bytes(), before)
            with pikepdf.Pdf.open(source) as pdf:
                self.assertEqual(len(pdf.pages), 1)

    @unittest.skipUnless(shutil.which("gs"), "Ghostscript não instalado")
    def test_separation_preview_really_removes_black_plate(self):
        with tempfile.TemporaryDirectory() as directory:
            source = create_preflight_pdf(Path(directory) / "source.pdf")
            with_black = Image.open(BytesIO(render_separation_preview(
                source, 1, ("Cyan", "Magenta", "Yellow", "Black"), dpi=72,
            ))).convert("RGB")
            without_black = Image.open(BytesIO(render_separation_preview(
                source, 1, ("Cyan", "Magenta", "Yellow"), dpi=72,
            ))).convert("RGB")

            self.assertIsNotNone(ImageChops.difference(
                with_black, without_black,
            ).getbbox())

    @unittest.skipUnless(shutil.which("gs"), "Ghostscript não instalado")
    def test_black_plate_is_zeroed_even_in_composite_black(self):
        with tempfile.TemporaryDirectory() as directory:
            source = create_composite_black_pdf(Path(directory) / "composite.pdf")
            all_plates = Image.open(BytesIO(render_separation_preview(
                source, 1, ("Cyan", "Magenta", "Yellow", "Black"), dpi=72,
            ))).convert("RGB")
            no_black = Image.open(BytesIO(render_separation_preview(
                source, 1, ("Cyan", "Magenta", "Yellow"), dpi=72,
            ))).convert("RGB")

            self.assertNotEqual(all_plates.getpixel((80, 50)), no_black.getpixel((80, 50)))
            self.assertNotEqual(no_black.getpixel((80, 50)), (255, 255, 255))

    @unittest.skipUnless(shutil.which("gs"), "Ghostscript não instalado")
    def test_spot_preview_is_composed_without_multichannel_tiff_stripes(self):
        with tempfile.TemporaryDirectory() as directory:
            source = create_spot_pdf(Path(directory) / "spot.pdf")
            preview = Image.open(BytesIO(render_separation_preview(
                source, 1, ("M87Spot",), dpi=72,
            ))).convert("RGB")

            corner = preview.getpixel((10, 10))
            self.assertTrue(all(value >= 225 for value in corner))
            red, green, blue = preview.getpixel((50, 60))
            self.assertGreater(red, green)
            self.assertGreater(blue, green)

    @unittest.skipUnless(shutil.which("gs"), "Ghostscript não instalado")
    def test_four_named_spots_render_together_and_as_a_subset(self):
        with tempfile.TemporaryDirectory() as directory:
            source = create_multi_spot_pdf(Path(directory) / "spots.pdf")
            names = ("COBRE", "PANTONE 116 C", "PANTONE 1795 C", "PANTONE 1807 C")
            all_spots = Image.open(BytesIO(render_separation_preview(
                source, 1, names, dpi=72,
            ))).convert("RGB")
            pantone_116 = Image.open(BytesIO(render_separation_preview(
                source, 1, ("PANTONE 116 C",), dpi=72,
            ))).convert("RGB")

            self.assertIsNotNone(ImageChops.difference(all_spots, pantone_116).getbbox())
            self.assertNotEqual(all_spots.getpixel((45, 80)), (255, 255, 255))
            self.assertEqual(pantone_116.getpixel((45, 80)), (255, 255, 255))
            self.assertNotEqual(pantone_116.getpixel((120, 80)), (255, 255, 255))

    @unittest.skipUnless(shutil.which("gs"), "Ghostscript não instalado")
    def test_each_process_plate_can_be_isolated(self):
        with tempfile.TemporaryDirectory() as directory:
            source = create_process_plates_pdf(Path(directory) / "process.pdf")
            samples = {
                "Cyan": (45, 80), "Magenta": (120, 80),
                "Yellow": (195, 80), "Black": (270, 80),
            }
            for selected, coordinate in samples.items():
                with self.subTest(selected=selected):
                    preview = Image.open(BytesIO(render_separation_preview(
                        source, 1, (selected,), dpi=72,
                    ))).convert("RGB")
                    self.assertNotEqual(preview.getpixel(coordinate), (255, 255, 255))
                    for other, other_coordinate in samples.items():
                        if other != selected:
                            self.assertEqual(
                                preview.getpixel(other_coordinate), (255, 255, 255)
                            )

    @unittest.skipUnless(shutil.which("gs"), "Ghostscript não instalado")
    def test_complete_preview_uses_the_same_icc_color_conversion(self):
        profile = find_profile(FOGRA39_LABEL)
        srgb = Path("/System/Library/ColorSync/Profiles/sRGB Profile.icc")
        if profile is None or not srgb.is_file():
            self.skipTest("Perfis FOGRA39/sRGB não disponíveis")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = create_process_plates_pdf(root / "source.pdf")
            converted = root / "fogra.pdf"
            reference = root / "reference.png"
            convert_pdf_to_cmyk(source, converted, FOGRA39_LABEL)

            preview = Image.open(BytesIO(render_separation_preview(
                converted, 1, ("Cyan", "Magenta", "Yellow", "Black"), dpi=144,
            ))).convert("RGB")
            subprocess.run([
                find_ghostscript(), "-dSAFER", "-dBATCH", "-dNOPAUSE", "-dQUIET",
                "-sDEVICE=png16m", "-r144",
                f"-sDefaultCMYKProfile={profile}", f"-sOutputICCProfile={srgb}",
                f"-sOutputFile={reference}", str(converted),
            ], check=True)
            baseline = Image.open(reference).convert("RGB")

            self.assertIsNone(ImageChops.difference(preview, baseline).getbbox())

    @unittest.skipUnless(shutil.which("gs"), "Ghostscript não instalado")
    def test_preview_caps_extremely_wide_pages_for_qt_texture_safety(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "wide.pdf"
            document = fitz.open()
            document.new_page(width=12000, height=1000)
            document.save(source)
            document.close()

            preview = Image.open(BytesIO(render_separation_preview(
                source, 1, ("Black",), dpi=180,
            )))

            self.assertLessEqual(max(preview.size), PREVIEW_MAX_EDGE + 1)

    @unittest.skipUnless(Path("/opt/homebrew/bin/gs").is_file(), "Ghostscript Homebrew ausente")
    def test_separation_preview_works_with_finder_like_path(self):
        with tempfile.TemporaryDirectory() as directory:
            source = create_preflight_pdf(Path(directory) / "source.pdf")
            with patch.dict("os.environ", {"PATH": "/usr/bin:/bin"}, clear=False):
                preview = render_separation_preview(
                    source, 1, ("Cyan", "Magenta", "Yellow", "Black"), dpi=72,
                )

            self.assertTrue(preview.startswith(b"\x89PNG"))

    @unittest.skipUnless(shutil.which("gs"), "Ghostscript não instalado")
    def test_conversion_keeps_effective_dpi_and_installs_output_intent(self):
        if available_profiles()[FOGRA39_LABEL] is None:
            self.skipTest("Coated FOGRA39 não instalado")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = create_preflight_pdf(root / "source.pdf")
            output = root / "output.pdf"
            before = analyze_color_preflight(source)

            result = convert_pdf_to_cmyk(source, output, FOGRA39_LABEL)
            after = analyze_color_preflight(output)

            self.assertTrue(output.is_file())
            self.assertEqual(result["minimum_dpi"], before["images"][0]["dpi"])
            self.assertEqual(after["pages"], before["pages"])
            self.assertTrue(after["output_intents"])
            self.assertIn("FOGRA39", after["output_intents"][0]["identifier"])


if __name__ == "__main__":
    unittest.main()
