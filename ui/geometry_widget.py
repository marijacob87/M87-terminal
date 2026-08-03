from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

import fitz
from PySide6.QtCore import QPointF, QSettings, QRectF, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QDialog, QFileDialog, QFrame,
    QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMessageBox, QPushButton,
    QRadioButton, QSpinBox, QVBoxLayout, QWidget,
)
from ui.expression_spinbox import ExpressionDoubleSpinBox
from ui.tool_design import (
    TOOL_CARD_MARGINS, TOOL_CARD_SPACING, TOOL_CONTROLS_WIDTH,
    TOOL_STANDARD_QSS, configure_measure_swap, set_tool_role,
)

from core.geometry import (
    BoxSettings, FormatSettings, GeometryDocumentInfo,
    GeometryError, GeometrySettings, apply_geometry, inspect_geometry,
)

YELLOW = "#FFC400"
RED = "#FF4B4B"
ANCHOR_NAMES = (
    "top_left", "top", "top_right",
    "left", "center", "right",
    "bottom_left", "bottom", "bottom_right",
)
FIXED_FORMATS = {
    "A4 · 210 × 297": (210.0, 297.0),
    "A3 · 297 × 420": (297.0, 420.0),
}


def _decimal(value):
    return f"{value:.2f}".replace(".", ",")


def _compact_decimal(value):
    if abs(value - round(value)) < .005:
        return str(round(value))
    return f"{value:.2f}".rstrip("0").rstrip(".").replace(".", ",")


def _spin(value=0.0, minimum=0.0, maximum=10000.0, suffix=" mm"):
    widget = ExpressionDoubleSpinBox()
    widget.setRange(minimum, maximum)
    widget.setDecimals(2)
    widget.setSingleStep(1.0)
    widget.setSuffix(suffix)
    widget.setValue(value)
    return widget


def _field(label, widget):
    layout = QVBoxLayout()
    layout.setSpacing(3)
    caption = QLabel(label)
    caption.setObjectName("geoFieldLabel")
    set_tool_role(caption, "fieldLabel")
    layout.addWidget(caption)
    layout.addWidget(widget)
    return layout


