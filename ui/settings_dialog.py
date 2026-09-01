from __future__ import annotations

import json
import unicodedata
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QPoint, QRectF, QSettings, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor, QCursor, QIcon, QImage, QKeyEvent, QKeySequence, QPainterPath,
    QPixmap, QRegion, QShortcut, QTextCursor,
)
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QDialog, QFileDialog, QFrame,
    QHeaderView, QHBoxLayout, QLabel, QListWidget, QMessageBox,
    QListWidgetItem, QLineEdit, QPlainTextEdit, QPushButton, QScrollArea,
    QStackedWidget, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget,
)

from core.project_metadata import (
    git_entries,
    latest_git_commit,
    reference_items,
    reference_product,
    system_info,
)
from ui.tool_design import (
    TOOL_STANDARD_QSS, apply_terminal_accent, set_tool_role,
    show_button_success,
)
from ui.widgets import DarkMetallicTitleBar


YELLOW = "#FFC400"
ROOT = Path(__file__).resolve().parent.parent


class LibraryTableWidget(QTableWidget):
    def keyPressEvent(self, event: QKeyEvent):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            row = self.currentRow()
            column = self.currentColumn()
            if row >= 0 and column >= 0:
                next_column = column + 1
                next_row = row
                if next_column >= self.columnCount():
                    next_column = 0
                    next_row = min(row + 1, self.rowCount() - 1)
                self.setCurrentCell(next_row, next_column)
                self.editItem(self.item(next_row, next_column))
                event.accept()
                return
        super().keyPressEvent(event)


def _white_asset_icon(path):
    pixmap = QPixmap(str(path)).scaled(
        24, 24, Qt.KeepAspectRatio, Qt.SmoothTransformation
    )
    if pixmap.isNull():
        return QIcon()
    image = pixmap.toImage().convertToFormat(QImage.Format_RGBA8888)
    for y in range(image.height()):
        for x in range(image.width()):
            source = image.pixelColor(x, y)
            luminance = max(source.red(), source.green(), source.blue())
            alpha = max(0, min(255, round((luminance - 60) * 255 / 195)))
            alpha = min(alpha, source.alpha())
            image.setPixelColor(x, y, QColor(255, 255, 255, alpha))
    return QIcon(QPixmap.fromImage(image))


