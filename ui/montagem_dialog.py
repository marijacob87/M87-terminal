from PySide6.QtCore import Qt, QRectF, QSettings, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core.montagem_calculator import obter_opcoes


DIALOG_STYLE = """
QDialog {
    background: #111318;
    color: #E8E8E8;
}
QLabel {
    color: #E8E8E8;
    font-size: 12px;
}
QLabel#sectionTitle {
    color: #D0931D;
    font-size: 10px;
    font-weight: 900;
    letter-spacing: 1.2px;
}
QLabel#fieldLabel {
    color: #8E9198;
    font-size: 9px;
    font-weight: 800;
}
QLabel#resultTitle {
    color: #D0931D;
    font-size: 10px;
    font-weight: 900;
    letter-spacing: 1px;
}
QLabel#resultMain {
    color: #E8E8E8;
    font-size: 22px;
    font-weight: 800;
}
QLabel#resultMeta {
    color: #BFC2C8;
    font-size: 11px;
}
QLabel#warning {
    color: #D0931D;
    background: rgba(208, 147, 29, 0.10);
    border-left: 3px solid #D0931D;
    padding: 7px 9px;
    border-radius: 5px;
    font-size: 10px;
}
QFrame#line {
    background: #D0931D;
    max-height: 1px;
    min-height: 1px;
}
QFrame#resultCard {
    background: #15181E;
    border: 1px solid #363A42;
    border-radius: 8px;
}
QFrame#resultCard[selected="true"] {
    border: 1px solid #D0931D;
}
QDoubleSpinBox, QSpinBox {
    background: #171A20;
    color: #E8E8E8;
    border: 1px solid #3A3E47;
    border-radius: 6px;
    padding: 6px 8px;
    font-size: 12px;
    min-height: 22px;
}
QDoubleSpinBox:focus, QSpinBox:focus {
    border: 1px solid #D0931D;
}
QCheckBox {
    color: #E8E8E8;
    spacing: 8px;
    font-size: 11px;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #5A5F69;
    border-radius: 3px;
    background: #171A20;
}
QCheckBox::indicator:checked {
    background: #D0931D;
    border-color: #D0931D;
}
QPushButton {
    background: #D0931D;
    color: #111318;
    border: none;
    border-radius: 8px;
    padding: 7px 18px;
    font-size: 11px;
    font-weight: 900;
}
QPushButton:hover { background: #E0A735; }
QPushButton:pressed { background: #B8821A; }
QPushButton#secondaryButton {
    background: transparent;
    color: #D0931D;
    border: 1px solid #D0931D;
}
"""


class MontagemPreview(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.resultado = None
        self.papel_l = 0.0
        self.papel_a = 0.0
        self.espaco = 0.0
        self.setMinimumHeight(260)

    def set_data(self, resultado, papel_l, papel_a, espaco):
        self.resultado = resultado
        self.papel_l = papel_l
        self.papel_a = papel_a
        self.espaco = espaco
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), QColor("#111318"))

        if not self.resultado or self.papel_l <= 0 or self.papel_a <= 0:
            painter.setPen(QColor("#8E9198"))
            painter.drawText(self.rect(), Qt.AlignCenter, "Preencha as medidas para visualizar")
            return

        margin = 22.0
        available = self.rect().adjusted(int(margin), int(margin), -int(margin), -int(margin))
        scale = min(available.width() / self.papel_l, available.height() / self.papel_a)
        draw_w = self.papel_l * scale
        draw_h = self.papel_a * scale
        origin_x = available.center().x() - draw_w / 2
        origin_y = available.center().y() - draw_h / 2
        paper = QRectF(origin_x, origin_y, draw_w, draw_h)

        painter.setPen(QPen(QColor("#E8E8E8"), 1.2))
        painter.setBrush(QColor("#15181E"))
        painter.drawRect(paper)

        r = self.resultado
        useful = QRectF(
            origin_x + r.margem_esquerda * scale,
            origin_y + r.margem_superior * scale,
            max(0.0, self.papel_l - r.margem_esquerda - r.margem_direita) * scale,
            max(0.0, self.papel_a - r.margem_superior - r.margem_inferior) * scale,
        )
        dash = QPen(QColor("#D0931D"), 1.0, Qt.DashLine)
        painter.setPen(dash)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(useful)

        painter.setPen(QPen(QColor("#D7D9DE"), 1.0))
        for linha in range(r.linhas):
            for coluna in range(r.colunas):
                x_mm = r.inicio_x + coluna * (r.peca_l + self.espaco)
                # Resultado do site usa origem inferior. Qt usa origem superior.
                y_mm_bottom = r.inicio_y + linha * (r.peca_a + self.espaco)
                y_mm_top = self.papel_a - y_mm_bottom - r.peca_a
                rect = QRectF(
                    origin_x + x_mm * scale,
                    origin_y + y_mm_top * scale,
                    r.peca_l * scale,
                    r.peca_a * scale,
                )
                painter.drawRect(rect)

        painter.setPen(QColor("#8E9198"))
        painter.setFont(QFont(self.font().family(), 9))
        painter.drawText(
            QRectF(paper.left(), max(0, paper.top() - 20), paper.width(), 16),
            Qt.AlignCenter,
            f"{self.papel_l:g} × {self.papel_a:g} mm",
        )


