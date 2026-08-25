from __future__ import annotations

import json
import platform
import subprocess
from pathlib import Path


UNAVAILABLE_HISTORY = "Histórico não disponível"


def read_reference(root: Path) -> dict:
    try:
        data = json.loads((root / "reference.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def reference_items(root: Path, section_id: str) -> list:
    data = read_reference(root)
    section = next(
        (
            item
            for item in data.get("sections", [])
            if item.get("id") == section_id
        ),
        {},
    )
    items = list(section.get("items", []))
    for group in section.get("groups", []):
        items.extend(group.get("items", []))
    return items


def reference_product(root: Path) -> dict:
    product = read_reference(root).get("product", {})
    return product if isinstance(product, dict) else {}


def latest_git_commit(root: Path) -> str:
    try:
        result = subprocess.run(
            [
                "git", "-C", str(root), "log", "-1",
                "--date=format:%d/%m/%Y %H:%M",
                "--pretty=format:%h · %ad · %s",
            ],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        return result.stdout.strip() or UNAVAILABLE_HISTORY
    except (OSError, subprocess.SubprocessError):
        return UNAVAILABLE_HISTORY


def git_entries(root: Path, limit: int = 80) -> list[tuple[str, str]]:
    try:
        result = subprocess.run(
            [
                "git", "-C", str(root), "log",
                "--date=format:%d/%m/%Y",
                "--pretty=format:%ad%x1f%s%x1e", "-n", str(limit),
            ],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if result.returncode != 0 or not result.stdout.strip():
        return []

    entries = []
    for record in result.stdout.split("\x1e"):
        record = record.strip()
        if not record or "\x1f" not in record:
            continue
        date_text, subject = record.split("\x1f", 1)
        entries.append((date_text.strip(), subject.strip()))
    return entries


def system_info(root: Path, app_version: str) -> str:
    mac_version = platform.mac_ver()[0] or platform.release()
    return (
        f"Instalação: {root}\n"
        f"macOS {mac_version} · {platform.machine()} · "
        f"Python {platform.python_version()} · M87 v{app_version}"
    )
