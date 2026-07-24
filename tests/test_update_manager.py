import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from core import update_manager
from core.update_manager import UpdateError, UpdatePackage


def create_update_zip(path: Path, files: dict[str, bytes]) -> Path:
    manifest = {
        "name": "Teste",
        "version": "1.0",
        "description": "Pacote de teste",
        "restart": False,
        "files": list(files),
    }
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("update.json", json.dumps(manifest))
        for relative, content in files.items():
            archive.writestr(relative, content)
    return path


class UpdateInspectionTests(unittest.TestCase):
    def test_accepts_valid_package(self):
        with tempfile.TemporaryDirectory() as directory:
            zip_path = create_update_zip(
                Path(directory) / "update.zip",
                {"core/example.py": b"new"},
            )
            package = update_manager.inspect_update(zip_path)
            self.assertEqual(package.files, ("core/example.py",))
            self.assertFalse(package.restart)

    def test_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as directory:
            zip_path = Path(directory) / "update.zip"
            manifest = {"files": ["../outside.py"]}
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.writestr("update.json", json.dumps(manifest))
                archive.writestr("../outside.py", "unsafe")
            with self.assertRaises(UpdateError):
                update_manager.inspect_update(zip_path)


class UpdateInstallationTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.backup_dir = self.root / "backup"
        self.zip_path = self.root / "package.zip"

        self.patches = [
            patch.object(update_manager, "PROJECT_ROOT", self.root),
            patch.object(update_manager, "BACKUP_DIR", self.backup_dir),
            patch.object(
                update_manager,
                "LAST_BACKUP",
                self.backup_dir / "ultimo_backup.zip",
            ),
            patch.object(
                update_manager,
                "_move_package_to_trash",
                return_value=(True, "package.zip"),
            ),
        ]
        for current_patch in self.patches:
            current_patch.start()

    def tearDown(self):
        for current_patch in reversed(self.patches):
            current_patch.stop()
        self.temporary_directory.cleanup()

    def package(self, files):
        create_update_zip(self.zip_path, files)
        return UpdatePackage(
            zip_path=self.zip_path,
            package_root="",
            name="Teste",
            version="1",
            description="",
            files=tuple(files),
            restart=False,
        )

    def test_installs_all_files_and_creates_backup(self):
        original = self.root / "core" / "existing.py"
        original.parent.mkdir(parents=True)
        original.write_bytes(b"old")
        original.chmod(0o755)
        package = self.package({
            "core/existing.py": b"new",
            "core/created.py": b"created",
        })

        installed = update_manager.install_update(package)

        self.assertEqual(installed, 2)
        self.assertEqual(original.read_bytes(), b"new")
        self.assertEqual(original.stat().st_mode & 0o777, 0o755)
        self.assertEqual(
            (self.root / "core" / "created.py").read_bytes(),
            b"created",
        )
        with zipfile.ZipFile(update_manager.LAST_BACKUP) as backup:
            self.assertEqual(backup.namelist(), ["core/existing.py"])

    def test_rolls_back_existing_and_new_files_after_failure(self):
        first = self.root / "first.py"
        second = self.root / "second.py"
        first.write_bytes(b"first-old")
        second.write_bytes(b"second-old")
        package = self.package({
            "first.py": b"first-new",
            "second.py": b"second-new",
            "created.py": b"created",
        })
        real_replace = os.replace

        def fail_on_second(source, destination):
            if (
                Path(destination).name == "second.py"
                and str(source).endswith(".m87_update_tmp")
            ):
                raise OSError("falha simulada")
            return real_replace(source, destination)

        with patch.object(update_manager.os, "replace", side_effect=fail_on_second):
            with self.assertRaises(UpdateError):
                update_manager.install_update(package)

        self.assertEqual(first.read_bytes(), b"first-old")
        self.assertEqual(second.read_bytes(), b"second-old")
        self.assertFalse((self.root / "created.py").exists())
        self.assertFalse((self.root / "first.py.m87_update_tmp").exists())
        self.assertFalse((self.root / "second.py.m87_update_tmp").exists())


if __name__ == "__main__":
    unittest.main()
