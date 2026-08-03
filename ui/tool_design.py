from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout


TOOL_CONTROLS_WIDTH = 400
TOOL_PAGE_MARGINS = (14, 12, 14, 12)
TOOL_PAGE_SPACING = 9
TOOL_COLUMN_SPACING = 12
TOOL_CARD_MARGINS = (11, 8, 11, 9)
TOOL_CARD_SPACING = 7
TOOL_CHIP_HEIGHT = 25


TOOL_STANDARD_QSS = """
QWidget[toolSurface="true"], QWidget[toolRole="controls"] { background:#080a0d; }
QFrame[toolRole="card"] {
    background:rgba(255,255,255,.025);
    border:1px solid rgba(255,255,255,.08);
    border-radius:7px;
}
QLabel[toolRole="cardTitle"] {
    color:#FFC400; font-size:9px; font-weight:700; letter-spacing:.7px;
}
QLabel[toolRole="fieldLabel"] {
    color:rgba(255,255,255,.43); font-size:8px;
}
QWidget[toolSurface="true"] QLineEdit,
QWidget[toolSurface="true"] QComboBox,
QWidget[toolSurface="true"] QSpinBox,
QWidget[toolSurface="true"] QDoubleSpinBox {
    color:rgba(255,255,255,.88);
    background:rgba(255,255,255,.07);
    border:1px solid rgba(255,255,255,.08);
    border-radius:4px;
    min-height:20px;
}
QPushButton[toolRole="chip"] {
    color:rgba(255,255,255,.68);
    border:1px solid rgba(255,255,255,.12);
    background:rgba(255,255,255,.035);
    border-radius:0;
    min-height:25px; max-height:25px;
    padding:0 8px;
}
QPushButton[toolRole="chip"]:hover {
    color:#FFC400; border-color:rgba(255,196,0,.35);
}
QPushButton#toolMeasureSwap {
    color:#FFC400;
    border:1px solid rgba(255,196,0,.35);
    background:rgba(255,196,0,.08);
    border-radius:4px;
    padding:0;
    min-width:28px; max-width:28px;
    min-height:22px; max-height:22px;
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
    border-radius:7px;
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
    color:rgba(255,196,0,.72); font-size:8px; font-weight:700;
}
QPushButton#toolSuggestion QLabel[toolRole="suggestionValue"] {
    color:rgba(255,255,255,.86); font-size:10px; font-weight:700;
}
QPushButton#toolSuggestion QLabel[toolRole="suggestionMeta"] {
    color:rgba(255,255,255,.48); font-size:9px;
}
"""


def set_tool_role(widget, role):
    widget.setProperty("toolRole", role)
    return widget


def configure_measure_swap(button):
    """Padroniza o botão que troca largura e altura nas ferramentas."""
    button.setText("⇄")
    button.setObjectName("toolMeasureSwap")
    button.setFixedSize(28, 22)
    button.setToolTip("Inverter largura e altura")
    return button


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