class ResultCard(QFrame):
    clicked = Signal(int)

    def __init__(self, index, title, parent=None):
        super().__init__(parent)
        self.index = index
        self.setObjectName("resultCard")
        self.setProperty("selected", False)
        self.setCursor(Qt.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(4)

        self.title = QLabel(title)
        self.title.setObjectName("resultTitle")
        self.main = QLabel("—")
        self.main.setObjectName("resultMain")
        self.orientation = QLabel("")
        self.orientation.setObjectName("resultMeta")
        self.details = QLabel("")
        self.details.setObjectName("resultMeta")
        self.details.setWordWrap(True)

        layout.addWidget(self.title)
        layout.addWidget(self.main)
        layout.addWidget(self.orientation)
        layout.addSpacing(5)
        layout.addWidget(self.details)

    def mousePressEvent(self, event):
        self.clicked.emit(self.index)
        super().mousePressEvent(event)

    def set_selected(self, selected):
        self.setProperty("selected", bool(selected))
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def set_result(self, result, quantidade):
        self.main.setText(f"{result.colunas} × {result.linhas} = {result.total}")
        self.orientation.setText(result.orientacao)
        lines = [f"Aproveitamento: {result.aproveitamento:.1f}%"]
        if result.planos is not None:
            excedente = int(result.pecas_produzidas - quantidade)
            lines.extend([
                f"Folhas necessárias: {result.planos}",
                f"Produzidas: {result.pecas_produzidas}",
                f"Excedentes: +{excedente}",
            ])
        else:
            lines.append("Quantidade não informada")
        self.details.setText("\n".join(lines))


class MontagemDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings = QSettings("M87Tools", "M87Terminal")
        self.results = []
        self.selected_result = 0

        self.setWindowTitle("MON · Calcular Montagem")
        self.resize(980, 610)
        self.setMinimumSize(880, 560)
        self.setStyleSheet(DIALOG_STYLE)
        self.build_ui()
        self.connect_signals()
        self.recalculate()

    def _double_field(self, value=0.0, maximum=100000.0):
        field = QDoubleSpinBox()
        field.setRange(0.0, maximum)
        field.setDecimals(2)
        field.setSingleStep(1.0)
        field.setValue(value)
        field.setAccelerated(True)
        field.setGroupSeparatorShown(False)
        return field

    def _labeled(self, label, widget):
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        text = QLabel(label)
        text.setObjectName("fieldLabel")
        layout.addWidget(text)
        layout.addWidget(widget)
        return box

    def build_ui(self):
        main = QVBoxLayout(self)
        main.setContentsMargins(22, 18, 22, 16)
        main.setSpacing(12)

        content = QHBoxLayout()
        content.setSpacing(24)
        content.addWidget(self.build_inputs(), 0)
        content.addWidget(self.build_results(), 1)
        main.addLayout(content, 1)
        main.addLayout(self.build_buttons())

    def build_inputs(self):
        wrapper = QWidget()
        wrapper.setFixedWidth(300)
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(9)

        title = QLabel("PAPEL")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        self.papel_l = self._double_field(480)
        self.papel_a = self._double_field(330)
        row = QHBoxLayout()
        row.addWidget(self._labeled("Largura (mm)", self.papel_l))
        row.addWidget(self._labeled("Altura (mm)", self.papel_a))
        layout.addLayout(row)

        self.inverter_papel = QCheckBox("Inverter medidas do papel")
        layout.addWidget(self.inverter_papel)
        layout.addWidget(self._separator())

        title = QLabel("PEÇA")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        self.peca_l = self._double_field(85)
        self.peca_a = self._double_field(55)
        row = QHBoxLayout()
        row.addWidget(self._labeled("Largura (mm)", self.peca_l))
        row.addWidget(self._labeled("Altura (mm)", self.peca_a))
        layout.addLayout(row)

        self.inverter_peca = QCheckBox("Inverter medidas da peça")
        layout.addWidget(self.inverter_peca)
        layout.addWidget(self._separator())

        self.quantidade = QSpinBox()
        self.quantidade.setRange(0, 100000000)
        self.quantidade.setSpecialValueText("Opcional")
        self.quantidade.setValue(100)

        self.espaco = self._double_field(5)
        self.margem = self._double_field(5)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        grid.addWidget(self._labeled("Quantidade", self.quantidade), 0, 0, 1, 2)
        grid.addWidget(self._labeled("Espaço (mm)", self.espaco), 1, 0)
        grid.addWidget(self._labeled("Margem (mm)", self.margem), 1, 1)
        layout.addLayout(grid)

        self.pinca = QCheckBox("Acrescentar 15 mm de pinça")
        layout.addWidget(self.pinca)

        hint = QLabel("Pinça sempre na parte inferior da folha horizontal.")
        hint.setObjectName("fieldLabel")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.warning = QLabel("")
        self.warning.setObjectName("warning")
        self.warning.setWordWrap(True)
        self.warning.hide()
        layout.addWidget(self.warning)
        layout.addStretch()
        return wrapper

    def build_results(self):
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        cards = QHBoxLayout()
        cards.setSpacing(12)
        self.best_card = ResultCard(0, "MELHOR MONTAGEM")
        self.second_card = ResultCard(1, "2ª OPÇÃO")
        self.best_card.clicked.connect(self.select_result)
        self.second_card.clicked.connect(self.select_result)
        cards.addWidget(self.best_card)
        cards.addWidget(self.second_card)
        layout.addLayout(cards)

        preview_title = QLabel("PRÉVIA DA MONTAGEM")
        preview_title.setObjectName("sectionTitle")
        layout.addWidget(preview_title)

        self.preview = MontagemPreview()
        layout.addWidget(self.preview, 1)
        return wrapper

    def build_buttons(self):
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        clear_button = QPushButton("LIMPAR")
        clear_button.setObjectName("secondaryButton")
        clear_button.clicked.connect(self.clear_fields)

        close_button = QPushButton("OK")
        close_button.setFixedWidth(62)
        close_button.clicked.connect(self.accept)

        layout.addWidget(clear_button)
        layout.addStretch()
        layout.addWidget(close_button)
        return layout

    def _separator(self):
        line = QFrame()
        line.setObjectName("line")
        line.setFrameShape(QFrame.HLine)
        return line

    def connect_signals(self):
        fields = [
            self.papel_l, self.papel_a, self.peca_l, self.peca_a,
            self.quantidade, self.espaco, self.margem,
        ]
        for field in fields:
            field.valueChanged.connect(self.recalculate)

        for checkbox in [self.inverter_papel, self.inverter_peca, self.pinca]:
            checkbox.toggled.connect(self.recalculate)

    def current_values(self):
        papel_l = self.papel_l.value()
        papel_a = self.papel_a.value()
        peca_l = self.peca_l.value()
        peca_a = self.peca_a.value()

        if self.inverter_papel.isChecked():
            papel_l, papel_a = papel_a, papel_l
        if self.pinca.isChecked():
            papel_l, papel_a = max(papel_l, papel_a), min(papel_l, papel_a)
        if self.inverter_peca.isChecked():
            peca_l, peca_a = peca_a, peca_l

        quantidade = self.quantidade.value() or None
        return papel_l, papel_a, peca_l, peca_a, quantidade

    def recalculate(self):
        papel_l, papel_a, peca_l, peca_a, quantidade = self.current_values()
        valid = all(value > 0 for value in [papel_l, papel_a, peca_l, peca_a])

        if not valid:
            self.results = []
            self.warning.setText("Preencha papel e peça antes de calcular. A quantidade pode ficar vazia.")
            self.warning.show()
            self.best_card.main.setText("—")
            self.second_card.main.setText("—")
            self.preview.set_data(None, 0, 0, 0)
            return

        self.warning.hide()
        self.results = obter_opcoes(
            papel_l=papel_l,
            papel_a=papel_a,
            peca_l=peca_l,
            peca_a=peca_a,
            espaco=self.espaco.value(),
            margem=self.margem.value(),
            quantidade=quantidade,
            acrescentar_pinca=self.pinca.isChecked(),
        )

        self.best_card.set_result(self.results[0], quantidade or 0)
        self.second_card.set_result(self.results[1], quantidade or 0)
        self.select_result(min(self.selected_result, 1))

    def select_result(self, index):
        self.selected_result = index
        self.best_card.set_selected(index == 0)
        self.second_card.set_selected(index == 1)
        if not self.results:
            return
        papel_l, papel_a, _, _, _ = self.current_values()
        self.preview.set_data(
            self.results[index], papel_l, papel_a, self.espaco.value()
        )

    def clear_fields(self):
        for field in [self.papel_l, self.papel_a, self.peca_l, self.peca_a]:
            field.setValue(0)
        self.quantidade.setValue(0)
        self.espaco.setValue(5)
        self.margem.setValue(5)
        self.pinca.setChecked(False)
        self.inverter_papel.setChecked(False)
        self.inverter_peca.setChecked(False)
        self.papel_l.setFocus()

    def showEvent(self, event):
        super().showEvent(event)
        geometry = self.settings.value("montagem_dialog/geometry")
        if geometry:
            self.restoreGeometry(geometry)
        self.ensure_window_is_visible()

    def _save_geometry(self):
        self.settings.setValue("montagem_dialog/geometry", self.saveGeometry())

    def closeEvent(self, event):
        self._save_geometry()
        super().closeEvent(event)

    def accept(self):
        self._save_geometry()
        super().accept()

    def reject(self):
        self._save_geometry()
        super().reject()

    def ensure_window_is_visible(self):
        geometry = self.frameGeometry()
        if any(screen.availableGeometry().intersects(geometry) for screen in QApplication.screens()):
            return
        screen = QApplication.primaryScreen()
        if screen:
            geometry.moveCenter(screen.availableGeometry().center())
            self.move(geometry.topLeft())
