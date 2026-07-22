import gc
import os
import shutil
import stat
import subprocess
import time
from pathlib import Path

from AppKit import NSApplicationActivationPolicyRegular, NSWorkspace

from core.trash_manager import empty_trash as _stable_empty_trash


PROJECT_ROOT = Path(__file__).resolve().parent.parent

_LAST_KILL_REPORT = {}


def get_last_kill_report():
    return dict(_LAST_KILL_REPORT)


def _regular_apps():
    """Retorna apenas aplicativos visíveis ao utilizador no macOS."""
    return [
        app
        for app in NSWorkspace.sharedWorkspace().runningApplications()
        if app.activationPolicy() == NSApplicationActivationPolicyRegular
    ]


def _run_osascript(script: str, timeout: float = 15.0) -> bool:
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            check=False,
        )

        if result.returncode != 0 and result.stderr.strip():
            print(f"[macOS] {result.stderr.strip()}")

        return result.returncode == 0

    except subprocess.TimeoutExpired:
        print("[macOS] A operação demorou mais do que o esperado.")
        return False

    except Exception as error:
        print(f"[macOS] Falha ao executar AppleScript: {error}")
        return False


def _close_finder_windows():
    _run_osascript(
        'tell application "Finder" to close every window',
        timeout=5,
    )


def minimize_all_apps() -> bool:
    """Oculta todos os aplicativos e fecha as janelas do Finder."""
    current_pid = os.getpid()
    failures = []

    _close_finder_windows()

    for app in _regular_apps():
        try:
            if app.processIdentifier() == current_pid:
                continue

            if not app.hide() and not app.isHidden():
                failures.append(app.localizedName() or "Aplicativo")

        except Exception as error:
            name = app.localizedName() or "Aplicativo"
            failures.append(name)
            print(f"[MIN] Falha ao ocultar {name}: {error}")

    if failures:
        print(f"[MIN] Não foi possível ocultar: {', '.join(failures)}")

    return not failures


def _is_vmware(app) -> bool:
    bundle_id = (app.bundleIdentifier() or "").lower()
    name = (app.localizedName() or "").lower()

    return (
        "vmware" in bundle_id
        or "vmware fusion" in name
    )


def _quit_vmware_gracefully():
    """
    O comando direto ao VMware é mais confiável do que enviar apenas
    terminate() ao processo identificado pelo NSWorkspace.
    """
    _run_osascript(
        'tell application "VMware Fusion" to quit',
        timeout=8,
    )


def _release_safe_memory() -> bool:
    """
    Libera apenas memória ociosa do próprio M87.

    O macOS recupera automaticamente a memória dos aplicativos encerrados.
    Não usa purge e não apaga caches gerais do sistema.
    """
    try:
        gc.collect()

        try:
            import ctypes

            libc = ctypes.CDLL("/usr/lib/libSystem.B.dylib")
            relief = getattr(
                libc,
                "malloc_zone_pressure_relief",
                None,
            )

            if relief is not None:
                relief.argtypes = [
                    ctypes.c_void_p,
                    ctypes.c_size_t,
                ]
                relief.restype = ctypes.c_size_t
                relief(None, 0)

        except Exception:
            pass

        return True

    except Exception as error:
        print(
            "[MEMÓRIA] Não foi possível liberar "
            f"memória ociosa: {error}"
        )
        return False


def _fresh_regular_apps_by_pid():
    """
    Faz uma nova leitura dos aplicativos abertos para evitar usar
    objetos antigos do NSWorkspace.
    """
    apps = {}

    for app in _regular_apps():
        try:
            pid = int(app.processIdentifier())
            apps[pid] = app
        except Exception:
            continue

    return apps


def _wait_until_closed(target_pids, timeout: float):
    """
    Espera globalmente pelo encerramento dos processos e retorna apenas
    os PIDs que continuam realmente abertos.
    """
    deadline = time.monotonic() + timeout
    remaining = set(target_pids)

    while remaining and time.monotonic() < deadline:
        running = _fresh_regular_apps_by_pid()
        remaining.intersection_update(running.keys())

        if remaining:
            time.sleep(0.12)

    return remaining


def _pid_is_really_running(pid: int) -> bool:
    """
    Confirma diretamente no macOS se o processo ainda existe.

    Não usa NSWorkspace para o relatório porque ele pode manter
    aplicativos já encerrados na lista durante alguns segundos.
    """
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "stat="],
            capture_output=True,
            text=True,
            timeout=1,
            check=False,
        )

        if result.returncode != 0:
            return False

        status = result.stdout.strip()

        # Processo zombie já está encerrado para os nossos efeitos.
        return bool(status) and "Z" not in status

    except Exception:
        return False


def _wait_for_real_processes(pids, timeout: float):
    """
    Aguarda apenas os processos que continuam realmente ativos.
    """
    remaining = set(pids)
    deadline = time.monotonic() + timeout

    while remaining and time.monotonic() < deadline:
        remaining = {
            pid
            for pid in remaining
            if _pid_is_really_running(pid)
        }

        if remaining:
            time.sleep(0.10)

    return remaining


