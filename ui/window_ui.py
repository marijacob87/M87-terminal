import os
import subprocess
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCursor, QIcon
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSizeGrip,
    QVBoxLayout,
    QWidget,
)

from core.config import APP_MIN_HEIGHT, APP_MIN_WIDTH, APP_TITLE
from core.state import load_window_state
from ui.suggestions import SuggestionsBox
from ui.terminal_input import TerminalInput
from ui.widgets import CommandRow


class WindowUiMixin:
    def setup_window(self):
        self.setWindowTitle("M87 TERMINAL")

        project_root = Path(__file__).resolve().parent.parent
        icon_path = project_root / "assets" / "m87_icon.png"

        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAcceptDrops(True)
        self.setMinimumSize(APP_MIN_WIDTH, APP_MIN_HEIGHT)

        state = load_window_state()
        width = max(APP_MIN_WIDTH, state["width"])
        height = max(APP_MIN_HEIGHT, state["height"])

        self.normal_height = height
        self.resize(width, height)
        self.move(state["x"], state["y"])

    def build_ui(self):
        central = QWidget()
        central.setObjectName("terminalBox")
        central.setAcceptDrops(False)
        central.setAutoFillBackground(False)

        self.main_layout = QVBoxLayout(central)
        self.main_layout.setContentsMargins(14, 8, 14, 6)
        self.main_layout.setSpacing(2)

        self.build_title()
        self.build_status()
        self.build_commands()
        self.build_input()
        self.build_resize_grip()

        self.setCentralWidget(central)
        QTimer.singleShot(100, self.input.setFocus)

    def build_title(self):
        self.title = QLabel(APP_TITLE)
        self.title.setObjectName("title")

        self.code_button = QLabel("</>")
        self.code_button.setObjectName("codeButton")
        self.code_button.setCursor(QCursor(Qt.PointingHandCursor))
        self.code_button.setToolTip("Abrir projeto no VS Code")
        self.code_button.mousePressEvent = (
            lambda event: self.open_project_in_vscode()
        )

        self.minimize_button = QLabel("—")
        self.minimize_button.setObjectName("minimizeButton")
        self.minimize_button.setCursor(QCursor(Qt.PointingHandCursor))
        self.minimize_button.setToolTip("Minimizar")
        self.minimize_button.mousePressEvent = (
            lambda event: self.showMinimized()
        )

        title_layout = QHBoxLayout()
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(2)
        title_layout.addWidget(self.title)
        title_layout.addStretch()
        title_layout.addWidget(self.code_button)
        title_layout.addWidget(self.minimize_button)

        self.main_layout.addLayout(title_layout)

    def open_project_in_vscode(self):
        project_path = os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))
        )

        try:
            subprocess.Popen(
                ["open", "-a", "Visual Studio Code", project_path]
            )
        except Exception as error:
            print(f"ERRO AO ABRIR VS CODE: {error}")

    def build_status(self):
        self.status = QLabel("")
        self.status.setObjectName("status")

        self.divider_1 = QLabel("────────────────────────────────────")
        self.divider_1.setObjectName("divider")

        self.main_layout.addWidget(self.status)
        self.main_layout.addWidget(self.divider_1)

    def build_commands(self):
        self.commands_grid = QGridLayout()
        self.commands_grid.setContentsMargins(0, 0, 0, 0)
        self.commands_grid.setHorizontalSpacing(6)
        self.commands_grid.setVerticalSpacing(0)

        for item in self.commands:
            code = item.get("code", "").upper()
            label = item.get("label", code)

            if not code:
                continue

            row = CommandRow(label, code, self.execute_command)
            self.rows[code] = row
            self.command_widgets.append(row)

        self.main_layout.addLayout(self.commands_grid)

        self.divider_2 = QLabel("────────────────────────────────────")
        self.divider_2.setObjectName("divider")
        self.main_layout.addWidget(self.divider_2)

    def build_input(self):
        self.input = TerminalInput("m87@macstudio ~ %")
        self.input.setObjectName("terminalInput")
        self.input.returnPressed.connect(self.execute_from_input)
        self.input.textChanged.connect(self.update_suggestions)
        self.input.arrowUpPressed.connect(self.move_suggestion_up)
        self.input.arrowDownPressed.connect(self.move_suggestion_down)
        self.input.escapePressed.connect(self.clear_context)

        self.active_file_label = QLabel("")
        self.active_file_label.setObjectName("activeFileLabel")
        self.active_file_label.setWordWrap(True)
        self.active_file_label.hide()

        self.suggestions = SuggestionsBox()
        self.suggestions.clear()

        self.main_layout.addWidget(self.input)
        self.main_layout.addWidget(self.active_file_label)
        self.main_layout.addWidget(self.suggestions)

    def build_resize_grip(self):
        grip_layout = QHBoxLayout()
        grip_layout.setContentsMargins(0, 0, 0, 0)

        self.size_grip = QSizeGrip(self)
        self.size_grip.setObjectName("sizeGrip")

        grip_layout.addStretch()
        grip_layout.addWidget(self.size_grip)
        self.main_layout.addLayout(grip_layout)
