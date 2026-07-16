import os
import sys

from core.anydesk import (
    get_anydesk_suggestions,
    open_anydesk_app,
    open_anydesk_machine,
)
from core.app_search import open_application
from core.app_tracker import restart_app
from core.client_search import open_path
from core.running_apps import close_running_application
from core.config import BREAKPOINT_WIDTH
from core.executor import execute
from core.system_actions import get_last_kill_report
from core.input_handler import handle_input_text
from core.suggestion_engine import get_suggestions
from ui.constants import PDF_ACTIONS


class CommandControllerMixin:
    def _clear_input_silently(self):
        """
        Limpa o QLineEdit interno sem disparar textChanged.

        Bloquear self.input não basta, porque TerminalInput é
        apenas o QWidget exterior. O sinal vem de self.input.edit.
        """
        self.input.edit.blockSignals(True)
        self.input.clear()
        self.input.edit.blockSignals(False)

    def _open_anydesk_menu(self, query=""):
        self.anydesk_menu_active = True

        self.suggestions.set_items(
            get_anydesk_suggestions(query)
        )

        self.input.setFocus()

    def update_suggestions(self, text):
        text = text.strip()
        upper_text = text.upper()

        if self.current_pdf:
            suggestions = self.get_pdf_suggestions(text)

        elif (
            upper_text == "ANY"
            or upper_text.startswith("ANY ")
        ):
            self.anydesk_menu_active = True

            query = text[3:].strip()

            suggestions = get_anydesk_suggestions(
                query
            )

        else:
            # Quando o menu ANY já está aberto e o campo
            # está vazio, não recria a lista de comandos.
            if (
                getattr(
                    self,
                    "anydesk_menu_active",
                    False,
                )
                and not text
            ):
                return

            self.anydesk_menu_active = False

            suggestions = get_suggestions(
                text,
                self.commands,
            )

        if suggestions:
            self.suggestions.set_items(suggestions)
        else:
            self.clear_suggestions()

        if self.current_pdf:
            from PySide6.QtCore import QTimer

            QTimer.singleShot(
                0,
                self.ajustar_altura_ao_conteudo,
            )

    def clear_suggestions(self):
        self.suggestions.clear()

    def move_suggestion_up(self):
        self.suggestions.move_up()

    def move_suggestion_down(self):
        self.suggestions.move_down()

    def execute_selected_suggestion(self):
        selected = self.suggestions.selected_item()

        if not selected:
            return False

        # Guarda a seleção antes de limpar qualquer coisa.
        self._clear_input_silently()
        self.clear_suggestions()

        self.anydesk_menu_active = False

        if isinstance(selected, dict):
            selected_type = selected.get("type")

            if selected_type == "pdf_action":
                self.execute_pdf_action(selected)
                return True

            if selected_type == "application":
                open_application(selected)
                return True

            if selected_type == "running_application":
                close_running_application(selected)
                return True

            if selected_type == "anydesk_machine":
                open_anydesk_machine(
                    selected.get("id", "")
                )
                return True

            if selected_type == "anydesk_app":
                open_anydesk_app()
                return True

            self.execute_command(
                selected.get("code", "")
            )

            return True

        open_path(selected)
        return True

    def execute_command(self, code):
        code = code.upper()

        if code == "ANY":
            self._clear_input_silently()
            self._open_anydesk_menu()
            return

        if code in ("RE", "RES"):
            if self.last_real_app:
                restart_app(self.last_real_app)

            return

        if code == "MON":
            from ui.montagem_dialog import MontagemDialog

            dialog = MontagemDialog(self)
            dialog.exec()
            self.input.setFocus()
            return

        if code == "BAR":
            from ui.code_generator_dialog import CodeGeneratorDialog

            dialog = CodeGeneratorDialog(self)
            dialog.exec()
            self.input.setFocus()
            return

        command = next(
            (
                item
                for item in self.commands
                if item.get(
                    "code",
                    "",
                ).upper() == code
            ),
            None,
        )

        if not command:
            return

        if code == "KILL":
            from PySide6.QtWidgets import QApplication

            self.session_result_label.setText("Encerrando sessão...")
            self.session_result_label.show()
            self.ajustar_altura_ao_conteudo()
            QApplication.processEvents()

        result = execute(command)

        if code == "KILL":
            from PySide6.QtCore import QTimer

            report = get_last_kill_report()
            remaining = report.get("remaining", [])
            closed = report.get("closed", 0)
            total = report.get("total", 0)

            lines = [
                "Sessão encerrada",
                f"Aplicativos: {closed}/{total} fechados",
                f"Desktop: {'limpo' if report.get('desktop', False) else 'não concluído'}",
                f"Lixeira: {'vazia' if report.get('trash', False) else 'não concluída'}",
                f"Cache: {'limpo' if report.get('cache', False) else 'não concluído'}",
                f"Memória: {'liberada' if report.get('memory', False) else 'não concluída'}",
            ]

            if remaining:
                lines.append("Ainda abertos: " + ", ".join(remaining))

            self.session_result_label.setText("\n".join(lines))
            self.session_result_label.show()
            QTimer.singleShot(0, self.ajustar_altura_ao_conteudo)
            QTimer.singleShot(12000, self.clear_session_result)

        if result == "reload":
            self.restart_app()

    def clear_session_result(self):
        if not hasattr(self, "session_result_label"):
            return

        self.session_result_label.clear()
        self.session_result_label.hide()

        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, self.restaurar_altura_normal)

    def execute_from_input(self):
        text = self.input.text().strip()
        upper_text = text.upper()

        if self.current_pdf:
            pdf_action = next(
                (
                    item
                    for item in PDF_ACTIONS
                    if item.get(
                        "code",
                        "",
                    ).upper() == upper_text
                ),
                None,
            )

            if pdf_action:
                self._clear_input_silently()
                self.clear_suggestions()
                self.execute_pdf_action(pdf_action)
                return

        # O texto ANY já transforma as sugestões na lista de máquinas.
        # Portanto, o primeiro Enter deve executar imediatamente a máquina
        # destacada, em vez de consumir um Enter apenas para abrir outro menu.
        if (
            upper_text == "ANY"
            or upper_text.startswith("ANY ")
            or (
                getattr(
                    self,
                    "anydesk_menu_active",
                    False,
                )
                and not text
            )
        ):
            if self.execute_selected_suggestion():
                return

            # Fallback raro: mantém o menu disponível caso ainda não exista
            # nenhuma sugestão pronta no instante do Enter.
            self._clear_input_silently()
            self._open_anydesk_menu(
                text[3:].strip()
                if upper_text.startswith("ANY")
                else ""
            )
            return

        if self.execute_selected_suggestion():
            return

        handle_input_text(self, text)

    def restart_app(self):
        self.save_current_state()

        os.execv(
            sys.executable,
            [sys.executable] + sys.argv,
        )

    def rebuild_command_grid(self):
        columns = (
            1
            if self.width() < BREAKPOINT_WIDTH
            else 2
        )

        if columns == self.current_columns:
            return

        self.current_columns = columns

        while self.commands_grid.count():
            item = self.commands_grid.takeAt(0)
            widget = item.widget()

            if widget:
                widget.setParent(None)

        section_order = ["Sistema", "Abrir", "Ferramentas"]

        if columns == 1:
            row_index = 0

            for section in section_order:
                widgets = self.command_sections.get(section, [])

                if not widgets:
                    continue

                self.commands_grid.addWidget(
                    self.section_labels[section],
                    row_index,
                    0,
                )
                row_index += 1

                for widget in widgets:
                    self.commands_grid.addWidget(
                        widget,
                        row_index,
                        0,
                    )
                    row_index += 1

            return

        left_row = 0
        system_widgets = self.command_sections.get("Sistema", [])

        if system_widgets:
            self.commands_grid.addWidget(
                self.section_labels["Sistema"],
                left_row,
                0,
            )
            left_row += 1

            for widget in system_widgets:
                self.commands_grid.addWidget(
                    widget,
                    left_row,
                    0,
                )
                left_row += 1

        right_row = 0

        for section in ["Abrir", "Ferramentas"]:
            widgets = self.command_sections.get(section, [])

            if not widgets:
                continue

            self.commands_grid.addWidget(
                self.section_labels[section],
                right_row,
                1,
            )
            right_row += 1

            for widget in widgets:
                self.commands_grid.addWidget(
                    widget,
                    right_row,
                    1,
                )
                right_row += 1

