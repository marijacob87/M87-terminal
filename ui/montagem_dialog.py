from pathlib import Path

from PySide6.QtCore import QPoint, Qt, QRectF, QSettings, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QIcon, QPainter, QPen
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
    QSizeGrip,
    QVBoxLayout,
    QWidget,
)

from core.montagem_calculator import obter_opcoes
from ui.tool_design import (
    TOOL_CONTROLS_WIDTH, TOOL_STANDARD_QSS,
    configure_measure_swap, set_tool_role,
)
from ui.widgets import DarkMetallicTitleBar


ROOT = Path(__file__).resolve().parent.parent
YELLOW = "#FFC400"


DIALOG_STYLE = f"""
QWidget {{ font-family: "JetBrains Mono"; font-size: 10px; }}
QWidget#monBox, QWidget#monContent, QWidget#monControls {{ background: #080a0d; }}
QWidget#monBox {{ border: 1px solid rgba(255,196,0,.20); border-radius: 13px; }}
QWidget#monBox[embedded="true"] {{ border-radius: 0; }}
QLabel#monWindowTitle {{ color: white; font-size: 10px; letter-spacing: 1px; }}
QLabel#monClose {{ color: white; font-size: 16px; padding: 0 4px; }}
QLabel#monClose:hover {{ color: {YELLOW}; }}
QLabel {{ color: rgba(255,255,255,.66); }}
QFrame#monCard, QFrame#resultCard {{ background: rgba(255,255,255,.025); border: 1px solid rgba(255,255,255,.08); border-radius: 7px; }}
QLabel#monCardTitle, QLabel#sectionTitle {{ color: {YELLOW}; font-size: 9px; font-weight: 700; letter-spacing: .7px; }}
QLabel#fieldLabel {{ color: rgba(255,255,255,.43); font-size: 8px; }}
QLabel#resultTitle {{ color: rgba(255,196,0,.78); font-size: 9px; font-weight: 700; letter-spacing: .7px; }}
QLabel#resultMain {{ color: rgba(255,255,255,.92); font-size: 16px; font-weight: 700; }}
QLabel#resultMeta {{ color: rgba(255,255,255,.52); font-size: 9px; }}
QLabel#warning {{ color: rgba(255,205,205,.76); background: rgba(145,35,35,.16); border: 1px solid rgba(255,85,85,.42); border-radius: 5px; padding: 5px 7px; font-size: 8px; }}
QFrame#resultCard[selected="true"] {{ background: rgba(255,255,255,.065); border: 1px solid rgba(255,255,255,.12); }}
QDoubleSpinBox, QSpinBox {{ background: rgba(255,255,255,.07); color: rgba(255,255,255,.88); border: 1px solid rgba(255,255,255,.08); border-radius: 4px; padding: 3px 5px; min-height: 20px; }}
QCheckBox {{ color: rgba(255,255,255,.78); spacing: 6px; }}
QCheckBox::indicator {{ width: 13px; height: 13px; border: 1px solid rgba(255,255,255,.22); border-radius: 3px; background: rgba(255,255,255,.05); }}
QCheckBox::indicator:checked {{ background: {YELLOW}; border-color: {YELLOW}; }}
QPushButton {{ min-height: 20px; background: rgba(255,255,255,.04); border: 1px solid rgba(255,255,255,.12); border-radius: 4px; padding: 3px 10px; color: rgba(255,255,255,.66); }}
QPushButton:hover {{ color: #fff0a0; border-color: rgba(255,196,0,.55); }}
QPushButton:pressed {{ background: rgba(255,196,0,.12); }}
QPushButton#primaryButton {{ color: {YELLOW}; font-weight: 700; border: 1px solid rgba(255,196,0,.35); background: rgba(255,196,0,.08); }}
QPushButton#secondaryButton {{ color: rgba(255,255,255,.66); border: 1px solid rgba(255,255,255,.12); background: rgba(255,255,255,.04); }}
QWidget#monPreview {{ border: 1px solid rgba(255,196,0,.18); border-radius: 7px; background: #080a0d; }}
""" + TOOL_STANDARD_QSS


