import json
import os
import subprocess
from pathlib import Path


_HISTORY_DIR = Path.home() / "Library/Application Support/M87 Terminal"
_HISTORY_FILE = _HISTORY_DIR / "recent_folders.json"
_MAX_STORED = 30


def _load_history():
    try:
        with _HISTORY_FILE.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return []

    return data if isinstance(data, list) else []


def _save_history(items):
    try:
        _HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        with _HISTORY_FILE.open("w", encoding="utf-8") as handle:
            json.dump(items[:_MAX_STORED], handle, ensure_ascii=False, indent=2)
    except OSError:
        pass


def record_recent_folder(path):
    """Guarda uma pasta no histórico do M87, sem duplicados."""
    if not path:
        return False

    try:
        folder = Path(os.path.expanduser(str(path))).resolve()
    except (OSError, RuntimeError):
        folder = Path(os.path.expanduser(str(path)))

    if not folder.is_dir():
        return False

    folder_text = str(folder)
    items = _load_history()
    items = [
        item for item in items
        if isinstance(item, dict) and item.get("path") != folder_text
    ]
    items.insert(0, {"name": folder.name or folder_text, "path": folder_text})
    _save_history(items)
    return True


def _finder_window_paths():
    """
    Lê as pastas abertas nas janelas do Finder.

    Usa Apple Events diretamente com o Finder, sem clicar em menus nem usar
    System Events. Na primeira utilização, o macOS pode pedir autorização para
    o M87 Terminal controlar o Finder.
    """
    script = r'''
tell application "Finder"
    set output to ""
    repeat with finderWindow in every Finder window
        try
            set folderPath to POSIX path of (target of finderWindow as alias)
            if output is not "" then set output to output & linefeed
            set output to output & folderPath
        end try
    end repeat
    return output
end tell
'''

    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=1.5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []

    if result.returncode != 0:
        return []

    paths = []
    for line in result.stdout.splitlines():
        value = line.strip()
        if value and value not in paths:
            paths.append(value)

    return paths


def sync_finder_history():
    """Adiciona ao histórico as pastas atualmente abertas no Finder."""
    paths = _finder_window_paths()

    # O Finder devolve as janelas da frente para trás. Gravamos ao contrário
    # para que a janela mais à frente termine no topo do histórico.
    items = _load_history()
    original = list(items)
    for path in reversed(paths):
        try:
            folder = Path(os.path.expanduser(str(path))).resolve()
        except (OSError, RuntimeError):
            folder = Path(os.path.expanduser(str(path)))

        if not folder.is_dir():
            continue

        folder_text = str(folder)
        items = [
            item for item in items
            if isinstance(item, dict) and item.get("path") != folder_text
        ]
        items.insert(
            0,
            {"name": folder.name or folder_text, "path": folder_text},
        )

    items = items[:_MAX_STORED]
    if items != original:
        _save_history(items)

    return len(paths)


def get_recent_folders(limit=10, refresh=True):
    """
    Retorna as pastas recentes acompanhadas pelo M87.

    O histórico combina:
    - pastas abertas diretamente pelo Finder enquanto o M87 está ativo;
    - pastas abertas por comandos do próprio Terminal.
    """
    if refresh:
        sync_finder_history()

    output = []
    seen = set()

    for item in _load_history():
        if not isinstance(item, dict):
            continue

        path = os.path.expanduser(str(item.get("path", "")).strip())
        if not path or path in seen or not os.path.isdir(path):
            continue

        seen.add(path)
        output.append({
            "type": "recent_folder",
            "name": str(item.get("name", "")).strip() or Path(path).name,
            "path": path,
        })

        if len(output) >= limit:
            break

    return output
