from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEvent, QPoint, QSettings, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor, QCursor, QFont, QFontMetrics, QIcon, QKeySequence, QShortcut,
)
from PySide6.QtWidgets import (
    QApplication, QDialog, QHBoxLayout, QLabel, QSizeGrip, QSizePolicy,
    QStyle, QStyleOptionTab, QStylePainter, QTabBar, QTabWidget, QVBoxLayout,
    QWidget,
)

from ui.code_generator_dialog import CodeGeneratorDialog
from ui.geometry_widget import GeometryWidget
from ui.imposition_dialog import ImpositionDialog
from ui.montagem_dialog import MontagemDialog
from ui.organize_pages_widget import OrganizePagesWidget
from ui.widgets import DarkMetallicTitleBar

ROOT = Path(__file__).resolve().parent.parent
YELLOW = "#FFC400"


class ToolsTabBar(QTabBar):
    SHORTCUTS = ("", "⌘F16", "⌘F17", "⌘F18", "⌘F19")

    def paintEvent(self, event):
        painter = QStylePainter(self)
        for index in range(self.count()):
            option = QStyleOptionTab()
            self.initStyleOption(option, index)
            name = option.text
            option.text = ""
            painter.drawControl(QStyle.CE_TabBarTab, option)

            selected = bool(option.state & QStyle.State_Selected)
            name_font = QFont(self.font())
            name_font.setBold(True)
            shortcut_font = QFont(self.font())
            shortcut_font.setBold(False)
            shortcut_font.setPointSizeF(max(7.0, shortcut_font.pointSizeF() - 2.0))

            shortcut = self.SHORTCUTS[index] if index < len(self.SHORTCUTS) else ""
            name_width = QFontMetrics(name_font).horizontalAdvance(name)
            shortcut_width = QFontMetrics(shortcut_font).horizontalAdvance(shortcut)
            gap = 8 if shortcut else 0
            left = option.rect.center().x() - (name_width + gap + shortcut_width) // 2

            name_rect = option.rect.adjusted(left - option.rect.left(), 0, 0, 0)
            name_rect.setWidth(name_width)
            painter.setFont(name_font)
            painter.setPen(QColor(YELLOW if selected else "#777777"))
            painter.drawText(name_rect, Qt.AlignVCenter | Qt.AlignLeft, name)

            shortcut_rect = option.rect.adjusted(
                left + name_width + gap - option.rect.left(), 0, 0, 0
            )
            shortcut_rect.setWidth(shortcut_width)
            painter.setFont(shortcut_font)
            painter.setPen(QColor("#555555" if selected else "#444444"))
            painter.drawText(shortcut_rect, Qt.AlignVCenter | Qt.AlignLeft, shortcut)


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
    TAB_ORDER = ("ORG", "GEO", "IMP", "MON", "BAR")
    TAB_LABELS = ("ORGANIZAR PÁGINAS", "GEOMETRIA", "IMPOSIÇÃO", "MONTAGEM", "EAN-13")

    def __init__(self, parent=None, initial_tab="GEO"):
        super().__init__(parent)
        self.settings = QSettings("M87Tools", "M87Terminal")
        self.drag_position = QPoint()
        self._pages = {}
        self._last_drop_paths = []
        self._drop_guard_active = False
        self._geometry_output_path = None
        self._loading_geometry_into_imp = False
        self._syncing_pdf_state = False
        self._org_work_path = None
        self._org_work_payload = None
        self._setup_window()
        self._build_ui()
        self._setup_shortcuts()
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
        self.tabs.setTabBar(ToolsTabBar(self.tabs))

        org = OrganizePagesWidget(self)
        self._pages["ORG"] = org
        geo = GeometryWidget(self)
        self._pages["GEO"] = geo
        imp = self._embed_dialog(ImpositionDialog(self), "IMP")
        mon = self._embed_dialog(MontagemDialog(self), "MON")
        bar_page = self._embed_dialog(CodeGeneratorDialog(self), "BAR")
        for page, label in zip((org, geo, imp, mon, bar_page), self.TAB_LABELS):
            self.tabs.addTab(page, label)
        root.addWidget(self.tabs, 1)

        self.drop_overlay = PdfDropOverlay(self._pdf_paths, self.tabs)
        self.drop_overlay.pdfDropped.connect(self._load_dropped_pdfs)

        self._pages["IMP"].pdfStateChanged.connect(self._on_imp_pdf_state_changed)
        org.pdfStateChanged.connect(self._on_org_pdf_state_changed)
        org.workPdfChanged.connect(self._on_org_work_pdf_changed)
        geo.pdfStateChanged.connect(self._on_geo_pdf_state_changed)
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

    def _setup_shortcuts(self):
        tab_shortcuts = (
            (Qt.Key_F16, "GEO"),
            (Qt.Key_F17, "IMP"),
            (Qt.Key_F18, "MON"),
            (Qt.Key_F19, "BAR"),
        )
        self._tab_shortcuts = []
        undo_shortcut = QShortcut(
            QKeySequence.Undo,
            self,
            activated=self._undo_current_tab,
        )
        undo_shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        self._tab_shortcuts.append(undo_shortcut)
        for key, code in tab_shortcuts:
            shortcut = QShortcut(
                QKeySequence(Qt.ControlModifier | key),
                self,
                activated=lambda target=code: self.open_tab(target),
            )
            self._tab_shortcuts.append(shortcut)

        for key, step in ((Qt.Key_Right, 1), (Qt.Key_Left, -1)):
            shortcut = QShortcut(
                QKeySequence(Qt.ControlModifier | key),
                self,
                activated=lambda offset=step: self._change_tab(offset),
            )
            self._tab_shortcuts.append(shortcut)

    def _undo_current_tab(self):
        focus = QApplication.focusWidget()
        if focus and self._undo_focused_editor(focus):
            return
        code = self.TAB_ORDER[self.tabs.currentIndex()]
        page = self._pages.get(code)
        if code == "ORG" and page:
            page._undo_action()
        elif code == "GEO" and page and hasattr(page, "undo_last_action"):
            page.undo_last_action()

    @staticmethod
    def _undo_focused_editor(widget):
        if hasattr(widget, "isReadOnly") and widget.isReadOnly():
            return False
        if hasattr(widget, "isUndoAvailable") and widget.isUndoAvailable():
            widget.undo()
            return True
        document = widget.document() if hasattr(widget, "document") else None
        if document and document.isUndoAvailable():
            widget.undo()
            return True
        return False

    def _change_tab(self, step):
        count = self.tabs.count()
        if count:
            self.tabs.setCurrentIndex((self.tabs.currentIndex() + step) % count)

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

    def open_pdfs(self, paths, tab="IMP"):
        """Carrega PDFs na janela compartilhada e abre a ferramenta pedida."""
        paths = list(paths or [])
        if paths:
            self._set_pdf_paths(paths)
        self.open_tab(tab)

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
            self.TAB_ORDER.index("ORG"),
        )

    def _load_dropped_pdfs(self, paths):
        if not paths or self._drop_guard_active:
            return
        # Um mesmo Drop pode atravessar mais de um filtro Qt. Este pequeno
        # bloqueio impede carregar o lote duas vezes sem alterar a experiência.
        self._drop_guard_active = True
        try:
            self._set_pdf_paths(paths)
        finally:
            QTimer.singleShot(0, self._release_drop_guard)

    def _set_pdf_paths(self, paths):
        self._last_drop_paths = list(paths)
        self._org_work_path = None
        self._org_work_payload = None
        self._syncing_pdf_state = True
        try:
            self._pages["ORG"].load_pdfs(self._last_drop_paths)
            self._pages["IMP"].load_pdfs(self._last_drop_paths)
            self._pages["GEO"].set_pdf_state(self._last_drop_paths)
        finally:
            self._syncing_pdf_state = False
        self._pages["ORG"].set_sync_status(
            self._tools_have_path(self._last_drop_paths[0])
        )

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

        if (
            event_type == QEvent.Type.KeyPress
            and self.isVisible()
            and self._event_belongs_to_tools(watched)
            and event.matches(QKeySequence.Paste)
        ):
            paths = self._clipboard_pdf_paths()
            if paths:
                self._set_pdf_paths(paths)
                return True

        if (
            event_type == QEvent.Type.KeyPress
            and self.isVisible()
            and self._event_belongs_to_tools(watched)
            and event.modifiers() & Qt.ControlModifier
        ):
            tab_by_key = {
                Qt.Key_F16: "GEO",
                Qt.Key_F17: "IMP",
                Qt.Key_F18: "MON",
                Qt.Key_F19: "BAR",
            }
            if event.key() in tab_by_key:
                self.open_tab(tab_by_key[event.key()])
                return True
            if event.key() == Qt.Key_Right:
                self._change_tab(1)
                return True
            if event.key() == Qt.Key_Left:
                self._change_tab(-1)
                return True

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
        if self._loading_geometry_into_imp or self._syncing_pdf_state:
            return
        self._last_drop_paths = list(paths)
        self._pages["GEO"].set_pdf_state(self._last_drop_paths)

    def _on_org_pdf_state_changed(self, paths):
        self._last_drop_paths = list(paths)
        self._org_work_path = None
        self._org_work_payload = None
        if self._syncing_pdf_state:
            return
        self._syncing_pdf_state = True
        try:
            self._pages["IMP"].load_pdfs(self._last_drop_paths)
            self._pages["GEO"].set_pdf_state(self._last_drop_paths)
        finally:
            self._syncing_pdf_state = False
        if self._last_drop_paths:
            self._pages["ORG"].set_sync_status(
                self._tools_have_path(self._last_drop_paths[0])
            )

    def _tools_have_path(self, path):
        desired = Path(path).expanduser().resolve()
        for code in ("GEO", "IMP"):
            loaded = getattr(self._pages[code], "pdf_path", None)
            if not loaded or Path(loaded).expanduser().resolve() != desired:
                return False
        return True

    def _on_org_work_pdf_changed(self, payload):
        path = Path(payload.get("path", "")).expanduser().resolve()
        source = Path(payload.get("source", "")).expanduser().resolve()
        if not path.is_file():
            return
        self._org_work_path = str(path)
        self._org_work_payload = {"path": str(path), "source": str(source)}
        self._apply_org_work_to_tools()

    def _apply_org_work_to_tools(self):
        payload = self._org_work_payload
        if not payload:
            return
        path = Path(payload["path"])
        source = Path(payload["source"])
        if not path.is_file():
            return
        self._syncing_pdf_state = True
        imp_ok = False
        geo_ok = False
        try:
            imp = self._pages["IMP"]
            imp_path = getattr(imp, "pdf_path", None)
            if not imp_path or Path(imp_path).resolve() != path.resolve():
                imp.load_pdf(str(path), naming_path=str(source))
            imp_path = getattr(imp, "pdf_path", None)
            imp_ok = bool(imp_path and Path(imp_path).resolve() == path.resolve())
            geo = self._pages["GEO"]
            geo_path = getattr(geo, "pdf_path", None)
            if not geo_path or Path(geo_path).resolve() != path.resolve():
                geo.set_pdf_state([str(path)])
            geo_path = getattr(geo, "pdf_path", None)
            geo_ok = bool(geo_path and Path(geo_path).resolve() == path.resolve())
        finally:
            self._syncing_pdf_state = False
        self._pages["ORG"].set_sync_status(imp_ok and geo_ok)

    def _on_geo_pdf_state_changed(self, paths):
        if self._syncing_pdf_state or not self._org_work_payload or not paths:
            return
        desired = Path(self._org_work_payload["path"]).resolve()
        loaded = Path(paths[0]).expanduser().resolve()
        if loaded == desired:
            self._apply_org_work_to_tools()

    @staticmethod
    def _clipboard_pdf_paths():
        clipboard = QApplication.clipboard()
        mime_data = clipboard.mimeData() if clipboard else None
        paths = ToolsDialog._pdf_paths(mime_data)
        if paths:
            return paths
        text = clipboard.text().strip() if clipboard else ""
        if text.startswith("file://"):
            from PySide6.QtCore import QUrl
            text = QUrl(text).toLocalFile()
        candidate = Path(text).expanduser() if text else None
        if candidate and candidate.is_file() and candidate.suffix.casefold() == ".pdf":
            return [str(candidate.resolve())]
        return []

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
        geo = self._pages["GEO"]
        original_path = getattr(geo, "pdf_path", None)
        self._loading_geometry_into_imp = True
        try:
            imp.load_pdf(str(geometry_output), naming_path=original_path)
            loaded_path = getattr(imp, "pdf_path", None)
            if loaded_path and Path(loaded_path).resolve() == geometry_output:
                self._geometry_output_path = None
                return True
            return False
        finally:
            self._loading_geometry_into_imp = False

    def _sync_geo_state(self, index=0):
        if self._org_work_payload:
            self._apply_org_work_to_tools()
        if index == self.TAB_ORDER.index("IMP"):
            imp = self._pages["IMP"]
            if hasattr(imp, "refresh_paper_library"):
                imp.refresh_paper_library()
            self._load_geometry_output_into_imp()
            return
        if index == self.TAB_ORDER.index("GEO"):
            paths = [self._org_work_path] if self._org_work_path else self._last_drop_paths
            self._pages["GEO"].set_pdf_state(paths)
            return

    def _close_tools(self):
        self.close()

    def _release_all_pdfs(self):
        self._last_drop_paths = []
        self._org_work_path = None
        self._org_work_payload = None
        self._geometry_output_path = None
        self._loading_geometry_into_imp = False
        self._syncing_pdf_state = True
        try:
            org = self._pages.get("ORG")
            if org and hasattr(org, "clear_pdf"):
                org.clear_pdf()
            imp = self._pages.get("IMP")
            if imp and hasattr(imp, "_clear_batch"):
                imp._clear_batch()
            geo = self._pages.get("GEO")
            if geo and hasattr(geo, "set_pdf_state"):
                # Se houver worker ativo, GEO conserva este pedido vazio e
                # executa a liberação assim que o processamento terminar.
                geo.set_pdf_state([])
        finally:
            self._syncing_pdf_state = False

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
        self._release_all_pdfs()
        self.settings.setValue("tools_dialog/geometry", self.saveGeometry())
        super().closeEvent(event)

    def __del__(self):
        app = QApplication.instance()
        if app:
            app.removeEventFilter(self)
