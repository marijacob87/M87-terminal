from __future__ import annotations

from AppKit import NSEvent, NSEventMaskKeyDown
from PySide6.QtCore import QObject, Signal

F19_KEY_CODE = 80


class GlobalF19Hotkey(QObject):
    """Observa a F19 fora do aplicativo e entrega a ativação à thread do Qt."""

    activated = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._monitor = None
        self._handler = self._handle_event

    def start(self) -> bool:
        if self._monitor is not None:
            return True
        try:
            self._monitor = NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
                NSEventMaskKeyDown,
                self._handler,
            )
        except Exception as error:
            print(f"[ATALHO F19] Não foi possível iniciar: {error}")
            self._monitor = None
        return self._monitor is not None

    def stop(self):
        if self._monitor is None:
            return
        try:
            NSEvent.removeMonitor_(self._monitor)
        except Exception:
            pass
        self._monitor = None

    def _handle_event(self, event):
        try:
            if int(event.keyCode()) == F19_KEY_CODE and not event.isARepeat():
                self.activated.emit()
        except Exception:
            return
