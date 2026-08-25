from __future__ import annotations

from pathlib import Path

import fitz
from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap, QTransform
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QMessageBox, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from core.color_preflight import (
    FOGRA39_LABEL, US_COATED_LABEL, analyze_color_preflight,
    convert_pdf_to_cmyk, render_separation_preview,
)
from core.preferences import save_path
from ui.tool_design import (
    TOOL_CARD_MARGINS, TOOL_CARD_SPACING, TOOL_COLUMN_SPACING,
    TOOL_CONTROLS_WIDTH, TOOL_PAGE_MARGINS, TOOL_PAGE_SPACING,
    TOOL_STANDARD_QSS, ToolPreviewToolbar, apply_terminal_accent,
    create_pdf_file_card, set_document_control_enabled, set_open_pdf_loaded,
    set_tool_role, show_button_success,
)


YELLOW = "#FFC400"


def _card(title: str) -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    set_tool_role(frame, "card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(*TOOL_CARD_MARGINS)
    layout.setSpacing(TOOL_CARD_SPACING)
    caption = QLabel(title)
    set_tool_role(caption, "cardTitle")
    layout.addWidget(caption)
    return frame, layout


class ColorWorker(QThread):
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, path: str, parent=None):
        super().__init__(parent)
        self.path = path

    def run(self):
        try:
            self.succeeded.emit(analyze_color_preflight(self.path))
        except Exception as error:
            self.failed.emit(str(error))


class ConversionWorker(QThread):
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, source: str, output: str, profile: str, parent=None):
        super().__init__(parent)
        self.source = source
        self.output = output
        self.profile = profile

    def run(self):
        try:
            self.succeeded.emit(convert_pdf_to_cmyk(
                self.source, self.output, self.profile,
            ))
        except Exception as error:
            self.failed.emit(str(error))


class SeparationWorker(QThread):
    succeeded = Signal(object, bytes)
    failed = Signal(object, str)

    def __init__(self, key, parent=None):
        super().__init__(parent)
        self.key = key

    def run(self):
        path, page_number, colorants = self.key
        try:
            preview = render_separation_preview(
                path, page_number, colorants, dpi=180,
            )
            self.succeeded.emit(self.key, preview)
        except Exception as error:
            self.failed.emit(self.key, str(error))


