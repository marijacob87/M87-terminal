from __future__ import annotations

import ctypes

from AppKit import NSEvent, NSEventMaskKeyDown
from PySide6.QtCore import QObject, Signal


F19_KEY_CODE = 80
_CARBON_PATH = "/System/Library/Frameworks/Carbon.framework/Carbon"


def _four_char_code(value: bytes) -> int:
    return int.from_bytes(value, "big")


class _EventTypeSpec(ctypes.Structure):
    _fields_ = (("event_class", ctypes.c_uint32), ("event_kind", ctypes.c_uint32))


class _EventHotKeyID(ctypes.Structure):
    _fields_ = (("signature", ctypes.c_uint32), ("identifier", ctypes.c_uint32))


class GlobalF19Hotkey(QObject):
    """Encaminha a F19 global para a thread principal do Qt."""

    activated = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._monitor = None
        self._handler = self._handle_event
        self._carbon = None
        self._carbon_callback = None
        self._carbon_handler_ref = ctypes.c_void_p()
        self._carbon_hotkey_ref = ctypes.c_void_p()

    def start(self) -> bool:
        if self._carbon_hotkey_ref.value or self._monitor is not None:
            return True
        if self._start_carbon_hotkey():
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

    def _start_carbon_hotkey(self) -> bool:
        """Registra F19 no sistema sem exigir Monitoramento de Entrada."""
        try:
            carbon = ctypes.cdll.LoadLibrary(_CARBON_PATH)
            callback_type = ctypes.CFUNCTYPE(
                ctypes.c_int32,
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.c_void_p,
            )

            def pressed(_next_handler, _event, _user_data):
                self.activated.emit()
                return 0

            callback = callback_type(pressed)
            event_type = _EventTypeSpec(_four_char_code(b"keyb"), 5)

            carbon.GetApplicationEventTarget.restype = ctypes.c_void_p
            target = carbon.GetApplicationEventTarget()
            carbon.InstallEventHandler.argtypes = (
                ctypes.c_void_p,
                callback_type,
                ctypes.c_uint32,
                ctypes.POINTER(_EventTypeSpec),
                ctypes.c_void_p,
                ctypes.POINTER(ctypes.c_void_p),
            )
            carbon.InstallEventHandler.restype = ctypes.c_int32
            status = carbon.InstallEventHandler(
                target,
                callback,
                1,
                ctypes.byref(event_type),
                None,
                ctypes.byref(self._carbon_handler_ref),
            )
            if status != 0:
                return False

            carbon.RegisterEventHotKey.argtypes = (
                ctypes.c_uint32,
                ctypes.c_uint32,
                _EventHotKeyID,
                ctypes.c_void_p,
                ctypes.c_uint32,
                ctypes.POINTER(ctypes.c_void_p),
            )
            carbon.RegisterEventHotKey.restype = ctypes.c_int32
            status = carbon.RegisterEventHotKey(
                F19_KEY_CODE,
                0,
                _EventHotKeyID(_four_char_code(b"M87F"), 19),
                target,
                0,
                ctypes.byref(self._carbon_hotkey_ref),
            )
            if status != 0:
                carbon.RemoveEventHandler(self._carbon_handler_ref)
                self._carbon_handler_ref = ctypes.c_void_p()
                return False

            self._carbon = carbon
            self._carbon_callback = callback
            return True
        except Exception as error:
            print(f"[ATALHO F19] Registro nativo indisponível: {error}")
            self._carbon = None
            self._carbon_callback = None
            self._carbon_handler_ref = ctypes.c_void_p()
            self._carbon_hotkey_ref = ctypes.c_void_p()
            return False

    def stop(self):
        if self._carbon is not None:
            try:
                if self._carbon_hotkey_ref.value:
                    self._carbon.UnregisterEventHotKey(self._carbon_hotkey_ref)
                if self._carbon_handler_ref.value:
                    self._carbon.RemoveEventHandler(self._carbon_handler_ref)
            except Exception:
                pass
            self._carbon = None
            self._carbon_callback = None
            self._carbon_handler_ref = ctypes.c_void_p()
            self._carbon_hotkey_ref = ctypes.c_void_p()
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
