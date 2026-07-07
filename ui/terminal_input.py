from PySide6.QtCore import Qt, QTimer, Signal, QEvent
from PySide6.QtGui import QColor, QFontMetrics, QPainter
from PySide6.QtWidgets import QLineEdit, QWidget


class HiddenLineEdit(QLineEdit):
    def paintEvent(self, event):
        pass


class TerminalInput(QWidget):
    arrowUpPressed = Signal()
    arrowDownPressed = Signal()
    escapePressed = Signal()
    returnPressed = Signal()
    textChanged = Signal(str)
    fileDropped = Signal(str)

    def __init__(self, prompt="m87@macstudio ~ %", parent=None):
        super().__init__(parent)

        self.prompt = prompt
        self.cursor_visible = True
        self.has_input_focus = False

        self.edit = HiddenLineEdit(self)
        self.edit.setFrame(False)
        self.edit.setStyleSheet("""
            QLineEdit {
                background: transparent;
                border: none;
                color: transparent;
                padding: 0px;
            }
        """)

        self.edit.installEventFilter(self)
        self.edit.textChanged.connect(self._on_text_changed)
        self.edit.returnPressed.connect(self.returnPressed.emit)

        self.cursor_timer = QTimer(self)
        self.cursor_timer.timeout.connect(self._toggle_cursor)
        self.cursor_timer.start(500)

        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumHeight(18)
        self.setAcceptDrops(True)
        self.edit.setAcceptDrops(False)

    def eventFilter(self, obj, event):
        if obj == self.edit:
            if event.type() == QEvent.FocusIn:
                self.has_input_focus = True
                self.cursor_visible = True
                self.update()

            elif event.type() == QEvent.FocusOut:
                self.has_input_focus = False
                self.cursor_visible = False
                self.update()

            elif event.type() == QEvent.KeyPress:
                if event.key() == Qt.Key_Up:
                    self.arrowUpPressed.emit()
                    return True

                if event.key() == Qt.Key_Down:
                    self.arrowDownPressed.emit()
                    return True

                if event.key() == Qt.Key_Escape:
                    self.escapePressed.emit()
                    return True

        return super().eventFilter(obj, event)

    def _on_text_changed(self, text):
        self.textChanged.emit(text)
        self.update()

    def _toggle_cursor(self):
        self.cursor_visible = self.edit.hasFocus() and not self.cursor_visible
        self.update()

    def text(self):
        return self.edit.text()

    def clear(self):
        self.edit.clear()
        self.update()

    def setText(self, text):
        self.edit.setText(text)
        self.update()

    def setPlaceholderText(self, text):
        self.edit.setPlaceholderText(text)

    def setFocus(self):
        self.edit.setFocus()

    def mousePressEvent(self, event):
        self.edit.setFocus()
        self.has_input_focus = True
        self.cursor_visible = True
        self.update()
        super().mousePressEvent(event)

    def resizeEvent(self, event):
        self.edit.setGeometry(0, 0, self.width(), self.height())
        super().resizeEvent(event)

    def get_visible_text(self, text, max_width, metrics):
        if metrics.horizontalAdvance(text) <= max_width:
            return text

        ellipsis = "…"

        visible = ""

        for char in reversed(text):
            test = ellipsis + char + visible

            if metrics.horizontalAdvance(test) > max_width:
                break

            visible = char + visible

        return ellipsis + visible
    
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()

            if urls:
                path = urls[0].toLocalFile()

                if path.lower().endswith(".pdf"):
                    event.acceptProposedAction()
                    return

        event.ignore()


    def dropEvent(self, event):
        urls = event.mimeData().urls()

        if not urls:
            event.ignore()
            return

        path = urls[0].toLocalFile()

        if path.lower().endswith(".pdf"):
            self.fileDropped.emit(path)
            event.acceptProposedAction()
            return

        event.ignore()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.TextAntialiasing)

        font = self.font()
        painter.setFont(font)

        metrics = QFontMetrics(font)

        prompt_color = QColor(114, 255, 66, 242)
        text_color = QColor(165, 255, 115, 255)
        cursor_color = QColor(114, 255, 66, 230)

        baseline = metrics.ascent()

        prompt_text = self.prompt + " "
        typed_text = self.edit.text()

        prompt_width = metrics.horizontalAdvance(prompt_text)
        cursor_w = max(7, metrics.horizontalAdvance("M") - 1)
        available_text_width = self.width() - prompt_width - cursor_w - 4

        visible_text = self.get_visible_text(
            typed_text,
            available_text_width,
            metrics,
        )

        painter.setPen(prompt_color)
        painter.drawText(0, baseline, prompt_text)

        painter.setPen(text_color)
        painter.drawText(prompt_width, baseline, visible_text)

        if self.cursor_visible and self.edit.hasFocus():
            text_width = metrics.horizontalAdvance(visible_text)

            cursor_x = prompt_width + text_width + 1
            cursor_y = 2
            cursor_h = metrics.height() - 4

            painter.fillRect(
                cursor_x,
                cursor_y,
                cursor_w,
                cursor_h,
                cursor_color,
            )