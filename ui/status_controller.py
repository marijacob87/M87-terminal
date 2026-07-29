import psutil

from PySide6.QtCore import QCoreApplication, QTimer

from core.app_tracker import get_frontmost_app, is_valid_app
from core.config import BREAKPOINT_WIDTH, STATUS_UPDATE_MS, WEATHER_UPDATE_MS
from core.status_worker import StatusWorker


class StatusControllerMixin:
    def start_timers(self):
        psutil.cpu_percent(interval=None)
        self._status_workers = set()
        self._status_worker = None
        self._weather_worker = None
        application = QCoreApplication.instance()
        if application is not None:
            application.aboutToQuit.connect(self.stop_status_workers)

        self.update_weather()

        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self.update_status)
        self.status_timer.start(STATUS_UPDATE_MS)

        self.weather_timer = QTimer(self)
        self.weather_timer.timeout.connect(self.update_weather)
        self.weather_timer.start(WEATHER_UPDATE_MS)

    def update_weather(self):
        self._start_status_worker(update_weather=True)

    def update_status(self):
        self._start_status_worker(update_weather=False)

    def _start_status_worker(self, update_weather):
        attribute = "_weather_worker" if update_weather else "_status_worker"
        current = getattr(self, attribute, None)

        if current is not None and current.isRunning():
            return

        worker = StatusWorker(self.weather_temp, update_weather, self)
        setattr(self, attribute, worker)
        self._status_workers.add(worker)
        worker.completed.connect(self._apply_status_result)
        worker.finished.connect(
            lambda current_worker=worker: self._finish_status_worker(
                current_worker
            )
        )
        worker.start()

    def _apply_status_result(self, status_data, weather_temp):
        if weather_temp:
            self.weather_temp = weather_temp
        if status_data:
            self.status_data = status_data
        self.render_status()

    def _finish_status_worker(self, worker):
        self._status_workers.discard(worker)
        if self._status_worker is worker:
            self._status_worker = None
        if self._weather_worker is worker:
            self._weather_worker = None
        worker.deleteLater()

    def stop_status_workers(self):
        for worker in tuple(self._status_workers):
            if worker.isRunning():
                worker.wait(3500)

    def render_status(self):
        data = self.status_data.get("data", "--/--/----")
        hora = self.status_data.get("hora", "--:--")
        temp = self.status_data.get("temp", "--°C")
        battery = self.status_data.get("battery", "--%")
        ram = self.status_data.get("ram", "--%")
        cpu = self.status_data.get("cpu", "--%")
        networks = self.status_data.get("networks", {})
        network_text = "&nbsp;&nbsp;".join(
            f"<a href='mount:{name}' style='color:#AFAFAF; "
            f"text-decoration:none;'>{name}&nbsp;"
            f"<span style='color:"
            f"{'#70d878' if networks.get(name) else '#ff5f57'}'>●</span></a>"
            for name in ("NAS", "MIM", "PFI")
        )
        network_html = f"<span>{network_text}</span>"
        network_tooltip = (
            "Volumes SMB: NAS, Mimaki e PFI\n"
            "● verde = montado e acessível\n"
            "● vermelho = desmontado ou indisponível\n"
            "Clique numa unidade para montá-la"
        )
        self.status_network.setToolTip(network_tooltip)
        self.status_primary.setToolTip(network_tooltip)

        if self.width() < BREAKPOINT_WIDTH:
            self.status_primary.setText(f"{data}   {hora}   {temp}")
            self.status_secondary.setText(
                f"BAT {battery}   RAM {ram}   CPU {cpu}"
            )
            self.status_secondary.show()
            self.status_network.setText(network_html)
            self.status_network.show()
        else:
            self.status_primary.setText(
                f"<span>{data}&nbsp;&nbsp;&nbsp;{hora}&nbsp;&nbsp;&nbsp;"
                f"{temp}&nbsp;&nbsp;&nbsp;BAT {battery}&nbsp;&nbsp;&nbsp;"
                f"RAM {ram}&nbsp;&nbsp;&nbsp;CPU {cpu}&nbsp;&nbsp;&nbsp;"
                f"{network_text}</span>"
            )
            self.status_primary.setToolTip(network_tooltip)
            self.status_secondary.clear()
            self.status_secondary.hide()
            self.status_network.clear()
            self.status_network.hide()

    def mount_network_from_status(self, link):
        prefix = "mount:"
        if not link.startswith(prefix):
            return

        target = link[len(prefix):].strip().upper()
        if target not in {"NAS", "MIM", "PFI"}:
            return

        self._start_mount_volumes(target)

    def update_last_real_app(self):
        app_name = get_frontmost_app()

        if is_valid_app(app_name):
            self.last_real_app = app_name
