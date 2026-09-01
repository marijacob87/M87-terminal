import os
import re
import subprocess
import threading
import time
import unicodedata


ANYDESK_APP = "/Applications/AnyDesk.app"
APPLICATION_SERVICES = (
    "/System/Library/Frameworks/ApplicationServices.framework"
)

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
        "console": True,
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
                    "console": machine.get("console", False),
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


def _accessibility_is_trusted(prompt=False):
    """Verifica e, quando pedido, solicita Acessibilidade para o M87."""
    try:
        import objc

        namespace = {}
        bundle = objc.loadBundle(
            "ApplicationServices",
            namespace,
            bundle_path=APPLICATION_SERVICES,
        )
        objc.loadBundleFunctions(
            bundle,
            namespace,
            [("AXIsProcessTrustedWithOptions", b"Z@")],
        )
        objc.loadBundleVariables(
            bundle,
            namespace,
            [("kAXTrustedCheckOptionPrompt", b"@")],
        )
        options = {
            namespace["kAXTrustedCheckOptionPrompt"]: bool(prompt),
        }
        return bool(namespace["AXIsProcessTrustedWithOptions"](options))
    except Exception:
        return False


def _select_opened_session(confirm_console=False):
    if not _accessibility_is_trusted(prompt=True):
        return False

    script = r'''
    on run argv
        set confirmConsole to item 1 of argv is "true"
        tell application "AnyDesk" to activate
        delay 0.15
        tell application "System Events"
            tell process "AnyDesk"
                set frontmost to true
                keystroke "[" using {command down, shift down}

                if confirmConsole then
                    repeat 25 times
                        try
                            set controls to entire contents of window 1
                            repeat with controlItem in controls
                                try
                                    if role of controlItem is "AXButton" then
                                        set buttonName to name of controlItem as text
                                        if buttonName is "Conectar" or buttonName is "Connect" then
                                            click controlItem
                                            return "console-confirmed"
                                        end if
                                    end if
                                end try
                            end repeat
                        end try
                        delay 0.2
                    end repeat
                end if
            end tell
        end tell
        return "session-selected"
    end run
    '''
    try:
        result = subprocess.run(
            [
                "osascript",
                "-e",
                script,
                "true" if confirm_console else "false",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=7 if confirm_console else 2,
            check=False,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _open_machine_url(machine_id, startup_delay, confirm_console=False):
    """Envia o ID e seleciona a aba de sessão criada pelo AnyDesk."""
    if startup_delay:
        time.sleep(startup_delay)
    try:
        subprocess.Popen(
            [
                "open",
                "-b",
                "com.philandro.anydesk",
                f"anydesk:{machine_id}",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        # O AnyDesk 9 cria a sessão à esquerda, mas mantém "Nova sessão"
        # selecionada. Alterna uma aba para trás sem fechar nenhuma delas.
        time.sleep(0.45)
        _select_opened_session(confirm_console)
    except (OSError, subprocess.TimeoutExpired):
        return


def open_anydesk_machine(machine_id, confirm_console=False):
    machine_id = str(machine_id).strip()

    if not re.fullmatch(r"\d{6,12}", machine_id):
        return False

    if not os.path.isdir(ANYDESK_APP):
        return False

    try:
        launch = subprocess.run(
            [
                "open",
                "-g",
                "-a",
                "AnyDesk",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=3,
            check=False,
        )
        if launch.returncode != 0:
            return False

        threading.Thread(
            target=_open_machine_url,
            args=(machine_id, 0.8, bool(confirm_console)),
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
