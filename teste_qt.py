from PySide6.QtWidgets import QApplication, QLabel

app = QApplication([])

window = QLabel("QT PURO")
window.resize(240, 80)
window.show()

app.exec()
