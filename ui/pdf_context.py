import os
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from ui.constants import PDF_ACTIONS
from ui.rename_pdf_dialog import RenamePdfDialog


class PdfContextMixin:
    def ajustar_altura_ao_conteudo(
        self,
        atualizar_altura_normal=False,
        permitir_reduzir=False,
    ):
        """Ajusta a janela ao conteúdo variável sem comprimir o topo.

        Serve para sugestões, informações de PDF, resultados e rotinas. O
        cálculo anterior só era disparado para PDF; por isso as sugestões
        ocupavam espaço sem que a janela crescesse e acabavam sobrepostas aos
        comandos.
        """
        central = self.centralWidget()

        if central is None:
            return

        layout = central.layout()

        if layout is None:
            return

        layout.invalidate()
        layout.activate()
        central.updateGeometry()

        margins = layout.contentsMargins()
        layout_height = max(
            layout.sizeHint().height(),
            layout.minimumSize().height(),
        )

        # Folga mínima apenas para borda e arredondamento da janela.
        # O redimensionador não participa mais do layout, portanto não cria
        # espaço vazio sob a linha de comando.
        required_height = max(
            central.sizeHint().height(),
            central.minimumSizeHint().height(),
            layout_height + margins.top() + margins.bottom(),
        ) + 4

        if permitir_reduzir:
            new_height = required_height
        else:
            new_height = max(self.normal_height, required_height)
        screen = self.screen()

        if screen is not None:
            available = screen.availableGeometry()
            max_height = available.bottom() - self.y() - 12
            new_height = min(new_height, max_height)

        target_height = max(self.minimumHeight(), new_height)

        self.auto_resizing = True
        self.resize(self.width(), target_height)
        self.auto_resizing = False

        if atualizar_altura_normal:
            self.normal_height = target_height

    def restaurar_altura_normal(self):
        self.auto_resizing = True
        self.resize(self.width(), self.normal_height)
        self.auto_resizing = False

    def get_pdf_suggestions(self, text):
        text = text.strip().lower()

        if not text:
            return PDF_ACTIONS

        return [
            item
            for item in PDF_ACTIONS
            if text in item.get("code", "").lower()
            or text in item.get("value", "").lower()
        ]

    def clear_context(self):
        self.current_pdf = None
        self.current_pdf_info = None
        self.active_file_label.clear()
        self.active_file_label.hide()
        self.clear_suggestions()
        self.clear_calculator_result()
        self.reset_calculator_session()

        self.input.blockSignals(True)
        self.input.clear()
        self.input.blockSignals(False)
        self.input.setFocus()

        QTimer.singleShot(0, self.restaurar_altura_normal)

    def has_valid_drop_file(self, event):
        if not event.mimeData().hasUrls():
            return False

        return any(
            url.toLocalFile()
            and os.path.isfile(url.toLocalFile())
            and url.toLocalFile().lower().endswith(".pdf")
            for url in event.mimeData().urls()
        )

    def dragEnterEvent(self, event):
        if self.has_valid_drop_file(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if self.has_valid_drop_file(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        if not event.mimeData().hasUrls():
            event.ignore()
            return

        for url in event.mimeData().urls():
            path = url.toLocalFile()

            if path and path.lower().endswith(".pdf"):
                self.handle_file_drop(path)
                event.acceptProposedAction()
                return

        event.ignore()

    def handle_file_drop(self, path):
        path = os.path.abspath(path)

        if not os.path.isfile(path):
            return

        if path.lower().endswith(".pdf"):
            self.handle_pdf_drop(path)

    def handle_pdf_drop(self, path):
        self.current_pdf = path
        self.current_pdf_info = None

        self._clear_input_silently()
        self.clear_suggestions()
        self.active_file_label.clear()
        self.active_file_label.hide()

        try:
            dialog = self._open_tools_dialog("RES")
            dialog.open_pdfs(
                [path],
                tab="RES",
            )
            self.current_pdf = None
            self.current_pdf_info = None
            QTimer.singleShot(0, self.restaurar_altura_normal)
        except Exception as error:
            print(f"ERRO AO ABRIR RESUMO DO PDF: {error}")
            self.active_file_label.setText(
                "Não foi possível abrir o PDF no RESUMO."
            )
            self.active_file_label.show()
            self.activate_after_file_drop()
            QTimer.singleShot(0, self.ajustar_altura_ao_conteudo)


    def activate_after_file_drop(self):
        """Traz o M87 para frente e deixa o cursor pronto após o drop.

        O macOS costuma devolver o foco ao aplicativo de origem no final do
        arraste. Repetimos a ativação por alguns milissegundos para vencer essa
        devolução de foco sem exigir um clique manual.
        """
        def activate():
            self.show()
            self.raise_()
            self.activateWindow()
            QApplication.setActiveWindow(self)
            self.input.setFocus()

        activate()
        QTimer.singleShot(0, activate)
        QTimer.singleShot(120, activate)
        QTimer.singleShot(280, activate)

    def execute_pdf_action(self, action):
        if not self.current_pdf:
            return

        action_value = action.get("value")

        if action_value == "imposicao":
            self.open_imposition_with_pdf()
            return

        if action_value == "renomear":
            self.renomear_pdf_para_grafica()
            return

        if action_value == "info":
            self.open_pdf_info()
        elif action_value == "curvas":
            from core.pdf_curves import converter_pdf_em_curvas

            started = converter_pdf_em_curvas(self.current_pdf, self)

            if started:
                self.session_result_label.setText(
                    "CURVAS em processamento…\n"
                    "O original será preservado."
                )
                self.session_result_label.show()
                QTimer.singleShot(0, self.ajustar_altura_ao_conteudo)
                QTimer.singleShot(10000, self.clear_session_result)
            else:
                self.session_result_label.setText(
                    "Não foi possível iniciar CURVAS."
                )
                self.session_result_label.show()
                QTimer.singleShot(0, self.ajustar_altura_ao_conteudo)
                QTimer.singleShot(8000, self.clear_session_result)
        elif action_value == "reduzir":
            print(f"REDUZIR PDF: {self.current_pdf}")

        self.suggestions.set_items(PDF_ACTIONS)
        self.input.setFocus()
        QTimer.singleShot(0, self.ajustar_altura_ao_conteudo)

    def open_imposition_with_pdf(self):
        """Abre a janela compartilhada na aba IMP com o PDF ativo."""
        if not self.current_pdf:
            return

        opened = False
        try:
            dialog = self._open_tools_dialog("IMP")
            dialog.open_pdfs([self.current_pdf], tab="IMP")
            opened = True
        except Exception as error:
            print(f"ERRO AO ABRIR IMP COM PDF: {error}")
            self.session_result_label.setText(
                "Não foi possível abrir o PDF no IMP."
            )
            self.session_result_label.show()
            QTimer.singleShot(0, self.ajustar_altura_ao_conteudo)
            QTimer.singleShot(6000, self.clear_session_result)
        finally:
            self.suggestions.set_items(PDF_ACTIONS)
            if not opened:
                self.input.setFocus()
            QTimer.singleShot(0, self.ajustar_altura_ao_conteudo)

    def open_pdf_info(self):
        try:
            from core.pdf_info import analisar_pdf
            from ui.pdf_info_dialog import PdfInfoDialog

            info = self.current_pdf_info

            if not info:
                info = analisar_pdf(self.current_pdf)
                self.current_pdf_info = info

            dialog = PdfInfoDialog(info, self)
            dialog.exec()
        except Exception as error:
            print(f"ERRO INFO PDF: {error}")

    def renomear_pdf_para_grafica(self):
        if not self.current_pdf:
            return

        dialog = RenamePdfDialog(
            file_name=os.path.basename(self.current_pdf),
            file_path=self.current_pdf,
            page_count=int((self.current_pdf_info or {}).get("paginas", 1)),
            parent=self,
        )

        if not dialog.exec():
            self.input.setFocus()
            return

        units, per_sheet, paper = dialog.values()

        try:
            from core.pdf_info import analisar_pdf
            from core.pdf_rename import renomear_pdf

            if dialog.is_already_named():
                new_path = Path(self.current_pdf)
            else:
                new_path = renomear_pdf(
                    arquivo=self.current_pdf,
                    unidades=units,
                    por_plano=per_sheet,
                    papel=paper,
                )

            self.current_pdf = str(new_path)
            self.current_pdf_info = analisar_pdf(self.current_pdf)
            self.active_file_label.setText(os.path.basename(self.current_pdf))
            entries = dialog.print_log_entries()
            if entries:
                from core.print_log import clean_record_name
                from ui.print_log_dialog import submit_print_log

                dialog.print_log_editor.set_single_name(
                    clean_record_name(new_path.name)
                )
                submit_print_log(self, dialog.print_log_editor)
        except Exception as error:
            print(f"ERRO AO RENOMEAR PDF: {error}")

        self.suggestions.set_items(PDF_ACTIONS)
        self.input.setFocus()
        QTimer.singleShot(0, self.ajustar_altura_ao_conteudo)
