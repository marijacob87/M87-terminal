import hashlib
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import fitz
import pikepdf
from PIL import ImageCms

from core.pdf_preservation import (
    PdfPreservationError,
    preserve_output_intents,
)
from scripts.convert_pdf_to_curves import converter_pdf_em_curvas


def create_basic_pdf(path: Path) -> Path:
    document = fitz.open()
    page = document.new_page(width=300, height=200)
    page.insert_text(fitz.Point(30, 50), "M87 ICC")
    document.save(path)
    document.close()
    return path


def add_output_intent(path: Path, pdfx_version: str = "PDF/X-4") -> bytes:
    profile = ImageCms.ImageCmsProfile(
        ImageCms.createProfile("sRGB")
    ).tobytes()

    with pikepdf.Pdf.open(path, allow_overwriting_input=True) as pdf:
        stream = pdf.make_stream(profile)
        stream.N = 3
        stream.Alternate = pikepdf.Name.DeviceRGB

        intent = pdf.make_indirect(
            pikepdf.Dictionary({
                "/Type": pikepdf.Name.OutputIntent,
                "/S": pikepdf.Name.GTS_PDFX,
                "/OutputConditionIdentifier": "M87 synthetic sRGB",
                "/Info": "Perfil sintético para regressão",
                "/DestOutputProfile": stream,
            })
        )
        pdf.Root.OutputIntents = pikepdf.Array([intent])
        pdf.docinfo["/GTS_PDFXVersion"] = pdfx_version
        pdf.save(path)

    return profile


def output_profile(path: Path) -> bytes:
    with pikepdf.Pdf.open(path) as pdf:
        intent = pdf.Root.OutputIntents[0]
        return intent.DestOutputProfile.read_bytes()


class PdfPreservationTests(unittest.TestCase):
    def test_copies_output_intent_and_exact_icc_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = create_basic_pdf(root / "source.pdf")
            expected_profile = add_output_intent(source)
            output = create_basic_pdf(root / "output.pdf")

            result = preserve_output_intents(source, output)

            self.assertEqual(result.output_intents, 1)
            self.assertEqual(result.icc_profiles, 1)
            self.assertEqual(result.source_pdfx, "PDF/X-4")
            self.assertEqual(
                hashlib.sha256(output_profile(output)).digest(),
                hashlib.sha256(expected_profile).digest(),
            )
            with pikepdf.Pdf.open(output) as pdf:
                self.assertNotIn("/GTS_PDFXVersion", pdf.docinfo)
                self.assertNotIn("/GTS_PDFXConformance", pdf.docinfo)

    def test_leaves_output_untouched_when_source_has_no_intent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = create_basic_pdf(root / "source.pdf")
            output = create_basic_pdf(root / "output.pdf")
            before = output.read_bytes()

            result = preserve_output_intents(source, output)

            self.assertEqual(result.output_intents, 0)
            self.assertEqual(output.read_bytes(), before)

    def test_failure_does_not_replace_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "invalid.pdf"
            source.write_bytes(b"not a pdf")
            output = create_basic_pdf(root / "output.pdf")
            before = output.read_bytes()

            with self.assertRaises(PdfPreservationError):
                preserve_output_intents(source, output)

            self.assertEqual(output.read_bytes(), before)

    @unittest.skipUnless(shutil.which("gs"), "Ghostscript não instalado")
    def test_curves_preserves_icc_without_claiming_pdfx(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = create_basic_pdf(root / "source.pdf")
            expected_profile = add_output_intent(source, "PDF/X-1:2001")
            output = root / "curves.pdf"

            result = converter_pdf_em_curvas(str(source), str(output))

            self.assertTrue(result["ok"], result["message"])
            self.assertTrue(result["output_intent_preserved"])
            self.assertEqual(result["source_pdfx"], "PDF/X-1:2001")
            self.assertEqual(output_profile(output), expected_profile)
            with pikepdf.Pdf.open(output) as pdf:
                self.assertNotIn("/GTS_PDFXVersion", pdf.docinfo)

    @unittest.skipUnless(shutil.which("gs"), "Ghostscript não instalado")
    def test_curves_discards_output_when_icc_preservation_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = create_basic_pdf(root / "source.pdf")
            output = root / "curves.pdf"

            with patch(
                "scripts.convert_pdf_to_curves.preserve_output_intents",
                side_effect=PdfPreservationError("falha ICC simulada"),
            ):
                result = converter_pdf_em_curvas(str(source), str(output))

            self.assertFalse(result["ok"])
            self.assertIn("falha ICC simulada", result["message"])
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
