from PySide6.QtCore import QThread, Signal

from core.whatsapp_download import (
    download_whatsapp_files,
    list_active_whatsapp_chats,
)


class WhatsAppChatsWorker(QThread):
    progress = Signal(str)
    completed = Signal(list)
    failed = Signal(str)

    def run(self):
        try:
            chats = list_active_whatsapp_chats(progress=self.progress.emit)
        except Exception as error:
            self.failed.emit(str(error))
            return

        self.completed.emit(chats)


class WhatsAppDownloadWorker(QThread):
    progress = Signal(str)
    completed = Signal(int, str)
    failed = Signal(str)

    def __init__(self, request, parent=None):
        super().__init__(parent)
        self.request = request

    def run(self):
        try:
            count, directory = download_whatsapp_files(
                self.request,
                progress=self.progress.emit,
            )
        except Exception as error:
            self.failed.emit(str(error))
            return

        self.completed.emit(count, str(directory))
