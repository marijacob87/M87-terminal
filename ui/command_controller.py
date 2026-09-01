import os
from datetime import date

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
from core.restart import restart_m87_process
from core.config import BREAKPOINT_WIDTH
from core.executor import execute
from core.system_actions import get_last_kill_report
from core.input_handler import handle_input_text
from core.planner import PlannerStore, parse_terminal_task, week_start
from core.suggestion_engine import get_suggestions
from ui.command_workflows import CommandWorkflowMixin
from ui.constants import PDF_ACTIONS
from PySide6.QtWidgets import QApplication


class CommandControllerMixin(CommandWorkflowMixin):
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

        if parse_terminal_task(text):
            self.clear_suggestions()
            return

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

        # Ao desaparecerem as sugestões, a janela deve recalcular também para
        # baixo. Sem permitir a redução, ela permanecia presa na maior altura
        # atingida durante a digitação.
        QTimer.singleShot(
            0,
            lambda: self.ajustar_altura_ao_conteudo(permitir_reduzir=True),
        )
        QTimer.singleShot(
            30,
            lambda: self.ajustar_altura_ao_conteudo(permitir_reduzir=True),
        )

    def move_suggestion_up(self):
        if self.suggestions.items:
            self._clear_command_navigation()
            self.suggestions.move_up()
            return
        self._move_command_navigation(-1)

    def move_suggestion_down(self):
        if self.suggestions.items:
            self._clear_command_navigation()
            self.suggestions.move_down()
            return
        self._move_command_navigation(1)

    def _clear_command_navigation(self):
        index = getattr(self, "command_navigation_index", -1)
        if 0 <= index < len(self.command_widgets):
            self.command_widgets[index].set_normal_style()
        self.command_navigation_index = -1

    def _move_command_navigation(self, direction):
        """Seleciona os comandos visíveis na grade acima do prompt."""
        if (
            self.input.text().strip()
            or self.current_pdf
            or getattr(self, "anydesk_menu_active", False)
            or not self.command_widgets
        ):
            return

        if self.suggestions.items:
            self.clear_suggestions()

        previous = getattr(self, "command_navigation_index", -1)
        if 0 <= previous < len(self.command_widgets):
            self.command_widgets[previous].set_normal_style()

        if previous < 0:
            index = 0 if direction > 0 else len(self.command_widgets) - 1
        else:
            index = (previous + direction) % len(self.command_widgets)

        self.command_navigation_index = index
        self.command_widgets[index].set_keyboard_selected_style()

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
                    selected.get("id", ""),
                    confirm_console=selected.get("console", False),
                )
                return True

            if selected_type == "anydesk_app":
                open_anydesk_app()
                return True

            if selected_type == "recent_folder":
                open_path(selected.get("path", ""))
                return True

            if selected_type == "whatsapp_contact":
                from datetime import date
                from core.whatsapp_download import WhatsAppRequest

                contact = selected.get("name", "")
                if contact:
                    requested_day = getattr(
                        self,
                        "whatsapp_request_day",
                        date.today(),
                    )
                    self.start_whatsapp_download(
                        WhatsAppRequest(contact=contact, day=requested_day)
                    )
                return True

            self.execute_command(
                selected.get("code", "")
            )

            return True

        open_path(selected)
        return True

    def execute_command(self, code):
        code = code.upper()

        if code == "NOTAS":
            self._clear_input_silently()
            self.clear_suggestions()
            self.open_settings_section("notes")
            return

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

            # O histórico já é sincronizado em segundo plano. Consultar o
            # Finder novamente aqui bloquearia o Enter por até 1,5 segundo.
            folders = get_recent_folders(limit=10, refresh=False)

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

        if code == "CC":
            from ui.checklist_dialog import ChecklistDialog

            dialog = getattr(self, "checklist_dialog", None)
            if dialog is None:
                dialog = ChecklistDialog(self)
                self.checklist_dialog = dialog
            dialog.show()
            dialog.raise_()
            dialog.activateWindow()
            self._clear_input_silently()
            self.clear_suggestions()
            self.input.setFocus()
            return

        if code == "TODO":
            from core.planner_web import open_planner_web

            if open_planner_web():
                self._clear_input_silently()
                self.clear_suggestions()
                return

            from ui.planner_dialog import PlannerDialog

            dialog = getattr(self, "planner_dialog", None)
            if dialog is None:
                dialog = PlannerDialog(self)
                self.planner_dialog = dialog
            dialog.show()
            dialog.raise_()
            dialog.activateWindow()
            self._clear_input_silently()
            self.clear_suggestions()
            return

        # RE permanece como alias oculto do comando visível REL.
        if code in {"REL", "RE"}:
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

        if code in {"PDF", "IMP", "ORG", "GEO", "MON", "BAR"}:
            target_tab = "RES" if code == "PDF" else code
            self._open_tools_dialog(target_tab)
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

        # Comando de controle: precisa ser tratado antes de qualquer sugestão
        # (inclusive a busca de aplicativos iniciada por "#").
        if text == "##":
            self._clear_command_navigation()
            self._clear_input_silently()
            self.clear_suggestions()
            self.restart_app()
            return

        if upper_text == "NOTAS":
            self._clear_command_navigation()
            self.execute_command("NOTAS")
            return

        terminal_task = parse_terminal_task(text)
        if terminal_task:
            tag, task_text = terminal_task
            task_date = date.today()
            day_name = PlannerStore().add_task_for_date(
                task_date,
                tag,
                task_text,
            )
            self._clear_command_navigation()
            self._clear_input_silently()
            self.clear_suggestions()

            if day_name is None:
                message = "⚠ O planner recebe tarefas de segunda a sexta"
            else:
                dialog = getattr(self, "planner_dialog", None)
                if dialog and dialog.current_start == week_start(task_date):
                    dialog._flush_notes_save()
                    dialog.store = PlannerStore()
                    dialog._load_week()
                message = f"✓ Tarefa adicionada em {day_name}"

            self.session_result_label.setText(message)
            self.session_result_label.show()
            from PySide6.QtCore import QTimer
            QTimer.singleShot(3500, self.clear_session_result)
            return

        command_index = getattr(self, "command_navigation_index", -1)
        if (
            not text
            and command_index >= 0
            and not self.current_pdf
        ):
            code = self.command_widgets[command_index].code_text
            self._clear_command_navigation()
            self.execute_command(code)
            return

        if text:
            self._clear_command_navigation()

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

        if upper_text.startswith("MU "):
            self._clear_input_silently()
            self.clear_suggestions()
            self._start_mount_volumes(text[3:].strip())
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
        dialog = getattr(self, "planner_dialog", None)
        if dialog is not None:
            dialog._save_window_geometry()
        self.save_current_state()
        self._force_close = True
        restart_m87_process()
        app = QApplication.instance()
        app.closeAllWindows()
        app.processEvents()
        os._exit(0)

    def rebuild_command_grid(self):
        columns = (
            1
            if self.width() < BREAKPOINT_WIDTH
            else 2
        )

        if columns == self.current_columns:
            # A largura pode permanecer na mesma faixa, mas o Qt pode recalcular
            # as métricas da fonte ou restaurar widgets que estavam ocultos.
            # Revalidar a altura evita que o divisor atravesse a última linha.
            self._fix_commands_container_height()
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

    def _commands_column_height(self, sections):
        """Calcula a altura real de uma coluna de comandos.

        O cálculo usa os próprios widgets, em vez de depender apenas do
        ``sizeHint`` do QGridLayout. No macOS, o layout pode devolver uma altura
        provisória durante a restauração da janela, cortando exatamente a
        última linha de comandos.
        """
        widgets = []

        for section in sections:
            rows = self.command_sections.get(section, [])
            if not rows:
                continue
            widgets.append(self.section_labels[section])
            widgets.extend(rows)

        if not widgets:
            return 0

        spacing = max(0, self.commands_grid.verticalSpacing())
        heights = [
            max(widget.sizeHint().height(), widget.minimumSizeHint().height())
            for widget in widgets
        ]
        return sum(heights) + spacing * max(0, len(heights) - 1)

    def _required_commands_height(self):
        margins = self.commands_grid.contentsMargins()

        if self.current_columns == 1:
            content_height = self._commands_column_height(
                ["Sistema", "Abrir", "Ferramentas"]
            )
        else:
            left_height = self._commands_column_height(["Sistema"])
            right_height = self._commands_column_height(
                ["Abrir", "Ferramentas"]
            )
            content_height = max(left_height, right_height)

        layout_height = max(
            self.commands_grid.sizeHint().height(),
            self.commands_grid.minimumSize().height(),
        )

        # As linhas têm altura fixa. Uma folga mínima de 2 px basta para
        # absorver arredondamentos da tela Retina sem criar um vão visual.
        return max(content_height, layout_height) + margins.top() + margins.bottom() + 2

    def _fix_commands_container_height(self):
        """Mantém todas as linhas de comandos integralmente visíveis."""
        if not hasattr(self, "commands_container"):
            return

        self.commands_grid.invalidate()
        self.commands_grid.activate()

        height = self._required_commands_height()
        if height > 14:
            self.commands_container.setFixedHeight(height)

        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, self._finalize_commands_container_height)

    def _finalize_commands_container_height(self):
        if not hasattr(self, "commands_container"):
            return

        self.commands_grid.invalidate()
        self.commands_grid.activate()

        height = self._required_commands_height()
        if height > 14:
            self.commands_container.setFixedHeight(height)

        # A altura-base também precisa comportar título, status, comandos,
        # prompt e divisor. Assim qualquer mensagem nova nasce abaixo dos
        # comandos, e a janela cresce apenas para baixo.
        self.ajustar_altura_ao_conteudo(
            atualizar_altura_normal=True,
            permitir_reduzir=True,
        )
