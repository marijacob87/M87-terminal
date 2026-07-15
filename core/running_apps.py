import os
import unicodedata

from AppKit import NSApplicationActivationPolicyRegular, NSRunningApplication, NSWorkspace


MAX_RESULTS = 12

_PROTECTED_BUNDLE_IDS = {
    "com.apple.finder",
    "com.apple.dock",
    "com.apple.systemuiserver",
}


def _normalize(text):
    text = str(text or "").strip().lower()
    text = unicodedata.normalize("NFKD", text)
    return "".join(char for char in text if not unicodedata.combining(char))


def _score(name, query):
    normalized_name = _normalize(name)

    if not query:
        return 0
    if normalized_name == query:
        return 0
    if normalized_name.startswith(query):
        return 1

    words = normalized_name.replace("-", " ").replace("_", " ").split()
    if any(word.startswith(query) for word in words):
        return 2
    if query in normalized_name:
        return 3

    return 999


def search_running_applications(query=""):
    """Retorna apenas aplicativos visíveis e abertos no momento."""
    query = _normalize(query)
    current_pid = os.getpid()
    results = []
    seen_pids = set()

    for running_app in NSWorkspace.sharedWorkspace().runningApplications():
        try:
            pid = int(running_app.processIdentifier())
            bundle_id = running_app.bundleIdentifier() or ""
            name = running_app.localizedName() or "Aplicativo"
            policy = running_app.activationPolicy()

            if pid == current_pid or pid in seen_pids:
                continue
            if policy != NSApplicationActivationPolicyRegular:
                continue
            if bundle_id in _PROTECTED_BUNDLE_IDS:
                continue

            score = _score(name, query)
            if score >= 999:
                continue

            seen_pids.add(pid)
            results.append({
                "type": "running_application",
                "name": name,
                "pid": pid,
                "bundle_id": bundle_id,
                "score": score,
            })
        except Exception as error:
            print(f"[#] Falha ao ler aplicativo aberto: {error}")

    results.sort(
        key=lambda item: (
            item["score"],
            _normalize(item["name"]),
            item["pid"],
        )
    )

    for item in results:
        item.pop("score", None)

    return results[:MAX_RESULTS]


def close_running_application(app_item):
    """Solicita encerramento normal ao aplicativo selecionado."""
    try:
        pid = int(app_item.get("pid", 0))
    except (TypeError, ValueError):
        return False

    if not pid or pid == os.getpid():
        return False

    running_app = NSRunningApplication.runningApplicationWithProcessIdentifier_(pid)
    if running_app is None or running_app.isTerminated():
        return True

    bundle_id = running_app.bundleIdentifier() or ""
    if bundle_id in _PROTECTED_BUNDLE_IDS:
        return False

    try:
        return bool(running_app.terminate())
    except Exception as error:
        print(f"[#] Não foi possível fechar {app_item.get('name', 'aplicativo')}: {error}")
        return False
