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
import os
import re
from datetime import datetime
from io import BytesIO

import fitz
import pikepdf


MM_PER_POINT = 25.4 / 72
POINT_PER_MM = 72 / 25.4

PROCESS_COLORS = {
    "Cyan": "C",
    "C": "C",
    "Magenta": "M",
    "M": "M",
    "Yellow": "Y",
    "Y": "Y",
    "Black": "K",
    "K": "K",
}

IGNORE_SPOT_NAMES = {"All", "None", "Registration"}


def pt_to_mm(valor):
    return round(float(valor) * MM_PER_POINT, 2)


def mm_to_pt(valor):
    return float(valor) * POINT_PER_MM


def box_to_mm(box):
    largura_pt = float(box[2]) - float(box[0])
    altura_pt = float(box[3]) - float(box[1])
    return pt_to_mm(largura_pt), pt_to_mm(altura_pt)


def formatar_mm(largura, altura):
    return f"{largura:.1f} mm x {altura:.1f} mm"


def orientacao(largura, altura):
    if abs(largura - altura) < 0.5:
        return "Quadrado"
    if largura > altura:
        return "Paisagem"
    return "Retrato"


def formatar_data_pdf(data_pdf):
    if not data_pdf:
        return "Não informado"

    try:
        limpa = str(data_pdf).replace("D:", "")
        data = datetime.strptime(limpa[:14], "%Y%m%d%H%M%S")
        return data.strftime("%d/%m/%Y às %H:%M")
    except Exception:
        return str(data_pdf)


def formatar_peso(bytes_total):
    if bytes_total < 1024 * 1024:
        return f"{bytes_total / 1024:.1f} KB"
    return f"{bytes_total / (1024 * 1024):.2f} MB"


def analisar_boxes(pdf_bytes):
    paginas = []

    with pikepdf.open(BytesIO(pdf_bytes)) as pdf:
        for numero, pagina in enumerate(pdf.pages, start=1):
            media = pagina.get("/MediaBox")
            trim = pagina.get("/TrimBox")
            bleed = pagina.get("/BleedBox")
            crop = pagina.get("/CropBox")

            media_mm = box_to_mm(media)
            trim_mm = box_to_mm(trim) if trim else media_mm
            bleed_mm = box_to_mm(bleed) if bleed else media_mm
            crop_mm = box_to_mm(crop) if crop else media_mm

            paginas.append(
                {
                    "pagina": numero,
                    "media": media_mm,
                    "trim": trim_mm,
                    "bleed": bleed_mm,
                    "crop": crop_mm,
                    "tem_trim": trim is not None,
                    "tem_bleed": bleed is not None,
                    "tem_crop": crop is not None,
                }
            )

    return paginas


def nome_pdf_para_texto(nome):
    nome = str(nome).replace("/", "")

    def trocar_hex(match):
        try:
            return chr(int(match.group(1), 16))
        except Exception:
            return ""

    return re.sub(r"#([0-9A-Fa-f]{2})", trocar_hex, nome).strip()


def marcar_processo(nome_cor, resultado):
    nome_cor = nome_pdf_para_texto(nome_cor)

    if nome_cor in PROCESS_COLORS:
        canal = PROCESS_COLORS[nome_cor]
        resultado[canal] = True
        resultado["CMYK"] = True
        return

    if nome_cor and nome_cor not in IGNORE_SPOT_NAMES:
        resultado["SPOTS"].add(nome_cor)


def marcar_cmyk(c, m, y, k, resultado):
    if c > 0:
        resultado["C"] = True
    if m > 0:
        resultado["M"] = True
    if y > 0:
        resultado["Y"] = True
    if k > 0:
        resultado["K"] = True

    if c > 0 or m > 0 or y > 0 or k > 0:
        resultado["CMYK"] = True


def analisar_color_space(color_space, resultado, mapa_cores=None):
    try:
        if isinstance(color_space, pikepdf.Name):
            nome = nome_pdf_para_texto(color_space)

            if nome == "DeviceCMYK":
                resultado["CMYK"] = True
            elif nome == "DeviceRGB":
                resultado["RGB"] = True
            elif nome == "DeviceGray":
                resultado["GRAY"] = True

        elif isinstance(color_space, pikepdf.Array) and len(color_space) > 0:
            tipo = nome_pdf_para_texto(color_space[0])

            if tipo == "Separation" and len(color_space) >= 3:
                nome_cor = nome_pdf_para_texto(color_space[1])
                marcar_processo(nome_cor, resultado)
                analisar_color_space(color_space[2], resultado, mapa_cores)

            elif tipo == "DeviceN" and len(color_space) >= 3:
                nomes = color_space[1]

                if isinstance(nomes, pikepdf.Array):
                    for item in nomes:
                        marcar_processo(nome_pdf_para_texto(item), resultado)

                analisar_color_space(color_space[2], resultado, mapa_cores)

            else:
                texto = str(color_space)

                if "DeviceCMYK" in texto:
                    resultado["CMYK"] = True
                if "DeviceRGB" in texto:
                    resultado["RGB"] = True
                if "DeviceGray" in texto:
                    resultado["GRAY"] = True

    except Exception:
        pass


