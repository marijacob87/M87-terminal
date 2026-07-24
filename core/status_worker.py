from PySide6.QtCore import QThread, Signal

from core.status import get_porto_temp, get_status_data


class StatusWorker(QThread):
    completed = Signal(dict, str)

    def __init__(self, weather_temp: str, update_weather: bool, parent=None):
        super().__init__(parent)
        self.weather_temp = weather_temp
        self.update_weather = update_weather

    def run(self):
        weather_temp = (
            get_porto_temp()
            if self.update_weather
            else self.weather_temp
        )

        try:
            status_data = get_status_data(weather_temp)
        except Exception as error:
            print(f"[STATUS] Não foi possível atualizar o estado: {error}")
            status_data = {}

        self.completed.emit(status_data, weather_temp)
