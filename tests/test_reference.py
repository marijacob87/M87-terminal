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
