import tempfile
import unittest
from pathlib import Path

from core.konica_spool import KonicaSpoolError, send_pdf_to_hold


class KonicaSpoolTests(unittest.TestCase):
    def test_copies_pdf_without_overwriting_existing_job(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "job.pdf"
            source.write_bytes(b"%PDF-test")
            hold = root / "hold"
            hold.mkdir()
            (hold / "job.pdf").write_bytes(b"existing")

            destination = send_pdf_to_hold(source, hold)

            self.assertEqual(destination.name, "job (2).pdf")
            self.assertEqual(destination.read_bytes(), b"%PDF-test")
            self.assertEqual((hold / "job.pdf").read_bytes(), b"existing")
            self.assertFalse(any(path.suffix == ".upload" for path in hold.iterdir()))

    def test_rejects_non_pdf_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "job.txt"
            source.write_text("not a pdf")
            with self.assertRaises(KonicaSpoolError):
                send_pdf_to_hold(source, Path(temporary))
