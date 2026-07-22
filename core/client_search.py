import plistlib
import re
import subprocess
import unicodedata
from pathlib import Path


TRABALHOS_PATH = Path("/Volumes/Trabalhos")
SAVED_SEARCH_DIR = Path.home() / "Library" / "Saved Searches"
MAX_RESULTS = 20


# O macOS transforma ":" em "/" em nomes de arquivo.
# Este caractere tem a mesma aparência, mas permanece como dois-pontos no Finder.
DISPLAY_COLON = "꞉"


def normalize(text):
    text = str(text).strip().lower()
    text = unicodedata.normalize("NFKD", text)

    return "".join(
        char for char in text
        if not unicodedata.combining(char)
    )


def letter_folder(letter):
    """Retorna a pasta alfabética exata dentro de Trabalhos (A, B, C...)."""
    wanted = normalize(letter)

    if len(wanted) != 1 or not wanted.isalpha():
        return None

    if not TRABALHOS_PATH.exists():
        return None

    for folder in TRABALHOS_PATH.iterdir():
        if folder.is_dir() and normalize(folder.name) == wanted:
            return folder

    return TRABALHOS_PATH / wanted.upper()


def first_letter_folder(query):
    query = normalize(query)

    if not query:
        return None

    return letter_folder(query[0])


def search_fast_client(query, folder_letter=None):
    query = normalize(query)

    if not query:
        return []

    folder = (
        letter_folder(folder_letter)
        if folder_letter
        else first_letter_folder(query)
    )

    if not folder or not folder.exists():
        return []

    results = []

    for item in sorted(folder.iterdir(), key=lambda path: normalize(path.name)):
        if item.is_dir() and query in normalize(item.name):
            results.append(item)

            if len(results) >= MAX_RESULTS:
                break

    return results


def open_path(path):
    if not path:
        return False

    path = Path(path)

    if path.is_dir():
        try:
            from core.recent_folders import record_recent_folder
            record_recent_folder(path)
        except Exception:
            pass

    subprocess.Popen(
        ["open", str(path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    return True


def _spotlight_escape(value):
    """Escapa texto para uma consulta Spotlight do tipo kMDItemFSName."""
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def _safe_filename(value):
    value = re.sub(r"[^\w\-. ]+", " ", str(value), flags=re.UNICODE)
    value = re.sub(r"\s+", " ", value).strip()
    return value[:60] or "Busca"


def _set_extension_hidden(path):
    """Marca a extensão .savedSearch como oculta no Finder."""
    script = """
on run argv
    tell application "Finder"
        set searchFile to POSIX file (item 1 of argv) as alias
        set extension hidden of searchFile to true
    end tell
end run
"""

    subprocess.run(
        ["osascript", "-e", script, str(path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )


def finder_search(query):
    """Abre uma busca do Finder limitada a /Volumes/Trabalhos."""
    query = str(query).strip()

    if not query:
        return False

    if not TRABALHOS_PATH.exists():
        raise FileNotFoundError(
            f'A pasta "{TRABALHOS_PATH}" não está disponível.'
        )

    SAVED_SEARCH_DIR.mkdir(parents=True, exist_ok=True)

    safe_query = _safe_filename(query)
    display_name = f"M87 • Busca{DISPLAY_COLON} {safe_query}"
    saved_search_path = SAVED_SEARCH_DIR / f"{display_name}.savedSearch"

    escaped_query = _spotlight_escape(query)
    raw_query = f'(kMDItemFSName == "*{escaped_query}*"cd)'
    scope_path = str(TRABALHOS_PATH)

    saved_search = {
        "CompatibleVersion": 1,
        "RawQuery": raw_query,
        "SearchCriteria": {
            "FXCriteriaSlices": [
                {
                    "criteria": raw_query,
                    "displayValues": ["Nome", "contém", query],
                    "rowType": 0,
                    "subrows": [],
                }
            ],
            "FXScope": 0,
            "FXScopeArrayOfPaths": [scope_path],
        },
        "ViewSettings": {
            "ListViewSettings": {
                "calculateAllSizes": False,
                "iconSize": 16,
                "showIconPreview": True,
                "sortColumn": "name",
                "textSize": 12,
                "useRelativeDates": True,
            }
        },
    }

    with saved_search_path.open("wb") as file:
        plistlib.dump(saved_search, file, fmt=plistlib.FMT_XML, sort_keys=False)

    _set_extension_hidden(saved_search_path)

    subprocess.Popen(
        ["open", "-a", "Finder", str(saved_search_path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    return True
