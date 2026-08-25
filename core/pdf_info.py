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

IGNORE_SPOT_NAMES = {
    "All",
    "None",
    "Registration",
}


# ============================================================
# CONVERSÕES E FORMATAÇÃO
# ============================================================

def pt_to_mm(value):
    return round(float(value) * MM_PER_POINT, 2)


def mm_to_pt(value):
    return float(value) * POINT_PER_MM


def box_to_mm(box):
    width_pt = float(box[2]) - float(box[0])
    height_pt = float(box[3]) - float(box[1])

    return pt_to_mm(width_pt), pt_to_mm(height_pt)


def format_mm(width, height):
    return f"{width:.1f} mm x {height:.1f} mm"


def get_orientation(width, height):
    if abs(width - height) < 0.5:
        return "Quadrado"

    if width > height:
        return "Paisagem"

    return "Retrato"


def format_pdf_date(pdf_date):
    if not pdf_date:
        return "Não informado"

    try:
        clean_date = str(pdf_date).replace("D:", "")
        parsed_date = datetime.strptime(clean_date[:14], "%Y%m%d%H%M%S")

        return parsed_date.strftime("%d/%m/%Y às %H:%M")

    except (TypeError, ValueError):
        return str(pdf_date)


def format_file_size(total_bytes):
    if total_bytes < 1024:
        return f"{total_bytes} bytes"

    if total_bytes < 1024 * 1024:
        return f"{total_bytes / 1024:.1f} KB"

    return f"{total_bytes / (1024 * 1024):.2f} MB"


# ============================================================
# BOXES DO PDF
# ============================================================

def analyze_boxes(pdf_bytes):
    pages = []

    with pikepdf.open(BytesIO(pdf_bytes)) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            media_box = page.get("/MediaBox")

            if media_box is None:
                continue

            trim_box = page.get("/TrimBox")
            bleed_box = page.get("/BleedBox")
            crop_box = page.get("/CropBox")

            media_mm = box_to_mm(media_box)
            trim_mm = box_to_mm(trim_box) if trim_box else media_mm
            bleed_mm = box_to_mm(bleed_box) if bleed_box else media_mm
            crop_mm = box_to_mm(crop_box) if crop_box else media_mm

            pages.append(
                {
                    "pagina": page_number,
                    "media": media_mm,
                    "trim": trim_mm,
                    "bleed": bleed_mm,
                    "crop": crop_mm,
                    "tem_trim": trim_box is not None,
                    "tem_bleed": bleed_box is not None,
                    "tem_crop": crop_box is not None,
                }
            )

    return pages


# ============================================================
# NOMES E COLOR SPACES
# ============================================================

def pdf_name_to_text(name):
    name = str(name).replace("/", "")

    def replace_hex(match):
        try:
            return chr(int(match.group(1), 16))
        except (TypeError, ValueError):
            return ""

    return re.sub(r"#([0-9A-Fa-f]{2})", replace_hex, name).strip()


def mark_process_color(color_name, result):
    color_name = pdf_name_to_text(color_name)

    if color_name in PROCESS_COLORS:
        channel = PROCESS_COLORS[color_name]

        result[channel] = True
        result["CMYK"] = True
        return

    if color_name and color_name not in IGNORE_SPOT_NAMES:
        result["SPOTS"].add(color_name)


def mark_cmyk(cyan, magenta, yellow, black, result):
    if cyan > 0:
        result["C"] = True

    if magenta > 0:
        result["M"] = True

    if yellow > 0:
        result["Y"] = True

    if black > 0:
        result["K"] = True

    if any(value > 0 for value in (cyan, magenta, yellow, black)):
        result["CMYK"] = True


