from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEvent, QPoint, QSettings, Qt, QTimer, Signal
from PySide6.QtGui import QCursor, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QDialog, QHBoxLayout, QLabel, QSizeGrip, QSizePolicy,
    QTabWidget, QVBoxLayout, QWidget,
)

from ui.code_generator_dialog import CodeGeneratorDialog
from ui.geometry_widget import GeometryWidget
from ui.imposition_dialog import ImpositionDialog
from ui.montagem_dialog import MontagemDialog
from ui.widgets import DarkMetallicTitleBar

ROOT = Path(__file__).resolve().parent.parent
YELLOW = "#FFC400"


class PdfDropOverlay(QWidget):
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
        return any(url.isLocalFile() and url.toLocalFile().lower().endswith(".pdf") for url in mime_data.urls())

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
        # Ao trocar do widget interno para esta camada, o Qt envia DragLeave.
        # Não escondemos imediatamente, pois isso quebraria o drop no macOS.
        event.accept()


class ToolsDialog(QDialog):
    TAB_ORDER = ("GEO", "IMP", "MON", "BAR")
    TAB_LABELS = ("GEOMETRIA", "IMPOSIÇÃO", "MONTAGEM", "EAN-13")

    def __init__(self, parent=None, initial_tab="GEO"):
        super().__init__(parent)
        self.settings = QSettings("M87Tools", "M87Terminal")
        self.drag_position = QPoint()
        self._pages = {}
        self._last_drop_paths = []
        self._drop_guard_active = False
        self._geometry_output_path = None
        self._loading_geometry_into_imp = False
        self._setup_window()
        self._build_ui()
        self._prepare_drop_targets()
        self._restore_geometry()
        self.open_tab(initial_tab)
        QApplication.instance().installEventFilter(self)

    def _setup_window(self):
        self.setWindowTitle("M87 TERMINAL")
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAcceptDrops(True)
        self.setMinimumSize(1040, 650)
        self.resize(1220, 760)
        icon = ROOT / "assets" / "m87_icon.png"
        if icon.exists():
            self.setWindowIcon(QIcon(str(icon)))

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.box = QWidget()
        self.box.setObjectName("toolsBox")
        self.box.setAcceptDrops(True)
        outer.addWidget(self.box)

        root = QVBoxLayout(self.box)
        root.setContentsMargins(0, 0, 0, 6)
        root.setSpacing(0)

        bar = DarkMetallicTitleBar(height=28, radius=12)
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(14, 0, 10, 0)
        title = QLabel("M87 TERMINAL")
        title.setObjectName("toolsWindowTitle")
        close = QLabel("×")
        close.setObjectName("toolsClose")
        close.setCursor(QCursor(Qt.PointingHandCursor))
        close.mousePressEvent = lambda event: self._close_tools()
        bar_layout.addWidget(title)
        bar_layout.addStretch()
        bar_layout.addWidget(close)
        root.addWidget(bar)
        bar.mousePressEvent = self._title_press
        bar.mouseMoveEvent = self._title_move

        self.tabs = QTabWidget()
        self.tabs.setObjectName("toolsTabs")
        self.tabs.setDocumentMode(True)
        self.tabs.setAcceptDrops(True)

        imp = self._embed_dialog(ImpositionDialog(self), "IMP")
        geo = GeometryWidget(self)
        self._pages["GEO"] = geo
        mon = self._embed_dialog(MontagemDialog(self), "MON")
        bar_page = self._embed_dialog(CodeGeneratorDialog(self), "BAR")
        for page, label in zip((geo, imp, mon, bar_page), self.TAB_LABELS):
            self.tabs.addTab(page, label)
        root.addWidget(self.tabs, 1)

        self.drop_overlay = PdfDropOverlay(self._pdf_paths, self.tabs)
        self.drop_overlay.pdfDropped.connect(self._load_dropped_pdfs)

        self._pages["IMP"].pdfStateChanged.connect(self._on_imp_pdf_state_changed)
        geo.appliedPdfChanged.connect(self._on_geometry_applied)
        self.tabs.currentChanged.connect(self._sync_geo_state)

        grip_row = QHBoxLayout()
        grip_row.setContentsMargins(0, 0, 4, 0)
        grip_row.addStretch()
        grip_row.addWidget(QSizeGrip(self.box))
        root.addLayout(grip_row)
        QShortcut(QKeySequence(Qt.Key_Escape), self, activated=self._close_tools)

        self.setStyleSheet(f"""
            QWidget {{ font-family:'JetBrains Mono'; font-size:10px; }}
            QWidget#toolsBox {{ background:rgba(0,0,0,238); border:1px solid rgba(255,196,0,.22); border-radius:13px; }}
            QLabel#toolsWindowTitle {{ color:white; font-size:10px; font-weight:700; letter-spacing:1px; }}
            QLabel#toolsClose {{ color:white; font-size:16px; padding:0 4px; }}
            QLabel#toolsClose:hover {{ color:{YELLOW}; }}
            QTabWidget#toolsTabs::pane {{ border:0; border-top:1px solid rgba(255,196,0,.14); background:#000; }}
            QTabBar::tab {{ background:rgba(255,255,255,.035); color:rgba(255,255,255,.48); border:0; border-right:1px solid rgba(255,255,255,.025); padding:10px 26px; min-width:110px; font-weight:700; }}
            QTabBar::tab:hover {{ color:rgba(255,196,0,.88); background:rgba(255,196,0,.045); }}
            QTabBar::tab:selected {{ color:{YELLOW}; background:rgba(255,196,0,.10); border-bottom:2px solid {YELLOW}; }}
        """)

    def _embed_dialog(self, dialog, code):
        self._pages[code] = dialog
        dialog.setWindowFlags(Qt.Widget)
        dialog.setAttribute(Qt.WA_TranslucentBackground, False)
        dialog.setMinimumSize(0, 0)
        dialog.setMaximumSize(16777215, 16777215)
        dialog.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        dialog.setAcceptDrops(True)

        for titlebar in dialog.findChildren(DarkMetallicTitleBar):
            titlebar.hide()
        for grip in dialog.findChildren(QSizeGrip):
            grip.hide()
        for shortcut in dialog.findChildren(QShortcut):
            shortcut.setEnabled(False)

        box_name = {"IMP": "impBox", "MON": "monBox", "BAR": "barBox"}.get(code)
        box = dialog.findChild(QWidget, box_name) if box_name else None
        if box:
            box.setProperty("embedded", True)
            box.style().unpolish(box)
            box.style().polish(box)

        page = QWidget(self.tabs)
        page.setObjectName(f"{code.lower()}Page")
        page.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(0)
        dialog.setParent(page)
        page_layout.addWidget(dialog, 1)
        dialog.show()
        return page

    def _prepare_drop_targets(self):
        # O drop é tratado no nível da janela e também no QApplication.
        # Assim nenhum filho (preview, tabela, campo, checkbox ou painel criado
        # depois) consegue "engolir" o PDF antes de chegar à ferramenta.
        for widget in [self, self.box, self.tabs, *self.findChildren(QWidget)]:
            widget.setAcceptDrops(True)
            widget.installEventFilter(self)

    def open_tab(self, code):
        code = str(code).upper()
        if code not in self.TAB_ORDER:
            code = "GEO"
        self.tabs.setCurrentIndex(self.TAB_ORDER.index(code))
        if not self.isVisible():
            self.show()
        self.raise_()
        self.activateWindow()

    @staticmethod
    def _pdf_paths(mime_data):
        paths, seen = [], set()
        if not mime_data or not mime_data.hasUrls():
            return paths
        for url in mime_data.urls():
            local = url.toLocalFile()
            if not local:
                continue
            path = Path(local).expanduser()
            try:
                path = path.resolve()
            except OSError:
                pass
            key = str(path).casefold()
            if path.is_file() and path.suffix.casefold() == ".pdf" and key not in seen:
                seen.add(key)
                paths.append(str(path))
        return paths

    def _drop_is_enabled(self):
        return self.tabs.currentIndex() in (
            self.TAB_ORDER.index("GEO"),
            self.TAB_ORDER.index("IMP"),
        )

    def _load_dropped_pdfs(self, paths):
        if not paths or self._drop_guard_active:
            return
        # Um mesmo Drop pode atravessar mais de um filtro Qt. Este pequeno
        # bloqueio impede carregar o lote duas vezes sem alterar a experiência.
        self._drop_guard_active = True
        try:
            self._last_drop_paths = list(paths)
            self._pages["IMP"].load_pdfs(paths)
            self._pages["GEO"].set_pdf_state(paths)
        finally:
            QTimer.singleShot(0, self._release_drop_guard)

    def _release_drop_guard(self):
        self._drop_guard_active = False

    def _event_belongs_to_tools(self, watched):
        # O filtro também está instalado no QApplication. Nessa situação,
        # validamos se o objeto que recebeu o evento pertence a esta janela.
        if watched is self or watched is self.box or watched is self.tabs:
            return True
        if isinstance(watched, QWidget):
            window = watched.window()
            if window is self:
                return True
            current = watched
            while current is not None:
                if current is self:
                    return True
                current = current.parentWidget()
        return False

    @staticmethod
    def _has_pdf_url_candidate(mime_data):
        if not mime_data or not mime_data.hasUrls():
            return False
        return any(
            url.isLocalFile() and url.toLocalFile().lower().endswith(".pdf")
            for url in mime_data.urls()
        )

    def _cursor_is_inside(self):
        return self.frameGeometry().contains(QCursor.pos())

    def _show_drop_overlay(self):
        if not hasattr(self, "drop_overlay"):
            return
        self.drop_overlay.setGeometry(self.tabs.rect())
        self.drop_overlay.raise_()
        self.drop_overlay.show()

    def eventFilter(self, watched, event):
        event_type = event.type()
        drag_types = (QEvent.Type.DragEnter, QEvent.Type.DragMove)

        if event_type in drag_types:
            if (
                self.isVisible()
                and self._drop_is_enabled()
                and self._cursor_is_inside()
                and self._has_pdf_url_candidate(event.mimeData())
            ):
                self._show_drop_overlay()
                event.acceptProposedAction()
                return True

        elif event_type == QEvent.Type.Drop:
            if self.isVisible() and self._drop_is_enabled() and self._cursor_is_inside():
                paths = self._pdf_paths(event.mimeData())
                if paths:
                    self._load_dropped_pdfs(paths)
                    self.drop_overlay.hide()
                    event.acceptProposedAction()
                    return True

        elif event_type == QEvent.Type.DragLeave:
            QTimer.singleShot(30, self._hide_overlay_if_cursor_left)

        return super().eventFilter(watched, event)

    def _hide_overlay_if_cursor_left(self):
        if hasattr(self, "drop_overlay") and not self._cursor_is_inside():
            self.drop_overlay.hide()

    def dragEnterEvent(self, event):
        if self._drop_is_enabled() and self._has_pdf_url_candidate(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        self.dragEnterEvent(event)

    def dropEvent(self, event):
        paths = self._pdf_paths(event.mimeData())
        if self._drop_is_enabled() and paths:
            self._load_dropped_pdfs(paths)
            event.acceptProposedAction()
        else:
            event.ignore()

    def _on_imp_pdf_state_changed(self, paths):
        if self._loading_geometry_into_imp:
            return
        self._last_drop_paths = list(paths)
        self._pages["GEO"].set_pdf_state(self._last_drop_paths)

    def _on_geometry_applied(self, path):
        self._geometry_output_path = str(path)
        self._load_geometry_output_into_imp()

    def _load_geometry_output_into_imp(self):
        if not self._geometry_output_path or self._loading_geometry_into_imp:
            return False
        geometry_output = Path(self._geometry_output_path).expanduser().resolve()
        if not geometry_output.is_file():
            return False
        imp = self._pages["IMP"]
        self._loading_geometry_into_imp = True
        try:
            imp.load_pdf(str(geometry_output))
            loaded_path = getattr(imp, "pdf_path", None)
            if loaded_path and Path(loaded_path).resolve() == geometry_output:
                self._geometry_output_path = None
                return True
            return False
        finally:
            self._loading_geometry_into_imp = False

    def _sync_geo_state(self, index=0):
        if index == self.TAB_ORDER.index("IMP"):
            self._load_geometry_output_into_imp()
            return
        if index == self.TAB_ORDER.index("GEO"):
            self._pages["GEO"].set_pdf_state(self._last_drop_paths)

    def _close_tools(self):
        imp = self._pages.get("IMP")
        if imp and hasattr(imp, "_clear_batch"):
            imp._clear_batch()
        geo = self._pages.get("GEO")
        if geo and hasattr(geo, "clear_pdf"):
            geo.clear_pdf()
        self.close()

    def _title_press(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def _title_move(self, event):
        if event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "drop_overlay"):
            self.drop_overlay.setGeometry(self.tabs.rect())

    def _restore_geometry(self):
        geometry = self.settings.value("tools_dialog/geometry")
        if geometry:
            self.restoreGeometry(geometry)

    def closeEvent(self, event):
        imp = self._pages.get("IMP")
        if imp and hasattr(imp, "_clear_batch") and getattr(imp, "batch_items", None):
            imp._clear_batch()
        geo = self._pages.get("GEO")
        if geo and hasattr(geo, "clear_pdf"):
            geo.clear_pdf()
        self.settings.setValue("tools_dialog/geometry", self.saveGeometry())
        super().closeEvent(event)

    def __del__(self):
        app = QApplication.instance()
        if app:
            app.removeEventFilter(self)
