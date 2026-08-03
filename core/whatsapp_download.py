from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from pathlib import Path

WHATSAPP_URL = "https://web.whatsapp.com/"
SESSION_DIR = Path.home() / "Library" / "Application Support" / "M87 Terminal" / "WhatsApp"
DOWNLOAD_ROOT = Path.home() / "Desktop"
CHROME_PATHS = (
    Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
    Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
    Path("/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"),
)


@dataclass(frozen=True)
class WhatsAppRequest:
    contact: str
    day: date


def _plain(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(char for char in normalized if not unicodedata.combining(char)).casefold()


def parse_whatsapp_command(text: str, today: date | None = None) -> WhatsAppRequest | None:
    """Interpreta WPP [BAIXAR] <contacto> HOJE sem depender de aspas."""
    match = re.fullmatch(
        r"\s*WPP(?:\s+BAIXAR)?\s+(.+?)\s+HOJE\s*",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return None

    contact = match.group(1).strip().strip("\"'")
    if not contact:
        return None

    return WhatsAppRequest(contact=contact, day=today or date.today())


def output_directory(request: WhatsAppRequest) -> Path:
    return DOWNLOAD_ROOT


def available_path(directory: Path, filename: str) -> Path:
    """Devolve um nome livre; arquivos existentes nunca são sobrescritos."""
    source = Path(filename)
    stem = source.stem or "arquivo"
    suffix = source.suffix
    candidate = directory / source.name
    index = 2

    while candidate.exists():
        candidate = directory / f"{stem} ({index}){suffix}"
        index += 1

    return candidate


def _browser_executable() -> str | None:
    for path in CHROME_PATHS:
        if path.is_file():
            return str(path)
    return None


def _launch_context(playwright):
    launch_options = {
        "user_data_dir": str(SESSION_DIR),
        "headless": True,
        "accept_downloads": True,
        "viewport": {"width": 1180, "height": 820},
    }
    executable = _browser_executable()
    if executable:
        launch_options["executable_path"] = executable

    try:
        return playwright.chromium.launch_persistent_context(**launch_options)
    except Exception as error:
        raise WhatsAppDownloadError(
            "Não encontrei um navegador compatível. Instale o Google Chrome "
            "ou execute: python -m playwright install chromium"
        ) from error


def _open_authenticated_page(context, timeout_error, notify):
    page = context.pages[0] if context.pages else context.new_page()
    notify("Abrindo o WhatsApp Web…")
    page.goto(WHATSAPP_URL, wait_until="domcontentloaded", timeout=60_000)
    try:
        page.locator("#pane-side").wait_for(state="visible", timeout=20_000)
    except timeout_error as error:
        raise WhatsAppDownloadError(
            "A sessão do WhatsApp expirou. Será necessário autenticar novamente."
        ) from error
    return page


def list_active_whatsapp_chats(progress=None, limit: int = 20) -> list[str]:
    """Lista as conversas atualmente visíveis na barra lateral do WhatsApp."""
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeout
        from playwright.sync_api import sync_playwright
    except ImportError as error:
        raise WhatsAppDownloadError(
            "Falta instalar a automação Web. Execute novamente o instalador do M87."
        ) from error

    notify = progress or (lambda _message: None)
    SESSION_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        context = _launch_context(playwright)
        try:
            page = _open_authenticated_page(context, PlaywrightTimeout, notify)
            notify("Carregando as conversas ativas…")
            rows = page.locator(
                '#pane-side [role="row"][data-testid^="list-item-"]'
            )
            rows.first.wait_for(state="visible", timeout=5000)
            chats = []

            for index in range(rows.count()):
                contact_titles = rows.nth(index).locator("span[title]")
                if contact_titles.count() == 0:
                    continue

                # O primeiro título da linha é o contacto. Os restantes são
                # prévias da mensagem e links, não conversas.
                title = (
                    contact_titles.first.get_attribute("title") or ""
                ).strip()
                if title and title not in chats:
                    chats.append(title)
                if len(chats) >= limit:
                    break

            if not chats:
                raise WhatsAppDownloadError("Não encontrei conversas ativas no WhatsApp.")

            return chats
        finally:
            context.close()


def _message_matches(pre_plain_text: str, request: WhatsAppRequest) -> bool:
    date_match = re.search(r"(\d{1,2})/(\d{1,2})/(\d{2,4})", pre_plain_text)
    if not date_match:
        return False

    day, month, year = (int(value) for value in date_match.groups())
    if year < 100:
        year += 2000

    try:
        message_day = date(year, month, day)
    except ValueError:
        return False

    return message_day == request.day and _plain(request.contact) in _plain(pre_plain_text)


def _is_outgoing_labels(labels: list[str]) -> bool:
    outgoing_statuses = {
        "lida",
        "entregue",
        "enviada",
        "read",
        "delivered",
        "sent",
    }
    return any(
        _plain(label).startswith(("voce:", "you:"))
        or _plain(label) in outgoing_statuses
        for label in labels
    )


def _filename_from_media_title(title: str) -> str:
    match = re.search(r'"([^"]+)"', title)
    return Path(match.group(1)).name if match else ""


def _media_records(locator) -> list[dict]:
    records = []
    for index in range(locator.count()):
        media = locator.nth(index)
        message = media.locator(
            'xpath=ancestor::*[starts-with(@data-testid,"conv-msg-")][1]'
        )
        if message.count() == 0:
            continue
        labels = message.locator("[aria-label]")
        aria_labels = [
            (labels.nth(label_index).get_attribute("aria-label") or "").strip()
            for label_index in range(labels.count())
        ]
        if _is_outgoing_labels(aria_labels):
            continue
        test_id = message.get_attribute("data-testid") or ""
        message_id = test_id.removeprefix("conv-msg-")
        media_type = media.get_attribute("data-testid") or ""
        if not message_id or media_type not in {"document-thumb", "image-thumb"}:
            continue
        media_title = (media.get_attribute("title") or "").strip()
        record = {
            "id": message_id,
            "type": media_type,
            "name": _filename_from_media_title(media_title),
        }
        if record not in records:
            records.append(record)
    return records


def _first_marker(main, labels):
    for label in labels:
        marker = main.get_by_text(label, exact=True)
        if marker.count():
            return marker
    return None


def _scroll_to_bottom(page) -> None:
    main = page.locator("#main")
    main.hover()
    for _attempt in range(4):
        page.mouse.wheel(0, 100_000)
        page.wait_for_timeout(180)


def _collect_day_media(page, requested_day: date) -> list[dict]:
    """Recolhe documentos e imagens limitados ao dia solicitado."""
    main = page.locator("#main")
    main.hover()
    records = []
    difference = (date.today() - requested_day).days
    excluded_keys = set()

    if difference == 0:
        target_labels = ("Hoje", "Today")
        newer_labels = ()
    elif difference == 1:
        today_is_loaded = _first_marker(main, ("Hoje", "Today")) is not None
        if today_is_loaded:
            newer_records = _collect_day_media(page, date.today())
            excluded_keys = {
                (record["id"], record["type"])
                for record in newer_records
            }
            _scroll_to_bottom(page)
        target_labels = ("Ontem", "Yesterday")
        newer_labels = ("Hoje", "Today")
    else:
        raise WhatsAppDownloadError(
            "Por enquanto, o WPP aceita somente Hoje ou Ontem."
        )

    target_seen = False

    # Se Ontem já é o dia mais recente, existem dois marcadores enquanto o
    # separador real ainda está carregado: o separador e o cabeçalho fixo.
    # Percorre somente enquanto ambos existirem. Quando resta um, ele é apenas
    # o cabeçalho fixo e as mensagens seguintes já pertencem a dias anteriores.
    initial_target = _first_marker(main, target_labels)
    initial_newer = _first_marker(main, newer_labels)
    if difference == 1 and initial_target is not None and initial_newer is None:
        initial_count = initial_target.count()
        latest_records = []

        for _attempt in range(12):
            marker = _first_marker(main, target_labels)
            if marker is None:
                break
            if initial_count >= 2 and marker.count() < 2:
                break

            media = marker.last.locator(
                'xpath=following::*['
                '@data-testid="document-thumb" or '
                '@data-testid="image-thumb"]'
            )
            for record in _media_records(media):
                if record not in latest_records:
                    latest_records.append(record)

            page.mouse.wheel(0, -1600)
            page.wait_for_timeout(200)

        return latest_records

    for _attempt in range(32):
        target_marker = _first_marker(main, target_labels)
        newer_marker = _first_marker(main, newer_labels)

        if target_marker is not None:
            target_seen = True
            media = target_marker.last.locator(
                'xpath=following::*['
                '@data-testid="document-thumb" or '
                '@data-testid="image-thumb"]'
            )
            candidates = _media_records(media)

            newer_keys = set()
            if newer_marker is not None:
                newer_media = newer_marker.last.locator(
                    'xpath=following::*['
                    '@data-testid="document-thumb" or '
                    '@data-testid="image-thumb"]'
                )
                newer_keys = {
                    (record["id"], record["type"])
                    for record in _media_records(newer_media)
                }
            newer_keys.update(excluded_keys)

            for record in candidates:
                key = (record["id"], record["type"])
                if key not in newer_keys and record not in records:
                    records.append(record)
        else:
            if target_seen:
                break

        page.mouse.wheel(0, -2400)
        page.wait_for_timeout(220)

    return records


def _find_visible_media(page, record: dict):
    message = page.locator(
        f'#main [data-testid="conv-msg-{record["id"]}"]'
    )
    if message.count() == 0:
        return None
    media = message.locator(f'[data-testid="{record["type"]}"]')
    return media.first if media.count() else None


def _restore_chat(page) -> bool:
    """Fecha visualizadores que possam ter ficado abertos após uma falha."""
    main = page.locator("#main")
    for _attempt in range(3):
        viewer = page.locator(
            '[data-testid="pdf-viewer-iframe"], '
            '[data-testid*="media-viewer"]'
        )
        visible_viewer = (
            viewer.count()
            and any(
                viewer.nth(index).is_visible()
                for index in range(viewer.count())
            )
        )
        if main.count() and main.is_visible() and not visible_viewer:
            return True
        page.keyboard.press("Escape")
        page.wait_for_timeout(180)
    return bool(main.count() and main.is_visible())


class WhatsAppDownloadError(RuntimeError):
    pass


def _validate_completed_batch(
    expected: int,
    pending: dict,
    saved_paths: list[Path],
) -> None:
    existing = [
        path
        for path in saved_paths
        if path.is_file() and path.stat().st_size > 0
    ]
    if pending or len(existing) != expected:
        missing = len(pending) + max(0, len(saved_paths) - len(existing))
        raise WhatsAppDownloadError(
            "Download incompleto — não considere o lote concluído.\n"
            f"Esperados: {expected} • Confirmados: {len(existing)} "
            f"• Em falta: {missing}"
        )


def download_whatsapp_files(request: WhatsAppRequest, progress=None) -> tuple[int, Path]:
    """Baixa anexos recebidos hoje na conversa usando uma sessão Web isolada."""
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeout
        from playwright.sync_api import sync_playwright
    except ImportError as error:
        raise WhatsAppDownloadError(
            "Falta instalar a automação Web. Execute novamente o instalador do M87."
        ) from error

    notify = progress or (lambda _message: None)
    destination = output_directory(request)
    destination.mkdir(parents=True, exist_ok=True)
    SESSION_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        context = _launch_context(playwright)
        try:
            page = _open_authenticated_page(context, PlaywrightTimeout, notify)

            notify(f"Abrindo a conversa com {request.contact}…")
            rows = page.locator(
                '#pane-side [role="row"][data-testid^="list-item-"]'
            )
            selected_row = None

            for index in range(rows.count()):
                titles = rows.nth(index).locator("span[title]")
                if titles.count() == 0:
                    continue
                title = (titles.first.get_attribute("title") or "").strip()
                if title == request.contact:
                    selected_row = rows.nth(index)
                    break

            if selected_row is None:
                raise WhatsAppDownloadError(
                    f'A conversa "{request.contact}" já não está visível. '
                    "Digite WPP novamente para atualizar a lista."
                )

            try:
                selected_row.click(timeout=5000)
            except PlaywrightTimeout as error:
                raise WhatsAppDownloadError(
                    f'Não consegui abrir a conversa "{request.contact}".'
                ) from error

            page.locator("#main").wait_for(state="visible", timeout=15_000)
            page.locator(
                '#main [data-testid^="conv-msg-"]'
            ).first.wait_for(state="visible", timeout=5000)

            media_records = _collect_day_media(page, request.day)
            day_label = (
                "hoje"
                if request.day == date.today()
                else "ontem"
            )
            if not media_records:
                raise WhatsAppDownloadError(
                    f'Não encontrei arquivos recebidos {day_label} '
                    f'de "{request.contact}".'
                )

            expected = len(media_records)
            notify(
                f"Verificando {expected} anexos recebidos {day_label}…"
            )

            # Volta ao fim da conversa e percorre novamente para baixar cada
            # documento pelo título. Isso evita perder elementos quando o
            # WhatsApp recicla as mensagens fora da área visível.
            _scroll_to_bottom(page)

            saved_paths = []
            pending = {
                (record["id"], record["type"]): record
                for record in media_records
            }

            for _attempt in range(26):
                for key, record in list(pending.items()):
                    media = _find_visible_media(page, record)
                    if media is None:
                        continue

                    try:
                        download = None

                        # Anexos recebidos que ainda não estão no computador
                        # iniciam o download no próprio clique.
                        try:
                            with page.expect_download(
                                timeout=2000,
                            ) as download_info:
                                media.click(timeout=5000)
                            download = download_info.value
                        except Exception:
                            # Imagens e anexos já carregados abrem o
                            # visualizador; nesse caso usa o botão superior.
                            viewer_downloads = page.locator(
                                'button[aria-label="Download" i], '
                                'button[aria-label="Baixar" i]'
                            )
                            viewer_downloads.first.wait_for(
                                state="visible",
                                timeout=5000,
                            )
                            with page.expect_download(
                                timeout=20_000,
                            ) as download_info:
                                viewer_downloads.first.click(timeout=5000)
                            download = download_info.value

                        target = available_path(
                            destination,
                            download.suggested_filename,
                        )
                        expected_name = record.get("name", "")
                        received_name = Path(
                            download.suggested_filename
                        ).name
                        if (
                            expected_name
                            and _plain(received_name) != _plain(expected_name)
                        ):
                            raise WhatsAppDownloadError(
                                "O nome recebido não coincide com a mensagem: "
                                f"{expected_name} ≠ {received_name}"
                            )
                        download.save_as(target)
                        if not target.is_file() or target.stat().st_size <= 0:
                            raise WhatsAppDownloadError(
                                f"O arquivo {target.name} foi criado vazio."
                            )
                        saved_paths.append(target)
                        pending.pop(key, None)
                        notify(f"Baixando {target.name}…")
                    except Exception as error:
                        print(f"[WPP] Documento não baixado: {error}")
                    finally:
                        page.keyboard.press("Escape")
                        page.wait_for_timeout(120)
                        _restore_chat(page)

                if not pending:
                    break

                if not _restore_chat(page):
                    break
                page.locator("#main").hover(timeout=3000)
                page.mouse.wheel(0, -2400)
                page.wait_for_timeout(220)

            _validate_completed_batch(expected, pending, saved_paths)
            notify(f"Verificação concluída: {expected}/{expected} arquivos.")
            return expected, destination
        finally:
            context.close()
