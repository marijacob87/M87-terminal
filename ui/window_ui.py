import os
import subprocess
import math
from pathlib import Path

from PySide6.QtCore import QPointF, QSettings, Qt, QTimer
from PySide6.QtGui import QColor, QCursor, QIcon, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QApplication,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.config import APP_MIN_HEIGHT, APP_MIN_WIDTH, APP_TITLE
from core.state import load_window_state
from ui.suggestions import SuggestionsBox
from ui.terminal_input import TerminalInput
from ui.widgets import (
    CommandRow,
    DarkMetallicTitleBar,
    HorizontalResizeGrip,
    SectionLabel,
)


class SettingsIcon(QWidget):
    """Engrenagem com lupa em traços brancos para a barra do Terminal."""

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(QPen(QColor(175, 175, 175, 252), 1.05,
                            Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.setBrush(Qt.NoBrush)

        center = QPointF(11.2, 7.2)
        gear = QPainterPath()
        for index in range(32):
            angle = math.radians(-90 + index * 11.25)
            radius = 5.0 if index % 4 in (0, 1) else 3.9
            point = QPointF(
                center.x() + math.cos(angle) * radius,
                center.y() + math.sin(angle) * radius,
            )
            if index == 0:
                gear.moveTo(point)
            else:
                gear.lineTo(point)
        gear.closeSubpath()
        painter.drawPath(gear)
        painter.drawEllipse(center, 1.6, 1.6)

        lens_center = QPointF(6.6, 10.2)
        painter.drawEllipse(lens_center, 3.1, 3.1)
        painter.drawLine(QPointF(4.4, 12.4), QPointF(2.3, 14.5))


class WindowUiMixin:
    def setup_window(self):
        self.setWindowTitle("M87 TERMINAL")

        project_root = Path(__file__).resolve().parent.parent
        icon_path = project_root / "assets" / "m87_icon.png"

        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAcceptDrops(True)
        self.setMinimumSize(APP_MIN_WIDTH, APP_MIN_HEIGHT)

        remember = QSettings("M87Tools", "M87Terminal").value(
            "general/remember_geometry", True, type=bool
        )
        state = load_window_state() if remember else {
            "width": APP_MIN_WIDTH, "height": APP_MIN_HEIGHT,
        }
        width = max(APP_MIN_WIDTH, state["width"])
        height = max(APP_MIN_HEIGHT, state["height"])

        self.normal_height = height
        self.resize(width, height)
        screen = QApplication.primaryScreen()

        if screen:
            self.locked_window_position = screen.availableGeometry().topLeft()
            self.move(self.locked_window_position)
        else:
            self.locked_window_position = self.pos()

    def build_ui(self):
        central = QWidget()
        central.setObjectName("terminalBox")
        central.setAcceptDrops(False)
        central.setAutoFillBackground(False)

        self.main_layout = QVBoxLayout(central)
        self.main_layout.setContentsMargins(0, 0, 0, 4)
        self.main_layout.setSpacing(0)
        self.main_layout.setAlignment(Qt.AlignTop)

        self.build_title()
        self.build_status()
        self.build_commands()
        self.build_input()
        self.build_resize_grip()

        self.setCentralWidget(central)
        QTimer.singleShot(100, self.input.setFocus)

    def build_title(self):
        self.title = QLabel(APP_TITLE.upper())
        self.title.setObjectName("title")
        self.title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        self.settings_button = SettingsIcon()
        self.settings_button.setObjectName("settingsButton")
        self.settings_button.setCursor(QCursor(Qt.PointingHandCursor))
        self.settings_button.setToolTip("Configurações  ⌘,")
        self.settings_button.setFixedSize(18, 18)
        self.settings_button.mousePressEvent = lambda event: self.open_settings()

        self.title_container = DarkMetallicTitleBar()
        title_layout = QHBoxLayout(self.title_container)
        title_layout.setContentsMargins(14, 0, 9, 0)
        title_layout.setSpacing(0)
        title_layout.addWidget(self.title)
        title_layout.addStretch()
        title_layout.addWidget(self.settings_button)

        self.main_layout.addWidget(self.title_container)

        # Todo o conteúdo abaixo da barra mantém a margem compacta original.
        self.content_container = QWidget()
        self.content_container.setObjectName("contentContainer")
        self.content_layout = QVBoxLayout(self.content_container)
        self.content_layout.setContentsMargins(14, 6, 14, 4)
        self.content_layout.setSpacing(0)
        self.content_layout.setAlignment(Qt.AlignTop)
        self.main_layout.addWidget(self.content_container)

    def open_settings_section(self, section_id):
        self.open_settings()
        self.settings_dialog.show_section(section_id)

    def open_settings(self):
        from ui.settings_dialog import SettingsDialog

        dialog = getattr(self, "settings_dialog", None)
        if dialog is None:
            dialog = SettingsDialog(self)
            dialog.librariesChanged.connect(self._refresh_shared_libraries)
            self.settings_dialog = dialog
        dialog.navigation.setCurrentRow(dialog._key_to_row["general"])
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _refresh_shared_libraries(self):
        tools = getattr(self, "tools_dialog", None)
        if tools is None:
            return
        try:
            geometry = tools._pages.get("GEO")
            if geometry and hasattr(geometry, "_reload_preset_combos"):
                geometry._reload_preset_combos()
            imposition = tools._pages.get("IMP")
            if imposition and hasattr(imposition, "refresh_paper_library"):
                imposition.refresh_paper_library()
        except RuntimeError:
            pass

    def open_project_in_vscode(self):
        project_path = os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))
        )

        try:
            subprocess.Popen(
                ["open", "-a", "Visual Studio Code", project_path]
            )
        except Exception as error:
            print(f"ERRO AO ABRIR VS CODE: {error}")

    def open_codex(self):
        try:
            subprocess.Popen(
                ["open", "-b", "com.openai.codex"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as error:
            print(f"ERRO AO ABRIR CODEX: {error}")

    def build_status(self):
        # O status pertence ao cabeçalho e não participa da distribuição
        # vertical do restante da janela. Assim ele permanece colado ao
        # título mesmo quando a altura do app é aumentada.
        self.status_container = QWidget()
        self.status_container.setObjectName("statusContainer")
        self.status_container.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Fixed,
        )

        status_layout = QVBoxLayout(self.status_container)
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.setSpacing(0)

        self.status_primary = QLabel("")
        self.status_primary.setObjectName("status")
        self.status_primary.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Fixed,
        )

        self.status_secondary = QLabel("")
        self.status_secondary.setObjectName("status")
        self.status_secondary.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Fixed,
        )

        self.status_network = QLabel("")
        self.status_network.setObjectName("status")
        self.status_network.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Fixed,
        )
        for label in (self.status_primary, self.status_network):
            label.setTextInteractionFlags(Qt.LinksAccessibleByMouse)
            label.setOpenExternalLinks(False)
            label.linkActivated.connect(self.mount_network_from_status)

        # Cada linha usa a mesma altura-base dos comandos e do prompt.
        # Isso cria um ritmo vertical regular em toda a janela.
        self.status_primary.setFixedHeight(18)
        self.status_secondary.setFixedHeight(18)
        self.status_network.setFixedHeight(18)
        self.status_primary.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.status_secondary.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.status_network.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        # Compatibilidade com trechos antigos que ainda consultem self.status.
        self.status = self.status_primary

        self.divider_1 = QLabel("────────────────────────────────────")
        self.divider_1.setObjectName("divider")
        self.divider_1.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Fixed,
        )
        self.divider_1.setFixedHeight(18)
        self.divider_1.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        status_layout.addWidget(self.status_primary)
        status_layout.addWidget(self.status_secondary)
        status_layout.addWidget(self.status_network)
        status_layout.addWidget(self.divider_1)
        self.content_layout.addWidget(self.status_container)

    def build_commands(self):
        self.commands_container = QWidget()
        self.commands_container.setObjectName("commandsContainer")
        self.commands_container.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Fixed,
        )

        self.commands_grid = QGridLayout(self.commands_container)
        self.commands_grid.setContentsMargins(0, 0, 0, 0)
        self.commands_grid.setHorizontalSpacing(6)
        self.commands_grid.setVerticalSpacing(0)

        self.command_sections = {}
        self.section_labels = {}
        self.all_command_rows = {}
        all_sections = []
        raw_hidden = QSettings("M87Tools", "M87Terminal").value(
            "terminal/hidden_commands", []
        )
        from core.command_preferences import normalize_code_list

        hidden_codes = set(normalize_code_list(raw_hidden))

        for item in self.commands:
            code = item.get("code", "").upper()
            label = item.get("label", code)
            section = item.get("section", "Comandos")
            if section not in all_sections:
                all_sections.append(section)

            if not code:
                continue

            row = CommandRow(label, code, self.execute_command)
            self.rows[code] = row
            self.all_command_rows[code] = (section, row)
            if code in hidden_codes:
                row.hide()
                continue
            self.command_widgets.append(row)
            self.command_sections.setdefault(section, []).append(row)

        for section in all_sections:
            self.section_labels[section] = SectionLabel(section)

        self.content_layout.addWidget(self.commands_container)
        # Separação real entre a última ferramenta e o divisor do prompt.
        # Evita que o traço atravesse "MP MUPI Print" por arredondamento das
        # métricas da fonte no macOS.
        self.content_layout.addSpacing(8)

        self.divider_2 = QLabel("────────────────────────────────────")
        self.divider_2.setObjectName("divider")
        self.divider_2.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.divider_2.setFixedHeight(18)
        self.divider_2.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.content_layout.addWidget(self.divider_2)

    def apply_command_visibility(self, visible_codes):
        visible = {str(code).upper() for code in visible_codes}
        all_codes = set(self.all_command_rows)
        hidden = sorted(all_codes - visible)
        settings = QSettings("M87Tools", "M87Terminal")
        settings.setValue("terminal/hidden_commands", hidden)
        settings.setValue(
            "terminal/command_order",
            [
                str(item.get("code", "")).strip().upper()
                for item in self.commands
                if str(item.get("code", "")).strip()
            ],
        )
        settings.sync()

        self.command_widgets = []
        self.command_sections = {}
        for item in self.commands:
            code = item.get("code", "").upper()
            entry = self.all_command_rows.get(code)
            if not entry:
                continue
            section, row = entry
            row.hide()
            if code in visible:
                self.command_widgets.append(row)
                self.command_sections.setdefault(section, []).append(row)

        self.current_columns = None
        self.rebuild_command_grid()
        for row in self.command_widgets:
            row.show()
        self.ajustar_altura_ao_conteudo()

    def build_input(self):
        self.input = TerminalInput("m87@ -")
        self.input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.input.setFixedHeight(18)
        self.input.setObjectName("terminalInput")
        self.input.returnPressed.connect(self.execute_from_input)
        self.input.textChanged.connect(self.update_suggestions)
        self.input.textChanged.connect(self.clear_calculator_result)
        self.input.arrowUpPressed.connect(self.move_suggestion_up)
        self.input.arrowDownPressed.connect(self.move_suggestion_down)
        self.input.escapePressed.connect(self.clear_context)
        self.input.calculatorEntryReset.connect(self.reset_calculator_session)

        self.calculator_result_label = QLabel("")
        self.calculator_result_label.setObjectName("calculatorResultLabel")
        self.calculator_result_label.setWordWrap(False)
        self.calculator_result_label.hide()

        self.session_result_label = QLabel("")
        self.session_result_label.setObjectName("activeFileLabel")
        self.session_result_label.setWordWrap(True)
        self.session_result_label.hide()

        self.active_file_label = QLabel("")
        self.active_file_label.setObjectName("activeFileLabel")
        self.active_file_label.setWordWrap(True)
        self.active_file_label.hide()

        self.suggestions = SuggestionsBox()
        self.suggestions.clear()

        self.content_layout.addWidget(self.input)
        self.content_layout.addWidget(self.calculator_result_label)
        self.content_layout.addWidget(self.session_result_label)
        self.content_layout.addWidget(self.active_file_label)
        self.content_layout.addWidget(self.suggestions)


    def clear_calculator_result(self, _text=None):
        if hasattr(self, "calculator_result_label"):
            self.calculator_result_label.clear()
            self.calculator_result_label.hide()

    def reset_calculator_session(self):
        self.calculator_repeat_operation = None
        self.clear_calculator_result()

    def build_resize_grip(self):
        # O redimensionador fica sobreposto no canto inferior direito.
        # Assim não ocupa uma linha própria nem alonga a janela em repouso.
        self.size_grip = HorizontalResizeGrip(self, self.centralWidget())
        self.size_grip.setObjectName("sizeGrip")
        self.size_grip.raise_()
