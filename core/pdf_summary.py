import re
from pathlib import Path


def clean_document_name(file_name):
    stem = Path(file_name).stem
    words = re.sub(r"[_\-.]+", " ", stem).split()
    words = [
        word
        for word in words
        if not re.fullmatch(r"20\d{2}|\d+[xX]\d+", word)
    ]
    if not words:
        return "Material"
    material = words[0].title()
    client = " ".join(words[1:]).strip()
    client = re.sub(r"(?i)^abordo(?=tours$)", "A Bordo ", client).title()
    return f'{material} "{client}"' if client else material


def build_job_summary(info):
    name = clean_document_name(info.get("nome", "PDF"))
    boxes = info.get("boxes", [])
    trim = boxes[0].get("trim") if boxes else None
    if trim:
        width, height = trim
        size = f"{width:g}x{height:g}mm"
    else:
        size = str(info.get("medida_trim", "formato não informado"))
    colors = info.get("cores", {})
    color_count = 4 if colors.get("CMYK") else 1
    sides = color_count if int(info.get("paginas", 1)) > 1 else 0
    return f"{name} no formato {size}, impressos {color_count}/{sides} cores"