def coletar_mapa_cores(recursos, mapa_cores, resultado, visitados=None):
    if visitados is None:
        visitados = set()

    if recursos is None:
        return

    try:
        obj_id = id(recursos)
        if obj_id in visitados:
            return
        visitados.add(obj_id)

        color_spaces = recursos.get("/ColorSpace", {})

        if isinstance(color_spaces, pikepdf.Dictionary):
            for nome, color_space in color_spaces.items():
                chave = nome_pdf_para_texto(nome)
                mapa_cores[chave] = color_space
                analisar_color_space(color_space, resultado, mapa_cores)

        xobjects = recursos.get("/XObject", {})

        if isinstance(xobjects, pikepdf.Dictionary):
            for _, xobj in xobjects.items():
                try:
                    sub_recursos = xobj.get("/Resources")
                    coletar_mapa_cores(sub_recursos, mapa_cores, resultado, visitados)
                except Exception:
                    pass

    except Exception:
        pass


def tokenizar_pdf_stream(texto):
    padrao = re.compile(
        r"/[^\s\[\]\(\)<>/%]+|"
        r"-?\d*\.?\d+(?:[eE][+-]?\d+)?|"
        r"[A-Za-z\*]+|"
        r"\[|\]"
    )
    return padrao.findall(texto)


def resolver_color_space(nome, mapa_cores):
    nome = nome_pdf_para_texto(nome)

    if nome in ["DeviceCMYK", "DeviceRGB", "DeviceGray"]:
        return nome

    return mapa_cores.get(nome)


def analisar_scn(valores, color_space_atual, mapa_cores, resultado):
    cs = resolver_color_space(color_space_atual, mapa_cores)

    if not cs:
        return

    if isinstance(cs, str):
        if cs == "DeviceCMYK" and len(valores) >= 4:
            marcar_cmyk(valores[-4], valores[-3], valores[-2], valores[-1], resultado)

        elif cs == "DeviceRGB" and len(valores) >= 3:
            if valores[-3] > 0 or valores[-2] > 0 or valores[-1] > 0:
                resultado["RGB"] = True

        elif cs == "DeviceGray" and len(valores) >= 1:
            if valores[-1] > 0:
                resultado["GRAY"] = True

        return

    try:
        if isinstance(cs, pikepdf.Array) and len(cs) > 0:
            tipo = nome_pdf_para_texto(cs[0])

            if tipo == "Separation" and len(cs) >= 2:
                nome_cor = nome_pdf_para_texto(cs[1])
                tint = valores[-1] if valores else 0

                if tint > 0:
                    marcar_processo(nome_cor, resultado)

            elif tipo == "DeviceN" and len(cs) >= 2:
                nomes = cs[1]

                if isinstance(nomes, pikepdf.Array):
                    usados = valores[-len(nomes):]

                    for nome_cor, tint in zip(nomes, usados):
                        if tint > 0:
                            marcar_processo(nome_pdf_para_texto(nome_cor), resultado)

            elif tipo == "ICCBased":
                texto = str(cs)

                if "DeviceCMYK" in texto and len(valores) >= 4:
                    marcar_cmyk(valores[-4], valores[-3], valores[-2], valores[-1], resultado)
                elif "DeviceRGB" in texto and len(valores) >= 3:
                    if valores[-3] > 0 or valores[-2] > 0 or valores[-1] > 0:
                        resultado["RGB"] = True
                elif "DeviceGray" in texto and len(valores) >= 1:
                    if valores[-1] > 0:
                        resultado["GRAY"] = True

    except Exception:
        pass


