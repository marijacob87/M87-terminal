from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QDialog,
    QCheckBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from core.print_log import PrintLogEntry, PrintLogError, send_entries


ENDPOINT_KEY = "print_log/apps_script_url"
ACCESS_KEY = "print_log/access_key"


class PrintLogEditor:
    def __init__(self, entries: list[PrintLogEntry], settings: QSettings):
        self.settings = settings
        self._model_applied = True
        self._model_back_rows = [entry.back > 0 for entry in entries]
        self.model_copy = QCheckBox("+1 plano para modelo")
        self.model_copy.setChecked(True)
        self.model_copy.toggled.connect(self._toggle_model_copy)
        self.table = QTableWidget(len(entries), 5)
        self.table.setHorizontalHeaderLabels(
            ["DIA", "OPERADOR", "NOME DO ARQUIVO / CLIENTE", "FRENTE", "VERSO"]
        )
        self.table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        for column in (0, 1, 3, 4):
            header.setSectionResizeMode(column, QHeaderView.ResizeToContents)
        self.table.setMinimumHeight(min(260, 70 + len(entries) * 34))

        for row, entry in enumerate(entries):
            self._set_spin(
                row,
                0,
                entry.day,
                1,
                31,
                Qt.FocusPolicy.ClickFocus,
            )
            operator = QTableWidgetItem(entry.operator)
            operator.setFlags(operator.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 1, operator)
            self.table.setItem(row, 2, QTableWidgetItem(entry.name))
            self._set_spin(row, 3, entry.front + 1, 0, 9_999_999)
            self._set_spin(
                row,
                4,
                entry.back + (1 if entry.back > 0 else 0),
                0,
                9_999_999,
            )

        self.endpoint = QLineEdit(str(settings.value(ENDPOINT_KEY, "")))
        self.endpoint.setPlaceholderText("https://script.google.com/macros/s/.../exec")
        self.access_key = QLineEdit(str(settings.value(ACCESS_KEY, "")))
        self.access_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.access_key.setPlaceholderText("Chave definida no Apps Script")

    def _set_spin(
        self,
        row: int,
        column: int,
        value: int,
        minimum: int,
        maximum: int,
        focus_policy=Qt.FocusPolicy.StrongFocus,
    ):
        spin = QSpinBox()
        spin.setRange(minimum, maximum)
        spin.setValue(value)
        spin.setFocusPolicy(focus_policy)
        self.table.setCellWidget(row, column, spin)

    def add_to(self, layout: QVBoxLayout):
        layout.addWidget(self.model_copy)
        layout.addWidget(self.table)
        config = QFormLayout()
        config.addRow("Endereço da integração", self.endpoint)
        config.addRow("Chave de acesso", self.access_key)
        layout.addLayout(config)

    def entries(self) -> list[PrintLogEntry]:
        result = []
        for row in range(self.table.rowCount()):
            name_item = self.table.item(row, 2)
            result.append(
                PrintLogEntry(
                    day=self.table.cellWidget(row, 0).value(),
                    operator="Mariane",
                    name=(name_item.text() if name_item else "").strip(),
                    front=self.table.cellWidget(row, 3).value(),
                    back=self.table.cellWidget(row, 4).value(),
                )
            )
        return result

    def set_single_name_and_counts(self, name: str, front: int, back: int):
        if self.table.rowCount() != 1:
            return
        self._model_back_rows[0] = back > 0
        self.set_single_name(name)
        self.table.cellWidget(0, 3).setValue(
            front + (1 if self._model_applied else 0)
        )
        self.table.cellWidget(0, 4).setValue(
            back + (1 if self._model_applied and back > 0 else 0)
        )

    def set_single_name(self, name: str):
        if self.table.rowCount() == 1:
            self.table.item(0, 2).setText(name)

    def _toggle_model_copy(self, checked: bool):
        if checked == self._model_applied:
            return
        delta = 1 if checked else -1
        for row in range(self.table.rowCount()):
            front = self.table.cellWidget(row, 3)
            back = self.table.cellWidget(row, 4)
            front.setValue(max(0, front.value() + delta))
            if self._model_back_rows[row]:
                back.setValue(max(0, back.value() + delta))
        self._model_applied = checked

    def save_config(self):
        self.settings.setValue(ENDPOINT_KEY, self.endpoint.text().strip())
        self.settings.setValue(ACCESS_KEY, self.access_key.text().strip())

    def validate(self) -> bool:
        if any(not entry.name for entry in self.entries()):
            QMessageBox.warning(None, "M87 • PLANILHA", "Informe o nome de todos os registros.")
            return False
        if not self.endpoint.text().strip() or not self.access_key.text().strip():
            QMessageBox.warning(
                None,
                "M87 • PLANILHA",
                "Configure o endereço da integração e a chave de acesso.",
            )
            return False
        return True


