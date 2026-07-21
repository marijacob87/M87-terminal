from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget


class SuggestionsBox(QWidget):
    def __init__(self):
        super().__init__()

        self.items = []
        self.selected_index = 0

        self.setObjectName("suggestionsBox")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 2, 0, 2)
        self.layout.setSpacing(0)
        self.layout.setSizeConstraint(QVBoxLayout.SetFixedSize)

        self.hide()

    # =========================
    # DADOS
    # =========================

    def set_items(self, items):
        self.items = items[:6]
        self.selected_index = 0
        self.render()

    def clear(self):
        self.items = []
        self.selected_index = 0
        self.render()

    # =========================
    # NAVEGAÇÃO
    # =========================

    def move_up(self):
        if not self.items:
            return

        self.selected_index = (self.selected_index - 1) % len(self.items)
        self.render()

    def move_down(self):
        if not self.items:
            return

        self.selected_index = (self.selected_index + 1) % len(self.items)
        self.render()

    def selected_item(self):
        if not self.items:
            return None

        return self.items[self.selected_index]

    def selected_command(self):
        return self.selected_item()

    # =========================
    # TEXTO
    # =========================

    def format_item_text(self, item, prefix):
        if isinstance(item, dict):
            if item.get("type") in ("application", "running_application"):
                return f"{prefix} {item.get('name', 'Aplicativo')}"

            if item.get("type") in ("anydesk_machine", "anydesk_app"):
                return f"{prefix} {item.get('name', 'AnyDesk')}"

            if "code" in item:
                code = item.get("code", "")
                label = item.get("label", "")

                if label:
                    return f"{prefix} {code}   {label}"

                return f"{prefix} {code}"

        return f"{prefix} {item.name}"

    # =========================
    # RENDER
    # =========================

    def render(self):
        while self.layout.count():
            layout_item = self.layout.takeAt(0)
            widget = layout_item.widget()

            if widget:
                widget.deleteLater()

        if not self.items:
            self.setMinimumHeight(0)
            self.setMaximumHeight(0)
            self.hide()
            self.updateGeometry()
            return

        for index, item in enumerate(self.items):
            prefix = "▶" if index == self.selected_index else " "
            label = QLabel(self.format_item_text(item, prefix))
            label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            label.setObjectName(
                "suggestionSelected"
                if index == self.selected_index
                else "suggestionItem"
            )
            self.layout.addWidget(label)

        self.show()
        self.layout.invalidate()
        self.layout.activate()
        self.adjustSize()

        required_height = self.layout.sizeHint().height()
        self.setMinimumHeight(required_height)
        self.setMaximumHeight(required_height)
        self.updateGeometry()

        # O macOS pode terminar de medir a fonte apenas no próximo ciclo.
        QTimer.singleShot(0, self._finalize_height)

    def _finalize_height(self):
        if not self.items:
            return

        self.layout.invalidate()
        self.layout.activate()
        required_height = self.layout.sizeHint().height()
        self.setMinimumHeight(required_height)
        self.setMaximumHeight(required_height)
        self.updateGeometry()
