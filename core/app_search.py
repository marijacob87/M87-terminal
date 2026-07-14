import subprocess
import unicodedata
from pathlib import Path


APP_ROOTS = (
    Path('/Applications'),
    Path('/System/Applications'),
    Path.home() / 'Applications',
)

MAX_RESULTS = 12

# O nome real do pacote costuma estar em inglês, mesmo com o macOS em português.
# A busca considera os dois nomes, mas abre sempre o caminho real do aplicativo.
APP_ALIASES = {
    'books': ('livros',),
    'maps': ('mapas',),
    'photos': ('fotos',),
    'messages': ('mensagens',),
    'music': ('musica', 'música'),
    'notes': ('notas',),
    'reminders': ('lembretes',),
    'contacts': ('contatos', 'contactos'),
    'calendar': ('calendario', 'calendário'),
    'calculator': ('calculadora',),
    'preview': ('pre visualizacao', 'pré-visualização', 'visualizacao', 'visualização'),
    'voice memos': ('gravador', 'gravacoes', 'gravações'),
    'weather': ('tempo', 'meteorologia'),
    'find my': ('buscar',),
    'home': ('casa',),
    'shortcuts': ('atalhos',),
    'system settings': (
        'definicoes do sistema',
        'definições do sistema',
        'ajustes',
    ),
    'facetime': ('face time',),
    'mail': ('email', 'e-mail', 'correio'),
    'news': ('noticias', 'notícias'),
    'stocks': ('bolsa', 'acoes', 'ações'),
    'podcasts': ('podcasts',),
    'freeform': ('forma livre',),
}


def normalize(text):
    text = str(text).strip().lower()
    text = unicodedata.normalize('NFKD', text)
    return ''.join(char for char in text if not unicodedata.combining(char))


def _iter_apps(root):
    """Lista apps recursivamente sem entrar dentro de pacotes .app."""
    if not root.exists():
        return

    pending = [root]

    while pending:
        folder = pending.pop()

        try:
            children = list(folder.iterdir())
        except (OSError, PermissionError):
            continue

        for child in children:
            try:
                is_directory = child.is_dir()
            except OSError:
                continue

            if not is_directory:
                continue

            if child.suffix.lower() == '.app':
                yield child
            else:
                pending.append(child)


def _search_names(app_path):
    """Retorna o nome físico e os aliases conhecidos do aplicativo."""
    real_name = app_path.stem
    names = [real_name]
    names.extend(APP_ALIASES.get(normalize(real_name), ()))
    return names


def _score_name(app_name, query):
    name = normalize(app_name)

    if name == query:
        return 0

    if name.startswith(query):
        return 1

    words = name.replace('-', ' ').replace('_', ' ').split()
    if any(word.startswith(query) for word in words):
        return 2

    if query in name:
        return 3

    return 999


def _best_match(app_path, query):
    candidates = _search_names(app_path)
    scored = [(_score_name(name, query), name) for name in candidates]
    score, matched_name = min(scored, key=lambda item: (item[0], normalize(item[1])))
    return score, matched_name


def search_applications(query):
    query = normalize(query)

    if not query:
        return []

    found = []
    seen = set()

    for root in APP_ROOTS:
        for app_path in _iter_apps(root):
            try:
                score, matched_name = _best_match(app_path, query)
            except (OSError, ValueError):
                continue

            if score >= 999:
                continue

            key = normalize(str(app_path))
            if key in seen:
                continue

            seen.add(key)
            found.append({
                'type': 'application',
                'name': matched_name,
                'path': str(app_path),
                'score': score,
            })

    found.sort(
        key=lambda item: (
            item['score'],
            normalize(item['name']),
            normalize(item['path']),
        )
    )

    for item in found:
        item.pop('score', None)

    return found[:MAX_RESULTS]


def open_application(app_item):
    if isinstance(app_item, dict):
        app_path = app_item.get('path', '')
    else:
        app_path = str(app_item)

    if not app_path:
        return False

    try:
        subprocess.Popen(
            ['open', app_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        return False

    return True