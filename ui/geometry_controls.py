from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QButtonGroup, QGridLayout, QPushButton, QWidget


ANCHOR_NAMES = (
    "top_left", "top", "top_right",
    "left", "center", "right",
    "bottom_left", "bottom", "bottom_right",
)


class AnchorSelector(QWidget):
    changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        for index, name in enumerate(ANCHOR_NAMES):
            button = QPushButton()
            button.setObjectName("geoAnchor")
            button.setCheckable(True)
            button.setFixedSize(12, 12)
            button.setToolTip(name.replace("_", " ").title())
            self.group.addButton(button, index)
            layout.addWidget(button, index // 3, index % 3)
        self.setFixedSize(42, 42)
        self.group.idClicked.connect(
            lambda index: self.changed.emit(ANCHOR_NAMES[index])
        )
        self.set_anchor("center")

    def anchor(self):
        index = self.group.checkedId()
        return ANCHOR_NAMES[index] if index >= 0 else "center"

    def set_anchor(self, anchor):
        index = ANCHOR_NAMES.index(anchor) if anchor in ANCHOR_NAMES else 4
        self.group.button(index).setChecked(True)

