from __future__ import annotations

import json
import math
from pathlib import Path

import fitz
from PySide6.QtCore import (
    QEvent, QPoint, QPointF, QRectF, QSettings, Qt, QTimer, Signal,
)
from PySide6.QtGui import QColor, QCursor, QFont, QIcon, QImage, QPainter, QPen, QPixmap, QTransform
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QHeaderView,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QProgressBar,
    QRadioButton,
    QSizeGrip,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.imposition import (
    ImpositionError,
    LayoutOption,
    PdfGeometry,
    automatic_filename,
    automatic_sheet_label,
    build_custom_layout,
    calculate_layouts,
    calculate_plans,
    export_imposition,
    inspect_pdf,
    effective_bleed_rect,
    open_pdf_for_imposition,
)
from core.print_log import make_entry
from ui.geometry_widget import FIXED_FORMATS
from ui.print_log_dialog import PrintLogDialog
from ui.tool_design import (
    TOOL_CHIP_HEIGHT, TOOL_CONTROLS_WIDTH, TOOL_STANDARD_QSS,
    ToolSuggestionButton, configure_measure_swap, set_tool_role,
)
from ui.widgets import DarkMetallicTitleBar

ROOT = Path(__file__).resolve().parent.parent
YELLOW = "#FFC400"


class DropPanel(QFrame):
    fileDropped = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setObjectName("impDropPanel")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(8)
        self.icon = QLabel()
        self.icon.setObjectName("impDropIcon")
        self.icon.setFixedSize(30, 30)
        self.icon.setPixmap(self._build_pdf_download_icon())
        self.title = QLabel("ARRASTE OU CLIQUE PARA ESCOLHER\nUM OU MAIS PDFs")
        self.title.setObjectName("impDropTitle")
        self.title.setWordWrap(True)
        self.icon.setAlignment(Qt.AlignCenter)
        self.title.setAlignment(Qt.AlignCenter)
        layout.addStretch()
        layout.addWidget(self.icon, 0, Qt.AlignVCenter)
        layout.addWidget(self.title)
        layout.addStretch()

    def _build_pdf_download_icon(self) -> QPixmap:
        """Desenha um ícone compacto de PDF com seta, sem ultrapassar o canvas."""
        pixmap = QPixmap(30, 30)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing, True)

        pen = QPen(QColor(YELLOW), 1.6)
        pen.setJoinStyle(Qt.RoundJoin)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)

        # Documento compacto, inteiramente contido no canvas.
        painter.drawLine(5, 3, 17, 3)
        painter.drawLine(5, 3, 5, 24)
        painter.drawLine(5, 24, 15, 24)
        painter.drawLine(17, 3, 23, 9)
        painter.drawLine(23, 9, 23, 16)
        painter.drawLine(17, 3, 17, 9)
        painter.drawLine(17, 9, 23, 9)

        # Seta curta, com folga real em todas as bordas.
        painter.drawLine(20, 15, 20, 25)
        painter.drawLine(16, 21, 20, 25)
        painter.drawLine(24, 21, 20, 25)
        painter.end()
        return pixmap

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.fileDropped.emit("")
        super().mousePressEvent(event)

    def _pdf_paths_from_mime(self, mime_data):
        paths = []
        for url in mime_data.urls():
            path = Path(url.toLocalFile())
            if path.is_file() and path.suffix.lower() == ".pdf":
                paths.append(str(path))
        return paths

    def _install_drop_filters(self):
        # QTableWidget, QLineEdit e outros filhos aceitam o evento antes do diálogo.
        # Instalamos o mesmo filtro em toda a árvore para que soltar PDFs funcione
        # literalmente em qualquer ponto da janela.
        for widget in [self, *self.findChildren(QWidget)]:
            widget.setAcceptDrops(True)
            widget.installEventFilter(self)

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Type.DragEnter, QEvent.Type.DragMove):
            paths = self._pdf_paths_from_mime(event.mimeData())
            if paths:
                event.acceptProposedAction()
                return True
        elif event.type() == QEvent.Type.Drop:
            paths = self._pdf_paths_from_mime(event.mimeData())
            if paths:
                self.fileDropped.emit(paths)
                event.acceptProposedAction()
                return True
        return super().eventFilter(watched, event)

    def dragEnterEvent(self, event):
        paths = self._pdf_paths_from_mime(event.mimeData())
        if paths and all(path.lower().endswith(".pdf") for path in paths):
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = self._pdf_paths_from_mime(event.mimeData())
        if paths:
            self.fileDropped.emit(paths)
            event.acceptProposedAction()


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
        painter.fillRect(self.rect(), QColor(8, 10, 13))
        if not self.layout_option:
            painter.setPen(QColor(255, 255, 255, 95))
            painter.drawText(self.rect(), Qt.AlignCenter, "Arraste um PDF para visualizar a imposição")
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
            if self.mode == "repeat":
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
            pixmap = self.thumbnails[source_index] if source_index < len(self.thumbnails) else None
            if pixmap and not pixmap.isNull():
                transformed = pixmap.transformed(QTransform().rotate(90)) if option.rotated else pixmap
                painter.drawPixmap(bleed_rect.toRect(), transformed)
            else:
                painter.fillRect(bleed_rect, QColor(220, 220, 215))

            if self.mode == "sequential":
                painter.setBrush(QColor(0, 0, 0, 150))
                badge = QRectF(rect.left() + 3, rect.top() + 3, 30, 17)
                painter.drawRoundedRect(badge, 3, 3)
                painter.setPen(QColor(255, 255, 255))
                painter.drawText(badge, Qt.AlignCenter, str(source_index + 1))

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


