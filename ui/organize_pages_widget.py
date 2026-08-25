from __future__ import annotations

import tempfile
from pathlib import Path

import fitz
from PySide6.QtCore import QMimeData, QSize, Qt, Signal
from PySide6.QtGui import QColor, QDrag, QIcon, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMessageBox, QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from core.page_organizer import (
    PageSpec, page_specs, reorder_pages, rotated, save_pages, split_pages,
)
from core.preferences import save_path
from core.geometry import GeometryError, inspect_geometry
from ui.tool_design import (
    TOOL_CARD_MARGINS, TOOL_CARD_SPACING, TOOL_COLUMN_SPACING, TOOL_CONTROLS_WIDTH,
    TOOL_PAGE_MARGINS, TOOL_PAGE_SPACING, TOOL_STANDARD_QSS, ToolActionBar,
    ToolPreviewToolbar,
    create_pdf_file_card, set_open_pdf_loaded,
    apply_terminal_accent, draw_empty_pdf_message, format_pdf_file_summary,
    set_document_control_enabled, set_tool_role, show_button_success,
)
from ui.konica_print import spool_pdf


class PageList(QListWidget):
    reorderRequested = Signal(object, int)
    DRAG_MIME = "application/x-m87-page-reorder"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._drop_index = None

    def dragEnterEvent(self, event):
        if event.source() is self and event.mimeData().hasFormat(self.DRAG_MIME):
            event.setDropAction(Qt.CopyAction)
            event.accept()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.source() is not self or not event.mimeData().hasFormat(self.DRAG_MIME):
            super().dragMoveEvent(event)
            return
        self._drop_index = self._insertion_index(event.position().toPoint())
        self.viewport().update()
        event.setDropAction(Qt.CopyAction)
        event.accept()

    def dragLeaveEvent(self, event):
        self._clear_drop_indicator()
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        if (
            event.source() is not self
            or not event.mimeData().hasFormat(self.DRAG_MIME)
            or self._drop_index is None
        ):
            self._clear_drop_indicator()
            super().dropEvent(event)
            return

        selected_rows = sorted(self.row(item) for item in self.selectedItems())
        target = self._drop_index
        self._clear_drop_indicator()
        # CopyAction impede o QListWidget de apagar os itens de origem depois
        # do drop. A mudança real acontece atomicamente no modelo do M87.
        event.setDropAction(Qt.CopyAction)
        event.accept()
        self.reorderRequested.emit(selected_rows, target)

    def startDrag(self, _supported_actions):
        if not self.selectedItems():
            return
        mime_data = QMimeData()
        mime_data.setData(self.DRAG_MIME, b"m87")
        drag = QDrag(self)
        drag.setMimeData(mime_data)
        current = self.currentItem()
        if current and not current.icon().isNull():
            drag.setPixmap(current.icon().pixmap(QSize(72, 92)))
        drag.exec(Qt.CopyAction)

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.count():
            painter = QPainter(self.viewport())
            draw_empty_pdf_message(painter, self.viewport().rect())
        geometry = self._indicator_geometry()
        if geometry is None:
            return
        x, top, bottom = geometry
        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor("#FFC400"), 3))
        painter.drawLine(x, top, x, bottom)

    def _insertion_index(self, position):
        if not self.count():
            return 0
        item = self.itemAt(position)
        if item is None:
            item = min(
                (self.item(index) for index in range(self.count())),
                key=lambda candidate: (
                    self.visualItemRect(candidate).center() - position
                ).manhattanLength(),
            )
        index = self.row(item)
        rect = self.visualItemRect(item)
        if position.y() < rect.top():
            return index
        if position.y() > rect.bottom():
            return index + 1
        return index if position.x() < rect.center().x() else index + 1

    def _indicator_geometry(self):
        if self._drop_index is None or not self.count():
            return None
        if self._drop_index < self.count():
            rect = self.visualItemRect(self.item(self._drop_index))
            return rect.left() - 5, rect.top() + 3, rect.bottom() - 3
        rect = self.visualItemRect(self.item(self.count() - 1))
        return rect.right() + 5, rect.top() + 3, rect.bottom() - 3

    def _clear_drop_indicator(self):
        self._drop_index = None
        self.viewport().update()


