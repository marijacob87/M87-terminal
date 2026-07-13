import os
import sys

from core.app_tracker import restart_app
from core.client_search import open_path
from core.config import BREAKPOINT_WIDTH
from core.executor import execute
from core.input_handler import handle_input_text
from core.suggestion_engine import get_suggestions
from ui.constants import PDF_ACTIONS


class CommandControllerMixin:
    def update_suggestions(self, text):
        if self.current_pdf:
            suggestions = self.get_pdf_suggestions(text)
        else:
            suggestions = get_suggestions(text, self.commands)

        if suggestions:
            self.suggestions.set_items(suggestions)
        else:
            self.clear_suggestions()

        if self.current_pdf:
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, self.ajustar_altura_ao_conteudo)

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

        self.input.blockSignals(True)
        self.input.clear()
        self.input.blockSignals(False)
        self.clear_suggestions()

        if isinstance(selected, dict):
            if selected.get("type") == "pdf_action":
                self.execute_pdf_action(selected)
                return True

            self.execute_command(selected.get("code", ""))
            return True

        open_path(selected)
        return True

    def execute_command(self, code):
        code = code.upper()

        if code == "RE":
            if self.last_real_app:
                restart_app(self.last_real_app)
            return

        command = next(
            (
                item
                for item in self.commands
                if item.get("code", "").upper() == code
            ),
            None,
        )

        if not command:
            return

        result = execute(command)

        if result == "reload":
            self.restart_app()

    def execute_from_input(self):
        text = self.input.text().strip()

        if self.current_pdf:
            pdf_action = next(
                (
                    item
                    for item in PDF_ACTIONS
                    if item.get("code", "").upper() == text.upper()
                ),
                None,
            )

            if pdf_action:
                self.input.blockSignals(True)
                self.input.clear()
                self.input.blockSignals(False)
                self.clear_suggestions()
                self.execute_pdf_action(pdf_action)
                return

        if self.execute_selected_suggestion():
            return

        handle_input_text(self, text)

    def restart_app(self):
        self.save_current_state()
        os.execv(sys.executable, [sys.executable] + sys.argv)

    def rebuild_command_grid(self):
        columns = 1 if self.width() < BREAKPOINT_WIDTH else 2

        if columns == self.current_columns:
            return

        self.current_columns = columns

        while self.commands_grid.count():
            item = self.commands_grid.takeAt(0)
            widget = item.widget()

            if widget:
                widget.setParent(None)

        if columns == 1:
            for index, widget in enumerate(self.command_widgets):
                self.commands_grid.addWidget(widget, index, 0)
            return

        half = (len(self.command_widgets) + 1) // 2

        for index, widget in enumerate(self.command_widgets):
            column = 0 if index < half else 1
            row = index if index < half else index - half
            self.commands_grid.addWidget(widget, row, column)
