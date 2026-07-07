from PySide6.QtCore import QTimer

from core.calculator import calculate, is_calculation
from core.client_search import (
    open_path,
    search_fast_client,
    finder_search,
)


def show_temporary_placeholder(input_widget, message):
    input_widget.setPlaceholderText(message)

    QTimer.singleShot(
        1200,
        lambda: input_widget.setPlaceholderText("")
    )


def handle_input_text(app, text):
    text = text.strip()

    if not text:
        return

    # =========================
    # //texto = busca no Finder
    # Ex: //clube dos gestores
    # =========================

    if text.startswith("//"):
        query = text[2:].strip()
        app.input.clear()

        if query:
            finder_search(query)
        else:
            show_temporary_placeholder(
                app.input,
                "digite o que buscar"
            )

        return

    # =========================
    # /texto = busca rápida e abre direto
    # Ex: /rota
    # =========================

    if text.startswith("/") and not text.startswith("/app"):
        query = text[1:].strip()
        results = search_fast_client(query)

        app.input.clear()
        app.clear_suggestions()

        if results:
            open_path(results[0])
        else:
            show_temporary_placeholder(
                app.input,
                "cliente não encontrado"
            )

        return

    # =========================
    # SUGESTÃO NORMAL
    # =========================

    selected = app.suggestions.selected_item()

    if selected:
        app.execute_selected_suggestion()
        return

    # =========================
    # CÁLCULO
    # =========================

    if is_calculation(text):
        try:
            result = calculate(text)
            app.input.setText(result)
            return
        except Exception:
            show_temporary_placeholder(
                app.input,
                "cálculo inválido"
            )
            return

    # =========================
    # COMANDO NORMAL
    # =========================

    code = text.upper()
    app.input.clear()

    if code in app.rows:
        app.rows[code].execute()
    else:
        show_temporary_placeholder(
            app.input,
            "comando não encontrado"
        )