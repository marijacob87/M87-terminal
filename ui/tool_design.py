from PySide6.QtCore import QLineF, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import (
    QColor, QIcon, QPainter, QPainterPath, QPalette, QPen, QPixmap,
)
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel,
    QProxyStyle, QPushButton, QRadioButton, QSizePolicy, QStyle, QVBoxLayout,
    QWidget,
)

from ui.design_tokens import (
    BUTTON_HEIGHT, CARD_RADIUS, CHIP_HEIGHT, COLOR_ACCENT,
    COLOR_BACKGROUND, COLOR_DISABLED_MARK, COLOR_SELECTION_MARK,
    EMPTY_PDF_MESSAGE, FIELD_HEIGHT, FOOTER_BUTTON_SIZE,
    FONT_SIZE_BODY, FONT_SIZE_CARD_TITLE, FONT_SIZE_FIELD_LABEL,
    FONT_SIZE_SECONDARY,
    MEASURE_SWAP_FONT_SIZE, MEASURE_SWAP_FONT_WEIGHT, SELECTION_INDICATOR_SCALE,
    TEXT_EMPTY, TOOL_BACKGROUND,
    TOOL_CARD_MARGINS, TOOL_CARD_SPACING, TOOL_COLUMN_SPACING,
    TOOL_CONTROLS_WIDTH, TOOL_PAGE_MARGINS, TOOL_PAGE_SPACING,
)


TOOL_FIELD_HEIGHT = FIELD_HEIGHT
TOOL_BUTTON_HEIGHT = BUTTON_HEIGHT
TOOL_CHIP_HEIGHT = CHIP_HEIGHT
TOOL_FOOTER_BUTTON_SIZE = FOOTER_BUTTON_SIZE