def submit_print_log(parent, editor: PrintLogEditor) -> bool:
    editor.save_config()
    entries = editor.entries()
    try:
        result = send_entries(
            editor.endpoint.text(),
            editor.access_key.text(),
            entries,
        )
        duplicates = result.get("duplicates") or []
        if duplicates:
            names = "\n".join(f"• {name}" for name in duplicates)
            answer = QMessageBox.question(
                parent,
                "M87 • Registro duplicado",
                f"Já existe registro para:\n\n{names}\n\nEnviar novamente?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return False
            send_entries(
                editor.endpoint.text(),
                editor.access_key.text(),
                entries,
                allow_duplicates=True,
            )
    except PrintLogError as error:
        QMessageBox.critical(parent, "M87 • PLANILHA", str(error))
        return False
    _notify_terminal(
        parent,
        "Registrado na planilha",
    )
    return True


def _notify_terminal(parent, text: str):
    current = parent
    while current is not None:
        notify = getattr(current, "_notify_terminal", None)
        if callable(notify):
            notify(text)
            return
        label = getattr(current, "session_result_label", None)
        if label is not None:
            label.setText(text)
            label.show()
            adjust = getattr(current, "ajustar_altura_ao_conteudo", None)
            if callable(adjust):
                QTimer.singleShot(0, adjust)
            clear = getattr(current, "clear_session_result", None)
            if callable(clear):
                QTimer.singleShot(8000, clear)
            return
        current = current.parent() if hasattr(current, "parent") else None


class PrintLogDialog(QDialog):
    def __init__(self, entries: list[PrintLogEntry], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Confirmar registros da Konica")
        self.setModal(True)
        self.resize(780, min(560, 250 + len(entries) * 34))
        self.setStyleSheet(
            """
            QDialog { background-color: rgb(8, 13, 22); }
            QLabel { color: rgba(255, 255, 255, 0.72); font-family: "Menlo"; font-size: 11px; }
            QLabel#printLogTitle { color: rgb(244, 189, 4); font-size: 14px; font-weight: 700; }
            QLineEdit, QSpinBox {
                min-height: 28px; padding: 0 7px; color: rgba(255,255,255,.92);
                background: rgba(255,255,255,.05);
                border: 1px solid rgba(208,147,29,.55); border-radius: 5px;
            }
            QTableWidget {
                color: rgba(255,255,255,.88); background: rgba(255,255,255,.025);
                border: 1px solid rgba(208,147,29,.35);
                gridline-color: rgba(255,255,255,.10);
            }
            QHeaderView::section {
                color: rgb(244,189,4); background: rgba(244,189,4,.08);
                border: 0; padding: 6px; font-family: "Menlo"; font-size: 10px;
            }
            QPushButton {
                min-width: 92px; min-height: 30px; padding: 0 12px;
                color: rgb(244,189,4); background: rgba(255,255,255,.06);
                border: 1px solid rgba(208,147,29,.55); border-radius: 6px;
                font-family: "Menlo"; font-size: 11px; font-weight: 700;
            }
            QPushButton:hover { background: rgba(244,189,4,.14); }
            """
        )
        self.editor = PrintLogEditor(
            entries,
            QSettings("M87Tools", "M87Terminal"),
        )

        layout = QVBoxLayout(self)
        title = QLabel("CONFIRMAR ENVIO PARA A PLANILHA")
        title.setObjectName("printLogTitle")
        layout.addWidget(title)
        self.editor.add_to(layout)
        buttons = QHBoxLayout()
        cancel = QPushButton("Cancelar")
        send = QPushButton("Enviar")
        cancel.clicked.connect(self.reject)
        send.clicked.connect(self._submit)
        send.setDefault(False)
        send.setAutoDefault(False)
        buttons.addStretch()
        buttons.addWidget(cancel)
        buttons.addWidget(send)
        layout.addLayout(buttons)
        self._return_shortcut = QShortcut(
            QKeySequence(Qt.Key.Key_Return),
            self,
        )
        self._return_shortcut.activated.connect(self._submit)
        self._enter_shortcut = QShortcut(
            QKeySequence(Qt.Key.Key_Enter),
            self,
        )
        self._enter_shortcut.activated.connect(self._submit)

    def _submit(self):
        if self.editor.validate() and submit_print_log(self, self.editor):
            self.accept()
