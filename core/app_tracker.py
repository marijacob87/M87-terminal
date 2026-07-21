import os
import subprocess
import time

from AppKit import NSRunningApplication, NSWorkspace


IGNORED_APPS = {
    "Python",
    "Python Launcher",
    "Terminal",
    "iTerm2",
    "Visual Studio Code",
    "M87 TERM",
    "M87 Terminal",
}

IGNORED_BUNDLE_IDS = {
    "com.apple.Terminal",
    "com.googlecode.iterm2",
    "com.microsoft.VSCode",
}


def _app_snapshot(running_app):
    if running_app is None:
        return None

    try:
        return {
            "name": running_app.localizedName() or "",
            "bundle_id": running_app.bundleIdentifier() or "",
            "pid": int(running_app.processIdentifier()),
        }
    except Exception:
        return None


def get_frontmost_app():
    """Retorna o app realmente em primeiro plano, sem confundir o próprio M87."""
    try:
        running_app = NSWorkspace.sharedWorkspace().frontmostApplication()
        app = _app_snapshot(running_app)

        if not app or app["pid"] == os.getpid():
            return None

        return app
    except Exception:
        return None


def is_valid_app(app):
    if not app:
        return False

    if isinstance(app, str):
        return app not in IGNORED_APPS

    name = str(app.get("name", "")).strip()
    bundle_id = str(app.get("bundle_id", "")).strip()
    pid = int(app.get("pid", 0) or 0)

    if not name or pid == os.getpid():
        return False
    if name in IGNORED_APPS:
        return False
    if bundle_id in IGNORED_BUNDLE_IDS:
        return False

    return True


def _find_running_app(app):
    try:
        pid = int(app.get("pid", 0) or 0)
    except (TypeError, ValueError):
        pid = 0

    if pid:
        running = NSRunningApplication.runningApplicationWithProcessIdentifier_(pid)
        if running is not None and not running.isTerminated():
            return running

    bundle_id = str(app.get("bundle_id", "")).strip()
    if bundle_id:
        matches = NSRunningApplication.runningApplicationsWithBundleIdentifier_(bundle_id)
        if matches:
            return matches[0]

    return None


def restart_app(app):
    """Fecha o último app usado e o abre novamente de forma confiável."""
    if isinstance(app, str):
        app = {"name": app, "bundle_id": "", "pid": 0}

    if not is_valid_app(app):
        return False

    name = str(app.get("name", "")).strip()
    bundle_id = str(app.get("bundle_id", "")).strip()
    running = _find_running_app(app)

    if running is not None:
        try:
            running.terminate()
        except Exception:
            pass

        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if running.isTerminated():
                break
            time.sleep(0.1)

        if not running.isTerminated():
            try:
                running.forceTerminate()
            except Exception:
                pass
            time.sleep(0.4)

    command = ["open"]
    if bundle_id:
        command += ["-b", bundle_id]
    else:
        command += ["-a", name]

    result = subprocess.run(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )

    return result.returncode == 0
