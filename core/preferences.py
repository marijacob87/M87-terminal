from pathlib import Path

from PySide6.QtCore import QSettings


def settings_store() -> QSettings:
    return QSettings("M87Tools", "M87Terminal")


def preference(key: str, default=False, *, value_type=bool):
    return settings_store().value(key, default, type=value_type)


def save_path(default_path: str | Path) -> str:
    default = Path(default_path).expanduser()
    folder = str(settings_store().value("general/default_save_folder", "")).strip()
    if not folder:
        return str(default)
    target = Path(folder).expanduser()
    if not target.is_dir():
        return str(default)
    return str(target / default.name)
