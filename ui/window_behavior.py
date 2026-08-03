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
        position = getattr(
            self,
            "locked_window_position",
            geometry.topLeft(),
        )

        save_window_state(
            position.x(),
            position.y(),
            geometry.width(),
            height,
        )

    def mousePressEvent(self, event):
        # A janela principal fica fixa no canto superior esquerdo.
        # Diálogos e ferramentas preservam o comportamento próprio de arraste.
        self.drag_position = None
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self.drag_position = None
        super().mouseReleaseEvent(event)
