import unittest

from core.pdf_summary import build_job_summary


class PdfSummaryTests(unittest.TestCase):
    def test_builds_editable_work_order_description(self):
        info = {
            "nome": "Voucher_abordotours_2026.pdf",
            "paginas": 2,
            "boxes": [{"trim": (210.0, 200.0)}],
            "cores": {"CMYK": True},
        }
        self.assertEqual(
            build_job_summary(info),
            'Voucher "A Bordo Tours" no formato 210x200mm, '
            "impressos 4/4 cores",
        )

    def test_single_page_uses_front_only(self):
        info = {
            "nome": "Cartaz_Cliente.pdf",
            "paginas": 1,
            "boxes": [{"trim": (297.0, 420.0)}],
            "cores": {"CMYK": True},
        }
        self.assertTrue(build_job_summary(info).endswith("4/0 cores"))


if __name__ == "__main__":
    unittest.main()
