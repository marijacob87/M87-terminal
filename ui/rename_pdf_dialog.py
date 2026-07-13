from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class RenamePdfDialog(QDialog):
    def __init__(self, file_name: str, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Renomear para gráfica")
        self.setModal(True)
        self.setFixedWidth(380)
        self.setWindowFlags(Qt.Dialog)

        self.build_ui(file_name)
        self.apply_style()

    def build_ui(self, file_name: str):
        container = QVBoxLayout(self)
        container.setContentsMargins(0, 0, 0, 0)
        container.setSpacing(0)

        wrapper = QWidget()
        wrapper.setObjectName("renamePanel")

        panel = QVBoxLayout(wrapper)
        panel.setContentsMargins(20, 18, 20, 18)
        panel.setSpacing(14)

        title = QLabel("RENOMEAR PARA GRÁFICA")
        title.setObjectName("renameTitle")

        file_label = QLabel(file_name)
        file_label.setObjectName("renameFile")
        file_label.setWordWrap(True)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(12)
        form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        form.setFormAlignment(Qt.AlignTop)

        self.units_input = QSpinBox()
        self.units_input.setRange(1, 9_999_999)
        self.units_input.setValue(1)

        self.per_sheet_input = QSpinBox()
        self.per_sheet_input.setRange(1, 9_999_999)
        self.per_sheet_input.setValue(1)

        self.paper_input = QLineEdit("Mat 350g")

        form.addRow("Quantidade total", self.units_input)
        form.addRow("Unidades por plano", self.per_sheet_input)
        form.addRow("Papel / material", self.paper_input)

        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 4, 0, 0)
        buttons.setSpacing(10)

        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.setObjectName("cancelButton")
        self.cancel_button.clicked.connect(self.reject)
        self.cancel_button.setAutoDefault(False)

        self.rename_button = QPushButton("Renomear")
        self.rename_button.setObjectName("renameButton")
        self.rename_button.clicked.connect(self.accept)

        # Importante:
        # impede o botão de capturar Enter antes dos campos.
        self.rename_button.setDefault(False)
        self.rename_button.setAutoDefault(False)

        buttons.addStretch()
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.rename_button)

        panel.addWidget(title)
        panel.addWidget(file_label)
        panel.addLayout(form)
        panel.addLayout(buttons)

        container.addWidget(wrapper)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            widget_atual = self.focusWidget()

            if (
                widget_atual == self.units_input
                or widget_atual == self.units_input.lineEdit()
            ):
                self.per_sheet_input.setFocus()
                self.per_sheet_input.selectAll()
                event.accept()
                return

            if (
                widget_atual == self.per_sheet_input
                or widget_atual == self.per_sheet_input.lineEdit()
            ):
                self.paper_input.setFocus()
                self.paper_input.selectAll()
                event.accept()
                return

            if widget_atual == self.paper_input:
                self.accept()
                event.accept()
                return

        if event.key() == Qt.Key_Escape:
            self.reject()
            event.accept()
            return

        super().keyPressEvent(event)

    def apply_style(self):
        self.setStyleSheet(
            """
            QDialog {
                background-color: rgb(8, 13, 22);
            }

            QWidget#renamePanel {
                background-color: rgb(8, 13, 22);
                border: 1px solid rgba(208, 147, 29, 0.65);
                border-radius: 10px;
            }

            QLabel#renameTitle {
                color: rgba(244, 189, 4, 1);
                font-family: "Menlo";
                font-size: 14px;
                font-weight: 700;
            }

            QLabel#renameFile {
                color: rgba(255, 255, 255, 0.72);
                font-family: "Menlo";
                font-size: 11px;
                padding-bottom: 4px;
            }

            QLabel {
                color: rgba(255, 255, 255, 0.72);
                font-family: "Menlo";
                font-size: 11px;
            }

            QLineEdit,
            QSpinBox {
                min-height: 30px;
                padding: 0 8px;
                color: rgba(255, 255, 255, 0.92);
                background-color: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(208, 147, 29, 0.55);
                border-radius: 6px;
                font-family: "Menlo";
                font-size: 12px;
            }

            QLineEdit:focus,
            QSpinBox:focus {
                border: 1px solid rgba(244, 189, 4, 1);
            }

            QPushButton {
                min-width: 92px;
                min-height: 30px;
                padding: 0 12px;
                border-radius: 6px;
                font-family: "Menlo";
                font-size: 11px;
                font-weight: 700;
            }

            QPushButton#cancelButton {
                color: rgba(255, 255, 255, 0.72);
                background-color: rgba(255, 255, 255, 0.06);
                border: 1px solid rgba(255, 255, 255, 0.15);
            }

            QPushButton#renameButton {
                color: rgb(8, 13, 22);
                background-color: rgb(244, 189, 4);
                border: 1px solid rgb(244, 189, 4);
            }

            QPushButton#cancelButton:hover {
                background-color: rgba(255, 255, 255, 0.10);
            }

            QPushButton#renameButton:hover {
                background-color: rgb(255, 204, 51);
                border-color: rgb(255, 204, 51);
            }
            """
        )

    def showEvent(self, event):
        super().showEvent(event)

        if self.parent() is not None and self.parent().screen() is not None:
            screen = self.parent().screen()
        else:
            screen = QApplication.primaryScreen()

        if screen is not None:
            screen_geometry = screen.availableGeometry()
            dialog_geometry = self.frameGeometry()
            dialog_geometry.moveCenter(screen_geometry.center())
            self.move(dialog_geometry.topLeft())

        self.units_input.setFocus()
        self.units_input.selectAll()

    def values(self) -> tuple[int, int, str]:
        return (
            self.units_input.value(),
            self.per_sheet_input.value(),
            self.paper_input.text().strip() or "Mat 350g",
        )