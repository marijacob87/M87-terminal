from __future__ import annotations

import subprocess
from pathlib import Path


APP_NAME = "M87 Terminal"
APP_PATH = Path("/Applications/M87 Terminal.app")


def set_start_with_system(
    enabled: bool, *, hidden: bool = False
) -> tuple[bool, str]:
    if enabled and not APP_PATH.exists():
        return False, f"Aplicativo não encontrado em {APP_PATH}."

    delete_existing = (
        'tell application "System Events" to '
        f'delete every login item whose name is "{APP_NAME}"'
    )
    scripts = [delete_existing]
    if enabled:
        hidden_value = "true" if hidden else "false"
        scripts.append(
            'tell application "System Events" to make login item at end '
            f'with properties {{name:"{APP_NAME}", path:"{APP_PATH}", '
            f'hidden:{hidden_value}}}'
        )
    try:
        for script in scripts:
            result = subprocess.run(
                ["osascript", "-e", script], capture_output=True, text=True,
                timeout=8, check=False,
            )
            if result.returncode != 0:
                message = result.stderr.strip() or "Não foi possível alterar os itens de início."
                return False, message
    except (OSError, subprocess.SubprocessError) as error:
        return False, str(error)
    return True, ""