class OrganizePagesWidget(QWidget):
    pdfStateChanged = Signal(object)
    workPdfChanged = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("toolSurface", True)
        self.current_path: Path | None = None
        self._pages: list[PageSpec] = []
        self._undo: list[list[PageSpec]] = []
        self._redo: list[list[PageSpec]] = []
        self._icon_cache: dict[PageSpec, QIcon] = {}
        self._work_dir = tempfile.TemporaryDirectory(prefix="m87_org_")
        self._work_generation = 0
        self._thumbnail_zoom = 1.0
        self._build_ui()
        apply_terminal_accent(self)
        self.setStyleSheet(TOOL_STANDARD_QSS + self._qss())
        self._update_actions()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(*TOOL_PAGE_MARGINS)
        root.setSpacing(TOOL_PAGE_SPACING)
        body = QHBoxLayout()
        body.setSpacing(TOOL_COLUMN_SPACING)

        sidebar = QWidget()
        sidebar.setProperty("toolRole", "controls")
        sidebar.setFixedWidth(TOOL_CONTROLS_WIDTH)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(TOOL_PAGE_SPACING)

        file_card, self.open_button, self.file_label = create_pdf_file_card(
            self._choose_pdf
        )
        sidebar_layout.addWidget(file_card)

        selection_card, selection_layout = self._card("PÁGINAS SELECIONADAS")
        range_row = QHBoxLayout()
        range_row.setSpacing(6)
        self.range_edit = QLineEdit()
        self.range_edit.setPlaceholderText("1, 3-6")
        self.range_edit.returnPressed.connect(self._select_range)
        range_row.addWidget(self.range_edit, 1)
        range_row.addWidget(self._button("SELECIONAR", self._select_range))
        selection_layout.addLayout(range_row)
        filters = QHBoxLayout()
        filters.setSpacing(6)
        filters.addWidget(self._button("TODAS", self._select_all))
        filters.addWidget(self._button("PARES", lambda: self._select_kind("even")))
        filters.addWidget(self._button("ÍMPARES", lambda: self._select_kind("odd")))
        selection_layout.addLayout(filters)
        orientation = QHBoxLayout()
        orientation.setSpacing(6)
        orientation.addWidget(self._button("RETRATO", lambda: self._select_kind("portrait")))
        orientation.addWidget(self._button("PAISAGEM", lambda: self._select_kind("landscape")))
        selection_layout.addLayout(orientation)
        sidebar_layout.addWidget(selection_card)

        options_card, options_layout = self._card("OPÇÕES DE PÁGINA")
        transform_row = QHBoxLayout()
        transform_row.setSpacing(6)
        self.left_button = self._button("↶ 90°", lambda: self._rotate(-90))
        self.right_button = self._button("↷ 90°", lambda: self._rotate(90))
        self.duplicate_button = self._button("DUPLICAR", self._duplicate)
        self.delete_button = self._button("EXCLUIR", self._delete)
        for button in (self.left_button, self.right_button, self.duplicate_button, self.delete_button):
            transform_row.addWidget(button)
        options_layout.addLayout(transform_row)
        history_row = QHBoxLayout()
        history_row.setSpacing(6)
        self.undo_button = self._button("DESFAZER", self._undo_action)
        self.redo_button = self._button("REFAZER", self._redo_action)
        history_row.addWidget(self.undo_button)
        history_row.addWidget(self.redo_button)
        options_layout.addLayout(history_row)
        sidebar_layout.addWidget(options_card)

        document_card, document_layout = self._card("DOCUMENTO")
        self.insert_button = self._button("INSERIR", self._insert_pdf)
        self.replace_button = self._button("SUBSTITUIR", self._replace_pages)
        self.extract_button = self._button("EXTRAIR", self._extract_pages)
        self.split_button = self._button("DIVIDIR", self._split_pages)
        for button in (self.insert_button, self.replace_button, self.extract_button, self.split_button):
            button.setProperty("orgAction", True)
            document_layout.addWidget(button)
        sidebar_layout.addWidget(document_card)
        self._document_cards = (
            selection_card, options_card, document_card,
        )
        sidebar_layout.addStretch()
        body.addWidget(sidebar)

        workspace = QVBoxLayout()
        workspace.setContentsMargins(0, 0, 0, 0)
        workspace.setSpacing(TOOL_PAGE_SPACING)

        self.preview_toolbar = ToolPreviewToolbar()
        self.preview_toolbar.previous_button.clicked.connect(
            lambda: self._change_preview_page(-1)
        )
        self.preview_toolbar.next_button.clicked.connect(
            lambda: self._change_preview_page(1)
        )
        self.preview_toolbar.rotation_undo_button.clicked.connect(self._undo_action)
        self.preview_toolbar.rotate_button.clicked.connect(self._rotate_from_toolbar)
        self.preview_toolbar.zoom_out_button.clicked.connect(
            lambda: self._set_thumbnail_zoom(self._thumbnail_zoom - .25)
        )
        self.preview_toolbar.zoom_label.clicked.connect(
            lambda: self._set_thumbnail_zoom(1.0)
        )
        self.preview_toolbar.zoom_in_button.clicked.connect(
            lambda: self._set_thumbnail_zoom(self._thumbnail_zoom + .25)
        )
        workspace.addWidget(self.preview_toolbar)

        self.pages = PageList()
        self.pages.setViewMode(QListWidget.IconMode)
        self.pages.setResizeMode(QListWidget.Adjust)
        self.pages.setMovement(QListWidget.Snap)
        self.pages.setDragDropMode(QListWidget.DragDrop)
        self.pages.setDragEnabled(True)
        self.pages.setAcceptDrops(True)
        self.pages.setDropIndicatorShown(True)
        self.pages.setDragDropOverwriteMode(False)
        self.pages.setDefaultDropAction(Qt.CopyAction)
        self.pages.setSelectionMode(QListWidget.ExtendedSelection)
        self.pages.setIconSize(QSize(126, 166))
        self.pages.setGridSize(QSize(156, 205))
        self.pages.setSpacing(4)
        self.pages.reorderRequested.connect(self._order_changed)
        self.pages.itemSelectionChanged.connect(self._update_actions)
        workspace.addWidget(self.pages, 1)

        footer = QHBoxLayout()
        self.status = QLabel("ARRASTE UM PDF PARA COMEÇAR")
        self.status.setObjectName("orgStatus")
        self.status.hide()
        self.sync_status = QLabel("")
        self.sync_status.setObjectName("orgSyncStatus")
        self.hint = QLabel("⌘ clique seleciona várias · Shift seleciona intervalo · arraste para reordenar")
        self.hint.setObjectName("orgHint")
        footer.addWidget(self.sync_status)
        footer.addStretch()
        footer.addWidget(self.hint)
        workspace.addLayout(footer)
        body.addLayout(workspace, 1)
        root.addLayout(body, 1)

        self.action_bar = ToolActionBar(
            restore=self._restore_original,
            print_file=self._print_current,
            save_as=self._save_as,
        )
        self.restore_button = self.action_bar.restore_button
        self.print_button = self.action_bar.print_button
        self.save_button = self.action_bar.save_button
        root.addLayout(self.action_bar)

    def _card(self, title):
        card = QFrame()
        set_tool_role(card, "card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(*TOOL_CARD_MARGINS)
        layout.setSpacing(TOOL_CARD_SPACING)
        label = QLabel(title)
        set_tool_role(label, "cardTitle")
        layout.addWidget(label)
        return card, layout

    def _button(self, text, callback, primary=False):
        button = QPushButton(text)
        set_tool_role(button, "chip")
        if primary:
            button.setProperty("orgPrimary", True)
        button.clicked.connect(callback)
        return button

    def _qss(self):
        return """
        QLabel#orgHeading { color:#FFC400; font-size:11px; font-weight:700; letter-spacing:1px; padding:2px 2px 0 2px; }
        QListWidget { background:#050607; border:0; border-radius:0; color:rgba(255,255,255,.78); outline:0; padding:8px; }
        QListWidget::item { background:rgba(255,255,255,.025); border:1px solid rgba(255,255,255,.08); border-radius:5px; padding:7px; }
        QListWidget::item:hover { border-color:rgba(255,196,0,.28); background:rgba(255,196,0,.035); }
        QListWidget::item:selected { color:#FFC400; border:1px solid rgba(255,196,0,.65); background:rgba(255,196,0,.10); }
        QPushButton[orgPrimary="true"] { color:#FFC400; border-color:rgba(255,196,0,.40); background:rgba(255,196,0,.08); }
        QPushButton[orgAction="true"] { text-align:left; padding-left:12px; }
        QLabel#orgStatus { color:#FFC400; font-size:10px; font-weight:700; }
        QLabel#orgSyncStatus { color:rgba(255,255,255,.45); font-size:9px; font-weight:700; }
        QLabel#orgSyncStatus[syncState="ok"] { color:rgba(106,210,138,.85); }
        QLabel#orgSyncStatus[syncState="error"] { color:rgba(255,110,100,.90); }
        QLabel#orgHint { color:rgba(255,255,255,.35); font-size:9px; }
        """

    def load_pdfs(self, paths):
        candidates = [Path(path) for path in paths if str(path).lower().endswith(".pdf")]
        if not candidates:
            return
        self.load_pdf(candidates[0])

    def clear_pdf(self):
        self.current_path = None
        self._pages.clear()
        self._undo.clear()
        self._redo.clear()
        self._icon_cache.clear()
        self.pages.clear()
        self.file_label.setText("Nenhum PDF carregado")
        set_open_pdf_loaded(self.open_button, False)
        self.status.setText("ARRASTE UM PDF PARA COMEÇAR")
        self.sync_status.clear()
        self._work_generation = 0
        self._work_dir.cleanup()
        self._work_dir = tempfile.TemporaryDirectory(prefix="m87_org_")
        self._update_actions()

    def load_pdf(self, path):
        source = Path(path).expanduser().resolve()
        try:
            specs = page_specs(source)
        except Exception as error:
            QMessageBox.critical(self, "M87 • ORGANIZAR PÁGINAS", f"Não foi possível abrir o PDF:\n{error}")
            return
        self.current_path = source
        try:
            info = inspect_geometry(source)
            first_trim = info.pages[0].trim
            self.file_label.setText(format_pdf_file_summary(
                source.name,
                first_trim.width_mm,
                first_trim.height_mm,
                info.page_count,
            ))
        except GeometryError:
            self.file_label.setText(source.name)
        set_open_pdf_loaded(self.open_button, True)
        self._pages = specs
        self._icon_cache.clear()
        self._undo.clear()
        self._redo.clear()
        self._rebuild()
        self.set_sync_status(True, "ARQUIVO ORIGINAL SINCRONIZADO")
        self.pdfStateChanged.emit([str(source)])

    def _choose_pdf(self):
        path, _ = QFileDialog.getOpenFileName(self, "Abrir PDF", "", "PDF (*.pdf)")
        if path:
            self.load_pdf(path)

    def _thumbnails(self):
        missing = [spec for spec in dict.fromkeys(self._pages) if spec not in self._icon_cache]
        by_source = {}
        for spec in missing:
            by_source.setdefault(spec.source, []).append(spec)
        for source, specs in by_source.items():
            try:
                with fitz.open(source) as document:
                    for spec in specs:
                        page = document[spec.page_index]
                        pix = page.get_pixmap(matrix=fitz.Matrix(0.45, 0.45), alpha=False)
                        image = QImage(
                            pix.samples, pix.width, pix.height, pix.stride,
                            QImage.Format_RGB888,
                        ).copy()
                        pixmap = QPixmap.fromImage(image)
                        if spec.rotation:
                            from PySide6.QtGui import QTransform
                            pixmap = pixmap.transformed(
                                QTransform().rotate(spec.rotation),
                                Qt.SmoothTransformation,
                            )
                        self._icon_cache[spec] = QIcon(pixmap)
            except Exception:
                for spec in specs:
                    self._icon_cache[spec] = QIcon()
        return self._icon_cache

    def _rebuild(self, selected=None):
        selected = set(selected or [])
        self.pages.clear()
        icons = self._thumbnails()
        for index, spec in enumerate(self._pages):
            item = QListWidgetItem(icons[spec], f"PÁGINA {index + 1}")
            # O drag interno serializa os dados do item. Mantenha somente
            # tipos QVariant nativos; objetos Python impedem o drop no Qt.
            item.setData(Qt.UserRole, [
                str(spec.source), spec.page_index, spec.rotation,
            ])
            item.setFlags(
                item.flags()
                | Qt.ItemIsDragEnabled
                | Qt.ItemIsDropEnabled
            )
            item.setTextAlignment(Qt.AlignHCenter)
            self.pages.addItem(item)
            item.setSelected(index in selected)
        name = self.current_path.name if self.current_path else "—"
        self.status.setText(f"{name.upper()}  ·  {len(self._pages)} PÁGINAS")
        self._update_actions()

    def _snapshot(self):
        self._undo.append(list(self._pages))
        self._redo.clear()

    def _change_preview_page(self, offset):
        if not self._pages:
            return
        row = self.pages.currentRow()
        if row < 0:
            row = 0
        row = max(0, min(len(self._pages) - 1, row + offset))
        item = self.pages.item(row)
        self.pages.setCurrentItem(item)
        item.setSelected(True)
        self.pages.scrollToItem(item)
        self._update_actions()

    def _rotate_from_toolbar(self):
        if not self.pages.selectedItems() and self.pages.count():
            self.pages.setCurrentRow(max(0, self.pages.currentRow()))
            self.pages.currentItem().setSelected(True)
        self._rotate(90)

    def _set_thumbnail_zoom(self, zoom):
        self._thumbnail_zoom = min(1.75, max(.5, zoom))
        self.pages.setIconSize(QSize(
            round(126 * self._thumbnail_zoom),
            round(166 * self._thumbnail_zoom),
        ))
        self.pages.setGridSize(QSize(
            round(156 * self._thumbnail_zoom),
            round(205 * self._thumbnail_zoom),
        ))
        self.preview_toolbar.zoom_label.setText(
            f"{round(self._thumbnail_zoom * 100)}%"
        )

    def _selected_rows(self):
        return sorted(self.pages.row(item) for item in self.pages.selectedItems())

    def _order_changed(self, selected_rows, target):
        old = list(self._pages)
        reordered, insertion = reorder_pages(old, selected_rows, target)
        moving_count = len({int(row) for row in selected_rows if 0 <= int(row) < len(old)})
        if not moving_count:
            return
        if reordered == old:
            self._rebuild(selected_rows)
            return
        self._undo.append(old)
        self._redo.clear()
        self._pages = reordered
        self._rebuild(range(insertion, insertion + moving_count))
        self._queue_publish()

    def _rotate(self, degrees):
        rows = self._selected_rows()
        if not rows:
            return
        self._snapshot()
        for row in rows:
            self._pages[row] = rotated(self._pages[row], degrees)
        self._rebuild(rows)
        self._queue_publish()

    def _duplicate(self):
        rows = self._selected_rows()
        if not rows:
            return
        self._snapshot()
        selected = []
        offset = 0
        for row in rows:
            position = row + 1 + offset
            self._pages.insert(position, self._pages[row + offset])
            selected.append(position)
            offset += 1
        self._rebuild(selected)
        self._queue_publish()

    def _delete(self):
        rows = self._selected_rows()
        if not rows:
            return
        if len(rows) == len(self._pages):
            QMessageBox.warning(self, "M87 • ORGANIZAR PÁGINAS", "O PDF precisa manter pelo menos uma página.")
            return
        answer = QMessageBox.question(self, "M87 • ORGANIZAR PÁGINAS", f"Excluir {len(rows)} página(s) selecionada(s)?")
        if answer != QMessageBox.Yes:
            return
        self._snapshot()
        for row in reversed(rows):
            del self._pages[row]
        self._rebuild()
        self._queue_publish()

    def _insert_pdf(self):
        if not self.current_path:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Inserir páginas de PDF", "", "PDF (*.pdf)")
        if not path:
            return
        try:
            inserted = page_specs(path)
        except Exception as error:
            QMessageBox.critical(self, "M87 • ORGANIZAR PÁGINAS", str(error))
            return
        rows = self._selected_rows()
        position = rows[-1] + 1 if rows else len(self._pages)
        self._snapshot()
        self._pages[position:position] = inserted
        self._rebuild(range(position, position + len(inserted)))
        self._queue_publish()

    def _replace_pages(self):
        rows = self._selected_rows()
        if not rows:
            return
        path, _ = QFileDialog.getOpenFileName(self, "PDF com páginas substitutas", "", "PDF (*.pdf)")
        if not path:
            return
        replacements = page_specs(path)
        if len(replacements) < len(rows):
            QMessageBox.warning(self, "M87 • ORGANIZAR PÁGINAS", "O PDF substituto não possui páginas suficientes.")
            return
        self._snapshot()
        for row, spec in zip(rows, replacements):
            self._pages[row] = spec
        self._rebuild(rows)
        self._queue_publish()

    def _extract_pages(self):
        rows = self._selected_rows()
        if not rows or not self.current_path:
            return
        default = str(self.current_path.with_name(f"{self.current_path.stem}_extraido.pdf"))
        path, _ = QFileDialog.getSaveFileName(self, "Extrair páginas", save_path(default), "PDF (*.pdf)")
        if path:
            self._write([self._pages[row] for row in rows], path, "Páginas extraídas")

    def _split_pages(self):
        if not self.current_path:
            return
        dialog = QMessageBox(self)
        dialog.setWindowTitle("M87 • DIVIDIR PDF")
        dialog.setText("Quantidade máxima de páginas por arquivo:")
        spin = QSpinBox(dialog)
        spin.setRange(1, max(1, len(self._pages)))
        spin.setValue(1)
        dialog.layout().addWidget(spin, 1, 1)
        dialog.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
        if dialog.exec() != QMessageBox.Ok:
            return
        folder = QFileDialog.getExistingDirectory(self, "Pasta para os PDFs divididos", str(self.current_path.parent))
        if not folder:
            return
        try:
            outputs = split_pages(self.current_path, self._pages, folder, spin.value())
            show_button_success(self.split_button, restore_text="DIVIDIR")
            self.status.setText(f"✓ {len(outputs)} PDFs salvos")
        except Exception as error:
            QMessageBox.critical(self, "M87 • ORGANIZAR PÁGINAS", str(error))

    def _save_as(self):
        if not self.current_path:
            return
        default = str(self.current_path.with_name(f"{self.current_path.stem}_organizado.pdf"))
        path, _ = QFileDialog.getSaveFileName(self, "Salvar PDF organizado", save_path(default), "PDF (*.pdf)")
        if path:
            self._write(self._pages, path, "PDF organizado")

    def _restore_original(self):
        if self.current_path:
            self.load_pdf(self.current_path)

    def _print_current(self):
        if not self.current_path or not self._pages:
            return
        temporary = tempfile.TemporaryDirectory(prefix="m87_org_print_")
        output = Path(temporary.name) / f"{self.current_path.stem}_organizado.pdf"
        try:
            save_pages(self.current_path, self._pages, output)
        except Exception as error:
            temporary.cleanup()
            QMessageBox.critical(
                self, "M87 • ORGANIZAR PÁGINAS",
                f"Não foi possível preparar o PDF para impressão:\n{error}",
            )
            return
        spool_pdf(
            self, output, button=self.print_button, cleanup=temporary.cleanup,
        )

    def _write(self, specs, path, title):
        try:
            output = save_pages(self.current_path, specs, path)
            button = (
                self.extract_button
                if title == "Páginas extraídas"
                else self.save_button
            )
            show_button_success(button)
            self.status.setText(f"✓ {title} salvo: {Path(output).name}")
        except Exception as error:
            QMessageBox.critical(self, "M87 • ORGANIZAR PÁGINAS", f"Não foi possível salvar:\n{error}")

    def _undo_action(self):
        if not self._undo:
            return
        self._redo.append(list(self._pages))
        self._pages = self._undo.pop()
        self._rebuild()
        self._queue_publish()

    def _redo_action(self):
        if not self._redo:
            return
        self._undo.append(list(self._pages))
        self._pages = self._redo.pop()
        self._rebuild()
        self._queue_publish()

    def _queue_publish(self):
        if self.current_path and self._pages:
            self.set_sync_status(False)
            # A publicação é intencionalmente síncrona: ao terminar qualquer
            # ação, as outras abas já devem apontar para a mesma versão.
            self._publish_changes()

    def _publish_changes(self):
        if not self.current_path or not self._pages:
            return
        self._work_generation += 1
        output = Path(self._work_dir.name) / f"org_{self._work_generation:04d}.pdf"
        try:
            save_pages(self.current_path, self._pages, output)
        except Exception as error:
            self.set_sync_status(False, "ERRO DE SINCRONIZAÇÃO", error=True)
            QMessageBox.critical(
                self,
                "M87 • ORGANIZAR PÁGINAS",
                f"Não foi possível atualizar as outras ferramentas:\n{error}",
            )
            return
        self.workPdfChanged.emit({
            "path": str(output),
            "source": str(self.current_path),
        })

    def set_sync_status(self, synchronized, text=None, error=False):
        if error:
            state = "error"
            message = text or "ERRO DE SINCRONIZAÇÃO"
        elif synchronized:
            state = "ok"
            message = text or "SINCRONIZADO COM GEO E IMP"
        else:
            state = "pending"
            message = text or "SINCRONIZANDO…"
        self.sync_status.setProperty("syncState", state)
        self.sync_status.setText(message)
        self.sync_status.style().unpolish(self.sync_status)
        self.sync_status.style().polish(self.sync_status)

    def _select_all(self):
        self.pages.selectAll()

    def _select_kind(self, kind):
        self.pages.clearSelection()
        dimensions = {}
        if kind in {"portrait", "landscape"}:
            for source in {spec.source for spec in self._pages}:
                with fitz.open(source) as document:
                    dimensions[source] = [(page.rect.width, page.rect.height) for page in document]
        for row, spec in enumerate(self._pages):
            number = row + 1
            match = (kind == "even" and number % 2 == 0) or (kind == "odd" and number % 2 == 1)
            if kind in {"portrait", "landscape"}:
                width, height = dimensions[spec.source][spec.page_index]
                if spec.rotation % 180:
                    width, height = height, width
                match = (kind == "portrait" and height >= width) or (kind == "landscape" and width > height)
            self.pages.item(row).setSelected(match)

    def _select_range(self):
        try:
            rows = self._parse_range(self.range_edit.text(), len(self._pages))
        except ValueError as error:
            QMessageBox.warning(self, "M87 • ORGANIZAR PÁGINAS", str(error))
            return
        self.pages.clearSelection()
        for row in rows:
            self.pages.item(row).setSelected(True)

    @staticmethod
    def _parse_range(text, total):
        if not text.strip():
            raise ValueError("Informe as páginas. Exemplo: 1, 3-6")
        result = set()
        try:
            for part in text.replace(" ", "").split(","):
                if "-" in part:
                    start, end = (int(value) for value in part.split("-", 1))
                    if start > end:
                        raise ValueError
                    result.update(range(start, end + 1))
                else:
                    result.add(int(part))
        except (TypeError, ValueError):
            raise ValueError("Intervalo inválido. Use o formato 1, 3-6.") from None
        if not result or min(result) < 1 or max(result) > total:
            raise ValueError(f"As páginas devem estar entre 1 e {total}.")
        return sorted(number - 1 for number in result)

    def _update_actions(self):
        loaded = bool(self.current_path and self._pages)
        selected = bool(self.pages.selectedItems())
        for card in self._document_cards:
            set_document_control_enabled(card, loaded)
        for button in (
            self.insert_button, self.split_button, self.save_button,
            self.restore_button, self.print_button,
        ):
            button.setEnabled(loaded)
        for button in (
            self.replace_button, self.extract_button, self.left_button,
            self.right_button, self.duplicate_button, self.delete_button,
        ):
            button.setEnabled(loaded and selected)
        self.range_edit.setEnabled(loaded)
        self.undo_button.setEnabled(bool(self._undo))
        self.redo_button.setEnabled(bool(self._redo))
        self.preview_toolbar.set_document_enabled(loaded)
        row = self.pages.currentRow()
        if loaded and row < 0:
            row = 0
        self.preview_toolbar.page_label.setText(
            f"Página {row + 1} de {len(self._pages)}" if loaded else "Nenhum PDF"
        )
        self.preview_toolbar.previous_button.setEnabled(loaded and row > 0)
        self.preview_toolbar.next_button.setEnabled(
            loaded and row + 1 < len(self._pages)
        )
        self.preview_toolbar.rotation_undo_button.setEnabled(bool(self._undo))
