import os
import subprocess
import threading
import time
import unicodedata


ANYDESK_APP = "/Applications/AnyDesk.app"

ANYDESK_MACHINES = [
    {
        "name": "DUPLO",
        "id": "1657421817",
    },
    {
        "name": "MIMAKI",
        "id": "593418813",
    },
    {
        "name": "PRINECT",
        "id": "317203682",
    },
]


def _normalize(text):
    text = unicodedata.normalize(
        "NFKD",
        str(text).strip().lower(),
    )

    return "".join(
        character
        for character in text
        if not unicodedata.combining(character)
    )


def get_anydesk_suggestions(query=""):
    query = _normalize(query)
    suggestions = []

    for machine in ANYDESK_MACHINES:
        name = machine["name"]
        normalized_name = _normalize(name)

        if (
            not query
            or normalized_name.startswith(query)
            or query in normalized_name
        ):
            suggestions.append(
                {
                    "type": "anydesk_machine",
                    "name": name,
                    "id": machine["id"],
                }
            )

    if (
        not query
        or "app".startswith(query)
        or query in "app"
    ):
        suggestions.append(
            {
                "type": "anydesk_app",
                "name": "APP",
            }
        )

    return suggestions


def _close_new_session_tab():
    """
    O endereço anydesk:ID abre a máquina correta, mas deixa
    uma guia vazia de Nova sessão na frente.

    Após a ligação carregar, fecha somente a guia atual.
    A guia da máquina correta permanece aberta.
    """

    # Tempo para o AnyDesk criar as duas guias.
    time.sleep(3.5)

    apple_script = r'''
    tell application "AnyDesk"
        activate
    end tell

    delay 0.5

    tell application "System Events"
        if exists process "AnyDesk" then
            tell process "AnyDesk"
                set frontmost to true

                delay 3

                -- Fecha a guia atual "Nova sessão".
                -- A sessão correta fica aberta atrás dela.
                keystroke "w" using {command down}
            end tell
        end if
    end tell
    '''

    try:
        subprocess.run(
            [
                "osascript",
                "-e",
                apple_script,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=8,
            check=False,
        )

    except (
        OSError,
        subprocess.TimeoutExpired,
    ):
        pass


def open_anydesk_machine(machine_id):
    machine_id = str(machine_id).strip()

    if not machine_id:
        return False

    if not os.path.isdir(ANYDESK_APP):
        return False

    try:
        subprocess.Popen(
            [
                "open",
                f"anydesk:{machine_id}",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        threading.Thread(
            target=_close_new_session_tab,
            daemon=True,
        ).start()

        return True

    except OSError:
        return False


def open_anydesk_app():
    try:
        subprocess.Popen(
            [
                "open",
                "-a",
                "AnyDesk",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        return True

    except OSError:
        return False