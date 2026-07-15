from PySide6.QtCore import Qt, QSettings
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
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
    font-size: 12px;
}

QLabel#label {
    color: #8E9198;
    font-size: 9px;
    font-weight: 900;
    letter-spacing: 1px;
    margin-top: 4px;
}

QLabel#value {
    color: #E8E8E8;
    font-size: 12px;
    font-weight: 600;
}

QLabel#previewCaption {
    color: #8E9198;
    font-size: 10px;
}

QLabel#sectionTitle {
    color: #D0931D;
    font-size: 10px;
    font-weight: 900;
    letter-spacing: 1.2px;
    margin-bottom: 3px;
}

QLabel#warning {
    color: #D0931D;
    background: rgba(208, 147, 29, 0.10);
    border-left: 3px solid #D0931D;
    padding: 6px 8px;
    border-radius: 5px;
    font-size: 10px;
}

QFrame#line {
    background: #D0931D;
    max-height: 1px;
    min-height: 1px;
    margin-top: 7px;
    margin-bottom: 5px;
}

QPushButton {
    background: #D0931D;
    color: #111318;
    border: none;
    border-radius: 8px;
    padding: 7px 18px;
    font-size: 11px;
    font-weight: 900;
}

QPushButton:hover {
    background: #E0A735;
}

