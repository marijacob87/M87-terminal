from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

import fitz
from PySide6.QtCore import QSettings, Qt, QTimer, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFrame,
    QGridLayout, QHBoxLayout, QLabel,
    QMessageBox, QPushButton,
    QRadioButton, QSpinBox, QVBoxLayout, QWidget,
)
from ui.expression_spinbox import ExpressionDoubleSpinBox
from ui.geometry_controls import AnchorSelector
from ui.geometry_preview import GeometryPreview
from ui.geometry_workers import GeometryApplyWorker
from ui.tool_design import (
    TOOL_BACKGROUND, TOOL_BUTTON_HEIGHT, TOOL_CARD_MARGINS, TOOL_CARD_SPACING,
    TOOL_COLUMN_SPACING, TOOL_CONTROLS_WIDTH, TOOL_FIELD_HEIGHT,
    TOOL_STANDARD_QSS, ToolActionBar, ToolPreviewToolbar,
    configure_measure_swap,
    create_pdf_file_card, set_open_pdf_loaded,
    apply_terminal_accent, draw_empty_pdf_message, format_pdf_file_summary,
    set_document_control_enabled, set_tool_role,
)
from ui.konica_print import spool_pdf

from core.geometry import (
    BoxSettings, FormatSettings, GeometryDocumentInfo,
    GeometryError, GeometrySettings, inspect_geometry,
)
from core.preferences import save_path

