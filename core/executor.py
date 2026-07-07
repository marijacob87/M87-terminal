import subprocess
import webbrowser
from pathlib import Path


def execute(command):
    """
    Executa um comando vindo do commands.json.

    Tipos aceitos:
    - shortcut
    - folder
    - app
    - shell
    - url
    - internal
    """

    command_type = command.get("type")
    value = command.get("value")
    code = command.get("code", "??")

    if not command_type or not value:
        print(f"[ERRO] Comando {code} sem type/value.")
        return False

    try:
        if command_type == "shortcut":
            return run_shortcut(value)

        if command_type == "folder":
            return open_folder(value)

        if command_type == "app":
            return open_app(value)

        if command_type == "shell":
            return run_shell(value)

        if command_type == "url":
            return open_url(value)

        if command_type == "internal":
            return value

        print(f"[ERRO] Tipo desconhecido em {code}: {command_type}")
        return False

    except Exception as error:
        print(f"[ERRO] Falha ao executar {code}: {error}")
        return False


def run_shortcut(name):
    result = subprocess.run(
        ["shortcuts", "run", name],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print(result.stderr.strip())
        return False

    return True


def open_folder(path):
    expanded_path = Path(path).expanduser()

    result = subprocess.run(
        ["open", str(expanded_path)],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print(result.stderr.strip())
        return False

    return True


def open_app(app_name):
    result = subprocess.run(
        ["open", "-a", app_name],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print(result.stderr.strip())
        return False

    return True


def run_shell(command):
    result = subprocess.run(
        command,
        shell=True,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print(result.stderr.strip())
        return False

    return True


def open_url(url):
    webbrowser.open(url)
    return True