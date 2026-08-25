import unittest

from core.imposition_naming import filename_from_sheet_label, sheet_label_from_filename


class ImpositionNamingTests(unittest.TestCase):
    def test_sheet_label_updates_filename(self):
        label = "100un 10 Planos • Mat350g • Cartão Bónus Oficina • 17/08/2026"
        self.assertEqual(
            filename_from_sheet_label(label),
            "100un 10p_Mat350g_Cartão Bónus Oficina_17082026.pdf",
        )

    def test_filename_updates_sheet_label(self):
        filename = "100un 10p_Mat350g_Novo nome_17082026.pdf"
        self.assertEqual(
            sheet_label_from_filename(filename),
            "100un 10 Planos • Mat350g • Novo nome • 17/08/2026",
        )

    def test_filename_keeps_underscores_inside_job_name(self):
        filename = "100un 10p_Mat350g_Cartão_Bónus_Oficina_17082026.pdf"
        self.assertIn("Cartão_Bónus_Oficina", sheet_label_from_filename(filename))

    def test_reads_previous_filename_format(self):
        old_filename = "100un 10Planos_Mat350g_Nome_17082026.pdf"
        self.assertEqual(
            sheet_label_from_filename(old_filename),
            "100un 10 Planos • Mat350g • Nome • 17/08/2026",
        )


if __name__ == "__main__":
    unittest.main()
