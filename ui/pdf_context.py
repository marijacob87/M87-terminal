import os

from PySide6.QtCore import QTimer

from ui.constants import PDF_ACTIONS
from ui.rename_pdf_dialog import RenamePdfDialog


class PdfContextMixin:
    def ajustar_altura_ao_conteudo(self):
        central = self.centralWidget()

        if central is None:
            return

        layout = central.layout()

        if layout is not None:
            layout.activate()

        required_height = central.sizeHint().height()
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

    def clear_context(self):
        self.current_pdf = None
        self.current_pdf_info = None
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

        if os.path.isfile(path) and path.lower().endswith(".pdf"):
            self.handle_pdf_drop(path)

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
        self.input.setFocus()
        QTimer.singleShot(0, self.ajustar_altura_ao_conteudo)

    def execute_pdf_action(self, action):
        if not self.current_pdf:
            return

        action_value = action.get("value")

        if action_value == "renomear":
            self.renomear_pdf_para_grafica()
            return

        if action_value == "info":
            self.open_pdf_info()
        elif action_value == "curvas":
            print(f"CURVAS PDF: {self.current_pdf}")
        elif action_value == "reduzir":
            print(f"REDUZIR PDF: {self.current_pdf}")

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
