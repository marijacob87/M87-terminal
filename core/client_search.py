from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import plistlib
import re
import subprocess
import threading
import unicodedata
from pathlib import Path


DEFAULT_TRABALHOS_PATH = Path("/Volumes/Trabalhos")
TRABALHOS_PATH = DEFAULT_TRABALHOS_PATH
SAVED_SEARCH_DIR = Path.home() / "Library" / "Saved Searches"
CLIENT_INDEX_FILE = (
    Path.home()
    / "Library"
    / "Application Support"
    / "M87 Terminal"
    / "client_search_index.json"
)
MAX_RESULTS = 20
FILE_EXTENSION_PATTERN = re.compile(r"^(.*?)\s+(\.[^\s.]+)$")
_client_folder_cache = ()
_client_item_cache = ()
_client_cache_loaded = False
_client_item_cache_lock = threading.Lock()


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

    if TRABALHOS_PATH == DEFAULT_TRABALHOS_PATH and _client_cache_loaded:
        for client_folder in _client_folder_cache:
            folder = client_folder.parent

            if normalize(folder.name) == wanted:
                return folder

        return TRABALHOS_PATH / wanted.upper()

    try:
        for folder in TRABALHOS_PATH.iterdir():
            if folder.is_dir() and normalize(folder.name) == wanted:
                return folder
    except OSError:
        return None

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

    if TRABALHOS_PATH == DEFAULT_TRABALHOS_PATH and _client_cache_loaded:
        wanted_letter = normalize(folder_letter) if folder_letter else query[0]
        matches = (
            path
            for path in _client_folder_cache
            if normalize(path.parent.name) == wanted_letter
        )
        cached_results = _rank_paths(matches, query)

        if cached_results:
            return cached_results

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


def search_client_subfolders(query):
    """Busca pastas diretamente dentro das pastas de clientes."""
    query = normalize(query)

    if not query:
        return []

    if TRABALHOS_PATH == DEFAULT_TRABALHOS_PATH and _client_cache_loaded:
        cached_results = _rank_paths(_client_item_cache, query)

        if cached_results:
            return cached_results

    if not TRABALHOS_PATH.exists():
        return []

    indexed_results = _search_indexed_client_items(query)

    if indexed_results:
        return indexed_results

    try:
        with os.scandir(TRABALHOS_PATH) as entries:
            letter_folders = [
                Path(entry.path)
                for entry in entries
                if entry.is_dir() and len(normalize(entry.name)) == 1
            ]
    except OSError:
        return []

    partial_results = []

    executor = ThreadPoolExecutor(
        max_workers=min(8, len(letter_folders) or 1),
        thread_name_prefix="m87-client-letter",
    )
    futures = [
        executor.submit(_scan_client_letter, folder, query)
        for folder in letter_folders
    ]

    for future in as_completed(futures):
        exact_result, matches = future.result()

        if exact_result:
            executor.shutdown(wait=False, cancel_futures=True)
            return [exact_result]

        partial_results.extend(matches)

    executor.shutdown(wait=True)
    return _rank_paths(partial_results, query)


def _scan_client_letter(alphabet_folder, query):
    partial_results = []

    try:
        with os.scandir(alphabet_folder) as clients:
            for client in clients:
                if not client.is_dir():
                    continue

                try:
                    with os.scandir(client.path) as items:
                        for item in items:
                            if not item.is_dir():
                                continue

                            normalized_name = normalize(item.name)
                            path = Path(item.path)

                            if normalized_name == query:
                                return path, []

                            if query in normalized_name:
                                partial_results.append(path)
                except OSError:
                    continue
    except OSError:
        pass

    return None, partial_results


def split_file_search(query):
    """Separa ``nome .ext``; sem extensão, mantém a busca por pasta."""
    match = FILE_EXTENSION_PATTERN.fullmatch(str(query).strip())

    if not match:
        return str(query).strip(), None

    name, extension = match.groups()
    name = name.strip()

    if not name:
        return str(query).strip(), None

    return name, normalize(extension)


