import os
import sys

from PySide6.QtCore import QCoreApplication, QLibraryInfo
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from core.config import FONT_FAMILY


def configure_qt_plugins():
    plugins_path = QLibraryInfo.path(
        QLibraryInfo.LibraryPath.PluginsPath
    )

    if os.path.isdir(plugins_path):
        QCoreApplication.addLibraryPath(plugins_path)
    else:
        print(
            f"[ERRO] Pasta de plugins do Qt não encontrada: "
            f"{plugins_path}"
        )


def main():
    configure_qt_plugins()

    app = QApplication(sys.argv)
    app.setFont(QFont(FONT_FAMILY, 12))

    # Importado apenas depois que o Qt já iniciou corretamente.
    from ui.ui import M87Term

    window = M87Term()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())