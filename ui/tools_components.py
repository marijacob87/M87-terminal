from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QStyle,
    QStyleOptionTab,
    QStylePainter,
    QTabBar,
    QWidget,
)

from core.image_pdf import is_supported_image

YELLOW = "#FFC400"


class ToolsTabBar(QTabBar):
    """Desenha os nomes das abas mantendo o estilo atual da ToolsDialog."""

    def paintEvent(self, event):
        painter = QStylePainter(self)
        for index in range(self.count()):
            option = QStyleOptionTab()
            self.initStyleOption(option, index)
            name = option.text
            option.text = ""
            painter.drawControl(QStyle.CE_TabBarTab, option)

            selected = bool(option.state & QStyle.State_Selected)
            name_font = QFont(self.font())
            name_font.setBold(True)
            painter.setFont(name_font)
            painter.setPen(QColor(YELLOW if selected else "#777777"))
            painter.drawText(option.rect, Qt.AlignCenter, name)


class PdfDropOverlay(QWidget):
    """Camada transparente que mantém o drop de PDFs estável no macOS."""

    pdfDropped = Signal(object)

    def __init__(self, path_reader, parent=None):
        super().__init__(parent)
        self._path_reader = path_reader
        self.setAcceptDrops(True)
        self.setAttribute(Qt.WA_StyledBackground, False)
        self.hide()

    @staticmethod
    def _has_url_candidate(mime_data):
        if not mime_data or not mime_data.hasUrls():
            return False
        return any(
            url.isLocalFile()
            and (
                url.toLocalFile().lower().endswith(".pdf")
                or is_supported_image(url.toLocalFile())
            )
            for url in mime_data.urls()
        )

    def dragEnterEvent(self, event):
        if self._has_url_candidate(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        self.dragEnterEvent(event)

    def dropEvent(self, event):
        paths = self._path_reader(event.mimeData())
        if paths:
            self.pdfDropped.emit(paths)
            event.acceptProposedAction()
        else:
            event.ignore()
        self.hide()

    def dragLeaveEvent(self, event):
        # A troca do widget interno para a camada gera DragLeave no macOS.
        event.accept()