def analisar_stream_pdf(conteudo, mapa_cores, resultado):
    texto = conteudo.decode("latin-1", errors="ignore")
    tokens = tokenizar_pdf_stream(texto)

    operandos = []
    cs_fill = "DeviceGray"
    cs_stroke = "DeviceGray"

    operadores = {
        "k", "K", "rg", "RG", "g", "G",
        "cs", "CS", "sc", "SC", "scn", "SCN",
    }

    for token in tokens:
        if token not in operadores:
            operandos.append(token)
            continue

        try:
            if token == "k" and len(operandos) >= 4:
                valores = [float(v) for v in operandos[-4:]]
                marcar_cmyk(*valores, resultado)

            elif token == "K" and len(operandos) >= 4:
                valores = [float(v) for v in operandos[-4:]]
                marcar_cmyk(*valores, resultado)

            elif token == "rg" and len(operandos) >= 3:
                r, g, b = [float(v) for v in operandos[-3:]]
                if r > 0 or g > 0 or b > 0:
                    resultado["RGB"] = True

            elif token == "RG" and len(operandos) >= 3:
                r, g, b = [float(v) for v in operandos[-3:]]
                if r > 0 or g > 0 or b > 0:
                    resultado["RGB"] = True

            elif token == "g" and len(operandos) >= 1:
                gray = float(operandos[-1])
                if gray > 0:
                    resultado["GRAY"] = True

            elif token == "G" and len(operandos) >= 1:
                gray = float(operandos[-1])
                if gray > 0:
                    resultado["GRAY"] = True

            elif token == "cs" and operandos:
                cs_fill = nome_pdf_para_texto(operandos[-1])

            elif token == "CS" and operandos:
                cs_stroke = nome_pdf_para_texto(operandos[-1])

            elif token in ["sc", "scn"]:
                valores = [
                    float(v)
                    for v in operandos
                    if re.fullmatch(r"-?\d*\.?\d+(?:[eE][+-]?\d+)?", v)
                ]
                analisar_scn(valores, cs_fill, mapa_cores, resultado)

            elif token in ["SC", "SCN"]:
                valores = [
                    float(v)
                    for v in operandos
                    if re.fullmatch(r"-?\d*\.?\d+(?:[eE][+-]?\d+)?", v)
                ]
                analisar_scn(valores, cs_stroke, mapa_cores, resultado)

        except Exception:
            pass

        operandos = []


def ler_bytes_conteudo_pagina(pagina):
    conteudos = []

    try:
        contents = pagina.get("/Contents")

        if contents is None:
            return conteudos

        if isinstance(contents, pikepdf.Array):
            for item in contents:
                try:
                    conteudos.append(item.read_bytes())
                except Exception:
                    pass
        else:
            try:
                conteudos.append(contents.read_bytes())
            except Exception:
                pass

    except Exception:
        pass

    return conteudos


def analisar_xobjects(recursos, mapa_cores, resultado, visitados=None):
    if visitados is None:
        visitados = set()

    if recursos is None:
        return

    try:
        xobjects = recursos.get("/XObject", {})

        if not isinstance(xobjects, pikepdf.Dictionary):
            return

        for _, xobj in xobjects.items():
            obj_id = id(xobj)

            if obj_id in visitados:
                continue

            visitados.add(obj_id)

            subtype = str(xobj.get("/Subtype", ""))

            if subtype == "/Image":
                color_space = xobj.get("/ColorSpace")
                nome = nome_pdf_para_texto(color_space)

                if "DeviceCMYK" in nome:
                    resultado["CMYK"] = True
                    resultado["C"] = True
                    resultado["M"] = True
                    resultado["Y"] = True
                    resultado["K"] = True

                elif "DeviceRGB" in nome:
                    resultado["RGB"] = True

                elif "DeviceGray" in nome:
                    resultado["GRAY"] = True

            else:
                try:
                    analisar_stream_pdf(xobj.read_bytes(), mapa_cores, resultado)
                except Exception:
                    pass

                try:
                    sub_recursos = xobj.get("/Resources")
                    coletar_mapa_cores(sub_recursos, mapa_cores, resultado)
                    analisar_xobjects(sub_recursos, mapa_cores, resultado, visitados)
                except Exception:
                    pass

    except Exception:
        pass


def detectar_cores(pdf_bytes):
    resultado = {
        "CMYK": False,
        "RGB": False,
        "GRAY": False,
        "C": False,
        "M": False,
        "Y": False,
        "K": False,
        "SPOTS": set(),
    }

    with pikepdf.open(BytesIO(pdf_bytes)) as pdf:
        for pagina in pdf.pages:
            mapa_cores = {}

            recursos = pagina.get("/Resources")
            coletar_mapa_cores(recursos, mapa_cores, resultado)

            for conteudo in ler_bytes_conteudo_pagina(pagina):
                analisar_stream_pdf(conteudo, mapa_cores, resultado)

            analisar_xobjects(recursos, mapa_cores, resultado)

    spots_limpos = sorted(
        cor for cor in resultado["SPOTS"]
        if cor and cor not in IGNORE_SPOT_NAMES
    )

    return {
        "CMYK": resultado["CMYK"],
        "RGB": resultado["RGB"],
        "GRAY": resultado["GRAY"],
        "C": resultado["C"],
        "M": resultado["M"],
        "Y": resultado["Y"],
        "K": resultado["K"],
        "SPOTS": spots_limpos,
    }


def cor_escura(cor):
    if not cor:
        return True

    try:
        return all(c <= 0.25 for c in cor[:3])
    except Exception:
        return False