TOOL_STANDARD_QSS = """
QWidget[toolSurface="true"], QWidget[toolRole="controls"] { background:__TOOL_BACKGROUND__; }
QFrame[toolRole="card"] {
    background:rgba(255,255,255,.025);
    border:1px solid rgba(255,255,255,.08);
    border-radius:__CARD_RADIUS__px;
}
QLabel[toolRole="cardTitle"] {
    color:__ACCENT__; font-size:__FONT_CARD_TITLE__px; font-weight:700; letter-spacing:.7px;
}
QLabel[toolRole="fieldLabel"] {
    color:rgba(255,255,255,.48); font-size:__FONT_FIELD_LABEL__px;
}
QWidget[toolSurface="true"] QLineEdit,
QWidget[toolSurface="true"] QComboBox,
QWidget[toolSurface="true"] QSpinBox,
QWidget[toolSurface="true"] QDoubleSpinBox {
    color:rgba(255,255,255,.88);
    background:rgba(255,255,255,.07);
    border:1px solid rgba(255,255,255,.08);
    border-radius:4px;
    min-height:__TOOL_FIELD_HEIGHT__px; max-height:__TOOL_FIELD_HEIGHT__px;
    padding:0 5px;
}
QWidget[toolSurface="true"] QCheckBox,
QWidget[toolSurface="true"] QRadioButton {
    min-height:20px;
    spacing:6px;
    padding:0;
    color:rgba(255,255,255,.78);
}
QPushButton[toolRole="chip"] {
    color:rgba(255,255,255,.68);
    border:1px solid rgba(255,255,255,.12);
    background:rgba(255,255,255,.035);
    border-radius:0;
    min-height:25px; max-height:25px;
    padding:0 8px; font-size:__FONT_BODY__px;
}
QPushButton[toolRole="chip"]:hover {
    color:#FFC400; border-color:rgba(255,196,0,.35);
}
QPushButton#toolMeasureSwap {
    color:__ACCENT__;
    border:1px solid rgba(255,196,0,.35);
    background:rgba(255,196,0,.08);
    border-radius:4px;
    padding:0;
    min-width:28px; max-width:28px;
    min-height:26px; max-height:26px;
    font-size:__MEASURE_SWAP_FONT_SIZE__px;
    font-weight:__MEASURE_SWAP_FONT_WEIGHT__;
    text-align:center;
}
QPushButton#toolMeasureSwap:hover {
    color:#fff0a0;
    border-color:rgba(255,196,0,.60);
    background:rgba(255,196,0,.13);
}
QPushButton#toolSuggestion {
    background:rgba(255,255,255,.025);
    border:1px solid rgba(255,255,255,.08);
    border-radius:__CARD_RADIUS__px;
    min-height:62px;
    max-height:62px;
    padding:0;
    text-align:left;
}
QPushButton#toolSuggestion:checked {
    background:rgba(255,255,255,.065);
    border-color:rgba(255,255,255,.12);
}
QPushButton#toolSuggestion:disabled {
    background:rgba(255,255,255,.018);
    border-color:rgba(255,255,255,.06);
}
QPushButton#toolSuggestion QLabel[toolRole="suggestionTitle"] {
    color:rgba(255,196,0,.72); font-size:__FONT_FIELD_LABEL__px; font-weight:700;
}
QPushButton#toolSuggestion QLabel[toolRole="suggestionValue"] {
    color:rgba(255,255,255,.86); font-size:__FONT_BODY__px; font-weight:700;
}
QPushButton#toolSuggestion QLabel[toolRole="suggestionMeta"] {
    color:rgba(255,255,255,.52); font-size:__FONT_SECONDARY__px;
}
QPushButton[toolRole="footerAction"] {
    min-width:136px; max-width:136px;
    min-height:28px; max-height:28px;
    padding:0 12px;
    color:rgba(255,255,255,.68);
    border:1px solid rgba(255,255,255,.14);
    background:transparent;
    border-radius:4px;
    font-weight:700;
}
QPushButton[toolRole="footerAction"][actionRole="primary"] {
    color:__ACCENT__;
    border-color:rgba(255,196,0,.48);
    background:transparent;
}
QPushButton[toolRole="footerAction"]:hover {
    color:#fff0a0; border-color:rgba(255,196,0,.55);
}
QPushButton[toolRole="footerAction"]:disabled {
    color:rgba(255,255,255,.24);
    border-color:rgba(255,255,255,.07);
    background:transparent;
}
"""
TOOL_STANDARD_QSS = (
    TOOL_STANDARD_QSS
    .replace("__TOOL_FIELD_HEIGHT__", str(TOOL_FIELD_HEIGHT))
    .replace("__TOOL_BACKGROUND__", COLOR_BACKGROUND)
    .replace("__CARD_RADIUS__", str(CARD_RADIUS))
    .replace("__MEASURE_SWAP_FONT_SIZE__", str(MEASURE_SWAP_FONT_SIZE))
    .replace("__MEASURE_SWAP_FONT_WEIGHT__", str(MEASURE_SWAP_FONT_WEIGHT))
    .replace("__ACCENT__", COLOR_ACCENT)
    .replace("__FONT_CARD_TITLE__", str(FONT_SIZE_CARD_TITLE))
    .replace("__FONT_FIELD_LABEL__", str(FONT_SIZE_FIELD_LABEL))
    .replace("__FONT_BODY__", str(FONT_SIZE_BODY))
    .replace("__FONT_SECONDARY__", str(FONT_SIZE_SECONDARY))
)


def set_tool_role(widget, role):
    widget.setProperty("toolRole", role)
    return widget


def show_button_success(button, *, restore_text=None, duration=1600):
    """Confirma uma ação no próprio botão, sem abrir uma caixa modal."""
    if button is None:
        return
    generation = int(button.property("successGeneration") or 0) + 1
    button.setProperty("successGeneration", generation)
    original_text = restore_text if restore_text is not None else button.text()
    original_style = button.styleSheet()
    original_enabled = button.isEnabled()
    button.setText("✓")
    button.setEnabled(False)
    button.setStyleSheet(
        original_style
        + "QPushButton { color:#70D878; border-color:rgba(112,216,120,.72); "
          "background:rgba(50,150,80,.12); font-weight:700; }"
    )

    def restore():
        try:
            if int(button.property("successGeneration") or 0) != generation:
                return
            button.setText(original_text)
            button.setStyleSheet(original_style)
            button.setEnabled(original_enabled)
        except RuntimeError:
            pass

    QTimer.singleShot(duration, restore)


