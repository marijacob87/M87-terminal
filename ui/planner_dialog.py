from __future__ import annotations

import calendar as calendar_module
from datetime import date, timedelta

from PySide6.QtCore import QDate, QEvent, QMimeData, QPoint, QSettings, Qt, QTimer
from PySide6.QtGui import (
    QColor, QCursor, QDrag, QFont, QPainter, QPen, QTextCharFormat,
    QTextOption, QKeySequence, QShortcut,
)
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDateEdit, QDialog, QFrame, QGridLayout,
    QHBoxLayout, QLabel, QLineEdit, QMenu, QMessageBox, QPushButton, QScrollArea,
    QSizePolicy, QTextEdit, QVBoxLayout, QWidget, QListWidget,
    QStackedLayout,
)

from core.planner import (
    DAY_NAMES,
    PlannerStore,
    empty_task,
    task_has_content,
    week_start,
)
from ui.widgets import DarkMetallicTitleBar


TAG_COLORS = {
    "Arte": "#ffc400",
    "Duplo": "#53c5ae",
    "GTO": "#e42c8d",
    "SM": "#049ddd",
    "Konica": "#806bb4",
    "Pessoal": "#f5f5f5",
}

MONTH_NAMES = (
    "JANEIRO", "FEVEREIRO", "MARÇO", "ABRIL", "MAIO", "JUNHO",
    "JULHO", "AGOSTO", "SETEMBRO", "OUTUBRO", "NOVEMBRO", "DEZEMBRO",
)

BASE_TASK_HEIGHT = 28
APPROVALS_KEY = "APROVACAO"


