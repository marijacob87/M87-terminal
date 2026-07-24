from PySide6.QtCore import Qt

from core.state import save_window_state


class WindowBehaviorMixin:
    def resizeEvent(self, event):
        if hasattr(self, "size_grip"):
            margin = 3
            self.size_grip.move(
                self.width() - self.size_grip.width() - margin,
                self.height() - self.size_grip.height() - margin,
            )
            self.size_grip.raise_()

        if hasattr(self, "commands_grid"):
            self.rebuild_command_grid()

        if hasattr(self, "status"):
            self.render_status()

        # A altura normal representa o tamanho compacto do Terminal. Ela não
        # pode ser substituída por alturas temporárias criadas por sugestões,
        # resultados ou mensagens. O redimensionador manual altera apenas a
        # largura, portanto basta preservar a altura-base já calculada.
        if not self.auto_resizing:
            self.schedule_state_save()

        super().resizeEvent(event)

    def schedule_state_save(self):
        self.save_state_timer.start(500)

    def save_current_state(self):
        geometry = self.geometry()
        # Nunca grava no estado uma altura temporária de conteúdo variável.
        # Assim o Terminal também volta compacto após reiniciar.
        height = self.normal_height

        save_window_state(
            geometry.x(),
            geometry.y(),
            geometry.width(),
            height,
        )

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_position = (
                event.globalPosition().toPoint()
                - self.frameGeometry().topLeft()
            )
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.drag_position and event.buttons() == Qt.LeftButton:
            self.move(
                event.globalPosition().toPoint()
                - self.drag_position
            )
            self.schedule_state_save()
            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self.drag_position = None
        super().mouseReleaseEvent(event)