class ColorPreview(QWidget):
    zoomChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(430, 390)
        self._pixmap = QPixmap()
        self._bbox = None
        self._page_rect = None
        self._message = "Arraste um PDF para visualizar"
        self._zoom = 1.0
        self._pan = QPointF()
        self._drag_origin = None
        self._rotation = 0
        self._previous_rotation = 0

    def show_page(self, path: str, page_number: int = 1, bbox=None):
        document = fitz.open(path)
        try:
            page = document[max(0, min(page_number - 1, document.page_count - 1))]
            pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
            image = QImage.fromData(pix.tobytes("png"))
            self._pixmap = QPixmap.fromImage(image)
            self._page_rect = tuple(page.rect)
            self._bbox = tuple(bbox) if bbox else None
            self._message = f"PÁGINA {page_number}"
        finally:
            document.close()
        self.update()

    def show_image(self, png_bytes: bytes, message: str):
        self._pixmap = QPixmap.fromImage(QImage.fromData(png_bytes))
        self._bbox = self._page_rect = None
        self._message = message
        self.update()

    def set_loading(self, message="A preparar separações em alta qualidade…"):
        self._message = message
        self.update()

    def clear(self):
        self._pixmap = QPixmap()
        self._bbox = self._page_rect = None
        self._message = "Arraste um PDF para visualizar"
        self.reset_view()
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

    def rotate_right(self):
        self._previous_rotation = self._rotation
        self._rotation = (self._rotation + 90) % 360
        self.update()

    def undo_rotation(self):
        self._rotation, self._previous_rotation = (
            self._previous_rotation, self._rotation,
        )
        self.update()

    def reset_view(self):
        self._rotation = self._previous_rotation = 0
        self._pan = QPointF()
        self.set_zoom(1.0)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#050607"))
        if self._pixmap.isNull():
            painter.setPen(QColor(255, 255, 255, 90))
            painter.drawText(self.rect(), Qt.AlignCenter, self._message)
            return
        area = QRectF(self.rect()).adjusted(30, 18, -30, -34)
        pixmap = self._pixmap.transformed(
            QTransform().rotate(self._rotation),
            Qt.SmoothTransformation,
        ) if self._rotation else self._pixmap
        size = pixmap.size()
        size.scale(area.size().toSize(), Qt.KeepAspectRatio)
        size.setWidth(round(size.width() * self._zoom))
        size.setHeight(round(size.height() * self._zoom))
        target = QRectF(0, 0, size.width(), size.height())
        target.moveCenter(area.center() + self._pan)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.drawPixmap(target.toRect(), pixmap)
        if self._bbox and self._page_rect and not self._rotation:
            page = QRectF(
                self._page_rect[0], self._page_rect[1],
                self._page_rect[2] - self._page_rect[0],
                self._page_rect[3] - self._page_rect[1],
            )
            box = QRectF(
                self._bbox[0], self._bbox[1],
                self._bbox[2] - self._bbox[0],
                self._bbox[3] - self._bbox[1],
            )
            sx, sy = target.width() / page.width(), target.height() / page.height()
            marked = QRectF(
                target.left() + (box.left() - page.left()) * sx,
                target.top() + (box.top() - page.top()) * sy,
                box.width() * sx, box.height() * sy,
            )
            painter.setBrush(QColor(255, 75, 75, 35))
            painter.setPen(QPen(QColor("#FF4B4B"), 2))
            painter.drawRect(marked)
        painter.setPen(QColor(YELLOW))
        painter.drawText(QRectF(0, self.height() - 30, self.width(), 20),
                         Qt.AlignCenter, self._message)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self._zoom > 1.0:
            self._drag_origin = event.position()
            self.setCursor(Qt.ClosedHandCursor)
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


