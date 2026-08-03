from PySide6.QtCore import QEvent, QObject, QTimer, Qt
from PySide6.QtWidgets import QAbstractSpinBox


class SelectSpinBoxTextOnTab(QObject):
    """Seleciona valores numéricos ao navegar por Tab em todo o aplicativo."""

    def eventFilter(self, watched, event):
        if (
            isinstance(watched, QAbstractSpinBox)
            and event.type() == QEvent.Type.FocusIn
            and event.reason()
            in (
                Qt.FocusReason.TabFocusReason,
                Qt.FocusReason.BacktabFocusReason,
            )
        ):
            line_edit = watched.lineEdit()
            if line_edit is not None:
                QTimer.singleShot(0, line_edit.selectAll)
        return super().eventFilter(watched, event)
