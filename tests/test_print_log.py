import json
import unittest
from unittest.mock import patch

from core.print_log import (
    PrintLogEntry,
    clean_record_name,
    extract_plans,
    make_entry,
    send_entries,
)
from core.pdf_rename import parse_production_name


class _Response:
    def __init__(self, data):
        self.data = json.dumps(data).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self):
        return self.data


class PrintLogTests(unittest.TestCase):
    def test_parses_imp_production_name(self):
        data = parse_production_name(
            "100un 4pl_Olin 400g_TROTINETE_Cartão de Visita_Beatriz_28072026.pdf"
        )
        self.assertIsNotNone(data)
        self.assertEqual((data.units, data.plans, data.per_sheet), (100, 4, 25))
        self.assertEqual(data.paper, "Olin 400g")
        self.assertEqual(data.base, "TROTINETE_Cartão de Visita_Beatriz")

    def test_parses_multi_artwork_imposition_name(self):
        data = parse_production_name(
            "250un 10p_Mat150g_Compra TicketLine_17082026.pdf"
        )
        self.assertIsNotNone(data)
        self.assertEqual((data.units, data.plans), (250, 10))

    def test_parses_legacy_multi_artwork_imposition_name(self):
        data = parse_production_name(
            "10un cada_20pl_Mat350g_Compra TicketLine_02082026.pdf"
        )
        self.assertIsNotNone(data)
        self.assertEqual((data.units, data.plans), (10, 20))

    def test_two_page_imposition_registers_ten_front_and_ten_back(self):
        entry = make_entry(
            "250un 10p_Mat150g_Cartão Loja Covilhã_17082026.pdf",
            2,
            plans=10,
        )
        self.assertEqual((entry.front, entry.back), (10, 10))

    def test_parses_legacy_renamed_file(self):
        data = parse_production_name(
            "# Convite - 101un 6Planos Mat 350g 29072026.pdf"
        )
        self.assertIsNotNone(data)
        self.assertEqual((data.units, data.plans, data.per_sheet), (101, 6, 17))
        self.assertEqual(data.base, "Convite")

    def test_cleans_hash_and_pdf_extension(self):
        self.assertEqual(clean_record_name("# Trabalho.pdf"), "Trabalho")

    def test_extracts_short_and_long_plan_formats(self):
        self.assertEqual(extract_plans("100un 5p_Cliente.pdf"), 5)
        self.assertEqual(extract_plans("100un 5pl_Cliente.pdf"), 5)
        self.assertEqual(extract_plans("# Cliente - 100un 8Planos Papel.pdf"), 8)

    def test_suggests_simplex_and_duplex_counts(self):
        simplex = make_entry("100un 5pl_Cliente.pdf", 1)
        duplex = make_entry("100un 5pl_Cliente.pdf", 2)
        self.assertEqual((simplex.front, simplex.back), (5, 0))
        self.assertEqual((duplex.front, duplex.back), (5, 5))

    @patch("core.print_log.urllib.request.urlopen")
    def test_sends_expected_payload(self, urlopen):
        urlopen.return_value = _Response({"ok": True, "count": 1})
        entry = PrintLogEntry("Cliente", 5, 5, 29)
        result = send_entries(
            "https://script.google.com/macros/s/example/exec",
            "secret",
            [entry],
        )
        self.assertTrue(result["ok"])
        request = urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["records"][0]["operator"], "Mariane")
        self.assertEqual(payload["records"][0]["front"], 5)


if __name__ == "__main__":
    unittest.main()