def analyze_color_space(color_space, result, color_map=None):
    try:
        if isinstance(color_space, pikepdf.Name):
            name = pdf_name_to_text(color_space)

            if name == "DeviceCMYK":
                result["CMYK"] = True

            elif name == "DeviceRGB":
                result["RGB"] = True

            elif name == "DeviceGray":
                result["GRAY"] = True

            return

        if not isinstance(color_space, pikepdf.Array) or not color_space:
            return

        color_type = pdf_name_to_text(color_space[0])

        if color_type == "ICCBased" and len(color_space) >= 2:
            components = int(color_space[1].get("/N", 0))
            if components == 4:
                result["CMYK"] = True
                result["C"] = result["M"] = True
                result["Y"] = result["K"] = True
            elif components == 3:
                result["RGB"] = True
            elif components == 1:
                result["GRAY"] = True

        elif color_type in {"CalRGB", "Lab"}:
            result["RGB"] = True

        elif color_type == "Indexed" and len(color_space) >= 2:
            analyze_color_space(color_space[1], result, color_map)

        elif color_type == "Separation" and len(color_space) >= 3:
            color_name = pdf_name_to_text(color_space[1])

            mark_process_color(color_name, result)
            analyze_color_space(color_space[2], result, color_map)

        elif color_type == "DeviceN" and len(color_space) >= 3:
            color_names = color_space[1]

            if isinstance(color_names, pikepdf.Array):
                for item in color_names:
                    mark_process_color(item, result)

            analyze_color_space(color_space[2], result, color_map)

        else:
            text = str(color_space)

            if "DeviceCMYK" in text:
                result["CMYK"] = True

            if "DeviceRGB" in text:
                result["RGB"] = True

            if "DeviceGray" in text:
                result["GRAY"] = True

    except Exception:
        pass


def collect_color_map(resources, color_map, result, visited=None):
    if visited is None:
        visited = set()

    if resources is None:
        return

    try:
        object_id = id(resources)

        if object_id in visited:
            return

        visited.add(object_id)

        color_spaces = resources.get("/ColorSpace", {})

        if isinstance(color_spaces, pikepdf.Dictionary):
            for name, color_space in color_spaces.items():
                key = pdf_name_to_text(name)

                color_map[key] = color_space
                analyze_color_space(color_space, result, color_map)

        xobjects = resources.get("/XObject", {})

        if isinstance(xobjects, pikepdf.Dictionary):
            for xobject in xobjects.values():
                try:
                    child_resources = xobject.get("/Resources")
                    collect_color_map(
                        child_resources,
                        color_map,
                        result,
                        visited,
                    )
                except Exception:
                    pass

    except Exception:
        pass


# ============================================================
# CONTENT STREAMS
# ============================================================

def tokenize_pdf_stream(text):
    pattern = re.compile(
        r"/[^\s\[\]\(\)<>/%]+|"
        r"-?\d*\.?\d+(?:[eE][+-]?\d+)?|"
        r"[A-Za-z\*]+|"
        r"\[|\]"
    )

    return pattern.findall(text)


def resolve_color_space(name, color_map):
    name = pdf_name_to_text(name)

    if name in {
        "DeviceCMYK",
        "DeviceRGB",
        "DeviceGray",
    }:
        return name

    return color_map.get(name)


def analyze_scn(values, current_color_space, color_map, result):
    color_space = resolve_color_space(
        current_color_space,
        color_map,
    )

    if not color_space:
        return

    if isinstance(color_space, str):
        if color_space == "DeviceCMYK" and len(values) >= 4:
            mark_cmyk(
                values[-4],
                values[-3],
                values[-2],
                values[-1],
                result,
            )

        elif color_space == "DeviceRGB" and len(values) >= 3:
            if any(value > 0 for value in values[-3:]):
                result["RGB"] = True

        elif color_space == "DeviceGray" and values:
            if values[-1] > 0:
                result["GRAY"] = True

        return

    try:
        if not isinstance(color_space, pikepdf.Array) or not color_space:
            return

        color_type = pdf_name_to_text(color_space[0])

        if color_type == "Separation" and len(color_space) >= 2:
            color_name = pdf_name_to_text(color_space[1])
            tint = values[-1] if values else 0

            if tint > 0:
                mark_process_color(color_name, result)

        elif color_type == "DeviceN" and len(color_space) >= 2:
            color_names = color_space[1]

            if isinstance(color_names, pikepdf.Array):
                used_values = values[-len(color_names):]

                for color_name, tint in zip(
                    color_names,
                    used_values,
                ):
                    if tint > 0:
                        mark_process_color(color_name, result)

        elif color_type == "ICCBased" and len(color_space) >= 2:
            components = int(color_space[1].get("/N", 0))

            if components == 4 and len(values) >= 4:
                mark_cmyk(
                    values[-4],
                    values[-3],
                    values[-2],
                    values[-1],
                    result,
                )

            elif components == 3 and len(values) >= 3:
                if any(value > 0 for value in values[-3:]):
                    result["RGB"] = True

            elif components == 1 and values:
                if values[-1] > 0:
                    result["GRAY"] = True

    except Exception:
        pass