class _TerminalSelectionStyle(QProxyStyle):
    """Indicadores macOS-like usando a cor de destaque do Terminal."""

    def drawPrimitive(self, element, option, painter, widget=None):
        checkbox = element == QStyle.PrimitiveElement.PE_IndicatorCheckBox
        radio = element == QStyle.PrimitiveElement.PE_IndicatorRadioButton
        if not checkbox and not radio:
            return super().drawPrimitive(element, option, painter, widget)

        enabled = bool(option.state & QStyle.StateFlag.State_Enabled)
        selected = bool(option.state & QStyle.StateFlag.State_On)
        mixed = bool(option.state & QStyle.StateFlag.State_NoChange)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        yellow = QColor(COLOR_ACCENT)
        border = QColor(255, 255, 255, 105 if hovered else 72)
        fill = QColor(yellow if enabled else QColor(110, 110, 110))
        mark = QColor(COLOR_SELECTION_MARK if enabled else COLOR_DISABLED_MARK)
        available = QRectF(option.rect).adjusted(1.0, 1.0, -1.0, -1.0)
        width = available.width() * SELECTION_INDICATOR_SCALE
        height = available.height() * SELECTION_INDICATOR_SCALE
        rect = QRectF(
            available.center().x() - width / 2,
            available.center().y() - height / 2,
            width,
            height,
        )

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(fill if selected or mixed else border, 1.0))
        painter.setBrush(fill if selected or mixed else QColor(255, 255, 255, 12))
        if radio:
            painter.drawEllipse(rect)
            if selected:
                inset = min(rect.width(), rect.height()) * .30
                dot = rect.adjusted(inset, inset, -inset, -inset)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(mark)
                painter.drawEllipse(dot)
        else:
            radius = min(2.0, min(rect.width(), rect.height()) * .22)
            painter.drawRoundedRect(rect, radius, radius)
            painter.setPen(QPen(mark, 1.25, Qt.PenStyle.SolidLine,
                                Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            if mixed:
                y = rect.center().y()
                inset = rect.width() * .22
                painter.drawLine(QLineF(rect.left() + inset, y, rect.right() - inset, y))
            elif selected:
                path = QPainterPath()
                path.moveTo(rect.left() + rect.width() * .20, rect.center().y())
                path.lineTo(rect.left() + rect.width() * .43, rect.bottom() - rect.height() * .20)
                path.lineTo(rect.right() - rect.width() * .15, rect.top() + rect.height() * .18)
                painter.drawPath(path)
        painter.restore()


_TERMINAL_SELECTION_STYLE = None


def apply_terminal_accent(widget):
    """Aplica o amarelo do Terminal aos controles de seleção da superfície."""
    palette = widget.palette()
    yellow = QColor(COLOR_ACCENT)
    palette.setColor(QPalette.ColorRole.Highlight, yellow)
    if hasattr(QPalette.ColorRole, "Accent"):
        palette.setColor(QPalette.ColorRole.Accent, yellow)
    widget.setPalette(palette)
    global _TERMINAL_SELECTION_STYLE
    if _TERMINAL_SELECTION_STYLE is None:
        # Não passe QApplication.style() como base: QProxyStyle assumiria a
        # propriedade do estilo global e ambos tentariam destruí-lo no
        # encerramento, causando EXC_BAD_ACCESS no QApplication destructor.
        _TERMINAL_SELECTION_STYLE = _TerminalSelectionStyle()
        _TERMINAL_SELECTION_STYLE.setParent(QApplication.instance())
    controls = widget.findChildren(QCheckBox) + widget.findChildren(QRadioButton)
    for control in controls:
        control.setStyle(_TERMINAL_SELECTION_STYLE)
    return widget


def draw_empty_pdf_message(painter, rect):
    """Desenha o estado vazio idêntico em todas as prévias de PDF."""
    painter.setPen(QColor(*TEXT_EMPTY))
    painter.drawText(rect, Qt.AlignCenter, EMPTY_PDF_MESSAGE)


def configure_measure_swap(button):
    """Padroniza o botão que troca largura e altura nas ferramentas."""
    button.setText("⇄")
    button.setObjectName("toolMeasureSwap")
    button.setFixedSize(28, TOOL_FIELD_HEIGHT)
    button.setToolTip("Inverter largura e altura")
    return button


def _tinted_icon(pixmap, color):
    if pixmap.isNull():
        return pixmap
    tinted = QPixmap(pixmap.size())
    tinted.fill(Qt.transparent)
    painter = QPainter(tinted)
    painter.drawPixmap(0, 0, pixmap)
    painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
    painter.fillRect(tinted.rect(), QColor(color))
    painter.end()
    return tinted


def _sf_symbol_pixmap(name, size=18):
    try:
        from AppKit import NSImage

        image = NSImage.imageWithSystemSymbolName_accessibilityDescription_(name, None)
        if image is None:
            return QPixmap()
        image.setSize_((size, size))
        pixmap = QPixmap()
        pixmap.loadFromData(bytes(image.TIFFRepresentation()))
        return pixmap.scaled(
            size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
    except Exception:
        return QPixmap()


def _standard_icon(kind, normal_color="#FFFFFF"):
    style = QApplication.style()
    choices = {
        "open": QStyle.SP_DirOpenIcon,
        "restore": QStyle.SP_BrowserReload,
        "print": QStyle.SP_FileDialogDetailedView,
        "save": QStyle.SP_DialogSaveButton,
        "clear": QStyle.SP_DialogResetButton,
    }
    themed = {
        "open": "folder-open",
        "restore": "edit-undo",
        "print": "document-print",
        "save": "document-save-as",
        "clear": "edit-clear",
    }
    symbols = {
        "open": "folder",
        "restore": "arrow.counterclockwise",
        "print": "printer",
        "save": "square.and.arrow.down",
        "clear": "eraser",
    }
    pixmap = _sf_symbol_pixmap(symbols[kind])
    if pixmap.isNull():
        themed_icon = QIcon.fromTheme(themed[kind])
        fallback = themed_icon if not themed_icon.isNull() else style.standardIcon(choices[kind])
        pixmap = fallback.pixmap(QSize(18, 18))
    icon = QIcon()
    icon.addPixmap(_tinted_icon(pixmap, normal_color), QIcon.Normal, QIcon.Off)
    icon.addPixmap(_tinted_icon(pixmap, normal_color), QIcon.Active, QIcon.Off)
    icon.addPixmap(_tinted_icon(pixmap, "#70747B"), QIcon.Disabled, QIcon.Off)
    return icon


def configure_open_pdf_button(button):
    """Aplica o único padrão de entrada de PDF das ferramentas."""
    set_tool_role(button, "openPdf")
    button.setProperty("orgPrimary", False)
    button.setObjectName("toolOpenPdf")
    button.setText("ABRIR PDF")
    button.setIcon(_standard_icon("open", "#70747B"))
    button.setIconSize(QSize(15, 15))
    button.setFixedHeight(38)
    button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    # O estilo fica no próprio componente para não ser sobrescrito pelo QSS
    # específico de ORG, GEO ou IMP.
    button.setStyleSheet("""
        QPushButton#toolOpenPdf {
            min-height:38px; max-height:38px;
            color:#FFC400;
            border:1px solid rgba(255,196,0,.42);
            background:transparent;
            border-radius:4px;
            padding:0 16px;
            text-align:left;
            font-weight:700;
        }
        QPushButton#toolOpenPdf:hover {
            color:#fff0a0;
            border-color:rgba(255,196,0,.62);
            background:transparent;
        }
        QPushButton#toolOpenPdf:pressed {
            color:#FFFFFF;
            border-color:#FFC400;
            background:transparent;
        }
        QPushButton#toolOpenPdf:disabled {
            color:rgba(255,255,255,.24);
            border-color:rgba(255,255,255,.08);
            background:transparent;
        }
    """)
    return button


def set_open_pdf_loaded(button, loaded):
    """Alterna somente a cor do ícone conforme o estado do documento."""
    button.setIcon(_standard_icon("open", "#FFFFFF" if loaded else "#70747B"))


def set_document_control_enabled(widget, enabled, disabled_opacity=0.42):
    """Mantém o estado desabilitado visível mesmo sob QSS específicos."""
    effect = getattr(widget, "_tool_state_opacity", None)
    if effect is None:
        effect = QGraphicsOpacityEffect(widget)
        widget._tool_state_opacity = effect
        widget.setGraphicsEffect(effect)
    effect.setOpacity(1.0 if enabled else disabled_opacity)
    widget.setEnabled(enabled)


def configure_pdf_file_label(label):
    """Padroniza o estado/nome do arquivo abaixo do botão Abrir PDF."""
    label.setObjectName("toolPdfFileLabel")
    label.setText("Nenhum PDF carregado")
    label.setWordWrap(True)
    label.setStyleSheet("""
        QLabel#toolPdfFileLabel {
            color:rgba(255,255,255,.43);
            background:transparent;
            border:0;
            padding:2px 0 0 0;
            font-size:10px;
        }
        QLabel#toolPdfFileLabel:disabled {
            color:rgba(255,255,255,.43);
        }
    """)
    return label


def create_pdf_file_card(open_callback):
    """Cria o cartão Arquivo compartilhado por todas as ferramentas de PDF."""
    card = QFrame()
    set_tool_role(card, "card")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(*TOOL_CARD_MARGINS)
    layout.setSpacing(TOOL_CARD_SPACING)
    title = QLabel("ARQUIVO")
    set_tool_role(title, "cardTitle")
    button = configure_open_pdf_button(QPushButton())
    button.clicked.connect(open_callback)
    label = configure_pdf_file_label(QLabel())
    layout.addWidget(title)
    layout.addWidget(button)
    layout.addWidget(label)
    return card, button, label


def format_pdf_file_summary(name, trim_width_mm, trim_height_mm, page_count, suffix=""):
    """Formata os dados exibidos no card Arquivo de todas as ferramentas."""
    return (
        f"{name}{suffix}\n"
        f"TrimBox: {trim_width_mm:.2f} × {trim_height_mm:.2f} mm · "
        f"{page_count} pág."
    )


class ToolPreviewToolbar(QWidget):
    """Navegação, rotação e zoom idênticos nas prévias de PDF."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("toolPreviewToolbar")
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        self.previous_button = self._button("‹", 32)
        self.page_label = QLabel("Nenhum PDF")
        self.page_label.setObjectName("toolPreviewPageLabel")
        self.page_label.setAlignment(Qt.AlignCenter)
        self.page_label.setMinimumWidth(138)
        self.next_button = self._button("›", 32)
        self.rotation_undo_button = self._button("↶", 32)
        self.rotate_button = self._button("↻ 90°", 58)
        self.zoom_out_button = self._button("−", 32)
        self.zoom_label = self._button("100%", 58)
        self.zoom_in_button = self._button("+", 32)
        row.addStretch()
        row.addWidget(self.previous_button)
        row.addWidget(self.page_label)
        row.addWidget(self.next_button)
        row.addSpacing(8)
        row.addWidget(self.rotation_undo_button)
        row.addWidget(self.rotate_button)
        row.addSpacing(8)
        row.addWidget(self.zoom_out_button)
        row.addWidget(self.zoom_label)
        row.addWidget(self.zoom_in_button)
        row.addStretch()
        self.setStyleSheet("""
            QWidget#toolPreviewToolbar { background:transparent; }
            QPushButton#toolPreviewButton {
                min-height:24px; max-height:24px;
                color:rgba(255,255,255,.68);
                background:rgba(255,255,255,.035);
                border:1px solid rgba(255,255,255,.12);
                border-radius:0;
                padding:0;
                text-align:center;
            }
            QPushButton#toolPreviewButton:hover {
                color:#FFC400; border-color:rgba(255,196,0,.35);
            }
            QPushButton#toolPreviewButton:disabled,
            QLabel#toolPreviewPageLabel:disabled {
                color:#70747B;
            }
            QLabel#toolPreviewPageLabel {
                color:rgba(255,255,255,.68);
                font-weight:700;
            }
        """)

    @staticmethod
    def _button(text, width):
        button = QPushButton(text)
        button.setObjectName("toolPreviewButton")
        button.setFixedWidth(width)
        return button

    def set_document_enabled(self, enabled):
        for widget in (
            self.previous_button, self.page_label, self.next_button,
            self.rotation_undo_button, self.rotate_button,
            self.zoom_out_button, self.zoom_label, self.zoom_in_button,
        ):
            widget.setEnabled(enabled)
        set_document_control_enabled(self, enabled)


class _FooterActionButton(QPushButton):
    """Botão cujo texto permanece centralizado, independentemente do ícone."""

    def __init__(self, text, icon, parent=None):
        super().__init__(text, parent)
        self._footer_icon = icon
        self.setIconSize(QSize(15, 15))

    def paintEvent(self, event):
        super().paintEvent(event)
        mode = QIcon.Normal if self.isEnabled() else QIcon.Disabled
        pixmap = self._footer_icon.pixmap(self.iconSize(), mode, QIcon.Off)
        if pixmap.isNull():
            return
        painter = QPainter(self)
        x = 12
        y = (self.height() - pixmap.height()) // 2
        painter.drawPixmap(x, y, pixmap)


class ToolActionBar(QHBoxLayout):
    """Rodapé compartilhado para manter ações idênticas entre ferramentas."""

    def __init__(
        self, parent=None, *, restore=None, print_file=None, save_as=None,
        clear=None,
    ):
        super().__init__()
        self.setContentsMargins(0, 0, 0, 0)
        self.setSpacing(7)
        self.restore_button = self._add("RESTAURAR ORIGINAL", "restore", restore)
        self.addStretch()
        self.clear_button = self._add("LIMPAR", "clear", clear)
        self.print_button = self._add("IMPRIMIR", "print", print_file, primary=True)
        self.save_button = self._add("SALVAR COMO…", "save", save_as, primary=True)

    def _add(self, text, icon, callback, primary=False):
        if callback is None:
            return None
        button = _FooterActionButton(text, _standard_icon(icon))
        set_tool_role(button, "footerAction")
        button.setProperty("actionRole", "primary" if primary else "secondary")
        button.setFixedSize(*TOOL_FOOTER_BUTTON_SIZE)
        active_color = "#FFC400" if primary else "rgba(255,255,255,.68)"
        button.setStyleSheet(f"""
            QPushButton {{
                color:{active_color};
                background:transparent;
                border:1px solid rgba(255,255,255,.14);
                border-radius:4px;
                padding:0 12px;
                text-align:center;
                font-weight:700;
            }}
            QPushButton:hover {{
                color:#fff0a0; border-color:rgba(255,196,0,.55);
            }}
            QPushButton:disabled {{
                color:#70747B;
                background:transparent;
                border-color:rgba(255,255,255,.07);
            }}
        """)
        button.clicked.connect(callback)
        self.addWidget(button)
        return button

    def set_document_enabled(self, enabled):
        for button in (self.restore_button, self.print_button, self.save_button):
            if button is not None:
                button.setEnabled(enabled)


class ToolSuggestionButton(QPushButton):
    """Sugestão multilinha com a mesma métrica em todas as ferramentas."""

    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self.setObjectName("toolSuggestion")
        self.setCheckable(True)
        self._full_text = ""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(2)
        self.title_label = set_tool_role(QLabel(), "suggestionTitle")
        self.value_label = set_tool_role(QLabel(), "suggestionValue")
        self.meta_label = set_tool_role(QLabel(), "suggestionMeta")
        for label in (self.title_label, self.value_label, self.meta_label):
            label.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout.addWidget(self.title_label)
        layout.addWidget(self.value_label)
        layout.addWidget(self.meta_label)
        self.setText(text)

    def setText(self, text):
        self._full_text = str(text)
        lines = self._full_text.splitlines()
        if not hasattr(self, "title_label"):
            return
        self.title_label.setText(lines[0] if lines else "")
        self.value_label.setText(lines[1] if len(lines) > 1 else "—")
        self.meta_label.setText("\n".join(lines[2:]))
        self.meta_label.setVisible(len(lines) > 2)

    def text(self):
        return self._full_text
