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

VMX_PATH = (
    Path.home()
    / "Downloads"
    / "VIRTUAL MACHINES.LOCALIZED"
    / "Windows 11 64-bit Arm 2.vmwarevm"
    / "Windows 11 64-bit Arm 2.vmx"
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


def _volume_is_mounted(volume_name):
    """Confirma a unidade pelo ponto de montagem real em /Volumes."""
    volumes_dir = Path("/Volumes")

    try:
        for item in volumes_dir.iterdir():
            # O macOS pode acrescentar "-1" se já existir um nome ocupado.
            if item.name == volume_name or item.name.startswith(f"{volume_name}-"):
                return item.is_dir()
    except OSError as error:
        print(f"[MU] Não foi possível consultar /Volumes: {error}")

    return False


def _mount_volume(url):
    """Monta uma unidade SMB usando AppleScript sem quebrar URLs com espaços."""
    script = (
        'on run argv\n'
        '    mount volume (item 1 of argv)\n'
        'end run'
    )
    result = _run(["osascript", "-e", script, url], timeout=30)

    if not result:
        return False

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "erro desconhecido").strip()
        print(f"[MU] Falha ao montar {url}: {detail}")
        return False

    return True


def mount_network_volumes():
    """Monta e verifica todas as unidades configuradas.

    Não usa ping como pré-requisito, porque muitos servidores SMB respondem ao
    compartilhamento mesmo quando bloqueiam ICMP. O sucesso só é considerado
    depois de a unidade realmente aparecer em /Volumes.
    """
    all_ok = True

    for _host, url in NETWORK_VOLUMES:
        volume_name = url.rsplit("/", 1)[-1].replace("%20", " ")

        if _volume_is_mounted(volume_name):
            print(f"[MU] Já montada: {volume_name}")
            continue

        print(f"[MU] Montando: {volume_name}")
        requested = _mount_volume(url)

        if requested:
            # O Finder pode devolver antes de /Volumes ser atualizado.
            for _ in range(20):
                if _volume_is_mounted(volume_name):
                    break
                time.sleep(0.25)

        mounted = _volume_is_mounted(volume_name)
        print(f"[MU] {'OK' if mounted else 'FALHOU'}: {volume_name}")
        all_ok = all_ok and mounted

    return all_ok

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
