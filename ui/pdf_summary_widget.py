from pathlib import Path

import fitz
from PySide6.QtCore import QSize, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QPlainTextEdit, QPushButton, QScrollArea,
    QSizePolicy, QVBoxLayout, QWidget,
)

from core.pdf_info import analisar_pdf
from core.pdf_summary import build_job_summary
from core.spot_colors import spot_srgb
from ui.tool_design import (
    TOOL_CARD_MARGINS, TOOL_CARD_SPACING, TOOL_COLUMN_SPACING,
    TOOL_CONTROLS_WIDTH, TOOL_PAGE_MARGINS, TOOL_PAGE_SPACING,
    TOOL_STANDARD_QSS, ToolPreviewToolbar, apply_terminal_accent,
    create_pdf_file_card, set_document_control_enabled, set_open_pdf_loaded,
    set_tool_role,
)


class PdfSummaryWorker(QThread):
    firstThumbnailReady = Signal(str, bytes)
    analyzed = Signal(str, object)
    thumbnailsReady = Signal(str, object)
    failed = Signal(str, str)

    def __init__(self, path, supplied_info=None, first_thumbnail=b"", parent=None):
        super().__init__(parent)
        self.path = str(path)
        self.supplied_info = supplied_info
        self.first_thumbnail = first_thumbnail

    def run(self):
        try:
            first_bytes = self.first_thumbnail
            if not first_bytes:
                with fitz.open(self.path) as document:
                    if not document.page_count:
                        first_bytes = b""
                    else:
                        page = document[0]
                        scale = min(
                            0.7,
                            360.0 / max(page.rect.width, page.rect.height, 1.0),
                        )
                        first = page.get_pixmap(
                            matrix=fitz.Matrix(scale, scale), alpha=False,
                        )
                        first_bytes = first.tobytes("png")
                        self.firstThumbnailReady.emit(self.path, first_bytes)
            info = self.supplied_info or analisar_pdf(self.path)
            self.analyzed.emit(self.path, info)
            thumbnails = []
            with fitz.open(self.path) as document:
                for page in document:
                    # A primeira imagem reduzida serve somente para a resposta
                    # imediata. A lista definitiva precisa renderizar todas as
                    # páginas na mesma escala para manter dimensões idênticas.
                    pixmap = page.get_pixmap(
                        matrix=fitz.Matrix(0.9, 0.9), alpha=False,
                    )
                    thumbnails.append(pixmap.tobytes("png"))
            self.thumbnailsReady.emit(self.path, thumbnails)
        except Exception as error:
            self.failed.emit(self.path, str(error))


