import unittest
from pathlib import Path

from ui import design_tokens


class DesignSystemTests(unittest.TestCase):
    def test_shared_tool_metrics_come_from_tokens(self):
        source = (Path(__file__).parents[1] / "ui" / "tool_design.py").read_text()
        self.assertIn("from ui.design_tokens import", source)
        self.assertIn("TOOL_FIELD_HEIGHT = FIELD_HEIGHT", source)
        self.assertIn("TOOL_FOOTER_BUTTON_SIZE = FOOTER_BUTTON_SIZE", source)

    def test_approved_visual_parameters(self):
        self.assertEqual(design_tokens.COLOR_BACKGROUND, "#050607")
        self.assertEqual(design_tokens.COLOR_ACCENT, "#FFC400")
        self.assertEqual(design_tokens.FIELD_HEIGHT, 26)
        self.assertEqual(design_tokens.MEASURE_SWAP_FONT_SIZE, 15)
        self.assertEqual(design_tokens.MEASURE_SWAP_FONT_WEIGHT, 500)
        self.assertEqual(design_tokens.FOOTER_BUTTON_SIZE, (136, 28))
        self.assertEqual(design_tokens.SELECTION_INDICATOR_SCALE, .60)

    def test_every_pdf_tool_uses_the_shared_file_card(self):
        root = Path(__file__).resolve().parents[1]
        for relative in (
            "ui/pdf_summary_widget.py",
            "ui/organize_pages_widget.py",
            "ui/geometry_widget.py",
            "ui/colors_widget.py",
            "ui/imposition_dialog.py",
            "ui/manual_imposition_dialog.py",
        ):
            source = (root / relative).read_text(encoding="utf-8")
            self.assertIn("create_pdf_file_card(", source, relative)


if __name__ == "__main__":
    unittest.main()
