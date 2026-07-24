from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QMimeData, QPoint, QRectF, QSettings, Qt, QTimer
from PySide6.QtGui import QCursor, QDragEnterEvent, QDropEvent, QIcon, QImage, QKeySequence, QPainter, QPixmap, QShortcut
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QSizeGrip,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ui.widgets import DarkMetallicTitleBar

from core.code_tools import (
    generate_ean13_svg,
    generate_qr_png,
    generate_qr_svg,
    load_image_for_reader,
    normalize_ean13,
    read_codes_from_image,
)


STYLE = f"""
QWidget {{ font-family: "JetBrains Mono"; font-size: 10px; color: #FFC400; }}
QWidget#barBox {{ background: rgba(0,0,0,232); border: 1px solid rgba(255,196,0,.20); border-radius: 13px; }}
QLabel#barWindowTitle {{ color: white; font-size: 10px; letter-spacing: 1px; }}
QLabel#barClose {{ color: white; font-size: 16px; padding: 0 4px; }}
QLabel#barClose:hover {{ color: #FFC400; }}
QLabel {{ color: rgba(255,255,255,.82); }}
QLabel#sectionTitle {{ color: rgba(255,196,0,.75); font-size: 9px; font-weight: 600; letter-spacing: 1px; padding-top: 6px; border-bottom: 1px solid rgba(255,196,0,.16); }}
QLabel#muted {{ color: rgba(255,255,255,.45); font-size: 9px; }}
QLabel#statusOk {{ color: #70d878; font-weight: 700; }}
QLabel#statusError {{ color: #FFC400; font-weight: 700; }}
QLabel#value {{ color: white; font-weight: 700; }}
QFrame#line {{ background: rgba(255,196,0,.16); max-height: 1px; min-height: 1px; }}
QFrame#panel {{ background: rgba(255,255,255,.025); border: 1px solid rgba(255,196,0,.16); border-radius: 8px; }}
QLineEdit, QTextEdit, QSpinBox, QComboBox {{ background: rgba(255,255,255,.07); color: white; border: 1px solid rgba(255,255,255,.14); border-radius: 5px; padding: 6px 8px; min-height: 22px; }}
QLineEdit:focus, QTextEdit:focus, QSpinBox:focus, QComboBox:focus {{ border: 1px solid #FFC400; }}
QPushButton {{ background: rgba(255,255,255,.055); border: 1px solid rgba(255,196,0,.25); border-radius: 6px; padding: 7px 12px; color: rgba(255,196,0,.82); font-weight: 600; }}
QPushButton:hover {{ color: #fff0a0; border-color: rgba(255,196,0,.55); }}
QPushButton:pressed {{ background: rgba(255,196,0,.12); }}
QPushButton#secondary {{ background: transparent; color: rgba(255,196,0,.82); border: 1px solid rgba(255,196,0,.25); }}
QTabWidget::pane {{ border: 1px solid rgba(255,196,0,.16); border-radius: 8px; top: -1px; background: rgba(255,255,255,.015); }}
QTabBar::tab {{ background: rgba(255,255,255,.025); color: rgba(255,255,255,.55); border: 1px solid rgba(255,196,0,.13); padding: 9px 24px; min-width: 120px; font-weight: 600; }}
QTabBar::tab:selected {{ color: #FFC400; border-color: #FFC400; background: rgba(255,196,0,.08); }}
"""


