import subprocess
import unicodedata
from pathlib import Path


TRABALHOS_PATH = Path("/Volumes/Trabalhos")
MAX_RESULTS = 20


def normalize(text):
    text = str(text).strip().lower()
    text = unicodedata.normalize("NFKD", text)

    return "".join(
        char for char in text
        if not unicodedata.combining(char)
    )


def first_letter_folder(query):
    query = normalize(query)

    if not query:
        return None

    wanted = query[0]

    if not TRABALHOS_PATH.exists():
        return None

    for folder in TRABALHOS_PATH.iterdir():
        if folder.is_dir() and normalize(folder.name).startswith(wanted):
            return folder

    return TRABALHOS_PATH / wanted.upper()


def search_fast_client(query):
    query = normalize(query)

    if not query:
        return []

    folder = first_letter_folder(query)

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

    subprocess.Popen(
        ["open", str(path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    return True


def finder_search(query):
    query = (
        query.replace("\\", "\\\\")
             .replace('"', '\\"')
    )

    script = f'''
    tell application "Finder"
        activate
        open POSIX file "{TRABALHOS_PATH}"
    end tell

    delay 0.6

    tell application "System Events"
        keystroke "f" using command down
        delay 0.3
        keystroke "{query}"
    end tell
    '''

    subprocess.Popen(
        ["osascript", "-e", script],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    return True