class ImpositionDialog(QDialog):
    pdfStateChanged = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings = QSettings("M87Tools", "M87Terminal")
        self.drag_position = QPoint()
        self.pdf_path: Path | None = None
        self.naming_path: Path | None = None
        self.geometry_info: PdfGeometry | None = None
        self.options: list[LayoutOption] = []
        self.selected_option = 0
        self.manual_override = False
        self.current_sheet = 0
        self.thumbnails: list[QPixmap] = []
        self.batch_items: list[dict] = []
        self.batch_mode = False
        self.batch_cancelled = False
        self._updating_batch_table = False
        self.legend_customized = False
        self.filename_customized = False
        self._geometry_save_timer = QTimer(self)
        self._geometry_save_timer.setSingleShot(True)
        self._geometry_save_timer.timeout.connect(self._save_geometry)
        self._setup_window()
        self._build_ui()
        self._style()
        self._connect()
        self._install_drop_filters()
        self._restore_geometry()
        self.recalculate()

    def _setup_window(self):
        self.setWindowTitle("IMP · MONTAR IMPOSIÇÃO")
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAcceptDrops(True)
        self.setMinimumSize(1040, 650)
        self.resize(1180, 720)
        icon = ROOT / "assets" / "m87_icon.png"
        if icon.exists():
            self.setWindowIcon(QIcon(str(icon)))

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.box = QWidget()
        self.box.setObjectName("impBox")
        self.box.setProperty("toolSurface", True)
        outer.addWidget(self.box)
        root = QVBoxLayout(self.box)
        root.setContentsMargins(0, 0, 0, 8)
        root.setSpacing(5)

        bar = DarkMetallicTitleBar(height=28, radius=12)
        bar.setObjectName("impTitleBar")
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(14, 0, 10, 0)
        title = QLabel("M87 TERMINAL")
        title.setObjectName("impWindowTitle")
        close = QLabel("×")
        close.setObjectName("impClose")
        close.setCursor(QCursor(Qt.PointingHandCursor))
        close.mousePressEvent = lambda event: self.close()
        bar_layout.addWidget(title)
        bar_layout.addStretch()
        bar_layout.addWidget(close)
        root.addWidget(bar)
        bar.mousePressEvent = self._title_press
        bar.mouseMoveEvent = self._title_move

        body = QHBoxLayout()
        body.setContentsMargins(14, 12, 14, 4)
        body.setSpacing(12)
        body.addWidget(self._left_panel(), 0)

        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(7)
        self.batch_panel = self._batch_panel()
        self.batch_panel.hide()
        center_layout.addWidget(self.batch_panel, 0)
        center_layout.addWidget(self._sheet_identification_panel(), 0)
        zoom_row = QHBoxLayout()
        zoom_row.addStretch()
        self.zoom_out_button = QPushButton("−")
        self.zoom_label = QPushButton("100%")
        self.zoom_in_button = QPushButton("+")
        for button in (
            self.zoom_out_button, self.zoom_label, self.zoom_in_button,
        ):
            button.setObjectName("impZoom")
        self.zoom_out_button.setFixedWidth(28)
        self.zoom_label.setFixedWidth(48)
        self.zoom_in_button.setFixedWidth(28)
        zoom_row.addWidget(self.zoom_out_button)
        zoom_row.addWidget(self.zoom_label)
        zoom_row.addWidget(self.zoom_in_button)
        zoom_row.addStretch()
        center_layout.addLayout(zoom_row)
        self.preview = PreviewWidget()
        center_layout.addWidget(self.preview, 1)
        center_layout.addWidget(self._filename_panel(), 0)
        nav = QHBoxLayout()
        self.prev_sheet = QPushButton("‹ ANTERIOR")
        self.prev_sheet.setObjectName("impNav")
        self.sheet_label = QLabel("Montagem —")
        self.sheet_label.setObjectName("impSheetLabel")
        self.sheet_label.setAlignment(Qt.AlignCenter)
        self.next_sheet = QPushButton("PRÓXIMA ›")
        self.next_sheet.setObjectName("impNav")
        nav.addWidget(self.prev_sheet)
        nav.addWidget(self.sheet_label, 1)
        nav.addWidget(self.next_sheet)
        center_layout.addLayout(nav)
        body.addWidget(center, 1)
        body.addWidget(self._right_panel(), 0)
        root.addLayout(body, 1)

        grip_row = QHBoxLayout()
        grip_row.addStretch()
        grip_row.addWidget(QSizeGrip(self.box))
        root.addLayout(grip_row)

    def _batch_panel(self):
        panel = QFrame()
        panel.setObjectName("impBatchPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        top = QHBoxLayout()
        title = QLabel("LOTE DE PDFs")
        title.setObjectName("impSection")
        self.apply_all_quantity = QSpinBox()
        self.apply_all_quantity.setRange(1, 10000000)
        self.apply_all_quantity.setValue(500)
        self.apply_all_button = QPushButton("APLICAR QUANTIDADE A TODOS")
        self.remove_batch_button = QPushButton("REMOVER SELECIONADO")
        self.clear_batch_button = QPushButton("LIMPAR LOTE")
        top.addWidget(title)
        top.addStretch()
        top.addWidget(QLabel("Quantidade:"))
        top.addWidget(self.apply_all_quantity)
        top.addWidget(self.apply_all_button)
        top.addWidget(self.remove_batch_button)
        top.addWidget(self.clear_batch_button)
        layout.addLayout(top)

        self.batch_table = QTableWidget(0, 6)
        self.batch_table.setHorizontalHeaderLabels(
            ["Arquivo", "TrimBox", "Bleed", "Quantidade", "Planos", "Estado"]
        )
        self.batch_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.batch_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.batch_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.batch_table.verticalHeader().setVisible(False)
        header = self.batch_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        for col in range(1, 6):
            header.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        self.batch_table.setMaximumHeight(190)
        layout.addWidget(self.batch_table)

        self.batch_total_plans = QLabel("Total de planos: 0")
        self.batch_total_plans.setObjectName("impBatchTotal")
        self.batch_total_plans.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(self.batch_total_plans)

        progress_row = QHBoxLayout()
        self.batch_progress = QProgressBar()
        self.batch_progress.setRange(0, 100)
        self.batch_progress.setValue(0)
        self.batch_progress.hide()
        self.cancel_batch_button = QPushButton("CANCELAR LOTE")
        self.cancel_batch_button.hide()
        progress_row.addWidget(self.batch_progress, 1)
        progress_row.addWidget(self.cancel_batch_button)
        layout.addLayout(progress_row)
        return panel

    def _left_panel(self):
        panel = QWidget()
        panel.setObjectName("impControls")
        set_tool_role(panel, "controls")
        panel.setFixedWidth(TOOL_CONTROLS_WIDTH)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(7)

        file_card, file_layout = self._card("ARQUIVO")
        self.drop = DropPanel()
        self.drop.setFixedHeight(42)
        self.drop.icon.setFixedSize(22, 22)
        self.drop.icon.setPixmap(
            self.drop.icon.pixmap().scaled(
                22, 22, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
        )
        self.drop.title.setText("ARRASTE OU CLIQUE PARA ESCOLHER PDFs")
        file_layout.addWidget(self.drop)
        self.file_label = QLabel("Nenhum PDF carregado")
        self.file_label.setObjectName("impFile")
        self.file_label.setWordWrap(True)
        file_layout.addWidget(self.file_label)
        layout.addWidget(file_card)

        paper_card, paper_layout = self._card("PAPEL")
        self.paper_preset = QComboBox()
        self._reload_paper_library()
        paper_layout.addWidget(self.paper_preset)
        self.paper_w = self._double(480)
        self.paper_h = self._double(330)
        measures = QHBoxLayout()
        measures.setSpacing(7)
        measures.addWidget(self._labelled("Largura", self.paper_w), 1)
        self.swap = configure_measure_swap(QPushButton())
        measures.addWidget(self.swap, 0, Qt.AlignBottom)
        measures.addWidget(self._labelled("Altura", self.paper_h), 1)
        paper_layout.addLayout(measures)
        paper_presets = QHBoxLayout()
        paper_presets.setContentsMargins(0, 0, 0, 0)
        paper_presets.setSpacing(6)
        self.paper_quick_buttons = []
        quick_formats = (
            ("33×48", 330.0, 480.0),
            ("32×45", 320.0, 450.0),
            ("A3", 297.0, 420.0),
            ("A4", 210.0, 297.0),
        )
        for index, (text, width, height) in enumerate(quick_formats):
            button = QPushButton(text)
            button.setObjectName("impChip")
            set_tool_role(button, "chip")
            button.setFixedHeight(TOOL_CHIP_HEIGHT)
            button.clicked.connect(
                lambda _checked=False, w=width, h=height:
                self._apply_paper_dimensions(w, h)
            )
            self.paper_quick_buttons.append((button, width, height))
            paper_presets.addWidget(button)
        paper_presets.addStretch()
        paper_layout.addLayout(paper_presets)
        layout.addWidget(paper_card)

        spacing_card, spacing_layout = self._card("ESPAÇOS")
        self.gutter = self._double(5)
        self.margin = self._double(5)
        spacing_layout.addLayout(
            self._row_fields("Entre cortes", self.gutter, "Margens", self.margin)
        )
        self.add_gripper = QCheckBox("Adicionar pinça (+10 mm inferior)")
        self.add_gripper.setChecked(False)
        spacing_layout.addWidget(self.add_gripper)
        layout.addWidget(spacing_card)

        distribution_card, distribution_layout = self._card("DISTRIBUIÇÃO")
        self.repeat = QRadioButton("Repetir cada página")
        self.seq = QRadioButton("Sequencial 1, 2, 3…")
        self.repeat.setChecked(True)
        self.mode_group = QButtonGroup(self)
        self.mode_group.addButton(self.repeat)
        self.mode_group.addButton(self.seq)
        modes = QHBoxLayout()
        modes.setSpacing(18)
        modes.addWidget(self.repeat)
        modes.addWidget(self.seq)
        modes.addStretch()
        distribution_layout.addLayout(modes)
        self.order = QComboBox()
        self.order.addItems(["Esquerda → direita, depois desce", "Cima → baixo, depois avança"])
        distribution_layout.addWidget(self.order)
        layout.addWidget(distribution_card)
        layout.addWidget(self._marks_card())
        layout.addStretch()
        return panel

    def _marks_card(self):
        card, layout = self._card("MARCAS DE CORTE")
        self.marks = QCheckBox("Adicionar marcas de corte")
        self.marks.setChecked(True)
        layout.addWidget(self.marks)
        values = QHBoxLayout()
        self.mark_offset = self._double(3)
        self.mark_length = self._double(5)
        self.mark_thickness = self._double(.25, suffix=" pt", minimum=.01)
        values.addWidget(self._labelled("Offset", self.mark_offset))
        values.addWidget(self._labelled("Comprimento", self.mark_length))
        values.addWidget(self._labelled("Espessura", self.mark_thickness))
        layout.addLayout(values)
        return card

    def _right_panel(self):
        panel = QWidget()
        panel.setObjectName("impControls")
        set_tool_role(panel, "controls")
        panel.setFixedWidth(270)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(7)

        result_card, result_layout = self._card("RESULTADO")
        self.best = ToolSuggestionButton("MELHOR\n—")
        self.second = ToolSuggestionButton("SEGUNDA MELHOR\n—")
        self.best.setFixedHeight(64)
        self.second.setFixedHeight(64)
        self.best.setChecked(True)
        result_layout.addWidget(self.best)
        result_layout.addWidget(self.second)

        self.columns = QSpinBox()
        self.columns.setRange(1, 100)
        self.rows = QSpinBox()
        self.rows.setRange(1, 100)
        result_layout.addLayout(
            self._row_fields("Colunas", self.columns, "Linhas", self.rows)
        )
        self.plans_total_label = QLabel("Planos totais: —")
        self.plans_total_label.setObjectName("impPlansTotal")
        self.plans_total_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        result_layout.addWidget(self.plans_total_label)
        self.summary = QLabel("Carregue um PDF para calcular.")
        self.summary.setObjectName("impSummary")
        self.summary.setWordWrap(True)
        self.summary.setMinimumHeight(72)
        self.summary.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(result_card)

        production_card, production_layout = self._card("PRODUÇÃO")
        self.quantity = QSpinBox()
        self.quantity.setRange(1, 10000000)
        self.quantity.setValue(500)
        self.quantity.setGroupSeparatorShown(False)
        self.material = QLineEdit("Mat350g")
        self.material.setPlaceholderText("Nome do papel / material")
        production_layout.addWidget(
            self._labelled("Quantidade de cada página", self.quantity)
        )
        production_layout.addWidget(self._labelled("Material", self.material))
        material_presets = QHBoxLayout()
        material_presets.setContentsMargins(0, 0, 0, 0)
        material_presets.setSpacing(6)
        self.material_150 = QPushButton("Mat150g")
        self.material_350 = QPushButton("Mat350g")
        for button in (self.material_150, self.material_350):
            set_tool_role(button, "chip")
            button.setFixedHeight(TOOL_CHIP_HEIGHT)
        material_presets.addWidget(self.material_150)
        material_presets.addWidget(self.material_350)
        material_presets.addStretch()
        production_layout.addLayout(material_presets)
        production_layout.addStretch(1)
        layout.addWidget(production_card, 1)
        self.bleed_warning = QLabel(
            "Sangria inferior a 3 mm"
        )
        self.bleed_warning.setObjectName("impBleedWarning")
        self.bleed_warning.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.bleed_warning.hide()
        production_layout.addWidget(self.summary)
        production_layout.addWidget(self.bleed_warning)
        self.save = QPushButton("SALVAR NO DESKTOP")
        self.save.setObjectName("impSave")
        self.save.setEnabled(False)
        self.register_in_sheet = QCheckBox("Registrar na planilha")
        self.register_in_sheet.setChecked(
            self.settings.value(
                "imposition/register_in_sheet",
                False,
                type=bool,
            )
        )
        production_layout.addWidget(self.register_in_sheet)
        production_layout.addWidget(self.save)
        self.release_pdf_button = QPushButton("LIBERAR PDF")
        self.release_pdf_button.setObjectName("impRelease")
        self.release_pdf_button.setEnabled(False)
        self.release_pdf_button.setToolTip("Remove todos os PDFs carregados e limpa a prévia")
        production_layout.addWidget(self.release_pdf_button)
        return panel


    def _sheet_identification_panel(self):
        panel = QFrame()
        panel.setObjectName("impBatchPanel")
        layout = QHBoxLayout(panel)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(8)

        self.identify_sheets = QCheckBox("Identificar folhas")
        self.identify_sheets.setChecked(True)
        self.sheet_legend = QLineEdit()
        self.sheet_legend.setPlaceholderText("Legenda impressa no topo da folha")
        layout.addWidget(self.identify_sheets, 0)
        layout.addSpacing(14)
        layout.addWidget(self.sheet_legend, 1)
        return panel

    def _filename_panel(self):
        panel = QFrame()
        panel.setObjectName("impBatchPanel")
        layout = QHBoxLayout(panel)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(8)

        self.use_custom_filename = QCheckBox("Nome do arquivo")
        self.use_custom_filename.setChecked(True)
        self.filename = QLineEdit()
        self.filename.setObjectName("impFilename")
        self.filename.setPlaceholderText("Nome do PDF que será salvo")
        layout.addWidget(self.use_custom_filename, 0)
        layout.addSpacing(14)
        layout.addWidget(self.filename, 1)
        return panel

    def _double(self, value, suffix=" mm", minimum=0):
        widget = QDoubleSpinBox()
        widget.setRange(minimum, 100000)
        widget.setDecimals(2)
        widget.setValue(value)
        widget.setSuffix(suffix)
        return widget

    def _section(self, text):
        label = QLabel(text)
        label.setObjectName("impSection")
        return label

    @staticmethod
    def _compact_number(value):
        rounded = round(float(value), 1)
        if abs(rounded - round(rounded)) < .001:
            return str(int(round(rounded)))
        return f"{rounded:.1f}".replace(".", ",")

    @classmethod
    def _compact_measure(cls, width, height):
        return (
            f"{cls._compact_number(width)} × "
            f"{cls._compact_number(height)} mm"
        )

    def _card(self, title):
        card = QFrame()
        card.setObjectName("impCard")
        set_tool_role(card, "card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(11, 8, 11, 9)
        layout.setSpacing(7)
        label = QLabel(title)
        label.setObjectName("impCardTitle")
        set_tool_role(label, "cardTitle")
        layout.addWidget(label)
        return card, layout

    def _labelled(self, text, widget):
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        label = QLabel(text.upper())
        label.setObjectName("impFieldLabel")
        set_tool_role(label, "fieldLabel")
        layout.addWidget(label)
        layout.addWidget(widget)
        return box

    def _row_fields(self, first_text, first_widget, second_text, second_widget):
        layout = QHBoxLayout()
        layout.addWidget(self._labelled(first_text, first_widget))
        layout.addWidget(self._labelled(second_text, second_widget))
        return layout

    def _connect(self):
        self.drop.fileDropped.connect(self._choose_or_load)
        self.zoom_out_button.clicked.connect(self.preview.zoom_out)
        self.zoom_in_button.clicked.connect(self.preview.zoom_in)
        self.zoom_label.clicked.connect(self.preview.reset_zoom)
        self.preview.zoomChanged.connect(
            lambda value: self.zoom_label.setText(f"{value}%")
        )
        for widget in (self.paper_w, self.paper_h, self.gutter, self.margin, self.quantity):
            widget.valueChanged.connect(self.recalculate)
        self.material.textChanged.connect(self._material_text_changed)
        self.material_150.clicked.connect(
            lambda: self._apply_material_preset("Mat150g")
        )
        self.material_350.clicked.connect(
            lambda: self._apply_material_preset("Mat350g")
        )
        self.paper_preset.currentTextChanged.connect(self._paper_preset_changed)
        self.add_gripper.toggled.connect(self.recalculate)
        self.identify_sheets.toggled.connect(self.recalculate)
        self.sheet_legend.textEdited.connect(self._legend_edited)
        self.use_custom_filename.toggled.connect(self._filename_mode_changed)
        self.filename.textEdited.connect(self._filename_edited)
        self.repeat.toggled.connect(self._mode_changed)
        self.seq.toggled.connect(self._mode_changed)
        self.order.currentIndexChanged.connect(self.recalculate)
        self.marks.toggled.connect(self.recalculate)
        self.mark_offset.valueChanged.connect(self.recalculate)
        self.mark_length.valueChanged.connect(self.recalculate)
        self.mark_thickness.valueChanged.connect(self.recalculate)
        self.swap.clicked.connect(self._swap_paper)
        self.best.clicked.connect(lambda: self._select(0))
        self.second.clicked.connect(lambda: self._select(1))
        self.columns.valueChanged.connect(self._manual_grid_changed)
        self.rows.valueChanged.connect(self._manual_grid_changed)
        self.prev_sheet.clicked.connect(lambda: self._change_sheet(-1))
        self.next_sheet.clicked.connect(lambda: self._change_sheet(1))
        self.save.clicked.connect(self._save)
        self.register_in_sheet.toggled.connect(
            lambda checked: self.settings.setValue(
                "imposition/register_in_sheet",
                checked,
            )
        )
        self.batch_table.itemSelectionChanged.connect(self._batch_selection_changed)
        self.apply_all_button.clicked.connect(self._apply_quantity_to_all)
        self.remove_batch_button.clicked.connect(self._remove_selected_batch)
        self.clear_batch_button.clicked.connect(self._clear_batch)
        self.release_pdf_button.clicked.connect(self._clear_batch)
        self.cancel_batch_button.clicked.connect(self._cancel_batch)

    def _apply_material_preset(self, value: str):
        self.legend_customized = False
        self.filename_customized = False
        self.material.setText(value)
        self.recalculate()

    def _material_text_changed(self, _text):
        self.recalculate()

    def _geometry_custom_formats(self):
        raw = self.settings.value("geometry/custom_formats", "{}")
        try:
            values = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            values = {}
        return values if isinstance(values, dict) else {}

    def _paper_library(self):
        return {**FIXED_FORMATS, **self._geometry_custom_formats()}

    def _reload_paper_library(self):
        current = self.paper_preset.currentText()
        self.paper_preset.blockSignals(True)
        self.paper_preset.clear()
        names = ["PERSONALIZADO", *self._paper_library()]
        self.paper_preset.addItems(names)
        self.paper_preset.setCurrentText(
            current if current in names else "PERSONALIZADO"
        )
        self.paper_preset.blockSignals(False)

    def refresh_paper_library(self):
        self._reload_paper_library()
        self._sync_paper_presets()

    def _paper_preset_changed(self, name):
        dimensions = self._paper_library().get(name)
        if dimensions:
            self._apply_paper_dimensions(
                float(dimensions[0]), float(dimensions[1])
            )

    def _apply_paper_dimensions(self, width: float, height: float):
        self.paper_w.blockSignals(True)
        self.paper_h.blockSignals(True)
        self.paper_w.setValue(width)
        self.paper_h.setValue(height)
        self.paper_w.blockSignals(False)
        self.paper_h.blockSignals(False)
        self.manual_override = False
        self.current_sheet = 0
        self.recalculate()

    def _sync_paper_presets(self):
        width = round(self.paper_w.value(), 2)
        height = round(self.paper_h.value(), 2)
        match = "PERSONALIZADO"
        for name, dimensions in self._paper_library().items():
            if (
                abs(float(dimensions[0]) - width) < .02
                and abs(float(dimensions[1]) - height) < .02
            ):
                match = name
                break
        self.paper_preset.blockSignals(True)
        self.paper_preset.setCurrentText(match)
        self.paper_preset.blockSignals(False)
        # Assim como na Geometria, os chips são ações rápidas e não estados.

    def _legend_edited(self, _text):
        self.legend_customized = True

    def _filename_edited(self, _text):
        self.filename_customized = True

    def _filename_mode_changed(self, checked):
        self.filename.setEnabled(checked and not self.batch_mode)

    def _normalized_output_name(self, automatic_name: str) -> str:
        if self.batch_mode:
            return automatic_name
        if not self.use_custom_filename.isChecked():
            return Path(self.pdf_path).name if self.pdf_path else automatic_name
        name = self.filename.text().strip()
        if not name:
            return automatic_name
        name = Path(name).name
        if not name.lower().endswith(".pdf"):
            name += ".pdf"
        return name

    @staticmethod
    def _plans_description(mode, page_count, plans, compact=False):
        if mode == "repeat" and page_count > 1:
            total = plans * page_count
            if compact:
                return f"{plans} planos/pág. · {total} no total"
            return f"Planos: {plans} por página · {total} no total"
        return f"{plans} planos" if compact else f"Planos totais: {plans}"

    @staticmethod
    def _production_plans(mode, page_count, plans):
        return plans * page_count if mode == "repeat" else plans

    def _default_sheet_legend(
        self, path, quantity, plans, page_count=None, mode=None,
    ):
        page_count = page_count or (
            self.geometry_info.page_count if self.geometry_info else 1
        )
        mode = mode or ("repeat" if self.repeat.isChecked() else "sequential")
        each_artwork = mode == "repeat" and page_count > 1
        return automatic_sheet_label(
            path,
            quantity,
            self._production_plans(mode, page_count, plans),
            self.material.text(),
            each_artwork=each_artwork,
        )

    def _update_sheet_legend(self, path, quantity, plans):
        if self.legend_customized:
            return
        self.sheet_legend.blockSignals(True)
        self.sheet_legend.setText(self._default_sheet_legend(path, quantity, plans))
        self.sheet_legend.blockSignals(False)

    def _choose_or_load(self, paths):
        if not paths:
            paths, _ = QFileDialog.getOpenFileNames(
                self, "Escolher PDFs", str(Path.home() / "Desktop"), "PDF (*.pdf)"
            )
        elif isinstance(paths, str):
            paths = [paths]
        if paths:
            self.load_pdfs(paths)

    def load_pdf(self, path, naming_path=None):
        self.load_pdfs([path], naming_paths=[naming_path] if naming_path else None)

    def load_pdfs(self, paths, naming_paths=None):
        naming_paths = list(naming_paths or [])
        valid_paths = []
        seen = set()
        for index, raw in enumerate(paths):
            path = Path(raw).expanduser().resolve()
            if path.suffix.lower() == ".pdf" and path not in seen:
                naming_path = (
                    Path(naming_paths[index]).expanduser().resolve()
                    if index < len(naming_paths) and naming_paths[index]
                    else path
                )
                valid_paths.append((path, naming_path))
                seen.add(path)
        if not valid_paths:
            return

        items = []
        errors = []
        for path, naming_path in valid_paths:
            try:
                info = inspect_pdf(path)
                items.append({
                    "path": path,
                    "naming_path": naming_path,
                    "info": info,
                    "quantity": self.quantity.value(),
                    "status": "Pronto",
                    "error": "",
                })
            except ImpositionError as exc:
                errors.append(f"{path.name}: {exc}")

        if not items:
            self._message("\n".join(errors), error=True)
            return

        self.batch_items = items
        self.release_pdf_button.setEnabled(True)
        self.pdfStateChanged.emit([str(item["path"]) for item in items])
        self.batch_mode = len(items) > 1
        self.legend_customized = False
        self.filename_customized = False
        self.use_custom_filename.setEnabled(not self.batch_mode)
        self.filename.setEnabled(self.use_custom_filename.isChecked() and not self.batch_mode)
        self.manual_override = False
        self.batch_panel.setVisible(self.batch_mode)
        self.save.setText("PROCESSAR TODOS NO DESKTOP" if self.batch_mode else "SALVAR NO DESKTOP")
        self.file_label.setText(
            f"{len(items)} PDFs carregados · selecione um item para visualizar"
            if self.batch_mode else ""
        )
        self._populate_batch_table()
        self._activate_batch_index(0)
        if errors:
            self._message("Alguns arquivos não foram carregados:\n" + "\n".join(errors), error=True)

    def _activate_batch_index(self, index: int):
        if not self.batch_items:
            return
        index = max(0, min(index, len(self.batch_items) - 1))
        item = self.batch_items[index]
        self.pdf_path = item["path"]
        self.naming_path = item.get("naming_path", self.pdf_path)
        self.geometry_info = item["info"]
        self.quantity.blockSignals(True)
        self.quantity.setValue(item["quantity"])
        self.quantity.blockSignals(False)
        self.current_sheet = 0
        if self.batch_mode:
            self.file_label.setText(
                f"{self.naming_path.name}\nTrimBox: {self.geometry_info.trim_width_mm:.2f} × "
                f"{self.geometry_info.trim_height_mm:.2f} mm · {self.geometry_info.page_count} pág."
            )
        else:
            self.file_label.setText(
                f"{self.naming_path.name}\nTrimBox: {self.geometry_info.trim_width_mm:.2f} × "
                f"{self.geometry_info.trim_height_mm:.2f} mm · {self.geometry_info.page_count} pág."
            )
        self._render_thumbnails()
        self.bleed_warning.setVisible(not self.geometry_info.has_minimum_bleed)
        self.save.setEnabled(True)
        self.recalculate()

    def _populate_batch_table(self):
        self._updating_batch_table = True
        self.batch_table.setRowCount(len(self.batch_items))
        majority = self._majority_trim()
        total_plans = 0
        for row, item in enumerate(self.batch_items):
            info = item["info"]
            self.batch_table.setItem(
                row, 0, QTableWidgetItem(item.get("naming_path", item["path"]).name)
            )
            self.batch_table.setItem(row, 1, QTableWidgetItem(
                f"{info.trim_width_mm:.2f}×{info.trim_height_mm:.2f}"
            ))
            self.batch_table.setItem(row, 2, QTableWidgetItem("OK" if info.has_minimum_bleed else "⚠ Sem bleed"))
            qty = QSpinBox()
            qty.setRange(1, 10000000)
            qty.setValue(item["quantity"])
            qty.valueChanged.connect(lambda value, r=row: self._batch_quantity_changed(r, value))
            self.batch_table.setCellWidget(row, 3, qty)
            self.batch_table.setItem(row, 4, QTableWidgetItem("—"))
            size_diff = majority and not self._same_trim(info, majority)
            state = "⚠ Tamanho diferente" if size_diff else ("⚠ Sem bleed" if not info.has_minimum_bleed else "Pronto")
            item["status"] = state
            self.batch_table.setItem(row, 5, QTableWidgetItem(state))
        self._updating_batch_table = False
        if self.batch_items:
            self.batch_table.selectRow(0)

    def _same_trim(self, info, target, tolerance=0.15):
        return (
            abs(info.trim_width_mm - target[0]) <= tolerance
            and abs(info.trim_height_mm - target[1]) <= tolerance
        )

    def _majority_trim(self):
        if not self.batch_items:
            return None
        counts = {}
        for item in self.batch_items:
            info = item["info"]
            key = (round(info.trim_width_mm, 1), round(info.trim_height_mm, 1))
            counts[key] = counts.get(key, 0) + 1
        return max(counts, key=counts.get)

    def _batch_selection_changed(self):
        if self._updating_batch_table or not self.batch_mode:
            return
        row = self.batch_table.currentRow()
        if row >= 0:
            self._activate_batch_index(row)

    def _batch_quantity_changed(self, row, value):
        if 0 <= row < len(self.batch_items):
            self.batch_items[row]["quantity"] = value
            if row == self.batch_table.currentRow():
                self.quantity.blockSignals(True)
                self.quantity.setValue(value)
                self.quantity.blockSignals(False)
            self._refresh_batch_calculations()

    def _apply_quantity_to_all(self):
        value = self.apply_all_quantity.value()
        for row, item in enumerate(self.batch_items):
            item["quantity"] = value
            spin = self.batch_table.cellWidget(row, 3)
            if spin:
                spin.blockSignals(True)
                spin.setValue(value)
                spin.blockSignals(False)
        self.quantity.setValue(value)
        self._refresh_batch_calculations()

    def _remove_selected_batch(self):
        row = self.batch_table.currentRow()
        if row < 0 or row >= len(self.batch_items):
            return
        self.batch_items.pop(row)
        if not self.batch_items:
            self._clear_batch()
            return
        self.batch_mode = len(self.batch_items) > 1
        self.batch_panel.setVisible(self.batch_mode)
        self.save.setText("PROCESSAR TODOS NO DESKTOP" if self.batch_mode else "SALVAR NO DESKTOP")
        self._populate_batch_table()
        self._activate_batch_index(min(row, len(self.batch_items) - 1))

    def _clear_batch(self):
        self.batch_items = []
        self.batch_mode = False
        self.batch_panel.hide()
        self.pdf_path = None
        self.naming_path = None
        self.geometry_info = None
        self.thumbnails = []
        self.preview.reset_zoom()
        self.file_label.setText("Nenhum PDF carregado")
        self.release_pdf_button.setEnabled(False)
        self.save.setText("SALVAR NO DESKTOP")
        self.save.setEnabled(False)
        self.sheet_legend.clear()
        self.filename.clear()
        self.filename_customized = False
        self.use_custom_filename.setEnabled(True)
        self.filename.setEnabled(self.use_custom_filename.isChecked())
        self.bleed_warning.hide()
        self.pdfStateChanged.emit([])
        self.recalculate()

    def _cancel_batch(self):
        self.batch_cancelled = True

    def _render_thumbnails(self):
        self.thumbnails = []
        if not self.pdf_path:
            return
        doc = open_pdf_for_imposition(self.pdf_path)
        try:
            for index in range(doc.page_count):
                page = doc[index]
                clip = effective_bleed_rect(page)
                pix = page.get_pixmap(
                    matrix=fitz.Matrix(0.55, 0.55), alpha=False, clip=clip
                )
                image_format = QImage.Format_RGB888 if pix.n == 3 else QImage.Format_RGBA8888
                image = QImage(
                    pix.samples, pix.width, pix.height, pix.stride, image_format
                ).copy()
                self.thumbnails.append(QPixmap.fromImage(image))
        finally:
            doc.close()

    def recalculate(self, *_):
        self._sync_paper_presets()
        if not self.geometry_info:
            self.options = []
            self._refresh()
            return
        geometry = self.geometry_info
        self.options = calculate_layouts(
            self.paper_w.value(),
            self.paper_h.value(),
            geometry.trim_width_mm,
            geometry.trim_height_mm,
            self.gutter.value(),
            self.margin.value(),
            10.0 if self.add_gripper.isChecked() else 0.0,
        )
        self.selected_option = min(self.selected_option, max(0, len(self.options) - 1))
        if self.options and not self.manual_override:
            self._set_grid_boxes(self.options[self.selected_option])
        if self.batch_items and self.batch_table.currentRow() >= 0:
            self.batch_items[self.batch_table.currentRow()]["quantity"] = self.quantity.value()
        self._refresh()
        if self.batch_mode:
            self._refresh_batch_calculations()

    def _layout_for_item(self, item):
        info = item["info"]
        options = calculate_layouts(
            self.paper_w.value(), self.paper_h.value(),
            info.trim_width_mm, info.trim_height_mm,
            self.gutter.value(), self.margin.value(),
            10.0 if self.add_gripper.isChecked() else 0.0,
        )
        if not options:
            return None
        base = options[min(self.selected_option, len(options) - 1)]
        if not self.manual_override:
            return base
        return build_custom_layout(
            self.paper_w.value(), self.paper_h.value(),
            info.trim_width_mm, info.trim_height_mm,
            self.gutter.value(), self.margin.value(),
            self.columns.value(), self.rows.value(), base.rotated,
            10.0 if self.add_gripper.isChecked() else 0.0,
        )

    def _refresh_batch_calculations(self):
        if not self.batch_mode or self._updating_batch_table:
            return
        mode = "repeat" if self.repeat.isChecked() else "sequential"
        majority = self._majority_trim()
        total_plans = 0
        for row, item in enumerate(self.batch_items):
            info = item["info"]
            layout = self._layout_for_item(item)
            if layout:
                plans = calculate_plans(mode, info.page_count, layout.total, item["quantity"])
                total_plans += plans
                self.batch_table.setItem(row, 4, QTableWidgetItem(str(plans)))
            else:
                plans = 0
                self.batch_table.setItem(row, 4, QTableWidgetItem("—"))
            size_diff = majority and not self._same_trim(info, majority)
            if not layout:
                state = "✕ Não cabe"
            elif size_diff:
                state = "⚠ Tamanho diferente"
            elif not info.has_minimum_bleed:
                state = "⚠ Sem bleed"
            else:
                state = "Pronto"
            item["status"] = state
            self.batch_table.setItem(row, 5, QTableWidgetItem(state))
        self.batch_total_plans.setText(f"Total de planos: {total_plans}")

    def _active_layout(self) -> LayoutOption | None:
        if not self.options or not self.geometry_info:
            return None
        base = self.options[self.selected_option]
        if not self.manual_override:
            return base
        return build_custom_layout(
            self.paper_w.value(),
            self.paper_h.value(),
            self.geometry_info.trim_width_mm,
            self.geometry_info.trim_height_mm,
            self.gutter.value(),
            self.margin.value(),
            self.columns.value(),
            self.rows.value(),
            base.rotated,
            10.0 if self.add_gripper.isChecked() else 0.0,
        )

    def _refresh(self):
        mode = "repeat" if self.repeat.isChecked() else "sequential"
        for index, button in enumerate((self.best, self.second)):
            if index < len(self.options):
                option = self.options[index]
                option_plans = 0
                if self.geometry_info:
                    option_plans = calculate_plans(
                        mode,
                        self.geometry_info.page_count,
                        option.total,
                        self.quantity.value(),
                    )
                button.setText(
                    ("MELHOR" if index == 0 else "SEGUNDA MELHOR")
                    + f"\n{option.columns} × {option.rows} = {option.total} · {option.orientation_label}"
                    + (
                        "\n" + self._plans_description(
                            mode,
                            self.geometry_info.page_count,
                            option_plans,
                            compact=True,
                        )
                        if option_plans and self.geometry_info else ""
                    )
                )
                button.setEnabled(True)
                button.setChecked(index == self.selected_option and not self.manual_override)
            else:
                button.setText(("MELHOR" if index == 0 else "SEGUNDA MELHOR") + "\n—")
                button.setEnabled(False)

        option = self._active_layout()
        self.save.setEnabled(bool(option and self.geometry_info and self.pdf_path))
        if option and self.geometry_info and self.pdf_path:
            plans = calculate_plans(
                mode, self.geometry_info.page_count, option.total, self.quantity.value()
            )
            self._update_sheet_legend(
                self.naming_path or self.pdf_path, self.quantity.value(), plans
            )
            left_free = max(0.0, option.start_x_mm)
            top_free = max(0.0, option.start_y_mm)
            right_free = max(
                0.0,
                option.paper_width_mm - option.start_x_mm - option.occupied_width_mm,
            )
            bottom_free = max(
                0.0,
                option.paper_height_mm - option.start_y_mm - option.occupied_height_mm,
            )
            self.plans_total_label.setText(
                self._plans_description(
                    mode, self.geometry_info.page_count, plans
                )
            )
            self.summary.setText(
                f"Trim: {self._compact_measure(self.geometry_info.trim_width_mm, self.geometry_info.trim_height_mm)}\n"
                f"Medida do papel: {self._compact_measure(option.paper_width_mm, option.paper_height_mm)}\n"
                "Sobra:\n"
                f"E: {self._compact_number(left_free)} mm     D: {self._compact_number(right_free)} mm\n"
                f"T: {self._compact_number(top_free)} mm     B: {self._compact_number(bottom_free)} mm"
            )
            automatic_name = automatic_filename(
                self.naming_path or self.pdf_path,
                self.quantity.value(),
                self._production_plans(
                    mode, self.geometry_info.page_count, plans
                ),
                self.material.text(),
                each_artwork=(
                    mode == "repeat" and self.geometry_info.page_count > 1
                ),
            )
            if not self.filename_customized or self.batch_mode:
                self.filename.blockSignals(True)
                self.filename.setText(automatic_name)
                self.filename.blockSignals(False)
            total_sheets = self._preview_sheet_count(option)
            self.current_sheet = min(self.current_sheet, max(0, total_sheets - 1))
            self._update_navigation(total_sheets)
            self.preview.set_state(
                paper_w=option.paper_width_mm,
                paper_h=option.paper_height_mm,
                option=option,
                gutter=self.gutter.value(),
                page_count=self.geometry_info.page_count,
                mode=mode,
                fill_order="rows" if self.order.currentIndex() == 0 else "columns",
                thumbnails=self.thumbnails,
                crop_marks=self.marks.isChecked(),
                sheet_index=self.current_sheet,
                bleed_left=self.geometry_info.bleed_left_mm,
                bleed_top=self.geometry_info.bleed_top_mm,
                bleed_right=self.geometry_info.bleed_right_mm,
                bleed_bottom=self.geometry_info.bleed_bottom_mm,
                identify_sheets=self.identify_sheets.isChecked(),
                sheet_legend=self.sheet_legend.text(),
                total_sheets=total_sheets,
                crop_mark_offset=self.mark_offset.value(),
                crop_mark_length=self.mark_length.value(),
                crop_mark_thickness=self.mark_thickness.value(),
            )
        else:
            self.plans_total_label.setText("Planos totais: —")
            message = (
                "A grade escolhida não cabe no papel com as margens atuais."
                if self.geometry_info and self.manual_override
                else "A arte não cabe no papel com as margens atuais."
                if self.geometry_info
                else "Carregue um PDF para calcular."
            )
            self.summary.setText(message)
            self.filename.clear()
            if not self.legend_customized:
                self.sheet_legend.clear()
            self._update_navigation(0)
            self.preview.set_state(
                paper_w=self.paper_w.value(),
                paper_h=self.paper_h.value(),
                option=None,
                gutter=self.gutter.value(),
                page_count=0,
                mode="repeat",
                fill_order="rows",
                thumbnails=[],
                crop_marks=True,
                sheet_index=0,
            )

    def _preview_sheet_count(self, option: LayoutOption) -> int:
        if not self.geometry_info:
            return 0
        if self.repeat.isChecked():
            return self.geometry_info.page_count
        return max(1, math.ceil(self.geometry_info.page_count / option.total))

    def _update_navigation(self, total_sheets: int):
        if total_sheets < 1:
            self.sheet_label.setText("Montagem —")
            self.prev_sheet.setEnabled(False)
            self.next_sheet.setEnabled(False)
            return
        if self.repeat.isChecked():
            self.sheet_label.setText(
                f"Montagem {self.current_sheet + 1} de {total_sheets} · Página {self.current_sheet + 1}"
            )
        else:
            self.sheet_label.setText(f"Montagem {self.current_sheet + 1} de {total_sheets}")
        self.prev_sheet.setEnabled(self.current_sheet > 0)
        self.next_sheet.setEnabled(self.current_sheet < total_sheets - 1)

    def _change_sheet(self, delta: int):
        option = self._active_layout()
        if not option:
            return
        total = self._preview_sheet_count(option)
        self.current_sheet = max(0, min(total - 1, self.current_sheet + delta))
        self._refresh()

    def _mode_changed(self, *_):
        self.current_sheet = 0
        self.recalculate()

    def _manual_grid_changed(self, *_):
        if self.columns.signalsBlocked() or self.rows.signalsBlocked():
            return
        self.manual_override = True
        self.current_sheet = 0
        self._refresh()
        if self.batch_mode:
            self._refresh_batch_calculations()

    def _set_grid_boxes(self, option: LayoutOption):
        self.columns.blockSignals(True)
        self.rows.blockSignals(True)
        self.columns.setValue(option.columns)
        self.rows.setValue(option.rows)
        self.columns.blockSignals(False)
        self.rows.blockSignals(False)

    def _select(self, index):
        if index < len(self.options):
            self.selected_option = index
            self.manual_override = False
            self.current_sheet = 0
            self._set_grid_boxes(self.options[index])
            self._refresh()
            if self.batch_mode:
                self._refresh_batch_calculations()

    def _swap_paper(self):
        width, height = self.paper_w.value(), self.paper_h.value()
        self.paper_w.blockSignals(True)
        self.paper_h.blockSignals(True)
        self.paper_w.setValue(height)
        self.paper_h.setValue(width)
        self.paper_w.blockSignals(False)
        self.paper_h.blockSignals(False)
        self.manual_override = False
        self.current_sheet = 0
        self.recalculate()

    def _unique_desktop_output(self, name: str) -> Path:
        output = Path.home() / "Desktop" / name
        if not output.exists():
            return output
        counter = 2
        while True:
            candidate = output.with_name(f"{output.stem} ({counter}){output.suffix}")
            if not candidate.exists():
                return candidate
            counter += 1

    def _save(self):
        if self.batch_mode:
            self._save_batch()
            return
        option = self._active_layout()
        if not self.pdf_path or not option or not self.geometry_info:
            return
        mode = "repeat" if self.repeat.isChecked() else "sequential"
        plans = calculate_plans(
            mode, self.geometry_info.page_count, option.total, self.quantity.value()
        )
        automatic_name = automatic_filename(
            self.pdf_path,
            self.quantity.value(),
            self._production_plans(
                mode, self.geometry_info.page_count, plans
            ),
            self.material.text(),
            each_artwork=(
                mode == "repeat" and self.geometry_info.page_count > 1
            ),
        )
        name = self._normalized_output_name(automatic_name)
        output = self._unique_desktop_output(name)
        try:
            result = export_imposition(
                self.pdf_path, output, option, self.gutter.value(), mode,
                self.quantity.value(), self.marks.isChecked(),
                "rows" if self.order.currentIndex() == 0 else "columns",
                self.identify_sheets.isChecked(), self.sheet_legend.text(),
                crop_mark_offset_mm=self.mark_offset.value(),
                crop_mark_length_mm=self.mark_length.value(),
                crop_mark_thickness_pt=self.mark_thickness.value(),
            )
            message = f"✓ Imposição salva no Desktop\n{output.name}"
            if result.source_pdfx:
                profile_status = (
                    "perfil ICC preservado"
                    if result.output_intent_preserved
                    else "sem OutputIntent incorporado"
                )
                message += (
                    f"\n⚠ Origem {result.source_pdfx} · "
                    f"{profile_status} · PDF/X não reconfirmado"
                )
            self._message(message)
            self._notify_terminal(f"✓ IMP salvo: {output.name}")
            if self.register_in_sheet.isChecked():
                entry = make_entry(
                    output.name,
                    self.geometry_info.page_count,
                    plans=plans,
                )
                PrintLogDialog([entry], self).exec()
        except ImpositionError as exc:
            self._message(str(exc), error=True)

    def _save_batch(self):
        if not self.batch_items:
            return
        self.batch_cancelled = False
        self.batch_progress.show()
        self.cancel_batch_button.show()
        self.save.setEnabled(False)
        total = len(self.batch_items)
        completed = 0
        failed = 0
        warnings = 0
        saved_entries = []
        mode = "repeat" if self.repeat.isChecked() else "sequential"
        fill_order = "rows" if self.order.currentIndex() == 0 else "columns"

        for index, item in enumerate(self.batch_items):
            QApplication.processEvents()
            if self.batch_cancelled:
                break
            path = item["path"]
            info = item["info"]
            quantity = item["quantity"]
            option = self._layout_for_item(item)
            self.batch_progress.setValue(int(index * 100 / max(1, total)))
            self._message(f"Processando {index + 1} de {total}\n{path.name}")
            if not option:
                failed += 1
                item["status"] = "✕ Não cabe"
                self.batch_table.setItem(index, 5, QTableWidgetItem(item["status"]))
                continue
            plans = calculate_plans(mode, info.page_count, option.total, quantity)
            name = automatic_filename(
                path,
                quantity,
                self._production_plans(mode, info.page_count, plans),
                self.material.text(),
                each_artwork=(mode == "repeat" and info.page_count > 1),
            )
            output = self._unique_desktop_output(name)
            if self.legend_customized:
                label_text = self.sheet_legend.text()
            else:
                label_text = self._default_sheet_legend(
                    path, quantity, plans, info.page_count, mode
                )
            try:
                result = export_imposition(
                    path, output, option, self.gutter.value(), mode, quantity,
                    self.marks.isChecked(), fill_order,
                    self.identify_sheets.isChecked(), label_text,
                    crop_mark_offset_mm=self.mark_offset.value(),
                    crop_mark_length_mm=self.mark_length.value(),
                    crop_mark_thickness_pt=self.mark_thickness.value(),
                )
                completed += 1
                saved_entries.append(
                    make_entry(
                        output.name,
                        info.page_count,
                        plans=plans,
                    )
                )
                item_warnings = []
                if not info.has_minimum_bleed:
                    item_warnings.append("bleed")
                if result.source_pdfx:
                    item_warnings.append("PDF/X")
                if item_warnings:
                    warnings += 1
                    status = "✓ Salvo · ⚠ " + "/".join(item_warnings)
                else:
                    status = "✓ Salvo"
                item["status"] = status
                self.batch_table.setItem(index, 5, QTableWidgetItem(status))
            except ImpositionError as exc:
                failed += 1
                item["error"] = str(exc)
                item["status"] = "✕ Erro"
                self.batch_table.setItem(index, 5, QTableWidgetItem("✕ Erro"))
            QApplication.processEvents()

        processed = completed + failed
        self.batch_progress.setValue(100 if not self.batch_cancelled else int(processed * 100 / max(1, total)))
        self.cancel_batch_button.hide()
        self.save.setEnabled(True)
        if self.batch_cancelled:
            message = f"Lote cancelado · {completed} salvos · {failed} erros"
        else:
            message = (
                f"✓ Lote concluído\n{completed} arquivos gerados · "
                f"{failed} erros · {warnings} avisos"
            )
        self._message(message, error=failed > 0)
        self._notify_terminal(message.replace("\n", " · "))
        if self.register_in_sheet.isChecked() and saved_entries:
            PrintLogDialog(saved_entries, self).exec()
        QTimer.singleShot(2500, self.batch_progress.hide)

    def _notify_terminal(self, text):
        parent = self.parent()
        if parent and hasattr(parent, "session_result_label"):
            parent.session_result_label.setText(text)
            parent.session_result_label.show()
            if hasattr(parent, "clear_session_result"):
                QTimer.singleShot(8000, parent.clear_session_result)

    def _message(self, text, error=False):
        self.summary.setText(("⚠ " if error else "") + text)

    def _pdf_paths_from_mime(self, mime_data):
        paths = []
        for url in mime_data.urls():
            path = Path(url.toLocalFile())
            if path.is_file() and path.suffix.lower() == ".pdf":
                paths.append(str(path))
        return paths

    def _install_drop_filters(self):
        # QTableWidget, QLineEdit e outros filhos aceitam o evento antes do diálogo.
        # Instalamos o mesmo filtro em toda a árvore para que soltar PDFs funcione
        # literalmente em qualquer ponto da janela.
        for widget in [self, *self.findChildren(QWidget)]:
            widget.setAcceptDrops(True)
            widget.installEventFilter(self)

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Type.DragEnter, QEvent.Type.DragMove):
            paths = self._pdf_paths_from_mime(event.mimeData())
            if paths:
                event.acceptProposedAction()
                return True
        elif event.type() == QEvent.Type.Drop:
            paths = self._pdf_paths_from_mime(event.mimeData())
            if paths:
                self.load_pdfs(paths)
                event.acceptProposedAction()
                return True
        return super().eventFilter(watched, event)

    def dragEnterEvent(self, event):
        paths = self._pdf_paths_from_mime(event.mimeData())
        if paths and all(path.lower().endswith(".pdf") for path in paths):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        paths = self._pdf_paths_from_mime(event.mimeData())
        if paths:
            self.load_pdfs(paths)
            event.acceptProposedAction()
        else:
            event.ignore()

    def _title_press(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def _title_move(self, event):
        if event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_position)


    def _pdf_paths_from_mime(self, mime_data):
        paths = []
        seen = set()
        if not mime_data or not mime_data.hasUrls():
            return paths
        for url in mime_data.urls():
            raw = url.toLocalFile()
            if not raw:
                continue
            path = Path(raw).expanduser()
            try:
                path = path.resolve()
            except OSError:
                pass
            key = str(path).casefold()
            if path.is_file() and path.suffix.casefold() == ".pdf" and key not in seen:
                seen.add(key)
                paths.append(str(path))
        return paths

    def _install_drop_filters(self):
        for widget in [self, self.box, *self.findChildren(QWidget)]:
            widget.setAcceptDrops(True)
            widget.installEventFilter(self)

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Type.DragEnter, QEvent.Type.DragMove):
            if self._pdf_paths_from_mime(event.mimeData()):
                event.acceptProposedAction()
                return True
        if event.type() == QEvent.Type.Drop:
            paths = self._pdf_paths_from_mime(event.mimeData())
            if paths:
                self.load_pdfs(paths)
                event.acceptProposedAction()
                return True
        return super().eventFilter(watched, event)

    def dragEnterEvent(self, event):
        if self._pdf_paths_from_mime(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        self.dragEnterEvent(event)

    def dropEvent(self, event):
        paths = self._pdf_paths_from_mime(event.mimeData())
        if paths:
            self.load_pdfs(paths)
            event.acceptProposedAction()
        else:
            event.ignore()

    def _restore_geometry(self):
        geometry = self.settings.value("imposition_dialog_geometry")
        if geometry:
            self.restoreGeometry(geometry)

    def _schedule_geometry_save(self):
        if hasattr(self, "_geometry_save_timer"):
            self._geometry_save_timer.start(350)

    def _save_geometry(self):
        self.settings.setValue("imposition_dialog_geometry", self.saveGeometry())

    def moveEvent(self, event):
        super().moveEvent(event)
        self._schedule_geometry_save()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._schedule_geometry_save()

    def hideEvent(self, event):
        self._save_geometry()
        super().hideEvent(event)

    def closeEvent(self, event):
        self._save_geometry()
        super().closeEvent(event)

    def _style(self):
        self.setStyleSheet(
            f'''QWidget {{ font-family:"JetBrains Mono"; font-size:10px; }}
            QWidget#impBox, QWidget#impControls {{ background:#080a0d; }}
            QWidget#impBox {{ border:1px solid rgba(255,196,0,.20); border-radius:13px; }}
            QWidget#impBox[embedded="true"] {{ border:0; border-radius:0; background:#080a0d; }}
            QLabel#impWindowTitle {{ color:white; font-size:10px; letter-spacing:1px; }}
            QLabel#impClose {{ color:white; font-size:16px; padding:0 4px; }}
            QLabel#impClose:hover {{ color:{YELLOW}; }}
            QFrame#impCard, QFrame#impBatchPanel {{ background:rgba(255,255,255,.025); border:1px solid rgba(255,255,255,.08); border-radius:7px; }}
            QLabel#impCardTitle, QLabel#impSection {{ color:{YELLOW}; font-size:9px; font-weight:700; letter-spacing:.7px; }}
            QFrame#impDropPanel {{ border:1px solid rgba(255,255,255,.08); border-radius:6px; background:rgba(0,0,0,.18); }}
            QLabel#impDropIcon {{ font-size:20px; font-weight:600; color:rgba(255,196,0,.82); }}
            QLabel#impDropTitle {{ color:{YELLOW}; font-size:9px; font-weight:700; }}
            QLabel#impMuted {{ color:rgba(255,255,255,.45); }}
            QLabel#impFile {{ color:rgba(255,255,255,.43); font-size:9px; padding:1px; }}
            QLabel#impFieldLabel {{ color:rgba(255,255,255,.43); font-size:8px; }}
            QDoubleSpinBox,QSpinBox,QLineEdit,QComboBox {{ background:rgba(255,255,255,.07); border:1px solid rgba(255,255,255,.08); border-radius:4px; padding:3px 5px; color:rgba(255,255,255,.88); min-height:20px; }}
            QRadioButton,QCheckBox {{ color:rgba(255,255,255,.78); spacing:6px; }}
            QRadioButton::indicator,QCheckBox::indicator {{ width:13px; height:13px; }}
            QPushButton {{ min-height:20px; background:rgba(255,255,255,.04); border:1px solid rgba(255,255,255,.12); border-radius:4px; padding:3px 8px; color:rgba(255,255,255,.66); text-align:left; }}
            QPushButton:hover {{ color:#fff0a0; border-color:rgba(255,196,0,.55); }}
            QPushButton:checked {{ background:rgba(255,255,255,.065); color:rgba(255,255,255,.88); border-color:rgba(255,255,255,.12); }}
            QPushButton:disabled {{ color:rgba(255,255,255,.24); border-color:rgba(255,255,255,.10); }}
            QPushButton#impInlinePrimary, QPushButton#impSave {{ color:{YELLOW}; font-weight:700; border:1px solid rgba(255,196,0,.35); background:rgba(255,196,0,.08); }}
            QPushButton#impSave {{ text-align:center; }}
            QPushButton#impRelease {{ text-align:center; color:rgba(255,255,255,.62); background:rgba(255,255,255,.025); border-color:rgba(255,255,255,.12); }}
            QPushButton#impRelease:hover {{ color:#ffb3b3; border-color:rgba(255,90,90,.58); background:rgba(160,35,35,.18); }}
            QPushButton#impNav {{ text-align:center; min-width:92px; padding:3px 8px; }}
            QPushButton#impZoom {{
                color:rgba(255,255,255,.68); border:1px solid rgba(255,255,255,.12);
                background:rgba(255,255,255,.035); padding:0 8px; text-align:center;
            }}
            QPushButton#impZoom:hover {{ color:{YELLOW}; border-color:rgba(255,196,0,.35); }}
            QTableWidget {{ background:rgba(0,0,0,.28); border:1px solid rgba(255,255,255,.10); gridline-color:rgba(255,255,255,.08); color:white; }}
            QHeaderView::section {{ background:rgba(255,196,0,.10); color:{YELLOW}; border:0; padding:5px; }}
            QProgressBar {{ background:rgba(255,255,255,.06); border:1px solid rgba(255,255,255,.12); border-radius:5px; text-align:center; color:white; }}
            QProgressBar::chunk {{ background:rgba(255,196,0,.55); border-radius:4px; }}
            QWidget#impPreview {{ border:1px solid rgba(255,196,0,.18); border-radius:7px; background:#080a0d; }}
            QLabel#impSummary {{ color:rgba(255,255,255,.43); font-size:9px; }}
            QLabel#impPlansTotal {{ color:rgba(255,255,255,.43); font-size:9px; }}
            QLineEdit#impFilename {{ color:{YELLOW}; background:rgba(255,196,0,.04); border-color:rgba(255,196,0,.18); }}
            QLabel#impBleedWarning {{ color:#FF6262; background:transparent; border:0; padding:0; font-size:9px; font-weight:700; }}
            QLabel#impSheetLabel {{ color:rgba(255,255,255,.72); }}'''
            + TOOL_STANDARD_QSS
        )
