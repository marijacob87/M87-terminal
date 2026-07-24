from __future__ import annotations

from datetime import datetime
from pathlib import Path
import zipfile


PROJECT_PATH = Path(__file__).resolve().parent.parent

EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".idea",
}

EXCLUDED_FILES = {
    ".DS_Store",
}

EXCLUDED_SUFFIXES = {
    ".pyc",
    ".pyo",
}


def _should_skip(path: Path, project_root: Path) -> bool:
    relative_parts = path.relative_to(project_root).parts

    if any(part in EXCLUDED_DIRS for part in relative_parts):
        return True

    if path.name in EXCLUDED_FILES:
        return True

    if path.suffix.lower() in EXCLUDED_SUFFIXES:
        return True

    return False


def create_project_zip() -> Path:
    """Cria no Desktop um ZIP limpo do projeto M87 Terminal."""
    project_root = PROJECT_PATH.expanduser()

    if not project_root.is_dir():
        raise FileNotFoundError(
            f"Pasta do projeto não encontrada: {project_root}"
        )

    desktop = Path.home() / "Desktop"
    desktop.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    destination = desktop / f"m87_terminal_{timestamp}.zip"

    with zipfile.ZipFile(
        destination,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=6,
    ) as archive:
        for path in sorted(project_root.rglob("*")):
            if _should_skip(path, project_root):
                continue

            if not path.is_file():
                continue

            archive_name = Path(project_root.name) / path.relative_to(
                project_root
            )
            archive.write(path, archive_name)

    return destination
