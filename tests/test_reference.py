import json
import unittest

from core.config import APP_VERSION, COMMANDS_FILE, PROJECT_ROOT


REFERENCE_FILE = PROJECT_ROOT / "reference.json"


def _reference_codes(reference):
    codes = set()
    for section in reference.get("sections", []):
        codes.update(
            item.get("code")
            for item in section.get("items", [])
            if item.get("code")
        )
        for group in section.get("groups", []):
            codes.update(
                item.get("code")
                for item in group.get("items", [])
                if item.get("code")
            )
    return codes


class ReferenceConsistencyTests(unittest.TestCase):
    def setUp(self):
        self.commands = json.loads(COMMANDS_FILE.read_text(encoding="utf-8"))
        self.reference = json.loads(REFERENCE_FILE.read_text(encoding="utf-8"))

    def test_documents_every_visible_command(self):
        command_codes = {command["code"] for command in self.commands}
        missing = command_codes - _reference_codes(self.reference)
        self.assertEqual(missing, set())

    def test_version_matches_application(self):
        reference_version = self.reference["product"]["version"].lstrip("v")
        self.assertEqual(reference_version, APP_VERSION)

    def test_documents_shared_visual_system_without_obsolete_tab_shortcuts(self):
        sections = {section["id"]: section for section in self.reference["sections"]}
        self.assertIn("interface", sections)
        interface_codes = {item["code"] for item in sections["interface"]["items"]}
        self.assertTrue({"ABAS", "ARQUIVO", "SEM PDF", "PRÉVIA", "RODAPÉ"} <= interface_codes)
        shortcut_codes = _reference_codes(self.reference)
        for code in ("⌘F15", "⌘F16", "⌘F17", "⌘F18", "⌘F19"):
            self.assertNotIn(code, shortcut_codes)

    def test_section_ids_are_unique(self):
        section_ids = [section["id"] for section in self.reference["sections"]]
        self.assertEqual(len(section_ids), len(set(section_ids)))

    def test_notes_command_is_documented_but_stays_silent(self):
        self.assertIn("NOTAS", _reference_codes(self.reference))
        command_codes = {command["code"] for command in self.commands}
        self.assertNotIn("NOTAS", command_codes)

    def test_pdf_command_replaces_individual_pdf_tool_commands(self):
        command_codes = {command["code"] for command in self.commands}
        self.assertIn("PDF", command_codes)
        self.assertTrue({"GEO", "IMP", "ORG"}.isdisjoint(command_codes))
