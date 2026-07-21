import json
import subprocess
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QCursor, QIcon, QKeyEvent
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

ROOT = Path(__file__).resolve().parent.parent
REFERENCE_FILE = ROOT / "reference.json"
COMMANDS_FILE = ROOT / "commands.json"
YELLOW = "#FFC400"
GREEN = "#A5FF73"


class ReferenceSearchEdit(QLineEdit):
    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_Escape:
            self.clear()
            return
        super().keyPressEvent(event)


class ReferenceDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.drag_position = QPoint()
        self.data = self._load_json(REFERENCE_FILE, {"product": {}, "sections": []})
        self.sections = self.data.get("sections", [])
        self.active_section_id = "inicio"
        self.sidebar_buttons = {}

        self._setup_window()
        self._build_ui()
        self._apply_style()
        self.show_section("inicio")

    @staticmethod
    def _load_json(path, fallback):
        try:
            with open(path, "r", encoding="utf-8") as file:
                return json.load(file)
        except Exception:
            return fallback

    def _setup_window(self):
        self.setWindowTitle("M87 TERMINAL · REFERENCE")
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setModal(False)
        self.resize(820, 600)
        self.setMinimumSize(700, 500)

        icon_path = ROOT / "assets" / "m87_icon.png"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self.terminal_box = QWidget()
        self.terminal_box.setObjectName("referenceTerminalBox")
        outer.addWidget(self.terminal_box)

        main = QVBoxLayout(self.terminal_box)
        main.setContentsMargins(16, 10, 16, 12)
        main.setSpacing(6)

        self._build_title_bar(main)
        self._build_header(main)
        self._build_search(main)
        self._build_body(main)

    def _build_title_bar(self, parent_layout):
        bar = QWidget()
        bar.setObjectName("referenceTitleBar")
        bar.setFixedHeight(22)

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        title = QLabel("M87 TERMINAL · REFERENCE")
        title.setObjectName("referenceWindowTitle")
        layout.addWidget(title)
        layout.addStretch()

        close_button = QLabel("×")
        close_button.setObjectName("referenceClose")
        close_button.setCursor(QCursor(Qt.PointingHandCursor))
        close_button.setToolTip("Fechar")
        close_button.mousePressEvent = lambda event: self.close()
        layout.addWidget(close_button)

        parent_layout.addWidget(bar)
        parent_layout.addWidget(self._divider())

    def _counts(self):
        commands = self._load_json(COMMANDS_FILE, [])
        visible = len(commands) if isinstance(commands, list) else 0
        special = 7
        pdf_actions = 4
        return visible, special, pdf_actions

    def _build_header(self, parent_layout):
        product = self.data.get("product", {})
        visible, special, pdf_actions = self._counts()

        name = QLabel(product.get("name", "M87 TERMINAL"))
        name.setObjectName("referenceProduct")

        version = QLabel(
            f'{product.get("version", "v1.0.0")} · '
            f'Criado em {product.get("created", "03 de julho de 2026")}'
        )
        version.setObjectName("referenceMeta")

        summary = QLabel(
            f"{visible} comandos  ·  {special} recursos especiais  ·  "
            f"{pdf_actions} ações PDF"
        )
        summary.setObjectName("referenceCounts")

        parent_layout.addWidget(name)
        parent_layout.addWidget(version)
        parent_layout.addWidget(summary)

    def _build_search(self, parent_layout):
        search_row = QWidget()
        row_layout = QHBoxLayout(search_row)
        row_layout.setContentsMargins(0, 2, 0, 0)
        row_layout.setSpacing(0)

        prompt = QLabel("buscar ~ % ")
        prompt.setObjectName("referencePrompt")

        self.search = ReferenceSearchEdit()
        self.search.setObjectName("referenceSearch")
        self.search.setPlaceholderText("comando, função ou palavra-chave")
        self.search.textChanged.connect(self._on_search)

        row_layout.addWidget(prompt)
        row_layout.addWidget(self.search, 1)
        parent_layout.addWidget(search_row)
        parent_layout.addWidget(self._divider())

    def _build_body(self, parent_layout):
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(12)

        sidebar = QWidget()
        sidebar.setObjectName("referenceSidebar")
        sidebar.setFixedWidth(158)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 2, 10, 0)
        sidebar_layout.setSpacing(1)

        for section in self.sections:
            section_id = section.get("id", "")
            button = QPushButton(f'  {section.get("title", section_id).upper()}')
            button.setObjectName("referenceNav")
            button.setCursor(QCursor(Qt.PointingHandCursor))
            button.setCheckable(True)
            button.clicked.connect(
                lambda checked=False, sid=section_id: self.show_section(sid)
            )
            self.sidebar_buttons[section_id] = button
            sidebar_layout.addWidget(button)

        sidebar_layout.addStretch()

        signature = QLabel("Built with Python + Qt\nby Mariane Jacob")
        signature.setObjectName("referenceSignature")
        sidebar_layout.addWidget(signature)

        separator = QFrame()
        separator.setObjectName("referenceVerticalDivider")
        separator.setFrameShape(QFrame.VLine)

        self.scroll = QScrollArea()
        self.scroll.setObjectName("referenceScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.content = QWidget()
        self.content.setObjectName("referenceContent")
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(4, 0, 8, 8)
        self.content_layout.setSpacing(4)
        self.content_layout.setAlignment(Qt.AlignTop)
        self.scroll.setWidget(self.content)

        body.addWidget(sidebar)
        body.addWidget(separator)
        body.addWidget(self.scroll, 1)
        parent_layout.addLayout(body, 1)

    def _divider(self):
        label = QLabel("────────────────────────────────────────────────────────────────────────")
        label.setObjectName("referenceDivider")
        label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        return label

    def _clear_content(self):
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def _set_active_nav(self, section_id):
        for sid, button in self.sidebar_buttons.items():
            active = sid == section_id
            button.setChecked(active)
            title = next(
                (s.get("title", sid) for s in self.sections if s.get("id") == sid),
                sid,
            )
            button.setText(f"> {title.upper()}" if active else f"  {title.upper()}")

    def show_section(self, section_id):
        self.active_section_id = section_id
        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)
        self._set_active_nav(section_id)

        section = next((s for s in self.sections if s.get("id") == section_id), None)
        if section:
            self._render_section(section)

    def _render_section(self, section, items=None, search_title=None):
        self._clear_content()

        heading = QLabel(search_title or section.get("title", "").upper())
        heading.setObjectName("referenceHeading")
        self.content_layout.addWidget(heading)

        intro = section.get("intro", "")
        if intro:
            intro_label = QLabel(intro)
            intro_label.setObjectName("referenceIntro")
            intro_label.setWordWrap(True)
            self.content_layout.addWidget(intro_label)

        if section.get("dynamic") == "git" and items is None:
            self._render_changelog()
            self.content_layout.addStretch()
            return

        if items is not None:
            self._render_items(items)
        elif section.get("groups"):
            for group in section.get("groups", []):
                group_label = QLabel(group.get("title", ""))
                group_label.setObjectName("referenceGroup")
                self.content_layout.addWidget(group_label)
                self._render_items(group.get("items", []))
        else:
            self._render_items(section.get("items", []))

        self.content_layout.addStretch()
        self.scroll.verticalScrollBar().setValue(0)

    def _render_items(self, items):
        if not items:
            empty = QLabel("Nenhum resultado encontrado.")
            empty.setObjectName("referenceEmpty")
            self.content_layout.addWidget(empty)
            return
        for item in items:
            self.content_layout.addWidget(self._item_widget(item))

    def _item_widget(self, item):
        widget = QWidget()
        widget.setObjectName("referenceItem")

        layout = QGridLayout(widget)
        layout.setContentsMargins(0, 4, 0, 6)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(1)
        layout.setColumnMinimumWidth(0, 112)
        layout.setColumnStretch(1, 1)

        code = QLabel(item.get("code", ""))
        code.setObjectName("referenceCode")
        code.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        code.setTextInteractionFlags(Qt.TextSelectableByMouse)

        title = QLabel(item.get("title", ""))
        title.setObjectName("referenceItemTitle")
        title.setWordWrap(True)

        description = QLabel(item.get("description", ""))
        description.setObjectName("referenceDescription")
        description.setWordWrap(True)
        description.setTextInteractionFlags(Qt.TextSelectableByMouse)

        layout.addWidget(code, 0, 0, 2, 1)
        layout.addWidget(title, 0, 1)
        layout.addWidget(description, 1, 1)
        return widget

    def _all_items(self):
        for section in self.sections:
            for item in section.get("items", []):
                yield section, item
            for group in section.get("groups", []):
                for item in group.get("items", []):
                    yield section, item

    def _on_search(self, text):
        query = text.strip().casefold()
        if not query:
            section = next(
                (s for s in self.sections if s.get("id") == self.active_section_id),
                self.sections[0] if self.sections else {},
            )
            self._render_section(section)
            return

        results = []
        for section, item in self._all_items():
            haystack = " ".join(
                [
                    item.get("code", ""),
                    item.get("title", ""),
                    item.get("description", ""),
                    " ".join(item.get("keywords", [])),
                    section.get("title", ""),
                ]
            ).casefold()
            if query in haystack:
                enriched = dict(item)
                enriched["title"] = (
                    f'{item.get("title", "")} · {section.get("title", "")}'
                )
                results.append(enriched)

        self._set_active_nav("")
        self._render_section(
            {"title": "BUSCA"},
            items=results,
            search_title=f'RESULTADOS PARA "{text.strip()}"',
        )

    def _git_entries(self):
        try:
            result = subprocess.run(
                [
                    "git", "-C", str(ROOT), "log",
                    "--date=format:%d/%m/%Y",
                    "--pretty=format:%ad%x1f%s%x1e",
                    "-n", "80",
                ],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
            if result.returncode != 0 or not result.stdout.strip():
                return []

            entries = []
            for record in result.stdout.split("\x1e"):
                record = record.strip()
                if not record or "\x1f" not in record:
                    continue
                date_text, subject = record.split("\x1f", 1)
                entries.append((date_text.strip(), subject.strip()))
            return entries
        except Exception:
            return []

    def _render_changelog(self):
        entries = self._git_entries()
        if not entries:
            message = QLabel(
                "O histórico do Git não está disponível nesta cópia do projeto.\n"
                "No projeto conectado ao GitHub, os commits aparecem aqui automaticamente."
            )
            message.setObjectName("referenceDescription")
            message.setWordWrap(True)
            self.content_layout.addWidget(message)
            return

        current_date = None
        for date_text, subject in entries:
            if date_text != current_date:
                current_date = date_text
                try:
                    parsed = datetime.strptime(date_text, "%d/%m/%Y")
                    date_label_text = parsed.strftime("%d %b %Y").upper()
                except ValueError:
                    date_label_text = date_text

                date_label = QLabel(date_label_text)
                date_label.setObjectName("referenceChangeDate")
                self.content_layout.addWidget(date_label)

            commit = QLabel(f"▸ {subject}")
            commit.setObjectName("referenceCommit")
            commit.setWordWrap(True)
            commit.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self.content_layout.addWidget(commit)

    def _apply_style(self):
        self.setStyleSheet(
            f"""
            QWidget {{
                font-family: "JetBrains Mono";
                color: {YELLOW};
                font-size: 11px;
            }}
            QWidget#referenceTerminalBox {{
                background-color: rgba(0, 0, 0, 222);
                border: 1px solid rgba(255, 196, 0, 0.20);
                border-radius: 13px;
            }}
            QWidget#referenceTitleBar {{ background: transparent; }}
            QLabel#referenceWindowTitle {{
                color: {YELLOW}; font-size: 9px; font-weight: 400; letter-spacing: 1px;
            }}
            QLabel#referenceClose {{ color: {YELLOW}; font-size: 16px; padding: 0 4px; }}
            QLabel#referenceClose:hover {{ color: {GREEN}; }}
            QLabel#referenceDivider {{
                color: rgba(255, 196, 0, 0.58); font-size: 6px; max-height: 8px;
            }}
            QLabel#referenceProduct {{
                color: {YELLOW}; font-size: 16px; font-weight: 600;
                letter-spacing: 1px; padding-top: 2px;
            }}
            QLabel#referenceMeta {{ color: rgba(255, 196, 0, 0.76); font-size: 10px; }}
            QLabel#referenceCounts {{
                color: rgba(255, 255, 255, 0.76); font-size: 10px; padding: 1px 0 4px 0;
            }}
            QLabel#referencePrompt {{ color: {YELLOW}; font-size: 11px; }}
            QLineEdit#referenceSearch {{
                background: transparent; border: none; color: rgba(255,255,255,0.94);
                selection-background-color: rgba(255,196,0,0.30); padding: 0; min-height: 20px;
            }}
            QLineEdit#referenceSearch::placeholder {{ color: rgba(255,255,255,0.34); }}
            QWidget#referenceSidebar {{ background: transparent; }}
            QPushButton#referenceNav {{
                background: transparent; border: none; color: rgba(255, 196, 0, 0.56);
                text-align: left; padding: 5px 2px; font-size: 10px; letter-spacing: 1px;
            }}
            QPushButton#referenceNav:hover {{ color: rgba(255, 239, 150, 0.96); }}
            QPushButton#referenceNav:checked {{ color: {YELLOW}; }}
            QLabel#referenceSignature {{
                color: rgba(255,255,255,0.38); font-size: 9px; padding: 8px 2px 2px 2px;
            }}
            QFrame#referenceVerticalDivider {{
                color: rgba(255,196,0,0.26); background: rgba(255,196,0,0.26); max-width: 1px;
            }}
            QScrollArea#referenceScroll, QWidget#referenceContent {{
                background: transparent; border: none;
            }}
            QScrollBar:vertical {{ background: transparent; width: 7px; margin: 0; }}
            QScrollBar::handle:vertical {{
                background: rgba(255,196,0,0.30); min-height: 28px; border-radius: 3px;
            }}
            QScrollBar::handle:vertical:hover {{ background: rgba(255,196,0,0.52); }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            QLabel#referenceHeading {{
                color: {YELLOW}; font-size: 13px; font-weight: 600;
                letter-spacing: 1px; padding: 2px 0 4px 0;
            }}
            QLabel#referenceIntro {{
                color: rgba(255,255,255,0.62); font-size: 10px; padding: 0 0 5px 0;
            }}
            QLabel#referenceGroup {{
                color: rgba(255,196,0,0.72); font-size: 9px; font-weight: 600;
                letter-spacing: 1px; padding: 8px 0 2px 0;
            }}
            QWidget#referenceItem {{
                background: transparent; border-bottom: 1px solid rgba(255,196,0,0.10);
            }}
            QLabel#referenceCode {{ color: {YELLOW}; font-size: 10px; font-weight: 600; }}
            QLabel#referenceItemTitle {{ color: rgba(255,239,150,0.88); font-size: 10px; }}
            QLabel#referenceDescription {{
                color: rgba(255,255,255,0.67); font-size: 10px; padding-top: 1px;
            }}
            QLabel#referenceEmpty {{
                color: rgba(255,255,255,0.45); font-size: 10px; padding-top: 8px;
            }}
            QLabel#referenceChangeDate {{
                color: {YELLOW}; font-size: 10px; font-weight: 600; padding: 9px 0 2px 0;
            }}
            QLabel#referenceCommit {{
                color: rgba(255,255,255,0.68); font-size: 10px; padding: 2px 0 3px 0;
            }}
            """
        )

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and event.position().y() <= 35:
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton and not self.drag_position.isNull():
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self.drag_position = QPoint()
        super().mouseReleaseEvent(event)
