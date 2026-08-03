import os
import sys
from pathlib import Path

from AppKit import NSApplication, NSImage
from PySide6.QtCore import QCoreApplication, QLibraryInfo
from PySide6.QtGui import QFont, QIcon
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


def configure_app_icon(app):
    project_root = Path(__file__).resolve().parent
    png_path = project_root / "assets" / "m87_icon.png"
    icon_path = project_root / "assets" / "m87_icon.icns"

    if not png_path.exists():
        print(f"[ERRO] Ícone não encontrado: {png_path}")
        return

    app.setWindowIcon(QIcon(str(icon_path if icon_path.exists() else png_path)))
    image = NSImage.alloc().initWithContentsOfFile_(str(png_path))

    if image is None:
        print(f"[ERRO] Não foi possível carregar o ícone: {icon_path}")
        return

    NSApplication.sharedApplication().setApplicationIconImage_(image)


def main():
    configure_qt_plugins()

    app = QApplication(sys.argv)
    app.setApplicationName("M87 Terminal")
    app.setOrganizationName("M87Tools")
    app.setFont(QFont(FONT_FAMILY, 12))

    configure_app_icon(app)

    # Importado apenas depois que o Qt já iniciou corretamente.
    from ui.ui import M87Term

    window = M87Term()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
