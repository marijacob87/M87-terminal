import os

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from ui.constants import PDF_ACTIONS
from ui.rename_pdf_dialog import RenamePdfDialog


class PdfContextMixin:
    def ajustar_altura_ao_conteudo(self):
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

        # A altura do central já inclui quase tudo, mas em alguns ciclos do Qt
        # o último widget ainda não entrou no sizeHint. Somamos uma margem
        # pequena e estável para impedir que o divisor ou as sugestões encostem.
        required_height = max(
            central.sizeHint().height(),
            central.minimumSizeHint().height(),
            layout_height + margins.top() + margins.bottom(),
        ) + 12

        new_height = max(self.normal_height, required_height)
        screen = self.screen()

        if screen is not None:
            available = screen.availableGeometry()
            max_height = available.bottom() - self.y() - 12
            new_height = min(new_height, max_height)

        self.auto_resizing = True
        self.resize(self.width(), max(self.minimumHeight(), new_height))
        self.auto_resizing = False

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

    def definir_modo_atualizacao(self, ativo):
        """Reserva a área do Terminal para a atualização sem sobreposições."""
        self.commands_container.setVisible(not ativo)
        self.divider_2.setVisible(not ativo)

    def clear_context(self):
        self.current_pdf = None
        self.current_pdf_info = None
        self.current_update = None
        self.definir_modo_atualizacao(False)
        self.active_file_label.clear()
        self.active_file_label.hide()
        self.clear_suggestions()

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
            and url.toLocalFile().lower().endswith((".pdf", ".zip"))
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

            if path and path.lower().endswith((".pdf", ".zip")):
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
        elif path.lower().endswith(".zip"):
            self.handle_update_drop(path)

    def handle_update_drop(self, path):
        from core.update_manager import UpdateError, inspect_update

        self.current_pdf = None
        self.current_pdf_info = None
        self.current_update = None
        self.clear_suggestions()
        self.definir_modo_atualizacao(True)

        try:
            package = inspect_update(path)
            self.current_update = package

            quantidade = package.file_count
            arquivo_texto = "arquivo" if quantidade == 1 else "arquivos"
            lines = [
                "M87 • Atualização detectada",
                "",
                os.path.basename(path),
            ]
            if package.version:
                lines.extend(["", f"Versão {package.version}"])
            lines.extend(["", f"✓ {quantidade} {arquivo_texto} para atualizar"])

            self.active_file_label.setText("\n".join(lines))
            self.active_file_label.show()
            self.suggestions.set_items([
                {
                    "type": "update_action",
                    "label": "EXECUTAR ATUALIZAÇÃO",
                    "value": "install_update",
                }
            ])
        except UpdateError as error:
            self.definir_modo_atualizacao(False)
            self.active_file_label.setText(
                f"Pacote de atualização inválido\n{error}"
            )
            self.active_file_label.show()
            QTimer.singleShot(8000, self.clear_context)

        self._clear_input_silently()
        self.activate_after_file_drop()
        QTimer.singleShot(0, self.ajustar_altura_ao_conteudo)

    def handle_pdf_drop(self, path):
        from core.pdf_info import analisar_pdf, resumo_pdf

        self.current_pdf = path
        self.current_pdf_info = None

        try:
            self.current_pdf_info = analisar_pdf(path)
            text = resumo_pdf(self.current_pdf_info)
        except Exception as error:
            file_name = os.path.basename(path)
            text = f"{file_name}\nNão consegui ler as informações."
            print(f"ERRO AO LER PDF: {error}")

        self.active_file_label.setText(text)
        self.active_file_label.show()

        self.input.blockSignals(True)
        self.input.clear()
        self.input.blockSignals(False)

        self.suggestions.set_items(PDF_ACTIONS)
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
        """Abre o IMP com o PDF ativo já carregado."""
        if not self.current_pdf:
            return

        try:
            from ui.imposition_dialog import ImpositionDialog

            dialog = ImpositionDialog(self)
            dialog.load_pdf(self.current_pdf)
            dialog.exec()
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
            parent=self,
        )

        if not dialog.exec():
            self.input.setFocus()
            return

        units, per_sheet, paper = dialog.values()

        try:
            from core.pdf_info import analisar_pdf, resumo_pdf
            from core.pdf_rename import renomear_pdf

            new_path = renomear_pdf(
                arquivo=self.current_pdf,
                unidades=units,
                por_plano=per_sheet,
                papel=paper,
            )

            self.current_pdf = str(new_path)
            self.current_pdf_info = analisar_pdf(self.current_pdf)
            self.active_file_label.setText(
                resumo_pdf(self.current_pdf_info)
            )
        except Exception as error:
            print(f"ERRO AO RENOMEAR PDF: {error}")

        self.suggestions.set_items(PDF_ACTIONS)
        self.input.setFocus()
        QTimer.singleShot(0, self.ajustar_altura_ao_conteudo)
