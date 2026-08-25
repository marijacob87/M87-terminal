from __future__ import annotations

import os
import plistlib
import subprocess
import sys
from pathlib import Path

from core.config import PROJECT_ROOT


CANONICAL_APP = Path("/Applications/M87 Terminal.app")
BUNDLE_IDENTIFIER = "com.m87tools.terminal"


def _canonical_launcher() -> Path | None:
    info_path = CANONICAL_APP / "Contents" / "Info.plist"
    try:
        with info_path.open("rb") as stream:
            info = plistlib.load(stream)
    except (OSError, plistlib.InvalidFileException):
        return None
    if info.get("CFBundleIdentifier") != BUNDLE_IDENTIFIER:
        return None
    if Path(info.get("M87ProjectRoot", "")).resolve() != Path(PROJECT_ROOT).resolve():
        return None
    executable_name = info.get("CFBundleExecutable", "M87 Terminal")
    executable = CANONICAL_APP / "Contents" / "MacOS" / executable_name
    return executable if executable.is_file() else None


def restart_command(
    executable: str | None = None,
    project_root: str | os.PathLike[str] | None = None,
) -> tuple[str, list[str]]:
    """Cria um reinício previsível sem depender dos argumentos do launcher."""
    if executable is None and project_root is None:
        launcher = _canonical_launcher()
        if launcher is not None:
            return str(launcher), [str(launcher)]
    python = executable or sys.executable
    root = Path(project_root or PROJECT_ROOT).expanduser().resolve()
    main = root / "main.py"
    if not main.is_file():
        raise RuntimeError(f"main.py não encontrado em {root}")
    return python, [python, str(main)]


def restart_m87_process() -> None:
    if _canonical_launcher() is None:
        executable, arguments = restart_command()
        os.execv(executable, arguments)
    wait_for_exit = (
        'while kill -0 "$1" 2>/dev/null; do sleep 0.05; done; '
        'exec /usr/bin/open -b "$2"'
    )
    subprocess.Popen(
        [
            "/bin/sh", "-c", wait_for_exit, "m87-restart",
            str(os.getpid()), BUNDLE_IDENTIFIER,
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