class InkCanvas(QWidget):
    def __init__(self, strokes, changed, parent=None):
        super().__init__(parent)
        self.strokes = strokes
        self.changed = changed
        self.pen_enabled = True
        self.eraser = False
        self.color = "#FFC400"
        self.pen_width = 2
        self._current = None
        self.setMinimumHeight(0)
        self.setCursor(Qt.CrossCursor)

    def mousePressEvent(self, event):
        if not self.pen_enabled or event.button() != Qt.LeftButton:
            return super().mousePressEvent(event)
        point = event.position()
        if self.eraser:
            self.strokes[:] = [stroke for stroke in self.strokes if not self._near(stroke, point)]
            self.changed()
            self.update()
            return
        self._current = {"color": self.color, "width": self.pen_width, "points": [[point.x(), point.y()]]}
        self.strokes.append(self._current)
        self.update()

    def mouseMoveEvent(self, event):
        if self._current is not None:
            point = event.position()
            self._current["points"].append([point.x(), point.y()])
            self.update()

    def mouseReleaseEvent(self, event):
        if self._current is not None:
            self._current = None
            self.changed()

    @staticmethod
    def _near(stroke, point):
        return any((x - point.x()) ** 2 + (y - point.y()) ** 2 < 500 for x, y in stroke.get("points", []))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#0b0b0b"))
        painter.setPen(QPen(QColor("#3a3a3a"), 1))
        for y in range(28, self.height(), 25):
            painter.drawLine(0, y, self.width(), y)
        painter.setRenderHint(QPainter.Antialiasing)
        for stroke in self.strokes:
            points = stroke.get("points", [])
            if len(points) < 2:
                continue
            painter.setPen(QPen(QColor(stroke.get("color", "#FFC400")), stroke.get("width", 2), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            for first, second in zip(points, points[1:]):
                painter.drawLine(QPoint(*map(int, first)), QPoint(*map(int, second)))


class DaySection(QFrame):
    def __init__(self, day_name, dialog):
        super().__init__()
        self.day_name = day_name
        self.dialog = dialog
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().text() == "m87-planner-task":
            event.acceptProposedAction()


class ApprovalDropArea(QScrollArea):
    def __init__(self, dialog, parent=None):
        super().__init__(parent)
        self.dialog = dialog
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().text() == "m87-planner-task":
            event.acceptProposedAction()

    def dropEvent(self, event):
        self._drop_task(event)

    def viewportEvent(self, event):
        if event.type() in (QEvent.DragEnter, QEvent.DragMove):
            if event.mimeData().text() == "m87-planner-task":
                event.acceptProposedAction()
                return True
        elif event.type() == QEvent.Drop:
            self._drop_task(event)
            return True
        return super().viewportEvent(event)

    def _drop_task(self, event):
        row = getattr(self.dialog, "dragged_row", None)
        if row is not None:
            rows = self.widget().findChildren(PlannerTaskRow)
            target_index = sum(
                child.mapTo(self.viewport(), child.rect().center()).y()
                < event.position().y()
                for child in rows
            )
            self.dialog.move_task_to_approvals(row, target_index)
            self.dialog.dragged_row = None
            event.acceptProposedAction()


class DayDropArea(QScrollArea):
    def __init__(self, dialog, day_name, parent=None):
        super().__init__(parent)
        self.dialog = dialog
        self.day_name = day_name
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.drop_indicator = QFrame(self.viewport())
        self.drop_indicator.setStyleSheet("background:#ffc400; border:0;")
        self.drop_indicator.setFixedHeight(2)
        self.drop_indicator.hide()

    def dragEnterEvent(self, event):
        if event.mimeData().text() == "m87-planner-task":
            self._show_indicator(event)
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().text() == "m87-planner-task":
            self._show_indicator(event)
            event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self.drop_indicator.hide()

    def dropEvent(self, event):
        self._drop_task(event)

    def viewportEvent(self, event):
        if event.type() in (QEvent.DragEnter, QEvent.DragMove):
            if event.mimeData().text() == "m87-planner-task":
                self._show_indicator(event)
                event.acceptProposedAction()
                return True
        elif event.type() == QEvent.DragLeave:
            self.drop_indicator.hide()
            return True
        elif event.type() == QEvent.Drop:
            self._drop_task(event)
            return True
        return super().viewportEvent(event)

    def _show_indicator(self, event):
        rows = self.widget().findChildren(PlannerTaskRow)
        target_y = event.position().y()
        row_tops = [
            child.mapTo(self.viewport(), QPoint(0, 0)).y()
            for child in rows
        ]
        row_centers = [
            child.mapTo(self.viewport(), child.rect().center()).y()
            for child in rows
        ]
        index = next(
            (position for position, center in enumerate(row_centers) if target_y < center),
            len(rows),
        )
        if index < len(row_tops):
            line_y = row_tops[index]
        elif rows:
            last = rows[-1]
            line_y = last.mapTo(self.viewport(), QPoint(0, last.height())).y()
        else:
            line_y = 2
        self.drop_indicator.setGeometry(22, max(0, line_y - 1), max(1, self.viewport().width() - 29), 2)
        self.drop_indicator.show()
        self.drop_indicator.raise_()

    def _drop_task(self, event):
        self.drop_indicator.hide()
        row = getattr(self.dialog, "dragged_row", None)
        if row is not None:
            rows = self.widget().findChildren(PlannerTaskRow)
            target_index = sum(
                child.mapTo(self.viewport(), child.rect().center()).y()
                < event.position().y()
                for child in rows
            )
            self.dialog.move_task_to_day(row, self.day_name, target_index)
            self.dialog.dragged_row = None
            event.acceptProposedAction()

class TaskText(QTextEdit):
    def __init__(self, edit_task, text, client="", parent=None):
        super().__init__(parent)
        self.edit_task = edit_task
        self.setObjectName("plannerTaskText")
        if client:
            cursor = self.textCursor()
            client_format = QTextCharFormat()
            client_format.setFontWeight(QFont.Bold)
            cursor.insertText(client, client_format)
            if text:
                work_format = QTextCharFormat()
                work_format.setFontWeight(QFont.Light)
                cursor.insertText("\u2009-\u2009" + text, work_format)
        else:
            # A tarefa é conteúdo de texto simples: usar setPlainText preserva
            # cada quebra de linha ao recriar a linha depois de um arraste.
            self.setPlainText(text)
        self.setReadOnly(True)
        self.setAcceptDrops(False)
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.row_widget = None

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.row_widget is not None:
            self.row_widget._resize_editor()


class EmptyTaskLine(QLabel):
    """Linha vazia leve: abre o editor ao clicar, sem criar um QTextEdit."""

    def __init__(self, edit_task, parent=None):
        super().__init__(parent)
        self.edit_task = edit_task
        self.setObjectName("plannerEmptyTask")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(BASE_TASK_HEIGHT)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)


class CalendarDayLabel(QLabel):
    """Número de dia do mini-calendário que abre a semana correspondente."""

    def __init__(self, value, selected_date, activate_week, parent=None):
        super().__init__(value, parent)
        self.selected_date = selected_date
        self.activate_week = activate_week
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Abrir esta semana")

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.activate_week(self.selected_date)
            event.accept()
            return
        super().mouseReleaseEvent(event)


class PlannerResizeHandle(QWidget):
    """Área de redimensionamento confiável para a janela sem moldura."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._start_position = None
        self._start_size = None
        self.setCursor(Qt.SizeFDiagCursor)
        self.setFixedSize(24, 24)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._start_position = event.globalPosition().toPoint()
            self._start_size = self.window().size()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._start_position is None or not event.buttons() & Qt.LeftButton:
            super().mouseMoveEvent(event)
            return
        delta = event.globalPosition().toPoint() - self._start_position
        dialog = self.window()
        dialog.resize(
            max(dialog.minimumWidth(), self._start_size.width() + delta.x()),
            max(dialog.minimumHeight(), self._start_size.height() + delta.y()),
        )
        event.accept()

    def mouseReleaseEvent(self, event):
        self._start_position = None
        self._start_size = None
        event.accept()


class TaskEditorDialog(QDialog):
    def __init__(self, task, tags, parent=None, schedule_mode=False):
        super().__init__(parent)
        self.task = task
        self.schedule_mode = schedule_mode
        self.selected_tag = task.get("tag", "")
        self.setWindowTitle("Tarefa")
        self.setModal(True)
        self.setMinimumWidth(380)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        title = QLabel("TAREFA")
        title.setObjectName("taskEditorTitle")
        client_label = QLabel("CLIENTE")
        client_label.setObjectName("taskEditorFieldLabel")
        self.client = QLineEdit(task.get("client", ""))
        self.client.setObjectName("taskEditorClient")
        self.client.setPlaceholderText("Nome do cliente")
        self.client.installEventFilter(self)
        work_label = QLabel("TRABALHO")
        work_label.setObjectName("taskEditorFieldLabel")
        self.editor = QTextEdit()
        self.editor.setObjectName("taskEditorWork")
        self.editor.setPlainText(task.get("text", ""))
        self.editor.setFixedHeight(65)
        self.editor.setAcceptRichText(False)
        self.editor.installEventFilter(self)
        observations_label = QLabel("OBSERVAÇÕES")
        observations_label.setObjectName("taskEditorObservationsLabel")
        self.observations = QTextEdit()
        self.observations.setObjectName("taskEditorObservations")
        self.observations.setPlainText(task.get("observations", ""))
        self.observations.setFixedHeight(34)
        self.observations.setAcceptRichText(False)
        self.observations.installEventFilter(self)
        self.schedule_date = None
        self.recurrence = None
        if schedule_mode:
            schedule_label = QLabel("DATA E RECORRÊNCIA")
            schedule_label.setObjectName("taskEditorFieldLabel")
            schedule_controls = QHBoxLayout()
            self.schedule_date = QDateEdit(QDate.currentDate())
            self.schedule_date.setCalendarPopup(True)
            self.schedule_date.setDisplayFormat("dd/MM/yyyy")
            self.recurrence = QComboBox()
            self.recurrence.addItem("NÃO REPETIR", "once")
            self.recurrence.addItem("SEMANAL", "weekly")
            self.recurrence.addItem("MENSAL", "monthly")
            self.recurrence.addItem("ÚLTIMO DIA ÚTIL DO MÊS", "monthly_last_day")
            self.recurrence.addItem("ANUAL", "yearly")
        dots = QGridLayout()
        dots.setHorizontalSpacing(10)
        dots.setVerticalSpacing(8)
        dots.setColumnStretch(0, 1)
        dots.setColumnStretch(1, 1)
        self.tag_buttons = {}
        for index, tag in enumerate(tag for tag in tags if tag != "Financeiro"):
            button = QPushButton(tag.upper())
            button.setCheckable(True)
            button.setChecked(tag == self.selected_tag)
            button.setMinimumHeight(28)
            button.setStyleSheet(
                "QPushButton { color:#9d9d9d; background:#151515; "
                f"border:1px solid #363636; border-left:4px solid {TAG_COLORS.get(tag, '#888')}; "
                "border-radius:4px; padding:4px 8px; text-align:left; }"
                f"QPushButton:checked {{ color:#eeeeee; border-color:{TAG_COLORS.get(tag, '#888')}; "
                f"border-left:4px solid {TAG_COLORS.get(tag, '#888')}; }}"
            )
            button.clicked.connect(lambda checked=False, value=tag: self._select_tag(value))
            self.tag_buttons[tag] = button
            row, column = divmod(index, 2)
            dots.addWidget(button, row, column)
        buttons = QHBoxLayout()
        self.done_button = QPushButton("CONCLUÍDO")
        self.done_button.setObjectName("taskEditorDone")
        self._mark_done = task.get("done", False)
        self.done_button.clicked.connect(self._complete_task)
        cancel = QPushButton("CANCELAR")
        save = QPushButton("OK")
        cancel.clicked.connect(self.reject)
        save.clicked.connect(self.accept)
        buttons.addWidget(self.done_button)
        buttons.addStretch(); buttons.addWidget(cancel); buttons.addWidget(save)
        layout.addWidget(title)
        layout.addWidget(client_label)
        layout.addWidget(self.client)
        layout.addWidget(work_label)
        layout.addWidget(self.editor)
        layout.addWidget(observations_label)
        layout.addWidget(self.observations)
        if schedule_mode:
            layout.addWidget(schedule_label)
            schedule_controls.addWidget(self.schedule_date, 1)
            schedule_controls.addWidget(self.recurrence, 1)
            layout.addLayout(schedule_controls)
        layout.addLayout(dots)
        layout.addLayout(buttons)
        self.setStyleSheet("""
            TaskEditorDialog { background:#111; border:1px solid #4a4a4a; border-radius:7px; }
            QLabel { color:#bdbdbd; font-family:'JetBrains Mono'; font-size:10px; font-weight:700; }
            QLabel#taskEditorTitle { color:#ffc400; font-size:12px; }
            QLabel#taskEditorFieldLabel { color:#8f8f8f; font-size:9px; font-weight:300; letter-spacing:1px; }
            QLabel#taskEditorObservationsLabel { color:#8f8f8f; font-size:9px; font-weight:300; letter-spacing:1px; }
            QLineEdit#taskEditorClient { color:#c7c7c7; font-weight:700; background:#090909; border:1px solid #303030; border-radius:4px; padding:6px; }
            QTextEdit { color:#c7c7c7; background:#090909; border:1px solid #303030; border-radius:4px; padding:6px; }
            QTextEdit#taskEditorWork { color:#c7c7c7; }
            QTextEdit#taskEditorObservations { color:#9d9d9d; }
            QDateEdit, QComboBox { color:#bdbdbd; background:#090909; border:1px solid #303030; border-radius:4px; padding:5px; }
            QPushButton { color:#bdbdbd; background:#1b1b1b; border:1px solid #373737; border-radius:4px; padding:5px 9px; font-family:'JetBrains Mono'; font-size:10px; }
            QPushButton#taskEditorDone:checked { color:#d8d8d8; border-color:#777; background:#242424; }
        """)

    def _select_tag(self, tag):
        self.selected_tag = tag
        for value, button in self.tag_buttons.items():
            button.setChecked(value == tag)

    def accept(self):
        self.task["client"] = self.client.text().strip()
        self.task["text"] = self.editor.toPlainText()
        self.task["tag"] = self.selected_tag
        self.task["observations"] = self.observations.toPlainText()
        self.task["done"] = self._mark_done
        self.task.pop("show_checkbox", None)
        super().accept()

    def scheduled_date(self):
        return self.schedule_date.date().toPython() if self.schedule_date else None

    def scheduled_recurrence(self):
        return self.recurrence.currentData() if self.recurrence else "once"

    def _complete_task(self):
        self._mark_done = True
        self.accept()

    def keyPressEvent(self, event):
        if (
            event.key() in (Qt.Key_Return, Qt.Key_Enter)
            and not event.modifiers() & Qt.ShiftModifier
        ):
            self.accept()
            return
        super().keyPressEvent(event)

    def eventFilter(self, watched, event):
        if (
            watched in (self.client, self.editor, self.observations)
            and event.type() == QEvent.KeyPress
            and event.key() in (Qt.Key_Return, Qt.Key_Enter)
            and not event.modifiers() & Qt.ShiftModifier
        ):
            self.accept()
            return True
        return super().eventFilter(watched, event)


class PlannerSearchDialog(QDialog):
    """Busca leve no histórico local, sem alterar o planner."""

    def __init__(self, planner, parent=None):
        super().__init__(parent)
        self.planner = planner
        self.matches = []
        self.setWindowTitle("Buscar tarefas")
        self.setModal(True)
        self.setMinimumWidth(440)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        title = QLabel("BUSCAR TAREFAS")
        title.setObjectName("plannerSearchTitle")
        self.query = QLineEdit()
        self.query.setPlaceholderText("Cliente, trabalho ou categoria")
        self.query.textChanged.connect(self._refresh)
        self.results = QListWidget()
        self.results.itemActivated.connect(self._open_selected)
        close = QPushButton("FECHAR")
        close.clicked.connect(self.reject)
        layout.addWidget(title)
        layout.addWidget(self.query)
        layout.addWidget(self.results, 1)
        layout.addWidget(close, alignment=Qt.AlignRight)
        self.setStyleSheet("""
            PlannerSearchDialog { background:#111; border:1px solid #4a4a4a; border-radius:7px; }
            QLabel#plannerSearchTitle { color:#ffc400; font-family:'JetBrains Mono'; font-size:12px; font-weight:700; }
            QLineEdit, QListWidget { color:#c7c7c7; background:#090909; border:1px solid #303030; border-radius:4px; padding:6px; font-family:'JetBrains Mono'; }
            QListWidget::item { padding:6px; border-bottom:1px solid #252525; }
            QListWidget::item:selected { color:#ffc400; background:#1a1a1a; }
            QPushButton { color:#bdbdbd; background:#1b1b1b; border:1px solid #373737; border-radius:4px; padding:5px 9px; font-family:'JetBrains Mono'; font-size:10px; }
        """)
        self.query.setFocus()

    def _refresh(self, value):
        needle = value.strip().casefold()
        self.results.clear()
        self.matches = []
        if not needle:
            return

        def add(task, when, area):
            searchable = " ".join((
                task.get("client", ""), task.get("text", ""), task.get("tag", ""),
            )).casefold()
            if needle not in searchable:
                return
            label = " - ".join(part for part in (task.get("client", ""), task.get("text", "")) if part) or "(sem descrição)"
            self.matches.append((when, area))
            self.results.addItem(f"{when:%d/%m/%Y} · {area} · {label}")

        for key, week in self.planner.store.data.get("weeks", {}).items():
            try:
                start = date.fromisoformat(key)
            except ValueError:
                continue
            for offset, day_name in enumerate(DAY_NAMES):
                for task in week.get("days", {}).get(day_name, []):
                    if task_has_content(task):
                        add(task, start + timedelta(days=offset), day_name)
        for item in self.planner.store.data.get("scheduled", []):
            task = item.get("task", {})
            try:
                scheduled_for = date.fromisoformat(item.get("date", ""))
            except ValueError:
                continue
            if task_has_content(task):
                suffix = {"once": "AGENDADA", "weekly": "SEMANAL", "monthly": "MENSAL", "monthly_last_day": "ÚLTIMO DIA ÚTIL", "yearly": "ANUAL"}.get(item.get("recurrence"), "AGENDADA")
                add(task, scheduled_for, suffix)

    def _open_selected(self):
        index = self.results.currentRow()
        if not 0 <= index < len(self.matches):
            return
        selected_date, _area = self.matches[index]
        self.planner.current_start = week_start(selected_date)
        self.planner._load_week()
        self.accept()


class PlannerTaskRow(QWidget):
    def __init__(
        self,
        task,
        tags,
        changed,
        day_name=None,
        inline_edit=False,
        task_index=None,
        parent=None,
    ):
        super().__init__(parent)
        self.task = task
        self.changed = changed
        self.day_name = day_name
        self.inline_edit = inline_edit
        self.task_index = task_index
        self._drag_start = None
        self.priority_button = None
        self.delete_button = None
        self.next_day_button = None
        self.approval_age = None
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMouseTracking(True)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 0, 5, 0)
        layout.setSpacing(5)
        has_content = bool(
            task.get("client", "").strip()
            or task.get("text", "").strip()
        )
        self.has_content = has_content
        has_checkbox = inline_edit or has_content
        self.check = None
        if has_checkbox:
            self.check = QCheckBox()
            self.check.setChecked(task.get("done", False))
            if not inline_edit:
                self.check.setFixedSize(12, BASE_TASK_HEIGHT)
        if inline_edit:
            self.text = QLineEdit(task.get("text", ""))
            self.text.setPlaceholderText(" ")
        elif has_content:
            self.text = TaskText(
                self._edit_task,
                task.get("text", ""),
                task.get("client", ""),
            )
            self.text.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self.text.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self.text.setSizeAdjustPolicy(QTextEdit.AdjustToContents)
            self.text.setWordWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
            self.text.document().setDocumentMargin(5)
            self.text.row_widget = self
        else:
            self.text = EmptyTaskLine(self._edit_task)
        if not inline_edit:
            self.text.setCursor(Qt.OpenHandCursor)
        self.text.installEventFilter(self)
        if isinstance(self.text, TaskText):
            self.text.viewport().setCursor(Qt.OpenHandCursor)
            self.text.viewport().installEventFilter(self)
        if self.check is not None:
            alignment = Qt.AlignTop if not inline_edit else Qt.AlignVCenter
            layout.addWidget(self.check, 0, alignment)
            layout.addSpacing(4)
        layout.addWidget(self.text, 1)
        if not inline_edit and has_content:
            if self.day_name == APPROVALS_KEY:
                self.approval_age = QLabel(self._approval_age_text())
                self.approval_age.setObjectName("plannerApprovalAge")
                layout.addWidget(self.approval_age, 0, Qt.AlignTop)
            actions = QWidget()
            actions_layout = QVBoxLayout(actions)
            actions_layout.setContentsMargins(0, 0, 0, 0)
            actions_layout.setSpacing(0)
            self.priority_button = QPushButton("★")
            self.priority_button.setObjectName("plannerPriorityTask")
            self.priority_button.setToolTip("Marcar como prioridade")
            self.priority_button.setFixedSize(13, 9)
            self.priority_button.clicked.connect(self._toggle_priority)
            actions_layout.addWidget(self.priority_button)
            self.delete_button = QPushButton("×")
            self.delete_button.setObjectName("plannerDeleteTask")
            self.delete_button.setToolTip("Excluir tarefa")
            self.delete_button.setFixedSize(13, 9)
            self.delete_button.clicked.connect(self._delete_task)
            actions_layout.addWidget(self.delete_button)
            if self.day_name in DAY_NAMES:
                self.next_day_button = QPushButton("→")
                self.next_day_button.setObjectName("plannerNextDay")
                destination = "próxima segunda-feira" if self.day_name == "SEX" else "próximo dia"
                self.next_day_button.setToolTip(f"Mover para o {destination}")
                self.next_day_button.setFixedSize(13, 9)
                self.next_day_button.clicked.connect(self._move_to_next_day)
                actions_layout.addWidget(self.next_day_button)
            layout.addWidget(actions, 0, Qt.AlignTop)
            self._set_action_buttons_visible(False)
        if self.check is not None:
            self.check.toggled.connect(self._update)
        if inline_edit:
            self.text.editingFinished.connect(self._update)
        self._resize_editor()
        self._apply_done_style()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.inline_edit or not self.has_content:
            return
        painter = QPainter(self)
        painter.setPen(QPen(QColor("#292929"), 1))
        painter.drawLine(
            self.text.geometry().left(),
            self.height() - 1,
            self.width() - 5,
            self.height() - 1,
        )

    def enterEvent(self, event):
        self._set_action_buttons_visible(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._set_action_buttons_visible(False)
        super().leaveEvent(event)

    def _set_action_buttons_visible(self, visible):
        for button in (self.priority_button, self.delete_button, self.next_day_button):
            if button is None:
                continue
            if button is self.priority_button and self.task.get("priority", False):
                color = "#ffc400"
            else:
                color = "#8a8a8a" if visible else "transparent"
            button.setStyleSheet(
                "QPushButton { color:" + color + "; background:transparent; "
                "border:0; padding:0; font-size:9px; font-weight:300; }"
                "QPushButton:hover { color:#c0c0c0; }"
            )

    def eventFilter(self, watched, event):
        if watched in (self.text, getattr(self.text, "viewport", lambda: None)()) and not self.inline_edit:
            if event.type() == QEvent.MouseButtonDblClick:
                self._drag_start = None
                self._edit_task()
                return True
            if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                self._drag_start = event.position().toPoint()
                return True
            if (
                event.type() == QEvent.MouseMove
                and event.buttons() & Qt.LeftButton
                and self._drag_start is not None
                and (event.position().toPoint() - self._drag_start).manhattanLength()
                >= QApplication.startDragDistance()
            ):
                self._start_drag()
                return True
            if event.type() == QEvent.MouseButtonRelease:
                self._drag_start = None
                return True
        return super().eventFilter(watched, event)

    def _start_drag(self):
        if not self.day_name:
            return
        dialog = self.window()
        dialog.dragged_row = self
        drag = QDrag(self)
        mime = QMimeData()
        mime.setText("m87-planner-task")
        drag.setMimeData(mime)
        try:
            drag.exec(Qt.MoveAction)
        finally:
            if getattr(dialog, "dragged_row", None) is self:
                dialog.dragged_row = None
            self._drag_start = None

    def _update(self):
        if self.inline_edit:
            self.task["text"] = self.text.text()
        self.task.update(done=self.check.isChecked() if self.check else False)
        self._resize_editor()
        self._apply_done_style()
        self.changed()

    def _resize_editor(self):
        if self.inline_edit or not isinstance(self.text, TaskText):
            return
        if getattr(self, "_resizing_editor", False):
            return
        self._resizing_editor = True
        self.text.document().setTextWidth(self.text.viewport().width())
        document_height = self.text.document().size().height()
        target_height = max(BASE_TASK_HEIGHT, int(document_height) + 2)
        if self.text.height() != target_height:
            self.text.setFixedHeight(target_height)
        self._resizing_editor = False

    def _edit_task(self):
        dialog = TaskEditorDialog(self.task, self.window().store.data["tags"], self)
        if dialog.exec() == QDialog.Accepted:
            self.changed()
            # O checkbox aparece apenas quando a tarefa tem texto; reconstruir
            # a coluna atualiza essa estrutura imediatamente.
            self.window()._load_week()

    def _delete_task(self):
        answer = QMessageBox.question(
            self,
            "Excluir tarefa",
            "Excluir esta tarefa?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        self.window().delete_task_row(self)

    def _move_to_next_day(self):
        self.window().move_task_to_next_day(self)

    def _toggle_priority(self):
        self.task["priority"] = not self.task.get("priority", False)
        self._set_action_buttons_visible(True)
        self._apply_done_style()
        self.changed()

    def _approval_age_text(self):
        try:
            since = date.fromisoformat(self.task.get("approval_since", ""))
        except (TypeError, ValueError):
            return "0d"
        return f"{max(0, (date.today() - since).days)}d"

    def _apply_done_style(self):
        color = TAG_COLORS.get(self.task.get("tag"), "#777")
        if isinstance(self.text, EmptyTaskLine):
            self.text.setStyleSheet("")
        else:
            text_color = (
                "#ffc400"
                if self.task.get("priority", False)
                else "#808080" if self.day_name == APPROVALS_KEY else "#bdbdbd"
            )
            done_style = " text-decoration: line-through;" if self.check and self.check.isChecked() else ""
            self.text.setStyleSheet(f"color:{text_color};{done_style}")
        if self.check is None:
            return
        checked_color = "#777" if self.inline_edit else color
        self.check.setStyleSheet(
            "QCheckBox::indicator { border: 1px solid "
            f"{color}; border-radius:1px; }}"
            f"QCheckBox::indicator:checked {{ background:{checked_color}; }}"
        )


class PlannerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings = QSettings("M87Tools", "M87Terminal")
        self.store = PlannerStore()
        self.current_start = self._saved_week_start()
        self.drag_position = QPoint()
        self._geometry_restored = False
        self._geometry_save_timer = QTimer(self)
        self._geometry_save_timer.setSingleShot(True)
        self._geometry_save_timer.setInterval(250)
        self._geometry_save_timer.timeout.connect(self._save_window_geometry)
        self._notes_save_timer = QTimer(self)
        self._notes_save_timer.setSingleShot(True)
        self._notes_save_timer.setInterval(350)
        self._notes_save_timer.timeout.connect(self._flush_notes_save)
        self._pending_notes_text = None
        self._setup_window()
        self._build_ui()
        QApplication.instance().aboutToQuit.connect(self._save_window_geometry)
        self.search_shortcut = QShortcut(QKeySequence.Find, self)
        self.search_shortcut.activated.connect(self._open_search)
        self._load_week()

    def _setup_window(self):
        self.setWindowTitle("M87 TODO – PLANNER SEMANAL")
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMinimumSize(1060, 690)
        self.resize(1320, 810)
        self._restore_window_geometry()
        self._geometry_restored = True

    def _saved_week_start(self):
        saved = self.settings.value("planner/current_week", "")
        try:
            return week_start(date.fromisoformat(str(saved)))
        except ValueError:
            return week_start()

    def showEvent(self, event):
        super().showEvent(event)

    def _restore_window_geometry(self):
        geometry = self._saved_window_geometry()
        if geometry is not None:
            self.setGeometry(*geometry)
            return
        legacy_geometry = self.settings.value("planner/geometry")
        if legacy_geometry:
            self.restoreGeometry(legacy_geometry)

    def _saved_window_geometry(self):
        values = [
            self.settings.value(f"planner/window_{name}")
            for name in ("x", "y", "width", "height")
        ]
        try:
            x, y, width, height = (int(value) for value in values)
        except (TypeError, ValueError):
            return None
        if width < self.minimumWidth() or height < self.minimumHeight():
            return None
        return x, y, width, height

    def _saved_position(self):
        saved_x = self.settings.value("planner/position_x")
        saved_y = self.settings.value("planner/position_y")
        if saved_x is not None and saved_y is not None:
            return QPoint(int(saved_x), int(saved_y))

        position = self.settings.value("planner/position")
        if isinstance(position, QPoint):
            return position
        return None

    def _restore_saved_position(self, position=None):
        if position is not None:
            self.move(position)

    def moveEvent(self, event):
        self._schedule_window_geometry_save()
        super().moveEvent(event)

    def resizeEvent(self, event):
        self._schedule_window_geometry_save()
        super().resizeEvent(event)

    def _schedule_window_geometry_save(self):
        if self._geometry_restored:
            self._geometry_save_timer.start()

    def _save_window_geometry(self):
        if not self._geometry_restored:
            return
        self._geometry_save_timer.stop()
        geometry = self.geometry()
        self.settings.setValue("planner/geometry", self.saveGeometry())
        self.settings.setValue("planner/window_x", geometry.x())
        self.settings.setValue("planner/window_y", geometry.y())
        self.settings.setValue("planner/window_width", geometry.width())
        self.settings.setValue("planner/window_height", geometry.height())
        self.settings.setValue("planner/position_x", geometry.x())
        self.settings.setValue("planner/position_y", geometry.y())
        self.settings.setValue("planner/current_week", self.current_start.isoformat())
        self.settings.sync()

    def _build_ui(self):
        outer = QVBoxLayout(self); outer.setContentsMargins(7, 0, 7, 7)
        self.box = QWidget(); self.box.setObjectName("plannerBox"); outer.addWidget(self.box)
        root = QVBoxLayout(self.box); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)
        bar = DarkMetallicTitleBar(height=34, radius=12); bar.mousePressEvent = self._title_press; bar.mouseMoveEvent = self._title_move
        top = QHBoxLayout(bar); top.setContentsMargins(14, 0, 10, 0)
        title = QLabel("M87 - TO DO"); title.setObjectName("plannerTitle")
        close = QPushButton("×"); close.setObjectName("plannerClose"); close.clicked.connect(self.close)
        top.addWidget(title); top.addStretch(); top.addWidget(close); root.addWidget(bar)
        controls = QHBoxLayout(); controls.setContentsMargins(18, 13, 18, 9); controls.setSpacing(7)
        self.date_label = QLabel(); self.date_label.setObjectName("plannerDate"); controls.addWidget(self.date_label, 1)
        self.calendar = QDateEdit()
        self.calendar.setCalendarPopup(True)
        self.calendar.setDisplayFormat("dd/MM/yyyy")
        self.calendar.dateChanged.connect(self._select_date)
        controls.addWidget(self.calendar)
        root.addLayout(controls)
        content = QWidget(); content.setObjectName("plannerContent"); layout = QVBoxLayout(content); layout.setContentsMargins(16, 3, 16, 12); layout.setSpacing(10)
        priorities = self._section(None)
        priorities.setFixedWidth(500)
        priorities.setFixedHeight(76)
        self.priorities_layout = QGridLayout()
        self.priorities_layout.setContentsMargins(8, 12, 8, 3)
        self.priorities_layout.setSpacing(7)
        self.priorities_layout.setRowMinimumHeight(0, 27)
        self.priorities_layout.setRowMinimumHeight(1, 27)
        priorities.layout().addLayout(self.priorities_layout)
        priorities_row = QHBoxLayout()
        priorities_row.setSpacing(7)
        priorities_row.addWidget(priorities)
        priorities_row.addStretch()
        for label, callback in (
            ("‹", lambda: self._change_week(-1)),
            ("HOJE", self._today),
            ("›", lambda: self._change_week(1)),
            ("⌕", self._open_search),
            ("+", self._schedule_task),
        ):
            button = QPushButton(label)
            button.setObjectName("plannerButton")
            button.clicked.connect(callback)
            if label == "⌕":
                button.setToolTip("Buscar tarefas (⌘F)")
                button.setProperty("plannerSearch", True)
            elif label == "+":
                button.setToolTip("Agendar tarefa")
            if label in ("⌕", "+"):
                button.setProperty("plannerUtility", True)
            if label == "HOJE":
                button.setFixedSize(60, 39)
            elif label in ("‹", "›", "⌕", "+"):
                button.setFixedSize(40, 39)
            priorities_row.addWidget(button, 0, Qt.AlignBottom)
        layout.addLayout(priorities_row)
        self.days_grid = QGridLayout(); self.days_grid.setSpacing(8); self.days_grid.setRowStretch(0, 1); layout.addLayout(self.days_grid, 1)
        lower = QHBoxLayout(); lower.setSpacing(8)
        months = self._section(None)
        months.setFixedSize(370, 144)
        self.months_layout = QHBoxLayout()
        self.months_layout.setContentsMargins(0, 5, 0, 7)
        self.months_layout.setSpacing(2)
        months.layout().addLayout(self.months_layout)
        lower.addWidget(months)
        approvals = self._section("AGUARDANDO")
        approvals.setFixedWidth(300)
        approvals.setFixedHeight(144)
        approvals.findChild(QLabel).setObjectName("plannerNotesTitle")
        approvals_layout = approvals.layout()
        approvals_layout.setContentsMargins(14, 10, 8, 7)
        self.approvals_area = ApprovalDropArea(self)
        self.approvals_area.setObjectName("plannerApprovalsArea")
        self.approvals_area.setWidgetResizable(True)
        self.approvals_area.setFrameShape(QFrame.NoFrame)
        self.approvals_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.approvals_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        approvals_holder = QWidget()
        self.approvals_layout = QVBoxLayout(approvals_holder)
        self.approvals_layout.setContentsMargins(0, 0, 0, 0)
        self.approvals_layout.setSpacing(0)
        self.approvals_area.setWidget(approvals_holder)
        approvals_layout.addWidget(self.approvals_area, 1)
        lower.addWidget(approvals)
        notes = self._section("NOTAS")
        notes.setFixedHeight(144)
        notes_layout = notes.layout()
        notes_layout.setContentsMargins(14, 10, 8, 7)
        notes_title = notes_layout.takeAt(0).widget()
        notes_title.setObjectName("plannerNotesTitle")
        notes_header = QWidget()
        notes_header_layout = QHBoxLayout(notes_header)
        notes_header_layout.setContentsMargins(0, 0, 0, 0)
        notes_header_layout.setSpacing(4)
        notes_header_layout.addWidget(notes_title)
        notes_header_layout.addStretch()
        self.pen_button = self._notes_tool("✎", "Desenhar")
        self.pen_button.setCheckable(True)
        self.pen_button.toggled.connect(self._set_pen)
        self.eraser_button = self._notes_tool("⌫", "Apagar traço")
        self.eraser_button.setCheckable(True)
        self.eraser_button.toggled.connect(self._set_eraser)
        self.color_button = self._notes_tool("●", "Escolher cor")
        self.color_button.clicked.connect(self._open_pen_colors)
        self._set_pen_color("#FFC400")
        for button in (self.pen_button, self.eraser_button, self.color_button):
            notes_header_layout.addWidget(button)
        notes_layout.addWidget(notes_header)
        notes_body = QWidget()
        self.notes_stack = QStackedLayout(notes_body)
        self.notes_stack.setContentsMargins(0, 0, 0, 0)
        notes_layout.addWidget(notes_body, 1)
        lower.addWidget(notes, 1)
        layout.addLayout(lower)
        root.addWidget(content, 1)
        grip_row = QHBoxLayout()
        grip_row.setContentsMargins(0, 0, 4, 3)
        grip_row.addStretch()
        self.size_grip = PlannerResizeHandle(self.box)
        self.size_grip.setObjectName("plannerSizeGrip")
        grip_row.addWidget(self.size_grip)
        root.addLayout(grip_row)
        self.setStyleSheet("""
            QWidget { font-family: 'JetBrains Mono'; font-size: 11px; color:#d8d8d8; }
            QWidget#plannerBox { background:#080808; border:1px solid rgba(255,196,0,.25); border-radius:13px; }
            QLabel#plannerTitle { color:white; font-size:10px; font-weight:700; letter-spacing:1px; }
            QLabel#plannerDate { color:#9a9a9a; font-size:13px; font-weight:300; letter-spacing:3px; padding:4px 12px; background:transparent; }
            QPushButton#plannerClose { color:white; background:transparent; border:0; font-size:17px; } QPushButton#plannerClose:hover { color:#ffc400; }
            QPushButton#plannerButton { color:#c8c8c8; background:#171717; border:1px solid #303030; border-radius:4px; padding:6px 10px; font-weight:700; } QPushButton#plannerButton:hover, QPushButton#plannerButton:checked { color:#ffc400; border-color:#806300; }
            QPushButton#plannerButton[plannerUtility="true"] { font-size:17px; padding:0 0 3px; }
            QPushButton#plannerButton[plannerUtility="true"][plannerSearch="true"] { font-size:21px; padding:0 0 4px; }
            QFrame#plannerSection { background:#101010; border:1px solid #292929; border-radius:6px; } QLabel#plannerSectionTitle { color:#ffc400; font-size:12px; font-weight:700; padding:5px 7px; }
            QTextEdit, QLineEdit { background:transparent; border:0; border-bottom:1px solid #292929; padding:1px; } QTextEdit#plannerTaskText { border:0; padding:0; } QTextEdit:focus, QLineEdit:focus { border-bottom-color:#ffc400; }
            QLabel#plannerEmptyTask { background:transparent; border:0; border-bottom:1px solid #292929; }
            QScrollArea#plannerApprovalsArea, QScrollArea#plannerApprovalsArea > QWidget > QWidget { background:#101010; border:0; }
            QDateEdit { background:#161616; border:1px solid #303030; border-radius:4px; padding:4px; color:#bdbdbd; } QCheckBox::indicator { width:6px; height:6px; margin-top:2px; border:1px solid #747474; border-radius:1px; } QCheckBox::indicator:checked { background:#ffc400; border-color:#ffc400; }
            QLabel#plannerMonthTitle { color:#9a9a9a; font-size:9px; font-weight:700; padding-top:2px; }
            QLabel#plannerNotesTitle { color:#8f8f8f; font-size:9px; font-weight:300; letter-spacing:2px; }
            QPushButton#plannerNotesTool { color:#8f8f8f; background:#151515; border:1px solid #303030; border-radius:3px; padding:0; font-size:12px; }
            QPushButton#plannerNotesTool:hover, QPushButton#plannerNotesTool:checked { color:#ffc400; border-color:#806300; }
            QLabel#plannerApprovalAge { color:#808080; font-size:9px; font-weight:300; padding-top:4px; }
            QTextEdit#plannerNotesEditor { color:#8f8f8f; font-family:'JetBrains Mono'; font-size:9px; font-weight:300; letter-spacing:2px; }
            QTextEdit#plannerNotesEditor::placeholder { color:#8f8f8f; }
            QWidget#plannerMonth { background:transparent; } QWidget#plannerMonthGrid { background:transparent; } QLabel#plannerCalendarCell { color:#8b8b8b; font-size:8px; min-height:12px; } QLabel#plannerCalendarCell[activeWeek="true"] { color:#ffc400; }
            QPushButton#plannerDayMenu { color:#777; background:transparent; border:0; padding:0 5px; font-size:14px; }
            QWidget#plannerSizeGrip { background:transparent; }
        """)

    def _section(self, title):
        frame = QFrame(); frame.setObjectName("plannerSection"); outer = QVBoxLayout(frame); outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)
        if title:
            label = QLabel(title); label.setObjectName("plannerSectionTitle"); outer.addWidget(label)
        return frame

    @staticmethod
    def _notes_tool(icon, tooltip):
        button = QPushButton(icon)
        button.setObjectName("plannerNotesTool")
        button.setFixedSize(20, 20)
        button.setToolTip(tooltip)
        return button

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0); widget = item.widget()
            if widget: widget.deleteLater()

    def _load_week(self):
        self._flush_notes_save()
        self.week = self.store.apply_scheduled_tasks(self.current_start)
        self.date_label.setText(f"PLANNER SEMANAL {self.current_start:%Y}")
        self.calendar.blockSignals(True)
        self.calendar.setDate(QDate(
            self.current_start.year,
            self.current_start.month,
            self.current_start.day,
        ))
        self.calendar.blockSignals(False)
        tags = self.store.data["tags"]
        self._clear_layout(self.priorities_layout)
        for index, task in enumerate(self.week["priorities"]):
            self.priorities_layout.addWidget(
                PlannerTaskRow(task, tags, self._save, inline_edit=True),
                index // 2,
                index % 2,
            )
        self._load_month_calendars()
        self._clear_layout(self.days_grid)
        for index, name in enumerate(DAY_NAMES):
            frame = DaySection(name, self)
            frame.setObjectName("plannerSection")
            frame.setMinimumHeight(0)
            frame_layout = QVBoxLayout(frame)
            frame_layout.setContentsMargins(0, 0, 0, 0)
            frame_layout.setSpacing(0)
            title = QLabel(f"{name} · {(self.current_start + timedelta(days=index)):%d}")
            title.setObjectName("plannerSectionTitle")
            heading = QHBoxLayout()
            heading.setContentsMargins(0, 0, 4, 0)
            heading.addWidget(title)
            heading.addStretch()
            organize = QPushButton("⌄")
            organize.setObjectName("plannerDayMenu")
            organize.setToolTip("Opções do dia")
            organize.clicked.connect(
                lambda checked=False, day=name, button=organize:
                self._open_day_menu(day, button)
            )
            heading.addWidget(organize)
            frame_layout.addLayout(heading)
            task_scroll = DayDropArea(self, name)
            task_scroll.setWidgetResizable(True)
            task_scroll.setFrameShape(QFrame.NoFrame)
            task_scroll.setMinimumHeight(0)
            task_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            task_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            tasks_holder = QWidget()
            day_layout = QVBoxLayout(tasks_holder); day_layout.setContentsMargins(7, 2, 7, 4); day_layout.setSpacing(0)
            for task_index, task in enumerate(self.week["days"][name]):
                day_layout.addWidget(
                    PlannerTaskRow(
                        task,
                        tags,
                        self._save,
                        name,
                        task_index=task_index,
                    )
                )
            day_layout.addStretch()
            task_scroll.setWidget(tasks_holder)
            frame_layout.addWidget(task_scroll, 1)
            self.days_grid.addWidget(frame, 0, index)
        self._clear_layout(self.approvals_layout)
        for task_index, task in enumerate(self.store.data["approvals"]):
            self.approvals_layout.addWidget(
                PlannerTaskRow(
                    task,
                    tags,
                    self._save,
                    APPROVALS_KEY,
                    task_index=task_index,
                )
            )
        self.approvals_layout.addStretch()
        self._clear_layout(self.notes_stack)
        self.notes_editor = QTextEdit()
        self.notes_editor.setObjectName("plannerNotesEditor")
        self.notes_editor.setPlaceholderText("Notas da semana")
        self.notes_editor.setPlainText(self.week.get("notes_text", ""))
        self.notes_editor.textChanged.connect(
            lambda: self._queue_notes_save(self.notes_editor.toPlainText())
        )
        strokes = self.week.setdefault("notes", [])
        self.canvas = InkCanvas(strokes, self._save)
        self.canvas.color = getattr(self, "pen_color", "#FFC400")
        self.notes_stack.addWidget(self.notes_editor)
        self.notes_stack.addWidget(self.canvas)
        self._update_notes_mode()

    def _queue_notes_save(self, text):
        self._pending_notes_text = text
        self._notes_save_timer.start()

    def _flush_notes_save(self):
        if self._pending_notes_text is None or not hasattr(self, "week"):
            return
        self._notes_save_timer.stop()
        text = self._pending_notes_text
        self._pending_notes_text = None
        self.week["notes_text"] = text
        self._save()

    def _load_month_calendars(self):
        self._clear_layout(self.months_layout)
        first_month = self.current_start.replace(day=1)
        for offset in (0, 1):
            month = self._month_offset(first_month, offset)
            month_widget = QWidget()
            month_widget.setFixedWidth(175)
            month_widget.setObjectName("plannerMonth")
            month_layout = QVBoxLayout(month_widget)
            month_layout.setContentsMargins(0, 0, 0, 0)
            month_layout.setSpacing(1)
            label = QLabel(f"{MONTH_NAMES[month.month - 1]} {month.year}")
            label.setObjectName("plannerMonthTitle")
            label.setAlignment(Qt.AlignCenter)
            label.setFixedWidth(175)
            month_layout.addWidget(label, alignment=Qt.AlignHCenter)
            grid = self._month_grid(month)
            grid.setFixedWidth(175)
            month_layout.addWidget(grid, alignment=Qt.AlignHCenter)
            self.months_layout.addWidget(month_widget)

    def _month_grid(self, month):
        grid_widget = QWidget()
        grid_widget.setObjectName("plannerMonthGrid")
        grid = QGridLayout(grid_widget)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(0)
        grid.setVerticalSpacing(1)
        grid.setRowMinimumHeight(0, 13)
        headers = ("S", "T", "Q", "Q", "S", "S", "D")
        for column, header in enumerate(headers):
            label = QLabel(header)
            label.setAlignment(Qt.AlignCenter)
            label.setObjectName("plannerCalendarCell")
            grid.addWidget(label, 0, column)
            grid.setColumnStretch(column, 1)
            grid.setColumnMinimumWidth(column, 24)
        weeks = calendar_module.monthcalendar(month.year, month.month)
        weeks.extend([[0] * 7] * (6 - len(weeks)))
        for row, week in enumerate(weeks, start=1):
            grid.setRowMinimumHeight(row, 13)
            for column, day_number in enumerate(week):
                if day_number:
                    day = date(month.year, month.month, day_number)
                    label = CalendarDayLabel(
                        f"{day_number:02}",
                        day,
                        self._select_calendar_day,
                    )
                else:
                    label = QLabel("")
                label.setAlignment(Qt.AlignCenter)
                label.setObjectName("plannerCalendarCell")
                if day_number:
                    label.setProperty(
                        "activeWeek",
                        self.current_start <= day <= self.current_start + timedelta(days=6),
                    )
                grid.addWidget(label, row, column)
        return grid_widget

    def _select_calendar_day(self, selected_date):
        self.current_start = week_start(selected_date)
        self._load_week()
        self._save_window_geometry()

    def _open_day_menu(self, day, button):
        menu = QMenu(self)
        organize = menu.addAction("ORGANIZAR POR TIPO")
        organize.triggered.connect(lambda: self._organize_day_by_type(day))
        organize_completed = menu.addAction("CONCLUÍDAS + TIPO")
        organize_completed.triggered.connect(
            lambda: self._organize_day_completed_then_type(day)
        )
        menu.exec(button.mapToGlobal(button.rect().bottomLeft()))

    def _organize_day_by_type(self, day):
        tasks = self.week["days"][day]
        tasks.sort(
            key=lambda task: (
                not bool(task.get("text", "").strip()),
                task.get("tag", ""),
            )
        )
        self._save()
        self._load_week()

    def _organize_day_completed_then_type(self, day):
        tasks = self.week["days"][day]

        def sort_key(task):
            if not task.get("text", "").strip():
                return 2, ""
            if task.get("done", False):
                return 0, ""
            return 1, task.get("tag", "")

        tasks.sort(key=sort_key)
        self._save()
        self._load_week()

    @staticmethod
    def _month_offset(month, offset):
        month_number = month.month + offset
        year = month.year + (month_number - 1) // 12
        month_number = (month_number - 1) % 12 + 1
        return month.replace(year=year, month=month_number)

    @staticmethod
    def _row_task_index(row, tasks):
        """Localiza pela identidade da linha, nunca pelo texto da tarefa."""
        index = row.task_index
        if index is not None and 0 <= index < len(tasks) and tasks[index] is row.task:
            return index
        return next((i for i, task in enumerate(tasks) if task is row.task), None)

    def _source_tasks_for_row(self, row):
        if row.day_name == APPROVALS_KEY:
            return self.store.data["approvals"]
        if row.day_name in DAY_NAMES:
            return self.week["days"][row.day_name]
        return None

    def delete_task_row(self, row):
        tasks = self._source_tasks_for_row(row)
        if tasks is None:
            return
        source_index = self._row_task_index(row, tasks)
        if source_index is None:
            return
        if row.day_name == APPROVALS_KEY:
            del tasks[source_index]
        else:
            tasks[source_index] = empty_task()
        self._save()
        self._load_week()

    def move_task_to_day(self, row, destination, target_index):
        source = row.day_name
        if not source:
            return
        source_tasks = self._source_tasks_for_row(row)
        if source_tasks is None:
            return
        destination_tasks = self.week["days"][destination]
        source_index = self._row_task_index(row, source_tasks)
        if source_index is None or not destination_tasks:
            return
        target_index = max(0, min(target_index, len(destination_tasks) - 1))

        if source == APPROVALS_KEY:
            moving = source_tasks[source_index]
            displaced = destination_tasks[target_index]
            # Todas as referências são validadas antes da primeira mudança.
            # Assim, uma queda inválida nunca remove nem substitui uma tarefa.
            del source_tasks[source_index]
            moving.pop("approval_since", None)
            destination_tasks[target_index] = moving
            if task_has_content(displaced):
                source_tasks.insert(source_index, displaced)
            self._save()
            self._load_week()
            return

        # Cada posição representa uma linha visível do planner. Trocar as duas
        # posições preserva os espaços deixados entre tarefas.
        if source == destination and source_index == target_index:
            return
        moving = source_tasks[source_index]
        displaced = destination_tasks[target_index]
        source_tasks[source_index] = displaced
        destination_tasks[target_index] = moving
        self._save()
        self._load_week()

    def move_task_to_approvals(self, row, target_index):
        source = row.day_name
        if not source or source == APPROVALS_KEY:
            return
        source_tasks = self._source_tasks_for_row(row)
        if source_tasks is None:
            return
        source_index = self._row_task_index(row, source_tasks)
        if source_index is None:
            return
        moving = source_tasks[source_index]
        if not moving.get("approval_since"):
            moving["approval_since"] = date.today().isoformat()
        approvals = self.store.data["approvals"]
        target_index = max(0, min(target_index, len(approvals)))
        # Inserir primeiro preserva a tarefa mesmo se a lista de origem for
        # recriada pelo Qt durante a atualização da interface.
        approvals.insert(target_index, moving)
        source_tasks[source_index] = empty_task()
        self._save()
        self._load_week()

    def move_task_to_next_day(self, row):
        if row.day_name not in DAY_NAMES:
            return
        source_tasks = self._source_tasks_for_row(row)
        if source_tasks is None:
            return
        source_index = self._row_task_index(row, source_tasks)
        if source_index is None:
            return

        source_day_index = DAY_NAMES.index(row.day_name)
        if source_day_index == len(DAY_NAMES) - 1:
            target_week = self.store.get_week(self.current_start + timedelta(days=7))
            target_day = "SEG"
        else:
            target_week = self.week
            target_day = DAY_NAMES[source_day_index + 1]
        target_tasks = target_week["days"][target_day]
        target_index = next(
            (i for i, task in enumerate(target_tasks) if not task_has_content(task)),
            None,
        )
        moving = source_tasks[source_index]
        if target_index is None:
            target_tasks.append(moving)
        else:
            target_tasks[target_index] = moving
        source_tasks[source_index] = empty_task()
        self._save()
        self._load_week()

    def _save(self):
        self.store.save()

    def _open_search(self):
        PlannerSearchDialog(self, self).exec()

    def _schedule_task(self):
        task = empty_task()
        dialog = TaskEditorDialog(
            task,
            self.store.data["tags"],
            self,
            schedule_mode=True,
        )
        if dialog.exec() != QDialog.Accepted or not task_has_content(task):
            return
        scheduled_date = dialog.scheduled_date()
        self.store.add_scheduled_task(
            scheduled_date,
            task,
            dialog.scheduled_recurrence(),
        )
        self.current_start = week_start(scheduled_date)
        self._load_week()

    def closeEvent(self, event):
        self._flush_notes_save()
        self._save_window_geometry()
        super().closeEvent(event)

    def hideEvent(self, event):
        self._flush_notes_save()
        self._save_window_geometry()
        super().hideEvent(event)

    def _change_week(self, offset):
        self.current_start += timedelta(days=7 * offset)
        self._load_week()
        self._save_window_geometry()

    def _today(self):
        self.current_start = week_start()
        self._load_week()
        self._save_window_geometry()

    def _select_date(self, selected_date):
        self.current_start = week_start(selected_date.toPython())
        self._load_week()
        self._save_window_geometry()

    def _set_pen(self, enabled):
        canvas = getattr(self, "canvas", None)
        if canvas is None:
            return
        if enabled:
            self._flush_notes_save()
            self.eraser_button.blockSignals(True)
            self.eraser_button.setChecked(False)
            self.eraser_button.blockSignals(False)
            canvas.pen_enabled = True
            canvas.eraser = False
        elif not self.eraser_button.isChecked():
            canvas.pen_enabled = False
        self._update_notes_mode()

    def _set_eraser(self, enabled):
        canvas = getattr(self, "canvas", None)
        if canvas is None:
            return
        if enabled:
            self._flush_notes_save()
            self.pen_button.blockSignals(True)
            self.pen_button.setChecked(False)
            self.pen_button.blockSignals(False)
            canvas.pen_enabled = True
            canvas.eraser = True
        elif not self.pen_button.isChecked():
            canvas.pen_enabled = False
            canvas.eraser = False
        self._update_notes_mode()

    def _update_notes_mode(self):
        if not hasattr(self, "notes_stack") or not hasattr(self, "canvas"):
            return
        drawing = self.pen_button.isChecked() or self.eraser_button.isChecked()
        self.notes_stack.setCurrentWidget(self.canvas if drawing else self.notes_editor)

    def _open_pen_colors(self):
        menu = QMenu(self)
        for label, color in (
            ("AMARELO", "#FFC400"),
            ("AZUL", "#049DDD"),
            ("ROSA", "#E42C8D"),
            ("VERDE", "#53C5AE"),
            ("BRANCO", "#F5F5F5"),
        ):
            action = menu.addAction(label)
            action.triggered.connect(
                lambda checked=False, value=color: self._set_pen_color(value)
            )
        menu.exec(self.color_button.mapToGlobal(self.color_button.rect().bottomLeft()))

    def _set_pen_color(self, color):
        self.pen_color = color
        if hasattr(self, "canvas"):
            self.canvas.color = color
        if hasattr(self, "color_button"):
            self.color_button.setStyleSheet(
                f"color:{color}; background:#151515; border:1px solid #303030; "
                "border-radius:3px; padding:0; font-size:12px;"
            )
    def _duplicate(self):
        destination = self.current_start + timedelta(days=7)
        if destination.isoformat() in self.store.data["weeks"]:
            answer = QMessageBox.question(self, "Duplicar semana", "Substituir a semana seguinte?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if answer != QMessageBox.Yes:
                return
        self.store.duplicate_week(self.current_start, destination)
        self.current_start = destination
        self._load_week()

    def _title_press(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_position = event.globalPosition().toPoint()

    def _title_move(self, event):
        if event.buttons() & Qt.LeftButton:
            delta = event.globalPosition().toPoint() - self.drag_position
            self.move(self.pos() + delta)
            self.drag_position = event.globalPosition().toPoint()
