import os
import shutil
import subprocess
import time
from pathlib import Path

from PySide6.QtCore import QThread, Signal


NETWORK_VOLUMES = (
    ("jv100-160", "smb://jv100-160/Pasta Mimaki"),
    ("pfi", "smb://pfi/Trabalhos PFI"),
    ("NAS310BDA.local", "smb://NAS310BDA._smb._tcp.local/Trabalhos"),
)

VMX_PATH = Path(
    "/Users/marianejacob/Downloads/VIRTUAL MACHINES.LOCALIZED/"
    "Windows 11 64-bit Arm 2.vmwarevm/Windows 11 64-bit Arm 2.vmx"
)

STEPS = (
    "Unidades",
    "Mail",
    "WhatsApp",
    "Safari",
    "VMware",
    "Windows 11",
    "Notificações",
)


def _run(command, timeout=20):
    try:
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except Exception as error:
        print(f"[MR] Falha ao executar {command}: {error}")
        return None


def _ping(host):
    result = _run(["ping", "-c", "1", "-W", "1000", host], timeout=3)
    return bool(result and result.returncode == 0)


def _mount_volume(url):
    script = f'mount volume {url!r}'
    result = _run(["osascript", "-e", script], timeout=15)
    return bool(result and result.returncode == 0)


def mount_network_volumes():
    mounted = 0
    reachable = 0

    for host, url in NETWORK_VOLUMES:
        if not _ping(host):
            continue

        reachable += 1
        if _mount_volume(url):
            mounted += 1

    # Servidores indisponíveis são ignorados, como no Atalho original.
    return mounted == reachable


def _open_app(name):
    result = _run(["open", "-a", name], timeout=10)
    return bool(result and result.returncode == 0)


def _find_vmrun():
    candidates = (
        "/Applications/VMware Fusion.app/Contents/Library/vmrun",
        "/Applications/VMware Fusion.app/Contents/Library/vmrun-bin",
    )

    for candidate in candidates:
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate

    return shutil.which("vmrun")


def _start_windows_vm():
    vmrun = _find_vmrun()

    if not vmrun:
        print("[MR] vmrun não encontrado dentro do VMware Fusion.")
        return False

    if not VMX_PATH.exists():
        print(f"[MR] Arquivo da VM não encontrado: {VMX_PATH}")
        return False

    # Se já estiver ligada, considera a etapa concluída.
    listed = _run([vmrun, "list"], timeout=15)
    if listed and str(VMX_PATH) in listed.stdout:
        return True

    result = _run([vmrun, "start", str(VMX_PATH), "nogui"], timeout=60)
    return bool(result and result.returncode == 0)


def _clear_notifications():
    """Fecha a Central de Notificações e tenta acionar 'Limpar tudo'."""
    script = r'''
    tell application "System Events"
        try
            tell process "ControlCenter"
                set frontmost to true
                try
                    click menu bar item "Central de Notificações" of menu bar 1
                on error
                    try
                        click menu bar item "Notification Center" of menu bar 1
                    end try
                end try
                delay 0.7
            end tell

            tell process "NotificationCenter"
                set clearButtons to every button of every UI element of window 1 whose description is "Limpar tudo" or description is "Clear All"
                repeat with buttonGroup in clearButtons
                    repeat with clearButton in buttonGroup
                        try
                            click clearButton
                        end try
                    end repeat
                end repeat
            end tell

            key code 53
            return true
        on error
            key code 53
            return false
        end try
    end tell
    '''

    result = _run(["osascript", "-e", script], timeout=12)
    return bool(result and result.returncode == 0)


class MorningRoutineWorker(QThread):
    progress = Signal(str, bool)
    completed = Signal(float)

    def run(self):
        started = time.perf_counter()

        tasks = (
            ("Unidades", mount_network_volumes),
            ("Mail", lambda: _open_app("Mail")),
            ("WhatsApp", lambda: _open_app("WhatsApp")),
            ("Safari", lambda: _open_app("Safari")),
            ("VMware", lambda: _open_app("VMware Fusion")),
            ("Windows 11", _start_windows_vm),
            ("Notificações", _clear_notifications),
        )

        for label, action in tasks:
            try:
                ok = bool(action())
            except Exception as error:
                print(f"[MR] Erro em {label}: {error}")
                ok = False

            self.progress.emit(label, ok)

            # Pequena pausa para o macOS absorver cada abertura sem atropelos.
            if label not in ("Windows 11", "Notificações"):
                time.sleep(0.25)

        self.completed.emit(time.perf_counter() - started)


class MountVolumesWorker(QThread):
    completed = Signal(bool, float)

    def run(self):
        started = time.perf_counter()
        ok = mount_network_volumes()
        self.completed.emit(ok, time.perf_counter() - started)
