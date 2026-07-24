from __future__ import annotations

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget


class GeometryWidget(QWidget):
    saveRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("geoPage")
        self.setAcceptDrops(True)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        card = QFrame()
        card.setObjectName("geoEmptyCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(28, 28, 28, 28)
        card_layout.setSpacing(10)
        card_layout.addStretch()

        title = QLabel("GEOMETRIA")
        title.setObjectName("geoEmptyTitle")
        title.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(title)

        self.status = QLabel(
            "Arraste um PDF em qualquer área da janela.\n"
            "A ferramenta de geometria será construída na próxima etapa."
        )
        self.status.setObjectName("geoEmptyText")
        self.status.setAlignment(Qt.AlignCenter)
        self.status.setWordWrap(True)
        card_layout.addWidget(self.status)
        card_layout.addStretch()
        root.addWidget(card, 1)

        bottom = QHBoxLayout()
        bottom.addStretch()
        self.save_button = QPushButton("SALVAR PDF")
        self.save_button.setObjectName("geoSave")
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self.saveRequested.emit)
        bottom.addWidget(self.save_button)
        root.addLayout(bottom)

        self.setStyleSheet("""
            QWidget#geoPage { background:#080a0d; }
            QFrame#geoEmptyCard { background:rgba(255,255,255,.018); border:1px dashed rgba(255,196,0,.28); border-radius:10px; }
            QLabel#geoEmptyTitle { color:#FFC400; font-size:13px; font-weight:700; letter-spacing:1px; }
            QLabel#geoEmptyText { color:rgba(255,255,255,.48); font-size:10px; }
            QPushButton#geoSave { min-width:190px; text-align:center; font-weight:700; background:rgba(255,196,0,.14); border:1px solid rgba(255,196,0,.30); border-radius:6px; padding:8px 14px; color:#FFC400; }
            QPushButton#geoSave:disabled { color:rgba(255,255,255,.24); border-color:rgba(255,255,255,.10); background:rgba(255,255,255,.025); }
        """)

    def set_pdf_state(self, paths):
        paths = list(paths or [])
        if not paths:
            self.status.setText(
                "Arraste um PDF em qualquer área da janela.\n"
                "A ferramenta de geometria será construída na próxima etapa."
            )
            self.save_button.setEnabled(False)
            return
        name = paths[0].split("/")[-1]
        suffix = "" if len(paths) == 1 else f"  •  +{len(paths)-1} PDF(s)"
        self.status.setText(
            f"PDF carregado: {name}{suffix}\n"
            "As configurações da aba IMP permanecem disponíveis para salvar."
        )
        self.save_button.setEnabled(True)
