from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


DIALOG_STYLE = """
QDialog {
    background: #111318;
    color: #E8E8E8;
}

QLabel {
    color: #E8E8E8;
    font-size: 14px;
}

QLabel#label {
    color: #8E9198;
    font-size: 11px;
    font-weight: 900;
    letter-spacing: 1.1px;
    margin-top: 7px;
}

QLabel#value {
    color: #E8E8E8;
    font-size: 15px;
    font-weight: 600;
}

QLabel#previewCaption {
    color: #8E9198;
    font-size: 12px;
}

QLabel#warning {
    color: #D0931D;
    background: rgba(208, 147, 29, 0.10);
    border-left: 3px solid #D0931D;
    padding: 8px 10px;
    border-radius: 6px;
    font-size: 13px;
}

QFrame#line {
    background: #272A30;
    max-height: 1px;
    min-height: 1px;
    margin-top: 12px;
    margin-bottom: 8px;
}

QScrollArea {
    border: none;
    background: transparent;
}

QScrollArea > QWidget > QWidget {
    background: transparent;
}

QPushButton {
    background: #D0931D;
    color: #111318;
    border: none;
    border-radius: 8px;
    padding: 8px 18px;
    font-weight: 900;
}

QPushButton:hover {
    background: #E0A735;
}
"""


class PdfInfoDialog(QDialog):
    def __init__(self, info, parent=None):
        super().__init__(parent)

        self.info = info or {}

        self.setWindowTitle("INFO PDF")
        self.resize(920, 660)
        self.setMinimumSize(760, 540)
        self.setStyleSheet(DIALOG_STYLE)

        self.build_ui()

    # ========================================================
    # ESTRUTURA PRINCIPAL
    # ========================================================

    def build_ui(self):
        root_layout = QHBoxLayout(self)
        root_layout.setContentsMargins(24, 24, 24, 18)
        root_layout.setSpacing(28)

        root_layout.addLayout(
            self.build_preview_column()
        )

        root_layout.addWidget(
            self.build_info_column(),
            1,
        )

    # ========================================================
    # PREVIEW
    # ========================================================

    def build_preview_column(self):
        layout = QVBoxLayout()
        layout.setSpacing(10)

        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMinimumWidth(320)
        self.preview_label.setMinimumHeight(450)

        self.load_preview()

        caption = QLabel("Preview da primeira página")
        caption.setObjectName("previewCaption")
        caption.setAlignment(Qt.AlignCenter)

        layout.addWidget(self.preview_label)
        layout.addWidget(caption)
        layout.addStretch()

        return layout

    def load_preview(self):
        preview_png = self.info.get(
            "preview_png",
            b"",
        )

        pixmap = QPixmap()

        if (
            preview_png
            and pixmap.loadFromData(
                preview_png,
                "PNG",
            )
        ):
            scaled_pixmap = pixmap.scaled(
                320,
                450,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )

            self.preview_label.setPixmap(
                scaled_pixmap
            )

        else:
            self.preview_label.setText(
                "Sem preview"
            )

    # ========================================================
    # COLUNA DE INFORMAÇÕES
    # ========================================================

    def build_info_column(self):
        wrapper = QWidget()

        wrapper_layout = QVBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)
        wrapper_layout.setSpacing(12)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)

        content = QWidget()

        info_layout = QVBoxLayout(content)
        info_layout.setContentsMargins(0, 0, 8, 0)
        info_layout.setSpacing(4)

        self.add_file_information(info_layout)
        self.add_separator(info_layout)
        self.add_size_information(info_layout)
        self.add_trim_warning(info_layout)
        self.add_separator(info_layout)
        self.add_color_information(info_layout)

        info_layout.addStretch()

        scroll_area.setWidget(content)

        wrapper_layout.addWidget(scroll_area)
        wrapper_layout.addLayout(
            self.build_button_row()
        )

        return wrapper

    # ========================================================
    # BLOCOS DE CONTEÚDO
    # ========================================================

    def add_file_information(self, layout):
        self.add_line(
            layout,
            "Nome do arquivo",
            self.get_value("nome"),
        )

        self.add_line(
            layout,
            "Peso",
            self.get_value("peso"),
        )

        self.add_line(
            layout,
            "Orientação",
            self.get_value("orientacao"),
        )

        self.add_line(
            layout,
            "Criado em",
            self.get_value("criado_em"),
        )

        self.add_line(
            layout,
            "Data de criação",
            self.get_value("data_criacao"),
        )

        self.add_line(
            layout,
            "Data de modificação",
            self.get_value("data_modificacao"),
        )

        self.add_line(
            layout,
            "Quantidade de páginas",
            self.get_value("paginas"),
        )

    def add_size_information(self, layout):
        self.add_line(
            layout,
            "Medida do PDF",
            self.get_value("medida_pdf"),
        )

        self.add_line(
            layout,
            "Medida da marca de corte / Trim",
            self.get_value("medida_trim"),
        )

        self.add_line(
            layout,
            "Medida do Bleed",
            self.get_value("medida_bleed"),
        )

        self.add_line(
            layout,
            "Medida do Crop",
            self.get_value("medida_crop"),
        )

        crop_marks_text = (
            "Sim"
            if self.info.get("marcas_corte")
            else "Não"
        )

        self.add_line(
            layout,
            "Marcas de corte detectadas",
            crop_marks_text,
        )

    def add_trim_warning(self, layout):
        if self.info.get("tem_trim"):
            return

        self.add_warning(
            layout,
            "TrimBox não definido. "
            "Usando MediaBox como referência.",
        )

    def add_color_information(self, layout):
        colors = self.info.get("cores", {})

        separation_lines = []

        for label, key in [
            ("Ciano", "C"),
            ("Magenta", "M"),
            ("Amarelo", "Y"),
            ("Preto", "K"),
            ("RGB", "RGB"),
            ("Escala de cinza", "GRAY"),
        ]:
            mark = (
                "✓"
                if colors.get(key)
                else "□"
            )

            separation_lines.append(
                f"{mark} {label}"
            )

        spots = colors.get("SPOTS", [])

        special_mark = "✓" if spots else "□"

        separation_lines.append(
            f"{special_mark} Pantones / especiais"
        )

        self.add_line(
            layout,
            "Separações detectadas",
            "\n".join(separation_lines),
        )

        self.add_line(
            layout,
            "Pantones / cores especiais",
            (
                "\n".join(spots)
                if spots
                else "Nenhuma detectada"
            ),
        )

    # ========================================================
    # COMPONENTES
    # ========================================================

    def add_line(self, layout, label, value):
        label_widget = QLabel(str(label))
        label_widget.setObjectName("label")

        value_widget = QLabel(str(value))
        value_widget.setObjectName("value")
        value_widget.setWordWrap(True)

        layout.addWidget(label_widget)
        layout.addWidget(value_widget)

    def add_separator(self, layout):
        line = QFrame()
        line.setObjectName("line")
        line.setFrameShape(QFrame.HLine)

        layout.addWidget(line)

    def add_warning(self, layout, text):
        warning = QLabel(f"⚠️ {text}")
        warning.setObjectName("warning")
        warning.setWordWrap(True)

        layout.addWidget(warning)

    def build_button_row(self):
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        close_button = QPushButton("OK")
        close_button.clicked.connect(self.accept)

        button_layout.addWidget(close_button)

        return button_layout

    # ========================================================
    # UTILITÁRIOS
    # ========================================================

    def get_value(self, key):
        value = self.info.get(key)

        if value in {
            None,
            "",
        }:
            return "Não informado"

        return str(value)