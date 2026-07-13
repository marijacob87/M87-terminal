import psutil

from PySide6.QtCore import QTimer

from core.app_tracker import get_frontmost_app, is_valid_app
from core.config import BREAKPOINT_WIDTH, STATUS_UPDATE_MS, WEATHER_UPDATE_MS
from core.status import get_porto_temp, get_status_data


class StatusControllerMixin:
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

    def update_last_real_app(self):
        app_name = get_frontmost_app()

        if is_valid_app(app_name):
            self.last_real_app = app_name