FIXED_FORMATS = {
    "A5 · 148 × 210": (148.0, 210.0),
    "A4 · 210 × 297": (210.0, 297.0),
    "A3 · 297 × 420": (297.0, 420.0),
    "A5+4 · 152 × 214": (152.0, 214.0),
    "A4+4 · 214 × 301": (214.0, 301.0),
    "A3+4 · 301 × 424": (301.0, 424.0),
}


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
        self._pending_operation_pages = ()
        self._format_apply_timer = QTimer(self)
        self._format_apply_timer.setSingleShot(True)
        self._format_apply_timer.setInterval(450)
        self._size_apply_timer = QTimer(self)
        self._size_apply_timer.setSingleShot(True)
        self._size_apply_timer.setInterval(450)
        self._operation_buttons = {}
        self._format_quick_buttons = []
        self._build_ui()
        apply_terminal_accent(self)
        self._connect()
        self._set_enabled(False)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(9)
        body = QHBoxLayout()
        body.setSpacing(TOOL_COLUMN_SPACING)
        controls = QWidget()
        controls.setObjectName("geoControls")
        set_tool_role(controls, "controls")
        left = QVBoxLayout(controls)
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(7)
        file_card, self.open_button, self.file_label = create_pdf_file_card(
            self._choose_pdf
        )
        left.addWidget(file_card)
        format_card = self._format_card()
        sizes_card = self._sizes_card()
        cleanup_card = self._cleanup_card()
        self._document_cards = (format_card, sizes_card, cleanup_card)
        for card in self._document_cards:
            left.addWidget(card)
        left.addStretch()
        controls.setFixedWidth(TOOL_CONTROLS_WIDTH)
        body.addWidget(controls)

        right = QVBoxLayout()
        self.preview_toolbar = ToolPreviewToolbar()
        self.previous_page = self.preview_toolbar.previous_button
        self.next_page = self.preview_toolbar.next_button
        self.page_label = self.preview_toolbar.page_label
        self.zoom_out_button = self.preview_toolbar.zoom_out_button
        self.zoom_label = self.preview_toolbar.zoom_label
        self.zoom_in_button = self.preview_toolbar.zoom_in_button
        self.rotate_undo_button = self.preview_toolbar.rotation_undo_button
        self.rotate_button = self.preview_toolbar.rotate_button
        self.rotate_undo_button.setToolTip("Desfazer a última rotação")
        self.rotate_button.setToolTip("Rotacionar somente esta página em 90°")
        self._operation_buttons["rotation"] = (
            self.rotate_undo_button, self.rotate_button
        )
        right.addWidget(self.preview_toolbar)
        self.preview = GeometryPreview()
        right.addWidget(self.preview, 1)
        body.addLayout(right, 1)
        root.addLayout(body, 1)
        root.addLayout(self._bottom_bar())
        self.action_bar = ToolActionBar(
            restore=self._restore_original,
            print_file=self._print_current,
            save_as=self._save_as,
        )
        self.restore_button = self.action_bar.restore_button
        self.print_button = self.action_bar.print_button
        self.save_button = self.action_bar.save_button
        root.addLayout(self.action_bar)
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

    def _format_card(self):
        card, layout = self._card("FORMATO")
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
        card, layout = self._card("TRIMBOX")
        self.size_preset = QComboBox()
        self.size_preset.addItems(self._preset_names())
        layout.addWidget(self.size_preset)
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
        self.range_to_label = QLabel("ATÉ")
        row.addWidget(self.range_to_label)
        row.addWidget(self.page_to)
        row.addStretch()
        self.summary_label = QLabel("")
        self.summary_label.setObjectName("geoSummary")
        self.summary_label.setAlignment(Qt.AlignRight)
        row.addWidget(self.summary_label)
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
        self.format_preset.currentTextChanged.connect(self._format_preset_changed)
        self.size_preset.currentTextChanged.connect(
            lambda name: self._preset_changed(
                name, self.size_width, self.size_height
            )
        )
        self.range_radio.toggled.connect(self._range_toggled)
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
        self._operation_buttons["cleanup"][0].clicked.connect(
            lambda: self._undo("cleanup")
        )
        self._operation_buttons["cleanup"][1].clicked.connect(self._apply_cleanup)
        self._format_apply_timer.timeout.connect(self._apply_format)
        self._size_apply_timer.timeout.connect(self._apply_sizes)

    def _set_enabled(self, enabled):
        for card in self._document_cards:
            set_document_control_enabled(card, enabled)
        for widget in (
            self.save_button, self.previous_page, self.next_page,
            self.restore_button, self.print_button,
            self.current_radio, self.all_radio, self.range_radio,
            self.swap_format_button, self.swap_size_button,
        ):
            widget.setEnabled(enabled)
        self.preview_toolbar.set_document_enabled(enabled)
        for widget in (self.current_radio, self.all_radio, self.range_radio):
            set_document_control_enabled(widget, enabled)
        for undo, apply in self._operation_buttons.values():
            apply.setEnabled(enabled)
            undo.setEnabled(
                enabled and bool(self._undo_stack)
                and self._undo_stack[-1][0] == self._operation_for_button(undo)
            )
        self._range_toggled(self.range_radio.isChecked())
        range_enabled = enabled and self.range_radio.isChecked()
        set_document_control_enabled(self.page_from, range_enabled)
        set_document_control_enabled(self.range_to_label, enabled)
        set_document_control_enabled(self.page_to, range_enabled)

    def _choose_pdf(self):
        path, _ = QFileDialog.getOpenFileName(self, "Abrir PDF", "", "PDF (*.pdf)")
        if path:
            self.load_pdf(path)

    def _print_current(self):
        if self.current_path:
            spool_pdf(self, self.current_path, button=self.print_button)

    def _operation_for_button(self, button):
        for operation, (undo, _apply) in self._operation_buttons.items():
            if undo is button:
                return operation
        return ""

    def _apply_style(self):
        style = """
            QWidget#geoPage, QWidget#geoControls { background:__TOOL_BACKGROUND__; }
            QFrame#geoCard { background:rgba(255,255,255,.025); border:1px solid rgba(255,255,255,.08); border-radius:7px; }
            QLabel#geoCardTitle { color:#FFC400; font-size:10px; font-weight:700; letter-spacing:.7px; }
            QLabel#geoFieldLabel { color:rgba(255,255,255,.43); font-size:9px; }
            QLabel#geoPageLabel { color:rgba(255,255,255,.82); font-weight:700; min-width:150px; qproperty-alignment:AlignCenter; }
            QLabel#geoFileLabel, QLabel#geoSummary { color:rgba(255,255,255,.43); font-size:10px; }
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
                font-size:9px; padding:0; min-height:18px;
                border:1px solid rgba(255,255,255,.10);
                background:rgba(255,255,255,.025);
            }
            QPushButton#geoMiniSecondary { color:rgba(255,255,255,.45); }
            QPushButton#geoMiniPrimary {
                color:rgba(255,196,0,.72); border-color:rgba(255,196,0,.22);
            }
            QLabel#geoInlineLabel { color:rgba(255,255,255,.43); font-size:9px; font-weight:700; }
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
            QPushButton { min-height:__TOOL_BUTTON_HEIGHT__px; }
            QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox {
                min-height:__TOOL_FIELD_HEIGHT__px; max-height:__TOOL_FIELD_HEIGHT__px;
                padding-top:0; padding-bottom:0;
            }
        """ + TOOL_STANDARD_QSS
        style = style.replace("__TOOL_BACKGROUND__", TOOL_BACKGROUND)
        style = style.replace("__TOOL_BUTTON_HEIGHT__", str(TOOL_BUTTON_HEIGHT))
        style = style.replace("__TOOL_FIELD_HEIGHT__", str(TOOL_FIELD_HEIGHT))
        self.setStyleSheet(style)

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
        first_trim = info.pages[0].trim
        self.file_label.setText(format_pdf_file_summary(
            self.pdf_path.name,
            first_trim.width_mm,
            first_trim.height_mm,
            info.page_count,
            suffix,
        ))
        set_open_pdf_loaded(self.open_button, True)
        self.page_from.setRange(1, info.page_count)
        self.page_to.setRange(1, info.page_count)
        self.page_to.setValue(info.page_count)
        self.all_radio.setChecked(True)
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
        self._pending_operation_pages = ()
        self._preview_image = QPixmap()
        self.current_page = 0
        if hasattr(self, "file_label"):
            self.file_label.setText("Nenhum PDF carregado")
            set_open_pdf_loaded(self.open_button, False)
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
        self._set_size_fields(page.trim)
        self._select_matching_preset(
            self.format_preset, page.media.width_mm, page.media.height_mm
        )
        self._select_matching_preset(
            self.size_preset, page.trim.width_mm, page.trim.height_mm
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

    def _size_width_changed(self, value):
        if not self._loading and self._size_previous_width:
            self.size_x.blockSignals(True)
            self.size_x.setValue(
                self.size_x.value()
                + (self._size_previous_width - value) * .5
            )
            self.size_x.blockSignals(False)
        self._size_previous_width = value
        self._recognize_size_preset()
        self._refresh_preview()
        self._schedule_size_apply()

    def _size_height_changed(self, value):
        if not self._loading and self._size_previous_height:
            self.size_y.blockSignals(True)
            self.size_y.setValue(
                self.size_y.value()
                + (self._size_previous_height - value) * .5
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
        pending = BoxSettings(
            self.size_x.value(), self.size_y.value(),
            self.size_width.value(), self.size_height.value(),
        )
        self.preview.set_boxes(media, pending, self._preview_image)

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
        self._size_apply_timer.stop()
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
        settings = BoxSettings(
            self.size_x.value(), self.size_y.value(),
            self.size_width.value(), self.size_height.value(),
        )
        self._apply_settings("sizes", GeometrySettings(trim=settings))

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
        self._pending_operation_pages = pages
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
        operation_pages = tuple(self._pending_operation_pages)
        self._undo_stack.append((operation, Path(undo_path), operation_pages))
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
        self._pending_operation_pages = ()
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
        self.print_button.setEnabled(not busy and self.info is not None)
        for widget in (
            self.format_preset, self.format_width, self.format_height,
            self.allow_distortion, self.format_anchor,
            self.size_preset, self.size_width, self.size_height,
            self.size_x, self.size_y, self.trim_quick,
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
        _operation, snapshot, operation_pages = self._undo_stack.pop()
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
            self, "Salvar PDF", save_path(self.pdf_path), "PDF (*.pdf)"
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
        self._size_apply_timer.stop()
        self._changing_format_preset = True
        try:
            self._preset_changed(name, self.format_width, self.format_height)
        finally:
            self._changing_format_preset = False
        self._refresh_preview()
        self._schedule_format_apply()

    def _format_dimensions_changed(self, _value):
        self._size_apply_timer.stop()
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