def warm_client_search_cache():
    """Atualiza em segundo plano o índice persistente de ``/`` e ``//``."""
    global _client_cache_loaded, _client_folder_cache, _client_item_cache

    if not _client_item_cache_lock.acquire(blocking=False):
        return

    try:
        client_folders_list = []
        items = []

        if not TRABALHOS_PATH.exists():
            return

        try:
            letter_folders = (
                path
                for path in TRABALHOS_PATH.iterdir()
                if path.is_dir() and len(normalize(path.name)) == 1
            )

            for alphabet_folder in letter_folders:
                try:
                    client_folders = (
                        path for path in alphabet_folder.iterdir() if path.is_dir()
                    )

                    for client_folder in client_folders:
                        client_folders_list.append(client_folder)
                        try:
                            for item in client_folder.iterdir():
                                if item.is_dir():
                                    items.append(item)
                        except OSError:
                            continue
                except OSError:
                    continue
        except OSError:
            return

        _client_folder_cache = tuple(client_folders_list)
        _client_item_cache = tuple(items)
        _client_cache_loaded = True
        _save_client_search_cache()
    finally:
        _client_item_cache_lock.release()


def _rank_paths(paths, query):
    matches = []

    for path in paths:
        normalized_name = normalize(path.name)

        if query not in normalized_name:
            continue

        score = (
            0 if normalized_name == query
            else 1 if normalized_name.startswith(query)
            else 2
        )
        matches.append((score, normalized_name, path))

    matches.sort(key=lambda item: (item[0], item[1], normalize(item[2])))
    return [item[2] for item in matches[:MAX_RESULTS]]


def _load_client_search_cache():
    global _client_cache_loaded, _client_folder_cache, _client_item_cache

    try:
        data = json.loads(CLIENT_INDEX_FILE.read_text(encoding="utf-8"))

        if data.get("root") != str(DEFAULT_TRABALHOS_PATH):
            return

        _client_folder_cache = tuple(
            Path(path) for path in data.get("clients", [])
        )
        _client_item_cache = tuple(
            Path(path) for path in data.get("subfolders", [])
        )
        _client_cache_loaded = True
    except (OSError, TypeError, ValueError):
        pass


def _save_client_search_cache():
    data = {
        "root": str(DEFAULT_TRABALHOS_PATH),
        "clients": [str(path) for path in _client_folder_cache],
        "subfolders": [str(path) for path in _client_item_cache],
    }

    try:
        CLIENT_INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = CLIENT_INDEX_FILE.with_suffix(".tmp")
        temporary_path.write_text(
            json.dumps(data, ensure_ascii=False),
            encoding="utf-8",
        )
        temporary_path.replace(CLIENT_INDEX_FILE)
    except OSError:
        pass


def client_search_cache_ready():
    return _client_cache_loaded


def _search_indexed_client_items(query):
    """Consulta o índice Spotlight e mantém apenas letra/cliente/item."""
    if TRABALHOS_PATH != DEFAULT_TRABALHOS_PATH:
        return None

    escaped_query = _spotlight_escape(query)
    raw_query = (
        f'(kMDItemFSName == "*{escaped_query}*"cd)'
        ' && (kMDItemContentType == "public.folder")'
    )

    try:
        result = subprocess.run(
            ["mdfind", "-onlyin", str(TRABALHOS_PATH), raw_query],
            capture_output=True,
            text=True,
            timeout=0.35,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None

    if result.returncode != 0:
        return None

    matches = []

    for line in result.stdout.splitlines():
        path = Path(line.strip())

        if not line.strip():
            continue

        try:
            relative_path = path.relative_to(TRABALHOS_PATH)
        except ValueError:
            continue

        if len(relative_path.parts) != 3:
            continue

        normalized_name = normalize(path.name)

        if query not in normalized_name:
            continue

        score = (
            0 if normalized_name == query
            else 1 if normalized_name.startswith(query)
            else 2
        )
        matches.append((score, normalized_name, path))

    matches.sort(key=lambda item: (item[0], item[1], normalize(item[2])))
    return [item[2] for item in matches[:MAX_RESULTS]]


def open_path(path):
    if not path:
        return False

    path = Path(path)

    subprocess.Popen(
        ["open", str(path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    def record():
        try:
            from core.recent_folders import record_recent_folder
            record_recent_folder(path)
        except Exception:
            pass

    threading.Thread(
        target=record,
        name="m87-record-recent-folder",
        daemon=True,
    ).start()

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

    subprocess.Popen(
        ["osascript", "-e", script, str(path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
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

    name_query, extension = split_file_search(query)
    safe_query = _safe_filename(query)
    display_name = f"M87 • Busca{DISPLAY_COLON} {safe_query}"
    saved_search_path = SAVED_SEARCH_DIR / f"{display_name}.savedSearch"

    escaped_query = _spotlight_escape(name_query)
    raw_query = f'(kMDItemFSName == "*{escaped_query}*"cd)'

    if extension:
        escaped_extension = _spotlight_escape(extension)
        raw_query += f' && (kMDItemFSName == "*{escaped_extension}"cd)'

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


_load_client_search_cache()
