from PySide6.QtCore import QThread, Signal

from core.geometry import apply_geometry


class GeometryApplyWorker(QThread):
    succeeded = Signal(object, str, str, str)
    failed = Signal(str, str, str)

    def __init__(self, source, output, settings, pages, operation, undo_path):
        super().__init__()
        self.source = source
        self.output = output
        self.settings = settings
        self.pages = pages
        self.operation = operation
        self.undo_path = undo_path

    def run(self):
        try:
            info = apply_geometry(
                self.source, self.output, self.settings, self.pages
            )
        except Exception as exc:
            self.failed.emit(str(exc), self.operation, self.output)
            return
        self.succeeded.emit(
            info, self.output, self.operation, self.undo_path
        )

