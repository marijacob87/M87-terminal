from __future__ import annotations

import atexit
import io
import tempfile
from pathlib import Path

import fitz
from PIL import Image, ImageOps, UnidentifiedImageError


IMAGE_EXTENSIONS = {
    ".bmp", ".gif", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp",
}
DEFAULT_DPI = 300.0
_temporary_pdfs: set[Path] = set()


class ImagePdfError(RuntimeError):
    pass


def is_supported_image(path: str | Path) -> bool:
    candidate = Path(path).expanduser()
    return candidate.is_file() and candidate.suffix.casefold() in IMAGE_EXTENSIONS


def _valid_dpi(value) -> float:
    try:
        dpi = float(value)
    except (TypeError, ValueError):
        return DEFAULT_DPI
    return dpi if 10 <= dpi <= 2400 else DEFAULT_DPI


def _image_dpi(image: Image.Image) -> tuple[float, float]:
    stored = image.info.get("dpi")
    if isinstance(stored, (tuple, list)) and len(stored) >= 2:
        return _valid_dpi(stored[0]), _valid_dpi(stored[1])
    return DEFAULT_DPI, DEFAULT_DPI


def _renderable_image(image: Image.Image) -> bytes:
    image = ImageOps.exif_transpose(image)
    icc_profile = image.info.get("icc_profile")
    if image.mode in {"RGBA", "LA"} or "transparency" in image.info:
        rgba = image.convert("RGBA")
        flattened = Image.new("RGB", rgba.size, "white")
        flattened.paste(rgba, mask=rgba.getchannel("A"))
        image = flattened
    elif image.mode == "CMYK":
        stream = io.BytesIO()
        save_options = {
            "format": "JPEG", "quality": 100, "subsampling": 0,
        }
        if icc_profile:
            save_options["icc_profile"] = icc_profile
        image.save(stream, **save_options)
        return stream.getvalue()
    elif image.mode not in {"RGB", "L"}:
        image = image.convert("RGB")
    stream = io.BytesIO()
    save_options = {"format": "PNG", "optimize": True}
    if icc_profile:
        save_options["icc_profile"] = icc_profile
    image.save(stream, **save_options)
    return stream.getvalue()


def images_to_pdf(paths: list[str | Path]) -> Path:
    images = [Path(path).expanduser().resolve() for path in paths]
    if not images:
        raise ImagePdfError("Nenhuma imagem foi selecionada.")
    invalid = [path.name for path in images if not is_supported_image(path)]
    if invalid:
        raise ImagePdfError(f"Formato de imagem não suportado: {invalid[0]}")

    first_name = images[0].stem or "imagens"
    prefix = f"m87_{first_name[:40]}_"
    handle = tempfile.NamedTemporaryFile(prefix=prefix, suffix=".pdf", delete=False)
    output = Path(handle.name)
    handle.close()
    document = fitz.open()
    try:
        for path in images:
            try:
                with Image.open(path) as source:
                    dpi_x, dpi_y = _image_dpi(source)
                    rendered = ImageOps.exif_transpose(source)
                    width_px, height_px = rendered.size
                    image_data = _renderable_image(source)
            except (OSError, UnidentifiedImageError, ValueError) as exc:
                raise ImagePdfError(f"Não foi possível converter {path.name}: {exc}") from exc

            width_pt = max(1.0, width_px * 72.0 / dpi_x)
            height_pt = max(1.0, height_px * 72.0 / dpi_y)
            page = document.new_page(width=width_pt, height=height_pt)
            page.insert_image(page.rect, stream=image_data, keep_proportion=False)

        document.save(output, garbage=4, deflate=True)
    except ImagePdfError:
        output.unlink(missing_ok=True)
        raise
    except Exception as exc:
        output.unlink(missing_ok=True)
        raise ImagePdfError(f"Não foi possível criar o PDF: {exc}") from exc
    finally:
        document.close()

    _temporary_pdfs.add(output)
    return output


def _cleanup_temporary_pdfs() -> None:
    for path in tuple(_temporary_pdfs):
        path.unlink(missing_ok=True)


atexit.register(_cleanup_temporary_pdfs)
