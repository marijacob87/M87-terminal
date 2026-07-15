from PySide6.QtCore import QTimer

from core.app_search import open_application, search_applications
from core.calculator import calculate, is_calculation
from core.client_search import open_path, search_fast_client
from core.running_apps import close_running_application, search_running_applications


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
    # #texto = busca app aberto e fecha
    # Ex: #acr
    # =========================

    if text.startswith("#"):
        query = text[1:].strip()
        results = search_running_applications(query)

        app.input.clear()
        app.clear_suggestions()

        if results:
            close_running_application(results[0])
        else:
            show_temporary_placeholder(
                app.input,
                "aplicativo aberto não encontrado"
            )

        return

    # =========================
    # //texto = busca aplicativo
    # Ex: //illustrator
    # =========================

    if text.startswith("//"):
        query = text[2:].strip()
        results = search_applications(query)

        app.input.clear()
        app.clear_suggestions()

        if not query:
            show_temporary_placeholder(
                app.input,
                "digite o nome do aplicativo"
            )
        elif results:
            open_application(results[0])
        else:
            show_temporary_placeholder(
                app.input,
                "aplicativo não encontrado"
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
