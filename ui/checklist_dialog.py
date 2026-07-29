from __future__ import annotations

from PySide6.QtCore import QEvent, QPoint, QSettings, Qt, QTimer
from PySide6.QtGui import QCursor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ui.widgets import DarkMetallicTitleBar


CHECKLIST_SECTIONS = (
    (
        "FOLHA DE OBRA",
        (
            "Medida confere com o pedido",
            "Material conferido",
            "Quantidade conferida",
            "Modelos/variações conferidos",
            "Acabamentos conferidos",
            "Aprovação do cliente confirmada",
        ),
    ),
    (
        "ESTRUTURA",
        (
            "TrimBox na medida",
            "Sangria suficiente",
            "Margem interna segura",
            "Marcas de corte corretas",
            "Frente e verso conferidos",
            "Orientação frente/verso correta",
        ),
    ),
    (
        "CONTEÚDO",
        (
            "Textos revisados/aprovados",
            "Imagens com resolução adequada",
            "Logos/vetores/imagens nítidos",
            "Transparências e efeitos conferidos",
            "Páginas e ordem conferidas",
        ),
    ),
    (
        "CORES",
        (
            "Arquivo em CMYK",
            "Pretos conferidos",
            "Pantones conferidos",
            "Overprint conferido",
            "Brancos sem overprint",
        ),
    ),
    (
        "CORTE E ACABAMENTO",
        (
            "Medida correta do cortante",
            "Conferir/Pedir cortante",
            "Conferir montagem",
            "Cortante em overprint",
            "Ver acabamentos da FO",
        ),
    ),
    (
        "ARQUIVO FINAL",
        (
            "PDF exportado com sangria",
            "PDF e arquivo editável salvos",
            "Nome e versão identificados",
            "Prova/modelo conferido",
        ),
    ),
)

CHECKLIST_STATE_KEY = "checklist/v3/items"

SECTION_ACCENTS = (
    "gold",
    "violet",
    "blue",
    "cyan",
    "teal",
    "green",
)

SECTION_SHORT_TITLES = (
    "FOLHA DE OBRA",
    "ESTRUTURA",
    "CONTEÚDO",
    "CORES",
    "CORTE E ACABAMENTO",
    "ARQUIVO FINAL",
)


class ChecklistSection(QWidget):
    def __init__(
        self,
        number,
        title,
        items,
        accent,
        on_change,
        on_toggle,
        event_filter,
        parent=None,
    ):
        super().__init__(parent)
        self._on_change = on_change
        self._on_toggle = on_toggle
        self._expanded = False
        self.checkboxes = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.header = QPushButton()
        self.header.setObjectName("checklistSectionHeader")
        self.header.setProperty("accent", accent)
        self.header.setCursor(QCursor(Qt.PointingHandCursor))
        self.header.clicked.connect(self.toggle)
        root.addWidget(self.header)

        self.items_widget = QWidget()
        self.items_widget.setObjectName("checklistItems")
        self.items_widget.setProperty("accent", accent)
        items_layout = QVBoxLayout(self.items_widget)
        items_layout.setContentsMargins(13, 3, 4, 9)
        items_layout.setSpacing(1)

        for text in items:
            checkbox = QCheckBox(text)
            checkbox.setObjectName("checklistItem")
            checkbox.setProperty("accent", accent)
            checkbox.setProperty("item_key", f"{number}/{text}")
            checkbox.setToolTip(text)
            checkbox.setCursor(QCursor(Qt.PointingHandCursor))
            checkbox.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            checkbox.toggled.connect(self._item_changed)
            checkbox.installEventFilter(event_filter)
            self.checkboxes.append(checkbox)
            items_layout.addWidget(checkbox)

        root.addWidget(self.items_widget)
        self.number = number
        self.title = title
        self.update_header()

    @property
    def completed(self):
        return sum(checkbox.isChecked() for checkbox in self.checkboxes)

    def update_header(self):
        arrow = "▾" if self._expanded else "▸"
        self.header.setText(
            f"{arrow}  {self.number:02d}  {self.title}"
            f"     {self.completed}/{len(self.checkboxes)}"
        )

    def toggle(self):
        self._on_toggle(self)

    def set_expanded(self, expanded):
        self._expanded = expanded
        self.items_widget.setVisible(expanded)
        self.update_header()

    def _item_changed(self):
        self.update_header()
        self._on_change()


class ChecklistDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings = QSettings("M87Tools", "M87Terminal")
        self.drag_position = QPoint()
        self.sections = []
        self._restoring = False
        self._setup_window()
        self._build_ui()
        self._restore_state()
        self._update_progress()
        QTimer.singleShot(0, self._focus_first_active_item)

    def _setup_window(self):
        self.setWindowTitle("M87 CHECKLIST")
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMinimumHeight(560)
        self.setFixedWidth(224)
        self.resize(224, 760)

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self.box = QWidget()
        self.box.setObjectName("checklistBox")
        outer.addWidget(self.box)

        root = QVBoxLayout(self.box)
        root.setContentsMargins(0, 0, 0, 10)
        root.setSpacing(0)

        bar = DarkMetallicTitleBar(height=34, radius=12)
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(14, 0, 10, 0)
        bar_layout.setSpacing(8)

        title = QLabel("M87  CHECKLIST")
        title.setObjectName("checklistWindowTitle")
        bar_layout.addWidget(title)
        bar_layout.addStretch()

        self.pin_button = QPushButton("◇")
        self.pin_button.setObjectName("checklistWindowButton")
        self.pin_button.setToolTip("Manter visível")
        self.pin_button.setCheckable(True)
        self.pin_button.clicked.connect(self._toggle_always_on_top)
        bar_layout.addWidget(self.pin_button)

        minimize = QPushButton("—")
        minimize.setObjectName("checklistWindowButton")
        minimize.setToolTip("Minimizar")
        minimize.clicked.connect(self.showMinimized)
        bar_layout.addWidget(minimize)

        close = QPushButton("×")
        close.setObjectName("checklistWindowButton")
        close.setToolTip("Fechar")
        close.clicked.connect(self.close)
        bar_layout.addWidget(close)

        bar.mousePressEvent = self._title_press
        bar.mouseMoveEvent = self._title_move
        root.addWidget(bar)

        summary = QWidget()
        summary.setObjectName("checklistSummary")
        summary_layout = QVBoxLayout(summary)
        summary_layout.setContentsMargins(11, 12, 11, 10)
        summary_layout.setSpacing(5)

        heading_row = QHBoxLayout()
        heading_row.setSpacing(6)
        heading = QLabel("LIBERAÇÃO")
        heading.setObjectName("checklistHeading")
        self.counter = QLabel()
        self.counter.setObjectName("checklistCounter")
        heading_row.addWidget(heading)
        heading_row.addStretch()
        heading_row.addWidget(self.counter)
        summary_layout.addLayout(heading_row)

        self.progress = QProgressBar()
        self.progress.setObjectName("checklistProgress")
        self.progress.setRange(0, self.total_items)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(7)
        summary_layout.addWidget(self.progress)

        self.progress_message = QLabel()
        self.progress_message.setObjectName("checklistProgressMessage")
        summary_layout.addWidget(self.progress_message)
        root.addWidget(summary)

        divider = QFrame()
        divider.setObjectName("checklistDivider")
        divider.setFrameShape(QFrame.HLine)
        root.addWidget(divider)

        scroll = QScrollArea()
        scroll.setObjectName("checklistScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        content = QWidget()
        content.setObjectName("checklistContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(7, 7, 7, 6)
        content_layout.setSpacing(1)

        for number, ((_, items), accent, short_title) in enumerate(
            zip(CHECKLIST_SECTIONS, SECTION_ACCENTS, SECTION_SHORT_TITLES),
            start=1,
        ):
            section = ChecklistSection(
                number,
                short_title,
                items,
                accent,
                self._on_item_changed,
                self._toggle_section,
                self,
                content,
            )
            self.sections.append(section)
            content_layout.addWidget(section)
        content_layout.addStretch()

        scroll.setWidget(content)
        root.addWidget(scroll, 1)

        footer = QHBoxLayout()
        footer.setContentsMargins(10, 8, 10, 0)
        footer.setSpacing(8)

        clear_button = QPushButton("↺  NOVA CONFERÊNCIA")
        clear_button.setObjectName("checklistClear")
        clear_button.clicked.connect(self._clear)
        footer.addWidget(clear_button)
        root.addLayout(footer)

        QShortcut(
            QKeySequence(Qt.Key_Escape),
            self,
            activated=self._clear_and_close,
        )
        self.setStyleSheet(self._style())

    @property
    def total_items(self):
        return sum(len(items) for _, items in CHECKLIST_SECTIONS)

    @property
    def checked_items(self):
        return sum(section.completed for section in self.sections)

    def _on_item_changed(self):
        if self._restoring:
            return
        self._save_checks()
        self._update_progress()
        self._open_first_incomplete_section()
        QTimer.singleShot(0, self._ensure_item_focus)

    def _update_progress(self):
        checked = self.checked_items
        percent = round((checked / self.total_items) * 100)
        self.progress.setValue(checked)
        self.counter.setText(f"{checked}/{self.total_items}  ·  {percent}%")

        if checked == self.total_items:
            message = "✓ ARQUIVO LIBERADO PARA IMPRESSÃO"
            state = "complete"
        elif percent >= 75:
            message = "Revisão final. Falta pouco."
            state = "active"
        elif percent >= 50:
            message = "Metade do caminho."
            state = "active"
        elif percent >= 25:
            message = "Estrutura encaminhada."
            state = "active"
        else:
            message = "Marque cada ponto durante a conferência."
            state = "idle"

        self.progress_message.setText(message)
        self.progress.setProperty("state", state)
        self.progress_message.setProperty("state", state)
        self.progress.style().unpolish(self.progress)
        self.progress.style().polish(self.progress)
        self.progress_message.style().unpolish(self.progress_message)
        self.progress_message.style().polish(self.progress_message)

    def _toggle_section(self, selected):
        should_open = not selected._expanded
        for section in self.sections:
            section.set_expanded(section is selected and should_open)

    def _open_first_incomplete_section(self):
        active = next(
            (
                section
                for section in self.sections
                if section.completed < len(section.checkboxes)
            ),
            None,
        )
        for section in self.sections:
            section.set_expanded(section is active)

    def _visible_checkboxes(self):
        return [
            checkbox
            for section in self.sections
            if section._expanded
            for checkbox in section.checkboxes
        ]

    def _focus_first_active_item(self):
        checkboxes = self._visible_checkboxes()
        if not checkboxes:
            return
        target = next(
            (checkbox for checkbox in checkboxes if not checkbox.isChecked()),
            checkboxes[0],
        )
        target.setFocus(Qt.OtherFocusReason)

    def _ensure_item_focus(self):
        focused = self.focusWidget()
        if focused in self._visible_checkboxes():
            return
        self._focus_first_active_item()

    def eventFilter(self, watched, event):
        if event.type() == QEvent.KeyPress and isinstance(watched, QCheckBox):
            key = event.key()
            if key in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
                watched.toggle()
                event.accept()
                return True

            if key in (Qt.Key_Up, Qt.Key_Down):
                checkboxes = self._visible_checkboxes()
                if watched not in checkboxes:
                    self._focus_first_active_item()
                    return True
                offset = -1 if key == Qt.Key_Up else 1
                index = checkboxes.index(watched) + offset
                if 0 <= index < len(checkboxes):
                    checkboxes[index].setFocus(Qt.OtherFocusReason)
                else:
                    self._focus_adjacent_section(watched, offset)
                event.accept()
                return True

            if key in (Qt.Key_Left, Qt.Key_Right):
                offset = -1 if key == Qt.Key_Left else 1
                self._focus_adjacent_section(watched, offset)
                event.accept()
                return True

        return super().eventFilter(watched, event)

    def _focus_adjacent_section(self, watched, offset):
        current_index = next(
            (
                index
                for index, section in enumerate(self.sections)
                if watched in section.checkboxes
            ),
            None,
        )
        if current_index is None:
            return

        target_index = current_index + offset
        if not 0 <= target_index < len(self.sections):
            return

        target_section = self.sections[target_index]
        for section in self.sections:
            section.set_expanded(section is target_section)

        target = (
            target_section.checkboxes[-1]
            if offset < 0
            else target_section.checkboxes[0]
        )
        target.setFocus(Qt.OtherFocusReason)

    def _save_checks(self):
        for section in self.sections:
            for checkbox in section.checkboxes:
                key = checkbox.property("item_key")
                self.settings.setValue(
                    f"{CHECKLIST_STATE_KEY}/{key}",
                    checkbox.isChecked(),
                )

    def _restore_state(self):
        self._restoring = True
        for section in self.sections:
            for checkbox in section.checkboxes:
                key = checkbox.property("item_key")
                value = self.settings.value(
                    f"{CHECKLIST_STATE_KEY}/{key}",
                    False,
                    type=bool,
                )
                checkbox.setChecked(value)
            section.update_header()
        self._restoring = False
        self._open_first_incomplete_section()

        geometry = self.settings.value("checklist/geometry")
        if geometry:
            self.restoreGeometry(geometry)

        pinned = self.settings.value("checklist/always_on_top", False, type=bool)
        self.pin_button.setChecked(pinned)
        self._apply_pin_style(pinned)
        if pinned:
            self.setWindowFlag(Qt.WindowStaysOnTopHint, True)

    def _clear(self):
        self._restoring = True
        for section in self.sections:
            for checkbox in section.checkboxes:
                checkbox.setChecked(False)
            section.set_expanded(section.number == 1)
        self._restoring = False
        self._save_checks()
        self._update_progress()
        self._focus_first_active_item()

    def _clear_and_close(self):
        self._clear()
        self.close()

    def _toggle_always_on_top(self, pinned):
        self.settings.setValue("checklist/always_on_top", pinned)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, pinned)
        self._apply_pin_style(pinned)
        self.show()
        self.raise_()
        self.activateWindow()

    def _apply_pin_style(self, pinned):
        self.pin_button.setText("◆" if pinned else "◇")
        self.pin_button.setToolTip(
            "Desativar manter visível" if pinned else "Manter visível"
        )

    def _title_press(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_position = (
                event.globalPosition().toPoint()
                - self.frameGeometry().topLeft()
            )
            event.accept()

    def _title_move(self, event):
        if event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()

    def closeEvent(self, event):
        self.settings.setValue("checklist/geometry", self.saveGeometry())
        self._save_checks()
        super().closeEvent(event)

    @staticmethod
    def _style():
        return """
            QWidget {
                font-family: "JetBrains Mono";
                color: rgba(220, 220, 220, 0.92);
                font-size: 11px;
            }
            QWidget#checklistBox {
                background-color: rgba(8, 9, 12, 242);
                border: 1px solid rgba(255, 255, 255, 42);
                border-radius: 13px;
            }
            QLabel#checklistWindowTitle {
                color: rgba(205, 205, 205, 0.96);
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 1px;
                background: transparent;
            }
            QPushButton#checklistWindowButton {
                color: rgba(190, 190, 190, 0.9);
                background: transparent;
                border: none;
                font-size: 13px;
                font-weight: 600;
                min-width: 16px;
                max-width: 16px;
                padding: 0;
            }
            QPushButton#checklistWindowButton:hover { color: #FFE066; }
            QWidget#checklistSummary { background: transparent; }
            QLabel#checklistHeading {
                color: rgba(255, 255, 255, 0.76);
                font-size: 9px;
                font-weight: 700;
                letter-spacing: 1px;
            }
            QLabel#checklistCounter {
                color: #FFC400;
                font-size: 10px;
                font-weight: 700;
            }
            QProgressBar#checklistProgress {
                background: rgba(255, 255, 255, 0.10);
                border: none;
                border-radius: 3px;
            }
            QProgressBar#checklistProgress::chunk {
                background: #D59D00;
                border-radius: 3px;
            }
            QProgressBar#checklistProgress[state="complete"]::chunk {
                background: #36D98B;
            }
            QLabel#checklistProgressMessage {
                color: rgba(180, 180, 180, 0.70);
                font-size: 9px;
            }
            QLabel#checklistProgressMessage[state="complete"] {
                color: #51E6A0;
                font-weight: 700;
            }
            QFrame#checklistDivider {
                color: rgba(255, 255, 255, 0.13);
                max-height: 1px;
                border: none;
                background: rgba(255, 255, 255, 0.13);
            }
            QScrollArea#checklistScroll {
                background: transparent;
                border: none;
            }
            QScrollArea#checklistScroll > QWidget > QWidget {
                background: transparent;
            }
            QWidget#checklistContent,
            QWidget#checklistItems { background: transparent; }
            QPushButton#checklistSectionHeader {
                color: rgba(255, 255, 255, 0.64);
                background: transparent;
                border: none;
                border-radius: 5px;
                text-align: left;
                font-size: 9px;
                font-weight: 700;
                letter-spacing: 0.5px;
                padding: 7px 4px 6px 4px;
            }
            QPushButton#checklistSectionHeader:hover {
                background: rgba(255, 196, 0, 0.05);
            }
            QPushButton#checklistSectionHeader[accent="gold"] {
                color: #D7A62C;
            }
            QPushButton#checklistSectionHeader[accent="violet"] {
                color: #A888DE;
            }
            QPushButton#checklistSectionHeader[accent="blue"] {
                color: #7F9DE8;
            }
            QPushButton#checklistSectionHeader[accent="cyan"] {
                color: #64BCCC;
            }
            QPushButton#checklistSectionHeader[accent="teal"] {
                color: #5FB9AA;
            }
            QPushButton#checklistSectionHeader[accent="green"] {
                color: #73C991;
            }
            QWidget#checklistItems[accent="gold"] {
                border-left: 2px solid rgba(215, 166, 44, 0.58);
            }
            QWidget#checklistItems[accent="violet"] {
                border-left: 2px solid rgba(168, 136, 222, 0.58);
            }
            QWidget#checklistItems[accent="blue"] {
                border-left: 2px solid rgba(127, 157, 232, 0.58);
            }
            QWidget#checklistItems[accent="cyan"] {
                border-left: 2px solid rgba(100, 188, 204, 0.58);
            }
            QWidget#checklistItems[accent="teal"] {
                border-left: 2px solid rgba(95, 185, 170, 0.58);
            }
            QWidget#checklistItems[accent="green"] {
                border-left: 2px solid rgba(115, 201, 145, 0.58);
            }
            QCheckBox#checklistItem {
                color: rgba(214, 214, 214, 0.86);
                font-size: 10px;
                spacing: 6px;
                padding: 4px 2px;
            }
            QCheckBox#checklistItem:hover { color: rgba(255, 255, 255, 0.98); }
            QCheckBox#checklistItem:focus {
                color: rgba(255, 255, 255, 0.98);
                border-radius: 4px;
            }
            QCheckBox#checklistItem[accent="gold"]:focus {
                background: rgba(215, 166, 44, 0.12);
            }
            QCheckBox#checklistItem[accent="violet"]:focus {
                background: rgba(168, 136, 222, 0.12);
            }
            QCheckBox#checklistItem[accent="blue"]:focus {
                background: rgba(127, 157, 232, 0.12);
            }
            QCheckBox#checklistItem[accent="cyan"]:focus {
                background: rgba(100, 188, 204, 0.12);
            }
            QCheckBox#checklistItem[accent="teal"]:focus {
                background: rgba(95, 185, 170, 0.12);
            }
            QCheckBox#checklistItem[accent="green"]:focus {
                background: rgba(115, 201, 145, 0.12);
            }
            QCheckBox#checklistItem:checked {
                color: rgba(180, 180, 180, 0.55);
            }
            QCheckBox#checklistItem::indicator {
                width: 15px;
                height: 15px;
                border: 1px solid rgba(255, 255, 255, 0.26);
                border-radius: 4px;
                background: rgba(255, 255, 255, 0.025);
            }
            QCheckBox#checklistItem::indicator:hover {
                border-color: rgba(255, 196, 0, 0.75);
            }
            QCheckBox#checklistItem::indicator:checked {
                image: none;
            }
            QCheckBox#checklistItem[accent="gold"]::indicator:checked {
                background: #D7A62C;
                border-color: #F0C75A;
            }
            QCheckBox#checklistItem[accent="violet"]::indicator:checked {
                background: #936FD0;
                border-color: #B89AE8;
            }
            QCheckBox#checklistItem[accent="blue"]::indicator:checked {
                background: #6787D9;
                border-color: #94ADEB;
            }
            QCheckBox#checklistItem[accent="cyan"]::indicator:checked {
                background: #48A9BC;
                border-color: #77C7D5;
            }
            QCheckBox#checklistItem[accent="teal"]::indicator:checked {
                background: #409F91;
                border-color: #72C5B7;
            }
            QCheckBox#checklistItem[accent="green"]::indicator:checked {
                background: #58AE76;
                border-color: #83D39E;
            }
            QPushButton#checklistClear {
                color: rgba(255, 196, 0, 0.82);
                background: rgba(255, 196, 0, 0.06);
                border: 1px solid rgba(255, 196, 0, 0.25);
                border-radius: 6px;
                padding: 7px 10px;
                font-size: 9px;
                font-weight: 700;
                letter-spacing: 0.5px;
            }
            QPushButton#checklistClear:hover {
                color: #FFE066;
                background: rgba(255, 196, 0, 0.12);
                border-color: rgba(255, 196, 0, 0.55);
            }
            QScrollBar:vertical {
                background: transparent;
                width: 7px;
                margin: 2px 0;
            }
            QScrollBar::handle:vertical {
                background: rgba(255, 255, 255, 0.16);
                border-radius: 3px;
                min-height: 28px;
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0;
            }
        """