class MontagemPreview(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.resultado = None
        self.papel_l = 0.0
        self.papel_a = 0.0
        self.espaco = 0.0
        self.setMinimumHeight(260)
        self.setObjectName("monPreview")

    def set_data(self, resultado, papel_l, papel_a, espaco):
        self.resultado = resultado
        self.papel_l = papel_l
        self.papel_a = papel_a
        self.espaco = espaco
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), QColor("#080a0d"))

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
        set_tool_role(self, "card")
        self.setProperty("selected", False)
        self.setCursor(Qt.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(11, 8, 11, 9)
        layout.setSpacing(7)

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
        self.drag_position = QPoint()
        self.results = []
        self.selected_result = 0

        self.setWindowTitle("MON · CALCULAR MONTAGEM")
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.resize(980, 610)
        self.setMinimumSize(880, 560)
        icon = ROOT / "assets" / "m87_icon.png"
        if icon.exists():
            self.setWindowIcon(QIcon(str(icon)))
        self.setStyleSheet(DIALOG_STYLE)
        self.build_ui()
        self.connect_signals()
        self.recalculate()


    def _title_press(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def _title_move(self, event):
        if event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()

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
        text = QLabel(label.upper())
        text.setObjectName("fieldLabel")
        set_tool_role(text, "fieldLabel")
        layout.addWidget(text)
        layout.addWidget(widget)
        return box

    def _card(self, title):
        card = QFrame()
        card.setObjectName("monCard")
        set_tool_role(card, "card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(11, 8, 11, 9)
        layout.setSpacing(7)
        label = QLabel(title)
        label.setObjectName("monCardTitle")
        set_tool_role(label, "cardTitle")
        layout.addWidget(label)
        return card, layout

    def build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.box = QWidget()
        self.box.setObjectName("monBox")
        self.box.setProperty("toolSurface", True)
        outer.addWidget(self.box)

        main = QVBoxLayout(self.box)
        main.setContentsMargins(0, 0, 0, 8)
        main.setSpacing(5)

        bar = DarkMetallicTitleBar(height=28, radius=12)
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(14, 0, 10, 0)
        title = QLabel("M87 TERMINAL · MON · CALCULAR MONTAGEM")
        title.setObjectName("monWindowTitle")
        close = QLabel("×")
        close.setObjectName("monClose")
        close.setCursor(QCursor(Qt.PointingHandCursor))
        close.mousePressEvent = lambda event: self.close()
        bar_layout.addWidget(title)
        bar_layout.addStretch()
        bar_layout.addWidget(close)
        main.addWidget(bar)
        bar.mousePressEvent = self._title_press
        bar.mouseMoveEvent = self._title_move

        content = QHBoxLayout()
        content.setContentsMargins(14, 12, 14, 4)
        content.setSpacing(12)
        content.addWidget(self.build_inputs(), 0)
        content.addWidget(self.build_results(), 1)
        main.addLayout(content, 1)

        bottom = self.build_buttons()
        bottom.addWidget(QSizeGrip(self.box))
        main.addLayout(bottom)

    def build_inputs(self):
        wrapper = QWidget()
        wrapper.setObjectName("monControls")
        set_tool_role(wrapper, "controls")
        wrapper.setFixedWidth(TOOL_CONTROLS_WIDTH)
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(7)

        paper_card, paper_layout = self._card("PAPEL")
        self.papel_l = self._double_field(480)
        self.papel_a = self._double_field(330)
        row = QHBoxLayout()
        row.addWidget(self._labeled("Largura (mm)", self.papel_l))
        self.inverter_papel = configure_measure_swap(QPushButton())
        row.addWidget(self.inverter_papel, 0, Qt.AlignBottom)
        row.addWidget(self._labeled("Altura (mm)", self.papel_a))
        paper_layout.addLayout(row)
        layout.addWidget(paper_card)

        piece_card, piece_layout = self._card("PEÇA")
        self.peca_l = self._double_field(85)
        self.peca_a = self._double_field(55)
        row = QHBoxLayout()
        row.addWidget(self._labeled("Largura (mm)", self.peca_l))
        self.inverter_peca = configure_measure_swap(QPushButton())
        row.addWidget(self.inverter_peca, 0, Qt.AlignBottom)
        row.addWidget(self._labeled("Altura (mm)", self.peca_a))
        piece_layout.addLayout(row)
        layout.addWidget(piece_card)

        production_card, production_layout = self._card("PRODUÇÃO")
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
        production_layout.addLayout(grid)

        self.pinca = QCheckBox("Acrescentar 15 mm de pinça")
        production_layout.addWidget(self.pinca)

        hint = QLabel("Pinça sempre na parte inferior da folha horizontal.")
        hint.setObjectName("fieldLabel")
        hint.setWordWrap(True)
        production_layout.addWidget(hint)

        self.warning = QLabel("")
        self.warning.setObjectName("warning")
        self.warning.setWordWrap(True)
        self.warning.hide()
        production_layout.addWidget(self.warning)
        layout.addWidget(production_card)
        layout.addStretch()
        return wrapper

    def build_results(self):
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(7)

        cards = QHBoxLayout()
        cards.setSpacing(7)
        self.best_card = ResultCard(0, "MELHOR MONTAGEM")
        self.second_card = ResultCard(1, "2ª OPÇÃO")
        self.best_card.clicked.connect(self.select_result)
        self.second_card.clicked.connect(self.select_result)
        cards.addWidget(self.best_card)
        cards.addWidget(self.second_card)
        layout.addLayout(cards)

        self.preview = MontagemPreview()
        layout.addWidget(self.preview, 1)
        return wrapper

    def build_buttons(self):
        layout = QHBoxLayout()
        layout.setContentsMargins(14, 0, 14, 0)

        clear_button = QPushButton("LIMPAR")
        clear_button.setObjectName("secondaryButton")
        clear_button.clicked.connect(self.clear_fields)

        close_button = QPushButton("OK")
        close_button.setObjectName("primaryButton")
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

        self.inverter_papel.clicked.connect(
            lambda: self._swap_measure_fields(self.papel_l, self.papel_a)
        )
        self.inverter_peca.clicked.connect(
            lambda: self._swap_measure_fields(self.peca_l, self.peca_a)
        )
        self.pinca.toggled.connect(self.recalculate)

    def _swap_measure_fields(self, width, height):
        width_value, height_value = width.value(), height.value()
        width.blockSignals(True)
        height.blockSignals(True)
        width.setValue(height_value)
        height.setValue(width_value)
        width.blockSignals(False)
        height.blockSignals(False)
        self.recalculate()

    def current_values(self):
        papel_l = self.papel_l.value()
        papel_a = self.papel_a.value()
        peca_l = self.peca_l.value()
        peca_a = self.peca_a.value()

        if self.pinca.isChecked():
            papel_l, papel_a = max(papel_l, papel_a), min(papel_l, papel_a)

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
        self.papel_l.setFocus()

    def showEvent(self, event):
        super().showEvent(event)
        # Quando a MONTAGEM está embutida na janela de ferramentas, trocar de aba
        # também dispara showEvent. Restaurar a geometria da antiga janela solta
        # nesse momento reposicionava e redimensionava o conteúdo dentro da aba.
        if not self.isWindow():
            return
        geometry = self.settings.value("montagem_dialog/geometry")
        if geometry:
            self.restoreGeometry(geometry)
        self.ensure_window_is_visible()

    def _save_geometry(self):
        if self.isWindow():
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
