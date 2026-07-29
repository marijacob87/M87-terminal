import unittest
from unittest.mock import patch

from core import recent_folders


class RecentFoldersTests(unittest.TestCase):
    def test_sync_does_not_rewrite_unchanged_history(self):
        existing = [{"name": "Cliente", "path": "/Volumes/Trabalhos/Cliente"}]

        with (
            patch.object(
                recent_folders,
                "_finder_window_paths",
                return_value=["/Volumes/Trabalhos/Cliente"],
            ),
            patch.object(recent_folders, "_load_history", return_value=existing),
            patch.object(recent_folders.Path, "is_dir", return_value=True),
            patch.object(recent_folders, "_save_history") as save_history,
        ):
            self.assertEqual(recent_folders.sync_finder_history(), 1)

        save_history.assert_not_called()

    def test_sync_writes_all_changes_once(self):
        with (
            patch.object(
                recent_folders,
                "_finder_window_paths",
                return_value=["/Volumes/Trabalhos/A", "/Volumes/Trabalhos/B"],
            ),
            patch.object(recent_folders, "_load_history", return_value=[]),
            patch.object(recent_folders.Path, "is_dir", return_value=True),
            patch.object(recent_folders, "_save_history") as save_history,
        ):
            self.assertEqual(recent_folders.sync_finder_history(), 2)

        save_history.assert_called_once()
