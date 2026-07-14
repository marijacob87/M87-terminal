from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel


class SuggestionsBox(QWidget):
    def __init__(self):
        super().__init__()

        self.items = []
        self.selected_index = 0

        self.setObjectName("suggestionsBox")

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 2, 0, 2)
        self.layout.setSpacing(0)

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

        self.selected_index = (
            self.selected_index - 1
        ) % len(self.items)

        self.render()

    def move_down(self):
        if not self.items:
            return

        self.selected_index = (
            self.selected_index + 1
        ) % len(self.items)

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
            if item.get("type") == "application":
                return (
                    f"{prefix} "
                    f"{item.get('name', 'Aplicativo')}"
                )

            if item.get("type") in (
                "anydesk_machine",
                "anydesk_app",
            ):
                return (
                    f"{prefix} "
                    f"{item.get('name', 'AnyDesk')}"
                )

            if "code" in item:
                code = item.get("code", "")
                label = item.get("label", "")

                if label:
                    return (
                        f"{prefix} "
                        f"{code}   {label}"
                    )

                return f"{prefix} {code}"

        return f"{prefix} {item.name}"

    # =========================
    # RENDER
    # =========================

    def render(self):
        while self.layout.count():
            item = self.layout.takeAt(0)

            if item.widget():
                item.widget().deleteLater()

        if not self.items:
            self.hide()
            return

        for index, item in enumerate(self.items):
            prefix = "▶" if index == self.selected_index else " "
            text = self.format_item_text(item, prefix)

            label = QLabel(text)

            label.setObjectName(
                "suggestionSelected"
                if index == self.selected_index
                else "suggestionItem"
            )

            self.layout.addWidget(label)

        self.show()