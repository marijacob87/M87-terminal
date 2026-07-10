from PySide6.QtWidgets import QApplication
from ui.ui import M87Term

app = QApplication([])

window = M87Term()
window.show()

app.exec()
