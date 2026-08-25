from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Optional

from PIL import Image


L_CODES = {
    "0": "0001101", "1": "0011001", "2": "0010011", "3": "0111101",
    "4": "0100011", "5": "0110001", "6": "0101111", "7": "0111011",
    "8": "0110111", "9": "0001011",
}
G_CODES = {
    "0": "0100111", "1": "0110011", "2": "0011011", "3": "0100001",
    "4": "0011101", "5": "0111001", "6": "0000101", "7": "0010001",
    "8": "0001001", "9": "0010111",
}
R_CODES = {
    "0": "1110010", "1": "1100110", "2": "1101100", "3": "1000010",
    "4": "1011100", "5": "1001110", "6": "1010000", "7": "1000100",
    "8": "1001000", "9": "1110100",
}
PARITY = {
    "0": "LLLLLL", "1": "LLGLGG", "2": "LLGGLG", "3": "LLGGGL",
    "4": "LGLLGG", "5": "LGGLLG", "6": "LGGGLL", "7": "LGLGLG",
    "8": "LGLGGL", "9": "LGGLGL",
}


def calculate_ean13_check_digit(code12: str) -> str:
    if len(code12) != 12 or not code12.isdigit():
        raise ValueError("O código-base precisa ter exatamente 12 dígitos.")
    total = sum(int(d) if i % 2 == 0 else int(d) * 3 for i, d in enumerate(code12))
    return str((10 - total % 10) % 10)


def normalize_ean13(value: str) -> tuple[Optional[str], str]:
    value = "".join(value.split())
    if not value:
        return None, "Digite 12 ou 13 números."
    if not value.isdigit():
        return None, "Use apenas números."
    if len(value) not in (12, 13):
        return None, "O EAN-13 precisa ter 12 ou 13 dígitos."
    if len(value) == 12:
        digit = calculate_ean13_check_digit(value)
        return value + digit, f"Dígito {digit} calculado automaticamente."
    expected = calculate_ean13_check_digit(value[:12])
    if value[-1] != expected:
        return None, f"Dígito incorreto. O código válido seria {value[:12]}{expected}."
    return value, "Código EAN-13 válido."


def ean13_pattern(code: str) -> str:
    first, left, right = code[0], code[1:7], code[7:13]
    bits = "101"
    for digit, parity in zip(left, PARITY[first]):
        bits += L_CODES[digit] if parity == "L" else G_CODES[digit]
    bits += "01010"
    bits += "".join(R_CODES[digit] for digit in right)
    return bits + "101"


def generate_ean13_svg(
    code: str,
    width_mm: float = 37.29,
    height_mm: float = 25.93,
    show_text: bool = True,
) -> bytes:
    """Gera EAN-13 vetorial com cada algarismo posicionado individualmente.

    Não usa ``letter-spacing`` porque alguns editores, especialmente ao abrir o
    SVG no Illustrator, interpretam esse atributo de forma diferente e deslocam
    os números. Cada dígito recebe sua própria coordenada, igual à prévia.
    """
    pattern = ean13_pattern(code)
    quiet_left = 3.63
    quiet_right = 2.31
    module = (width_mm - quiet_left - quiet_right) / 95
    bar_y = 1.0
    normal_h = 17.8
    guard_h = 21.2
    guards = set(range(0, 3)) | set(range(45, 50)) | set(range(92, 95))

    bars: list[str] = []
    x = quiet_left
    for index, bit in enumerate(pattern):
        if bit == "1":
            height = guard_h if index in guards else normal_h
            bars.append(
                f'<rect x="{x:.4f}" y="{bar_y:.4f}" width="{module:.4f}" '
                f'height="{height:.4f}" fill="#000000"/>'
            )
        x += module

    text = ""
    if show_text:
        text_y = 22.15
        font_size = 3.7
        digit_nodes = [
            f'<text x="{quiet_left * 0.43:.4f}" y="{text_y:.4f}" text-anchor="middle">{code[0]}</text>'
        ]

        # Os seis algarismos da esquerda começam depois da guarda inicial
        # (3 módulos), e cada algarismo ocupa exatamente 7 módulos.
        for index, digit in enumerate(code[1:7]):
            center = quiet_left + (3 + index * 7 + 3.5) * module
            digit_nodes.append(
                f'<text x="{center:.4f}" y="{text_y:.4f}" text-anchor="middle">{digit}</text>'
            )

        # O lado direito começa no módulo 50, após a guarda central.
        for index, digit in enumerate(code[7:13]):
            center = quiet_left + (50 + index * 7 + 3.5) * module
            digit_nodes.append(
                f'<text x="{center:.4f}" y="{text_y:.4f}" text-anchor="middle">{digit}</text>'
            )

        text = (
            f'<g fill="#000000" font-family="Arial,Helvetica,sans-serif" '
            f'font-size="{font_size}" font-weight="400">'
            + "".join(digit_nodes)
            + "</g>"
        )

    svg = f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{width_mm}mm" height="{height_mm}mm"
     viewBox="0 0 {width_mm} {height_mm}">
  <rect width="100%" height="100%" fill="#ffffff"/>
  <g shape-rendering="crispEdges">{''.join(bars)}</g>
  {text}
</svg>"""
    return svg.encode("utf-8")


def generate_qr_svg(content: str, border: int = 2, scale: int = 8, error: str = "m") -> bytes:
    try:
        import segno
    except ImportError as exc:
        raise RuntimeError("A biblioteca leve 'segno' não está instalada.") from exc

    qr = segno.make(content, error=error.lower())
    buffer = BytesIO()
    qr.save(buffer, kind="svg", scale=scale, border=border, dark="#000000", light="#ffffff")
    return buffer.getvalue()


def generate_qr_png(content: str, border: int = 2, scale: int = 12, error: str = "m") -> bytes:
    try:
        import segno
    except ImportError as exc:
        raise RuntimeError("A biblioteca leve 'segno' não está instalada.") from exc

    qr = segno.make(content, error=error.lower())
    buffer = BytesIO()
    qr.save(buffer, kind="png", scale=scale, border=border, dark="#000000", light="#ffffff")
    return buffer.getvalue()


def load_image_for_reader(path: str | Path) -> Image.Image:
    path = Path(path)
    if path.suffix.lower() == ".pdf":
        import fitz

        document = fitz.open(path)
        if not document.page_count:
            raise ValueError("O PDF não possui páginas.")
        page = document.load_page(0)
        pix = page.get_pixmap(matrix=fitz.Matrix(2.5, 2.5), alpha=False)
        return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    return Image.open(path).convert("RGB")


def read_codes_from_image(image: Image.Image) -> list[dict[str, str]]:
    try:
        import zxingcpp
    except ImportError as exc:
        raise RuntimeError("A biblioteca leve 'zxing-cpp' não está instalada.") from exc

    image = image.convert("RGB")
    results = []
    for item in zxingcpp.read_barcodes(image):
        results.append({
            "type": str(item.format).replace("BarcodeFormat.", ""),
            "value": item.text,
            "valid": "Sim" if item.valid else "Não",
        })
    return results
