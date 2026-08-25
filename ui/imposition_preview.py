from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap, QTransform
from PySide6.QtWidgets import QWidget

from core.imposition import LayoutOption
from ui.tool_design import TOOL_BACKGROUND


YELLOW = "#FFC400"


class PreviewWidget(QWidget):
    zoomChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("impPreview")
        self.setMinimumSize(420, 420)
        self.paper_w = 480.0
        self.paper_h = 330.0
        self.layout_option: LayoutOption | None = None
        self.gutter = 5.0
        self.page_count = 0
        self.mode = "repeat"
        self.fill_order = "rows"
        self.thumbnails: list[QPixmap] = []
        self.crop_marks = True
        self.crop_mark_offset = 3.0
        self.crop_mark_length = 5.0
        self.crop_mark_thickness = .25
        self.sheet_index = 0
        self.bleed_left = 0.0
        self.bleed_top = 0.0
        self.bleed_right = 0.0
        self.bleed_bottom = 0.0
        self.identify_sheets = False
        self.sheet_legend = ""
        self.total_sheets = 0
        self.page_assignments: list[int | None] | None = None
        self.page_rotations: list[int] | None = None
        self.page_visibility: list[bool] | None = None
        self._zoom = 1.0
        self._pan = QPointF()
        self._drag_origin = None

    def set_state(
        self,
        *,
        paper_w,
        paper_h,
        option,
        gutter,
        page_count,
        mode,
        fill_order,
        thumbnails,
        crop_marks,
        sheet_index,
        bleed_left=0.0,
        bleed_top=0.0,
        bleed_right=0.0,
        bleed_bottom=0.0,
        identify_sheets=False,
        sheet_legend="",
        total_sheets=0,
        crop_mark_offset=3.0,
        crop_mark_length=5.0,
        crop_mark_thickness=.25,
        page_assignments=None,
        page_rotations=None,
        page_visibility=None,
    ):
        self.paper_w = paper_w
        self.paper_h = paper_h
        self.layout_option = option
        self.gutter = gutter
        self.page_count = page_count
        self.mode = mode
        self.fill_order = fill_order
        self.thumbnails = thumbnails
        self.crop_marks = crop_marks
        self.sheet_index = sheet_index
        self.bleed_left = bleed_left
        self.bleed_top = bleed_top
        self.bleed_right = bleed_right
        self.bleed_bottom = bleed_bottom
        self.identify_sheets = identify_sheets
        self.sheet_legend = sheet_legend
        self.total_sheets = total_sheets
        self.crop_mark_offset = crop_mark_offset
        self.crop_mark_length = crop_mark_length
        self.crop_mark_thickness = crop_mark_thickness
        self.page_assignments = page_assignments
        self.page_rotations = page_rotations
        self.page_visibility = page_visibility
        self.update()

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

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(TOOL_BACKGROUND))
        if not self.layout_option:
            painter.setPen(QColor(255, 255, 255, 95))
            painter.drawText(self.rect(), Qt.AlignCenter, "Arraste um PDF para visualizar")
            return

        margin = 28.0
        area = self.rect().adjusted(int(margin), int(margin), -int(margin), -int(margin))
        scale = min(
            area.width() / self.paper_w, area.height() / self.paper_h
        ) * self._zoom
        paper_w_px, paper_h_px = self.paper_w * scale, self.paper_h * scale
        origin_x = area.center().x() - paper_w_px / 2 + self._pan.x()
        origin_y = area.center().y() - paper_h_px / 2 + self._pan.y()
        paper = QRectF(origin_x, origin_y, paper_w_px, paper_h_px)
        painter.setPen(QPen(QColor(255, 255, 255, 170), 1))
        painter.setBrush(QColor(245, 245, 242))
        painter.drawRect(paper)

        option = self.layout_option
        positions: list[tuple[int, int]] = []
        if self.fill_order == "columns":
            for col in range(option.columns):
                for row in range(option.rows):
                    positions.append((row, col))
        else:
            for row in range(option.rows):
                for col in range(option.columns):
                    positions.append((row, col))

        for slot, (row, col) in enumerate(positions):
            if self.page_assignments is not None:
                source_index = self.page_assignments[slot]
            elif self.mode == "repeat":
                source_index = self.sheet_index
            else:
                source_index = self.sheet_index * option.total + slot
                if source_index >= self.page_count:
                    break

            x = origin_x + (option.start_x_mm + col * (option.item_width_mm + self.gutter)) * scale
            y = origin_y + (option.start_y_mm + row * (option.item_height_mm + self.gutter)) * scale
            rect = QRectF(x, y, option.item_width_mm * scale, option.item_height_mm * scale)
            if option.rotated:
                bleed_left = self.bleed_bottom
                bleed_top = self.bleed_left
                bleed_right = self.bleed_top
                bleed_bottom = self.bleed_right
            else:
                bleed_left = self.bleed_left
                bleed_top = self.bleed_top
                bleed_right = self.bleed_right
                bleed_bottom = self.bleed_bottom
            bleed_rect = QRectF(
                rect.left() - bleed_left * scale,
                rect.top() - bleed_top * scale,
                rect.width() + (bleed_left + bleed_right) * scale,
                rect.height() + (bleed_top + bleed_bottom) * scale,
            )
            artwork_visible = (
                self.page_visibility is None
                or slot >= len(self.page_visibility)
                or self.page_visibility[slot]
            )
            pixmap = (
                self.thumbnails[source_index]
                if artwork_visible and source_index is not None and source_index < len(self.thumbnails)
                else None
            )
            if pixmap and not pixmap.isNull():
                rotation = 90 if option.rotated else 0
                if self.page_rotations is not None and slot < len(self.page_rotations):
                    rotation += self.page_rotations[slot]
                transformed = pixmap.transformed(QTransform().rotate(rotation)) if rotation else pixmap
                painter.drawPixmap(bleed_rect.toRect(), transformed)
            elif source_index is None or not artwork_visible:
                painter.fillRect(rect, QColor(255, 255, 255))
            else:
                painter.fillRect(bleed_rect, QColor(220, 220, 215))

            show_empty_manual_badge = (
                self.page_assignments is not None and self.page_visibility is not None
            )
            show_numbered_badge = (
                source_index is not None
                and (self.mode == "sequential" or self.page_assignments is not None)
            )
            if show_numbered_badge or show_empty_manual_badge:
                invalid_page = source_index is not None and source_index >= self.page_count
                hidden_artwork = source_index is not None and not artwork_visible
                painter.setBrush(
                    QColor(145, 30, 30, 220) if invalid_page else QColor(0, 0, 0, 150)
                )
                painter.setPen(
                    QPen(QColor(YELLOW), 1.4)
                    if hidden_artwork and not invalid_page
                    else QPen(QColor(255, 255, 255, 150), 0.8)
                )
                badge = QRectF(rect.left() + 3, rect.top() + 3, 30, 17)
                painter.drawRoundedRect(badge, 3, 3)
                painter.setPen(QColor(255, 255, 255))
                if source_index is not None:
                    painter.drawText(badge, Qt.AlignCenter, str(source_index + 1))

            if self.page_visibility is not None:
                painter.setBrush(Qt.NoBrush)
                painter.setPen(QPen(QColor(175, 175, 170), 0.8))
                painter.drawRect(rect)

        if self.crop_marks:
            self._draw_outer_marks(painter, option, scale, origin_x, origin_y)

        if self.identify_sheets and self.sheet_legend.strip():
            self._draw_sheet_label(painter, paper, scale)


    def _draw_sheet_label(self, painter, paper, scale):
        label = " ".join(self.sheet_legend.split())
        painter.save()
        font = QFont("Helvetica")
        # O mínimo legível também acompanha o zoom para que a legenda preserve
        # a mesma proporção visual em relação à folha.
        font.setPixelSize(max(1, round(max(6.0 * self._zoom, 2.47 * scale))))
        painter.setFont(font)
        painter.setPen(QColor(0, 0, 0))
        right = paper.right() - 50.0 * scale
        top = paper.top() + 5.0 * scale
        height = max(3.2 * scale, painter.fontMetrics().height())
        rect = QRectF(paper.left() + 3.0 * scale, top,
                      max(1.0, right - (paper.left() + 3.0 * scale)), height)
        painter.drawText(rect, Qt.AlignRight | Qt.AlignTop, label)
        painter.restore()

    def _draw_outer_marks(self, painter, option, scale, origin_x, origin_y):
        length = self.crop_mark_length * scale
        distance = self.crop_mark_offset * scale
        painter.setPen(
            QPen(
                QColor(0, 0, 0),
                max(0.55, self.crop_mark_thickness * scale / 2.83465),
            )
        )

        left = origin_x + option.start_x_mm * scale
        top = origin_y + option.start_y_mm * scale
        right = origin_x + (option.start_x_mm + option.occupied_width_mm) * scale
        bottom = origin_y + (option.start_y_mm + option.occupied_height_mm) * scale

        x_boundaries = set()
        for col in range(option.columns):
            x0 = origin_x + (option.start_x_mm + col * (option.item_width_mm + self.gutter)) * scale
            x_boundaries.add(round(x0, 3))
            x_boundaries.add(round(x0 + option.item_width_mm * scale, 3))
        for x in sorted(x_boundaries):
            painter.drawLine(int(x), int(top - distance - length), int(x), int(top - distance))
            painter.drawLine(int(x), int(bottom + distance), int(x), int(bottom + distance + length))

        y_boundaries = set()
        for row in range(option.rows):
            y0 = origin_y + (option.start_y_mm + row * (option.item_height_mm + self.gutter)) * scale
            y_boundaries.add(round(y0, 3))
            y_boundaries.add(round(y0 + option.item_height_mm * scale, 3))
        for y in sorted(y_boundaries):
            painter.drawLine(int(left - distance - length), int(y), int(left - distance), int(y))
            painter.drawLine(int(right + distance), int(y), int(right + distance + length), int(y))

