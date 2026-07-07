import json
import os
import sys

import psutil

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QLabel,
    QMainWindow,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QWidget,
    QSizeGrip,
)

from core.app_tracker import get_frontmost_app, is_valid_app, restart_app
from core.client_search import open_path
from core.config import (
    APP_MIN_HEIGHT,
    APP_MIN_WIDTH,
    APP_TITLE,
    BREAKPOINT_WIDTH,
    COMMANDS_FILE,
    STATUS_UPDATE_MS,
    WEATHER_UPDATE_MS,
)
from core.executor import execute
from core.input_handler import handle_input_text
from core.state import load_window_state, save_window_state
from core.status import get_porto_temp, get_status_data
from core.styles import APP_STYLE
from core.suggestion_engine import get_suggestions
from ui.suggestions import SuggestionsBox
from ui.terminal_input import TerminalInput
from ui.widgets import CommandRow


PDF_ACTIONS = [
    {"code": "INFO", "type": "pdf_action", "value": "info"},
    {"code": "CURVAS", "type": "pdf_action", "value": "curvas"},
    {"code": "REDUZIR", "type": "pdf_action", "value": "reduzir"},
    {"code": "RENOMEAR", "type": "pdf_action", "value": "renomear"},
]


class M87Term(QMainWindow):
    def __init__(self):
        super().__init__()

        self.commands = self.load_commands()
        self.rows = {}
        self.command_widgets = []
        self.drag_position = None
        self.current_columns = None

        self.current_pdf = None

        self.weather_temp = "--°C"
        self.status_data = {}
        self.last_real_app = None

        self.save_state_timer = QTimer(self)
        self.save_state_timer.setSingleShot(True)
        self.save_state_timer.timeout.connect(self.save_current_state)

        self.app_tracker_timer = QTimer(self)
        self.app_tracker_timer.timeout.connect(self.update_last_real_app)
        self.app_tracker_timer.start(1000)

        self.setup_window()
        self.build_ui()
        self.apply_style()
        self.rebuild_command_grid()
        self.start_timers()

    # =========================
    # SETUP
    # =========================

    def setup_window(self):
        self.setWindowTitle("M87 TERM")
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAcceptDrops(True)
        self.setMinimumSize(APP_MIN_WIDTH, APP_MIN_HEIGHT)

        state = load_window_state()
        self.resize(state["width"], state["height"])
        self.move(state["x"], state["y"])

    def build_ui(self):
        central = QWidget()
        central.setObjectName("terminalBox")
        central.setAcceptDrops(True)

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

        self.minimize_button = QLabel("—")
        self.minimize_button.setObjectName("minimizeButton")
        self.minimize_button.setCursor(QCursor(Qt.PointingHandCursor))
        self.minimize_button.mousePressEvent = lambda event: self.showMinimized()

        title_layout = QHBoxLayout()
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(0)

        title_layout.addWidget(self.title)
        title_layout.addStretch()
        title_layout.addWidget(self.minimize_button)

        self.main_layout.addLayout(title_layout)

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

        # Drop agora fica centralizado na janela inteira.
        # Evita conflito entre input e janela.
        # self.input.fileDropped.connect(self.handle_file_drop)

        self.input.escapePressed.connect(self.clear_context)

        self.active_file_label = QLabel("")
        self.active_file_label.setObjectName("activeFileLabel")
        self.active_file_label.hide()

        self.suggestions = SuggestionsBox()

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

    # =========================
    # DADOS
    # =========================

    def load_commands(self):
        with open(COMMANDS_FILE, "r", encoding="utf-8") as file:
            return json.load(file)

    # =========================
    # STATUS
    # =========================

    def start_timers(self):
        psutil.cpu_percent(interval=None)

        self.update_weather()
        self.update_status()

        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self.update_status)
        self.status_timer.start(STATUS_UPDATE_MS)

        self.weather_timer = QTimer(self)
        self.weather_timer.timeout.connect(self.update_weather)
        self.weather_timer.start(WEATHER_UPDATE_MS)

    def update_weather(self):
        self.weather_temp = get_porto_temp()
        self.update_status()

    def update_status(self):
        self.status_data = get_status_data(self.weather_temp)
        self.render_status()

    def render_status(self):
        data = self.status_data.get("data", "--/--/----")
        hora = self.status_data.get("hora", "--:--")
        temp = self.status_data.get("temp", "--°C")
        battery = self.status_data.get("battery", "--%")
        ram = self.status_data.get("ram", "--%")
        cpu = self.status_data.get("cpu", "--%")

        if self.width() < BREAKPOINT_WIDTH:
            self.status.setText(
                f"{data}   {hora}   {temp}\n"
                f"BAT {battery}   RAM {ram}   CPU {cpu}"
            )
        else:
            self.status.setText(
                f"{data}   {hora}   {temp}   "
                f"BAT {battery}   RAM {ram}   CPU {cpu}"
            )

    # =========================
    # APP TRACKER
    # =========================

    def update_last_real_app(self):
        app_name = get_frontmost_app()

        if is_valid_app(app_name):
            self.last_real_app = app_name

    # =========================
    # SUGESTÕES
    # =========================

    def update_suggestions(self, text):
        if self.current_pdf:
            suggestions = self.get_pdf_suggestions(text)

            if suggestions:
                self.suggestions.set_items(suggestions)
            else:
                self.clear_suggestions()

            return

        suggestions = get_suggestions(text, self.commands)

        if suggestions:
            self.suggestions.set_items(suggestions)
        else:
            self.clear_suggestions()

    def get_pdf_suggestions(self, text):
        text = text.strip().lower()

        if not text:
            return PDF_ACTIONS

        return [
            item
            for item in PDF_ACTIONS
            if text in item.get("code", "").lower()
            or text in item.get("value", "").lower()
        ]

    def clear_suggestions(self):
        self.suggestions.clear()

    def clear_context(self):
        self.current_pdf = None
        self.active_file_label.clear()
        self.active_file_label.hide()
        self.clear_suggestions()
        self.input.clear()
        self.input.setFocus()

    def move_suggestion_up(self):
        self.suggestions.move_up()

    def move_suggestion_down(self):
        self.suggestions.move_down()

    def execute_selected_suggestion(self):
        selected = self.suggestions.selected_item()

        if not selected:
            return False

        self.input.blockSignals(True)
        self.input.clear()
        self.input.blockSignals(False)

        self.clear_suggestions()

        if isinstance(selected, dict):
            if selected.get("type") == "pdf_action":
                self.execute_pdf_action(selected)
                return True

            self.execute_command(selected.get("code", ""))
            return True

        open_path(selected)
        return True

    # =========================
    # ARQUIVO ARRASTADO
    # =========================

    def has_valid_drop_file(self, event):
        if not event.mimeData().hasUrls():
            return False

        for url in event.mimeData().urls():
            path = url.toLocalFile()

            if path and os.path.exists(path):
                return True

        return False

    def dragEnterEvent(self, event):
        if self.has_valid_drop_file(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if self.has_valid_drop_file(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        if not event.mimeData().hasUrls():
            event.ignore()
            return

        urls = event.mimeData().urls()

        for url in urls:
            path = url.toLocalFile()

            if path:
                self.handle_file_drop(path)
                event.acceptProposedAction()
                return

        event.ignore()

    def handle_file_drop(self, path):
        path = os.path.abspath(path)

        if not os.path.exists(path):
            return

        if path.lower().endswith(".pdf"):
            self.handle_pdf_drop(path)
            return

    def handle_pdf_drop(self, path):
        self.current_pdf = path

        file_name = os.path.basename(path)

        self.active_file_label.setWordWrap(True)
        self.active_file_label.setText(f"PDF ativo:\n{file_name}")
        self.active_file_label.show()

        self.input.blockSignals(True)
        self.input.clear()
        self.input.blockSignals(False)

        self.suggestions.set_items(PDF_ACTIONS)
        self.input.setFocus()

    def execute_pdf_action(self, action):
        if not self.current_pdf:
            return

        action_value = action.get("value")

        if action_value == "info":
            print(f"INFO PDF: {self.current_pdf}")

        elif action_value == "curvas":
            print(f"CURVAS PDF: {self.current_pdf}")

        elif action_value == "reduzir":
            print(f"REDUZIR PDF: {self.current_pdf}")

        elif action_value == "renomear":
            print(f"RENOMEAR PDF: {self.current_pdf}")

        self.suggestions.set_items(PDF_ACTIONS)
        self.input.setFocus()

    # =========================
    # COMANDOS
    # =========================

    def execute_command(self, code):
        code = code.upper()

        if code == "RE":
            if self.last_real_app:
                restart_app(self.last_real_app)
            return

        command = next(
            (
                item
                for item in self.commands
                if item.get("code", "").upper() == code
            ),
            None,
        )

        if not command:
            return

        result = execute(command)

        if result == "reload":
            self.restart_app()

    def execute_from_input(self):
        text = self.input.text().strip()

        if self.current_pdf:
            pdf_action = next(
                (
                    item
                    for item in PDF_ACTIONS
                    if item.get("code", "").upper() == text.upper()
                ),
                None,
            )

            if pdf_action:
                self.input.blockSignals(True)
                self.input.clear()
                self.input.blockSignals(False)

                self.clear_suggestions()
                self.execute_pdf_action(pdf_action)
                return

        if self.execute_selected_suggestion():
            return

        handle_input_text(self, text)

    def restart_app(self):
        self.save_current_state()
        os.execv(sys.executable, [sys.executable] + sys.argv)

    # =========================
    # GRID RESPONSIVO
    # =========================

    def rebuild_command_grid(self):
        columns = 1 if self.width() < BREAKPOINT_WIDTH else 2

        if columns == self.current_columns:
            return

        self.current_columns = columns

        while self.commands_grid.count():
            item = self.commands_grid.takeAt(0)
            widget = item.widget()

            if widget:
                widget.setParent(None)

        if columns == 1:
            for index, widget in enumerate(self.command_widgets):
                self.commands_grid.addWidget(widget, index, 0)
        else:
            half = (len(self.command_widgets) + 1) // 2

            for index, widget in enumerate(self.command_widgets):
                column = 0 if index < half else 1
                row = index if index < half else index - half

                self.commands_grid.addWidget(widget, row, column)

    def resizeEvent(self, event):
        self.rebuild_command_grid()
        self.render_status()
        self.schedule_state_save()
        super().resizeEvent(event)

    # =========================
    # ESTADO DA JANELA
    # =========================

    def schedule_state_save(self):
        self.save_state_timer.start(500)

    def save_current_state(self):
        geometry = self.geometry()

        save_window_state(
            geometry.x(),
            geometry.y(),
            geometry.width(),
            geometry.height(),
        )

    # =========================
    # MOVER JANELA
    # =========================

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_position = (
                event.globalPosition().toPoint()
                - self.frameGeometry().topLeft()
            )
            event.accept()

    def mouseMoveEvent(self, event):
        if self.drag_position and event.buttons() == Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            self.schedule_state_save()
            event.accept()

    def mouseReleaseEvent(self, event):
        self.drag_position = None

    # =========================
    # ESTILO
    # =========================

    def apply_style(self):
        self.setStyleSheet(APP_STYLE)