class SvgPreview(QLabel):
    def __init__(self, parent=None, max_square: int | None = None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(320, 260)
        self.setObjectName("preview")
        self.setStyleSheet("background:#FFFFFF; border:1px solid rgba(255,196,0,.18); border-radius:8px; color:#555;")
        self._svg = b""
        self._max_square = max_square

    def set_svg(self, data: bytes):
        self._svg = data or b""
        if not self._svg:
            self.clear()
            self.setText("Prévia")
            return

        renderer = QSvgRenderer(QByteArray(self._svg))
        image = QImage(self.size(), QImage.Format_ARGB32)
        image.fill(Qt.white)
        painter = QPainter(image)

        source_size = renderer.defaultSize()
        if source_size.width() <= 0 or source_size.height() <= 0:
            source_ratio = 1.0
        else:
            source_ratio = source_size.width() / source_size.height()

        available_w = max(1, self.width() - 28)
        available_h = max(1, self.height() - 28)
        if self._max_square:
            available_w = min(available_w, self._max_square)
            available_h = min(available_h, self._max_square)

        if source_ratio >= available_w / available_h:
            target_w = available_w
            target_h = target_w / source_ratio
        else:
            target_h = available_h
            target_w = target_h * source_ratio

        target = QRectF(
            (self.width() - target_w) / 2,
            (self.height() - target_h) / 2,
            target_w,
            target_h,
        )
        renderer.render(painter, target)
        painter.end()
        self.setPixmap(QPixmap.fromImage(image))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._svg:
            QTimer.singleShot(0, lambda: self.set_svg(self._svg))


class ImagePreview(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumHeight(230)
        self.setStyleSheet("background:#FFFFFF; border:1px solid rgba(255,196,0,.18); border-radius:8px; color:#555;")
        self._source = QPixmap()
        self.setText("Prévia do código")

    def set_image(self, image: QImage):
        if image.isNull():
            self.clear_image()
            return
        self._source = QPixmap.fromImage(image)
        self._refresh()

    def clear_image(self):
        self._source = QPixmap()
        self.clear()
        self.setText("Prévia do código")

    def _refresh(self):
        if self._source.isNull():
            return
        self.setPixmap(
            self._source.scaled(
                max(1, self.width() - 20),
                max(1, self.height() - 20),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._refresh()


class CodeGeneratorDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings = QSettings("M87Tools", "M87Terminal")
        self.drag_position = QPoint()
        self.ean_svg = b""
        self.qr_svg = b""
        self.qr_png = b""
        self.reader_image = None

        self.setWindowTitle("BAR · GERADOR DE CÓDIGOS")
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.resize(1120, 700)
        self.setMinimumSize(980, 620)
        icon = Path(__file__).resolve().parent.parent / "assets" / "m87_icon.png"
        if icon.exists():
            self.setWindowIcon(QIcon(str(icon)))
        self.setStyleSheet(STYLE)
        self.setAcceptDrops(True)

        self._build_ui()
        self._restore_geometry()
        QShortcut(QKeySequence(Qt.Key_Escape), self, activated=self.close)


    def _title_press(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def _title_move(self, event):
        if event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.box = QWidget()
        self.box.setObjectName("barBox")
        outer.addWidget(self.box)

        root = QVBoxLayout(self.box)
        root.setContentsMargins(0, 0, 0, 8)
        root.setSpacing(5)

        bar = DarkMetallicTitleBar(height=28, radius=12)
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(14, 0, 10, 0)
        title = QLabel("M87 TERMINAL · BAR · GERADOR DE CÓDIGOS")
        title.setObjectName("barWindowTitle")
        close = QLabel("×")
        close.setObjectName("barClose")
        close.setCursor(QCursor(Qt.PointingHandCursor))
        close.mousePressEvent = lambda event: self.close()
        bar_layout.addWidget(title)
        bar_layout.addStretch()
        bar_layout.addWidget(close)
        root.addWidget(bar)
        bar.mousePressEvent = self._title_press
        bar.mouseMoveEvent = self._title_move

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_ean_tab(), "▥  EAN-13")
        self.tabs.addTab(self._build_qr_tab(), "▦  QR CODE")
        self.tabs.addTab(self._build_reader_tab(), "⌗  LEITOR")
        tabs_wrap = QHBoxLayout()
        tabs_wrap.setContentsMargins(14, 2, 14, 0)
        tabs_wrap.addWidget(self.tabs)
        root.addLayout(tabs_wrap, 1)

        bottom = QHBoxLayout()
        bottom.setContentsMargins(14, 0, 8, 0)
        clear_btn = QPushButton("LIMPAR TUDO")
        clear_btn.setObjectName("secondary")
        clear_btn.clicked.connect(self.clear_all)
        close_btn = QPushButton("FECHAR")
        close_btn.setObjectName("secondary")
        close_btn.clicked.connect(self.close)
        bottom.addWidget(clear_btn)
        bottom.addStretch()
        bottom.addWidget(close_btn)
        bottom.addWidget(QSizeGrip(self.box))
        root.addLayout(bottom)

    def _panel(self):
        frame = QFrame()
        frame.setObjectName("panel")
        return frame

    def _section(self, text):
        label = QLabel(text)
        label.setObjectName("sectionTitle")
        return label

    def _line(self):
        line = QFrame()
        line.setObjectName("line")
        return line

    def _build_ean_tab(self):
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(24)

        left = self._panel()
        left.setFixedWidth(390)
        form = QVBoxLayout(left)
        form.setContentsMargins(18, 16, 18, 16)
        form.setSpacing(10)
        form.addWidget(self._section("DADOS"))
        form.addWidget(QLabel("Número (12 ou 13 dígitos)"))
        self.ean_input = QLineEdit()
        self.ean_input.setPlaceholderText("560123456789")
        self.ean_input.setMaxLength(13)
        self.ean_input.textChanged.connect(self.update_ean)
        form.addWidget(self.ean_input)

        self.ean_status = QLabel("Digite um código.")
        self.ean_status.setObjectName("muted")
        form.addWidget(self.ean_status)
        form.addWidget(self._line())
        form.addWidget(self._section("INFORMAÇÕES"))

        info = QGridLayout()
        info.setHorizontalSpacing(12)
        info.setVerticalSpacing(10)
        self.ean_full = QLabel("—")
        self.ean_digit = QLabel("—")
        self.ean_structure = QLabel("—")
        for value in (self.ean_full, self.ean_digit, self.ean_structure):
            value.setObjectName("value")
            value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        info.addWidget(QLabel("Código completo"), 0, 0)
        info.addWidget(self.ean_full, 0, 1)
        info.addWidget(QLabel("Dígito verificador"), 1, 0)
        info.addWidget(self.ean_digit, 1, 1)
        info.addWidget(QLabel("Estrutura"), 2, 0)
        info.addWidget(self.ean_structure, 2, 1)
        form.addLayout(info)
        form.addStretch()

        right = self._panel()
        preview_layout = QVBoxLayout(right)
        preview_layout.setContentsMargins(18, 16, 18, 16)
        preview_layout.setSpacing(12)
        preview_layout.addWidget(self._section("PRÉVIA"))
        self.ean_preview = SvgPreview()
        preview_layout.addWidget(self.ean_preview, 1)
        note = QLabel("A visualização é apenas para referência. Para impressão, use o SVG.")
        note.setObjectName("muted")
        note.setAlignment(Qt.AlignCenter)
        preview_layout.addWidget(note)

        buttons = QHBoxLayout()
        copy_svg = QPushButton("COPIAR SVG")
        copy_svg.setObjectName("secondary")
        copy_svg.clicked.connect(lambda: self.copy_svg(self.ean_svg))
        save_svg = QPushButton("BAIXAR SVG")
        save_svg.setObjectName("secondary")
        save_svg.clicked.connect(lambda: self.save_svg(self.ean_svg, "ean13.svg"))
        buttons.addStretch()
        buttons.addWidget(copy_svg)
        buttons.addWidget(save_svg)
        buttons.addStretch()
        preview_layout.addLayout(buttons)

        layout.addWidget(left)
        layout.addWidget(right, 1)
        return page

    def _build_qr_tab(self):
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(24)

        left = self._panel()
        left.setFixedWidth(390)
        form = QVBoxLayout(left)
        form.setContentsMargins(18, 16, 18, 16)
        form.setSpacing(10)
        form.addWidget(self._section("DADOS"))
        form.addWidget(QLabel("Tipo / sugestão rápida"))
        self.qr_template = QComboBox()
        self.qr_templates = {
            "Texto livre": "",
            "URL": "https://exemplo.com",
            "E-mail": "mailto:nome@exemplo.com",
            "Telefone": "tel:+351912345678",
            "SMS": "sms:+351912345678?body=Olá",
            "WhatsApp": "https://wa.me/351912345678?text=Olá",
            "Wi-Fi": "WIFI:T:WPA;S:NOME_DA_REDE;P:SENHA;;",
            "Contato (vCard)": "BEGIN:VCARD\nVERSION:3.0\nFN:Nome Completo\nTEL:+351912345678\nEMAIL:nome@exemplo.com\nEND:VCARD",
            "Localização": "geo:41.1579,-8.6291",
            "Evento": "BEGIN:VEVENT\nSUMMARY:Título do evento\nDTSTART:20260716T180000\nDTEND:20260716T190000\nLOCATION:Local\nEND:VEVENT",
        }
        self.qr_template.addItems(self.qr_templates.keys())
        self.qr_template.currentTextChanged.connect(self.apply_qr_template)
        form.addWidget(self.qr_template)
        form.addWidget(QLabel("Texto, URL ou conteúdo"))
        self.qr_input = QTextEdit()
        self.qr_input.setPlaceholderText("Ex.: https://...  |  mailto:...  |  tel:+351...")
        self.qr_input.setMinimumHeight(130)
        self.qr_input.textChanged.connect(self.update_qr)
        form.addWidget(self.qr_input)

        grid = QGridLayout()
        grid.addWidget(QLabel("Margem"), 0, 0)
        grid.addWidget(QLabel("Correção de erro"), 0, 1)
        self.qr_border = QSpinBox()
        self.qr_border.setRange(0, 10)
        self.qr_border.setValue(2)
        self.qr_border.valueChanged.connect(self.update_qr)
        self.qr_error = QComboBox()
        self.qr_error.addItems(["L", "M", "Q", "H"])
        self.qr_error.setCurrentText("M")
        self.qr_error.currentTextChanged.connect(self.update_qr)
        grid.addWidget(self.qr_border, 1, 0)
        grid.addWidget(self.qr_error, 1, 1)
        form.addLayout(grid)
        form.addWidget(self._line())
        form.addWidget(self._section("INFORMAÇÕES"))
        self.qr_status = QLabel("Digite um conteúdo.")
        self.qr_status.setObjectName("muted")
        self.qr_chars = QLabel("0 caracteres")
        self.qr_chars.setObjectName("value")
        form.addWidget(self.qr_status)
        form.addWidget(self.qr_chars)
        form.addStretch()

        right = self._panel()
        preview_layout = QVBoxLayout(right)
        preview_layout.setContentsMargins(18, 16, 18, 16)
        preview_layout.setSpacing(12)
        preview_layout.addWidget(self._section("PRÉVIA"))
        self.qr_preview = SvgPreview(max_square=430)
        preview_layout.addWidget(self.qr_preview, 1)

        buttons = QHBoxLayout()
        copy_svg = QPushButton("COPIAR SVG")
        copy_svg.setObjectName("secondary")
        copy_svg.clicked.connect(lambda: self.copy_svg(self.qr_svg))
        copy_png = QPushButton("COPIAR PNG")
        copy_png.setObjectName("secondary")
        copy_png.clicked.connect(self.copy_qr_png)
        save_svg = QPushButton("BAIXAR SVG")
        save_svg.setObjectName("secondary")
        save_svg.clicked.connect(lambda: self.save_svg(self.qr_svg, "qrcode.svg"))
        buttons.addStretch()
        buttons.addWidget(copy_svg)
        buttons.addWidget(copy_png)
        buttons.addWidget(save_svg)
        buttons.addStretch()
        preview_layout.addLayout(buttons)

        layout.addWidget(left)
        layout.addWidget(right, 1)
        return page

    def _build_reader_tab(self):
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(24)

        left = self._panel()
        left.setFixedWidth(430)
        form = QVBoxLayout(left)
        form.setContentsMargins(18, 16, 18, 16)
        form.setSpacing(12)
        form.addWidget(self._section("FONTE"))
        self.reader_drop = QLabel(
            "Arraste um PDF ou imagem aqui\n"
            "ou use COLAR para ler uma imagem copiada"
        )
        self.reader_drop.setAlignment(Qt.AlignCenter)
        self.reader_drop.setMinimumHeight(105)
        self.reader_drop.setStyleSheet("border:1px dashed #636872; border-radius:8px; color:#BFC2C8;")
        form.addWidget(self.reader_drop)

        source_buttons = QHBoxLayout()
        select_btn = QPushButton("SELECIONAR ARQUIVO")
        select_btn.setObjectName("secondary")
        select_btn.clicked.connect(self.select_reader_file)
        paste_btn = QPushButton("COLAR IMAGEM")
        paste_btn.setObjectName("secondary")
        paste_btn.clicked.connect(self.paste_reader_image)
        source_buttons.addWidget(select_btn)
        source_buttons.addWidget(paste_btn)
        form.addLayout(source_buttons)

        paste_hint = QLabel("Atalho na aba Leitor: ⌘V")
        paste_hint.setObjectName("muted")
        paste_hint.setAlignment(Qt.AlignCenter)
        form.addWidget(paste_hint)
        form.addWidget(self._line())
        form.addWidget(self._section("PRÉVIA"))
        self.reader_preview = ImagePreview()
        form.addWidget(self.reader_preview, 1)
        self.reader_status = QLabel("Nenhum arquivo ou imagem colada.")
        self.reader_status.setObjectName("muted")
        self.reader_status.setWordWrap(True)
        form.addWidget(self.reader_status)

        right = self._panel()
        result_layout = QVBoxLayout(right)
        result_layout.setContentsMargins(18, 16, 18, 16)
        result_layout.setSpacing(12)
        result_layout.addWidget(self._section("CÓDIGO ENCONTRADO"))
        self.reader_type = QLabel("—")
        self.reader_value = QTextEdit()
        self.reader_value.setReadOnly(True)
        self.reader_value.setMinimumHeight(180)
        self.reader_valid = QLabel("—")
        self.reader_type.setObjectName("value")
        self.reader_valid.setObjectName("value")

        grid = QGridLayout()
        grid.addWidget(QLabel("Tipo"), 0, 0)
        grid.addWidget(self.reader_type, 0, 1)
        grid.addWidget(QLabel("Status"), 1, 0)
        grid.addWidget(self.reader_valid, 1, 1)
        result_layout.addLayout(grid)
        result_layout.addWidget(QLabel("Valor"))
        result_layout.addWidget(self.reader_value)
        copy_btn = QPushButton("COPIAR VALOR")
        copy_btn.setObjectName("secondary")
        copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(self.reader_value.toPlainText()))
        result_layout.addWidget(copy_btn, alignment=Qt.AlignRight)
        result_layout.addStretch()

        layout.addWidget(left)
        layout.addWidget(right, 1)
        return page

    def apply_qr_template(self, template_name: str):
        template = self.qr_templates.get(template_name, "")
        if not template:
            self.qr_input.setPlaceholderText(
                "Ex.: https://...  |  mailto:...  |  tel:+351..."
            )
            return
        self.qr_input.setPlainText(template)
        self.qr_input.setFocus()
        cursor = self.qr_input.textCursor()
        cursor.select(cursor.SelectionType.Document)
        self.qr_input.setTextCursor(cursor)

    def update_ean(self):
        code, message = normalize_ean13(self.ean_input.text())
        if not code:
            self.ean_svg = b""
            self.ean_preview.set_svg(b"")
            self.ean_full.setText("—")
            self.ean_digit.setText("—")
            self.ean_structure.setText("—")
            self.ean_status.setObjectName("statusError" if self.ean_input.text() else "muted")
            self.ean_status.setText(message)
            self.ean_status.style().unpolish(self.ean_status)
            self.ean_status.style().polish(self.ean_status)
            return
        self.ean_svg = generate_ean13_svg(code)
        self.ean_preview.set_svg(self.ean_svg)
        self.ean_full.setText(code)
        self.ean_digit.setText(code[-1])
        self.ean_structure.setText(f"{code[:3]} {code[3:9]} {code[9:12]} {code[12]}")
        self.ean_status.setObjectName("statusOk")
        self.ean_status.setText("✓ " + message)
        self.ean_status.style().unpolish(self.ean_status)
        self.ean_status.style().polish(self.ean_status)

    def update_qr(self):
        content = self.qr_input.toPlainText().strip()
        self.qr_chars.setText(f"{len(content)} caracteres")
        if not content:
            self.qr_svg = b""
            self.qr_png = b""
            self.qr_preview.set_svg(b"")
            self.qr_status.setText("Digite um conteúdo.")
            self.qr_status.setObjectName("muted")
            return
        try:
            self.qr_svg = generate_qr_svg(content, self.qr_border.value(), 8, self.qr_error.currentText())
            self.qr_png = generate_qr_png(content, self.qr_border.value(), 12, self.qr_error.currentText())
            self.qr_preview.set_svg(self.qr_svg)
            self.qr_status.setText("✓ QR Code pronto")
            self.qr_status.setObjectName("statusOk")
        except Exception as error:
            self.qr_status.setText(str(error))
            self.qr_status.setObjectName("statusError")
        self.qr_status.style().unpolish(self.qr_status)
        self.qr_status.style().polish(self.qr_status)

    def copy_svg(self, data: bytes):
        if not data:
            return
        mime = QMimeData()
        mime.setData("image/svg+xml", QByteArray(data))
        mime.setText(data.decode("utf-8", errors="ignore"))
        QApplication.clipboard().setMimeData(mime)

    def copy_qr_png(self):
        if not self.qr_png:
            return
        image = QImage.fromData(self.qr_png, "PNG")
        if not image.isNull():
            QApplication.clipboard().setImage(image)

    def save_svg(self, data: bytes, default_name: str):
        if not data:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Salvar SVG", str(Path.home() / "Desktop" / default_name), "SVG (*.svg)")
        if path:
            if not path.lower().endswith(".svg"):
                path += ".svg"
            Path(path).write_bytes(data)

    def select_reader_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Selecionar PDF ou imagem", str(Path.home()), "PDF e imagens (*.pdf *.png *.jpg *.jpeg *.tif *.tiff *.bmp *.webp)")
        if path:
            self.read_file(path)

    def _pil_to_qimage(self, image: Image.Image) -> QImage:
        buffer = BytesIO()
        image.convert("RGB").save(buffer, format="PNG")
        return QImage.fromData(buffer.getvalue(), "PNG")

    def _show_reader_result(self, image: Image.Image, results: list[dict[str, str]], source_name: str):
        self.reader_image = image
        self.reader_preview.set_image(self._pil_to_qimage(image))
        self.reader_drop.setText(source_name)

        if not results:
            self.reader_type.setText("—")
            self.reader_value.clear()
            self.reader_valid.setText("Não encontrado")
            self.reader_status.setText("Nenhum EAN ou QR Code foi encontrado na imagem.")
            return

        first = results[0]
        self.reader_type.setText(first["type"])
        self.reader_value.setPlainText(first["value"])
        self.reader_valid.setText("Válido" if first["valid"] == "Sim" else "Não validado")
        suffix = f" · {len(results)} códigos encontrados" if len(results) > 1 else ""
        self.reader_status.setText("Código lido com sucesso" + suffix)

    def read_file(self, path: str):
        try:
            self.reader_status.setText("Lendo código...")
            QApplication.processEvents()
            image = load_image_for_reader(path)
            results = read_codes_from_image(image)
            self._show_reader_result(image, results, Path(path).name)
        except Exception as error:
            self.reader_status.setText(f"Não foi possível ler: {error}")

    def paste_reader_image(self):
        clipboard = QApplication.clipboard()
        mime = clipboard.mimeData()

        if mime.hasImage():
            qimage = clipboard.image()
            if qimage.isNull():
                self.reader_status.setText("A imagem copiada não pôde ser aberta.")
                return
            buffer = QBuffer()
            buffer.open(QIODevice.WriteOnly)
            qimage.save(buffer, "PNG")
            image = Image.open(BytesIO(bytes(buffer.data()))).convert("RGB")
            try:
                self.reader_status.setText("Lendo imagem colada...")
                QApplication.processEvents()
                results = read_codes_from_image(image)
                self._show_reader_result(image, results, "Imagem colada da área de transferência")
            except Exception as error:
                self.reader_status.setText(f"Não foi possível ler: {error}")
            return

        if mime.hasUrls():
            urls = mime.urls()
            if urls and urls[0].isLocalFile():
                self.read_file(urls[0].toLocalFile())
                return

        self.reader_status.setText(
            "A área de transferência não contém uma imagem ou arquivo compatível."
        )


    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        if urls:
            self.tabs.setCurrentIndex(2)
            self.read_file(urls[0].toLocalFile())
            event.acceptProposedAction()

    def clear_all(self):
        self.ean_input.clear()
        self.qr_input.clear()
        self.reader_drop.setText(
            "Arraste um PDF ou imagem aqui\n"
            "ou use COLAR para ler uma imagem copiada"
        )
        self.reader_preview.clear_image()
        self.reader_image = None
        self.reader_status.setText("Nenhum arquivo ou imagem colada.")
        self.reader_type.setText("—")
        self.reader_value.clear()
        self.reader_valid.setText("—")

    def keyPressEvent(self, event):
        if self.tabs.currentIndex() == 2 and event.matches(QKeySequence.Paste):
            self.paste_reader_image()
            event.accept()
            return
        super().keyPressEvent(event)

    def _restore_geometry(self):
        geometry = self.settings.value("code_generator_geometry")
        if geometry:
            self.restoreGeometry(geometry)
        else:
            screen = QApplication.primaryScreen().availableGeometry()
            self.move(screen.center() - self.rect().center())

    def closeEvent(self, event):
        self.settings.setValue("code_generator_geometry", self.saveGeometry())
        super().closeEvent(event)
