from PySide6.QtCore import QTimer

from core.app_search import open_application, search_applications
from core.calculator import calculate, is_calculation
from core.client_search import open_path, search_fast_client
from core.developer_tools import publish_git_update
from core.project_zip import create_project_zip
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
    # #code = abre o projeto no VS Code
    # =========================

    if text.lower() == "#code":
        app.input.clear()
        app.clear_suggestions()
        app.open_project_in_vscode()
        return

    # =========================
    # #git mensagem = add, commit e push
    # Ex: #git inclui comando de backup
    # =========================

    if text.lower() == "#git" or text.lower().startswith("#git "):
        from PySide6.QtWidgets import QApplication

        commit_message = text[4:].strip()
        app.input.clear()
        app.clear_suggestions()

        if not commit_message:
            show_temporary_placeholder(
                app.input,
                "escreva a atualização depois de #git"
            )
            return

        app.session_result_label.setText("↑ Enviando atualização para o GitHub...")
        app.session_result_label.show()
        QApplication.processEvents()

        result = publish_git_update(commit_message)
        app.session_result_label.setText(result.message)

        QTimer.singleShot(0, app.ajustar_altura_ao_conteudo)
        QTimer.singleShot(10000, app.clear_session_result)
        return

    # =========================
    # #zip = cria uma cópia limpa do projeto no Desktop
    # =========================

    if text.lower() == "#zip":
        from PySide6.QtWidgets import QApplication

        app.input.clear()
        app.clear_suggestions()
        app.session_result_label.setText("📦 Criando ZIP do projeto...")
        app.session_result_label.show()
        QApplication.processEvents()

        try:
            zip_path = create_project_zip()
            app.session_result_label.setText(
                "✓ ZIP criado no Desktop\n"
                f"{zip_path.name}"
            )
        except Exception as error:
            app.session_result_label.setText(
                "Não foi possível criar o ZIP.\n"
                f"{error}"
            )

        QTimer.singleShot(0, app.ajustar_altura_ao_conteudo)
        QTimer.singleShot(8000, app.clear_session_result)
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
