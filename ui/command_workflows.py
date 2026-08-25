class CommandWorkflowMixin:
    """Fluxos assíncronos acionados pelo controlador de comandos."""

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

    def _open_tools_dialog(self, target_tab):
        """Abre a ferramenta e recria a janela caso o Qt já a tenha destruído."""
        from shiboken6 import isValid
        from ui.tools_dialog import ToolsDialog

        dialog = getattr(self, "tools_dialog", None)
        if dialog is None or not isValid(dialog):
            dialog = ToolsDialog(self, initial_tab=target_tab)
            self.tools_dialog = dialog
        dialog.open_tab(target_tab)
        return dialog

