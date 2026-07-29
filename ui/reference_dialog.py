import json
import subprocess
import re
import unicodedata
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QPoint, QSettings, QTimer
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
    QSizeGrip,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ui.widgets import DarkMetallicTitleBar

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
        self.settings = QSettings("M87Tools", "M87Terminal")
        self._geometry_save_timer = QTimer(self)
        self._geometry_save_timer.setSingleShot(True)
        self._geometry_save_timer.timeout.connect(self._save_geometry)

        self._setup_window()
        self._build_ui()
        self._apply_style()
        self._restore_geometry()
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
        main.setContentsMargins(0, 0, 0, 8)
        main.setSpacing(4)

        self._build_title_bar(main)

        self.content_container = QWidget()
        self.content_container.setObjectName("referenceContentContainer")
        content = QVBoxLayout(self.content_container)
        content.setContentsMargins(16, 5, 16, 4)
        content.setSpacing(5)
        main.addWidget(self.content_container, 1)

        self._build_header(content)
        self._build_search(content)
        self._build_body(content)

        grip_row = QHBoxLayout()
        grip_row.setContentsMargins(0, 0, 2, 0)
        grip_row.addStretch()
        grip = QSizeGrip(self.terminal_box)
        grip.setObjectName("referenceSizeGrip")
        grip_row.addWidget(grip)
        main.addLayout(grip_row)

    def _build_title_bar(self, parent_layout):
        bar = DarkMetallicTitleBar(height=28, radius=12)
        bar.setObjectName("referenceTitleBar")

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(14, 0, 10, 0)
        layout.setSpacing(0)

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

    def _counts(self):
        """Calcula os totais diretamente do conteúdo do Reference."""
        commands = self._load_json(COMMANDS_FILE, [])
        visible = len(commands) if isinstance(commands, list) else 0

        sections_by_id = {
            section.get("id"): section
            for section in self.sections
            if isinstance(section, dict)
        }
        special = len(sections_by_id.get("buscas", {}).get("items", []))
        pdf_actions = len(sections_by_id.get("pdf", {}).get("items", []))
        return visible, special, pdf_actions

    def _build_header(self, parent_layout):
        product = self.data.get("product", {})
        visible, special, pdf_actions = self._counts()

        summary = QLabel(
            f"{visible} comandos  ·  {special} recursos especiais  ·  "
            f"{pdf_actions} ações PDF"
        )
        summary.setObjectName("referenceCounts")

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

        product = self.data.get("product", {})
        version = str(product.get("version", "")).lstrip("v")
        updated = product.get("updated") or product.get("created", "")
        signature = QLabel(
            f"Versão {version}\nBuilt with Python + Qt\n"
            f"Atualizado em {updated}\nby Mariane Jacob"
        )
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

        if search_title:
            heading = QLabel(search_title)
            heading.setObjectName("referenceHeading")
            self.content_layout.addWidget(heading)

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

    @staticmethod
    def _search_tokens(value):
        normalized = unicodedata.normalize("NFKD", str(value).casefold())
        normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
        return re.findall(r"[a-z0-9]+", normalized)

    def _on_search(self, text):
        raw_query = text.strip()
        query_tokens = self._search_tokens(raw_query)
        if not query_tokens:
            section = next(
                (s for s in self.sections if s.get("id") == self.active_section_id),
                self.sections[0] if self.sections else {},
            )
            self._render_section(section)
            return

        ranked_results = []
        for section, item in self._all_items():
            code_tokens = self._search_tokens(item.get("code", ""))
            title_tokens = self._search_tokens(item.get("title", ""))
            description_tokens = self._search_tokens(
                item.get("description", "")
            )
            keyword_tokens = self._search_tokens(" ".join(item.get("keywords", [])))
            searchable_tokens = set(
                code_tokens
                + title_tokens
                + description_tokens
                + keyword_tokens
            )

            # Cada termo precisa existir como palavra real. Assim, "git" não
            # encontra acidentalmente "digite". Prefixos continuam úteis
            # para buscas como "rein" ou "mont".
            def matches(term):
                return any(
                    token == term or (len(term) >= 3 and token.startswith(term))
                    for token in searchable_tokens
                )

            if not all(matches(term) for term in query_tokens):
                continue

            exact_code = all(term in code_tokens for term in query_tokens)
            exact_title = all(term in title_tokens for term in query_tokens)
            score = (3 if exact_code else 0) + (2 if exact_title else 0)
            ranked_results.append((score, section.get("title", ""), item))

        ranked_results.sort(key=lambda row: (-row[0], row[2].get("code", "")))
        results = []
        for _, section_title, item in ranked_results:
            enriched = dict(item)
            enriched["title"] = f'{item.get("title", "")} · {section_title}'
            results.append(enriched)

        self._set_active_nav("")
        self._render_section(
            {"title": "BUSCA"},
            items=results,
            search_title=f'RESULTADOS PARA "{raw_query}"',
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
                color: white; font-size: 10px; font-weight: 400; letter-spacing: 1px;
            }}
            QLabel#referenceClose {{ color: white; font-size: 16px; padding: 0 4px; }}
            QLabel#referenceClose:hover {{ color: {YELLOW}; }}
            QLabel#referenceDivider {{
                color: rgba(255, 196, 0, 0.58); font-size: 6px; max-height: 8px;
            }}
            QLabel#referenceProduct {{
                color: {YELLOW}; font-size: 16px; font-weight: 600;
                letter-spacing: 1px; padding-top: 2px;
            }}
            QLabel#referenceMeta {{ color: rgba(255, 196, 0, 0.82); font-size: 10px; padding-top: 1px; }}
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

    def _restore_geometry(self):
        geometry = self.settings.value("reference_dialog_geometry")
        if geometry:
            self.restoreGeometry(geometry)

    def _schedule_geometry_save(self):
        self._geometry_save_timer.start(350)

    def _save_geometry(self):
        self.settings.setValue("reference_dialog_geometry", self.saveGeometry())

    def moveEvent(self, event):
        super().moveEvent(event)
        self._schedule_geometry_save()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._schedule_geometry_save()

    def closeEvent(self, event):
        self._save_geometry()
        super().closeEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and event.position().y() <= 28:
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
        self._save_geometry()
        super().mouseReleaseEvent(event)