class ColorsWidget(QWidget):
    pdfDropped = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("toolSurface", True)
        self._path = None
        self._report = None
        self._worker = None
        self._conversion = None
        self._preview_worker = None
        self._pending_preview_key = None
        self._preview_cache = {}
        self._current_page = 0
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.timeout.connect(self._queue_separation_preview)
        self._build_ui()
        self._prepare_local_drop()
        self.setStyleSheet(TOOL_STANDARD_QSS + """
            QLabel#colorStatus { color:rgba(255,255,255,.62); }
            QLabel#colorGood { color:#75D18A; }
            QLabel#colorWarning { color:#FF9F43; }
            QListWidget#colorFindings {
                color:rgba(255,255,255,.74); background:rgba(255,255,255,.025);
                border:1px solid rgba(255,255,255,.08); border-radius:4px;
                outline:0; font-size:11px;
            }
            QListWidget#colorFindings::item { padding:3px 3px; }
            QListWidget#colorFindings::item:selected {
                color:#FFC400; background:rgba(255,196,0,.08);
            }
        """)
        apply_terminal_accent(self)
        self.clear_pdf()

    def _prepare_local_drop(self):
        for widget in (self, *self.findChildren(QWidget)):
            widget.setAcceptDrops(True)
            widget.installEventFilter(self)

    @staticmethod
    def _dropped_pdf_paths(mime_data):
        paths, seen = [], set()
        if not mime_data or not mime_data.hasUrls():
            return paths
        for url in mime_data.urls():
            if not url.isLocalFile():
                continue
            path = Path(url.toLocalFile()).expanduser()
            try:
                path = path.resolve()
            except OSError:
                pass
            key = str(path).casefold()
            if path.is_file() and path.suffix.casefold() == ".pdf" and key not in seen:
                seen.add(key)
                paths.append(str(path))
        return paths

    def eventFilter(self, watched, event):
        event_type = event.type()
        if event_type in (QEvent.DragEnter, QEvent.DragMove):
            if self._dropped_pdf_paths(event.mimeData()):
                event.acceptProposedAction()
                return True
        elif event_type == QEvent.Drop:
            paths = self._dropped_pdf_paths(event.mimeData())
            if paths:
                self.pdfDropped.emit(paths)
                event.acceptProposedAction()
                return True
        return super().eventFilter(watched, event)

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(*TOOL_PAGE_MARGINS)
        root.setSpacing(TOOL_COLUMN_SPACING)
        controls_scroll = QScrollArea()
        controls_scroll.setWidgetResizable(True)
        controls_scroll.setFrameShape(QFrame.NoFrame)
        controls_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        controls_scroll.setFixedWidth(TOOL_CONTROLS_WIDTH)
        controls = QWidget()
        controls.setProperty("toolRole", "controls")
        left = QVBoxLayout(controls)
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(TOOL_PAGE_SPACING)

        file_card, self.open_button, self.file_label = create_pdf_file_card(
            self._choose_pdf
        )
        left.addWidget(file_card)

        display_card, display = _card("MOSTRAR")
        self.mode = QComboBox()
        self.mode.addItems(("TODAS AS CORES", "CMYK", "RGB", "PANTONES"))
        self.mode.currentIndexChanged.connect(self._update_color_visibility)
        display.addWidget(self.mode)
        self.cmyk_toggle = QCheckBox("CMYK · TODAS")
        self.cmyk_toggle.toggled.connect(self._toggle_all_cmyk)
        display.addWidget(self.cmyk_toggle)
        self.color_checks = {}
        self.color_box = QWidget()
        self.color_layout = QVBoxLayout(self.color_box)
        self.color_layout.setContentsMargins(0, 0, 0, 0)
        self.color_layout.setSpacing(2)
        display.addWidget(self.color_box)
        left.addWidget(display_card)

        profile_card, profile = _card("PADRÃO DE COR DO ARQUIVO")
        self.profile_status = QLabel("Nenhum PDF analisado")
        self.profile_status.setWordWrap(True)
        self.profile_status.setObjectName("colorStatus")
        profile.addWidget(self.profile_status)
        self.pdfx_status = QLabel("")
        self.pdfx_status.setObjectName("colorStatus")
        profile.addWidget(self.pdfx_status)
        left.addWidget(profile_card)

        warning_card, warning = _card("AVISOS DE PRÉ-IMPRESSÃO")
        self.summary = QLabel("A análise exibirá imagens abaixo de 72 dpi, fontes e preto composto.")
        self.summary.setWordWrap(True)
        self.summary.setObjectName("colorStatus")
        warning.addWidget(self.summary)
        self.findings = QListWidget()
        self.findings.setObjectName("colorFindings")
        self.findings.setMinimumHeight(96)
        self.findings.setWordWrap(True)
        self.findings.setTextElideMode(Qt.ElideNone)
        self.findings.itemClicked.connect(self._show_finding)
        warning.addWidget(self.findings)
        left.addWidget(warning_card)

        convert_card, convert = _card("CONVERTER PARA CMYK")
        self.destination = QComboBox()
        self.destination.addItems((FOGRA39_LABEL, US_COATED_LABEL))
        convert.addWidget(self.destination)
        note = QLabel("Sempre cria outro PDF. Imagens não são reamostradas e a saída é validada antes de ser entregue.")
        note.setWordWrap(True)
        note.setObjectName("colorStatus")
        convert.addWidget(note)
        self.convert_button = QPushButton("SALVAR COMO CMYK")
        set_tool_role(self.convert_button, "footerAction")
        self.convert_button.setProperty("actionRole", "primary")
        self.convert_button.setEnabled(False)
        self.convert_button.clicked.connect(self._convert)
        convert.addWidget(self.convert_button, 0, Qt.AlignRight)
        left.addWidget(convert_card)
        self._document_cards = (
            display_card, profile_card, warning_card, convert_card,
        )
        left.addStretch()
        controls_scroll.setWidget(controls)
        root.addWidget(controls_scroll)

        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(TOOL_PAGE_SPACING)
        self.preview_toolbar = ToolPreviewToolbar()
        self.previous_page = self.preview_toolbar.previous_button
        self.next_page = self.preview_toolbar.next_button
        self.page_label = self.preview_toolbar.page_label
        self.preview_toolbar.previous_button.clicked.connect(
            lambda: self._change_page(-1)
        )
        self.preview_toolbar.next_button.clicked.connect(
            lambda: self._change_page(1)
        )
        self.preview_toolbar.zoom_out_button.clicked.connect(self.preview_zoom_out)
        self.preview_toolbar.zoom_in_button.clicked.connect(self.preview_zoom_in)
        self.preview_toolbar.zoom_label.clicked.connect(self.preview_reset_zoom)
        self.preview_toolbar.rotate_button.clicked.connect(self.preview_rotate)
        self.preview_toolbar.rotation_undo_button.clicked.connect(
            self.preview_undo_rotation
        )
        self.preview_toolbar.set_document_enabled(False)
        self.preview_toolbar.rotate_button.setToolTip("Girar apenas a visualização")
        self.preview_toolbar.rotation_undo_button.setToolTip(
            "Desfazer giro da visualização"
        )
        right.addWidget(self.preview_toolbar)
        self.preview = ColorPreview()
        self.preview.zoomChanged.connect(
            lambda value: self.preview_toolbar.zoom_label.setText(f"{value}%")
        )
        right.addWidget(self.preview, 1)
        root.addLayout(right, 1)
        self._preview = self.preview

    def _set_document_enabled(self, enabled):
        for widget in self._document_cards:
            set_document_control_enabled(widget, enabled)
        set_document_control_enabled(self._preview, enabled)

    def _choose_pdf(self):
        path, _ = QFileDialog.getOpenFileName(self, "Abrir PDF", "", "PDF (*.pdf)")
        if path:
            self.load_pdfs([path])

    def load_pdfs(self, paths):
        paths = list(paths or [])
        if not paths:
            self.clear_pdf()
            return
        self._path = str(Path(paths[0]).expanduser().resolve())
        self._set_document_enabled(True)
        self._report = None
        self._current_page = 0
        self._preview_cache.clear()
        self._pending_preview_key = None
        self.convert_button.setEnabled(False)
        set_open_pdf_loaded(self.open_button, True)
        self.file_label.setText(Path(self._path).name)
        self.profile_status.setText("Analisando espaços de cor e objetos…")
        self.findings.clear()
        self.preview.reset_view()
        self.preview.show_page(self._path)
        self.preview_toolbar.set_document_enabled(False)
        self.page_label.setText("Analisando…")
        self._worker = ColorWorker(self._path, self)
        self._worker.succeeded.connect(self._analysis_ready)
        self._worker.failed.connect(self._analysis_failed)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.start()

    def clear_pdf(self):
        self._path = self._report = None
        self._current_page = 0
        self._preview_cache.clear()
        self._pending_preview_key = None
        self._preview_timer.stop()
        set_open_pdf_loaded(self.open_button, False)
        self.file_label.setText("Nenhum PDF carregado")
        self.profile_status.setText("Nenhum PDF analisado")
        self.pdfx_status.clear()
        self.summary.setText("A análise exibirá imagens abaixo de 72 dpi, fontes e preto composto.")
        self.findings.clear()
        self._clear_color_checks()
        self.convert_button.setEnabled(False)
        self.preview_toolbar.set_document_enabled(False)
        self.page_label.setText("Nenhum PDF")
        self.preview.clear()
        self._set_document_enabled(False)

    def _analysis_ready(self, report):
        if report.get("path") != self._path:
            return
        self._report = report
        self.profile_status.setText(report["profile_name"])
        current = report["profile_name"].casefold()
        self.profile_status.setObjectName(
            "colorGood" if "fogra39" in current or "iso coated v2" in current
            else "colorWarning"
        )
        self.profile_status.style().unpolish(self.profile_status)
        self.profile_status.style().polish(self.profile_status)
        self.pdfx_status.setText(f'PDF/X: {report["pdfx"] or "não declarado"}')
        self._populate_colors(report["colors"])
        self._populate_findings(report)
        profile_path = report["profiles_available"].get(self.destination.currentText())
        self.convert_button.setEnabled(bool(profile_path))
        self.preview_toolbar.set_document_enabled(True)
        self.preview_toolbar.rotation_undo_button.setEnabled(True)
        self._update_page_controls()
        self._schedule_separation_preview()

    def _analysis_failed(self, message):
        self.profile_status.setText(message)
        self.profile_status.setObjectName("colorWarning")

    def _clear_color_checks(self):
        while self.color_layout.count():
            item = self.color_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.color_checks = {}
        self.cmyk_toggle.setCheckState(Qt.Unchecked)

    def _populate_colors(self, colors):
        self._clear_color_checks()
        names = []
        has_printable_content = any(
            colors.get(key) for key in ("CMYK", "RGB", "GRAY")
        ) or bool(colors.get("SPOTS"))
        if has_printable_content:
            names.extend((channel, "CMYK") for channel in ("C", "M", "Y", "K"))
        if colors.get("RGB"):
            names.append(("RGB", "RGB"))
        names.extend((name, "PANTONES") for name in colors.get("SPOTS", []))
        if not names:
            label = QLabel("Nenhuma tinta identificada")
            label.setObjectName("colorStatus")
            self.color_layout.addWidget(label)
        for name, group in names:
            checkbox = QCheckBox(name)
            checkbox.setChecked(True)
            checkbox.setProperty("colorGroup", group)
            checkbox.toggled.connect(self._color_selection_changed)
            if group == "CMYK":
                checkbox.toggled.connect(self._sync_cmyk_toggle)
            self.color_layout.addWidget(checkbox)
            self.color_checks[name] = checkbox
        apply_terminal_accent(self)
        self._sync_cmyk_toggle()
        self._update_color_visibility()

    def _toggle_all_cmyk(self, checked):
        for checkbox in self.color_checks.values():
            if checkbox.property("colorGroup") == "CMYK":
                checkbox.blockSignals(True)
                checkbox.setChecked(checked)
                checkbox.blockSignals(False)
        self._color_selection_changed()

    def _sync_cmyk_toggle(self):
        checks = [
            checkbox for checkbox in self.color_checks.values()
            if checkbox.property("colorGroup") == "CMYK"
        ]
        state = Qt.Checked if checks and all(
            checkbox.isChecked() for checkbox in checks
        ) else Qt.Unchecked
        self.cmyk_toggle.blockSignals(True)
        self.cmyk_toggle.setCheckState(state)
        self.cmyk_toggle.blockSignals(False)

    def _update_color_visibility(self):
        mode = self.mode.currentText()
        self.cmyk_toggle.setVisible(mode in ("TODAS AS CORES", "CMYK"))
        for checkbox in self.color_checks.values():
            group = checkbox.property("colorGroup")
            checkbox.setVisible(mode == "TODAS AS CORES" or group == mode)
        self._color_selection_changed()

    def _color_selection_changed(self):
        if not self._path or not self._report:
            return
        mode = self.mode.currentText()
        if mode == "RGB":
            rgb = self.color_checks.get("RGB")
            if rgb is not None and rgb.isChecked():
                self.preview.show_page(self._path, self._current_page + 1)
                self.preview._message = "RGB · espaço de origem (não é chapa)"
                self.preview.update()
                return
        self._schedule_separation_preview()

    def _selected_colorants(self):
        aliases = {"C": "Cyan", "M": "Magenta", "Y": "Yellow", "K": "Black"}
        mode = self.mode.currentText()
        result = []
        for name, checkbox in self.color_checks.items():
            group = checkbox.property("colorGroup")
            if not checkbox.isChecked():
                continue
            if mode != "TODAS AS CORES" and group != mode:
                continue
            if name == "RGB":
                continue
            result.append(aliases.get(name, name))
        return tuple(result)

    def _schedule_separation_preview(self):
        if self._path and self._report:
            self._preview_timer.start(120)

    def _queue_separation_preview(self):
        key = (self._path, self._current_page + 1, self._selected_colorants())
        cached = self._preview_cache.get(key)
        if cached:
            self._show_separation_result(key, cached)
            return
        self._pending_preview_key = key
        self.preview.set_loading()
        if self._preview_worker is None:
            self._start_pending_preview()

    def _start_pending_preview(self):
        key = self._pending_preview_key
        self._pending_preview_key = None
        if key is None:
            return
        self._preview_worker = SeparationWorker(key, self)
        self._preview_worker.succeeded.connect(self._separation_ready)
        self._preview_worker.failed.connect(self._separation_failed)
        self._preview_worker.finished.connect(self._separation_finished)
        self._preview_worker.start()

    def _separation_ready(self, key, png_bytes):
        if len(self._preview_cache) >= 12:
            self._preview_cache.pop(next(iter(self._preview_cache)))
        self._preview_cache[key] = png_bytes
        current_key = (
            self._path, self._current_page + 1, self._selected_colorants(),
        )
        if key == current_key:
            self._show_separation_result(key, png_bytes)

    def _show_separation_result(self, key, png_bytes):
        selected = key[2]
        labels = {
            "Cyan": "C", "Magenta": "M", "Yellow": "Y", "Black": "K",
        }
        names = [labels.get(name, name) for name in selected]
        suffix = ", ".join(names) if names else "nenhuma chapa"
        self.preview.show_image(png_bytes, f"CHAPAS ATIVAS · {suffix}")

    def _separation_failed(self, key, message):
        current_key = (
            self._path, self._current_page + 1, self._selected_colorants(),
        )
        if key == current_key:
            self.preview.show_page(self._path, self._current_page + 1)
            self.preview._message = f"Prévia de separações indisponível · {message}"
            self.preview.update()

    def _separation_finished(self):
        worker = self._preview_worker
        self._preview_worker = None
        if worker is not None:
            worker.deleteLater()
        if self._pending_preview_key is not None:
            self._start_pending_preview()

    def _change_page(self, offset):
        if not self._report:
            return
        target = max(0, min(
            self._current_page + offset, self._report["pages"] - 1,
        ))
        if target == self._current_page:
            return
        self._current_page = target
        self.preview.reset_view()
        self._update_page_controls()
        if self.mode.currentText() == "RGB":
            self._color_selection_changed()
        else:
            self._schedule_separation_preview()

    def _update_page_controls(self):
        pages = self._report["pages"] if self._report else 0
        self.page_label.setText(
            f"Página {self._current_page + 1} de {pages}" if pages else "Nenhum PDF"
        )
        self.previous_page.setEnabled(self._current_page > 0)
        self.next_page.setEnabled(self._current_page + 1 < pages)

    def preview_zoom_out(self):
        self.preview.zoom_out()

    def preview_zoom_in(self):
        self.preview.zoom_in()

    def preview_reset_zoom(self):
        self.preview.reset_zoom()

    def preview_rotate(self):
        self.preview.rotate_right()

    def preview_undo_rotation(self):
        self.preview.undo_rotation()

    def _populate_findings(self, report):
        self.findings.clear()
        spots = report["colors"].get("SPOTS", [])
        if spots:
            spot_message = (
                f'⚠ {len(spots)} spot/Pantone: ' + ", ".join(spots)
            )
            item = QListWidgetItem(
                spot_message
            )
            item.setToolTip(spot_message)
            item.setData(Qt.UserRole, {"page": 1})
            self.findings.addItem(item)
        profile_name = report["profile_name"].casefold()
        if "fogra39" not in profile_name and "iso coated v2" not in profile_name:
            item = QListWidgetItem(
                "⚠ Perfil diferente de Coated FOGRA39"
            )
            item.setData(Qt.UserRole, {"page": 1})
            self.findings.addItem(item)
        for image in report["low_resolution"]:
            item = QListWidgetItem(
                f'⚠ Pág. {image["page"]} · imagem {image["index"]} · {image["dpi"]:.1f} dpi'
            )
            item.setData(Qt.UserRole, {"page": image["page"], "bbox": image["bbox"]})
            self.findings.addItem(item)
        for finding in report["composite_black"]:
            item = QListWidgetItem(f'⚠ Pág. {finding["page"]} · {finding["message"]}')
            item.setData(Qt.UserRole, {"page": finding["page"]})
            self.findings.addItem(item)
        for font in report["unembedded_fonts"]:
            pages = ", ".join(str(page) for page in font["pages"])
            item = QListWidgetItem(f'⚠ Fonte não incorporada · {font["name"]} · pág. {pages}')
            item.setData(Qt.UserRole, {"page": font["pages"][0]})
            self.findings.addItem(item)
        count = self.findings.count()
        self.summary.setText(
            "Nenhum risco automático encontrado."
            if not count else f"{count} aviso(s). Clique em um item para localizar no PDF."
        )

    def _show_finding(self, item):
        data = item.data(Qt.UserRole) or {}
        if self._path:
            page = data.get("page", 1)
            self._current_page = max(0, page - 1)
            self.preview.reset_view()
            self._update_page_controls()
            self.preview.show_page(self._path, page, data.get("bbox"))

    def _convert(self):
        if not self._path or not self._report:
            return
        profile = self.destination.currentText()
        if not self._report["profiles_available"].get(profile):
            QMessageBox.warning(self, "Perfil ausente", f"O perfil {profile} não está instalado.")
            return
        source = Path(self._path)
        suggested = source.with_name(f"{source.stem}_CMYK.pdf")
        output, _ = QFileDialog.getSaveFileName(
            self, "Salvar PDF convertido", save_path(suggested), "PDF (*.pdf)",
        )
        if not output:
            return
        if Path(output).resolve() == source:
            QMessageBox.warning(self, "Salvar Como", "Escolha outro nome. O original será preservado.")
            return
        answer = QMessageBox.question(
            self, "Confirmar conversão CMYK",
            f"Converter todos os objetos e Pantones para:\n{profile}\n\n"
            "A saída será validada e o original não será alterado.",
        )
        if answer != QMessageBox.Yes:
            return
        self.convert_button.setEnabled(False)
        self.convert_button.setText("CONVERTENDO…")
        self._conversion = ConversionWorker(self._path, output, profile, self)
        self._conversion.succeeded.connect(self._conversion_ready)
        self._conversion.failed.connect(self._conversion_failed)
        self._conversion.finished.connect(self._conversion.deleteLater)
        self._conversion.start()

    def _conversion_ready(self, result):
        self.convert_button.setText("SALVAR COMO CMYK")
        self.convert_button.setEnabled(True)
        show_button_success(self.convert_button, restore_text="SALVAR COMO CMYK")

    def _conversion_failed(self, message):
        self.convert_button.setText("SALVAR COMO CMYK")
        self.convert_button.setEnabled(True)
        QMessageBox.critical(
            self, "Conversão cancelada",
            f"Nenhum PDF final foi entregue porque a validação falhou.\n\n{message}",
        )
