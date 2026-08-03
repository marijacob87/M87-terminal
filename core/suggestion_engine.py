from core.anydesk import get_anydesk_suggestions
from core.running_apps import search_running_applications


def command_score(item, query):
    q = query.lower().strip()
    code = item.get("code", "").lower()
    label = item.get("label", "").lower()

    if code == q:
        return 0

    if code.startswith(q):
        return 1

    if label.startswith(q):
        return 2

    if q in code:
        return 3

    if q in label:
        return 4

    return 999


def get_suggestions(query, commands):
    query = query.strip()

    if not query:
        return commands

    # ANY ou ANY texto = menu/busca do AnyDesk
    upper_query = query.upper()

    if upper_query == "ANY" or upper_query.startswith("ANY "):
        anydesk_query = query[3:].strip()
        return get_anydesk_suggestions(anydesk_query)

    # Ferramentas internas de desenvolvimento não aparecem
    # na lista visual de comandos.
    lower_query = query.lower()
    if (
        lower_query in {"#zip", "#code", "#git"}
        or lower_query.startswith("#git ")
    ):
        return []

    # #nome = aplicativos abertos no momento
    if query.startswith("#"):
        app_query = query[1:].strip()
        return search_running_applications(app_query)

    # /#nome = busca no Finder; //nome = pasta dentro de cliente
    if query.startswith("/#") or query.startswith("//"):
        return []

    # /nome = cliente
    if query.startswith("/") and not query.startswith("/app"):
        return []

    matches = [
        item
        for item in commands
        if command_score(item, query) < 999
    ]

    matches.sort(
        key=lambda item: (
            command_score(item, query),
            item.get("code", "").lower(),
            item.get("label", "").lower(),
        )
    )

    return matches
