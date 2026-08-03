from PySide6.QtGui import QValidator
from PySide6.QtWidgets import QDoubleSpinBox

from core.calculator import calculate


class ExpressionDoubleSpinBox(QDoubleSpinBox):
    """Campo decimal que também aceita cálculos aritméticos simples."""

    _allowed = frozenset("0123456789+-*/()., ")

    def __init__(self, parent=None):
        super().__init__(parent)
        self._editing_suffix = ""

    def focusInEvent(self, event):
        self._editing_suffix = self.suffix()
        if self._editing_suffix:
            self.setSuffix("")
        super().focusInEvent(event)
        self.lineEdit().deselect()
        self.lineEdit().setCursorPosition(len(self.lineEdit().text()))

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        if self._editing_suffix:
            suffix = self._editing_suffix
            self._editing_suffix = ""
            self.setSuffix(suffix)

    def _expression(self, text):
        value = text.strip()
        suffix = self.suffix().strip()
        prefix = self.prefix().strip()
        if prefix and value.startswith(prefix):
            value = value[len(prefix):].strip()
        if suffix and value.endswith(suffix):
            value = value[:-len(suffix)].strip()
        return value

    def validate(self, text, position):
        expression = self._expression(text)
        if not expression:
            state = QValidator.State.Intermediate
        elif any(character not in self._allowed for character in expression):
            state = QValidator.State.Invalid
        else:
            try:
                calculate(expression)
                state = QValidator.State.Acceptable
            except (SyntaxError, TypeError, ValueError, ZeroDivisionError):
                state = QValidator.State.Intermediate
        return state, text, position

    def valueFromText(self, text):
        expression = self._expression(text)
        try:
            result = float(calculate(expression).replace(",", "."))
        except (SyntaxError, TypeError, ValueError, ZeroDivisionError):
            return self.value()
        return min(self.maximum(), max(self.minimum(), result))
