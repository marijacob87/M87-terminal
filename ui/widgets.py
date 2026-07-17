from PySide6.QtCore import QTimer, Qt, QRectF
from PySide6.QtGui import QColor, QCursor, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QLabel, QHBoxLayout, QWidget, QSizePolicy


class MetallicRainbowLabel(QLabel):
    """QLabel com gradiente arco-íris metálico para o título."""

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

    def _gradient(self, rect):
        gradient = QLinearGradient(
            rect.left(),
            rect.center().y(),
            rect.right(),
            rect.center().y(),
        )

        stops = (
            (0.00, "#FF4F55"),
            (0.08, "#FF8A56"),
            (0.16, "#FFD166"),
            (0.23, "#FFF2A8"),
            (0.32, "#54E38E"),
            (0.40, "#B8FFD7"),
            (0.50, "#36C5F0"),
            (0.59, "#9EEBFF"),
            (0.68, "#587BFF"),
            (0.78, "#C06CFF"),
            (0.87, "#F3B0FF"),
            (1.00, "#FF4F91"),
        )

        for position, color in stops:
            gradient.setColorAt(position, QColor(color))

        return gradient

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        rect = QRectF(self.contentsRect())
        painter.setFont(self.font())
        painter.setPen(QPen(self._gradient(rect), 1))
        painter.drawText(rect, int(self.alignment()), self.text())


class CommandRow(QWidget):
    def __init__(self, label, code, on_execute):
        super().__init__()

        self.label_text = label
        self.code_text = code
        self.on_execute = on_execute
        self.is_hovering_text = False

        self.setObjectName("commandRow")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 1, 2, 1)
        layout.setSpacing(4)

        self.code = QLabel(code)
        self.code.setObjectName("commandCode")
        self.code.setCursor(QCursor(Qt.PointingHandCursor))

        self.label = QLabel(label)
        self.label.setObjectName("commandLabel")
        self.label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.label.setCursor(QCursor(Qt.PointingHandCursor))

        self.flag = QLabel("")
        self.flag.setObjectName("flag")
        self.flag.setFixedWidth(12)

        layout.addWidget(self.code)
        layout.addWidget(self.label)
        layout.addWidget(self.flag)
        layout.addStretch()

        self.code.enterEvent = self.enter_text
        self.label.enterEvent = self.enter_text

        self.code.leaveEvent = self.leave_text
        self.label.leaveEvent = self.leave_text

        self.code.mousePressEvent = self.click_text
        self.label.mousePressEvent = self.click_text

        self.set_normal_style()

    def set_normal_style(self):
        self.setStyleSheet("""
            QWidget#commandRow {
                border-radius: 5px;
                background-color: transparent;
            }

            QLabel#commandCode {
                color: rgba(244, 189, 4, 1);
                font-size: 11px;
                font-weight: 400;
            }

            QLabel#commandLabel {
                color: rgba(244, 189, 4, 0.72);
                font-size: 11px;
                font-weight: 400;
            }
        """)

    def set_hover_style(self):
        self.setStyleSheet("""
            QWidget#commandRow {
                border-radius: 5px;
                background-color: transparent;
            }

            QLabel#commandCode {
                color: rgb(255, 221, 40);
                font-size: 11px;
                font-weight: 400;
            }

            QLabel#commandLabel {
                color: rgb(255, 239, 150);
                font-size: 11px;
                font-weight: 400;
            }
        """)

    def enter_text(self, event):
        self.is_hovering_text = True
        self.set_hover_style()

    def leave_text(self, event):
        self.is_hovering_text = False
        self.set_normal_style()

    def click_text(self, event):
        self.execute()

    def execute(self):
        self.flag.setText("✓")
        self.on_execute(self.code_text)
        QTimer.singleShot(900, lambda: self.flag.setText(""))

class SectionLabel(QLabel):
    def __init__(self, text):
        super().__init__(text.upper())
        self.setObjectName("sectionLabel")
        self.setStyleSheet("""
            QLabel#sectionLabel {
                color: rgba(244, 189, 4, 0.48);
                font-size: 9px;
                font-weight: 500;
                letter-spacing: 1px;
                padding: 4px 2px 1px 2px;
            }
        """)
