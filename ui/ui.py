import json

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QMainWindow

from core.config import APP_MIN_HEIGHT, COMMANDS_FILE
from core.styles import APP_STYLE
from ui.command_controller import CommandControllerMixin
from ui.pdf_context import PdfContextMixin
from ui.status_controller import StatusControllerMixin
from ui.window_behavior import WindowBehaviorMixin
from ui.window_ui import WindowUiMixin


class M87Term(
    PdfContextMixin,
    CommandControllerMixin,
    StatusControllerMixin,
    WindowBehaviorMixin,
    WindowUiMixin,
    QMainWindow,
):
    def __init__(self):
        super().__init__()

        self.commands = self.load_commands()
        self.rows = {}
        self.command_widgets = []
        self.drag_position = None
        self.current_columns = None

        self.current_pdf = None
        self.current_pdf_info = None
        self.current_update = None

        self.weather_temp = "--°C"
        self.status_data = {}
        self.last_real_app = None

        self.normal_height = APP_MIN_HEIGHT
        self.auto_resizing = False

        self.save_state_timer = QTimer(self)
        self.save_state_timer.setSingleShot(True)
        self.save_state_timer.timeout.connect(self.save_current_state)

        self.app_tracker_timer = QTimer(self)
        self.app_tracker_timer.timeout.connect(self.update_last_real_app)
        self.app_tracker_timer.start(1000)

        self.finder_folder_timer = QTimer(self)
        self.finder_folder_timer.timeout.connect(self.sync_recent_finder_folders)
        self.finder_folder_timer.start(2500)

        self.setup_window()
        self.build_ui()
        self.apply_style()
        self.rebuild_command_grid()
        self.start_timers()
        self.clear_suggestions()


    def sync_recent_finder_folders(self):
        try:
            from core.recent_folders import sync_finder_history
            sync_finder_history()
        except Exception:
            pass

    def load_commands(self):
        with open(COMMANDS_FILE, "r", encoding="utf-8") as file:
            return json.load(file)

    def apply_style(self):
        self.setStyleSheet(APP_STYLE)