def detectar_marcas_de_corte(doc):
    total_linhas_suspeitas = 0

    for pagina in doc:
        desenhos = pagina.get_drawings()

        for desenho in desenhos:
            largura_linha = desenho.get("width", 0)

            if largura_linha is None or largura_linha > 1.2:
                continue

            if not cor_escura(desenho.get("color")):
                continue

            for item in desenho.get("items", []):
                if not item or item[0] != "l":
                    continue

                p1 = item[1]
                p2 = item[2]

                dx = abs(p2.x - p1.x)
                dy = abs(p2.y - p1.y)

                comprimento = max(dx, dy)
                comprimento_mm = pt_to_mm(comprimento)

                eh_horizontal = dy <= mm_to_pt(0.3) and dx > 0
                eh_vertical = dx <= mm_to_pt(0.3) and dy > 0

                if not (eh_horizontal or eh_vertical):
                    continue

                if 2 <= comprimento_mm <= 25:
                    total_linhas_suspeitas += 1

    return total_linhas_suspeitas >= 4


def gerar_preview_png(doc):
    pagina = doc[0]
    pix = pagina.get_pixmap(matrix=fitz.Matrix(0.45, 0.45), alpha=False)
    return pix.tobytes("png")


def analisar_pdf(caminho_pdf):
    with open(caminho_pdf, "rb") as arquivo:
        pdf_bytes = arquivo.read()

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    metadata = doc.metadata or {}

    boxes = analisar_boxes(pdf_bytes)
    primeira = boxes[0]

    cores = detectar_cores(pdf_bytes)
    marcas_corte = detectar_marcas_de_corte(doc)
    preview_png = gerar_preview_png(doc)

    media_l, media_a = primeira["media"]
    trim_l, trim_a = primeira["trim"]

    criado_em = (
        metadata.get("creator")
        or metadata.get("producer")
        or metadata.get("format")
        or "Não informado"
    )

    return {
        "caminho": caminho_pdf,
        "nome": os.path.basename(caminho_pdf),
        "peso": formatar_peso(len(pdf_bytes)),
        "paginas": len(doc),
        "orientacao": orientacao(media_l, media_a),
        "criado_em": criado_em,
        "data_criacao": formatar_data_pdf(metadata.get("creationDate")),
        "data_modificacao": formatar_data_pdf(metadata.get("modDate")),
        "medida_pdf": formatar_mm(media_l, media_a),
        "medida_trim": formatar_mm(trim_l, trim_a),
        "medida_bleed": formatar_mm(*primeira["bleed"]),
        "medida_crop": formatar_mm(*primeira["crop"]),
        "tem_trim": primeira["tem_trim"],
        "tem_bleed": primeira["tem_bleed"],
        "tem_crop": primeira["tem_crop"],
        "marcas_corte": marcas_corte,
        "cores": cores,
        "boxes": boxes,
        "preview_png": preview_png,
    }


def resumo_pdf(info):
    paginas = "1 página" if info["paginas"] == 1 else f'{info["paginas"]} páginas'
    return (
        f'{info["nome"]}\n'
        f'{paginas} • Trim: {info["medida_trim"]} • {info["peso"]}'
    )


def info_pdf_completa(info):
    cores = info["cores"]
    spots = ", ".join(cores["SPOTS"]) if cores["SPOTS"] else "Nenhuma detectada"

    separacoes = []
    for label, key in [
        ("Ciano", "C"),
        ("Magenta", "M"),
        ("Amarelo", "Y"),
        ("Preto", "K"),
        ("RGB", "RGB"),
    ]:
        separacoes.append(f'{"✓" if cores[key] else "□"} {label}')

    separacoes.append(f'{"✓" if cores["SPOTS"] else "□"} Pantones / especiais')

    trim_obs = "" if info["tem_trim"] else "\n\n⚠️ TrimBox não definido. Usando MediaBox como referência."

    return (
        f'Nome do arquivo\n{info["nome"]}\n\n'
        f'Peso\n{info["peso"]}\n\n'
        f'Orientação\n{info["orientacao"]}\n\n'
        f'Criado em\n{info["criado_em"]}\n\n'
        f'Data de criação\n{info["data_criacao"]}\n\n'
        f'Quantidade de páginas\n{info["paginas"]}\n\n'
        f'Medida do PDF\n{info["medida_pdf"]}\n\n'
        f'Medida da marca de corte / Trim\n{info["medida_trim"]}\n\n'
        f'Medida do Bleed\n{info["medida_bleed"]}\n\n'
        f'Marcas de corte detectadas\n{"Sim" if info["marcas_corte"] else "Não"}\n\n'
        f'Separações detectadas\n' + "\n".join(separacoes) + "\n\n"
        f'Pantones / cores especiais\n{spots}'
        f'{trim_obs}'
    )
