from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QScrollArea,
    QFrame,
    QPushButton,
)


class PdfInfoDialog(QDialog):
    def __init__(self, info, parent=None):
        super().__init__(parent)
        self.info = info

        self.setWindowTitle("INFO PDF")
        self.resize(920, 660)
        self.setMinimumSize(760, 540)

        self.setStyleSheet(
            """
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
                text-transform: uppercase;
                margin-top: 7px;
            }
            QLabel#value {
                color: #E8E8E8;
                font-size: 15px;
                font-weight: 600;
                line-height: 1.25;
            }
            QLabel#previewCaption {
                color: #8E9198;
                font-size: 12px;
            }
            QLabel#warning {
                color: #D0931D;
                background: rgba(208,147,29,0.10);
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
        )

        self.build_ui()

    def build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 18)
        root.setSpacing(28)

        root.addLayout(self.build_preview_column())
        root.addWidget(self.build_info_column(), 1)

    def build_preview_column(self):
        layout = QVBoxLayout()
        layout.setSpacing(10)

        preview = QLabel()
        preview.setAlignment(Qt.AlignCenter)
        preview.setMinimumWidth(320)
        preview.setMinimumHeight(450)

        pixmap = QPixmap()
        preview_png = self.info.get("preview_png", b"")

        if preview_png and pixmap.loadFromData(preview_png, "PNG"):
            preview.setPixmap(
                pixmap.scaled(
                    320,
                    450,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                )
            )
        else:
            preview.setText("Sem preview")

        caption = QLabel("Preview da primeira página")
        caption.setObjectName("previewCaption")
        caption.setAlignment(Qt.AlignCenter)

        layout.addWidget(preview)
        layout.addWidget(caption)
        layout.addStretch()

        return layout

    def build_info_column(self):
        wrapper = QWidget()
        wrapper_layout = QVBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)
        wrapper_layout.setSpacing(12)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        content = QWidget()
        info_layout = QVBoxLayout(content)
        info_layout.setContentsMargins(0, 0, 8, 0)
        info_layout.setSpacing(4)

        self.add_line(info_layout, "Nome do arquivo", self.info.get("nome", "Não informado"))
        self.add_line(info_layout, "Peso", self.info.get("peso", "Não informado"))
        self.add_line(info_layout, "Orientação", self.info.get("orientacao", "Não informado"))
        self.add_line(info_layout, "Criado em", self.info.get("criado_em", "Não informado"))
        self.add_line(info_layout, "Data de criação", self.info.get("data_criacao", "Não informado"))
        self.add_line(info_layout, "Quantidade de páginas", self.info.get("paginas", "Não informado"))

        self.add_separator(info_layout)

        self.add_line(info_layout, "Medida do PDF", self.info.get("medida_pdf", "Não informado"))
        self.add_line(info_layout, "Medida da marca de corte / Trim", self.info.get("medida_trim", "Não informado"))
        self.add_line(info_layout, "Medida do Bleed", self.info.get("medida_bleed", "Não informado"))
        self.add_line(info_layout, "Medida do Crop", self.info.get("medida_crop", "Não informado"))
        self.add_line(
            info_layout,
            "Marcas de corte detectadas",
            "Sim" if self.info.get("marcas_corte") else "Não",
        )

        if not self.info.get("tem_trim"):
            self.add_warning(info_layout, "TrimBox não definido. Usando MediaBox como referência.")

        self.add_separator(info_layout)
        self.add_separacoes(info_layout)

        info_layout.addStretch()
        scroll.setWidget(content)

        button_row = QHBoxLayout()
        button_row.addStretch()
        close_btn = QPushButton("OK")
        close_btn.clicked.connect(self.accept)
        button_row.addWidget(close_btn)

        wrapper_layout.addWidget(scroll)
        wrapper_layout.addLayout(button_row)

        return wrapper

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

    def add_separacoes(self, layout):
        cores = self.info.get("cores", {})

        checks = []
        for label, key in [
            ("Ciano", "C"),
            ("Magenta", "M"),
            ("Amarelo", "Y"),
            ("Preto", "K"),
            ("RGB", "RGB"),
        ]:
            checks.append(f'{"✓" if cores.get(key) else "□"} {label}')

        spots = cores.get("SPOTS", [])
        checks.append(f'{"✓" if spots else "□"} Pantones / especiais')

        self.add_line(layout, "Separações detectadas", "\n".join(checks))
        self.add_line(
            layout,
            "Pantones / cores especiais",
            "\n".join(spots) if spots else "Nenhuma detectada",
        )
