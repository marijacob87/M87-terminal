from __future__ import annotations

import os
import plistlib
import shutil
import stat
import subprocess
import tempfile
import time
from pathlib import Path

APP_SUPPORT = Path.home() / "Library" / "Application Support" / "M87 Terminal"
HELPER_APP = APP_SUPPORT / "M87 Trash Helper.app"
HELPER_BUNDLE_ID = "pt.m87tools.trash-helper"
HELPER_VERSION = "2.0.0"
STATUS_FILE = APP_SUPPORT / "trash_helper_status.txt"


def _run(command: list[str], timeout: float = 30.0) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _finder_empty_script() -> str:
    return r'''
tell application "Finder"
    try
        if (count of items of trash) > 0 then
            empty trash
        end if

        repeat 120 times
            if (count of items of trash) is 0 then
                return "OK"
            end if
            delay 0.25
        end repeat

        return "NOT_EMPTY|" & (count of items of trash)
    on error errorMessage number errorNumber
        return "ERROR|" & errorNumber & "|" & errorMessage
    end try
end tell
'''


def _empty_with_direct_applescript() -> tuple[bool, str]:
    """Primeira tentativa: fala diretamente com o Finder."""
    try:
        result = _run(["/usr/bin/osascript", "-e", _finder_empty_script()], timeout=40)
    except subprocess.TimeoutExpired:
        return False, "TIMEOUT|Finder demorou demais"
    except Exception as error:
        return False, f"ERROR|direct|{error}"

    response = result.stdout.strip()
    if response == "OK":
        return True, response

    if not response:
        response = result.stderr.strip() or f"RETURN_CODE|{result.returncode}"

    return False, response


def _helper_script() -> str:
    status_path = str(STATUS_FILE).replace("\\", "\\\\").replace('"', '\\"')
    return f'''
on run
    set statusPath to "{status_path}"
    set statusText to ""

    try
        tell application "Finder"
            if (count of items of trash) > 0 then
                empty trash
            end if

            repeat 120 times
                if (count of items of trash) is 0 then
                    set statusText to "OK"
                    exit repeat
                end if
                delay 0.25
            end repeat

            if statusText is "" then
                set statusText to "NOT_EMPTY|" & (count of items of trash)
            end if
        end tell
    on error errorMessage number errorNumber
        set statusText to "ERROR|" & errorNumber & "|" & errorMessage
    end try

    do shell script "/usr/bin/printf %s " & quoted form of statusText & " > " & quoted form of statusPath
end run
'''


def _installed_helper_is_current() -> bool:
    info_path = HELPER_APP / "Contents" / "Info.plist"
    if not info_path.exists():
        return False

    try:
        with info_path.open("rb") as handle:
            info = plistlib.load(handle)
        return (
            info.get("CFBundleIdentifier") == HELPER_BUNDLE_ID
            and info.get("CFBundleShortVersionString") == HELPER_VERSION
        )
    except Exception:
        return False


def _install_helper() -> bool:
    """
    Cria um app auxiliar com identidade estável e assinatura ad-hoc.

    A assinatura depois da edição do Info.plist é essencial: sem ela o macOS
    pode recusar registrar o helper na lista de Automação.
    """
    APP_SUPPORT.mkdir(parents=True, exist_ok=True)

    if _installed_helper_is_current():
        return True

    shutil.rmtree(HELPER_APP, ignore_errors=True)

    try:
        with tempfile.TemporaryDirectory(prefix="m87-trash-helper-") as tmp:
            script_path = Path(tmp) / "trash_helper.applescript"
            script_path.write_text(_helper_script(), encoding="utf-8")

            result = _run(
                ["/usr/bin/osacompile", "-o", str(HELPER_APP), str(script_path)],
                timeout=30,
            )
            if result.returncode != 0:
                print(f"[CL] Não foi possível criar o helper: {result.stderr.strip()}")
                return False

        info_path = HELPER_APP / "Contents" / "Info.plist"
        with info_path.open("rb") as handle:
            info = plistlib.load(handle)

        info.update(
            {
                "CFBundleIdentifier": HELPER_BUNDLE_ID,
                "CFBundleName": "M87 Trash Helper",
                "CFBundleDisplayName": "M87 Trash Helper",
                "CFBundleShortVersionString": HELPER_VERSION,
                "CFBundleVersion": "2",
                "LSUIElement": True,
            }
        )

        with info_path.open("wb") as handle:
            plistlib.dump(info, handle)

        _run(["/usr/bin/xattr", "-dr", "com.apple.quarantine", str(HELPER_APP)], timeout=10)

        sign = _run(
            ["/usr/bin/codesign", "--force", "--deep", "--sign", "-", str(HELPER_APP)],
            timeout=30,
        )
        if sign.returncode != 0:
            print(f"[CL] Não foi possível assinar o helper: {sign.stderr.strip()}")
            return False

        return True

    except Exception as error:
        print(f"[CL] Não foi possível instalar o helper: {error}")
        return False


