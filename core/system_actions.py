import os
import time

from AppKit import NSApplicationActivationPolicyRegular, NSWorkspace


def _regular_apps():
    """Retorna os aplicativos visíveis ao utilizador no macOS."""
    workspace = NSWorkspace.sharedWorkspace()

    return [
        app
        for app in workspace.runningApplications()
        if app.activationPolicy() == NSApplicationActivationPolicyRegular
    ]


def minimize_all_apps() -> bool:
    """Oculta todos os aplicativos, mantendo o M87 visível."""
    current_pid = os.getpid()

    for app in _regular_apps():
        try:
            if app.processIdentifier() == current_pid:
                continue

            app.hide()
        except Exception as error:
            print(
                f"[MIN] Não foi possível ocultar "
                f"{app.localizedName()}: {error}"
            )

    return True


def kill_all_apps() -> bool:
    """Encerra todos os aplicativos, mantendo Finder e M87 abertos."""
    current_pid = os.getpid()
    protected_bundle_ids = {
        "com.apple.finder",
    }

    for app in _regular_apps():
        try:
            if app.processIdentifier() == current_pid:
                continue

            bundle_id = app.bundleIdentifier() or ""

            if bundle_id in protected_bundle_ids:
                app.hide()
                continue

            app.terminate()

        except Exception as error:
            print(
                f"[KILL] Não foi possível encerrar "
                f"{app.localizedName()}: {error}"
            )

    # Dá um instante para os aplicativos responderem ao encerramento normal.
    time.sleep(0.4)

    return True
