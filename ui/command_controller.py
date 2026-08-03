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
        self.input.setFocus()

    def _finish_mount_volumes(self, ok, elapsed):
        from PySide6.QtCore import QTimer

        elapsed_text = f"{elapsed:.1f}".replace(".", ",")
        symbol = "✓" if ok else "⚠"
        label = getattr(self, "_mount_label", "Unidades")
        self.session_result_label.setText(
            f"{symbol} Verificação concluída: {label} ({elapsed_text} s)"
        )
        self.session_result_label.show()
        QTimer.singleShot(0, self.ajustar_altura_ao_conteudo)
        QTimer.singleShot(7000, self.clear_session_result)
        self.mount_worker = None
        self.update_status()

    def _start_mount_volumes(self, target=None):
        from core.morning_routine import MountVolumesWorker
        from core.network_volumes import select_network_volumes

        if getattr(self, "mount_worker", None):
            return

        volumes = select_network_volumes(target)
        if not volumes:
            from PySide6.QtCore import QTimer

            self.session_result_label.setText(
                "⚠ Unidade desconhecida. Use MU MIM, MU PFI ou MU NAS."
            )
            self.session_result_label.show()
            QTimer.singleShot(0, self.ajustar_altura_ao_conteudo)
            QTimer.singleShot(7000, self.clear_session_result)
            return

        label = "unidades" if len(volumes) > 1 else volumes[0]["label"]
        self._mount_label = "Unidades" if len(volumes) > 1 else label
        self.session_result_label.setText(f"▸ Montando {label}…")
        self.session_result_label.show()
        self.ajustar_altura_ao_conteudo()

        self.mount_worker = MountVolumesWorker(target, self)
        self.mount_worker.completed.connect(self._finish_mount_volumes)
        self.mount_worker.start()

    def start_whatsapp_download(self, request):
        from PySide6.QtCore import QTimer
        from core.whatsapp_worker import WhatsAppDownloadWorker

        worker = getattr(self, "whatsapp_worker", None)
        if worker is not None and worker.isRunning():
            self.session_result_label.setText("⚠ Já existe um download do WhatsApp em curso")
            self.session_result_label.show()
            QTimer.singleShot(0, self.ajustar_altura_ao_conteudo)
            return

        def show_progress(message):
            self.session_result_label.setText(f"▸ {message}")
            self.session_result_label.show()
            self.ajustar_altura_ao_conteudo()

        def completed(count, directory):
            label = "arquivo" if count == 1 else "arquivos"
            self.session_result_label.setText(
                f"✓ WhatsApp • {count}/{count} {label} "
                f"recebidos e verificados\n{directory}"
            )
            self.session_result_label.show()
            self.whatsapp_worker = None
            QTimer.singleShot(0, self.ajustar_altura_ao_conteudo)
            QTimer.singleShot(12000, self.clear_session_result)

        def failed(message):
            self.session_result_label.setText(f"⚠ WhatsApp\n{message}")
            self.session_result_label.show()
            self.whatsapp_worker = None
            QTimer.singleShot(0, self.ajustar_altura_ao_conteudo)
            QTimer.singleShot(12000, self.clear_session_result)

        self.whatsapp_worker = WhatsAppDownloadWorker(request, self)
        self.whatsapp_worker.progress.connect(show_progress)
        self.whatsapp_worker.completed.connect(completed)
        self.whatsapp_worker.failed.connect(failed)
        show_progress("A preparar o WhatsApp Web…")
        self.whatsapp_worker.start()

    def start_whatsapp_contacts(self, requested_day=None):
        from datetime import date
        from PySide6.QtCore import QTimer
        from core.whatsapp_worker import WhatsAppChatsWorker

        self.whatsapp_request_day = requested_day or date.today()
        worker = getattr(self, "whatsapp_chats_worker", None)
        if worker is not None and worker.isRunning():
            return

        def show_progress(message):
            self.session_result_label.setText(f"▸ {message}")
            self.session_result_label.show()
            self.ajustar_altura_ao_conteudo()

        def completed(chats):
            items = [
                {"type": "whatsapp_contact", "name": name}
                for name in chats
            ]
            self.whatsapp_chats_worker = None
            self.session_result_label.clear()
            self.session_result_label.hide()
            self.suggestions.set_items(items, limit=20)
            self.input.setFocus()
            QTimer.singleShot(0, self.ajustar_altura_ao_conteudo)

        def failed(message):
            self.whatsapp_chats_worker = None
            self.session_result_label.setText(f"⚠ WhatsApp\n{message}")
            self.session_result_label.show()
            QTimer.singleShot(0, self.ajustar_altura_ao_conteudo)
            QTimer.singleShot(12000, self.clear_session_result)

        self.whatsapp_chats_worker = WhatsAppChatsWorker(self)
        self.whatsapp_chats_worker.progress.connect(show_progress)
        self.whatsapp_chats_worker.completed.connect(completed)
        self.whatsapp_chats_worker.failed.connect(failed)
        show_progress("A preparar as conversas do WhatsApp…")
        self.whatsapp_chats_worker.start()

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

        if code in {"IMP", "ORG", "GEO", "MON", "BAR"}:
            from ui.tools_dialog import ToolsDialog

            dialog = getattr(self, "tools_dialog", None)
            if dialog is None:
                dialog = ToolsDialog(self, initial_tab=code)
                self.tools_dialog = dialog
            else:
                dialog.open_tab(code)
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
