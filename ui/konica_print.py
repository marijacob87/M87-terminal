from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QMessageBox

from core.konica_spool import KonicaSpoolError, send_pdf_to_hold
from ui.tool_design import show_button_success


class KonicaSpoolWorker(QThread):
    completed = Signal(str)
    failed = Signal(str)

    def __init__(self, pdf_path, parent=None):
        super().__init__(parent)
        self.pdf_path = Path(pdf_path)

    def run(self):
        try:
            destination = send_pdf_to_hold(self.pdf_path)
        except KonicaSpoolError as exc:
            self.failed.emit(str(exc))
            return
        self.completed.emit(destination.name)


def spool_pdf(owner, pdf_path, *, button=None, cleanup=None):
    if getattr(owner, "_konica_spool_worker", None):
        return
    worker = KonicaSpoolWorker(pdf_path, owner)
    owner._konica_spool_worker = worker
    if button is not None:
        button.setEnabled(False)
        button.setText("ENVIANDO…")

    def finish():
        if button is not None:
            button.setText("IMPRIMIR")
            button.setEnabled(True)
        owner._konica_spool_worker = None
        worker.deleteLater()
        if cleanup is not None:
            cleanup()

    def completed(filename):
        finish()
        show_button_success(button, restore_text="IMPRIMIR")
        status = getattr(owner, "status", None)
        if status is not None and hasattr(status, "setText"):
            status.setText(f"✓ Enviado para Hold: {filename}")

    def failed(message):
        QMessageBox.critical(owner, "M87 • KONICA", message)
        finish()

    worker.completed.connect(completed)
    worker.failed.connect(failed)
    worker.start()
    return worker
