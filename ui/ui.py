import json
import threading

from AppKit import (
    NSApplication,
    NSApplicationActivateAllWindows,
    NSApplicationActivateIgnoringOtherApps,
    NSRunningApplication,
)
from PySide6.QtCore import QSettings, Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox

from core.config import APP_MIN_HEIGHT, COMMANDS_FILE
from core.global_hotkey import GlobalF19Hotkey
from core.styles import APP_STYLE
from ui.command_controller import CommandControllerMixin
from ui.focus_behavior import SelectSpinBoxTextOnTab
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
    client_search_finished = Signal(int, object)

    def __init__(self):
        super().__init__()

        self.commands = self.load_commands()
        self.rows = {}
        self.command_widgets = []
        self.drag_position = None
        self.current_columns = None

        self.current_pdf = None
        self.current_pdf_info = None

        self.weather_temp = "--°C"
        self.status_data = {}
        self.last_real_app = None
        self._client_search_request = 0
        self.client_search_finished.connect(self._finish_client_subfolder_search)

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
        self._finder_sync_lock = threading.Lock()

        self.setup_window()
        self.build_ui()
        self._settings_shortcut = QShortcut(QKeySequence("Ctrl+,"), self)
        self._settings_shortcut.activated.connect(self.open_settings)
        self._f19_local_shortcut = QShortcut(QKeySequence("F19"), self)
        self._f19_local_shortcut.setContext(Qt.ApplicationShortcut)
        self._f19_local_shortcut.activated.connect(self.activate_terminal_input)
        self._f19_hotkey = GlobalF19Hotkey(self)
        self._f19_hotkey.activated.connect(self.activate_terminal_input)
        self._f19_hotkey.start()
        QApplication.instance().aboutToQuit.connect(self._f19_hotkey.stop)
        self._spinbox_focus_filter = SelectSpinBoxTextOnTab(self)
        QApplication.instance().installEventFilter(self._spinbox_focus_filter)
        self.apply_style()
        self.rebuild_command_grid()
        self.start_timers()
        self.clear_suggestions()
        threading.Thread(
            target=self._warm_client_search_cache,
            name="m87-client-search-cache",
            daemon=True,
        ).start()
        # A janela das ferramentas concentra vários widgets de PDF. Criá-la
        # durante o drop fazia o usuário esperar pela montagem da interface
        # antes de ver a primeira página. Preparamos uma única instância
        # oculta depois da inicialização e a reutilizamos em todos os comandos.
        QTimer.singleShot(1500, self._warm_tools_dialog)

    def activate_terminal_input(self):
        if self.isMinimized():
            self.showNormal()
        elif not self.isVisible():
            self.show()

        options = (
            NSApplicationActivateAllWindows
            | NSApplicationActivateIgnoringOtherApps
        )
        NSRunningApplication.currentApplication().activateWithOptions_(options)
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        self.raise_()
        self.activateWindow()
        self.input.setFocus()


    @staticmethod
    def _warm_client_search_cache():
        try:
            from core.client_search import warm_client_search_cache
            warm_client_search_cache()
        except Exception as error:
            print(f"[CLIENTES] Não foi possível criar o índice: {error}")

    def _warm_tools_dialog(self):
        """Prepara silenciosamente a janela compartilhada das ferramentas."""
        try:
            from shiboken6 import isValid
            from ui.tools_dialog import ToolsDialog

            dialog = getattr(self, "tools_dialog", None)
            if dialog is not None and isValid(dialog):
                return
            self.tools_dialog = ToolsDialog(
                self,
                initial_tab="RES",
                show_on_create=False,
            )
        except Exception as error:
            # O aquecimento é apenas uma otimização. Se falhar, o fluxo normal
        # recria a janela no primeiro comando sem comprometer o Terminal.
            print(f"[FERRAMENTAS] Não foi possível preparar a janela: {error}")

    def start_client_subfolder_search(self, query):
        from core.client_search import search_client_subfolders

        self._client_search_request += 1
        request_id = self._client_search_request
        self.session_result_label.setText("Buscando pasta do cliente…")
        self.session_result_label.show()
        QTimer.singleShot(0, self.ajustar_altura_ao_conteudo)

        def search():
            results = search_client_subfolders(query)
            self.client_search_finished.emit(request_id, results)

        threading.Thread(
            target=search,
            name="m87-client-subfolder-search",
            daemon=True,
        ).start()

    def _finish_client_subfolder_search(self, request_id, results):
        if request_id != self._client_search_request:
            return

        self.clear_session_result()

        if results:
            from core.client_search import open_path
            open_path(results[0])
            return

        self.input.setPlaceholderText("pasta do cliente não encontrada")
        QTimer.singleShot(1200, lambda: self.input.setPlaceholderText(""))

    def sync_recent_finder_folders(self):
        if not self._finder_sync_lock.acquire(blocking=False):
            return

        def sync():
            try:
                from core.recent_folders import sync_finder_history
                sync_finder_history()
            except Exception as error:
                print(f"[FINDER] Não foi possível atualizar o histórico: {error}")
            finally:
                self._finder_sync_lock.release()

        threading.Thread(
            target=sync,
            name="m87-finder-history",
            daemon=True,
        ).start()

    def load_commands(self):
        with open(COMMANDS_FILE, "r", encoding="utf-8") as file:
            commands = json.load(file)
        from core.command_preferences import order_commands

        saved_order = QSettings("M87Tools", "M87Terminal").value(
            "terminal/command_order", []
        )
        return order_commands(commands, saved_order)

    def apply_style(self):
        self.setStyleSheet(APP_STYLE)

    def closeEvent(self, event):
        settings = QSettings("M87Tools", "M87Terminal")
        if (
            not getattr(self, "_force_close", False)
            and settings.value("general/confirm_close", True, type=bool)
        ):
            answer = QMessageBox.question(
                self,
                "M87 Terminal",
                "Deseja fechar o M87 Terminal?",
                QMessageBox.Cancel | QMessageBox.Yes,
                QMessageBox.Cancel,
            )
            if answer != QMessageBox.Yes:
                event.ignore()
                return
        super().closeEvent(event)
