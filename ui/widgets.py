from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QLabel, QHBoxLayout, QWidget, QSizePolicy


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