def kill_all_apps() -> bool:
    """
    Encerra a sessão rapidamente e gera o relatório usando
    processos reais, sem os resultados atrasados do NSWorkspace.
    """
    global _LAST_KILL_REPORT

    current_pid = os.getpid()
    protected_bundle_ids = {
        "com.apple.finder",
    }

    targets = {}
    apps_by_pid = {}

    _close_finder_windows()

    # Faz apenas uma leitura inicial dos aplicativos.
    for app in _regular_apps():
        try:
            pid = int(app.processIdentifier())

            if pid == current_pid:
                continue

            bundle_id = app.bundleIdentifier() or ""

            if bundle_id in protected_bundle_ids:
                app.hide()
                continue

            name = app.localizedName() or "Aplicativo"

            targets[pid] = {
                "name": name,
                "vmware": _is_vmware(app),
            }

            apps_by_pid[pid] = app

        except Exception as error:
            print(f"[KILL] Falha ao preparar aplicativo: {error}")

    # Primeira tentativa para todos, sem esperar app por app.
    for pid, app in apps_by_pid.items():
        try:
            app.terminate()

        except Exception as error:
            name = targets[pid]["name"]
            print(f"[KILL] Falha ao encerrar {name}: {error}")

    # Espera curta global.
    remaining = _wait_for_real_processes(
        targets.keys(),
        timeout=1.6,
    )

    # Segunda tentativa somente no que realmente continua aberto.
    for pid in list(remaining):
        app = apps_by_pid.get(pid)

        if app is None:
            continue

        try:
            app.terminate()

        except Exception as error:
            name = targets[pid]["name"]
            print(
                f"[KILL] Segunda tentativa falhou em {name}: {error}"
            )

    remaining = _wait_for_real_processes(
        remaining,
        timeout=0.7,
    )

    # VMware recebe tratamento especial somente se tiver sobrevivido.
    vmware_remaining = {
        pid
        for pid in remaining
        if targets.get(pid, {}).get("vmware")
    }

    if vmware_remaining:
        _run_osascript(
            'tell application "VMware Fusion" to quit',
            timeout=2,
        )

        remaining = _wait_for_real_processes(
            remaining,
            timeout=0.5,
        )

    # Último recurso: força apenas o VMware.
    for pid in list(remaining):
        if not targets.get(pid, {}).get("vmware"):
            continue

        app = apps_by_pid.get(pid)

        if app is None:
            continue

        try:
            app.forceTerminate()

        except Exception as error:
            print(
                "[KILL] Não foi possível forçar "
                f"VMware Fusion: {error}"
            )

    remaining = _wait_for_real_processes(
        remaining,
        timeout=0.4,
    )

    # Limpeza da sessão.
    desktop_ok = _empty_folder(
        Path.home() / "Desktop"
    )

    trash_ok = empty_trash()
    cache_ok = clean_safe_caches()
    memory_ok = _release_safe_memory()

    # Confirma novamente diretamente nos processos reais.
    final_remaining = {
        pid
        for pid in targets
        if _pid_is_really_running(pid)
    }

    remaining_names = [
        targets[pid]["name"]
        for pid in targets
        if pid in final_remaining
    ]

    closed_count = len(targets) - len(final_remaining)

    _LAST_KILL_REPORT = {
        "closed": closed_count,
        "total": len(targets),
        "desktop": desktop_ok,
        "trash": trash_ok,
        "cache": cache_ok,
        "memory": memory_ok,
        "remaining": remaining_names,
    }

    if remaining_names:
        print(
            "[KILL] Permaneceram realmente abertos: "
            + ", ".join(remaining_names)
        )

    return (
        not remaining_names
        and desktop_ok
        and trash_ok
        and cache_ok
        and memory_ok
    )


def _make_writable(path: Path):
    try:
        current_mode = path.stat().st_mode
        path.chmod(current_mode | stat.S_IWUSR)
    except OSError:
        pass


def _remove_path(path: Path) -> bool:
    try:
        if path.is_symlink() or path.is_file():
            _make_writable(path)
            path.unlink(missing_ok=True)

        elif path.is_dir():
            shutil.rmtree(
                path,
                onerror=lambda function, value, exception: (
                    _make_writable(Path(value)),
                    function(value),
                ),
            )

        return True

    except Exception as error:
        print(
            f"[CL] Não foi possível apagar "
            f"{path}: {error}"
        )
        return False


def _empty_folder(folder: Path) -> bool:
    if not folder.exists():
        return True

    try:
        items = list(folder.iterdir())

    except Exception as error:
        print(
            f"[CL] Não foi possível abrir "
            f"{folder}: {error}"
        )
        return False

    ok = True

    for item in items:
        ok = _remove_path(item) and ok

    return ok


def empty_trash() -> bool:
    """Usa o helper persistente do M87 para esvaziar a Lixeira."""
    return _stable_empty_trash()

def clean_safe_caches() -> bool:
    """
    Remove somente caches Python do projeto M87.

    Não percorre caches gerais do macOS nem temporários de outros apps.
    """
    ok = True

    for cache_dir in list(
        PROJECT_ROOT.rglob("__pycache__")
    ):
        ok = _remove_path(cache_dir) and ok

    for pyc_file in list(
        PROJECT_ROOT.rglob("*.pyc")
    ):
        ok = _remove_path(pyc_file) and ok

    return ok


def clean_desktop_and_trash() -> bool:
    """Limpa o Desktop e a Lixeira usando uma única rotina central."""
    # A Lixeira vem primeiro para que qualquer pedido de permissão do macOS
    # apareça antes da limpeza do Desktop e para evitar falhas silenciosas.
    trash_ok = empty_trash()

    desktop_ok = _empty_folder(
        Path.home() / "Desktop"
    )

    if not trash_ok:
        print("[CL] Desktop limpo, mas a Lixeira não pôde ser esvaziada.")

    return desktop_ok and trash_ok