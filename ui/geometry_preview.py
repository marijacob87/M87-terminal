from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QWidget

from ui.tool_design import TOOL_BACKGROUND, draw_empty_pdf_message


YELLOW = "#FFC400"
RED = "#FF4B4B"


def _decimal(value):
    return f"{value:.2f}".replace(".", ",")


def _scaled_font(font, delta):
    scaled = QFont(font)
    if font.pointSizeF() > 0:
        scaled.setPointSizeF(max(1, font.pointSizeF() + delta))
    elif font.pixelSize() > 0:
        scaled.setPixelSize(max(1, font.pixelSize() + round(delta)))
    return scaled


class GeometryPreview(QWidget):
    zoomChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("geoPreview")
        self.setMinimumSize(430, 390)
        self.media = None
        self.trim = None
        self.content = None
        self.page_image = QPixmap()
        self._zoom = 1.0
        self._pan = QPointF()
        self._drag_origin = None

    def set_boxes(self, media, trim, page_image=None, content=None):
        self.media = media
        self.trim = trim
        self.content = content
        if page_image is not None:
            self.page_image = page_image
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(TOOL_BACKGROUND))
        if not self.media:
            draw_empty_pdf_message(painter, self.rect())
            return
        area = QRectF(self.rect()).adjusted(55, 55, -55, -55)
        scale = min(
            area.width() / max(self.media.width_mm, 1),
            area.height() / max(self.media.height_mm, 1),
        ) * self._zoom
        media_rect = QRectF(
            area.center().x() - self.media.width_mm * scale / 2 + self._pan.x(),
            area.center().y() - self.media.height_mm * scale / 2 + self._pan.y(),
            self.media.width_mm * scale,
            self.media.height_mm * scale,
        )
        painter.fillRect(media_rect, QColor(235, 235, 230))
        if not self.page_image.isNull():
            content = self.content or self.media
            content_rect = QRectF(
                media_rect.left() + content.x_mm * scale,
                media_rect.top() + content.y_mm * scale,
                content.width_mm * scale,
                content.height_mm * scale,
            )
            painter.drawPixmap(content_rect.toRect(), self.page_image)
        trim_rect = QRectF(
            media_rect.left() + self.trim.x_mm * scale,
            media_rect.top() + self.trim.y_mm * scale,
            self.trim.width_mm * scale,
            self.trim.height_mm * scale,
        )
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor(YELLOW), 1.4, Qt.DashLine))
        painter.drawRect(media_rect)
        painter.setPen(QPen(QColor(RED), 1.5, Qt.DashLine))
        painter.drawRect(trim_rect)
        base_font = painter.font()
        painter.setFont(_scaled_font(base_font, 1))
        painter.setPen(QColor("#FF6262"))
        painter.drawText(
            QRectF(media_rect.left(), media_rect.top() - 24, media_rect.width(), 18),
            Qt.AlignCenter,
            f"TRIMBOX  {_decimal(self.trim.width_mm)} × "
            f"{_decimal(self.trim.height_mm)} mm",
        )
        painter.setFont(_scaled_font(base_font, -1))
        painter.setPen(QColor(YELLOW))
        painter.drawText(
            QRectF(media_rect.left(), media_rect.bottom() + 15, media_rect.width(), 18),
            Qt.AlignCenter,
            f"MEDIABOX  {_decimal(self.media.width_mm)} × "
            f"{_decimal(self.media.height_mm)} mm",
        )

    def set_zoom(self, zoom):
        self._zoom = min(4.0, max(.5, zoom))
        if self._zoom <= 1.0:
            self._pan = QPointF()
        self.zoomChanged.emit(round(self._zoom * 100))
        self.update()

    def zoom_in(self):
        self.set_zoom(self._zoom + .25)

    def zoom_out(self):
        self.set_zoom(self._zoom - .25)

    def reset_zoom(self):
        self._pan = QPointF()
        self.set_zoom(1.0)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._zoom > 1.0:
            self._drag_origin = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_origin is not None:
            self._pan += event.position() - self._drag_origin
            self._drag_origin = event.position()
            self.update()
            event.accept()

    def mouseReleaseEvent(self, event):
        if self._drag_origin is not None:
            self._drag_origin = None
            self.unsetCursor()
            event.accept()

