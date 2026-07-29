from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

import fitz
from PySide6.QtCore import QSettings, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFrame,
    QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
    QRadioButton, QSpinBox, QVBoxLayout, QWidget,
)

from core.geometry import (
    BoxSettings, CropMarkSettings, FormatSettings, GeometryDocumentInfo,
    GeometryError, GeometrySettings, apply_geometry, inspect_geometry,
)

YELLOW = "#FFC400"
ANCHOR_NAMES = (
    "top_left", "top", "top_right",
    "left", "center", "right",
    "bottom_left", "bottom", "bottom_right",
)


def _spin(value=0.0, minimum=0.0, maximum=10000.0, suffix=" mm"):
    widget = QDoubleSpinBox()
    widget.setRange(minimum, maximum)
    widget.setDecimals(2)
    widget.setSingleStep(1.0)
    widget.setSuffix(suffix)
    widget.setValue(value)
    return widget


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
        checked = self.group.checkedId()
        return ANCHOR_NAMES[checked] if checked >= 0 else "center"

    def set_anchor(self, anchor):
        index = ANCHOR_NAMES.index(anchor) if anchor in ANCHOR_NAMES else 4
        self.group.button(index).setChecked(True)


class BoxEditor(QFrame):
    changed = Signal()

    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setObjectName("geoSubCard")
        self._previous_width = 0.0
        self._previous_height = 0.0
        layout = QGridLayout(self)
        layout.setContentsMargins(9, 7, 9, 8)
        layout.setHorizontalSpacing(6)
        layout.setVerticalSpacing(3)
        heading = QLabel(title)
        heading.setObjectName("geoSubTitle")
        self.enabled_box = QCheckBox("ALTERAR")
        layout.addWidget(heading, 0, 0, 1, 2)
        layout.addWidget(self.enabled_box, 0, 2, Qt.AlignRight)
        self.x = _spin()
        self.y = _spin()
        self.width = _spin()
        self.height = _spin()
        for index, (label, widget) in enumerate((
            ("X OFFSET", self.x), ("Y OFFSET", self.y),
            ("LARGURA", self.width), ("ALTURA", self.height),
        )):
            box = QVBoxLayout()
            caption = QLabel(label)
            caption.setObjectName("geoFieldLabel")
            box.addWidget(caption)
            box.addWidget(widget)
            layout.addLayout(box, 1 + index // 2, index % 2)
        anchor_label = QLabel("ÂNCORA")
        anchor_label.setObjectName("geoFieldLabel")
        self.anchor = AnchorSelector()
        layout.addWidget(anchor_label, 1, 2, Qt.AlignBottom)
        layout.addWidget(self.anchor, 2, 2, Qt.AlignTop)
        for widget in (self.x, self.y):
            widget.valueChanged.connect(self._value_changed)
        self.width.valueChanged.connect(self._width_changed)
        self.height.valueChanged.connect(self._height_changed)
        self.anchor.changed.connect(self._anchor_changed)
        self.enabled_box.toggled.connect(lambda _value: self.changed.emit())

    @staticmethod
    def _factors(anchor):
        horizontal = 0 if anchor.endswith("left") or anchor == "left" else (
            1 if anchor.endswith("right") or anchor == "right" else .5
        )
        vertical = 0 if anchor.startswith("top") or anchor == "top" else (
            1 if anchor.startswith("bottom") or anchor == "bottom" else .5
        )
        return horizontal, vertical

    def _width_changed(self, value):
        self.enabled_box.setChecked(True)
        if self._previous_width:
            horizontal, _ = self._factors(self.anchor.anchor())
            self.x.blockSignals(True)
            self.x.setValue(self.x.value() + (self._previous_width - value) * horizontal)
            self.x.blockSignals(False)
        self._previous_width = value
        self.changed.emit()

    def _height_changed(self, value):
        self.enabled_box.setChecked(True)
        if self._previous_height:
            _, vertical = self._factors(self.anchor.anchor())
            self.y.blockSignals(True)
            self.y.setValue(self.y.value() + (self._previous_height - value) * vertical)
            self.y.blockSignals(False)
        self._previous_height = value
        self.changed.emit()

    def _value_changed(self, _value):
        self.enabled_box.setChecked(True)
        self.changed.emit()

    def _anchor_changed(self, _value):
        self.enabled_box.setChecked(True)
        self.changed.emit()

    def set_geometry(self, geometry):
        for widget in (self.x, self.y, self.width, self.height):
            widget.blockSignals(True)
        self.x.setValue(geometry.x_mm)
        self.y.setValue(geometry.y_mm)
        self.width.setValue(geometry.width_mm)
        self.height.setValue(geometry.height_mm)
        self._previous_width = geometry.width_mm
        self._previous_height = geometry.height_mm
        self.enabled_box.setChecked(False)
        for widget in (self.x, self.y, self.width, self.height):
            widget.blockSignals(False)

    def settings(self):
        return BoxSettings(
            self.x.value(), self.y.value(), self.width.value(), self.height.value()
        )

    def applied_settings(self):
        return self.settings() if self.enabled_box.isChecked() else None


class GeometryPreview(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("geoPreview")
        self.setMinimumSize(390, 390)
        self.media = None
        self.trim = None
        self.content = None
        self.page_image = QPixmap()

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
        margin = 62.0
        area = QRectF(self.rect()).adjusted(margin, margin, -margin, -margin)
        scale = min(
            area.width() / max(self.media.width_mm, 1),
            area.height() / max(self.media.height_mm, 1),
        )
        width = self.media.width_mm * scale
        height = self.media.height_mm * scale
        media_rect = QRectF(
            area.center().x() - width / 2,
            area.center().y() - height / 2,
            width, height,
        )
        painter.setBrush(QColor(235, 235, 230))
        painter.setPen(Qt.NoPen)
        painter.drawRect(media_rect)
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
        painter.setPen(QPen(QColor("#FF4B4B"), 1.5, Qt.DashLine))
        painter.drawRect(trim_rect)
        painter.setPen(QColor(YELLOW))
        painter.drawText(
            QRectF(media_rect.left(), media_rect.top() - 24, media_rect.width(), 18),
            Qt.AlignCenter,
            f"MEDIABOX  {self.media.width_mm:.2f} × {self.media.height_mm:.2f} mm",
        )
        painter.setPen(QColor("#FF6262"))
        painter.drawText(
            QRectF(trim_rect.left(), trim_rect.bottom() + 7, trim_rect.width(), 18),
            Qt.AlignCenter,
            f"TRIMBOX  {self.trim.width_mm:.2f} × {self.trim.height_mm:.2f} mm",
        )


class GeometryWidget(QWidget):
    pdfStateChanged = Signal(list)
    appliedPdfChanged = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("geoPage")
        self.setAcceptDrops(True)
        self.settings_store = QSettings("M87Tools", "M87Terminal")
        self.pdf_path = None
        self.current_path = None
        self.info: GeometryDocumentInfo | None = None
        self.current_page = 0
        self._session = None
        self._undo_path = None
        self._apply_serial = 0
        self._preview_image = QPixmap()
        self._loading = False
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
        left = QVBoxLayout(controls)
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(6)
        left.addWidget(self._format_card())
        self.media_editor = BoxEditor("MEDIABOX · FOLHA TOTAL")
        self.trim_editor = BoxEditor("TRIMBOX · CORTE FINAL")
        left.addWidget(self.media_editor)
        left.addWidget(self.trim_editor)
        left.addWidget(self._cleanup_card())
        left.addWidget(self._marks_card())
        left.addStretch()
        controls.setMinimumWidth(410)
        controls.setMaximumWidth(450)
        body.addWidget(controls, 0)

        right = QVBoxLayout()
        navigation = QHBoxLayout()
        self.previous_page = QPushButton("‹")
        self.next_page = QPushButton("›")
        self.page_label = QLabel("Nenhum PDF")
        self.page_label.setObjectName("geoPageLabel")
        navigation.addStretch()
        navigation.addWidget(self.previous_page)
        navigation.addWidget(self.page_label)
        navigation.addWidget(self.next_page)
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
        layout = QVBoxLayout(card)
        layout.setContentsMargins(11, 9, 11, 10)
        layout.setSpacing(7)
        label = QLabel(title)
        label.setObjectName("geoCardTitle")
        layout.addWidget(label)
        return card, layout

    def _format_card(self):
        card, layout = self._card("FORMATO · REDIMENSIONA PÁGINA E CONTEÚDO")
        preset_row = QHBoxLayout()
        self.format_preset = QComboBox()
        self.format_preset.addItems(["PERSONALIZADO", "A4 · 210 × 297", "A3 · 297 × 420"])
        self.format_name = QLineEdit()
        self.format_name.setPlaceholderText("Nome do formato")
        self.save_format = QPushButton("SALVAR")
        self.delete_format = QPushButton("EXCLUIR")
        preset_row.addWidget(self.format_preset, 2)
        preset_row.addWidget(self.format_name, 2)
        preset_row.addWidget(self.save_format)
        preset_row.addWidget(self.delete_format)
        layout.addLayout(preset_row)
        dimensions = QHBoxLayout()
        self.apply_format_button = QPushButton("APLICAR FORMATO")
        self.apply_format_button.setObjectName("geoInlinePrimary")
        self.format_width = _spin(210)
        self.format_height = _spin(297)
        dimensions.addWidget(self.apply_format_button)
        dimensions.addStretch()
        dimensions.addWidget(QLabel("L"))
        dimensions.addWidget(self.format_width)
        dimensions.addWidget(QLabel("A"))
        dimensions.addWidget(self.format_height)
        layout.addLayout(dimensions)
        options = QHBoxLayout()
        self.allow_distortion = QCheckBox("PERMITIR DISTORÇÃO")
        self.format_anchor = AnchorSelector()
        options.addWidget(self.allow_distortion)
        options.addStretch()
        options.addWidget(QLabel("ÂNCORA"))
        options.addWidget(self.format_anchor)
        layout.addLayout(options)
        self._load_formats()
        return card

    def _cleanup_card(self):
        card, layout = self._card("LIMPEZA")
        self.remove_outside = QCheckBox(
            "REMOVER OBJETOS TOTALMENTE FORA DA TRIMBOX"
        )
        layout.addWidget(self.remove_outside)
        note = QLabel("Objetos que tocam ou atravessam a TrimBox são mantidos.")
        note.setObjectName("geoHint")
        layout.addWidget(note)
        return card

    def _marks_card(self):
        card, layout = self._card("MARCAS DE CORTE")
        self.marks_enabled = QCheckBox("ADICIONAR MARCAS")
        layout.addWidget(self.marks_enabled)
        values = QHBoxLayout()
        self.mark_offset = _spin(3)
        self.mark_length = _spin(5)
        self.mark_thickness = _spin(.25, .01, 10, " pt")
        for label, widget in (
            ("OFFSET", self.mark_offset),
            ("COMPRIMENTO", self.mark_length),
            ("ESPESSURA", self.mark_thickness),
        ):
            column = QVBoxLayout()
            caption = QLabel(label)
            caption.setObjectName("geoFieldLabel")
            column.addWidget(caption)
            column.addWidget(widget)
            values.addLayout(column)
        layout.addLayout(values)
        self.expand_media = QCheckBox(
            "AUMENTAR MEDIABOX AUTOMATICAMENTE QUANDO NECESSÁRIO"
        )
        layout.addWidget(self.expand_media)
        black = QLabel("COR · 100% BLACK")
        black.setObjectName("geoHint")
        layout.addWidget(black)
        return card

    def _bottom_bar(self):
        row = QHBoxLayout()
        self.current_radio = QRadioButton("PÁGINA ATUAL")
        self.all_radio = QRadioButton("TODAS")
        self.range_radio = QRadioButton("INTERVALO")
        self.current_radio.setChecked(True)
        self.page_from = QSpinBox()
        self.page_to = QSpinBox()
        self.page_from.setMinimum(1)
        self.page_to.setMinimum(1)
        row.addWidget(self.current_radio)
        row.addWidget(self.all_radio)
        row.addWidget(self.range_radio)
        row.addWidget(self.page_from)
        row.addWidget(QLabel("ATÉ"))
        row.addWidget(self.page_to)
        row.addStretch()
        self.undo_button = QPushButton("DESFAZER")
        self.apply_button = QPushButton("APLICAR")
        self.save_button = QPushButton("SALVAR COMO…")
        self.undo_button.setObjectName("geoPrimary")
        self.apply_button.setObjectName("geoPrimary")
        self.save_button.setObjectName("geoPrimary")
        row.addWidget(self.undo_button)
        row.addWidget(self.apply_button)
        row.addWidget(self.save_button)
        return row

    def _connect(self):
        self.previous_page.clicked.connect(lambda: self._change_page(-1))
        self.next_page.clicked.connect(lambda: self._change_page(1))
        self.apply_button.clicked.connect(self._apply)
        self.undo_button.clicked.connect(self._undo)
        self.save_button.clicked.connect(self._save_as)
        self.save_format.clicked.connect(self._save_custom_format)
        self.delete_format.clicked.connect(self._delete_custom_format)
        self.format_preset.currentTextChanged.connect(self._preset_changed)
        self.range_radio.toggled.connect(self._range_toggled)
        for widget in (
            self.format_width, self.format_height,
            self.allow_distortion,
            self.media_editor, self.trim_editor,
        ):
            signal = (
                widget.changed if hasattr(widget, "changed")
                else widget.valueChanged if hasattr(widget, "valueChanged")
                else widget.toggled
            )
            signal.connect(self._refresh_preview)
        self.format_anchor.changed.connect(self._refresh_preview)
        self.apply_format_button.clicked.connect(self._apply_format)

    def _set_enabled(self, enabled):
        for widget in (
            self.apply_button, self.apply_format_button, self.save_button, self.previous_page,
            self.next_page, self.current_radio, self.all_radio,
            self.range_radio, self.page_from, self.page_to,
        ):
            widget.setEnabled(enabled)
        self.undo_button.setEnabled(enabled and self._undo_path is not None)

    def _apply_style(self):
        self.setStyleSheet("""
            QWidget#geoPage, QWidget#geoControls { background:#080a0d; }
            QFrame#geoCard, QFrame#geoSubCard { background:rgba(255,255,255,.025); border:1px solid rgba(255,255,255,.08); border-radius:7px; }
            QLabel#geoCardTitle, QLabel#geoSubTitle { color:#FFC400; font-size:9px; font-weight:700; letter-spacing:.7px; }
            QLabel#geoFieldLabel, QLabel#geoHint { color:rgba(255,255,255,.43); font-size:8px; }
            QLabel#geoPageLabel { color:rgba(255,255,255,.82); font-weight:700; min-width:150px; qproperty-alignment:AlignCenter; }
            QLabel#geoFileLabel { color:rgba(255,255,255,.48); }
            QWidget#geoPreview { border:1px solid rgba(255,196,0,.18); border-radius:7px; }
            QPushButton#geoAnchor { border:1px solid rgba(255,255,255,.16); border-radius:3px; background:rgba(255,255,255,.035); padding:0; }
            QPushButton#geoAnchor:checked { background:#FFC400; border-color:#FFC400; }
            QPushButton#geoPrimary { min-width:125px; color:#FFC400; font-weight:700; border-color:rgba(255,196,0,.38); background:rgba(255,196,0,.10); }
            QPushButton#geoInlinePrimary { color:#FFC400; font-weight:700; border:1px solid rgba(255,196,0,.35); background:rgba(255,196,0,.08); padding:2px 12px; }
            QWidget#geoPage QCheckBox, QWidget#geoPage QRadioButton { color:rgba(255,255,255,.78); }
            QWidget#geoPage QLabel { color:rgba(255,255,255,.66); }
            QWidget#geoPage QLineEdit, QWidget#geoPage QComboBox,
            QWidget#geoPage QSpinBox, QWidget#geoPage QDoubleSpinBox {
                color:rgba(255,255,255,.88);
                background:rgba(255,255,255,.07);
                border:1px solid rgba(255,255,255,.08);
                border-radius:4px;
            }
            QWidget#geoPage QPushButton { color:rgba(255,255,255,.76); }
            QWidget#geoPage QPushButton#geoPrimary,
            QWidget#geoPage QPushButton#geoInlinePrimary { color:#FFC400; }
            QWidget#geoPage QLabel#geoCardTitle,
            QWidget#geoPage QLabel#geoSubTitle { color:#FFC400; }
            QWidget#geoPage QLabel#geoFieldLabel,
            QWidget#geoPage QLabel#geoHint,
            QWidget#geoPage QLabel#geoFileLabel { color:rgba(255,255,255,.43); }
            QPushButton, QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox { min-height:20px; }
            QPushButton#geoAnchor { min-height:0; min-width:0; }
        """)

    def set_pdf_state(self, paths):
        paths = list(paths or [])
        if not paths:
            self.clear_pdf()
            return
        path = Path(paths[0]).expanduser().resolve()
        if path == self.pdf_path:
            return
        self.load_pdf(path, ignored=max(0, len(paths) - 1))

    def load_pdf(self, path, ignored=0):
        try:
            info = inspect_geometry(path)
        except GeometryError as exc:
            QMessageBox.critical(self, "M87 • GEOMETRIA", str(exc))
            return
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
        self._set_enabled(True)
        self._load_page()
        self.pdfStateChanged.emit([str(self.pdf_path)])

    def clear_pdf(self):
        if self._session is not None:
            self._session.cleanup()
        self._session = None
        self.pdf_path = None
        self.current_path = None
        self.info = None
        self._undo_path = None
        self._apply_serial = 0
        self._preview_image = QPixmap()
        self.current_page = 0
        if hasattr(self, "file_label"):
            self.file_label.setText("Arraste um PDF em qualquer área da janela.")
            self.page_label.setText("Nenhum PDF")
            self.preview.set_boxes(None, None)
            self._set_enabled(False)

    def _load_page(self):
        page = self.info.pages[self.current_page]
        self._loading = True
        self.media_editor.set_geometry(page.media)
        self.trim_editor.set_geometry(page.trim)
        self.format_width.setValue(page.media.width_mm)
        self.format_height.setValue(page.media.height_mm)
        self._loading = False
        self.page_label.setText(
            f"Página {self.current_page + 1} de {self.info.page_count}"
        )
        self.previous_page.setEnabled(self.current_page > 0)
        self.next_page.setEnabled(self.current_page + 1 < self.info.page_count)
        self._render_page_preview()
        self._refresh_preview()

    def _render_page_preview(self):
        self._preview_image = QPixmap()
        if not self.current_path or not Path(self.current_path).exists():
            return
        try:
            document = fitz.open(self.current_path)
            page = document[self.current_page]
            try:
                page.set_cropbox(page.mediabox)
            except Exception:
                pass
            matrix = fitz.Matrix(1.15, 1.15)
            pixmap = page.get_pixmap(matrix=matrix, alpha=False)
            image = QImage(
                pixmap.samples, pixmap.width, pixmap.height, pixmap.stride,
                QImage.Format_RGB888,
            ).copy()
            self._preview_image = QPixmap.fromImage(image)
            document.close()
        except Exception:
            self._preview_image = QPixmap()

    def _refresh_preview(self, *_args):
        if self._loading or not self.info:
            return
        media = self.media_editor.settings()
        trim = self.trim_editor.settings()
        source_media = self.info.pages[self.current_page].media
        content = BoxSettings(0, 0, source_media.width_mm, source_media.height_mm)
        if self.media_editor.enabled_box.isChecked():
            shift_x = (media.width_mm - source_media.width_mm) / 2.0
            shift_y = (media.height_mm - source_media.height_mm) / 2.0
            content = BoxSettings(
                shift_x, shift_y, source_media.width_mm, source_media.height_mm
            )
            if not self.trim_editor.enabled_box.isChecked():
                trim = BoxSettings(
                    trim.x_mm + shift_x,
                    trim.y_mm + shift_y,
                    trim.width_mm,
                    trim.height_mm,
                )
        if not self.media_editor.enabled_box.isChecked():
            old_width = max(media.width_mm, .01)
            old_height = max(media.height_mm, .01)
            new_width = self.format_width.value()
            new_height = self.format_height.value()
            sx, sy = new_width / old_width, new_height / old_height
            if not self.allow_distortion.isChecked():
                sx = sy = min(sx, sy)
            horizontal, vertical = BoxEditor._factors(self.format_anchor.anchor())
            gap_x = new_width - old_width * sx
            gap_y = new_height - old_height * sy
            media = BoxSettings(0, 0, new_width, new_height)
            content = BoxSettings(
                gap_x * horizontal, gap_y * vertical,
                old_width * sx, old_height * sy,
            )
            if not self.trim_editor.enabled_box.isChecked():
                trim = BoxSettings(
                    trim.x_mm * sx + gap_x * horizontal,
                    trim.y_mm * sy + gap_y * vertical,
                    trim.width_mm * sx,
                    trim.height_mm * sy,
                )
        self.preview.set_boxes(media, trim, self._preview_image, content)

    def _change_page(self, delta):
        target = self.current_page + delta
        if self.info and 0 <= target < self.info.page_count:
            self.current_page = target
            self._load_page()

    def _selected_pages(self):
        if self.all_radio.isChecked():
            return range(self.info.page_count)
        if self.range_radio.isChecked():
            start, end = self.page_from.value(), self.page_to.value()
            if start > end:
                raise GeometryError("O início do intervalo deve ser menor que o fim.")
            return range(start - 1, end)
        return [self.current_page]

    def _geometry_settings(self):
        return GeometrySettings(
            media=self.media_editor.applied_settings(),
            trim=self.trim_editor.applied_settings(),
            remove_outside_trim=self.remove_outside.isChecked(),
            crop_marks=CropMarkSettings(
                enabled=self.marks_enabled.isChecked(),
                offset_mm=self.mark_offset.value(),
                length_mm=self.mark_length.value(),
                thickness_pt=self.mark_thickness.value(),
                auto_expand_media=self.expand_media.isChecked(),
            ),
        )

    def _format_settings(self):
        return GeometrySettings(format=FormatSettings(
            self.format_width.value(),
            self.format_height.value(),
            self.format_anchor.anchor(),
            self.allow_distortion.isChecked(),
        ))

    def _apply_format(self):
        self._apply_settings(self._format_settings())

    def _apply(self):
        self._apply_settings(self._geometry_settings())

    def _apply_settings(self, settings):
        if not self.current_path:
            return
        root = Path(self._session.name)
        undo = root / "undo.pdf"
        self._apply_serial += 1
        output = root / f"applied_{self._apply_serial}.pdf"
        try:
            shutil.copy2(self.current_path, undo)
            info = apply_geometry(
                self.current_path, output,
                settings, self._selected_pages(),
            )
        except GeometryError as exc:
            if output != self.current_path:
                output.unlink(missing_ok=True)
            QMessageBox.critical(self, "M87 • GEOMETRIA", str(exc))
            return
        self._undo_path = undo
        self.current_path = output
        self.info = info
        self._set_enabled(True)
        self._load_page()
        self.file_label.setText(f"{self.pdf_path.name} · alterações aplicadas em memória")
        self.appliedPdfChanged.emit(str(self.current_path))

    def _undo(self):
        if not self._undo_path or not self._undo_path.exists():
            return
        self._apply_serial += 1
        output = Path(self._session.name) / f"applied_{self._apply_serial}.pdf"
        shutil.copy2(self._undo_path, output)
        self.current_path = output
        self.info = inspect_geometry(output)
        self._undo_path = None
        self._set_enabled(True)
        self._load_page()
        self.file_label.setText(f"{self.pdf_path.name} · última aplicação desfeita")
        self.appliedPdfChanged.emit(str(self.current_path))

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
        try:
            if destination.resolve() == self.pdf_path.resolve():
                QMessageBox.warning(
                    self, "M87 • GEOMETRIA",
                    "Escolha outro nome para preservar o PDF original.",
                )
                return
            shutil.copy2(self.current_path, destination)
        except OSError as exc:
            QMessageBox.critical(
                self, "M87 • GEOMETRIA", f"Não foi possível salvar o PDF: {exc}"
            )
            return
        self.file_label.setText(f"Salvo: {destination.name}")

    def _range_toggled(self, checked):
        self.page_from.setEnabled(checked and self.info is not None)
        self.page_to.setEnabled(checked and self.info is not None)

    def _custom_formats(self):
        raw = self.settings_store.value("geometry/custom_formats", "{}")
        try:
            values = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            values = {}
        return values if isinstance(values, dict) else {}

    def _load_formats(self):
        if not hasattr(self, "format_preset"):
            return
        for name in self._custom_formats():
            self.format_preset.addItem(name)

    def _save_custom_format(self):
        name = self.format_name.text().strip()
        if not name:
            QMessageBox.warning(self, "M87 • GEOMETRIA", "Informe o nome do formato.")
            return
        formats = self._custom_formats()
        formats[name] = [self.format_width.value(), self.format_height.value()]
        self.settings_store.setValue("geometry/custom_formats", json.dumps(formats))
        if self.format_preset.findText(name) < 0:
            self.format_preset.addItem(name)
        self.format_preset.setCurrentText(name)

    def _delete_custom_format(self):
        name = self.format_preset.currentText()
        formats = self._custom_formats()
        if name not in formats:
            return
        del formats[name]
        self.settings_store.setValue("geometry/custom_formats", json.dumps(formats))
        index = self.format_preset.findText(name)
        if index >= 0:
            self.format_preset.removeItem(index)

    def _preset_changed(self, name):
        fixed = {
            "A4 · 210 × 297": (210, 297),
            "A3 · 297 × 420": (297, 420),
        }
        dimensions = fixed.get(name) or self._custom_formats().get(name)
        if dimensions:
            self.format_width.setValue(float(dimensions[0]))
            self.format_height.setValue(float(dimensions[1]))