class PdfSummaryWidget(QWidget):
    """Resumo editável e visão geral do PDF compartilhado pelas ferramentas."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._path = None
        self._info = None
        self._page_pixmaps = []
        self._worker = None
        self._thumbnail_zoom = 0.75
        self._build_ui()
        self.setStyleSheet(TOOL_STANDARD_QSS + self._qss())
        apply_terminal_accent(self)
        self.clear_pdf()

    @staticmethod
    def _card(title):
        frame = QFrame()
        set_tool_role(frame, "card")
        frame.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(*TOOL_CARD_MARGINS)
        layout.setSpacing(TOOL_CARD_SPACING)
        caption = QLabel(title)
        set_tool_role(caption, "cardTitle")
        layout.addWidget(caption)
        return frame, layout

    @staticmethod
    def _value_label():
        label = QLabel("—")
        label.setObjectName("summaryValue")
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        return label

    @staticmethod
    def _button(text, callback):
        button = QPushButton(text)
        set_tool_role(button, "chip")
        button.clicked.connect(callback)
        return button

    def _build_ui(self):
        self.setProperty("toolSurface", True)
        root = QHBoxLayout(self)
        root.setContentsMargins(*TOOL_PAGE_MARGINS)
        root.setSpacing(TOOL_COLUMN_SPACING)

        scroll = QScrollArea()
        scroll.setObjectName("summaryScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFixedWidth(TOOL_CONTROLS_WIDTH)
        controls = QWidget()
        set_tool_role(controls, "controls")
        controls_layout = QVBoxLayout(controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(TOOL_PAGE_SPACING)

        file_card, self.open_button, self.file_name = create_pdf_file_card(
            self._choose_pdf
        )
        controls_layout.addWidget(file_card)

        summary_card, summary_layout = self._card("RESUMO")
        self.job_summary = QPlainTextEdit()
        self.job_summary.setObjectName("summaryJobText")
        self.job_summary.setPlaceholderText("Descrição para a ordem de trabalho")
        self.job_summary.setFixedHeight(62)
        summary_layout.addWidget(self.job_summary)
        summary_actions = QHBoxLayout()
        summary_actions.setSpacing(6)
        summary_actions.addStretch()
        self.clear_summary_button = self._button("LIMPAR", self.job_summary.clear)
        self.copy_summary_button = self._button("COPIAR", self._copy_summary)
        summary_actions.addWidget(self.clear_summary_button)
        summary_actions.addWidget(self.copy_summary_button)
        summary_layout.addLayout(summary_actions)
        controls_layout.addWidget(summary_card)

        document_card, document_layout = self._card("DOCUMENTO")
        document_grid = QGridLayout()
        document_grid.setContentsMargins(0, 2, 0, 0)
        document_grid.setHorizontalSpacing(16)
        document_grid.setVerticalSpacing(7)
        self.document_values = {}
        for row, (key, title) in enumerate((
            ("paginas", "PÁGINAS"), ("peso", "TAMANHO"),
            ("orientacao", "ORIENTAÇÃO"), ("criado_em", "CRIADO POR"),
        )):
            caption = QLabel(title)
            caption.setObjectName("summaryFieldLabel")
            value = self._value_label()
            self.document_values[key] = value
            document_grid.addWidget(caption, row, 0)
            document_grid.addWidget(value, row, 1)
        document_grid.setColumnStretch(1, 1)
        document_layout.addLayout(document_grid)
        controls_layout.addWidget(document_card)

        boxes_card, boxes_layout = self._card("DIMENSÕES")
        boxes_grid = QGridLayout()
        boxes_grid.setContentsMargins(0, 2, 0, 0)
        boxes_grid.setHorizontalSpacing(16)
        boxes_grid.setVerticalSpacing(7)
        self.box_values = {}
        for row, (key, title) in enumerate((
            ("medida_pdf", "MEDIABOX"), ("medida_trim", "TRIMBOX"),
        )):
            caption = QLabel(title)
            caption.setObjectName("summaryFieldLabel")
            value = self._value_label()
            self.box_values[key] = value
            boxes_grid.addWidget(caption, row, 0)
            boxes_grid.addWidget(value, row, 1)
        boxes_grid.setColumnStretch(1, 1)
        boxes_layout.addLayout(boxes_grid)
        self.show_media_box = QCheckBox("EXIBIR LINHA DA MEDIABOX")
        self.show_trim_box = QCheckBox("EXIBIR LINHA DA TRIMBOX")
        self.show_media_box.toggled.connect(self._refresh_thumbnails)
        self.show_trim_box.toggled.connect(self._refresh_thumbnails)
        boxes_layout.addWidget(self.show_media_box)
        boxes_layout.addWidget(self.show_trim_box)
        controls_layout.addWidget(boxes_card)

        colors_card, self.colors_layout = self._card("CORES")
        self.colors_empty = self._value_label()
        self.colors_layout.addWidget(self.colors_empty)
        self._color_rows = []
        controls_layout.addWidget(colors_card)
        alerts_card, alerts_layout = self._card("VERIFICAÇÃO RÁPIDA")
        self.alerts_value = self._value_label()
        alerts_layout.addWidget(self.alerts_value)
        controls_layout.addWidget(alerts_card)
        self._document_cards = (
            summary_card, document_card, boxes_card, colors_card, alerts_card,
        )
        controls_layout.addStretch()
        scroll.setWidget(controls)

        preview_frame = QFrame()
        preview_frame.setObjectName("summaryPreviewFrame")
        preview_layout = QVBoxLayout(preview_frame)
        preview_layout.setContentsMargins(12, 12, 12, 12)
        preview_layout.setSpacing(8)
        preview_title = QLabel("PRÉVIA · TODAS AS PÁGINAS")
        preview_title.setObjectName("summaryPreviewTitle")
        self.preview_toolbar = ToolPreviewToolbar()
        for widget in (
            self.preview_toolbar.previous_button, self.preview_toolbar.page_label,
            self.preview_toolbar.next_button,
            self.preview_toolbar.rotation_undo_button,
            self.preview_toolbar.rotate_button,
        ):
            widget.hide()
        self.preview_toolbar.zoom_out_button.clicked.connect(
            lambda: self._set_thumbnail_zoom(self._thumbnail_zoom - 0.25)
        )
        self.preview_toolbar.zoom_label.clicked.connect(
            lambda: self._set_thumbnail_zoom(0.75)
        )
        self.preview_toolbar.zoom_in_button.clicked.connect(
            lambda: self._set_thumbnail_zoom(self._thumbnail_zoom + 0.25)
        )
        self.pages = QListWidget()
        self.pages.setObjectName("summaryPages")
        self.pages.setViewMode(QListWidget.IconMode)
        self.pages.setResizeMode(QListWidget.Adjust)
        self.pages.setMovement(QListWidget.Static)
        self.pages.setSelectionMode(QListWidget.NoSelection)
        self.pages.setSpacing(4)
        preview_layout.addWidget(preview_title)
        preview_layout.addWidget(self.preview_toolbar)
        preview_layout.addWidget(self.pages, 1)
        root.addWidget(scroll)
        root.addWidget(preview_frame, 1)
        self._preview_frame = preview_frame

    def _choose_pdf(self):
        path, _ = QFileDialog.getOpenFileName(self, "Abrir PDF", "", "PDF (*.pdf)")
        if path:
            self.load_pdfs([path])

    def _set_document_enabled(self, enabled):
        for widget in (*self._document_cards, self._preview_frame):
            set_document_control_enabled(widget, enabled)

    def load_pdfs(self, paths, info=None):
        paths = list(paths or [])
        if not paths:
            self.clear_pdf()
            return
        self._path = str(Path(paths[0]).expanduser())
        set_open_pdf_loaded(self.open_button, True)
        self._set_document_enabled(True)
        self.file_name.setText(Path(self._path).name)
        self.alerts_value.setText("Analisando PDF…")
        self.pages.clear()
        self._page_pixmaps = []
        self.preview_toolbar.set_document_enabled(False)
        first_thumbnail = self._render_fast_preview(self._path)
        if first_thumbnail:
            self._first_thumbnail_ready(self._path, first_thumbnail)
        worker = PdfSummaryWorker(
            self._path, info, first_thumbnail, self,
        )
        worker.firstThumbnailReady.connect(self._first_thumbnail_ready)
        worker.analyzed.connect(self._analysis_ready)
        worker.thumbnailsReady.connect(self._thumbnails_ready)
        worker.failed.connect(self._analysis_failed)
        worker.finished.connect(worker.deleteLater)
        self._worker = worker
        worker.start()

    @staticmethod
    def _render_fast_preview(path):
        try:
            with fitz.open(path) as document:
                if not document.page_count:
                    return b""
                page = document[0]
                scale = min(
                    0.55,
                    360.0 / max(page.rect.width, page.rect.height, 1.0),
                )
                pixmap = page.get_pixmap(
                    matrix=fitz.Matrix(scale, scale), alpha=False,
                )
                return pixmap.tobytes("png")
        except Exception:
            return b""

    def _first_thumbnail_ready(self, path, data):
        if path != self._path or not data:
            return
        image = QImage.fromData(data)
        if image.isNull():
            return
        self._page_pixmaps = [QPixmap.fromImage(image)]
        self._refresh_thumbnails()
        self._set_thumbnail_zoom(0.75)
        self.preview_toolbar.set_document_enabled(True)

    def _analysis_ready(self, path, info):
        if path != self._path:
            return
        self.set_info(info)

    def _thumbnails_ready(self, path, thumbnails):
        if path != self._path:
            return
        self._page_pixmaps = [
            QPixmap.fromImage(QImage.fromData(data)) for data in thumbnails
        ]
        self._refresh_thumbnails()
        self._set_thumbnail_zoom(0.75)
        self.preview_toolbar.set_document_enabled(True)

    def _analysis_failed(self, path, error):
        if path != self._path:
            return
        self.alerts_value.setText(f"Não foi possível analisar o PDF.\n{error}")

    def set_info(self, info):
        self._info = info
        self.file_name.setText(str(info.get("nome", Path(self._path).name)))
        for key, label in self.document_values.items():
            label.setText(str(info.get(key, "Não informado")))
        for key, label in self.box_values.items():
            label.setText(str(info.get(key, "Não informado")))

        colors = info.get("cores", {})
        spots = sorted(str(color) for color in colors.get("SPOTS", []))
        self._set_color_indicators(colors, spots)
        self.alerts_value.setText("\n".join((
            f'{"✓" if info.get("tem_trim") else "—"} TrimBox definido',
            f'{"✓" if info.get("tem_bleed") else "—"} BleedBox definido',
            f'{"✓" if info.get("marcas_corte") else "—"} Marcas de corte detectadas',
        )))
        self.job_summary.setPlainText(build_job_summary(info))

    def _refresh_thumbnails(self):
        scroll_position = self.pages.verticalScrollBar().value()
        self.pages.clear()
        boxes = (self._info or {}).get("boxes", [])
        for index, source in enumerate(self._page_pixmaps):
            pixmap = QPixmap(source)
            painter = QPainter(pixmap)
            painter.setBrush(Qt.NoBrush)
            if self.show_media_box.isChecked():
                painter.setPen(QPen(QColor("#FFC400"), 2, Qt.DashLine))
                painter.drawRect(pixmap.rect().adjusted(2, 2, -3, -3))
            if self.show_trim_box.isChecked() and index < len(boxes):
                media = boxes[index].get("media", (1, 1))
                trim = boxes[index].get("trim", media)
                width_ratio = min(1.0, trim[0] / max(media[0], 0.01))
                height_ratio = min(1.0, trim[1] / max(media[1], 0.01))
                trim_width = pixmap.width() * width_ratio
                trim_height = pixmap.height() * height_ratio
                left = (pixmap.width() - trim_width) / 2
                top = (pixmap.height() - trim_height) / 2
                painter.setPen(QPen(QColor("#FF6262"), 2, Qt.DashLine))
                painter.drawRect(round(left), round(top), round(trim_width), round(trim_height))
            painter.end()
            item = QListWidgetItem(QIcon(pixmap), f"PÁGINA {index + 1}")
            item.setTextAlignment(Qt.AlignHCenter)
            self.pages.addItem(item)
        self.pages.verticalScrollBar().setValue(scroll_position)
        self._set_thumbnail_zoom(self._thumbnail_zoom)

    def _set_thumbnail_zoom(self, zoom):
        self._thumbnail_zoom = min(1.5, max(0.25, zoom))
        max_width = round(520 * self._thumbnail_zoom)
        max_height = round(680 * self._thumbnail_zoom)
        self.pages.setIconSize(QSize(max_width, max_height))
        self.pages.setGridSize(QSize())
        for index, source in enumerate(self._page_pixmaps):
            if index >= self.pages.count() or source.isNull():
                continue
            scale = min(max_width / source.width(), max_height / source.height())
            display_width = round(source.width() * scale)
            display_height = round(source.height() * scale)
            self.pages.item(index).setSizeHint(QSize(
                display_width + 30,
                display_height + 48,
            ))
        self.preview_toolbar.zoom_label.setText(f"{round(self._thumbnail_zoom * 100)}%")

    @staticmethod
    def _cmyk_icon():
        pixmap = QPixmap(18, 18)
        painter = QPainter(pixmap)
        for color, x, y in (
            ("#00AEEF", 0, 0), ("#EC008C", 9, 0),
            ("#FFF200", 0, 9), ("#231F20", 9, 9),
        ):
            painter.fillRect(x, y, 9, 9, QColor(color))
        painter.end()
        return pixmap

    def _clear_color_indicators(self):
        for row in self._color_rows:
            self.colors_layout.removeWidget(row)
            row.deleteLater()
        self._color_rows.clear()

    def _set_color_indicators(self, colors, spots):
        self._clear_color_indicators()
        self.colors_empty.setVisible(False)
        has_indicator = False
        if colors.get("CMYK"):
            row = QWidget()
            layout = QHBoxLayout(row)
            layout.setContentsMargins(0, 2, 0, 2)
            layout.setSpacing(8)
            icon = QLabel()
            icon.setPixmap(self._cmyk_icon())
            label = QLabel("CMYK")
            label.setObjectName("summaryColorName")
            layout.addWidget(icon)
            layout.addWidget(label)
            layout.addStretch()
            self.colors_layout.addWidget(row)
            self._color_rows.append(row)
            has_indicator = True
        for spot in spots:
            row = QWidget()
            layout = QHBoxLayout(row)
            layout.setContentsMargins(0, 2, 0, 2)
            layout.setSpacing(8)
            swatch = QLabel()
            swatch.setObjectName("summarySpotSwatch")
            swatch.setFixedSize(18, 18)
            swatch.setStyleSheet(
                f"background:{spot_srgb(spot)}; border:1px solid rgba(255,255,255,.24);"
            )
            label = QLabel(spot)
            label.setObjectName("summaryColorName")
            layout.addWidget(swatch)
            layout.addWidget(label)
            layout.addStretch()
            self.colors_layout.addWidget(row)
            self._color_rows.append(row)
            has_indicator = True
        if not has_indicator:
            self.colors_empty.setText("Nenhuma cor detectada")
            self.colors_empty.setVisible(True)

    def _copy_summary(self):
        text = self.job_summary.toPlainText().strip()
        if text:
            QApplication.clipboard().setText(text)
            self.copy_summary_button.setText("COPIADO")
            QTimer.singleShot(1200, lambda: self.copy_summary_button.setText("COPIAR"))

    def clear_pdf(self):
        self._path = None
        self._info = None
        self._page_pixmaps = []
        self.file_name.setText("Nenhum PDF carregado")
        set_open_pdf_loaded(self.open_button, False)
        self.job_summary.clear()
        for label in (*self.document_values.values(), *self.box_values.values()):
            label.setText("—")
        self._clear_color_indicators()
        self.colors_empty.setText("—")
        self.colors_empty.setVisible(True)
        self.alerts_value.setText("Aguardando arquivo")
        self.pages.clear()
        self.preview_toolbar.set_document_enabled(False)
        self.preview_toolbar.zoom_label.setText("75%")
        self._set_document_enabled(False)

    @staticmethod
    def _qss():
        return """
        QScrollArea#summaryScroll { background:transparent; border:0; }
        QLabel#summaryFileName { color:#FFC400; font-size:11px; font-weight:700; }
        QLabel#summaryFilePath { color:rgba(255,255,255,.42); font-size:9px; }
        QLabel#summaryFieldLabel { color:rgba(255,255,255,.43); font-size:9px; }
        QLabel#summaryValue { color:rgba(255,255,255,.84); font-size:10px; }
        QLabel#summaryColorName { color:rgba(255,255,255,.84); font-size:10px; }
        QPlainTextEdit#summaryJobText { color:rgba(255,255,255,.88); background:rgba(255,255,255,.055); border:1px solid rgba(255,255,255,.10); border-radius:4px; padding:6px; }
        QFrame#summaryPreviewFrame { background:#050607; border:1px solid rgba(255,255,255,.06); }
        QLabel#summaryPreviewTitle { color:rgba(255,196,0,.72); font-size:10px; font-weight:700; }
        QListWidget#summaryPages { background:#050607; border:0; color:rgba(255,255,255,.58); outline:0; padding:8px; }
        QListWidget#summaryPages::item { background:rgba(255,255,255,.025); border:1px solid rgba(255,255,255,.08); border-radius:5px; padding:7px; }
        """
