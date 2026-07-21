from PySide6.QtCore import QTimer, Qt, QRectF, QPoint
from PySide6.QtGui import (
    QColor,
    QCursor,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import QLabel, QHBoxLayout, QWidget, QSizePolicy


class DarkMetallicTitleBar(QWidget):
    """Barra superior escura com gradiente metálico e cantos arredondados."""

    def __init__(self, parent=None, height=34, radius=12.0):
        super().__init__(parent)
        self._corner_radius = float(radius)
        self.setObjectName("titleContainer")
        self.setFixedHeight(height)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        rect = QRectF(self.rect())
        path = QPainterPath()
        radius = self._corner_radius
        path.moveTo(rect.left(), rect.bottom())
        path.lineTo(rect.left(), rect.top() + radius)
        path.quadTo(rect.left(), rect.top(), rect.left() + radius, rect.top())
        path.lineTo(rect.right() - radius, rect.top())
        path.quadTo(rect.right(), rect.top(), rect.right(), rect.top() + radius)
        path.lineTo(rect.right(), rect.bottom())
        path.closeSubpath()

        gradient = QLinearGradient(rect.left(), rect.center().y(), rect.right(), rect.center().y())
        stops = (
            (0.00, "#705000"),
            (0.07, "#9A6A05"),
            (0.15, "#38210F"),
            (0.28, "#211426"),
            (0.42, "#30116A"),
            (0.56, "#101250"),
            (0.70, "#062D58"),
            (0.84, "#07505C"),
            (1.00, "#173B40"),
        )
        for position, color in stops:
            gradient.setColorAt(position, QColor(color))

        painter.fillPath(path, gradient)

        # Reflexo metálico muito discreto: ilumina o topo sem parecer plástico.
        shine = QLinearGradient(rect.left(), rect.top(), rect.left(), rect.bottom())
        shine.setColorAt(0.00, QColor(255, 255, 255, 46))
        shine.setColorAt(0.36, QColor(255, 255, 255, 8))
        shine.setColorAt(0.62, QColor(0, 0, 0, 20))
        shine.setColorAt(1.00, QColor(0, 0, 0, 64))
        painter.fillPath(path, shine)

        painter.setPen(QPen(QColor(255, 255, 255, 28), 1))
        painter.drawLine(1, 0, self.width() - 2, 0)
        painter.setPen(QPen(QColor(255, 255, 255, 36), 1))
        painter.drawLine(0, self.height() - 1, self.width(), self.height() - 1)


class HorizontalResizeGrip(QWidget):
    """Permite alterar apenas a largura da janela, nunca sua altura-base."""

    def __init__(self, window, parent=None):
        super().__init__(parent)
        self.window = window
        self._start_global = QPoint()
        self._start_width = 0
        self.setObjectName("sizeGrip")
        self.setCursor(QCursor(Qt.SizeHorCursor))
        self.setFixedSize(14, 12)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._start_global = event.globalPosition().toPoint()
            self._start_width = self.window.width()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            delta = event.globalPosition().toPoint().x() - self._start_global.x()
            new_width = max(self.window.minimumWidth(), self._start_width + delta)
            self.window.resize(new_width, self.window.height())
            event.accept()
            return
        super().mouseMoveEvent(event)


class MetallicRainbowLabel(QLabel):
    """Mantido por compatibilidade com outras telas do projeto."""

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

    def _gradient(self, rect):
        gradient = QLinearGradient(rect.left(), rect.center().y(), rect.right(), rect.center().y())
        for position, color in (
            (0.00, "#FF4F55"), (0.16, "#FFD166"), (0.32, "#54E38E"),
            (0.50, "#36C5F0"), (0.68, "#587BFF"), (0.84, "#C06CFF"),
            (1.00, "#FF4F91"),
        ):
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
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

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
            QWidget#commandRow { border-radius: 5px; background-color: transparent; }
            QLabel#commandCode { color: rgba(244, 189, 4, 1); font-size: 11px; font-weight: 400; }
            QLabel#commandLabel { color: rgba(244, 189, 4, 0.72); font-size: 11px; font-weight: 400; }
        """)

    def set_hover_style(self):
        self.setStyleSheet("""
            QWidget#commandRow { border-radius: 5px; background-color: transparent; }
            QLabel#commandCode { color: rgb(255, 221, 40); font-size: 11px; font-weight: 400; }
            QLabel#commandLabel { color: rgb(255, 239, 150); font-size: 11px; font-weight: 400; }
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
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setStyleSheet("""
            QLabel#sectionLabel {
                color: rgba(255, 255, 255, 0.52);
                font-size: 9px;
                font-weight: 500;
                letter-spacing: 1px;
                padding: 4px 2px 1px 2px;
            }
        """)
