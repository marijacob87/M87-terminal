from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEvent, QPoint, QSettings, Qt, QTimer
from PySide6.QtGui import (
    QCursor, QIcon, QKeySequence, QShortcut,
)
from PySide6.QtWidgets import (
    QApplication, QDialog, QHBoxLayout, QLabel, QSizeGrip, QSizePolicy,
    QTabWidget, QVBoxLayout, QWidget,
)

from ui.code_generator_dialog import CodeGeneratorDialog
from ui.colors_widget import ColorsWidget
from ui.geometry_widget import GeometryWidget
from ui.imposition_dialog import ImpositionDialog
from ui.montagem_dialog import MontagemDialog
from ui.organize_pages_widget import OrganizePagesWidget
from ui.pdf_summary_widget import PdfSummaryWidget
from ui.tools_components import PdfDropOverlay, ToolsTabBar
from ui.widgets import DarkMetallicTitleBar

ROOT = Path(__file__).resolve().parent.parent
YELLOW = "#FFC400"


class ToolsDialog(QDialog):
    TAB_ORDER = ("RES", "ORG", "GEO", "COL", "IMP", "CIM", "MON", "BAR")
    TAB_LABELS = (
        "RESUMO", "ORGANIZAR PÁGINAS", "GEOMETRIA", "CORES",
        "IMPOSIÇÃO AUTOMÁTICA", "CRIAR IMPOSIÇÃO", "MONTAGEM", "EAN-13",
    )

    def __init__(self, parent=None, initial_tab="RES", show_on_create=True):
        super().__init__(parent)
        self.settings = QSettings("M87Tools", "M87Terminal")
        self.drag_position = QPoint()
        self._pages = {}
        self._last_drop_paths = []
        self._drop_guard_active = False
        self._geometry_output_path = None
        self._loading_geometry_into_imp = False
        self._syncing_pdf_state = False
        self._manual_imposition_dialog = None
        self._pdf_load_generation = 0
        self._org_work_path = None
        self._org_work_payload = None
        self._setup_window()
        self._build_ui()
        self._setup_shortcuts()
        self._prepare_drop_targets()
        self._restore_geometry()
        if (
            show_on_create
            and
            initial_tab == "RES"
            and self.settings.value(
                "general/restore_last_tool", True, type=bool
            )
        ):
            saved_tab = str(self.settings.value("tools_dialog/last_tab", "RES"))
            if saved_tab in self.TAB_ORDER:
                initial_tab = saved_tab
        if show_on_create:
            self.open_tab(initial_tab)
        else:
            if initial_tab not in self.TAB_ORDER:
                initial_tab = "RES"
            self.tabs.setCurrentIndex(self.TAB_ORDER.index(initial_tab))
            self.hide()
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

        summary = PdfSummaryWidget(self)
        self._pages["RES"] = summary
        org = OrganizePagesWidget(self)
        self._pages["ORG"] = org
        geo = GeometryWidget(self)
        self._pages["GEO"] = geo
        colors = ColorsWidget(self)
        self._pages["COL"] = colors
        colors.pdfDropped.connect(self._load_dropped_pdfs)
        imp = self._embed_dialog(ImpositionDialog(self), "IMP")
        custom_imp = QWidget(self.tabs)
        custom_imp.setObjectName("cimPage")
        custom_imp.setLayout(QVBoxLayout())
        custom_imp.layout().setContentsMargins(0, 0, 0, 0)
        custom_imp.layout().setSpacing(0)
        custom_status = QLabel("Carregando Criar Imposição…", custom_imp)
        custom_status.setAlignment(Qt.AlignCenter)
        custom_status.setObjectName("cimStatus")
        custom_imp.layout().addWidget(custom_status, 1)
        self._pages["CIM"] = custom_imp
        mon = self._embed_dialog(MontagemDialog(self), "MON")
        bar_page = self._embed_dialog(CodeGeneratorDialog(self), "BAR")
        for page, label in zip(
            (summary, org, geo, colors, imp, custom_imp, mon, bar_page),
            self.TAB_LABELS,
        ):
            self.tabs.addTab(page, label)
        root.addWidget(self.tabs, 1)

        self.drop_overlay = PdfDropOverlay(self._pdf_paths, self.tabs)
        self.drop_overlay.pdfDropped.connect(self._load_dropped_pdfs)

        self._pages["IMP"].pdfStateChanged.connect(self._on_imp_pdf_state_changed)
        org.pdfStateChanged.connect(self._on_org_pdf_state_changed)
        org.workPdfChanged.connect(self._on_org_work_pdf_changed)
        geo.pdfStateChanged.connect(self._on_geo_pdf_state_changed)
        geo.appliedPdfChanged.connect(self._on_geometry_applied)
        self.tabs.currentChanged.connect(self._tab_changed)

        grip_row = QHBoxLayout()
        grip_row.setContentsMargins(0, 0, 4, 0)
        grip_row.addStretch()
        grip_row.addWidget(QSizeGrip(self.box))
        root.addLayout(grip_row)
        QShortcut(QKeySequence(Qt.Key_Escape), self, activated=self._close_tools)

        self.setStyleSheet(f"""
            QWidget {{ font-family:'JetBrains Mono'; font-size:11px; }}
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
        self._tab_shortcuts = []
        undo_shortcut = QShortcut(
            QKeySequence.Undo,
            self,
            activated=self._undo_current_tab,
        )
        undo_shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        self._tab_shortcuts.append(undo_shortcut)
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
        elif code == "CIM" and self._manual_imposition_dialog is not None:
            self._manual_imposition_dialog.undo_last_action()
        elif page and hasattr(page, "undo_last_action"):
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

        box_name = {
            "IMP": "impBox", "CIM": "manualImpBox",
            "MON": "monBox", "BAR": "barBox",
        }.get(code)
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
            code = "RES"
        self.tabs.setCurrentIndex(self.TAB_ORDER.index(code))
        if not self.isVisible():
            self.show()
        self.raise_()
        self.activateWindow()

    def open_pdfs(self, paths, tab="RES", summary_info=None):
        """Carrega PDFs na janela compartilhada e abre a ferramenta pedida."""
        paths = list(paths or [])
        # A janela precisa aparecer mesmo que uma das ferramentas secundárias
        # encontre um PDF que não consiga interpretar.
        self.open_tab(tab)
        QApplication.processEvents()
        if paths:
            self._pdf_load_generation += 1
            generation = self._pdf_load_generation

            def load_after_open():
                if generation != self._pdf_load_generation:
                    return
                self._set_pdf_paths(paths, summary_info=summary_info)

            QTimer.singleShot(0, load_after_open)

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
        # O PDF pertence à janela compartilhada, não à aba visível.
        # Aceitá-lo em toda a janela evita exigir que o usuário navegue antes.
        return 0 <= self.tabs.currentIndex() < self.tabs.count()

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

    def _set_pdf_paths(self, paths, summary_info=None):
        self._last_drop_paths = list(paths)
        self._geometry_output_path = None
        self._org_work_path = None
        self._org_work_payload = None
        self._syncing_pdf_state = True
        try:
            # O Resumo é a única aba carregada imediatamente. As demais usam
            # o mesmo caminho quando forem abertas, evitando processar o PDF
            # seis vezes durante o drop.
            self._pages["RES"].load_pdfs(
                self._last_drop_paths,
                info=summary_info,
            )
        finally:
            self._syncing_pdf_state = False

    def _release_drop_guard(self):
        self._drop_guard_active = False

    def _event_belongs_to_tools(self, watched):
        # O filtro também está instalado no QApplication. Nessa situação,
        # validamos se o objeto que recebeu o evento pertence a esta janela.
        if watched is self or watched is self.box or watched is self.tabs:
            return True
        if self.windowHandle() is not None and watched is self.windowHandle():
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
        current = watched
        while current is not None and hasattr(current, "parent"):
            if current is self:
                return True
            current = current.parent()
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
                and self._event_belongs_to_tools(watched)
                and self._has_pdf_url_candidate(event.mimeData())
            ):
                # No macOS/Retina, QCursor.pos() pode estar em outra escala.
                # O próprio receptor do evento é a referência segura para
                # saber que o arraste está dentro desta janela.
                if hasattr(self, "drop_overlay"):
                    self.drop_overlay.hide()
                event.acceptProposedAction()
                return True

        elif event_type == QEvent.Type.Drop:
            if (
                self.isVisible()
                and self._drop_is_enabled()
                and self._event_belongs_to_tools(watched)
            ):
                paths = self._pdf_paths(event.mimeData())
                if paths:
                    self._load_dropped_pdfs(paths)
                    self.drop_overlay.hide()
                    event.acceptProposedAction()
                    return True

        elif event_type == QEvent.Type.DragLeave:
            if hasattr(self, "drop_overlay"):
                self.drop_overlay.hide()

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
        self._geometry_output_path = None
        self._pages["GEO"].set_pdf_state(self._last_drop_paths)
        self._pages["COL"].load_pdfs(self._last_drop_paths)

    def _on_org_pdf_state_changed(self, paths):
        if self._syncing_pdf_state:
            return
        self._last_drop_paths = list(paths)
        self._geometry_output_path = None
        self._org_work_path = None
        self._org_work_payload = None
        self._syncing_pdf_state = True
        try:
            self._pages["IMP"].load_pdfs(self._last_drop_paths)
            self._pages["GEO"].set_pdf_state(self._last_drop_paths)
            self._pages["COL"].load_pdfs(self._last_drop_paths)
        finally:
            self._syncing_pdf_state = False
        if self._last_drop_paths:
            self._pages["ORG"].set_sync_status(
                self._tools_have_path(self._last_drop_paths[0])
            )

    def _tools_have_path(self, path):
        desired = Path(path).expanduser().resolve()
        for code in ("GEO", "IMP", "COL"):
            attribute = "_path" if code == "COL" else "pdf_path"
            loaded = getattr(self._pages[code], attribute, None)
            if not loaded or Path(loaded).expanduser().resolve() != desired:
                return False
        return True

    def _on_org_work_pdf_changed(self, payload):
        path = Path(payload.get("path", "")).expanduser().resolve()
        source = Path(payload.get("source", "")).expanduser().resolve()
        if not path.is_file():
            return
        self._geometry_output_path = None
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
            colors = self._pages["COL"]
            color_path = getattr(colors, "_path", None)
            if not color_path or Path(color_path).resolve() != path.resolve():
                colors.load_pdfs([str(path)])
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
        self._org_work_path = None
        self._org_work_payload = None
        self._apply_geometry_output_to_tools()

    def _active_work_path(self):
        candidates = (
            self._geometry_output_path,
            self._org_work_path,
            self._last_drop_paths[0] if self._last_drop_paths else None,
        )
        for raw_path in candidates:
            if not raw_path:
                continue
            path = Path(raw_path).expanduser().resolve()
            if path.is_file():
                return path
        return None

    def _apply_geometry_output_to_tools(self):
        if not self._geometry_output_path:
            return False
        geometry_output = Path(
            self._geometry_output_path
        ).expanduser().resolve()
        if not geometry_output.is_file():
            return False
        geo = self._pages["GEO"]
        original_path = getattr(geo, "pdf_path", None)
        paths = [str(geometry_output)]
        self._loading_geometry_into_imp = True
        self._syncing_pdf_state = True
        try:
            self._pages["RES"].load_pdfs(paths)
            self._pages["ORG"].load_pdfs(paths)
            self._pages["IMP"].load_pdf(
                str(geometry_output), naming_path=original_path
            )
            if self._manual_imposition_dialog is not None:
                self._manual_imposition_dialog.load_pdfs(paths)
            self._pages["COL"].load_pdfs(paths)
        finally:
            self._syncing_pdf_state = False
            self._loading_geometry_into_imp = False
        return True

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
            return bool(
                loaded_path and Path(loaded_path).resolve() == geometry_output
            )
        finally:
            self._loading_geometry_into_imp = False

    def _sync_geo_state(self, index=0):
        if self._org_work_payload and not self._geometry_output_path:
            self._apply_org_work_to_tools()
        if index == self.TAB_ORDER.index("IMP"):
            imp = self._pages["IMP"]
            desired = self._active_work_path()
            if desired is not None:
                loaded = getattr(imp, "pdf_path", None)
                if not loaded or Path(loaded).expanduser().resolve() != desired:
                    original = getattr(self._pages["GEO"], "pdf_path", None)
                    imp.load_pdf(str(desired), naming_path=original)
            if hasattr(imp, "refresh_paper_library"):
                imp.refresh_paper_library()
            return
        if index == self.TAB_ORDER.index("ORG"):
            desired = self._active_work_path()
            current = getattr(self._pages["ORG"], "current_path", None)
            if desired is not None and (
                not current or Path(current).resolve() != desired
            ):
                self._pages["ORG"].load_pdfs([str(desired)])
            return
        if index == self.TAB_ORDER.index("GEO"):
            if self._geometry_output_path:
                return
            paths = [self._org_work_path] if self._org_work_path else self._last_drop_paths
            self._pages["GEO"].set_pdf_state(paths)
            return
        if index == self.TAB_ORDER.index("COL"):
            active = self._active_work_path()
            paths = [str(active)] if active is not None else []
            current = getattr(self._pages["COL"], "_path", None)
            if paths and (
                not current or Path(current).resolve() != Path(paths[0]).resolve()
            ):
                self._pages["COL"].load_pdfs(paths)
            return

    def _tab_changed(self, index):
        if 0 <= index < len(self.TAB_ORDER):
            self.settings.setValue("tools_dialog/last_tab", self.TAB_ORDER[index])
        if index == self.TAB_ORDER.index("CIM"):
            self._initialize_manual_imposition()
        self._sync_geo_state(index)

    def _initialize_manual_imposition(self):
        try:
            self._ensure_manual_imposition()
        except Exception as error:
            page = self._pages["CIM"]
            status = page.findChild(QLabel, "cimStatus")
            if status:
                status.setText(
                    "Não foi possível abrir Criar Imposição.\n"
                    f"{type(error).__name__}: {error}"
                )
            print(
                "[CRIAR IMPOSIÇÃO] "
                f"{type(error).__name__}: {error}"
            )

    def _ensure_manual_imposition(self):
        if self._manual_imposition_dialog is not None:
            return self._manual_imposition_dialog
        from ui.manual_imposition_dialog import ManualImpositionDialog

        page = self._pages["CIM"]
        dialog = ManualImpositionDialog(self)
        dialog.setWindowFlags(Qt.Widget)
        dialog.setAttribute(Qt.WA_TranslucentBackground, False)
        dialog.setMinimumSize(0, 0)
        dialog.setMaximumSize(16777215, 16777215)
        dialog.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        dialog.setParent(page)
        box = dialog.findChild(QWidget, "manualImpBox")
        if box:
            box.setProperty("embedded", True)
            box.style().unpolish(box)
            box.style().polish(box)
        while page.layout().count():
            item = page.layout().takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        page.layout().addWidget(dialog, 1)
        dialog.pdfStateChanged.connect(self._on_imp_pdf_state_changed)
        self._manual_imposition_dialog = dialog
        dialog.show()
        active = self._active_work_path()
        if active is not None:
            dialog.load_pdfs([str(active)])
        return dialog

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
            summary = self._pages.get("RES")
            if summary and hasattr(summary, "clear_pdf"):
                summary.clear_pdf()
            imp = self._pages.get("IMP")
            if imp and hasattr(imp, "_clear_batch"):
                imp._clear_batch()
            geo = self._pages.get("GEO")
            if geo and hasattr(geo, "set_pdf_state"):
                # Se houver worker ativo, GEO conserva este pedido vazio e
                # executa a liberação assim que o processamento terminar.
                geo.set_pdf_state([])
            colors = self._pages.get("COL")
            if colors and hasattr(colors, "clear_pdf"):
                colors.clear_pdf()
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
        if not self.settings.value(
            "general/remember_geometry", True, type=bool
        ):
            return
        geometry = self.settings.value("tools_dialog/geometry")
        if geometry:
            self.restoreGeometry(geometry)

    def closeEvent(self, event):
        self._release_all_pdfs()
        if self.settings.value(
            "general/remember_geometry", True, type=bool
        ):
            self.settings.setValue("tools_dialog/geometry", self.saveGeometry())
        super().closeEvent(event)

    def __del__(self):
        app = QApplication.instance()
        if app:
            app.removeEventFilter(self)
