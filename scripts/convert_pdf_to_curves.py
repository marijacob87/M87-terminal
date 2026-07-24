#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.pdf_preservation import (  # noqa: E402
    PdfPreservationError,
    preserve_output_intents,
)


GS_CANDIDATES = (
    "/opt/homebrew/bin/gs",
    "/usr/local/bin/gs",
    "/usr/bin/gs",
)


def _result(ok: bool, message: str, output: Path | None = None, **extra: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "ok": ok,
        "message": message,
        "output": str(output) if output else "",
    }
    data.update(extra)
    return data


def _find_ghostscript() -> str | None:
    env_path = shutil.which("gs")
    if env_path:
        return env_path

    for candidate in GS_CANDIDATES:
        if Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return candidate

    return None


def _page_geometry(pdf_path: Path) -> list[dict[str, tuple[float, float, float, float] | None]]:
    import fitz

    attributes = (
        ("/MediaBox", "mediabox"),
        ("/CropBox", "cropbox"),
        ("/TrimBox", "trimbox"),
        ("/BleedBox", "bleedbox"),
        ("/ArtBox", "artbox"),
    )
    geometry: list[dict[str, tuple[float, float, float, float] | None]] = []

    document = fitz.open(pdf_path)
    try:
        for page in document:
            item: dict[str, tuple[float, float, float, float] | None] = {}
            for key, attribute in attributes:
                rect = getattr(page, attribute, None)
                if rect is None:
                    item[key] = None
                else:
                    item[key] = tuple(
                        round(float(value), 4)
                        for value in (rect.x0, rect.y0, rect.x1, rect.y1)
                    )
            geometry.append(item)
    finally:
        document.close()

    return geometry


def _font_count(pdf_path: Path) -> int:
    import fitz

    count = 0
    document = fitz.open(pdf_path)
    try:
        seen: set[int] = set()
        for page in document:
            for font in page.get_fonts(full=True):
                xref = int(font[0]) if font and font[0] else 0
                if xref not in seen:
                    seen.add(xref)
                    count += 1
    finally:
        document.close()
    return count


def _validate_output(source: Path, output: Path) -> tuple[bool, str]:
    if not output.is_file() or output.stat().st_size == 0:
        return False, "O Ghostscript terminou, mas não gerou um PDF válido."

    try:
        source_geometry = _page_geometry(source)
        output_geometry = _page_geometry(output)
    except Exception as error:
        return False, f"Não consegui validar as medidas do PDF gerado: {error}"

    if len(source_geometry) != len(output_geometry):
        return False, (
            "A quantidade de páginas mudou durante a conversão "
            f"({len(source_geometry)} → {len(output_geometry)})."
        )

    tolerance = 0.05
    for page_number, (before, after) in enumerate(zip(source_geometry, output_geometry), start=1):
        for box_name in ("/MediaBox", "/CropBox", "/TrimBox", "/BleedBox", "/ArtBox"):
            old_box = before.get(box_name)
            new_box = after.get(box_name)

            if old_box is None or new_box is None:
                continue

            if any(abs(a - b) > tolerance for a, b in zip(old_box, new_box)):
                return False, (
                    f"A caixa {box_name[1:]} da página {page_number} mudou. "
                    "O arquivo gerado foi descartado por segurança."
                )

    try:
        fonts = _font_count(output)
    except Exception as error:
        return False, f"O PDF foi criado, mas não consegui confirmar as curvas: {error}"

    if fonts > 0:
        return False, (
            f"A validação ainda encontrou {fonts} recurso(s) de fonte no PDF. "
            "O arquivo gerado foi descartado para evitar um falso CURVAS."
        )

    return True, ""


def converter_pdf_em_curvas(pdf_path: str, output_path: str) -> dict[str, Any]:
    source = Path(pdf_path).expanduser().resolve()
    destination = Path(output_path).expanduser().resolve()

    if not source.is_file() or source.suffix.lower() != ".pdf":
        return _result(False, "O arquivo selecionado não é um PDF válido.")

    if destination.suffix.lower() != ".pdf":
        return _result(False, "O destino precisa ter a extensão .pdf.")

    ghostscript = _find_ghostscript()
    if not ghostscript:
        return _result(
            False,
            "O Ghostscript não está instalado.\n\n"
            "Abra o Terminal do macOS e execute:\n"
            "brew install ghostscript\n\n"
            "Depois reinicie o M87 com ##.",
            needs_ghostscript=True,
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    replacing_original = destination == source

    # Ghostscript não deve ler e escrever no mesmo arquivo. Quando a pessoa
    # escolhe substituir o original, geramos primeiro um PDF temporário seguro.
    if replacing_original:
        fd, temporary_name = tempfile.mkstemp(
            prefix=f".{source.stem}_CURVAS_",
            suffix=".pdf",
            dir=str(source.parent),
        )
        os.close(fd)
        work_output = Path(temporary_name)
        work_output.unlink(missing_ok=True)
    else:
        work_output = destination

    command = [
        ghostscript,
        "-q",
        "-dSAFER",
        "-dBATCH",
        "-dNOPAUSE",
        "-dNoOutputFonts",
        "-dAutoRotatePages=/None",
        "-dColorConversionStrategy=/LeaveColorUnchanged",
        "-sDEVICE=pdfwrite",
        "-dCompatibilityLevel=1.7",
        f"-sOutputFile={work_output}",
        str(source),
    ]

    try:
        process = subprocess.run(command, capture_output=True, text=True, timeout=900)
    except subprocess.TimeoutExpired:
        work_output.unlink(missing_ok=True)
        return _result(False, "A conversão ultrapassou 15 minutos e foi cancelada.")
    except Exception as error:
        work_output.unlink(missing_ok=True)
        return _result(False, f"Não consegui executar o Ghostscript: {error}")

    if process.returncode != 0:
        work_output.unlink(missing_ok=True)
        details = (process.stderr or process.stdout or "").strip()
        if len(details) > 1200:
            details = details[-1200:]
        return _result(
            False,
            "O Ghostscript não conseguiu converter o PDF."
            + (f"\n\n{details}" if details else ""),
            return_code=process.returncode,
        )

    try:
        preservation = preserve_output_intents(source, work_output)
    except PdfPreservationError as error:
        work_output.unlink(missing_ok=True)
        return _result(False, str(error))

    valid, validation_message = _validate_output(source, work_output)
    if not valid:
        work_output.unlink(missing_ok=True)
        return _result(False, validation_message)

    try:
        if replacing_original:
            os.replace(work_output, destination)
    except Exception as error:
        work_output.unlink(missing_ok=True)
        return _result(False, f"O PDF foi convertido, mas não consegui substituir o original: {error}")

    return _result(
        True,
        "Textos convertidos em curvas com sucesso.",
        destination,
        ghostscript=ghostscript,
        replaced_original=replacing_original,
        output_intent_preserved=preservation.output_intent_preserved,
        source_pdfx=preservation.source_pdfx,
    )


def main() -> int:
    if len(sys.argv) != 3:
        print(
            json.dumps(
                _result(False, "Uso: convert_pdf_to_curves.py origem.pdf destino.pdf"),
                ensure_ascii=False,
            )
        )
        return 2

    result = converter_pdf_em_curvas(sys.argv[1], sys.argv[2])
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
