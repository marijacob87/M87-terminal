import sys

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from core.config import FONT_FAMILY
from ui.ui import M87Term


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setFont(QFont(FONT_FAMILY, 12))

    window = M87Term()
    window.show()

    sys.exit(app.exec())