class AnchorSelector(QWidget):
    changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        for index, name in enumerate(ANCHOR_NAMES):
            button = QPushButton()
            button.setObjectName("geoAnchor")
            button.setCheckable(True)
            button.setFixedSize(12, 12)
            button.setToolTip(name.replace("_", " ").title())
            self.group.addButton(button, index)
            layout.addWidget(button, index // 3, index % 3)
        self.setFixedSize(42, 42)
        self.group.idClicked.connect(
            lambda index: self.changed.emit(ANCHOR_NAMES[index])
        )
        self.set_anchor("center")

    def anchor(self):
        index = self.group.checkedId()
        return ANCHOR_NAMES[index] if index >= 0 else "center"

    def set_anchor(self, anchor):
        index = ANCHOR_NAMES.index(anchor) if anchor in ANCHOR_NAMES else 4
        self.group.button(index).setChecked(True)


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
        painter.fillRect(self.rect(), QColor(8, 10, 13))
        if not self.media:
            painter.setPen(QColor(255, 255, 255, 90))
            painter.drawText(
                self.rect(), Qt.AlignCenter,
                "Arraste um PDF para visualizar a geometria",
            )
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
        painter.setPen(QColor(YELLOW))
        painter.drawText(
            QRectF(media_rect.left(), media_rect.top() - 24, media_rect.width(), 18),
            Qt.AlignCenter,
            f"MEDIABOX  {_decimal(self.media.width_mm)} × "
            f"{_decimal(self.media.height_mm)} mm",
        )
        painter.setPen(QColor("#FF6262"))
        painter.drawText(
            QRectF(trim_rect.left(), trim_rect.bottom() + 7, trim_rect.width(), 18),
            Qt.AlignCenter,
            f"TRIMBOX  {_decimal(self.trim.width_mm)} × "
            f"{_decimal(self.trim.height_mm)} mm",
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


class FormatLibraryDialog(QDialog):
    def __init__(self, custom_formats, parent=None):
        super().__init__(parent)
        self.setWindowTitle("M87 • BIBLIOTECA DE FORMATOS")
        self.setModal(True)
        self.setFixedWidth(430)
        self.custom_formats = {
            name: list(dimensions)
            for name, dimensions in custom_formats.items()
        }
        self._editing_name = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        self.formats = QListWidget()
        self.formats.setMinimumHeight(175)
        layout.addWidget(self.formats)

        self.name = QLineEdit()
        self.name.setPlaceholderText("Nome do formato")
        layout.addLayout(_field("NOME", self.name))

        dimensions = QHBoxLayout()
        self.width = _spin(210)
        self.height = _spin(297)
        dimensions.addLayout(_field("LARGURA", self.width))
        dimensions.addLayout(_field("ALTURA", self.height))
        layout.addLayout(dimensions)

        edit_actions = QHBoxLayout()
        new = QPushButton("NOVO")
        self.move_up = QPushButton("↑")
        self.move_down = QPushButton("↓")
        self.delete = QPushButton("APAGAR")
        self.save = QPushButton("SALVAR")
        new.setObjectName("geoSecondary")
        self.move_up.setObjectName("geoSecondary")
        self.move_down.setObjectName("geoSecondary")
        self.delete.setObjectName("geoSecondary")
        self.save.setObjectName("geoInlinePrimary")
        self.move_up.setFixedWidth(32)
        self.move_down.setFixedWidth(32)
        self.move_up.setToolTip("Subir formato")
        self.move_down.setToolTip("Descer formato")
        edit_actions.addWidget(new)
        edit_actions.addWidget(self.move_up)
        edit_actions.addWidget(self.move_down)
        edit_actions.addStretch()
        edit_actions.addWidget(self.delete)
        edit_actions.addWidget(self.save)
        layout.addLayout(edit_actions)

        actions = QHBoxLayout()
        actions.addStretch()
        cancel = QPushButton("CANCELAR")
        cancel.setObjectName("geoSecondary")
        finish = QPushButton("CONCLUIR")
        finish.setObjectName("geoInlinePrimary")
        cancel.setFixedWidth(88)
        finish.setFixedWidth(88)
        actions.addWidget(cancel)
        actions.addWidget(finish)
        layout.addLayout(actions)
        self.formats.currentItemChanged.connect(self._selection_changed)
        new.clicked.connect(self._new_format)
        self.move_up.clicked.connect(lambda: self._move_format(-1))
        self.move_down.clicked.connect(lambda: self._move_format(1))
        self.delete.clicked.connect(self._delete_format)
        self.save.clicked.connect(self._save_format)
        cancel.clicked.connect(self.reject)
        finish.clicked.connect(self.accept)
        self._reload_list()
        self._new_format()

    def _reload_list(self, selected=None):
        self.formats.blockSignals(True)
        self.formats.clear()
        selected_item = None
        for name, dimensions in FIXED_FORMATS.items():
            item = QListWidgetItem(
                f"{name}   ·   {_decimal(dimensions[0])} × "
                f"{_decimal(dimensions[1])} mm   ·   PADRÃO"
            )
            item.setData(Qt.ItemDataRole.UserRole, name)
            item.setData(Qt.ItemDataRole.UserRole + 1, True)
            self.formats.addItem(item)
        for name, dimensions in self.custom_formats.items():
            item = QListWidgetItem(
                f"{name}   ·   {_decimal(float(dimensions[0]))} × "
                f"{_decimal(float(dimensions[1]))} mm"
            )
            item.setData(Qt.ItemDataRole.UserRole, name)
            item.setData(Qt.ItemDataRole.UserRole + 1, False)
            self.formats.addItem(item)
            if name == selected:
                selected_item = item
        if selected_item is not None:
            self.formats.setCurrentItem(selected_item)
        self.formats.blockSignals(False)
        if selected_item is not None:
            self._selection_changed(selected_item, None)

    def _selection_changed(self, current, _previous):
        if current is None:
            return
        name = current.data(Qt.ItemDataRole.UserRole)
        builtin = bool(current.data(Qt.ItemDataRole.UserRole + 1))
        dimensions = FIXED_FORMATS[name] if builtin else self.custom_formats[name]
        self._editing_name = None if builtin else name
        self.name.setText(name)
        self.width.setValue(float(dimensions[0]))
        self.height.setValue(float(dimensions[1]))
        self.name.setEnabled(not builtin)
        self.width.setEnabled(not builtin)
        self.height.setEnabled(not builtin)
        self.save.setEnabled(not builtin)
        self.delete.setEnabled(not builtin)
        custom_names = list(self.custom_formats)
        position = custom_names.index(name) if not builtin else -1
        self.move_up.setEnabled(not builtin and position > 0)
        self.move_down.setEnabled(
            not builtin and position < len(custom_names) - 1
        )

    def _new_format(self):
        self.formats.clearSelection()
        self.formats.setCurrentRow(-1)
        self._editing_name = None
        self.name.clear()
        self.width.setValue(210)
        self.height.setValue(297)
        self.name.setEnabled(True)
        self.width.setEnabled(True)
        self.height.setEnabled(True)
        self.save.setEnabled(True)
        self.delete.setEnabled(False)
        self.move_up.setEnabled(False)
        self.move_down.setEnabled(False)
        self.name.setFocus()

    def _save_format(self):
        name = self.name.text().strip()
        if not name:
            QMessageBox.warning(
                self, "M87 • FORMATOS", "Informe o nome do formato."
            )
            return
        existing_names = set(FIXED_FORMATS) | set(self.custom_formats)
        if name != self._editing_name and name in existing_names:
            QMessageBox.warning(
                self, "M87 • FORMATOS",
                "Já existe um formato com esse nome. Escolha outro nome.",
            )
            return
        if self._editing_name and self._editing_name != name:
            del self.custom_formats[self._editing_name]
        self.custom_formats[name] = [self.width.value(), self.height.value()]
        self._editing_name = name
        self._reload_list(selected=name)

    def _move_format(self, offset):
        if not self._editing_name:
            return
        names = list(self.custom_formats)
        current = names.index(self._editing_name)
        target = current + offset
        if target < 0 or target >= len(names):
            return
        names[current], names[target] = names[target], names[current]
        self.custom_formats = {
            name: self.custom_formats[name]
            for name in names
        }
        self._reload_list(selected=self._editing_name)

    def _delete_format(self):
        if not self._editing_name:
            return
        answer = QMessageBox.question(
            self, "M87 • FORMATOS",
            f"Apagar o formato “{self._editing_name}”?",
            QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        del self.custom_formats[self._editing_name]
        self._reload_list()
        self._new_format()

    def formats_value(self):
        return self.custom_formats


class GeometryWidget(QWidget):
    pdfStateChanged = Signal(list)
    appliedPdfChanged = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("geoPage")
        self.setProperty("toolSurface", True)
        self.setAcceptDrops(True)
        self.settings_store = QSettings("M87Tools", "M87Terminal")
        self.pdf_path = None
        self.current_path = None
        self.info: GeometryDocumentInfo | None = None
        self.current_page = 0
        self._session = None
        self._apply_serial = 0
        self._undo_stack = []
        self._preview_image = QPixmap()
        self._loading = False
        self._changing_format_preset = False
        self._worker = None
        self._pending_pdf_state = None
        self._size_previous_width = 0.0
        self._size_previous_height = 0.0
        self._format_apply_timer = QTimer(self)
        self._format_apply_timer.setSingleShot(True)
        self._format_apply_timer.setInterval(450)
        self._size_apply_timer = QTimer(self)
        self._size_apply_timer.setSingleShot(True)
        self._size_apply_timer.setInterval(450)
        self._operation_buttons = {}
        self._format_quick_buttons = []
        self._build_ui()
        self._connect()
        self._set_enabled(False)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(9)
        body = QHBoxLayout()
        body.setSpacing(12)
        controls = QWidget()
        controls.setObjectName("geoControls")
        set_tool_role(controls, "controls")
        left = QVBoxLayout(controls)
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(7)
        left.addWidget(self._library_card())
        left.addWidget(self._format_card())
        left.addWidget(self._sizes_card())
        left.addWidget(self._cleanup_card())
        left.addStretch()
        controls.setFixedWidth(TOOL_CONTROLS_WIDTH)
        body.addWidget(controls)

        right = QVBoxLayout()
        navigation = QHBoxLayout()
        self.previous_page = QPushButton("‹")
        self.next_page = QPushButton("›")
        self.page_label = QLabel("Nenhum PDF")
        self.page_label.setObjectName("geoPageLabel")
        self.zoom_out_button = QPushButton("−")
        self.zoom_label = QPushButton("100%")
        self.zoom_in_button = QPushButton("+")
        self.rotate_undo_button = QPushButton("↶")
        self.rotate_button = QPushButton("↻ 90°")
        for button in (
            self.zoom_out_button, self.zoom_label, self.zoom_in_button,
            self.rotate_undo_button, self.rotate_button,
        ):
            button.setObjectName("geoZoom")
        self.zoom_out_button.setFixedWidth(28)
        self.zoom_label.setFixedWidth(48)
        self.zoom_in_button.setFixedWidth(28)
        self.rotate_undo_button.setFixedWidth(28)
        self.rotate_button.setFixedWidth(52)
        self.rotate_undo_button.setToolTip("Desfazer a última rotação")
        self.rotate_button.setToolTip("Rotacionar somente esta página em 90°")
        self._operation_buttons["rotation"] = (
            self.rotate_undo_button, self.rotate_button
        )
        navigation.addStretch()
        navigation.addWidget(self.previous_page)
        navigation.addWidget(self.page_label)
        navigation.addWidget(self.next_page)
        navigation.addSpacing(12)
        navigation.addWidget(self.rotate_undo_button)
        navigation.addWidget(self.rotate_button)
        navigation.addSpacing(12)
        navigation.addWidget(self.zoom_out_button)
        navigation.addWidget(self.zoom_label)
        navigation.addWidget(self.zoom_in_button)
        navigation.addStretch()
        right.addLayout(navigation)
        self.preview = GeometryPreview()
        right.addWidget(self.preview, 1)
        self.file_label = QLabel("Arraste um PDF em qualquer área da janela.")
        self.file_label.setObjectName("geoFileLabel")
        self.file_label.setAlignment(Qt.AlignCenter)
        right.addWidget(self.file_label)
        body.addLayout(right, 1)
        root.addLayout(body, 1)
        root.addLayout(self._bottom_bar())
        self._apply_style()

    def _card(self, title):
        card = QFrame()
        card.setObjectName("geoCard")
        set_tool_role(card, "card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(*TOOL_CARD_MARGINS)
        layout.setSpacing(TOOL_CARD_SPACING)
        label = QLabel(title)
        label.setObjectName("geoCardTitle")
        set_tool_role(label, "cardTitle")
        layout.addWidget(label)
        return card, layout

    def _action_row(self, operation, apply_text="APLICAR"):
        row = QHBoxLayout()
        row.addStretch()
        undo = QPushButton("DESFAZER")
        apply = QPushButton(apply_text)
        undo.setObjectName("geoSecondary")
        apply.setObjectName("geoInlinePrimary")
        undo.setFixedWidth(82)
        apply.setFixedWidth(96 if apply_text == "APLICAR" else 132)
        undo.setEnabled(False)
        row.addWidget(undo)
        row.addWidget(apply)
        self._operation_buttons[operation] = (undo, apply)
        return row

    def _library_card(self):
        card, layout = self._card("BIBLIOTECA DE FORMATOS")
        self.add_format = QPushButton("＋  ADICIONAR FORMATO")
        self.add_format.setObjectName("geoInlinePrimary")
        self.add_format.setFixedWidth(160)
        row = QHBoxLayout()
        row.addWidget(self.add_format)
        row.addStretch()
        layout.addLayout(row)
        return card

    def _format_card(self):
        card, layout = self._card("FORMATO TOTAL")
        self.format_preset = QComboBox()
        layout.addWidget(self.format_preset)
        quick = QHBoxLayout()
        quick.addWidget(self._quick_button("A3+4", 301, 424, "format"))
        quick.addWidget(self._quick_button("A5+4", 152, 214, "format"))
        quick.addWidget(self._quick_button("A4+4", 214, 301, "format"))
        quick.addStretch()
        layout.addLayout(quick)
        values = QHBoxLayout()
        self.format_width = _spin(210)
        self.format_height = _spin(297)
        values.addLayout(_field("LARGURA", self.format_width))
        self.swap_format_button = configure_measure_swap(QPushButton())
        values.addWidget(self.swap_format_button, 0, Qt.AlignBottom)
        values.addLayout(_field("ALTURA", self.format_height))
        anchor_column = QVBoxLayout()
        anchor_column.addWidget(self._caption("ÂNCORA"))
        self.format_anchor = AnchorSelector()
        anchor_column.addWidget(self.format_anchor)
        values.addLayout(anchor_column)
        layout.addLayout(values)
        option_row = QHBoxLayout()
        self.allow_distortion = QCheckBox("PERMITIR DISTORÇÃO")
        self.allow_distortion.setObjectName("geoSubtleCheck")
        self.allow_distortion.setChecked(True)
        option_row.addWidget(self.allow_distortion)
        option_row.addStretch()
        layout.addLayout(option_row)
        self.format_preset.addItems(self._preset_names())
        return card

    def _sizes_card(self):
        card, layout = self._card("TAMANHOS")
        target_row = QHBoxLayout()
        self.media_target = QCheckBox("MEDIABOX")
        self.media_target.setObjectName("geoMediaTarget")
        self.trim_target = QCheckBox("TRIMBOX")
        self.trim_target.setObjectName("geoTrimTarget")
        self.size_target_group = QButtonGroup(self)
        self.size_target_group.setExclusive(True)
        self.size_target_group.addButton(self.media_target)
        self.size_target_group.addButton(self.trim_target)
        self.trim_target.setChecked(True)
        target_row.addWidget(self.media_target)
        target_row.addWidget(self.trim_target)
        target_row.addStretch()
        layout.addLayout(target_row)
        self.size_preset = QComboBox()
        self.size_preset.addItems(self._preset_names())
        layout.addWidget(self.size_preset)
        self.media_quick = QWidget()
        media_quick_layout = QHBoxLayout(self.media_quick)
        media_quick_layout.setContentsMargins(0, 0, 0, 0)
        media_quick_layout.addWidget(
            self._quick_button("33×48", 330, 480, "sizes")
        )
        media_quick_layout.addWidget(
            self._quick_button("32×45", 320, 450, "sizes")
        )
        media_quick_layout.addStretch()
        self.media_quick.hide()
        layout.addWidget(self.media_quick)
        self.trim_quick = QWidget()
        trim_quick_layout = QHBoxLayout(self.trim_quick)
        trim_quick_layout.setContentsMargins(0, 0, 0, 0)
        trim_quick_layout.addWidget(
            self._quick_button("A3", 297, 420, "sizes")
        )
        trim_quick_layout.addWidget(
            self._quick_button("A5", 148, 210, "sizes")
        )
        trim_quick_layout.addWidget(
            self._quick_button("A4", 210, 297, "sizes")
        )
        trim_quick_layout.addStretch()
        layout.addWidget(self.trim_quick)
        values = QGridLayout()
        values.setHorizontalSpacing(7)
        values.setVerticalSpacing(5)
        self.size_width = _spin()
        self.size_height = _spin()
        self.size_x = _spin(minimum=-10000)
        self.size_y = _spin(minimum=-10000)
        values.addLayout(_field("LARGURA", self.size_width), 0, 0)
        self.swap_size_button = configure_measure_swap(QPushButton())
        values.addWidget(self.swap_size_button, 0, 1, Qt.AlignBottom)
        values.addLayout(_field("ALTURA", self.size_height), 0, 2)
        values.addLayout(_field("X", self.size_x), 1, 0)
        values.addLayout(_field("Y", self.size_y), 1, 2)
        anchor_column = QVBoxLayout()
        anchor_column.addWidget(self._caption("ÂNCORA"))
        self.size_anchor = AnchorSelector()
        anchor_column.addWidget(self.size_anchor)
        values.addLayout(anchor_column, 0, 3, 2, 1)
        layout.addLayout(values)
        return card

    def _quick_button(self, text, width, height, target):
        button = QPushButton(text)
        button.setObjectName("geoChip")
        set_tool_role(button, "chip")
        button.setFixedHeight(25)
        button.clicked.connect(
            lambda: self._apply_quick_dimensions(width, height, target)
        )
        if target == "format":
            self._format_quick_buttons.append(button)
        return button

    def _cleanup_card(self):
        card, layout = self._card("LIMPEZA")
        cleanup_row = QHBoxLayout()
        cleanup_label = QLabel("REMOVER OBJETOS FORA DO TRIMBOX")
        cleanup_label.setObjectName("geoInlineLabel")
        cleanup_undo = QPushButton("DESFAZER")
        cleanup_apply = QPushButton("LIMPAR")
        cleanup_undo.setObjectName("geoMiniSecondary")
        cleanup_apply.setObjectName("geoMiniPrimary")
        cleanup_undo.setFixedSize(68, 20)
        cleanup_apply.setFixedSize(58, 20)
        cleanup_undo.setEnabled(False)
        cleanup_row.addWidget(cleanup_label)
        cleanup_row.addStretch()
        cleanup_row.addWidget(cleanup_undo)
        cleanup_row.addWidget(cleanup_apply)
        self._operation_buttons["cleanup"] = (cleanup_undo, cleanup_apply)
        layout.addLayout(cleanup_row)
        return card

    def _bottom_bar(self):
        row = QHBoxLayout()
        self.current_radio = QRadioButton("PÁGINA ATUAL")
        self.all_radio = QRadioButton("TODAS")
        self.range_radio = QRadioButton("INTERVALO")
        self.all_radio.setChecked(True)
        self.page_from = QSpinBox()
        self.page_to = QSpinBox()
        self.page_from.setMinimum(1)
        self.page_to.setMinimum(1)
        self.page_from.setEnabled(False)
        self.page_to.setEnabled(False)
        row.addWidget(self.current_radio)
        row.addWidget(self.all_radio)
        row.addWidget(self.range_radio)
        row.addWidget(self.page_from)
        row.addWidget(QLabel("ATÉ"))
        row.addWidget(self.page_to)
        row.addStretch()
        summary = QVBoxLayout()
        summary.setSpacing(4)
        self.summary_label = QLabel("")
        self.summary_label.setObjectName("geoSummary")
        self.summary_label.setAlignment(Qt.AlignRight)
        self.restore_button = QPushButton("RESTAURAR ORIGINAL")
        self.restore_button.setObjectName("geoSecondary")
        self.restore_button.setFixedWidth(135)
        self.save_button = QPushButton("SALVAR COMO…")
        self.save_button.setObjectName("geoPrimary")
        self.save_button.setFixedWidth(145)
        summary.addWidget(self.summary_label)
        summary_buttons = QHBoxLayout()
        summary_buttons.addStretch()
        summary_buttons.addWidget(self.restore_button)
        summary_buttons.addWidget(self.save_button)
        summary.addLayout(summary_buttons)
        row.addLayout(summary)
        return row

    @staticmethod
    def _caption(text):
        label = QLabel(text)
        label.setObjectName("geoFieldLabel")
        return label

    def _connect(self):
        self.previous_page.clicked.connect(lambda: self._change_page(-1))
        self.next_page.clicked.connect(lambda: self._change_page(1))
        self.rotate_button.clicked.connect(self._rotate_current_page)
        self.rotate_undo_button.clicked.connect(lambda: self._undo("rotation"))
        self.swap_format_button.clicked.connect(self._swap_format_dimensions)
        self.swap_size_button.clicked.connect(self._swap_size_dimensions)
        self.zoom_out_button.clicked.connect(self.preview.zoom_out)
        self.zoom_in_button.clicked.connect(self.preview.zoom_in)
        self.zoom_label.clicked.connect(self.preview.reset_zoom)
        self.preview.zoomChanged.connect(
            lambda value: self.zoom_label.setText(f"{value}%")
        )
        self.save_button.clicked.connect(self._save_as)
        self.restore_button.clicked.connect(self._restore_original)
        self.add_format.clicked.connect(self._add_custom_format)
        self.format_preset.currentTextChanged.connect(self._format_preset_changed)
        self.size_preset.currentTextChanged.connect(
            lambda name: self._preset_changed(
                name, self.size_width, self.size_height
            )
        )
        self.range_radio.toggled.connect(self._range_toggled)
        self.media_target.toggled.connect(self._target_changed)
        self.trim_target.toggled.connect(self._target_changed)
        for widget in (
            self.size_x, self.size_y,
        ):
            widget.valueChanged.connect(self._refresh_preview)
        self.format_width.valueChanged.connect(self._format_dimensions_changed)
        self.format_height.valueChanged.connect(self._format_dimensions_changed)
        self.size_width.valueChanged.connect(self._size_width_changed)
        self.size_height.valueChanged.connect(self._size_height_changed)
        self.size_x.valueChanged.connect(self._schedule_size_apply)
        self.size_y.valueChanged.connect(self._schedule_size_apply)
        self.allow_distortion.toggled.connect(self._format_option_changed)
        self.format_anchor.changed.connect(self._format_option_changed)
        self.size_anchor.changed.connect(self._refresh_preview)
        self._operation_buttons["cleanup"][0].clicked.connect(
            lambda: self._undo("cleanup")
        )
        self._operation_buttons["cleanup"][1].clicked.connect(self._apply_cleanup)
        self._format_apply_timer.timeout.connect(self._apply_format)
        self._size_apply_timer.timeout.connect(self._apply_sizes)

    def _set_enabled(self, enabled):
        for widget in (
            self.save_button, self.previous_page, self.next_page,
            self.restore_button,
            self.current_radio, self.all_radio, self.range_radio,
            self.media_target, self.trim_target,
            self.swap_format_button, self.swap_size_button,
        ):
            widget.setEnabled(enabled)
        for undo, apply in self._operation_buttons.values():
            apply.setEnabled(enabled)
            undo.setEnabled(
                enabled and bool(self._undo_stack)
                and self._undo_stack[-1][0] == self._operation_for_button(undo)
            )
        self._range_toggled(self.range_radio.isChecked())

    def _operation_for_button(self, button):
        for operation, (undo, _apply) in self._operation_buttons.items():
            if undo is button:
                return operation
        return ""

    def _apply_style(self):
        self.setStyleSheet("""
            QWidget#geoPage, QWidget#geoControls { background:#080a0d; }
            QFrame#geoCard { background:rgba(255,255,255,.025); border:1px solid rgba(255,255,255,.08); border-radius:7px; }
            QLabel#geoCardTitle { color:#FFC400; font-size:9px; font-weight:700; letter-spacing:.7px; }
            QLabel#geoFieldLabel { color:rgba(255,255,255,.43); font-size:8px; }
            QLabel#geoPageLabel { color:rgba(255,255,255,.82); font-weight:700; min-width:150px; qproperty-alignment:AlignCenter; }
            QLabel#geoFileLabel, QLabel#geoSummary { color:rgba(255,255,255,.43); font-size:9px; }
            QWidget#geoPreview { border:1px solid rgba(255,196,0,.18); border-radius:7px; }
            QPushButton#geoAnchor { border:1px solid rgba(255,255,255,.16); border-radius:3px; background:rgba(255,255,255,.035); padding:0; min-height:0; min-width:0; }
            QPushButton#geoAnchor:checked { background:#FFC400; border-color:#FFC400; }
            QPushButton#geoPrimary, QPushButton#geoInlinePrimary { color:#FFC400; font-weight:700; border:1px solid rgba(255,196,0,.35); background:rgba(255,196,0,.08); }
            QPushButton#geoSecondary { color:rgba(255,255,255,.66); border:1px solid rgba(255,255,255,.12); background:rgba(255,255,255,.04); }
            QPushButton#geoChip, QPushButton#geoZoom {
                color:rgba(255,255,255,.68); border:1px solid rgba(255,255,255,.12);
                background:rgba(255,255,255,.035); padding:0 8px;
            }
            QPushButton#geoChip:hover, QPushButton#geoZoom:hover {
                color:#FFC400; border-color:rgba(255,196,0,.35);
            }
            QPushButton#geoMiniSecondary, QPushButton#geoMiniPrimary {
                font-size:8px; padding:0; min-height:18px;
                border:1px solid rgba(255,255,255,.10);
                background:rgba(255,255,255,.025);
            }
            QPushButton#geoMiniSecondary { color:rgba(255,255,255,.45); }
            QPushButton#geoMiniPrimary {
                color:rgba(255,196,0,.72); border-color:rgba(255,196,0,.22);
            }
            QCheckBox#geoMediaTarget { color:#FFC400; }
            QCheckBox#geoTrimTarget { color:#FF6262; }
            QCheckBox#geoSubtleCheck { color:rgba(255,255,255,.58); font-size:9px; }
            QCheckBox#geoSubtleCheck::indicator { width:13px; height:13px; }
            QLabel#geoInlineLabel { color:rgba(255,255,255,.43); font-size:8px; font-weight:700; }
            QFrame#geoSeparator { background:rgba(255,255,255,.08); border:none; min-height:1px; max-height:1px; }
            QWidget#geoPage QCheckBox, QWidget#geoPage QRadioButton { color:rgba(255,255,255,.78); }
            QWidget#geoPage QLabel { color:rgba(255,255,255,.66); }
            QWidget#geoPage QLineEdit, QWidget#geoPage QComboBox,
            QWidget#geoPage QSpinBox, QWidget#geoPage QDoubleSpinBox,
            QWidget#geoPage QListWidget {
                color:rgba(255,255,255,.88); background:rgba(255,255,255,.07);
                border:1px solid rgba(255,255,255,.08); border-radius:4px;
            }
            QWidget#geoPage QListWidget::item { padding:6px; }
            QWidget#geoPage QListWidget::item:selected {
                color:#FFC400; background:rgba(255,196,0,.10);
            }
            QWidget#geoPage QPushButton { color:rgba(255,255,255,.76); }
            QWidget#geoPage QPushButton#geoPrimary,
            QWidget#geoPage QPushButton#geoInlinePrimary { color:#FFC400; }
            QWidget#geoPage QPushButton#toolMeasureSwap { color:#FFC400; }
            QWidget#geoPage QLabel#geoCardTitle { color:#FFC400; }
            QWidget#geoPage QLabel#geoFieldLabel,
            QWidget#geoPage QLabel#geoFileLabel,
            QWidget#geoPage QLabel#geoSummary { color:rgba(255,255,255,.43); }
            QPushButton, QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox { min-height:20px; }
        """ + TOOL_STANDARD_QSS)

    def set_pdf_state(self, paths):
        paths = list(paths or [])
        if self._worker and self._worker.isRunning():
            # Nunca descarte uma versão nova enquanto uma operação termina.
            # Apenas o pedido mais recente importa para a sincronização.
            self._pending_pdf_state = paths
            return False
        self._pending_pdf_state = None
        if not paths:
            self.clear_pdf()
            return True
        path = Path(paths[0]).expanduser().resolve()
        if path == self.pdf_path:
            return True
        return self.load_pdf(path, ignored=max(0, len(paths) - 1))

    def load_pdf(self, path, ignored=0):
        if self._worker and self._worker.isRunning():
            self._pending_pdf_state = [str(path)]
            return False
        try:
            info = inspect_geometry(path)
        except GeometryError as exc:
            QMessageBox.critical(self, "M87 • GEOMETRIA", str(exc))
            return False
        self.clear_pdf()
        self.pdf_path = Path(path)
        self.current_path = self.pdf_path
        self.info = info
        self.current_page = 0
        self._session = tempfile.TemporaryDirectory(prefix="m87_geometry_")
        suffix = f" · {ignored} PDF(s) ignorado(s)" if ignored else ""
        self.file_label.setText(f"{self.pdf_path.name}{suffix}")
        self.page_from.setRange(1, info.page_count)
        self.page_to.setRange(1, info.page_count)
        self.page_to.setValue(info.page_count)
        self.all_radio.setChecked(True)
        self.trim_target.setChecked(True)
        self._set_enabled(True)
        self._load_page()
        self.pdfStateChanged.emit([str(self.pdf_path)])
        return True

    def clear_pdf(self):
        if self._worker and self._worker.isRunning():
            return
        self._format_apply_timer.stop()
        self._size_apply_timer.stop()
        if self._session is not None:
            self._session.cleanup()
        self._session = None
        self.pdf_path = None
        self.current_path = None
        self.info = None
        self._undo_stack.clear()
        self._apply_serial = 0
        self._preview_image = QPixmap()
        self.current_page = 0
        if hasattr(self, "file_label"):
            self.file_label.setText("Arraste um PDF em qualquer área da janela.")
            self.page_label.setText("Nenhum PDF")
            self.summary_label.clear()
            self.preview.set_boxes(None, None)
            self.preview.reset_zoom()
            self._set_enabled(False)

    def _load_page(self):
        page = self.info.pages[self.current_page]
        self._loading = True
        self.format_width.setValue(page.media.width_mm)
        self.format_height.setValue(page.media.height_mm)
        self._set_size_fields(page.media if self.media_target.isChecked() else page.trim)
        self._select_matching_preset(
            self.format_preset, page.media.width_mm, page.media.height_mm
        )
        selected = page.media if self.media_target.isChecked() else page.trim
        self._select_matching_preset(
            self.size_preset, selected.width_mm, selected.height_mm
        )
        self._loading = False
        self.page_label.setText(
            f"Página {self.current_page + 1} de {self.info.page_count}"
        )
        self.previous_page.setEnabled(self.current_page > 0)
        self.next_page.setEnabled(self.current_page + 1 < self.info.page_count)
        self._update_summary()
        self._render_page_preview()
        self._refresh_preview()

    def _set_size_fields(self, geometry):
        for widget, value in (
            (self.size_x, geometry.x_mm), (self.size_y, geometry.y_mm),
            (self.size_width, geometry.width_mm),
            (self.size_height, geometry.height_mm),
        ):
            widget.blockSignals(True)
            widget.setValue(value)
            widget.blockSignals(False)
        self._size_previous_width = geometry.width_mm
        self._size_previous_height = geometry.height_mm

    @staticmethod
    def _anchor_factors(anchor):
        horizontal = 0 if anchor.endswith("left") or anchor == "left" else (
            1 if anchor.endswith("right") or anchor == "right" else .5
        )
        vertical = 0 if anchor.startswith("top") or anchor == "top" else (
            1 if anchor.startswith("bottom") or anchor == "bottom" else .5
        )
        return horizontal, vertical

    def _size_width_changed(self, value):
        if not self._loading and self._size_previous_width:
            horizontal, _ = self._anchor_factors(self.size_anchor.anchor())
            self.size_x.blockSignals(True)
            self.size_x.setValue(
                self.size_x.value()
                + (self._size_previous_width - value) * horizontal
            )
            self.size_x.blockSignals(False)
        self._size_previous_width = value
        self._recognize_size_preset()
        self._refresh_preview()
        self._schedule_size_apply()

    def _size_height_changed(self, value):
        if not self._loading and self._size_previous_height:
            _, vertical = self._anchor_factors(self.size_anchor.anchor())
            self.size_y.blockSignals(True)
            self.size_y.setValue(
                self.size_y.value()
                + (self._size_previous_height - value) * vertical
            )
            self.size_y.blockSignals(False)
        self._size_previous_height = value
        self._recognize_size_preset()
        self._refresh_preview()
        self._schedule_size_apply()

    def _recognize_size_preset(self):
        if not self._loading:
            self._select_matching_preset(
                self.size_preset,
                self.size_width.value(),
                self.size_height.value(),
            )

    def _schedule_size_apply(self, *_args):
        if not self._loading and self.info and self._worker is None:
            self._size_apply_timer.start()

    def _apply_quick_dimensions(self, width, height, target):
        if target == "format":
            self.format_width.setValue(width)
            self.format_height.setValue(height)
            return
        self.size_width.setValue(width)
        self.size_height.setValue(height)

    def _target_changed(self, _checked):
        self._size_apply_timer.stop()
        if self._loading or not self.info:
            return
        page = self.info.pages[self.current_page]
        if self.media_target.isChecked() and not self.trim_target.isChecked():
            selected = page.media
            self.media_quick.show()
            self.trim_quick.hide()
        elif self.trim_target.isChecked() and not self.media_target.isChecked():
            selected = page.trim
            self.media_quick.hide()
            self.trim_quick.show()
        else:
            return
        self._set_size_fields(selected)
        self._select_matching_preset(
            self.size_preset, selected.width_mm, selected.height_mm
        )
        self._refresh_preview()

    def _swap_size_dimensions(self):
        if self._loading or not self.info or self._worker:
            return
        self._size_apply_timer.stop()
        width = self.size_width.value()
        height = self.size_height.value()
        self._loading = True
        self.size_width.setValue(height)
        self.size_height.setValue(width)
        self._loading = False
        self._size_previous_width = height
        self._size_previous_height = width
        self._recognize_size_preset()
        self._refresh_preview()
        self._schedule_size_apply()

    def _render_page_preview(self):
        self._preview_image = QPixmap()
        if not self.current_path or not Path(self.current_path).exists():
            return
        try:
            with fitz.open(self.current_path) as document:
                page = document[self.current_page]
                try:
                    page.set_cropbox(page.mediabox)
                except Exception:
                    pass
                pixmap = page.get_pixmap(matrix=fitz.Matrix(1.1, 1.1), alpha=False)
                image = QImage(
                    pixmap.samples, pixmap.width, pixmap.height, pixmap.stride,
                    QImage.Format_RGB888,
                ).copy()
                self._preview_image = QPixmap.fromImage(image)
        except Exception:
            self._preview_image = QPixmap()

    def _refresh_preview(self, *_args):
        if self._loading or not self.info:
            return
        page = self.info.pages[self.current_page]
        media, trim = page.media, page.trim
        content = BoxSettings(0, 0, media.width_mm, media.height_mm)
        pending = BoxSettings(
            self.size_x.value(), self.size_y.value(),
            self.size_width.value(), self.size_height.value(),
        )
        if self.media_target.isChecked():
            shift_x = (pending.width_mm - media.width_mm) / 2
            shift_y = (pending.height_mm - media.height_mm) / 2
            content = BoxSettings(
                shift_x, shift_y, media.width_mm, media.height_mm
            )
            media = pending
            if not self.trim_target.isChecked():
                trim = BoxSettings(
                    trim.x_mm + shift_x, trim.y_mm + shift_y,
                    trim.width_mm, trim.height_mm,
                )
        if self.trim_target.isChecked():
            trim = pending
        self.preview.set_boxes(media, trim, self._preview_image, content)

    def _change_page(self, delta):
        target = self.current_page + delta
        if self.info and 0 <= target < self.info.page_count:
            self.current_page = target
            self._load_page()

    def _selected_pages(self):
        if self.all_radio.isChecked():
            return tuple(range(self.info.page_count))
        if self.range_radio.isChecked():
            start, end = self.page_from.value(), self.page_to.value()
            if start > end:
                raise GeometryError("O início do intervalo deve ser menor que o fim.")
            return tuple(range(start - 1, end))
        return (self.current_page,)

    def _apply_format(self):
        self._apply_settings("format", GeometrySettings(format=FormatSettings(
            self.format_width.value(), self.format_height.value(),
            self.format_anchor.anchor(), self.allow_distortion.isChecked(),
        )))

    def _swap_format_dimensions(self):
        if self._loading or not self.info or self._worker:
            return
        self._format_apply_timer.stop()
        width = self.format_width.value()
        height = self.format_height.value()
        self._loading = True
        self.format_width.setValue(height)
        self.format_height.setValue(width)
        self._loading = False
        self._select_matching_preset(
            self.format_preset,
            self.format_width.value(),
            self.format_height.value(),
        )
        self._refresh_preview()
        self._schedule_format_apply()

    def _rotate_current_page(self):
        self._format_apply_timer.stop()
        self._size_apply_timer.stop()
        self._apply_settings(
            "rotation",
            GeometrySettings(rotation_degrees=90),
            pages=(self.current_page,),
        )

    def _apply_sizes(self):
        if not self.media_target.isChecked() and not self.trim_target.isChecked():
            QMessageBox.warning(
                self, "M87 • GEOMETRIA", "Selecione MediaBox ou TrimBox."
            )
            return
        settings = BoxSettings(
            self.size_x.value(), self.size_y.value(),
            self.size_width.value(), self.size_height.value(),
        )
        self._apply_settings("sizes", GeometrySettings(
            media=settings if self.media_target.isChecked() else None,
            trim=settings if self.trim_target.isChecked() else None,
        ))

    def _apply_cleanup(self):
        self._apply_settings(
            "cleanup", GeometrySettings(remove_outside_trim=True)
        )

    def _apply_settings(self, operation, settings, pages=None):
        if not self.current_path or self._worker:
            return
        try:
            pages = tuple(pages) if pages is not None else self._selected_pages()
        except GeometryError as exc:
            QMessageBox.warning(self, "M87 • GEOMETRIA", str(exc))
            return
        root = Path(self._session.name)
        self._apply_serial += 1
        output = root / f"applied_{self._apply_serial}.pdf"
        undo = root / f"undo_{self._apply_serial}.pdf"
        try:
            shutil.copy2(self.current_path, undo)
        except OSError as exc:
            QMessageBox.critical(self, "M87 • GEOMETRIA", str(exc))
            return
        self._set_busy(True)
        if operation == "cleanup":
            self.file_label.setText(f"{self.pdf_path.name} · aplicando limpeza…")
        self._worker = GeometryApplyWorker(
            str(self.current_path), str(output), settings, pages,
            operation, str(undo),
        )
        self._worker.succeeded.connect(self._apply_finished)
        self._worker.failed.connect(self._apply_failed)
        self._worker.finished.connect(self._worker_finished)
        self._worker.start()

    def _apply_finished(self, info, output, operation, undo_path):
        self._undo_stack.append((operation, Path(undo_path)))
        self.current_path = Path(output)
        self.info = info
        self._load_page()
        self.file_label.setText(
            f"{self.pdf_path.name} · alterações aplicadas em memória"
        )
        self.appliedPdfChanged.emit(str(self.current_path))

    def _apply_failed(self, message, _operation, output):
        Path(output).unlink(missing_ok=True)
        QMessageBox.critical(self, "M87 • GEOMETRIA", message)
        if self.pdf_path:
            self.file_label.setText(self.pdf_path.name)

    def _worker_finished(self):
        worker = self._worker
        self._worker = None
        self._set_busy(False)
        if worker:
            worker.deleteLater()
        pending = self._pending_pdf_state
        self._pending_pdf_state = None
        if pending is not None:
            QTimer.singleShot(0, lambda paths=pending: self.set_pdf_state(paths))

    def _set_busy(self, busy):
        for undo, apply in self._operation_buttons.values():
            undo.setEnabled(False)
            apply.setEnabled(not busy and self.info is not None)
        self.save_button.setEnabled(not busy and self.info is not None)
        self.restore_button.setEnabled(not busy and self.info is not None)
        for widget in (
            self.format_preset, self.format_width, self.format_height,
            self.allow_distortion, self.format_anchor,
            self.size_preset, self.size_width, self.size_height,
            self.size_x, self.size_y, self.media_target, self.trim_target,
            self.media_quick, self.trim_quick,
            self.swap_format_button, self.swap_size_button,
        ):
            widget.setEnabled(not busy and self.info is not None)
        for button in self._format_quick_buttons:
            button.setEnabled(not busy and self.info is not None)
        if not busy:
            self._set_enabled(self.info is not None)

    def _undo(self, operation):
        if (
            not self._undo_stack
            or self._undo_stack[-1][0] != operation
            or self._worker
        ):
            return
        _operation, snapshot = self._undo_stack.pop()
        self._apply_serial += 1
        output = Path(self._session.name) / f"applied_{self._apply_serial}.pdf"
        try:
            shutil.copy2(snapshot, output)
            self.info = inspect_geometry(output)
        except (OSError, GeometryError) as exc:
            QMessageBox.critical(self, "M87 • GEOMETRIA", str(exc))
            return
        self.current_path = output
        self._set_enabled(True)
        self._load_page()
        self.file_label.setText(f"{self.pdf_path.name} · alteração desfeita")
        self.appliedPdfChanged.emit(str(self.current_path))

    def undo_last_action(self):
        """Desfaz a última operação aplicada, independentemente do cartão."""
        if self._worker:
            return False
        self._format_apply_timer.stop()
        self._size_apply_timer.stop()
        if not self._undo_stack:
            return False
        operation = self._undo_stack[-1][0]
        self._undo(operation)
        return True

    def _save_as(self):
        if not self.current_path:
            return
        selected, _ = QFileDialog.getSaveFileName(
            self, "Salvar PDF", str(self.pdf_path), "PDF (*.pdf)"
        )
        if not selected:
            return
        destination = Path(selected)
        if destination.suffix.casefold() != ".pdf":
            destination = destination.with_suffix(".pdf")
        temporary = None
        try:
            if destination.resolve() != Path(self.current_path).resolve():
                with tempfile.NamedTemporaryFile(
                    prefix=f".{destination.name}.",
                    suffix=".m87_save_tmp",
                    dir=destination.parent,
                    delete=False,
                ) as handle:
                    temporary = Path(handle.name)
                shutil.copy2(self.current_path, temporary)
                os.replace(temporary, destination)
        except OSError as exc:
            QMessageBox.critical(
                self, "M87 • GEOMETRIA", f"Não foi possível salvar o PDF: {exc}"
            )
            return
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        self.file_label.setText(f"Salvo: {destination.name}")

    def _restore_original(self):
        if not self.pdf_path or self._worker:
            return
        self._format_apply_timer.stop()
        self._size_apply_timer.stop()
        try:
            self.info = inspect_geometry(self.pdf_path)
        except GeometryError as exc:
            QMessageBox.critical(self, "M87 • GEOMETRIA", str(exc))
            return
        self.current_path = self.pdf_path
        self._undo_stack.clear()
        self.current_page = min(self.current_page, self.info.page_count - 1)
        self._set_enabled(True)
        self._load_page()
        self.file_label.setText(f"{self.pdf_path.name} · estado original restaurado")
        self.appliedPdfChanged.emit(str(self.current_path))

    def _update_summary(self):
        if not self.info:
            self.summary_label.clear()
            return
        page = self.info.pages[self.current_page]
        self.summary_label.setText(
            f"Media: {_compact_decimal(page.media.width_mm)}×"
            f"{_compact_decimal(page.media.height_mm)}mm\n"
            f"Trim: {_compact_decimal(page.trim.width_mm)}×"
            f"{_compact_decimal(page.trim.height_mm)}mm\n"
            f"{self.info.page_count} "
            f"{'página' if self.info.page_count == 1 else 'páginas'}"
        )

    def _range_toggled(self, checked):
        enabled = checked and self.info is not None and self._worker is None
        self.page_from.setEnabled(enabled)
        self.page_to.setEnabled(enabled)

    def _custom_formats(self):
        raw = self.settings_store.value("geometry/custom_formats", "{}")
        try:
            values = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            values = {}
        return values if isinstance(values, dict) else {}

    def _preset_names(self):
        return ["PERSONALIZADO", *FIXED_FORMATS, *self._custom_formats()]

    def _add_custom_format(self):
        dialog = FormatLibraryDialog(self._custom_formats(), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        formats = dialog.formats_value()
        self.settings_store.setValue("geometry/custom_formats", json.dumps(formats))
        self._reload_preset_combos()

    def _reload_preset_combos(self):
        current_format = self.format_preset.currentText()
        current_size = self.size_preset.currentText()
        names = self._preset_names()
        for combo, previous in (
            (self.format_preset, current_format),
            (self.size_preset, current_size),
        ):
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(names)
            combo.setCurrentText(
                previous if previous in names else "PERSONALIZADO"
            )
            combo.blockSignals(False)
        self._preset_changed(
            self.format_preset.currentText(),
            self.format_width,
            self.format_height,
        )
        self._preset_changed(
            self.size_preset.currentText(),
            self.size_width,
            self.size_height,
        )
        self._select_matching_preset(
            self.format_preset,
            self.format_width.value(),
            self.format_height.value(),
        )
        self._select_matching_preset(
            self.size_preset,
            self.size_width.value(),
            self.size_height.value(),
        )

    def _preset_changed(self, name, width, height):
        dimensions = FIXED_FORMATS.get(name) or self._custom_formats().get(name)
        if dimensions:
            width.setValue(float(dimensions[0]))
            height.setValue(float(dimensions[1]))

    def _format_preset_changed(self, name):
        if self._changing_format_preset:
            return
        self._changing_format_preset = True
        try:
            self._preset_changed(name, self.format_width, self.format_height)
            index = self.size_preset.findText(name)
            if index >= 0 and self.size_preset.currentIndex() != index:
                self.size_preset.setCurrentIndex(index)
        finally:
            self._changing_format_preset = False
        self._refresh_preview()
        self._schedule_format_apply()

    def _format_dimensions_changed(self, _value):
        if not self._loading and not self._changing_format_preset:
            self._select_matching_preset(
                self.format_preset,
                self.format_width.value(),
                self.format_height.value(),
            )
        self._refresh_preview()
        self._schedule_format_apply()

    def _format_option_changed(self, *_args):
        self._refresh_preview()
        self._schedule_format_apply()

    def _schedule_format_apply(self):
        if not self._loading and self.info and self._worker is None:
            self._format_apply_timer.start()

    def _select_matching_preset(self, combo, width, height):
        formats = {**FIXED_FORMATS, **self._custom_formats()}
        match = "PERSONALIZADO"
        for name, dimensions in formats.items():
            if (
                abs(float(dimensions[0]) - width) < .02
                and abs(float(dimensions[1]) - height) < .02
            ):
                match = name
                break
        combo.blockSignals(True)
        combo.setCurrentText(match)
        combo.blockSignals(False)