def analyze_pdf_stream(content, color_map, result):
    text = content.decode("latin-1", errors="ignore")
    # Imagens inline declaram o espaço entre BI/ID, sem operador de pintura.
    if "/DeviceCMYK" in text:
        result["CMYK"] = True
        result["C"] = result["M"] = True
        result["Y"] = result["K"] = True
    if "/DeviceRGB" in text:
        result["RGB"] = True
    if "/DeviceGray" in text:
        result["GRAY"] = True
    tokens = tokenize_pdf_stream(text)

    operands = []

    fill_color_space = "DeviceGray"
    stroke_color_space = "DeviceGray"

    operators = {
        "k",
        "K",
        "rg",
        "RG",
        "g",
        "G",
        "cs",
        "CS",
        "sc",
        "SC",
        "scn",
        "SCN",
    }

    for token in tokens:
        if token not in operators:
            operands.append(token)
            continue

        try:
            if token in {"k", "K"} and len(operands) >= 4:
                values = [
                    float(value)
                    for value in operands[-4:]
                ]

                mark_cmyk(*values, result)

            elif token in {"rg", "RG"} and len(operands) >= 3:
                values = [
                    float(value)
                    for value in operands[-3:]
                ]

                if any(value > 0 for value in values):
                    result["RGB"] = True

            elif token in {"g", "G"} and operands:
                gray = float(operands[-1])

                if gray > 0:
                    result["GRAY"] = True

            elif token == "cs" and operands:
                fill_color_space = pdf_name_to_text(
                    operands[-1]
                )

            elif token == "CS" and operands:
                stroke_color_space = pdf_name_to_text(
                    operands[-1]
                )

            elif token in {"sc", "scn"}:
                values = extract_numeric_operands(operands)

                analyze_scn(
                    values,
                    fill_color_space,
                    color_map,
                    result,
                )

            elif token in {"SC", "SCN"}:
                values = extract_numeric_operands(operands)

                analyze_scn(
                    values,
                    stroke_color_space,
                    color_map,
                    result,
                )

        except Exception:
            pass

        operands = []


def extract_numeric_operands(operands):
    numeric_pattern = re.compile(
        r"-?\d*\.?\d+(?:[eE][+-]?\d+)?"
    )

    return [
        float(value)
        for value in operands
        if numeric_pattern.fullmatch(value)
    ]


def read_page_content_bytes(page):
    contents_list = []

    try:
        contents = page.get("/Contents")

        if contents is None:
            return contents_list

        if isinstance(contents, pikepdf.Array):
            for item in contents:
                try:
                    contents_list.append(item.read_bytes())
                except Exception:
                    pass

        else:
            try:
                contents_list.append(contents.read_bytes())
            except Exception:
                pass

    except Exception:
        pass

    return contents_list


# ============================================================
# XOBJECTS E IMAGENS
# ============================================================

def analyze_xobjects(
    resources,
    color_map,
    result,
    visited=None,
):
    if visited is None:
        visited = set()

    if resources is None:
        return

    try:
        xobjects = resources.get("/XObject", {})

        if not isinstance(xobjects, pikepdf.Dictionary):
            return

        for xobject in xobjects.values():
            object_id = id(xobject)

            if object_id in visited:
                continue

            visited.add(object_id)

            subtype = str(xobject.get("/Subtype", ""))

            if subtype == "/Image":
                analyze_image_xobject(xobject, result)
                continue

            try:
                analyze_pdf_stream(
                    xobject.read_bytes(),
                    color_map,
                    result,
                )
            except Exception:
                pass

            try:
                child_resources = xobject.get("/Resources")

                collect_color_map(
                    child_resources,
                    color_map,
                    result,
                )

                analyze_xobjects(
                    child_resources,
                    color_map,
                    result,
                    visited,
                )

            except Exception:
                pass

    except Exception:
        pass


def analyze_image_xobject(xobject, result):
    color_space = xobject.get("/ColorSpace")
    if isinstance(color_space, pikepdf.Array):
        analyze_color_space(color_space, result)
        return
    color_name = pdf_name_to_text(color_space)

    if "DeviceCMYK" in color_name:
        result["CMYK"] = True
        result["C"] = True
        result["M"] = True
        result["Y"] = True
        result["K"] = True

    elif "DeviceRGB" in color_name:
        result["RGB"] = True

    elif "DeviceGray" in color_name:
        result["GRAY"] = True


# ============================================================
# DETECÇÃO DE CORES
# ============================================================

