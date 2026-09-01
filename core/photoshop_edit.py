from __future__ import annotations

import subprocess
from pathlib import Path

import fitz
from PIL import Image

from core.page_organizer import PageSpec, save_pages


PHOTOSHOP_BUNDLE_ID = "com.adobe.Photoshop"
EDIT_DPI = 300
DEFAULT_BLEED_MM = 3.0


class PhotoshopEditError(RuntimeError):
    pass


def prepare_page_for_photoshop(
    base_path: str | Path,
    spec: PageSpec,
    work_dir: str | Path,
    bleed_mm: float = 0.0,
) -> tuple[Path, Path]:
    folder = Path(work_dir).expanduser().resolve()
    folder.mkdir(parents=True, exist_ok=True)
    template = folder / "photoshop_page_template.pdf"
    image_path = folder / "pagina_para_editar.tif"
    try:
        save_pages(base_path, [spec], template)
        with fitz.open(template) as document:
            page = document[0]
            pixmap = page.get_pixmap(
                dpi=EDIT_DPI,
                colorspace=fitz.csCMYK,
                alpha=False,
                clip=page.trimbox if bleed_mm > 0 else None,
            )
            image = Image.frombytes(
                "CMYK",
                (pixmap.width, pixmap.height),
                pixmap.samples,
            )
            if bleed_mm > 0:
                image = _extend_edges(image, bleed_mm)
            image.save(
                image_path,
                format="TIFF",
                compression="tiff_lzw",
                dpi=(EDIT_DPI, EDIT_DPI),
            )
    except Exception as exc:
        raise PhotoshopEditError(
            f"Não foi possível preparar a página para o Photoshop: {exc}"
        ) from exc
    return image_path, template


def _extend_edges(image: Image.Image, bleed_mm: float) -> Image.Image:
    if bleed_mm <= 0:
        return image.copy()
    bleed_px = max(1, round(bleed_mm * EDIT_DPI / 25.4))
    sample_px = max(1, min(bleed_px, round(EDIT_DPI / 25.4)))
    width, height = image.size
    expanded = Image.new(
        image.mode,
        (width + 2 * bleed_px, height + 2 * bleed_px),
    )
    expanded.paste(image, (bleed_px, bleed_px))
    resample = Image.Resampling.BICUBIC

    left = image.crop((0, 0, sample_px, height)).resize(
        (bleed_px, height), resample
    )
    right = image.crop((width - sample_px, 0, width, height)).resize(
        (bleed_px, height), resample
    )
    top = image.crop((0, 0, width, sample_px)).resize(
        (width, bleed_px), resample
    )
    bottom = image.crop((0, height - sample_px, width, height)).resize(
        (width, bleed_px), resample
    )
    expanded.paste(left, (0, bleed_px))
    expanded.paste(right, (bleed_px + width, bleed_px))
    expanded.paste(top, (bleed_px, 0))
    expanded.paste(bottom, (bleed_px, bleed_px + height))

    for source_box, destination in (
        ((0, 0, sample_px, sample_px), (0, 0)),
        (
            (width - sample_px, 0, width, sample_px),
            (bleed_px + width, 0),
        ),
        (
            (0, height - sample_px, sample_px, height),
            (0, bleed_px + height),
        ),
        (
            (width - sample_px, height - sample_px, width, height),
            (bleed_px + width, bleed_px + height),
        ),
    ):
        corner = image.crop(source_box).resize((bleed_px, bleed_px), resample)
        expanded.paste(corner, destination)
    return expanded


def open_in_photoshop(path: str | Path) -> None:
    candidate = Path(path).expanduser().resolve()
    try:
        result = subprocess.run(
            [
                "/usr/bin/open", "-b", PHOTOSHOP_BUNDLE_ID,
                str(candidate),
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PhotoshopEditError(f"Não foi possível abrir o Photoshop: {exc}") from exc
    if result.returncode:
        message = result.stderr.strip() or "Adobe Photoshop não encontrado."
        raise PhotoshopEditError(message)


def edited_image_to_pdf(
    image_path: str | Path,
    template_path: str | Path,
    output_path: str | Path,
    bleed_mm: float = 0.0,
) -> Path:
    image_path = Path(image_path).expanduser().resolve()
    template_path = Path(template_path).expanduser().resolve()
    output_path = Path(output_path).expanduser().resolve()
    try:
        image_data = image_path.read_bytes()
        with fitz.open(template_path) as template:
            source = template[0]
            media = fitz.Rect(source.mediabox)
            crop = fitz.Rect(source.cropbox)
            trim = fitz.Rect(source.trimbox)
            bleed = fitz.Rect(source.bleedbox)
            art = fitz.Rect(source.artbox)
            metadata = template.metadata

        result = fitz.open()
        if bleed_mm > 0:
            bleed_pt = bleed_mm * 72.0 / 25.4
            page_width = trim.width + 2 * bleed_pt
            page_height = trim.height + 2 * bleed_pt
        else:
            bleed_pt = 0.0
            page_width = media.width
            page_height = media.height
        page = result.new_page(width=page_width, height=page_height)
        page.insert_image(page.rect, stream=image_data, keep_proportion=False)
        if bleed_mm > 0:
            full = fitz.Rect(0, 0, page_width, page_height)
            final_trim = fitz.Rect(
                bleed_pt,
                bleed_pt,
                page_width - bleed_pt,
                page_height - bleed_pt,
            )
            boxes = (
                (page.set_cropbox, full),
                (page.set_bleedbox, full),
                (page.set_trimbox, final_trim),
                (page.set_artbox, final_trim),
            )
        else:
            boxes = (
                (page.set_cropbox, crop),
                (page.set_bleedbox, bleed),
                (page.set_trimbox, trim),
                (page.set_artbox, art),
            )
        for setter, box in boxes:
            try:
                setter(box)
            except ValueError:
                pass
        result.set_metadata(metadata)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        result.save(output_path, garbage=4, deflate=True)
        result.close()
    except Exception as exc:
        raise PhotoshopEditError(
            f"Não foi possível atualizar a página editada: {exc}"
        ) from exc
    return output_path
