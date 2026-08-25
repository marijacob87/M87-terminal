from __future__ import annotations

from pathlib import Path

import fitz
from PySide6.QtCore import QEvent, QMimeData, QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QDrag, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFileDialog, QFrame,
    QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea,
    QSizePolicy, QSpinBox, QVBoxLayout, QWidget,
)

from core.imposition import (
    ImpositionError, build_custom_layout, effective_bleed_rect,
    export_manual_imposition, inspect_pdf, open_pdf_for_imposition,
    transform_duplex_back_slots,
)
from core.preferences import save_path
from ui.imposition_dialog import PreviewWidget
from ui.tool_design import (
    TOOL_BACKGROUND, TOOL_CHIP_HEIGHT,
    TOOL_STANDARD_QSS, ToolPreviewToolbar, apply_terminal_accent, configure_measure_swap,
    create_pdf_file_card, set_document_control_enabled, set_open_pdf_loaded,
    set_tool_role,
)
from ui.design_tokens import (
    TOOL_CARD_MARGINS, TOOL_CARD_SPACING, TOOL_COLUMN_SPACING,
    TOOL_CONTROLS_WIDTH, TOOL_PAGE_SPACING,
)

YELLOW = "#FFC400"


class PageThumbnail(QLabel):
    activated = Signal(int)

    def __init__(self, page_index, pixmap, parent=None):
        super().__init__(parent)
        self.page_index = page_index
        self.setAlignment(Qt.AlignCenter)
        self.setPixmap(pixmap.scaled(105, 105, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.setToolTip(f"Usar página {page_index + 1}")
        self.setCursor(Qt.PointingHandCursor)
        self._drag_origin = QPoint()
        self._dragging = False

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_origin = event.position().toPoint()
            self._dragging = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not event.buttons() & Qt.LeftButton:
            return
        if (event.position().toPoint() - self._drag_origin).manhattanLength() < 8:
            return
        mime = QMimeData()
        self._dragging = True
        mime.setData("application/x-m87-pdf-page", str(self.page_index).encode("ascii"))
        drag = QDrag(self)
        drag.setMimeData(mime)
        if self.pixmap() and not self.pixmap().isNull():
            drag.setPixmap(self.pixmap().scaled(70, 70, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        drag.exec(Qt.CopyAction)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and not self._dragging:
            self.activated.emit(self.page_index)
        self._dragging = False
        super().mouseReleaseEvent(event)


class InlinePageEdit(QLineEdit):
    navigateRequested = Signal(int)

    def event(self, event):
        if event.type() == QEvent.KeyPress:
            if event.key() == Qt.Key_Tab:
                self.navigateRequested.emit(1)
                event.accept()
                return True
            if event.key() == Qt.Key_Backtab:
                self.navigateRequested.emit(-1)
                event.accept()
                return True
        return super().event(event)

class EditablePreviewWidget(PreviewWidget):
    selectionChanged = Signal(object)
    pageEdited = Signal(int, int)
    sequenceDropRequested = Signal(int, int)
    boundaryNavigationRequested = Signal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.selected_slots: set[int] = set()
        self.setAcceptDrops(True)
        self.inline_editor = InlinePageEdit(self)
        self.inline_editor.setObjectName("manualInlinePage")
        self.inline_editor.setAlignment(Qt.AlignCenter)
        self.inline_editor.setMaxLength(4)
        self.inline_editor.hide()
        self.inline_editor.editingFinished.connect(self._commit_inline_edit)
        self.inline_editor.navigateRequested.connect(self._navigate_inline_edit)
        self._editing_slot = None

    def _slot_rects(self):
        option = self.layout_option
        if not option:
            return []
        margin = 28.0
        area = self.rect().adjusted(int(margin), int(margin), -int(margin), -int(margin))
        scale = min(area.width() / self.paper_w, area.height() / self.paper_h) * self._zoom
        origin_x = area.center().x() - self.paper_w * scale / 2 + self._pan.x()
        origin_y = area.center().y() - self.paper_h * scale / 2 + self._pan.y()
        return [
            QRectF(
                origin_x + (option.start_x_mm + col * (option.item_width_mm + self.gutter)) * scale,
                origin_y + (option.start_y_mm + row * (option.item_height_mm + self.gutter)) * scale,
                option.item_width_mm * scale,
                option.item_height_mm * scale,
            )
            for row in range(option.rows) for col in range(option.columns)
        ]

    def _slot_at(self, position: QPointF):
        for index, rect in enumerate(self._slot_rects()):
            if rect.contains(position):
                return index
        return None

    def mousePressEvent(self, event):
        slot = self._slot_at(event.position())
        if slot is None:
            self.selected_slots.clear()
        elif event.modifiers() & (Qt.ControlModifier | Qt.MetaModifier | Qt.ShiftModifier):
            if slot in self.selected_slots:
                self.selected_slots.remove(slot)
            else:
                self.selected_slots.add(slot)
        else:
            self.selected_slots = {slot}
        self.selectionChanged.emit(sorted(self.selected_slots))
        self.update()
        if slot is not None and not event.modifiers():
            self._start_inline_edit(slot)
        if slot is None:
            super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        slot = self._slot_at(event.position())
        if slot is not None:
            self.selected_slots = {slot}
            self.selectionChanged.emit([slot])
            self._start_inline_edit(slot)

    def _start_inline_edit(self, slot):
        rects = self._slot_rects()
        if slot >= len(rects):
            return
        rect = rects[slot]
        current = None
        if self.page_assignments is not None and slot < len(self.page_assignments):
            current = self.page_assignments[slot]
        self._editing_slot = slot
        self.inline_editor.setText("" if current is None else str(current + 1))
        self.inline_editor.setGeometry(
            int(rect.left() + 3), int(rect.top() + 3),
            max(38, min(54, int(rect.width() - 6))), 22,
        )
        self.inline_editor.show()
        self.inline_editor.raise_()
        self.inline_editor.setFocus()
        self.inline_editor.selectAll()

    def _commit_inline_edit(self):
        if self._editing_slot is None:
            return
        text = self.inline_editor.text().strip()
        value = int(text) if text.isdigit() else 0
        self.pageEdited.emit(self._editing_slot, value)
        self._editing_slot = None
        self.inline_editor.hide()

    def _navigate_inline_edit(self, direction):
        if self._editing_slot is None:
            return
        current_slot = self._editing_slot
        text = self.inline_editor.text().strip()
        value = int(text) if text.isdigit() else 0
        self.pageEdited.emit(current_slot, value)
        total = len(self._slot_rects())
        if not total:
            self._editing_slot = None
            self.inline_editor.hide()
            return
        self._editing_slot = None
        self.inline_editor.hide()
        self.boundaryNavigationRequested.emit(current_slot, direction)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat("application/x-m87-pdf-page"):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        self.dragEnterEvent(event)

    def dropEvent(self, event):
        slot = self._slot_at(event.position())
        if slot is None:
            event.ignore()
            return
        raw = bytes(event.mimeData().data("application/x-m87-pdf-page"))
        try:
            page_index = int(raw.decode("ascii"))
        except ValueError:
            event.ignore()
            return
        self.selected_slots = {slot}
        self.selectionChanged.emit([slot])
        self.sequenceDropRequested.emit(slot, page_index)
        event.acceptProposedAction()

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.selected_slots:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor(YELLOW), 3))
        rects = self._slot_rects()
        for slot in self.selected_slots:
            if slot < len(rects):
                painter.drawRect(rects[slot].adjusted(1.5, 1.5, -1.5, -1.5))


class ManualImpositionDialog(QDialog):
    pdfStateChanged = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pdf_path: Path | None = None
        self.geometry_info = None
        self.thumbnails: list[QPixmap] = []
        self.front_pages: list[int | None] = []
        self.back_pages: list[int | None] = []
        self.front_rotations: list[int] = []
        self.back_rotations: list[int] = []
        self.front_visibility: list[bool] = []
        self.back_visibility: list[bool] = []
        self.active_side = "front"
        self._undo_history: list[dict] = []
        self._pending_config_states: dict[QWidget, dict] = {}
        self._last_flip_index = 0
        self._build_ui()
        self._connect()
        self._style()
        self._rebuild_slots()
        for widget in (
            self.paper_w, self.paper_h, self.gutter, self.margin,
            self.columns, self.rows,
        ):
            widget.installEventFilter(self)
            widget.editingFinished.connect(
                lambda target=widget: self._configuration_edit_finished(target)
            )

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.box = QWidget()
        self.box.setObjectName("manualImpBox")
        self.box.setProperty("toolSurface", True)
        outer.addWidget(self.box)
        root = QVBoxLayout(self.box)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(TOOL_PAGE_SPACING)

        file_card, self.open_button, self.file_label = create_pdf_file_card(
            self._choose_pdf
        )
        file_card.setFixedWidth(TOOL_CONTROLS_WIDTH)
        root.addWidget(file_card, 0, Qt.AlignLeft)

        controls = QFrame()
        controls.setObjectName("manualCard")
        set_tool_role(controls, "card")
        grid = QGridLayout(controls)
        grid.setContentsMargins(11, 9, 11, 9)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)
        self.paper_w = self._measure(330)
        self.paper_h = self._measure(480)
        self.swap_measures = configure_measure_swap(QPushButton())
        self.gutter = self._measure(5)
        self.margin = self._measure(5)
        self.columns = self._integer(3, 1, 20)
        self.rows = self._integer(2, 1, 20)
        self.duplex = QCheckBox("Frente e verso")
        self.duplex.setChecked(True)
        self.flip = QComboBox()
        self.flip.addItems(["Virar pela borda longa", "Virar pela borda curta"])
        self.marks = QCheckBox("Marcas de corte")
        self.marks.setChecked(True)
        self.paper_w.setFixedWidth(170)
        self.paper_h.setFixedWidth(170)
        grid.addWidget(self._labelled("LARGURA", self.paper_w), 1, 0)
        grid.addWidget(self.swap_measures, 1, 1, Qt.AlignBottom)
        grid.addWidget(self._labelled("ALTURA", self.paper_h), 1, 2)
        grid.addWidget(self._labelled("ENTRE CORTES", self.gutter), 1, 3)
        grid.addWidget(self._labelled("MARGEM", self.margin), 1, 4)
        grid.addWidget(self._labelled("COLUNAS", self.columns), 1, 5)
        grid.addWidget(self._labelled("LINHAS", self.rows), 1, 6)
        grid.addWidget(self.duplex, 1, 7)
        grid.addWidget(self.flip, 1, 8)
        grid.addWidget(self.marks, 1, 9)
        root.addWidget(controls)

        content = QHBoxLayout()
        content.setSpacing(TOOL_COLUMN_SPACING)

        pages_card = QFrame()
        pages_card.setObjectName("manualCard")
        set_tool_role(pages_card, "card")
        pages_card.setFixedWidth(155)
        pages_layout = QVBoxLayout(pages_card)
        pages_layout.setContentsMargins(*TOOL_CARD_MARGINS)
        pages_layout.setSpacing(TOOL_CARD_SPACING)
        pages_title = QLabel("PÁGINAS DO PDF")
        pages_title.setObjectName("manualTitle")
        set_tool_role(pages_title, "cardTitle")
        pages_layout.addWidget(pages_title)
        pages_scroll = QScrollArea()
        pages_scroll.setWidgetResizable(True)
        pages_scroll.setFrameShape(QFrame.NoFrame)
        self.pages_host = QWidget()
        self.pages_layout = QVBoxLayout(self.pages_host)
        self.pages_layout.setContentsMargins(2, 2, 2, 2)
        self.pages_layout.setSpacing(8)
        self.pages_layout.addStretch()
        pages_scroll.setWidget(self.pages_host)
        pages_layout.addWidget(pages_scroll, 1)
        content.addWidget(pages_card)

        previews = QHBoxLayout()
        previews.setSpacing(TOOL_COLUMN_SPACING)
        self.front_preview_card, self.front_preview = self._preview_card("FRENTE")
        self.back_preview_card, self.back_preview = self._preview_card("VERSO")
        previews.addWidget(self.front_preview_card, 1)
        previews.addWidget(self.back_preview_card, 1)
        preview_host = QWidget()
        preview_host.setLayout(previews)
        content.addWidget(preview_host, 1)
        root.addLayout(content, 1)

        self.status = QLabel("Carregue um PDF para começar.")
        self.status.setObjectName("manualMuted")
        self.selection_label = QLabel("Selecione uma posição na folha")
        self.selection_label.setObjectName("manualMuted")
        info_row = QHBoxLayout()
        info_row.addWidget(self.status, 1)
        info_row.addWidget(self.selection_label)
        root.addLayout(info_row)

        footer = QHBoxLayout()
        self.release_pdf = QPushButton("LIBERAR PDF")
        self.rotate_90 = QPushButton("↻ 90°")
        self.rotate_180 = QPushButton("↻ 180°")
        self.clear_selected = QPushButton("ESVAZIAR")
        self.clear_all = QPushButton("LIMPAR TODAS")
        self.auto_fill = QPushButton("ADICIONAR PDF À MONTAGEM")
        self.output_name = QLineEdit("imposicao_manual.pdf")
        self.output_name.setMinimumWidth(300)
        self.output_name.setMaximumWidth(680)
        self.output_name.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.save_button = QPushButton("SALVAR COMO…")
        for button in (
            self.release_pdf, self.rotate_90, self.rotate_180, self.clear_selected,
            self.clear_all, self.auto_fill,
        ):
            set_tool_role(button, "chip")
            button.setFixedHeight(TOOL_CHIP_HEIGHT)
        set_tool_role(self.save_button, "footerAction")
        self.save_button.setProperty("actionRole", "primary")
        self.save_button.setFixedSize(136, 28)
        self.save_button.setEnabled(False)
        footer.addWidget(self.release_pdf)
        footer.addWidget(self.rotate_90)
        footer.addWidget(self.rotate_180)
        footer.addWidget(self.clear_selected)
        footer.addWidget(self.clear_all)
        footer.addWidget(self.auto_fill)
        footer.addWidget(self.output_name, 1)
        footer.addWidget(self.save_button)
        root.addLayout(footer)
        self._document_widgets = (
            controls, pages_card, self.front_preview_card,
            self.back_preview_card,
        )

    def _preview_card(self, title):
        card = QFrame()
        card.setObjectName("manualCard")
        set_tool_role(card, "card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(*TOOL_CARD_MARGINS)
        layout.setSpacing(TOOL_CARD_SPACING)
        label = QLabel(title)
        label.setObjectName("manualTitle")
        set_tool_role(label, "cardTitle")
        layout.addWidget(label)
        preview = EditablePreviewWidget(card)
        toolbar = ToolPreviewToolbar(card)
        for widget in (
            toolbar.previous_button, toolbar.page_label, toolbar.next_button,
            toolbar.rotation_undo_button, toolbar.rotate_button,
        ):
            widget.hide()
        toolbar.zoom_out_button.clicked.connect(preview.zoom_out)
        toolbar.zoom_in_button.clicked.connect(preview.zoom_in)
        toolbar.zoom_label.clicked.connect(preview.reset_zoom)
        preview.zoomChanged.connect(
            lambda value, label=toolbar.zoom_label: label.setText(f"{value}%")
        )
        preview.zoom_toolbar = toolbar
        layout.addWidget(toolbar)
        preview.setMinimumSize(260, 320)
        layout.addWidget(preview, 1)
        return card, preview

    @staticmethod
    def _measure(value):
        spin = QDoubleSpinBox()
        spin.setRange(0, 2000)
        spin.setDecimals(2)
        spin.setSuffix(" mm")
        spin.setValue(value)
        return spin

    @staticmethod
    def _integer(value, minimum, maximum):
        spin = QSpinBox()
        spin.setRange(minimum, maximum)
        spin.setValue(value)
        return spin

    @staticmethod
    def _labelled(text, widget):
        host = QWidget()
        layout = QVBoxLayout(host)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        label = QLabel(text)
        label.setObjectName("manualField")
        set_tool_role(label, "fieldLabel")
        layout.addWidget(label)
        layout.addWidget(widget)
        return host

    def _connect(self):
        self.swap_measures.clicked.connect(self._swap_paper_measures)
        for widget in (self.paper_w, self.paper_h, self.gutter, self.margin):
            widget.valueChanged.connect(self._refresh)
        self.columns.valueChanged.connect(self._rebuild_slots)
        self.rows.valueChanged.connect(self._rebuild_slots)
        self.duplex.toggled.connect(self._duplex_changed)
        self.duplex.pressed.connect(self._record_state)
        self.flip.activated.connect(self._flip_changed)
        self.marks.toggled.connect(self._refresh)
        self.marks.pressed.connect(self._record_state)
        self.auto_fill.clicked.connect(self._auto_fill)
        self.rotate_90.clicked.connect(lambda: self._rotate_selected(90))
        self.rotate_180.clicked.connect(lambda: self._rotate_selected(180))
        self.clear_selected.clicked.connect(self._clear_selected)
        self.clear_all.clicked.connect(self._clear_all_positions)
        self.release_pdf.clicked.connect(self._release_pdf)
        self.front_preview.selectionChanged.connect(
            lambda slots: self._selection_changed("front", slots)
        )
        self.back_preview.selectionChanged.connect(
            lambda slots: self._selection_changed("back", slots)
        )
        self.front_preview.pageEdited.connect(
            lambda slot, page: self._inline_page_edited("front", slot, page)
        )
        self.back_preview.pageEdited.connect(
            lambda slot, page: self._inline_page_edited("back", slot, page)
        )
        self.front_preview.sequenceDropRequested.connect(
            lambda slot, page: self._fill_from_drop("front", slot, page)
        )
        self.back_preview.sequenceDropRequested.connect(
            lambda slot, page: self._fill_from_drop("back", slot, page)
        )
        self.front_preview.boundaryNavigationRequested.connect(
            lambda slot, direction: self._cross_preview_navigation("front", slot, direction)
        )
        self.back_preview.boundaryNavigationRequested.connect(
            lambda slot, direction: self._cross_preview_navigation("back", slot, direction)
        )
        self.save_button.clicked.connect(self._save)

    def load_pdfs(self, paths):
        if not paths:
            return
        self._load_pdf(Path(paths[0]))

    def _choose_pdf(self):
        selected, _ = QFileDialog.getOpenFileName(self, "Abrir PDF", "", "PDF (*.pdf)")
        if selected:
            self._load_pdf(Path(selected))

    def _load_pdf(self, path: Path):
        try:
            info = inspect_pdf(path)
        except ImpositionError as exc:
            self.status.setText(f"⚠ {exc}")
            return
        self.pdf_path = path
        self.geometry_info = info
        self.file_label.setText(
            f"{path.name} · {info.page_count} pág. · "
            f"{info.trim_width_mm:.2f} × {info.trim_height_mm:.2f} mm"
        )
        set_open_pdf_loaded(self.open_button, True)
        self._render_thumbnails()
        self._populate_page_gallery()
        self._rebuild_slots()
        self._auto_fill()
        self._undo_history.clear()
        self.output_name.setText(f"{path.stem}_imposicao_manual.pdf")
        self.pdfStateChanged.emit([str(path)])
        self._set_document_enabled(True)

    def _set_document_enabled(self, enabled):
        for widget in self._document_widgets:
            set_document_control_enabled(widget, enabled)

    def _render_thumbnails(self):
        self.thumbnails = []
        doc = open_pdf_for_imposition(self.pdf_path)
        try:
            for page in doc:
                pix = page.get_pixmap(matrix=fitz.Matrix(.45, .45), alpha=False,
                                      clip=effective_bleed_rect(page))
                fmt = QImage.Format_RGB888 if pix.n == 3 else QImage.Format_RGBA8888
                image = QImage(pix.samples, pix.width, pix.height, pix.stride, fmt).copy()
                self.thumbnails.append(QPixmap.fromImage(image))
        finally:
            doc.close()

    def _populate_page_gallery(self):
        while self.pages_layout.count():
            item = self.pages_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for index, pixmap in enumerate(self.thumbnails):
            item = QWidget()
            layout = QVBoxLayout(item)
            layout.setContentsMargins(2, 2, 2, 2)
            layout.setSpacing(2)
            thumbnail = PageThumbnail(index, pixmap, item)
            thumbnail.activated.connect(self._assign_gallery_page)
            number = QLabel(f"PÁGINA {index + 1}")
            number.setAlignment(Qt.AlignCenter)
            number.setObjectName("manualPageNumber")
            layout.addWidget(thumbnail)
            layout.addWidget(number)
            self.pages_layout.addWidget(item)
        self.pages_layout.addStretch()

    def _rebuild_slots(self, *_):
        total = self.columns.value() * self.rows.value()
        self.front_pages = (self.front_pages + [None] * total)[:total]
        self.back_pages = (self.back_pages + [None] * total)[:total]
        self.front_rotations = (self.front_rotations + [0] * total)[:total]
        self.back_rotations = (self.back_rotations + [0] * total)[:total]
        self.front_visibility = (self.front_visibility + [False] * total)[:total]
        self.back_visibility = (self.back_visibility + [False] * total)[:total]
        self.front_preview.selected_slots.clear()
        self.back_preview.selected_slots.clear()
        self._duplex_changed(self.duplex.isChecked())
        self._refresh()

    def _back_output_assignments(self):
        return self._transform_back(self.back_pages)

    def _back_output_rotations(self):
        return self._transform_back(self.back_rotations)

    def _back_output_visibility(self):
        return self._transform_back(self.back_visibility)

    def _transform_back(self, values):
        return transform_duplex_back_slots(
            list(values), self.rows.value(), self.columns.value(),
            self.paper_w.value(), self.paper_h.value(),
            self.flip.currentIndex() == 0,
        )

    def _duplex_changed(self, checked):
        self.back_preview_card.setVisible(checked)
        self.flip.setEnabled(checked)
        self._refresh()

    def _auto_fill(self):
        if not self.geometry_info:
            return
        self._record_state()
        existing = list(self.front_pages)
        if self.duplex.isChecked():
            existing.extend(self.back_pages)
        if any(page is not None for page in existing):
            self.front_visibility = [page is not None for page in self.front_pages]
            self.back_visibility = [page is not None for page in self.back_pages]
            self._refresh()
            return
        if self.duplex.isChecked():
            for slot in range(len(self.front_pages)):
                front_page = slot * 2
                back_page = front_page + 1
                self.front_pages[slot] = (
                    front_page if front_page < self.geometry_info.page_count else None
                )
                self.back_pages[slot] = (
                    back_page if back_page < self.geometry_info.page_count else None
                )
            self.front_visibility = [page is not None for page in self.front_pages]
            self.back_visibility = [page is not None for page in self.back_pages]
            self._refresh()
            return
        page = 1
        sides = [self.front_pages]
        if self.duplex.isChecked():
            sides.append(self.back_pages)
        for side in sides:
            for index in range(len(side)):
                side[index] = page - 1 if page <= self.geometry_info.page_count else None
                page += 1
        self.front_visibility = [page is not None for page in self.front_pages]
        self.back_visibility = [page is not None for page in self.back_pages]
        self._refresh()

    def _selection_changed(self, side, slots):
        self.active_side = side
        other = self.back_preview if side == "front" else self.front_preview
        if slots:
            other.selected_slots.clear()
            other.update()
        face = "Frente" if side == "front" else "Verso"
        self.selection_label.setText(
            f"{face}: " + (
                ", ".join(str(slot + 1) for slot in slots)
                if slots else "nenhuma posição"
            )
        )
        self._update_edit_actions()

    def _selected_slots(self):
        preview = self.front_preview if self.active_side == "front" else self.back_preview
        return sorted(preview.selected_slots)

    def _active_pages(self):
        return self.front_pages if self.active_side == "front" else self.back_pages

    def _active_rotations(self):
        return self.front_rotations if self.active_side == "front" else self.back_rotations

    def _update_edit_actions(self):
        enabled = bool(self.geometry_info and self._selected_slots())
        for button in (self.rotate_90, self.rotate_180, self.clear_selected):
            button.setEnabled(enabled)

    def _assign_gallery_page(self, page_index):
        slots = self._selected_slots()
        if not slots:
            pages = self._active_pages()
            try:
                slot = pages.index(None)
            except ValueError:
                slot = 0
            preview = self.front_preview if self.active_side == "front" else self.back_preview
            preview.selected_slots = {slot}
            slots = [slot]
        pages = self._active_pages()
        visibility = self.front_visibility if self.active_side == "front" else self.back_visibility
        self._record_state()
        for slot in slots:
            pages[slot] = page_index
            visibility[slot] = True
        self._refresh()

    def _inline_page_edited(self, side, slot, page_number):
        if not self.geometry_info:
            return
        self._record_state()
        pages = self.front_pages if side == "front" else self.back_pages
        visibility = self.front_visibility if side == "front" else self.back_visibility
        pages[slot] = (
            page_number - 1
            if 1 <= page_number <= self.geometry_info.page_count
            else None
        )
        visibility[slot] = pages[slot] is not None
        self._refresh()

    def _cross_preview_navigation(self, side, current_slot, direction):
        if self.duplex.isChecked():
            if side == "front" and direction > 0:
                target, target_side, slot = self.back_preview, "back", current_slot
            elif side == "back" and direction < 0:
                target, target_side, slot = self.front_preview, "front", current_slot
            elif side == "back" and direction > 0:
                target, target_side = self.front_preview, "front"
                slot = (current_slot + 1) % len(self.front_pages)
            else:
                target, target_side = self.back_preview, "back"
                slot = (current_slot - 1) % len(self.back_pages)
        else:
            target, target_side = self.front_preview, "front"
            slot = (current_slot + direction) % len(self.front_pages)
        self.active_side = target_side
        self.front_preview.selected_slots.clear()
        self.back_preview.selected_slots.clear()
        target.selected_slots = {slot}
        self._selection_changed(target_side, [slot])
        target._start_inline_edit(slot)
        target.update()

    def _fill_from_drop(self, side, start_slot, page_index):
        """Troca somente a posição que recebeu a miniatura."""
        if not self.geometry_info:
            return
        self._record_state()
        pages = self.front_pages if side == "front" else self.back_pages
        visibility = self.front_visibility if side == "front" else self.back_visibility
        pages[start_slot] = page_index
        visibility[start_slot] = True
        self._refresh()

    def _rotate_selected(self, degrees):
        if not self._selected_slots():
            return
        self._record_state()
        rotations = self._active_rotations()
        for slot in self._selected_slots():
            rotations[slot] = (rotations[slot] + degrees) % 360
        self._refresh()

    def _clear_selected(self):
        if not self._selected_slots():
            return
        self._record_state()
        pages = self._active_pages()
        rotations = self._active_rotations()
        visibility = self.front_visibility if self.active_side == "front" else self.back_visibility
        for slot in self._selected_slots():
            pages[slot] = None
            rotations[slot] = 0
            visibility[slot] = False
        self._refresh()

    def _clear_all_positions(self):
        self._record_state()
        self.front_visibility = [False] * len(self.front_visibility)
        self.back_visibility = [False] * len(self.back_visibility)
        self.front_preview.selected_slots.clear()
        self.back_preview.selected_slots.clear()
        self.selection_label.setText("Artes removidas · números preservados")
        self._refresh()

    def _release_pdf(self):
        if not self.pdf_path:
            return
        self._record_state()
        self.pdf_path = None
        self.thumbnails = []
        self.front_visibility = [False] * len(self.front_visibility)
        self.back_visibility = [False] * len(self.back_visibility)
        self._populate_page_gallery()
        self.file_label.setText("Nenhum PDF carregado")
        set_open_pdf_loaded(self.open_button, False)
        self.status.setText("PDF liberado · grade e números preservados")
        self._set_document_enabled(False)
        self._refresh()

    def _layout(self):
        if not self.geometry_info:
            return None
        return build_custom_layout(
            self.paper_w.value(), self.paper_h.value(),
            self.geometry_info.trim_width_mm, self.geometry_info.trim_height_mm,
            self.gutter.value(), self.margin.value(), self.columns.value(),
            self.rows.value(), False,
        )

    def _swap_paper_measures(self):
        self._record_state()
        width, height = self.paper_w.value(), self.paper_h.value()
        self.paper_w.blockSignals(True)
        self.paper_h.blockSignals(True)
        self.paper_w.setValue(height)
        self.paper_h.setValue(width)
        self.paper_w.blockSignals(False)
        self.paper_h.blockSignals(False)
        self._refresh()

    def eventFilter(self, watched, event):
        if event.type() == QEvent.FocusIn and watched not in self._pending_config_states:
            self._pending_config_states[watched] = self._capture_state()
        return super().eventFilter(watched, event)

    def _configuration_edit_finished(self, widget):
        state = self._pending_config_states.pop(widget, None)
        if state and state["config"] != self._capture_state()["config"]:
            self._append_undo_state(state)

    def _flip_changed(self, index):
        if index != self._last_flip_index:
            state = self._capture_state()
            state["config"]["flip"] = self._last_flip_index
            self._append_undo_state(state)
            self._last_flip_index = index
        self._refresh()

    def _capture_state(self):
        return {
            "front_pages": list(self.front_pages),
            "back_pages": list(self.back_pages),
            "front_rotations": list(self.front_rotations),
            "back_rotations": list(self.back_rotations),
            "front_visibility": list(self.front_visibility),
            "back_visibility": list(self.back_visibility),
            "pdf_path": self.pdf_path,
            "geometry_info": self.geometry_info,
            "thumbnails": list(self.thumbnails),
            "config": {
                "paper_w": self.paper_w.value(),
                "paper_h": self.paper_h.value(),
                "gutter": self.gutter.value(),
                "margin": self.margin.value(),
                "columns": self.columns.value(),
                "rows": self.rows.value(),
                "duplex": self.duplex.isChecked(),
                "flip": self.flip.currentIndex(),
                "marks": self.marks.isChecked(),
            },
        }

    def _append_undo_state(self, state):
        self._undo_history.append(state)
        if len(self._undo_history) > 50:
            self._undo_history.pop(0)

    def _record_state(self):
        self._append_undo_state(self._capture_state())

    def undo_last_action(self):
        if not self._undo_history:
            self.status.setText("Nada para desfazer")
            return
        state = self._undo_history.pop()
        self.front_pages = state["front_pages"]
        self.back_pages = state["back_pages"]
        self.front_rotations = state["front_rotations"]
        self.back_rotations = state["back_rotations"]
        self.front_visibility = state["front_visibility"]
        self.back_visibility = state["back_visibility"]
        self.pdf_path = state["pdf_path"]
        self.geometry_info = state["geometry_info"]
        self.thumbnails = state["thumbnails"]
        config = state["config"]
        for widget, value in (
            (self.paper_w, config["paper_w"]),
            (self.paper_h, config["paper_h"]),
            (self.gutter, config["gutter"]),
            (self.margin, config["margin"]),
            (self.columns, config["columns"]),
            (self.rows, config["rows"]),
            (self.duplex, config["duplex"]),
            (self.flip, config["flip"]),
            (self.marks, config["marks"]),
        ):
            widget.blockSignals(True)
            widget.setChecked(value) if isinstance(widget, QCheckBox) else widget.setValue(value) if isinstance(widget, (QSpinBox, QDoubleSpinBox)) else widget.setCurrentIndex(value)
            widget.blockSignals(False)
        self._last_flip_index = config["flip"]
        self.back_preview_card.setVisible(config["duplex"])
        self.flip.setEnabled(config["duplex"])
        self._populate_page_gallery()
        set_open_pdf_loaded(self.open_button, bool(self.pdf_path))
        if self.pdf_path and self.geometry_info:
            self.file_label.setText(
                f"{self.pdf_path.name} · {self.geometry_info.page_count} pág. · "
                f"{self.geometry_info.trim_width_mm:.2f} × "
                f"{self.geometry_info.trim_height_mm:.2f} mm"
            )
        else:
            self.file_label.setText("Nenhum PDF carregado")
        self._set_document_enabled(bool(self.pdf_path))
        self.status.setText("↶ Última ação desfeita")
        self._refresh()

    def _refresh(self, *_):
        option = self._layout()
        assigned_pages = list(self.front_pages)
        visible_flags = list(self.front_visibility)
        if self.duplex.isChecked():
            assigned_pages.extend(self.back_pages)
            visible_flags.extend(self.back_visibility)
        invalid_pages = sorted({
            page + 1 for page in assigned_pages
            if page is not None and self.geometry_info and page >= self.geometry_info.page_count
        })
        has_visible_artwork = any(
            visible and page is not None
            for page, visible in zip(assigned_pages, visible_flags)
        )
        enabled = bool(option and self.pdf_path and not invalid_pages and has_visible_artwork)
        self.save_button.setEnabled(enabled)
        self.auto_fill.setEnabled(bool(self.geometry_info and self.pdf_path))
        self.release_pdf.setEnabled(bool(self.pdf_path))
        self.front_preview.zoom_toolbar.set_document_enabled(bool(self.geometry_info))
        self.back_preview.zoom_toolbar.set_document_enabled(bool(self.geometry_info))
        self._set_document_enabled(bool(self.pdf_path))
        if invalid_pages:
            self.status.setText(
                "⚠ Páginas inexistentes neste PDF: "
                + ", ".join(map(str, invalid_pages))
            )
        elif self.geometry_info and not option:
            self.status.setText("⚠ A grade não cabe no papel com as medidas atuais.")
        elif self.geometry_info:
            all_pages = list(self.front_pages)
            if self.duplex.isChecked():
                all_pages.extend(self.back_pages)
            used = {value for value in all_pages if value is not None}
            missing = self.geometry_info.page_count - len(used)
            if not has_visible_artwork:
                detail = "nenhuma arte adicionada à montagem"
            elif missing > 0:
                detail = f"⚠ {missing} página(s) não cabem ou ainda não foram usadas"
            else:
                detail = "todas as páginas distribuídas"
            self.status.setText(f"{option.total} posições por lado · {detail}")
        common = dict(
            paper_w=self.paper_w.value(), paper_h=self.paper_h.value(), option=option,
            gutter=self.gutter.value(), page_count=self.geometry_info.page_count if self.geometry_info else 0,
            mode="sequential", fill_order="rows", thumbnails=self.thumbnails,
            crop_marks=self.marks.isChecked(), sheet_index=0,
            bleed_left=self.geometry_info.bleed_left_mm if self.geometry_info else 0.0,
            bleed_top=self.geometry_info.bleed_top_mm if self.geometry_info else 0.0,
            bleed_right=self.geometry_info.bleed_right_mm if self.geometry_info else 0.0,
            bleed_bottom=self.geometry_info.bleed_bottom_mm if self.geometry_info else 0.0,
        )
        self.front_preview.set_state(
            **common,
            page_assignments=self.front_pages,
            page_rotations=self.front_rotations,
            page_visibility=self.front_visibility,
        )
        self.back_preview.set_state(
            **common,
            page_assignments=self.back_pages,
            page_rotations=self.back_rotations,
            page_visibility=self.back_visibility,
        )
        self._update_edit_actions()

    def _save(self):
        option = self._layout()
        if not self.pdf_path or not option:
            return
        default = save_path(Path.home() / "Desktop" / self.output_name.text().strip())
        selected, _ = QFileDialog.getSaveFileName(self, "Salvar imposição manual", default, "PDF (*.pdf)")
        if not selected:
            return
        output = Path(selected)
        if output.suffix.lower() != ".pdf":
            output = output.with_suffix(".pdf")
        try:
            export_manual_imposition(
                self.pdf_path, output, option, self.gutter.value(),
                [
                    page if self.front_visibility[index] else None
                    for index, page in enumerate(self.front_pages)
                ],
                (
                    [page if visibility else None for page, visibility in zip(
                        self._back_output_assignments(), self._back_output_visibility()
                    )]
                    if self.duplex.isChecked() else None
                ),
                front_rotations=self.front_rotations,
                back_rotations=(
                    self._back_output_rotations() if self.duplex.isChecked() else None
                ),
                crop_marks=self.marks.isChecked(),
            )
            self.status.setText(f"✓ Imposição salva: {output.name}")
        except ImpositionError as exc:
            self.status.setText(f"⚠ {exc}")

    def _style(self):
        apply_terminal_accent(self.box)
        self.setStyleSheet(TOOL_STANDARD_QSS + f"""
            QWidget#manualImpBox {{ background:{TOOL_BACKGROUND}; }}
            QLabel#manualMuted {{ color:rgba(255,255,255,.43); }}
            QLabel#manualPageNumber {{ color:rgba(255,255,255,.68); font-size:9px; }}
            QLineEdit#manualInlinePage {{
                color:white; background:rgba(0,0,0,.82);
                border:2px solid {YELLOW}; border-radius:4px;
                min-height:20px; max-height:20px; padding:0 3px;
                font-weight:700;
            }}
            QPushButton[toolRole="chip"] {{ text-align:center; }}
            QPushButton[toolRole="footerAction"] {{
                color:{YELLOW}; background:transparent;
                border:1px solid rgba(255,196,0,.48); border-radius:4px;
                text-align:center; font-weight:700;
            }}
        """)