QPushButton:pressed {
    background: #B8821A;
}
"""


class PdfInfoDialog(QDialog):
    def __init__(self, info, parent=None):
        super().__init__(parent)

        self.info = info or {}

        self.settings = QSettings(
        "M87Tools",
        "M87Terminal",
        )

        self.setWindowTitle("INFO PDF")
        self.resize(980, 600)
        self.setMinimumSize(880, 540)
        self.setStyleSheet(DIALOG_STYLE)

        self.build_ui()

    # ========================================================
    # ESTRUTURA PRINCIPAL
    # ========================================================

    def build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(22, 18, 22, 16)
        main_layout.setSpacing(10)

        content_layout = QHBoxLayout()
        content_layout.setSpacing(24)

        content_layout.addWidget(
            self.build_preview_column()
        )

        content_layout.addWidget(
            self.build_information_area(),
            1,
        )

        main_layout.addLayout(content_layout, 1)
        main_layout.addLayout(self.build_button_row())

    # ========================================================
    # PREVIEW
    # ========================================================

    def build_preview_column(self):
        wrapper = QWidget()
        wrapper.setFixedWidth(300)

        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMinimumSize(280, 390)
        self.preview_label.setMaximumSize(280, 430)
        self.preview_label.setSizePolicy(
            QSizePolicy.Fixed,
            QSizePolicy.Expanding,
        )

        self.load_preview()

        caption = QLabel("Preview da primeira página")
        caption.setObjectName("previewCaption")
        caption.setAlignment(Qt.AlignCenter)

        layout.addStretch()
        layout.addWidget(
            self.preview_label,
            alignment=Qt.AlignCenter,
        )
        layout.addWidget(caption)
        layout.addStretch()

        return wrapper

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
                280,
                410,
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
    # ÁREA DE INFORMAÇÕES
    # ========================================================

    def build_information_area(self):
        wrapper = QWidget()

        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(26)

        left_column = self.build_left_column()
        right_column = self.build_right_column()

        layout.addWidget(left_column, 1)
        layout.addWidget(right_column, 1)

        return wrapper

    def build_left_column(self):
        wrapper = QWidget()

        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(1)

        self.add_section_title(
            layout,
            "ARQUIVO",
        )

        self.add_file_information(layout)

        self.add_separator(layout)

        self.add_section_title(
            layout,
            "MEDIDAS",
        )

        self.add_size_information(layout)
        self.add_trim_warning(layout)

        layout.addStretch()

        return wrapper

    def build_right_column(self):
        wrapper = QWidget()

        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(1)

        self.add_section_title(
            layout,
            "CORES E SEPARAÇÕES",
        )

        self.add_color_information(layout)

        layout.addStretch()

        return wrapper

    # ========================================================
    # INFORMAÇÕES DO ARQUIVO
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

    # ========================================================
    # MEDIDAS
    # ========================================================

    def add_size_information(self, layout):
        self.add_line(
            layout,
            "Medida do PDF",
            self.get_value("medida_pdf"),
        )

        self.add_line(
            layout,
            "Marca de corte / Trim",
            self.get_value("medida_trim"),
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
            "MediaBox usada como referência.",
        )

    # ========================================================
    # CORES E SEPARAÇÕES
    # ========================================================

    def add_color_information(self, layout):
        colors = self.info.get("cores", {})

        separation_lines = []

        color_items = [
            ("Ciano", "C"),
            ("Magenta", "M"),
            ("Amarelo", "Y"),
            ("Preto", "K"),
            ("RGB", "RGB"),
            ("Escala de cinza", "GRAY"),
        ]

        for label, key in color_items:
            mark = (
                "✓"
                if colors.get(key)
                else "□"
            )

            separation_lines.append(
                f"{mark}  {label}"
            )

        spots = colors.get("SPOTS", [])

        special_mark = (
            "✓"
            if spots
            else "□"
        )

        separation_lines.append(
            f"{special_mark}  Pantones / especiais"
        )

        self.add_line(
            layout,
            "Separações detectadas",
            "\n".join(separation_lines),
        )

        self.add_separator(layout)

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

    def add_section_title(self, layout, text):
        title = QLabel(str(text))
        title.setObjectName("sectionTitle")

        layout.addWidget(title)

    def add_line(self, layout, label, value):
        label_widget = QLabel(str(label))
        label_widget.setObjectName("label")

        value_widget = QLabel(str(value))
        value_widget.setObjectName("value")
        value_widget.setWordWrap(True)
        value_widget.setTextInteractionFlags(
            Qt.TextSelectableByMouse
        )

        layout.addWidget(label_widget)
        layout.addWidget(value_widget)

    def add_separator(self, layout):
        line = QFrame()
        line.setObjectName("line")
        line.setFrameShape(QFrame.HLine)

        layout.addWidget(line)

    def add_warning(self, layout, text):
        warning = QLabel(f"⚠ {text}")
        warning.setObjectName("warning")
        warning.setWordWrap(True)

        layout.addWidget(warning)

    def build_button_row(self):
        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(0, 0, 0, 0)

        button_layout.addStretch()

        close_button = QPushButton("OK")
        close_button.setFixedWidth(62)
        close_button.clicked.connect(self.accept)

        button_layout.addWidget(close_button)

        return button_layout
    
    # ========================================================
    # POSIÇÃO E TAMANHO DA JANELA
    # ========================================================

    def showEvent(self, event):
        super().showEvent(event)

        saved_geometry = self.settings.value(
            "pdf_info_dialog/geometry"
        )

        if saved_geometry:
            self.restoreGeometry(saved_geometry)

        self.ensure_window_is_visible()

    def closeEvent(self, event):
        self.settings.setValue(
            "pdf_info_dialog/geometry",
            self.saveGeometry(),
        )

        super().closeEvent(event)

    def accept(self):
        self.settings.setValue(
            "pdf_info_dialog/geometry",
            self.saveGeometry(),
        )

        super().accept()

    def reject(self):
        self.settings.setValue(
            "pdf_info_dialog/geometry",
            self.saveGeometry(),
        )

        super().reject()

    def ensure_window_is_visible(self):
        dialog_geometry = self.frameGeometry()

        screens = QApplication.screens()

        is_visible = any(
            screen.availableGeometry().intersects(
                dialog_geometry
            )
            for screen in screens
        )

        if is_visible:
            return

        screen = QApplication.primaryScreen()

        if screen is None:
            return

        available_geometry = screen.availableGeometry()

        corrected_geometry = self.frameGeometry()
        corrected_geometry.moveCenter(
            available_geometry.center()
        )

        self.move(corrected_geometry.topLeft())

          
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