import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from core.project_metadata import (
    UNAVAILABLE_HISTORY,
    git_entries,
    latest_git_commit,
    reference_items,
    reference_product,
)


class ProjectMetadataTests(unittest.TestCase):
    def test_reads_product_and_grouped_reference_items(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = {
                "product": {"name": "M87"},
                "sections": [{
                    "id": "atalhos",
                    "items": [{"code": "A"}],
                    "groups": [{"items": [{"code": "B"}]}],
                }],
            }
            (root / "reference.json").write_text(json.dumps(data))

            self.assertEqual(reference_product(root), {"name": "M87"})
            self.assertEqual(
                reference_items(root, "atalhos"),
                [{"code": "A"}, {"code": "B"}],
            )

    @patch("core.project_metadata.subprocess.run")
    def test_parses_git_history_without_ui_dependency(self, run):
        run.return_value = Mock(
            returncode=0,
            stdout="20/08/2026\x1fRefatora estrutura\x1e",
        )

        self.assertEqual(
            git_entries(Path("/project")),
            [("20/08/2026", "Refatora estrutura")],
        )

    @patch("core.project_metadata.subprocess.run", side_effect=OSError)
    def test_unavailable_latest_commit_keeps_existing_message(self, _run):
        self.assertEqual(
            latest_git_commit(Path("/project")),
            UNAVAILABLE_HISTORY,
        )


if __name__ == "__main__":
    unittest.main()
