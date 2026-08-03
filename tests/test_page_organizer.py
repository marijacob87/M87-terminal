import tempfile
import unittest
from pathlib import Path

import fitz
import pikepdf

from core.page_organizer import (
    page_specs, reorder_pages, rotated, save_pages, split_pages,
)


class PageOrganizerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        self.source = self.folder / "source.pdf"
        with pikepdf.Pdf.new() as pdf:
            pdf.add_blank_page(page_size=(200, 300))
            pdf.add_blank_page(page_size=(400, 250))
            pdf.docinfo["/Title"] = "M87 test"
            pdf.save(self.source)

    def tearDown(self):
        self.temp.cleanup()

    def test_reorders_duplicates_and_rotates_pages(self):
        specs = page_specs(self.source)
        original_bytes = self.source.read_bytes()
        output = self.folder / "organized.pdf"
        save_pages(self.source, [specs[1], rotated(specs[0], 90), specs[1]], output)

        with pikepdf.Pdf.open(output) as pdf:
            self.assertEqual(len(pdf.pages), 3)
            self.assertEqual(list(pdf.pages[0].MediaBox), [0, 0, 400, 250])
            self.assertEqual(int(pdf.pages[1].obj.get("/Rotate", 0)), 0)
            self.assertEqual(list(pdf.pages[1].MediaBox), [0, 0, 300, 200])
            self.assertEqual(str(pdf.docinfo["/Title"]), "M87 test")
        with fitz.open(output) as pdf:
            self.assertEqual(pdf[1].rotation, 0)
            self.assertEqual((pdf[1].rect.width, pdf[1].rect.height), (300, 200))
        self.assertEqual(self.source.read_bytes(), original_bytes)

    def test_splits_by_page_count(self):
        specs = page_specs(self.source)
        outputs = split_pages(self.source, specs + specs, self.folder, 3)
        self.assertEqual([path.name for path in outputs], ["source_parte_01.pdf", "source_parte_02.pdf"])
        with pikepdf.Pdf.open(outputs[0]) as first, pikepdf.Pdf.open(outputs[1]) as second:
            self.assertEqual((len(first.pages), len(second.pages)), (3, 1))

    def test_split_never_overwrites_existing_pdf(self):
        existing = self.folder / "source_parte_01.pdf"
        existing.write_bytes(b"keep")
        outputs = split_pages(self.source, page_specs(self.source), self.folder, 2)
        self.assertEqual(outputs[0].name, "source_parte_01_2.pdf")
        self.assertEqual(existing.read_bytes(), b"keep")

    def test_reorder_is_atomic_when_dropped_on_another_page(self):
        pages = page_specs(self.source)
        original_count = len(pages)
        reordered, insertion = reorder_pages(pages, [0], 2)
        self.assertEqual(len(reordered), original_count)
        self.assertEqual(insertion, 1)
        self.assertEqual(reordered, [pages[1], pages[0]])


if __name__ == "__main__":
    unittest.main()
