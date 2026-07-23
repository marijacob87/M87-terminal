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
from core.recent_folders import get_recent_folders
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

        from PySide6.QtCore import QTimer

        if suggestions:
            self.suggestions.set_items(suggestions)
            # As sugestões também fazem parte do conteúdo variável. A janela
            # precisa crescer para baixo mesmo quando não há PDF ativo.
            QTimer.singleShot(0, self.ajustar_altura_ao_conteudo)
            QTimer.singleShot(30, self.ajustar_altura_ao_conteudo)
        else:
            self.clear_suggestions()

    def clear_suggestions(self):
        self.suggestions.clear()

        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, self.ajustar_altura_ao_conteudo)
        QTimer.singleShot(30, self.ajustar_altura_ao_conteudo)

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

            if selected_type == "update_action":
                self.install_pending_update()
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

            if selected_type == "recent_folder":
                open_path(selected.get("path", ""))
                return True

            self.execute_command(
                selected.get("code", "")
            )

            return True

        open_path(selected)
        return True

    def _show_routine_progress(self):
        lines = []

        for step in getattr(self, "morning_steps", []):
            status = self.morning_step_status.get(step, "…")
            lines.append(f"▸ {step:<14} {status}")

        self.session_result_label.setText("\n".join(lines))
        self.session_result_label.show()
        self.ajustar_altura_ao_conteudo()

    def _update_morning_step(self, label, ok):
        self.morning_step_status[label] = "✓" if ok else "⚠"
        self._show_routine_progress()

    def _finish_morning_routine(self, elapsed):
        from PySide6.QtCore import QTimer

        elapsed_text = f"{elapsed:.1f}".replace(".", ",")
        self.session_result_label.setText(
            "✓ Tudo pronto! Tenha um ótimo dia, Mari!\n"
            f"Ready in {elapsed_text} s"
        )
        self.session_result_label.show()
        QTimer.singleShot(0, self.ajustar_altura_ao_conteudo)
        QTimer.singleShot(12000, self.clear_session_result)

        self.morning_worker = None

    def _start_morning_routine(self):
        from core.morning_routine import MorningRoutineWorker, STEPS

        if getattr(self, "morning_worker", None):
            return

        self.morning_steps = list(STEPS)
        self.morning_step_status = {
            step: "…" for step in self.morning_steps
        }
        self._show_routine_progress()

        self.morning_worker = MorningRoutineWorker(self)
        self.morning_worker.progress.connect(self._update_morning_step)
        self.morning_worker.completed.connect(self._finish_morning_routine)
        self.morning_worker.start()

    def _finish_mount_volumes(self, ok, elapsed):
        from PySide6.QtCore import QTimer

        elapsed_text = f"{elapsed:.1f}".replace(".", ",")
        symbol = "✓" if ok else "⚠"
        self.session_result_label.setText(
            f"{symbol} Unidades verificadas em {elapsed_text} s"
        )
        self.session_result_label.show()
        QTimer.singleShot(0, self.ajustar_altura_ao_conteudo)
        QTimer.singleShot(7000, self.clear_session_result)
        self.mount_worker = None

    def _start_mount_volumes(self):
        from core.morning_routine import MountVolumesWorker

        if getattr(self, "mount_worker", None):
            return

        self.session_result_label.setText("▸ Montando unidades…")
        self.session_result_label.show()
        self.ajustar_altura_ao_conteudo()

        self.mount_worker = MountVolumesWorker(self)
        self.mount_worker.completed.connect(self._finish_mount_volumes)
        self.mount_worker.start()

    def execute_command(self, code):
        code = code.upper()

        if code == "MR":
            self._start_morning_routine()
            return

        if code == "MU":
            self._start_mount_volumes()
            return

        if code == "ANY":
            self._clear_input_silently()
            self._open_anydesk_menu()
            return

        if code == "RES":
            from PySide6.QtCore import QTimer

            folders = get_recent_folders(limit=10)

            self._clear_input_silently()
            self.clear_suggestions()

            if folders:
                self.suggestions.set_items(folders, limit=10)
                self.input.setFocus()
                QTimer.singleShot(0, self.ajustar_altura_ao_conteudo)
                QTimer.singleShot(30, self.ajustar_altura_ao_conteudo)
            else:
                self.session_result_label.setText(
                    "⚠ O Finder não devolveu nenhuma pasta recente"
                )
                self.session_result_label.show()
                QTimer.singleShot(0, self.ajustar_altura_ao_conteudo)
                QTimer.singleShot(6000, self.clear_session_result)

            return

        # RE continua disponível como atalho oculto para reiniciar o último app.
        if code == "RE":
            from PySide6.QtCore import QTimer

            app = self.last_real_app
            app_name = app.get("name", "aplicativo") if isinstance(app, dict) else app

            if not app:
                self.session_result_label.setText("⚠ Nenhum aplicativo anterior encontrado")
                self.session_result_label.show()
                QTimer.singleShot(0, self.ajustar_altura_ao_conteudo)
                QTimer.singleShot(5000, self.clear_session_result)
                return

            ok = restart_app(app)
            symbol = "✓" if ok else "⚠"
            message = (
                f"{symbol} {app_name} reiniciado"
                if ok
                else f"{symbol} Não foi possível reiniciar {app_name}"
            )
            self.session_result_label.setText(message)
            self.session_result_label.show()
            QTimer.singleShot(0, self.ajustar_altura_ao_conteudo)
            QTimer.singleShot(6000, self.clear_session_result)
            return

        if code == "MON":
            from ui.montagem_dialog import MontagemDialog

            dialog = MontagemDialog(self)
            dialog.exec()
            self.input.setFocus()
            return

        if code == "IMP":
            from ui.imposition_dialog import ImpositionDialog

            dialog = ImpositionDialog(self)
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

        if getattr(self, "current_update", None):
            if self.execute_selected_suggestion():
                return
            self.install_pending_update()
            return

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

    def install_pending_update(self):
        package = getattr(self, "current_update", None)
        if package is None:
            return

        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication
        from core.update_manager import UpdateError, install_update

        self._clear_input_silently()
        self.clear_suggestions()
        progress_lines = []

        def show_progress(message):
            progress_lines.append(message)
            # Mantém a tela compacta durante pacotes maiores.
            visible = progress_lines[-9:]
            self.session_result_label.setText("\n".join(visible))
            self.session_result_label.show()
            self.ajustar_altura_ao_conteudo()
            QApplication.processEvents()

        try:
            installed = install_update(package, progress=show_progress)
        except UpdateError as error:
            self.session_result_label.setText(
                f"⚠ Atualização cancelada\n{error}"
            )
            self.session_result_label.show()
            self.current_update = None
            QTimer.singleShot(0, self.ajustar_altura_ao_conteudo)
            QTimer.singleShot(10000, self.clear_session_result)
            self.input.setFocus()
            return

        self.current_update = None
        self.active_file_label.clear()
        self.active_file_label.hide()
        self.session_result_label.setText(
            f"✓ Atualização concluída\n"
            f"{installed} arquivos atualizados\n\n"
            f"Reiniciando..."
        )
        self.session_result_label.show()
        self.ajustar_altura_ao_conteudo()
        QApplication.processEvents()

        if package.restart:
            QTimer.singleShot(900, self.restart_app)
        else:
            QTimer.singleShot(8000, self.clear_session_result)

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

            self._fix_commands_container_height()
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

        self._fix_commands_container_height()

    def _fix_commands_container_height(self):
        """Reserva a altura real de todas as linhas de comandos.

        O ``sizeHint`` do QGridLayout pode ser calculado cedo demais, antes de
        as fontes e os widgets terminarem o primeiro passe de layout. Isso
        deixava a última linha parcialmente fora do container e o divisor
        acabava atravessando o comando MP. Fazemos dois passes e usamos a maior
        medida disponível, com uma pequena folga inferior.
        """
        if not hasattr(self, "commands_container"):
            return

        self.commands_grid.invalidate()
        self.commands_grid.activate()

        hint_height = self.commands_grid.sizeHint().height()
        minimum_height = self.commands_grid.minimumSize().height()
        height = max(hint_height, minimum_height) + 8

        if height > 8:
            self.commands_container.setMinimumHeight(height)
            self.commands_container.setMaximumHeight(height)

        # No macOS, o primeiro sizeHint ainda pode mudar após o widget ser
        # mostrado. Um segundo passe corrige a medida sem criar um loop.
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, self._finalize_commands_container_height)

    def _finalize_commands_container_height(self):
        if not hasattr(self, "commands_container"):
            return

        self.commands_grid.invalidate()
        self.commands_grid.activate()

        height = max(
            self.commands_grid.sizeHint().height(),
            self.commands_grid.minimumSize().height(),
        ) + 8

        if height > 8:
            self.commands_container.setMinimumHeight(height)
            self.commands_container.setMaximumHeight(height)

        if getattr(self, "current_pdf", None):
            self.ajustar_altura_ao_conteudo()