def detect_colors(pdf_bytes):
    result = {
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
        for page in pdf.pages:
            color_map = {}
            resources = page.get("/Resources")

            collect_color_map(
                resources,
                color_map,
                result,
            )

            for content in read_page_content_bytes(page):
                analyze_pdf_stream(
                    content,
                    color_map,
                    result,
                )

            analyze_xobjects(
                resources,
                color_map,
                result,
            )

    clean_spots = sorted(
        color
        for color in result["SPOTS"]
        if color and color not in IGNORE_SPOT_NAMES
    )

    return {
        "CMYK": result["CMYK"],
        "RGB": result["RGB"],
        "GRAY": result["GRAY"],
        "C": result["C"],
        "M": result["M"],
        "Y": result["Y"],
        "K": result["K"],
        "SPOTS": clean_spots,
    }


# ============================================================
# MARCAS DE CORTE
# ============================================================

def is_dark_color(color):
    if not color:
        return True

    try:
        return all(value <= 0.25 for value in color[:3])
    except (TypeError, ValueError):
        return False


def detect_crop_marks(document):
    suspicious_lines = 0

    for page in document:
        for drawing in page.get_drawings():
            line_width = drawing.get("width", 0)

            if line_width is None or line_width > 1.2:
                continue

            if not is_dark_color(drawing.get("color")):
                continue

            for item in drawing.get("items", []):
                if not item or item[0] != "l":
                    continue

                point_1 = item[1]
                point_2 = item[2]

                delta_x = abs(point_2.x - point_1.x)
                delta_y = abs(point_2.y - point_1.y)

                length = max(delta_x, delta_y)
                length_mm = pt_to_mm(length)

                is_horizontal = (
                    delta_y <= mm_to_pt(0.3)
                    and delta_x > 0
                )

                is_vertical = (
                    delta_x <= mm_to_pt(0.3)
                    and delta_y > 0
                )

                if not (is_horizontal or is_vertical):
                    continue

                if 2 <= length_mm <= 25:
                    suspicious_lines += 1

    return suspicious_lines >= 4


# ============================================================
# PREVIEW
# ============================================================

def generate_preview_png(document):
    if document.page_count == 0:
        return b""

    first_page = document[0]

    # Gera a imagem em resolução maior.
    # Depois ela é reduzida suavemente dentro da janela.
    pixmap = first_page.get_pixmap(
        matrix=fitz.Matrix(1.5, 1.5),
        alpha=False,
        colorspace=fitz.csRGB,
    )

    return pixmap.tobytes("png")


# ============================================================
# ANÁLISE PRINCIPAL
# ============================================================

def analisar_pdf(pdf_path):
    with open(pdf_path, "rb") as file:
        pdf_bytes = file.read()

    document = fitz.open(
        stream=pdf_bytes,
        filetype="pdf",
    )

    try:
        if document.page_count == 0:
            raise ValueError("O PDF não possui páginas.")

        metadata = document.metadata or {}
        boxes = analyze_boxes(pdf_bytes)

        if not boxes:
            raise ValueError(
                "Não foi possível identificar as dimensões do PDF."
            )

        first_page = boxes[0]

        colors = detect_colors(pdf_bytes)
        crop_marks = detect_crop_marks(document)
        preview_png = generate_preview_png(document)

        media_width, media_height = first_page["media"]
        trim_width, trim_height = first_page["trim"]

        created_by = (
            metadata.get("creator")
            or metadata.get("producer")
            or metadata.get("format")
            or "Não informado"
        )

        return {
            "caminho": pdf_path,
            "nome": os.path.basename(pdf_path),
            "peso": format_file_size(len(pdf_bytes)),
            "paginas": document.page_count,
            "orientacao": get_orientation(
                media_width,
                media_height,
            ),
            "criado_em": created_by,
            "data_criacao": format_pdf_date(
                metadata.get("creationDate")
            ),
            "data_modificacao": format_pdf_date(
                metadata.get("modDate")
            ),
            "medida_pdf": format_mm(
                media_width,
                media_height,
            ),
            "medida_trim": format_mm(
                trim_width,
                trim_height,
            ),
            "medida_bleed": format_mm(
                *first_page["bleed"]
            ),
            "medida_crop": format_mm(
                *first_page["crop"]
            ),
            "tem_trim": first_page["tem_trim"],
            "tem_bleed": first_page["tem_bleed"],
            "tem_crop": first_page["tem_crop"],
            "marcas_corte": crop_marks,
            "cores": colors,
            "boxes": boxes,
            "preview_png": preview_png,
        }

    finally:
        document.close()