class SettingsDialog(QDialog):
    librariesChanged = Signal()

    NAVIGATION = (
        ("GERAL", "general"),
        ("COMANDOS", "commands"),
        ("BIBLIOTECAS", "libraries"),
        ("ATALHOS", "shortcuts"),
        ("NOTAS", "notes"),
        ("SOBRE", "about"),
    )

    def __init__(self, terminal):
        super().__init__(terminal)
        self.terminal = terminal
        self.settings = QSettings("M87Tools", "M87Terminal")
        self._drag_position = QPoint()
        self._notes_save_timer = QTimer(self)
        self._notes_save_timer.setSingleShot(True)
        self._notes_save_timer.timeout.connect(self._save_notes)
        self._setup_window()
        self._build_ui()
        self._restore_geometry()

    def _setup_window(self):
        self.setWindowTitle("M87 • CONFIGURAÇÕES")
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMinimumSize(860, 560)
        self.resize(1040, 650)

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        box = QWidget()
        box.setObjectName("settingsBox")
        outer.addWidget(box)

        root = QVBoxLayout(box)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        bar = DarkMetallicTitleBar(height=30, radius=12)
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(14, 0, 10, 0)
        title = QLabel("CONFIGURAÇÕES")
        title.setObjectName("settingsWindowTitle")
        close = QLabel("×")
        close.setObjectName("settingsClose")
        close.setCursor(QCursor(Qt.PointingHandCursor))
        close.mousePressEvent = lambda event: self.close()
        bar_layout.addWidget(title)
        bar_layout.addStretch()
        bar_layout.addWidget(close)
        bar.mousePressEvent = self._title_press
        bar.mouseMoveEvent = self._title_move
        root.addWidget(bar)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        sidebar = QWidget()
        sidebar.setObjectName("settingsSidebar")
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 12)
        sidebar_layout.setSpacing(0)
        self.navigation = QListWidget()
        self.navigation.setObjectName("settingsNavigation")
        self.navigation.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.pages = QStackedWidget()
        self.pages.setObjectName("settingsPages")

        builders = {
            "general": self._general_page,
            "commands": self._commands_page,
            "libraries": self._libraries_page,
            "shortcuts": self._shortcuts_page,
            "notes": self._notes_page,
            "about": self._about_page,
        }
        self._row_to_page = {}
        self._key_to_row = {}
        for row, (label, key) in enumerate(self.NAVIGATION):
            item = QListWidgetItem(label)
            page_index = self.pages.count()
            self._row_to_page[row] = page_index
            self._key_to_row[key] = row
            self.pages.addWidget(builders[key]())
            self.navigation.addItem(item)
        self.navigation.currentRowChanged.connect(self._navigation_changed)
        self.navigation.setCurrentRow(self._key_to_row["general"])
        sidebar_layout.addWidget(self.navigation, 1)
        sidebar_layout.addWidget(self._quick_access_panel())
        sidebar.setFixedWidth(190)
        body.addWidget(sidebar)
        body.addWidget(self.pages, 1)
        root.addLayout(body, 1)

        self.setStyleSheet(TOOL_STANDARD_QSS + f"""
            QWidget#settingsBox {{
                background:#050607;
                border:1px solid rgba(255,196,0,.24);
                border-radius:13px;
            }}
            QLabel#settingsWindowTitle {{
                color:white; font-size:10px; font-weight:700; letter-spacing:1px;
            }}
            QLabel#settingsClose {{ color:white; font-size:16px; padding:0 4px; }}
            QLabel#settingsClose:hover {{ color:{YELLOW}; }}
            QListWidget#settingsNavigation {{
                background:rgba(255,255,255,.025);
                border:0;
                padding:12px 0;
                outline:0;
            }}
            QWidget#settingsSidebar {{
                background:rgba(255,255,255,.025);
                border:0; border-right:1px solid rgba(255,255,255,.10);
            }}
            QListWidget#settingsNavigation::item {{
                color:rgba(255,255,255,.62); min-height:34px;
                padding:0 18px; border:0;
            }}
            QListWidget#settingsNavigation::item:hover {{
                color:rgba(255,196,0,.88); background:rgba(255,196,0,.04);
            }}
            QListWidget#settingsNavigation::item:selected {{
                color:{YELLOW}; background:rgba(255,255,255,.055);
                border-right:2px solid {YELLOW}; font-weight:700;
            }}
            QStackedWidget#settingsPages {{ background:#050607; border:0; }}
            QLabel#settingsPageTitle {{ color:{YELLOW}; font-size:13px; font-weight:700; }}
            QLabel#settingsDescription {{ color:rgba(255,255,255,.48); font-size:11px; }}
            QLabel#settingsCardTitle {{ color:{YELLOW}; font-size:11px; font-weight:700; }}
            QLabel#settingsCardValue {{ color:rgba(255,255,255,.62); font-size:11px; }}
            QPushButton#settingsAction {{
                color:rgba(255,255,255,.72); background:rgba(255,255,255,.035);
                border:1px solid rgba(255,255,255,.14); border-radius:4px;
                min-height:28px; padding:0 12px; font-weight:700;
            }}
            QPushButton#settingsAction:hover {{ color:{YELLOW}; border-color:rgba(255,196,0,.42); }}
            QLabel#settingsQuickTitle {{
                color:rgba(255,255,255,.48); font-size:9px;
                font-weight:700; letter-spacing:.8px; padding:4px 14px;
            }}
            QPushButton#settingsQuickAction {{
                color:rgba(255,255,255,.64); background:transparent;
                border:1px solid rgba(255,255,255,.10); border-radius:4px;
                min-width:38px; max-width:38px; min-height:32px; max-height:32px;
                padding:0; text-align:center; font-size:17px; font-weight:700;
            }}
            QPushButton#settingsQuickAction:hover {{
                color:{YELLOW}; background:rgba(255,196,0,.045);
            }}
            QCheckBox {{ color:rgba(255,255,255,.76); min-height:24px; }}
            QCheckBox#settingsCommandCheck {{
                color:rgba(255,255,255,.70); font-size:11px;
                font-weight:400; min-height:25px; spacing:7px;
            }}
            QCheckBox#settingsCommandCheck:hover {{ color:rgba(255,239,150,.92); }}
            QTableWidget#settingsCommandTable {{
                color:rgba(255,255,255,.72);
                background:rgba(255,255,255,.015);
                alternate-background-color:rgba(255,255,255,.028);
                border:1px solid rgba(255,255,255,.09);
                border-radius:5px; gridline-color:rgba(255,255,255,.075);
                selection-background-color:rgba(255,196,0,.08);
                selection-color:rgba(255,255,255,.90);
                font-size:11px;
            }}
            QTableWidget#settingsCommandTable::item {{ padding:0 8px; }}
            QTableWidget#settingsCommandTable::item[commandSection="true"] {{
                color:rgba(255,196,0,.72);
                background:rgba(255,255,255,.04);
                font-size:10px; font-weight:700;
            }}
            QHeaderView::section {{
                color:rgba(255,196,0,.78);
                background:rgba(255,255,255,.045);
                border:0; border-right:1px solid rgba(255,255,255,.08);
                border-bottom:1px solid rgba(255,255,255,.10);
                padding:7px 8px; font-size:10px; font-weight:700;
            }}
            QTableWidget#settingsLibraryTable {{
                color:rgba(255,255,255,.76);
                background:rgba(255,255,255,.018);
                alternate-background-color:rgba(255,255,255,.03);
                border:1px solid rgba(255,255,255,.09);
                border-radius:5px; gridline-color:rgba(255,255,255,.07);
                selection-background-color:rgba(255,196,0,.10);
                selection-color:white; font-size:11px;
            }}
            QTableWidget#settingsLibraryTable::item {{ padding:0 8px; }}
            QPushButton#settingsLibraryAction {{
                color:rgba(255,255,255,.64); background:transparent;
                border:1px solid rgba(255,255,255,.11); border-radius:4px;
                min-height:23px; max-height:23px; padding:0 8px;
                font-size:9px; font-weight:700;
            }}
            QPushButton#settingsLibraryAction:hover {{
                color:{YELLOW}; border-color:rgba(255,196,0,.34);
            }}
            QToolTip {{
                color:rgba(255,255,255,.88); background:#171819;
                border:1px solid rgba(255,196,0,.30);
                padding:6px; font-size:10px;
            }}
            QPlainTextEdit#settingsNotes {{
                color:rgba(255,255,255,.86);
                font-size:11px;
                background:rgba(255,255,255,.035);
                border:1px solid rgba(255,255,255,.10);
                border-radius:7px; padding:10px;
                selection-background-color:rgba(255,196,0,.30);
            }}
            QLabel#settingsAboutName {{
                color:{YELLOW}; font-size:14px; font-weight:700;
                letter-spacing:1px;
            }}
            QLabel#settingsAboutText {{
                color:rgba(255,255,255,.76); font-size:11px;
            }}
            QLabel#settingsAboutMeta {{
                color:rgba(255,255,255,.56); font-size:10px;
            }}
            QLabel#settingsCounter {{
                color:{YELLOW}; font-size:11px; font-weight:700;
                letter-spacing:.6px;
            }}
            QLabel#settingsShortcutCategory {{
                color:rgba(255,196,0,.72); font-size:10px;
                font-weight:700; letter-spacing:.7px; padding:7px 2px 2px 2px;
            }}
            QFrame#settingsShortcutRow {{
                background:rgba(255,255,255,.025);
                border:1px solid rgba(255,255,255,.07);
                border-radius:5px;
            }}
            QLabel#settingsShortcutTitle {{
                color:rgba(255,239,150,.90); font-size:11px; font-weight:700;
            }}
            QLabel#settingsShortcutDescription {{
                color:rgba(255,255,255,.66); font-size:11px;
            }}
            QLabel#settingsChangeDate {{
                color:{YELLOW}; font-size:10px; font-weight:700;
                padding:8px 0 2px 0;
            }}
            QLabel#settingsCommit {{
                color:rgba(255,255,255,.68); font-size:11px;
                padding:1px 0;
            }}
            QPushButton#settingsChangelogButton {{
                color:rgba(255,255,255,.52); background:transparent;
                border:1px solid rgba(255,255,255,.10); border-radius:4px;
                min-height:24px; max-height:24px; padding:0 10px;
                font-size:9px; font-weight:700;
            }}
            QPushButton#settingsChangelogButton:hover {{
                color:{YELLOW}; border-color:rgba(255,196,0,.32);
            }}
        """)
        apply_terminal_accent(self)

    def _page(self, title, description):
        page = QWidget()
        page.setProperty("toolSurface", True)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(10)
        heading = QLabel(title)
        heading.setObjectName("settingsPageTitle")
        layout.addWidget(heading)
        layout.addSpacing(10)
        return page, layout

    def _general_page(self):
        page, layout = self._page(
            "GERAL", "Preferências globais do M87 Terminal."
        )
        windows_card = QFrame()
        set_tool_role(windows_card, "card")
        windows_layout = QVBoxLayout(windows_card)
        windows_layout.setContentsMargins(14, 11, 14, 11)
        windows_layout.setSpacing(7)
        windows_title = QLabel("JANELAS")
        windows_title.setObjectName("settingsCardTitle")
        self.remember_geometry = QCheckBox(
            "LEMBRAR TAMANHO E POSIÇÃO DAS JANELAS"
        )
        self.remember_geometry.setChecked(self.settings.value(
            "general/remember_geometry", True, type=bool
        ))
        windows_description = QLabel(
            "O M87 restaura automaticamente o tamanho e a posição usados anteriormente."
        )
        windows_description.setObjectName("settingsCardValue")
        windows_description.setWordWrap(True)
        windows_layout.addWidget(windows_title)
        windows_layout.addWidget(self.remember_geometry)
        windows_layout.addWidget(windows_description)
        self.restore_last_tool = QCheckBox(
            "RESTAURAR A ÚLTIMA FERRAMENTA OU ABA ABERTA"
        )
        self.restore_last_tool.setChecked(self.settings.value(
            "general/restore_last_tool", True, type=bool
        ))
        self.confirm_close = QCheckBox("CONFIRMAR ANTES DE FECHAR O M87")
        self.confirm_close.setChecked(self.settings.value(
            "general/confirm_close", True, type=bool
        ))
        windows_layout.addWidget(self.restore_last_tool)
        windows_layout.addWidget(self.confirm_close)
        layout.addWidget(windows_card)

        startup_card = QFrame()
        set_tool_role(startup_card, "card")
        startup_layout = QVBoxLayout(startup_card)
        startup_layout.setContentsMargins(14, 11, 14, 11)
        startup_layout.setSpacing(7)
        startup_title = QLabel("INICIALIZAÇÃO")
        startup_title.setObjectName("settingsCardTitle")
        self.start_with_system = QCheckBox("INICIAR JUNTO COM O SISTEMA")
        self.start_with_system.setChecked(
            self.settings.value(
                "general/start_with_system", True, type=bool,
            )
        )
        self.startup_status = QLabel(
            "O M87 será aberto automaticamente ao iniciar a sessão do macOS."
        )
        self.startup_status.setObjectName("settingsCardValue")
        self.startup_status.setWordWrap(True)
        startup_layout.addWidget(startup_title)
        startup_layout.addWidget(self.start_with_system)
        self.start_minimized = QCheckBox(
            "ABRIR O M87 MINIMIZADO AO INICIAR COM O SISTEMA"
        )
        self.start_minimized.setChecked(self.settings.value(
            "general/start_minimized", False, type=bool
        ))
        self.start_minimized.setEnabled(self.start_with_system.isChecked())
        startup_layout.addWidget(self.start_minimized)
        startup_layout.addWidget(self.startup_status)
        self.start_with_system.toggled.connect(self._start_with_system_changed)
        self.start_with_system.toggled.connect(self.start_minimized.setEnabled)
        self.start_minimized.toggled.connect(self._start_minimized_changed)
        layout.addWidget(startup_card)

        files_card = QFrame()
        set_tool_role(files_card, "card")
        files_layout = QVBoxLayout(files_card)
        files_layout.setContentsMargins(14, 11, 14, 11)
        files_layout.setSpacing(7)
        files_title = QLabel("ARQUIVOS E INTERFACE")
        files_title.setObjectName("settingsCardTitle")
        self.default_save_folder = QLabel()
        self.default_save_folder.setObjectName("settingsCardValue")
        self._update_default_folder_label()
        file_actions = QHBoxLayout()
        choose_folder = QPushButton("ESCOLHER PASTA…")
        choose_folder.setObjectName("settingsAction")
        choose_folder.clicked.connect(self._choose_default_save_folder)
        self.reset_interface_button = QPushButton("RESTAURAR PADRÕES DA INTERFACE")
        self.reset_interface_button.setObjectName("settingsAction")
        self.reset_interface_button.clicked.connect(self._reset_interface_defaults)
        file_actions.addWidget(choose_folder)
        file_actions.addWidget(self.reset_interface_button)
        file_actions.addStretch()
        files_layout.addWidget(files_title)
        files_layout.addWidget(self.default_save_folder)
        files_layout.addLayout(file_actions)
        layout.addWidget(files_card)

        for checkbox, key in (
            (self.remember_geometry, "general/remember_geometry"),
            (self.restore_last_tool, "general/restore_last_tool"),
            (self.confirm_close, "general/confirm_close"),
        ):
            checkbox.toggled.connect(
                lambda value, setting_key=key: self._set_preference(
                    setting_key, value
                )
            )
        layout.addStretch()
        return page

    def _set_preference(self, key, value):
        self.settings.setValue(key, value)
        self.settings.sync()

    def _update_default_folder_label(self):
        folder = str(self.settings.value("general/default_save_folder", ""))
        self.default_save_folder.setText(
            f"Pasta padrão para Salvar Como: {folder}"
            if folder else
            "Pasta padrão para Salvar Como: usar a pasta sugerida pela ferramenta."
        )

    def _choose_default_save_folder(self):
        current = str(self.settings.value(
            "general/default_save_folder", str(Path.home() / "Desktop")
        ))
        folder = QFileDialog.getExistingDirectory(
            self, "Pasta padrão para Salvar Como", current
        )
        if not folder:
            return
        self.settings.setValue("general/default_save_folder", folder)
        self.settings.sync()
        self._update_default_folder_label()

    def _reset_interface_defaults(self):
        answer = QMessageBox.question(
            self,
            "M87 • INTERFACE",
            "Restaurar tamanhos, posições e a última aba aberta?",
            QMessageBox.Cancel | QMessageBox.Yes,
            QMessageBox.Cancel,
        )
        if answer != QMessageBox.Yes:
            return
        for key in (
            "settings/geometry", "tools_dialog/geometry",
            "tools_dialog/last_tab", "pdf_info_dialog/geometry",
        ):
            self.settings.remove(key)
        self.settings.sync()
        show_button_success(
            self.reset_interface_button,
            restore_text="RESTAURAR PADRÕES DA INTERFACE",
        )

    def _start_with_system_changed(self, enabled):
        from core.startup import set_start_with_system

        success, message = set_start_with_system(
            enabled, hidden=self.start_minimized.isChecked()
        )
        if not success:
            self.start_with_system.blockSignals(True)
            self.start_with_system.setChecked(not enabled)
            self.start_with_system.blockSignals(False)
            self.startup_status.setText(f"Não foi possível alterar: {message}")
            return
        self.settings.setValue("general/start_with_system", enabled)
        self.settings.sync()
        self.startup_status.setText(
            "O M87 será aberto automaticamente ao iniciar a sessão do macOS."
            if enabled else
            "O M87 não será aberto automaticamente com o macOS."
        )

    def _start_minimized_changed(self, enabled):
        self._set_preference("general/start_minimized", enabled)
        if self.start_with_system.isChecked():
            self._start_with_system_changed(True)

    def _quick_access_panel(self):
        panel = QWidget()
        layout = QHBoxLayout(panel)
        layout.setContentsMargins(14, 8, 14, 0)
        layout.setSpacing(7)
        actions = (
            ("quick_vscode.png", "Abrir VS Code", self.terminal.open_project_in_vscode),
            ("quick_chatgpt.png", "Abrir ChatGPT", self.terminal.open_codex),
            ("quick_refresh.png", "Reiniciar M87", self.terminal.restart_app),
        )
        for icon_name, tooltip, callback in actions:
            button = QPushButton()
            button.setObjectName("settingsQuickAction")
            button.setIcon(_white_asset_icon(ROOT / "assets" / icon_name))
            button.setIconSize(QSize(21, 21))
            button.setCursor(QCursor(Qt.PointingHandCursor))
            button.setToolTip(tooltip)
            button.clicked.connect(callback)
            layout.addWidget(button)
        layout.addStretch()
        return panel

    def _commands_page(self):
        page, layout = self._page("COMANDOS", "")
        from core.command_preferences import normalize_code_list

        hidden = set(normalize_code_list(
            self.settings.value("terminal/hidden_commands", [])
        ))
        descriptions = {
            str(item.get("code", "")).upper(): str(item.get("description", ""))
            for item in self._reference_items("comandos")
        }
        commands = [
            command for command in self.terminal.commands
            if str(command.get("code", "")).strip()
        ]
        command_controls = QHBoxLayout()
        self.command_search = QLineEdit()
        self.command_search.setPlaceholderText("Buscar código, nome ou descrição")
        self.command_search.setClearButtonEnabled(True)
        self.command_counter = QLabel()
        self.command_counter.setObjectName("settingsDescription")
        mark_all = QPushButton("MARCAR TODOS")
        mark_all.setObjectName("settingsAction")
        restore = QPushButton("RESTAURAR PADRÃO")
        restore.setObjectName("settingsAction")
        command_controls.addWidget(self.command_search, 1)
        command_controls.addWidget(self.command_counter)
        command_controls.addWidget(mark_all)
        command_controls.addWidget(restore)
        layout.addLayout(command_controls)
        section_count = len({
            str(command.get("section", "COMANDOS")).upper()
            for command in commands
        })
        table = QTableWidget(len(commands) + section_count, 4)
        self.command_table = table
        table.setObjectName("settingsCommandTable")
        table.setHorizontalHeaderLabels(("", "CÓDIGO", "NOME", "DESCRIÇÃO"))
        table.horizontalHeaderItem(0).setTextAlignment(Qt.AlignCenter)
        table.horizontalHeaderItem(1).setTextAlignment(Qt.AlignCenter)
        table.verticalHeader().hide()
        table.setShowGrid(True)
        table.setAlternatingRowColors(True)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        table.setWordWrap(False)
        table.setColumnWidth(0, 38)
        table.setColumnWidth(1, 62)
        table.setColumnWidth(2, 170)
        header = table.horizontalHeader()
        for column in range(3):
            header.setSectionResizeMode(column, QHeaderView.Fixed)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        self.command_checks = {}
        self.command_rows = {}
        self.command_section_rows = {}
        row = 0
        current_section = None
        for command in commands:
            code = str(command.get("code", "")).upper()
            label = str(command.get("label", code))
            summary = str(command.get("description", "")).strip()
            summary = summary or descriptions.get(code, "")
            section = str(command.get("section", "COMANDOS")).upper()

            if section != current_section:
                current_section = section
                section_item = QTableWidgetItem(section)
                section_item.setData(Qt.UserRole, "section")
                section_item.setForeground(QColor(255, 196, 0, 185))
                section_item.setBackground(QColor(255, 255, 255, 10))
                section_item.setFlags(Qt.ItemIsEnabled)
                table.setItem(row, 0, section_item)
                table.setSpan(row, 0, 1, 4)
                table.setRowHeight(row, 26)
                self.command_section_rows[section] = row
                row += 1

            check_wrap = QWidget()
            check_layout = QHBoxLayout(check_wrap)
            check_layout.setContentsMargins(0, 0, 0, 0)
            check_layout.setAlignment(Qt.AlignCenter)
            check = QCheckBox()
            check.setObjectName("settingsCommandCheck")
            check.setChecked(code not in hidden)
            check_layout.addWidget(check)
            check.toggled.connect(self._command_selection_changed)
            self.command_checks[code] = check
            table.setCellWidget(row, 0, check_wrap)
            code_item = QTableWidgetItem(code)
            code_item.setTextAlignment(Qt.AlignCenter)
            table.setItem(row, 1, code_item)
            table.setItem(row, 2, QTableWidgetItem(label))
            description_item = QTableWidgetItem(summary)
            if code in {"END", "KILL", "CL"}:
                description_item.setText(f"⚠  {summary}")
                description_item.setToolTip(
                    "Ação crítica ou que exige confirmação.\n" + summary
                )
                description_item.setForeground(QColor(255, 190, 90))
            else:
                description_item.setToolTip(summary)
            table.setItem(row, 3, description_item)
            table.setRowHeight(row, 30)
            self.command_rows[row] = {
                "code": code,
                "name": label,
                "description": summary,
                "section": section,
            }
            row += 1

        table.cellClicked.connect(self._command_row_clicked)
        self.command_search.textChanged.connect(self._filter_commands)
        mark_all.clicked.connect(lambda: self._set_all_commands(True))
        restore.clicked.connect(self._restore_default_commands)
        self._update_command_counter()
        layout.addWidget(table, 1)
        return page

    def _set_all_commands(self, checked):
        for check in self.command_checks.values():
            check.blockSignals(True)
            check.setChecked(checked)
            check.blockSignals(False)
        self._command_selection_changed()

    def _restore_default_commands(self):
        self._set_all_commands(True)
        self.command_search.clear()

    def _update_command_counter(self):
        visible = sum(check.isChecked() for check in self.command_checks.values())
        self.command_counter.setText(
            f"{visible} DE {len(self.command_checks)} COMANDOS VISÍVEIS"
        )

    def _filter_commands(self, text):
        query = self._search_key(text.strip())
        sections = {}
        for row, command in self.command_rows.items():
            searchable = self._search_key(
                f"{command['code']} {command['name']} "
                f"{command['description']} {command['section']}"
            )
            show = not query or query in searchable
            self.command_table.setRowHidden(row, not show)
            sections.setdefault(command["section"], []).append(show)
        for section, row in self.command_section_rows.items():
            self.command_table.setRowHidden(row, not any(sections.get(section, [])))

    def _command_row_clicked(self, row, column):
        if column == 0 or row not in self.command_rows:
            return
        self._open_command_details(self.command_rows[row])

    def _open_command_details(self, command):
        code = command["code"]
        dialog = QDialog(self)
        dialog.setWindowTitle(f"{code} · {command['name']}")
        dialog.setModal(True)
        dialog.setFixedWidth(520)
        dialog.setProperty("toolSurface", True)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(10)

        shortcut = QLabel(f"Atalho: {code}")
        shortcut.setObjectName("settingsPageTitle")
        name = QLabel(f"Nome: {command['name']}")
        name.setObjectName("settingsCardValue")
        description = QLabel(
            f"- {command['description']}"
            if command["description"]
            else "- Descrição ainda não cadastrada."
        )
        description.setObjectName("settingsCardValue")
        description.setWordWrap(True)
        description.setMinimumHeight(44)
        layout.addWidget(shortcut)
        layout.addWidget(name)
        layout.addWidget(description)

        actions = QHBoxLayout()
        actions.addStretch()
        close = QPushButton("FECHAR")
        close.setObjectName("settingsAction")
        close.clicked.connect(dialog.accept)
        actions.addWidget(close)
        layout.addLayout(actions)

        dialog.setStyleSheet(self.styleSheet())
        apply_terminal_accent(dialog)
        dialog.exec()

    def _command_selection_changed(self, _checked=False):
        visible = [
            code for code, check in self.command_checks.items()
            if check.isChecked()
        ]
        self.terminal.apply_command_visibility(visible)
        self._update_command_counter()

    def _navigation_changed(self, row):
        page_index = self._row_to_page.get(row)
        if page_index is None:
            return
        self.pages.setCurrentIndex(page_index)
        if (
            row == self._key_to_row.get("about")
            and hasattr(self, "changelog_layout")
        ):
            self.refresh_git_history()

    def show_section(self, section_id):
        if section_id == "notes":
            self.navigation.setCurrentRow(self._key_to_row["notes"])
            QTimer.singleShot(0, self.focus_notes_editor)
            return
        if section_id in {"commands", "shortcuts", "searches"}:
            target = "commands" if section_id == "commands" else "shortcuts"
            self.navigation.setCurrentRow(self._key_to_row[target])
            return
        self.navigation.setCurrentRow(self._key_to_row.get(section_id, 0))

    def _notes_page(self):
        page, layout = self._page("NOTAS", "")
        note_bar = QHBoxLayout()
        self.notes_search = QLineEdit()
        self.notes_search.setPlaceholderText("Buscar nas notas  ⌘F")
        self.notes_search.setClearButtonEnabled(True)
        self.notes_status = QLabel()
        self.notes_status.setObjectName("settingsDescription")
        updated = str(self.settings.value("notes/updated_at", ""))
        self.notes_status.setText(
            f"SALVO · {updated}" if updated else "SALVO"
        )
        note_bar.addWidget(self.notes_search, 1)
        note_bar.addWidget(self.notes_status)
        layout.addLayout(note_bar)
        self.notes_editor = QPlainTextEdit()
        self.notes_editor.setObjectName("settingsNotes")
        self.notes_editor.setPlaceholderText(
            "Anote aqui ideias, ajustes e melhorias..."
        )
        self.notes_editor.setPlainText(
            str(self.settings.value("reference/notes", ""))
        )
        self.notes_editor.textChanged.connect(self._notes_changed)
        self.notes_search.returnPressed.connect(self._find_in_notes)
        self.notes_find_shortcut = QShortcut(QKeySequence.Find, page)
        self.notes_find_shortcut.activated.connect(
            lambda: self.notes_search.setFocus(Qt.ShortcutFocusReason)
        )
        layout.addWidget(self.notes_editor, 1)
        return page

    def _notes_changed(self):
        self.notes_status.setText("SALVANDO…")
        self._notes_save_timer.start(400)

    def _find_in_notes(self):
        query = self.notes_search.text().strip()
        if not query:
            return
        if not self.notes_editor.find(query):
            self.notes_editor.moveCursor(QTextCursor.Start)
            self.notes_editor.find(query)

    def _save_notes(self):
        if hasattr(self, "notes_editor"):
            self.settings.setValue(
                "reference/notes", self.notes_editor.toPlainText()
            )
            updated = datetime.now().strftime("%d/%m/%Y %H:%M")
            self.settings.setValue("notes/updated_at", updated)
            self.settings.sync()
            if hasattr(self, "notes_status"):
                self.notes_status.setText(f"SALVO · {updated}")

    def focus_notes_editor(self):
        self.notes_editor.moveCursor(QTextCursor.End)
        self.notes_editor.ensureCursorVisible()
        self.notes_editor.setFocus(Qt.OtherFocusReason)

    def _libraries_page(self):
        page, layout = self._page(
            "BIBLIOTECAS",
            "Clique duas vezes numa célula para editar. As alterações são salvas automaticamente.",
        )
        self._loading_libraries = True
        self.formats_page, self.formats_table = self._library_table_page(
            ("FORMATOS DE PAPEL", "LARGURA (mm)", "ALTURA (mm)"),
            self._add_format_row,
            lambda: self._remove_library_row(self.formats_table),
            name_width=210,
            swap_callback=self._swap_format_dimensions,
        )
        self.paper_types_page, self.paper_types_table = self._library_table_page(
            ("TIPOS DE PAPEL",),
            self._add_paper_type_row,
            lambda: self._remove_library_row(self.paper_types_table),
        )
        layout.addWidget(self.formats_page, 0)
        layout.addWidget(self.paper_types_page, 0)
        layout.addStretch()

        self._load_inline_libraries()
        self._resize_library_sections()
        self.formats_table.itemChanged.connect(self._save_inline_libraries)
        self.paper_types_table.itemChanged.connect(self._save_inline_libraries)
        self._loading_libraries = False
        return page

    def _resize_library_sections(self):
        format_height = min(
            360, max(210, 116 + self.formats_table.rowCount() * 30)
        )
        paper_height = min(
            240, max(148, 116 + self.paper_types_table.rowCount() * 30)
        )
        self.formats_page.setFixedHeight(format_height)
        self.paper_types_page.setFixedHeight(paper_height)

    def _library_table_page(
        self, headers, add_callback, remove_callback, name_width=None,
        swap_callback=None,
    ):
        page = QWidget()
        page.setProperty("toolSurface", True)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        table = LibraryTableWidget(0, len(headers))
        table.setObjectName("settingsLibraryTable")
        table.setHorizontalHeaderLabels(headers)
        for column in range(1, len(headers)):
            table.horizontalHeaderItem(column).setTextAlignment(Qt.AlignCenter)
        table.verticalHeader().hide()
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setTabKeyNavigation(True)
        if name_width is None:
            table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        else:
            table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
            table.setColumnWidth(0, name_width)
        for column in range(1, len(headers)):
            table.horizontalHeader().setSectionResizeMode(column, QHeaderView.Stretch)
        layout.addWidget(table, 1)
        actions = QHBoxLayout()
        add = QPushButton("+ ADICIONAR")
        add.setObjectName("settingsLibraryAction")
        add.clicked.connect(add_callback)
        remove = QPushButton("EXCLUIR")
        remove.setObjectName("settingsLibraryAction")
        remove.clicked.connect(remove_callback)
        move_up = QPushButton("↑")
        move_up.setObjectName("settingsLibraryAction")
        move_up.setFixedWidth(28)
        move_up.setToolTip("Mover entrada para cima")
        move_up.clicked.connect(lambda: self._move_library_row(table, -1))
        move_down = QPushButton("↓")
        move_down.setObjectName("settingsLibraryAction")
        move_down.setFixedWidth(28)
        move_down.setToolTip("Mover entrada para baixo")
        move_down.clicked.connect(lambda: self._move_library_row(table, 1))
        actions.addWidget(add)
        actions.addWidget(remove)
        actions.addWidget(move_up)
        actions.addWidget(move_down)
        if swap_callback is not None:
            swap = QPushButton("⇄")
            swap.setObjectName("settingsLibraryAction")
            swap.setFixedWidth(32)
            swap.setToolTip("Inverter largura e altura")
            swap.clicked.connect(swap_callback)
            actions.addWidget(swap)
        actions.addStretch()
        layout.addLayout(actions)
        return page, table

    def _swap_format_dimensions(self):
        row = self.formats_table.currentRow()
        if row < 0:
            return
        width = self._table_text(self.formats_table, row, 1)
        height = self._table_text(self.formats_table, row, 2)
        self.formats_table.blockSignals(True)
        self.formats_table.item(row, 1).setText(height)
        self.formats_table.item(row, 2).setText(width)
        self.formats_table.blockSignals(False)
        self._save_inline_libraries()

    def _load_inline_libraries(self):
        for name, dimensions in self._custom_formats().items():
            self._append_library_row(
                self.formats_table, (name, dimensions[0], dimensions[1])
            )
        for name in self._library_names(
            "libraries/paper_types", ["Mat150g", "Mat350g"]
        ):
            self._append_library_row(self.paper_types_table, (name,))

    @staticmethod
    def _append_library_row(table, values):
        row = table.rowCount()
        table.insertRow(row)
        for column, value in enumerate(values):
            item = QTableWidgetItem(str(value))
            if column > 0:
                item.setTextAlignment(Qt.AlignCenter)
            table.setItem(row, column, item)
        table.setRowHeight(row, 30)
        return row

    def _add_format_row(self):
        row = self._append_library_row(self.formats_table, ("NOVO FORMATO", "0", "0"))
        self._resize_library_sections()
        self.formats_table.setCurrentCell(row, 0)
        self.formats_table.editItem(self.formats_table.item(row, 0))

    def _add_paper_type_row(self):
        row = self._append_library_row(self.paper_types_table, ("NOVO PAPEL",))
        self._resize_library_sections()
        self.paper_types_table.setCurrentCell(row, 0)
        self.paper_types_table.editItem(self.paper_types_table.item(row, 0))

    def _remove_library_row(self, table):
        row = table.currentRow()
        if row < 0:
            return
        table.removeRow(row)
        self._resize_library_sections()
        self._save_inline_libraries()

    def _move_library_row(self, table, direction):
        row = table.currentRow()
        target = row + direction
        if row < 0 or target < 0 or target >= table.rowCount():
            return
        table.blockSignals(True)
        for column in range(table.columnCount()):
            current = self._table_text(table, row, column)
            other = self._table_text(table, target, column)
            table.item(row, column).setText(other)
            table.item(target, column).setText(current)
        table.blockSignals(False)
        table.selectRow(target)
        self._save_inline_libraries()

    def _save_inline_libraries(self, *_args):
        if self._loading_libraries:
            return

        formats = {}
        for row in range(self.formats_table.rowCount()):
            name = self._table_text(self.formats_table, row, 0)
            if not name:
                continue
            try:
                width = float(self._table_text(self.formats_table, row, 1).replace(",", "."))
                height = float(self._table_text(self.formats_table, row, 2).replace(",", "."))
            except ValueError:
                continue
            if width > 0 and height > 0:
                formats[name] = [width, height]

        paper_types = [
            self._table_text(self.paper_types_table, row, 0)
            for row in range(self.paper_types_table.rowCount())
            if self._table_text(self.paper_types_table, row, 0)
        ]
        self.settings.setValue("geometry/custom_formats", json.dumps(formats))
        self.settings.setValue("libraries/paper_types", json.dumps(paper_types))
        self.settings.sync()
        self.librariesChanged.emit()

    @staticmethod
    def _table_text(table, row, column):
        item = table.item(row, column)
        return item.text().strip() if item else ""

    def _library_names(self, key, default):
        raw = self.settings.value(key, json.dumps(default))
        try:
            values = json.loads(raw) if isinstance(raw, str) else raw
        except (TypeError, json.JSONDecodeError):
            values = default
        if isinstance(values, dict):
            return [str(name) for name in values]
        if isinstance(values, list):
            return [str(name) for name in values]
        return list(default)

    def _shortcuts_page(self):
        page, layout = self._page("ATALHOS", "")
        search = QLineEdit()
        search.setPlaceholderText("Buscar atalho, comando ou função")
        search.setClearButtonEnabled(True)
        layout.addWidget(search)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        content.setProperty("toolSurface", True)
        rows = QVBoxLayout(content)
        rows.setContentsMargins(0, 0, 8, 0)
        rows.setSpacing(2)
        overrides = {
            "</>": "Acesso rápido nas Configurações para abrir o projeto no VS Code.",
            "CHATGPT": "Acesso rápido nas Configurações para abrir o Codex.",
            "▤": "A documentação agora está incorporada às Configurações.",
            "↻": "Acesso rápido nas Configurações para reiniciar o M87.",
            "—": "Acesso rápido nas Configurações para minimizar o Terminal.",
        }
        records = []
        for item in self._reference_items("atalhos"):
            code = str(item.get("code", ""))
            if code in {"▤", "—"}:
                continue
            title = str(item.get("title", ""))
            description = overrides.get(code, str(item.get("description", "")))
            if code.startswith("⌘"):
                category = "TECLADO"
            elif code in {"ENTER", "↑ / ↓", "ESC"}:
                category = "NAVEGAÇÃO"
            elif code in {"CLIQUE", "ARRASTAR"}:
                category = "INTERAÇÃO"
            else:
                category = "ACESSOS DO APLICATIVO"
            records.append((category, code, title, description))
        for item in self._reference_items("buscas"):
            records.append((
                "BUSCAS E COMANDOS RÁPIDOS",
                str(item.get("code", "")),
                str(item.get("title", "")),
                str(item.get("description", "")),
            ))

        code_counts = {}
        for _category, code, _title, _description in records:
            normalized_code = code.strip().upper()
            if normalized_code:
                code_counts[normalized_code] = code_counts.get(normalized_code, 0) + 1

        self.shortcut_categories = {}
        self.shortcut_rows = []
        category_order = (
            "TECLADO", "NAVEGAÇÃO", "INTERAÇÃO",
            "ACESSOS DO APLICATIVO", "BUSCAS E COMANDOS RÁPIDOS",
        )
        for category in category_order:
            category_records = [record for record in records if record[0] == category]
            if not category_records:
                continue
            category_label = QLabel(category)
            category_label.setObjectName("settingsShortcutCategory")
            rows.addWidget(category_label)
            category_widgets = []
            for _, code, title, description in category_records:
                conflict = code_counts.get(code.strip().upper(), 0) > 1
                widget = self._shortcut_row(
                    code, title, description, conflict=conflict
                )
                searchable = self._search_key(f"{code} {title} {description}")
                self.shortcut_rows.append((widget, category, searchable))
                category_widgets.append(widget)
                rows.addWidget(widget)
            self.shortcut_categories[category] = (category_label, category_widgets)
        rows.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)
        search.textChanged.connect(self._filter_shortcuts)
        return page

    def _shortcut_row(self, code, title, description, *, conflict=False):
        widget = QFrame()
        widget.setObjectName("settingsShortcutRow")
        row = QVBoxLayout(widget)
        row.setContentsMargins(10, 5, 10, 5)
        row.setSpacing(1)
        warning = "   ⚠ CONFLITO" if conflict else ""
        first = QLabel(f"{code}   {title}{warning}")
        first.setObjectName("settingsShortcutTitle")
        if conflict:
            first.setToolTip(
                "Este atalho aparece em mais de um recurso. Verifique o contexto."
            )
        second_text = " ".join(description.split())
        if len(second_text) > 165:
            second_text = second_text[:162].rstrip() + "…"
        second = QLabel(second_text)
        second.setObjectName("settingsShortcutDescription")
        second.setWordWrap(False)
        first.setFixedHeight(17)
        second.setFixedHeight(17)
        row.addWidget(first)
        row.addWidget(second)
        widget.setFixedHeight(48)
        return widget

    def _filter_shortcuts(self, text):
        query = self._search_key(text.strip())
        for widget, _category, searchable in self.shortcut_rows:
            widget.setVisible(not query or query in searchable)
        for _category, (label, widgets) in self.shortcut_categories.items():
            label.setVisible(any(not widget.isHidden() for widget in widgets))

    @staticmethod
    def _search_key(value):
        normalized = unicodedata.normalize("NFKD", str(value).casefold())
        return "".join(
            character for character in normalized
            if not unicodedata.combining(character)
        )

    def _about_page(self):
        from core.config import APP_TITLE, APP_VERSION

        product = self._reference_product()
        commit = self._latest_git_commit()
        page = QWidget()
        page.setProperty("toolSurface", True)
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 12)
        page_layout.setSpacing(6)

        scroll = QScrollArea()
        self.about_scroll = scroll
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        content.setProperty("toolSurface", True)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(42, 26, 42, 18)
        layout.setSpacing(10)

        logo = QLabel()
        logo.setAlignment(Qt.AlignCenter)
        logo_path = ROOT / "assets" / "m87_icon.png"
        if logo_path.exists():
            logo.setPixmap(QPixmap(str(logo_path)).scaled(
                76, 76, Qt.KeepAspectRatio, Qt.SmoothTransformation
            ))
        layout.addWidget(logo)

        name = QLabel(APP_TITLE.upper())
        name.setObjectName("settingsAboutName")
        name.setAlignment(Qt.AlignCenter)
        layout.addWidget(name)

        from ui.tools_dialog import ToolsDialog
        counter = QLabel(
            f"{len(self.terminal.commands)} COMANDOS  ·  "
            f"{len(ToolsDialog.TAB_ORDER)} FERRAMENTAS"
        )
        counter.setObjectName("settingsCounter")
        counter.setAlignment(Qt.AlignCenter)
        layout.addWidget(counter)

        introduction = QLabel(
            "O M87 Terminal é uma aplicação nativa para macOS criada para\n"
            "agilizar tarefas de pré-impressão e produção gráfica. Reúne o\n"
            "terminal de comandos, tratamento de PDFs, geometria, imposição,\n"
            "montagem e ferramentas de conferência em um único ambiente."
        )
        introduction.setObjectName("settingsAboutText")
        introduction.setWordWrap(False)
        introduction.setAlignment(Qt.AlignCenter)
        introduction.setFixedWidth(620)
        introduction.setMinimumHeight(76)
        layout.addWidget(introduction, 0, Qt.AlignHCenter)
        layout.addSpacing(10)

        meta = QLabel(
            f"Versão v{APP_VERSION.lstrip('v')}  ·  "
            f"Criado em {product.get('created', 'data não informada')}\n"
            f"Última revisão registrada em "
            f"{product.get('updated', 'data não informada')}\n"
            "Desenvolvido por Mariane Jacob com Python + PySide6."
        )
        meta.setObjectName("settingsAboutMeta")
        meta.setWordWrap(False)
        meta.setAlignment(Qt.AlignCenter)
        meta.setFixedWidth(620)
        meta.setMinimumHeight(58)
        layout.addWidget(meta, 0, Qt.AlignHCenter)
        diagnostics = QLabel(self._system_info_text())
        diagnostics.setObjectName("settingsAboutMeta")
        diagnostics.setWordWrap(True)
        diagnostics.setTextInteractionFlags(Qt.TextSelectableByMouse)
        diagnostics.setAlignment(Qt.AlignCenter)
        layout.addWidget(diagnostics)
        copy_diagnostics = QPushButton("COPIAR INFORMAÇÕES DO SISTEMA")
        copy_diagnostics.setObjectName("settingsAction")
        copy_diagnostics.clicked.connect(self._copy_system_info)
        layout.addWidget(copy_diagnostics, 0, Qt.AlignHCenter)
        layout.addSpacing(12)

        log_title = QLabel("ÚLTIMO REGISTRO DO GITHUB")
        log_title.setObjectName("settingsCardTitle")
        log_title.setAlignment(Qt.AlignCenter)
        layout.addWidget(log_title)
        self.latest_git_label = QLabel(commit)
        self.latest_git_label.setObjectName("settingsAboutMeta")
        self.latest_git_label.setWordWrap(True)
        self.latest_git_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.latest_git_label)
        self.changelog_panel = QWidget()
        self.changelog_layout = QVBoxLayout(self.changelog_panel)
        self.changelog_layout.setContentsMargins(48, 8, 48, 8)
        self.changelog_layout.setSpacing(2)
        self._rebuild_changelog()
        self.changelog_panel.hide()
        layout.addWidget(self.changelog_panel)
        layout.addStretch()

        scroll.setWidget(content)
        page_layout.addWidget(scroll, 1)

        footer = QHBoxLayout()
        footer.setContentsMargins(0, 0, 14, 0)
        footer.addStretch()
        history_button = QPushButton("CHANGELOG")
        history_button.setObjectName("settingsChangelogButton")
        history_button.setCursor(QCursor(Qt.PointingHandCursor))
        history_button.setFixedWidth(86)
        footer.addWidget(history_button)
        page_layout.addLayout(footer)
        history_button.clicked.connect(
            lambda: self._toggle_changelog(history_button)
        )
        return page

    def _rebuild_changelog(self):
        while self.changelog_layout.count():
            item = self.changelog_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        current_date = None
        for date_text, subject in self._git_entries():
            if date_text != current_date:
                current_date = date_text
                try:
                    parsed = datetime.strptime(date_text, "%d/%m/%Y")
                    date_label_text = parsed.strftime("%d %b %Y").upper()
                except ValueError:
                    date_label_text = date_text
                date_label = QLabel(date_label_text)
                date_label.setObjectName("settingsChangeDate")
                self.changelog_layout.addWidget(date_label)
            entry = QLabel(f"▸ {subject}")
            entry.setObjectName("settingsCommit")
            entry.setWordWrap(True)
            entry.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self.changelog_layout.addWidget(entry)
        if current_date is None:
            unavailable = QLabel("Histórico de alterações não disponível.")
            unavailable.setObjectName("settingsAboutMeta")
            self.changelog_layout.addWidget(unavailable)

    def refresh_git_history(self):
        self.latest_git_label.setText(self._latest_git_commit())
        self._rebuild_changelog()
        if self.changelog_panel.isVisible():
            QTimer.singleShot(
                0,
                lambda: self.about_scroll.verticalScrollBar().setValue(0),
            )

    def _system_info_text(self):
        from core.config import APP_VERSION

        return system_info(ROOT, APP_VERSION)

    def _copy_system_info(self):
        QApplication.clipboard().setText(self._system_info_text())

    def _toggle_changelog(self, button):
        visible = not self.changelog_panel.isVisible()
        if visible:
            self.refresh_git_history()
        self.changelog_panel.setVisible(visible)
        button.setText(
            "FECHAR" if visible else "CHANGELOG"
        )
        if visible:
            QTimer.singleShot(
                0,
                lambda: self.about_scroll.verticalScrollBar().setValue(0),
            )
        else:
            self.about_scroll.verticalScrollBar().setValue(0)

    @staticmethod
    def _reference_items(section_id):
        return reference_items(ROOT, section_id)

    @staticmethod
    def _reference_product():
        return reference_product(ROOT)

    @staticmethod
    def _latest_git_commit():
        return latest_git_commit(ROOT)

    @staticmethod
    def _git_entries():
        return git_entries(ROOT)

    def _custom_formats(self):
        raw = self.settings.value("geometry/custom_formats", "{}")
        try:
            values = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            values = {}
        return values if isinstance(values, dict) else {}

    def _title_press(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def _title_move(self, event):
        if event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_position)

    def _restore_geometry(self):
        if not self.settings.value(
            "general/remember_geometry", True, type=bool
        ):
            return
        geometry = self.settings.value("settings/geometry")
        if geometry:
            self.restoreGeometry(geometry)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), 13, 13)
        self.setMask(QRegion(path.toFillPolygon().toPolygon()))

    def closeEvent(self, event):
        self._save_notes()
        if self.settings.value(
            "general/remember_geometry", True, type=bool
        ):
            self.settings.setValue("settings/geometry", self.saveGeometry())
        super().closeEvent(event)