def _empty_with_helper() -> tuple[bool, str]:
    if not _install_helper():
        return False, "ERROR|helper_install|falha ao instalar"

    APP_SUPPORT.mkdir(parents=True, exist_ok=True)
    try:
        STATUS_FILE.unlink(missing_ok=True)
    except Exception:
        pass

    try:
        result = _run(
            ["/usr/bin/open", "-n", "-W", str(HELPER_APP)],
            timeout=45,
        )
    except subprocess.TimeoutExpired:
        return False, "TIMEOUT|helper demorou demais"
    except Exception as error:
        return False, f"ERROR|helper_open|{error}"

    if result.returncode != 0:
        return False, result.stderr.strip() or f"RETURN_CODE|{result.returncode}"

    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            status = STATUS_FILE.read_text(encoding="utf-8").strip()
        except Exception:
            status = ""

        if status:
            return status == "OK", status
        time.sleep(0.1)

    return False, "ERROR|helper_status|sem resposta"


def _make_writable(path: Path) -> None:
    try:
        path.chmod(path.stat().st_mode | stat.S_IWUSR)
    except OSError:
        pass


def _remove_path(path: Path) -> bool:
    try:
        if path.is_symlink() or path.is_file():
            _make_writable(path)
            path.unlink(missing_ok=True)
        elif path.is_dir():
            shutil.rmtree(path, onerror=lambda fn, value, exc: (_make_writable(Path(value)), fn(value)))
        return True
    except Exception as error:
        print(f"[CL] Não foi possível apagar {path}: {error}")
        return False


def _trash_locations() -> list[Path]:
    uid = os.getuid()
    locations = [Path.home() / ".Trash"]
    volumes = Path("/Volumes")

    if volumes.exists():
        try:
            for volume in volumes.iterdir():
                locations.append(volume / ".Trashes" / str(uid))
        except OSError:
            pass

    return list(dict.fromkeys(locations))


def _empty_with_filesystem() -> tuple[bool, str]:
    """Último recurso para itens locais ou de volumes externos."""
    found = False
    ok = True

    for location in _trash_locations():
        if not location.exists():
            continue

        found = True
        try:
            items = list(location.iterdir())
        except Exception as error:
            ok = False
            print(f"[CL] Sem acesso a {location}: {error}")
            continue

        for item in items:
            ok = _remove_path(item) and ok

    if not found:
        return True, "OK|no_trash_folders"

    return ok, "OK|filesystem" if ok else "ERROR|filesystem|itens bloqueados"


def empty_trash() -> bool:
    """
    Esvazia a Lixeira por uma cadeia única e verificável.

    Ordem:
      1. AppleScript direto;
      2. helper persistente, assinado e com bundle id estável;
      3. remoção direta como último recurso.
    """
    direct_ok, direct_status = _empty_with_direct_applescript()
    if direct_ok:
        print("[CL] Lixeira esvaziada pelo Finder.")
        return True

    helper_ok, helper_status = _empty_with_helper()
    if helper_ok:
        print("[CL] Lixeira esvaziada pelo M87 Trash Helper.")
        return True

    filesystem_ok, filesystem_status = _empty_with_filesystem()
    if filesystem_ok:
        print("[CL] Lixeira esvaziada pelo modo direto.")
        return True

    print("[CL] Não foi possível esvaziar a Lixeira.")
    print(f"[CL] Finder: {direct_status}")
    print(f"[CL] Helper: {helper_status}")
    print(f"[CL] Direto: {filesystem_status}")

    if "-1743" in direct_status or "-1743" in helper_status:
        print(
            "[CL] O macOS negou Automação. Execute CL novamente e permita que "
            "M87 Trash Helper controle o Finder quando o aviso aparecer."
        )

    return False
