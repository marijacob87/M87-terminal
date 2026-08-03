from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import pikepdf

MM_TO_PT = 72.0 / 25.4
PT_TO_MM = 25.4 / 72.0
ANCHORS = {
    "top_left", "top", "top_right",
    "left", "center", "right",
    "bottom_left", "bottom", "bottom_right",
}


class GeometryError(RuntimeError):
    pass


@dataclass(frozen=True)
class BoxGeometry:
    x_mm: float
    y_mm: float
    width_mm: float
    height_mm: float


@dataclass(frozen=True)
class PageGeometry:
    media: BoxGeometry
    trim: BoxGeometry
    rotation: int


@dataclass(frozen=True)
class GeometryDocumentInfo:
    path: Path
    pages: tuple[PageGeometry, ...]

    @property
    def page_count(self) -> int:
        return len(self.pages)


@dataclass(frozen=True)
class FormatSettings:
    width_mm: float
    height_mm: float
    anchor: str = "center"
    allow_distortion: bool = False


@dataclass(frozen=True)
class BoxSettings:
    x_mm: float
    y_mm: float
    width_mm: float
    height_mm: float


@dataclass(frozen=True)
class CropMarkSettings:
    enabled: bool = False
    offset_mm: float = 3.0
    length_mm: float = 5.0
    thickness_pt: float = 0.25


@dataclass(frozen=True)
class GeometrySettings:
    format: FormatSettings | None = None
    media: BoxSettings | None = None
    trim: BoxSettings | None = None
    rotation_degrees: int = 0
    remove_outside_trim: bool = False
    crop_marks: CropMarkSettings = field(default_factory=CropMarkSettings)


def _numbers(value) -> tuple[float, float, float, float]:
    return tuple(float(number) for number in value)


def _box(page, name: str, fallback=None) -> tuple[float, float, float, float]:
    value = page.obj.get(name)
    if value is None:
        if fallback is None:
            raise GeometryError(f"A página não possui {name}.")
        return fallback
    return _numbers(value)


def _geometry_from_boxes(
    media: tuple[float, float, float, float],
    trim: tuple[float, float, float, float],
) -> tuple[BoxGeometry, BoxGeometry]:
    mx0, my0, mx1, my1 = media
    tx0, ty0, tx1, ty1 = trim
    media_geometry = BoxGeometry(
        0.0, 0.0, (mx1 - mx0) * PT_TO_MM, (my1 - my0) * PT_TO_MM
    )
    # A interface usa origem no canto superior esquerdo.
    trim_geometry = BoxGeometry(
        (tx0 - mx0) * PT_TO_MM,
        (my1 - ty1) * PT_TO_MM,
        (tx1 - tx0) * PT_TO_MM,
        (ty1 - ty0) * PT_TO_MM,
    )
    return media_geometry, trim_geometry


def inspect_geometry(path: str | os.PathLike[str]) -> GeometryDocumentInfo:
    pdf_path = Path(path).expanduser().resolve()
    if not pdf_path.is_file() or pdf_path.suffix.casefold() != ".pdf":
        raise GeometryError("Selecione um arquivo PDF válido.")
    try:
        with pikepdf.Pdf.open(pdf_path) as pdf:
            if not pdf.pages:
                raise GeometryError("O PDF não possui páginas.")
            pages = []
            for page in pdf.pages:
                media = _box(page, "/MediaBox")
                trim = _box(page, "/TrimBox", media)
                media_info, trim_info = _geometry_from_boxes(media, trim)
                pages.append(PageGeometry(
                    media=media_info,
                    trim=trim_info,
                    rotation=int(page.obj.get("/Rotate", 0)) % 360,
                ))
    except GeometryError:
        raise
    except pikepdf.PasswordError as exc:
        raise GeometryError("O PDF é protegido por senha.") from exc
    except Exception as exc:
        raise GeometryError(f"Não foi possível abrir o PDF: {exc}") from exc
    return GeometryDocumentInfo(pdf_path, tuple(pages))


def _anchor_factors(anchor: str) -> tuple[float, float]:
    if anchor not in ANCHORS:
        anchor = "center"
    horizontal = 0.0 if anchor.endswith("left") or anchor == "left" else (
        1.0 if anchor.endswith("right") or anchor == "right" else 0.5
    )
    vertical = 1.0 if anchor.startswith("top") or anchor == "top" else (
        0.0 if anchor.startswith("bottom") or anchor == "bottom" else 0.5
    )
    return horizontal, vertical


def _transform_rect(rect, matrix) -> list[float]:
    x0, y0, x1, y1 = _numbers(rect)
    sx, sy, tx, ty = matrix
    xs = (sx * x0 + tx, sx * x1 + tx)
    ys = (sy * y0 + ty, sy * y1 + ty)
    return [min(xs), min(ys), max(xs), max(ys)]


def _transform_points(values, matrix) -> pikepdf.Array:
    sx, sy, tx, ty = matrix
    result = []
    numbers = [float(value) for value in values]
    for index in range(0, len(numbers) - 1, 2):
        result.extend((sx * numbers[index] + tx, sy * numbers[index + 1] + ty))
    return pikepdf.Array(result)


def _wrap_page_contents(pdf, page, matrix) -> None:
    sx, sy, tx, ty = matrix
    prefix = pdf.make_stream(
        f"q\n{sx:.10f} 0 0 {sy:.10f} {tx:.10f} {ty:.10f} cm\n".encode("ascii")
    )
    suffix = pdf.make_stream(b"\nQ\n")
    contents = page.obj.get("/Contents")
    if contents is None:
        page.obj.Contents = pikepdf.Array([prefix, suffix])
    elif isinstance(contents, pikepdf.Array):
        page.obj.Contents = pikepdf.Array([prefix, *contents, suffix])
    else:
        page.obj.Contents = pikepdf.Array([prefix, contents, suffix])


def _transform_rect_affine(rect, matrix) -> list[float]:
    a, b, c, d, e, f = matrix
    x0, y0, x1, y1 = _numbers(rect)
    points = (
        (a * x + c * y + e, b * x + d * y + f)
        for x, y in ((x0, y0), (x0, y1), (x1, y0), (x1, y1))
    )
    transformed = tuple(points)
    xs = tuple(point[0] for point in transformed)
    ys = tuple(point[1] for point in transformed)
    return [min(xs), min(ys), max(xs), max(ys)]


def _transform_points_affine(values, matrix) -> pikepdf.Array:
    a, b, c, d, e, f = matrix
    numbers = [float(value) for value in values]
    result = []
    for index in range(0, len(numbers) - 1, 2):
        x, y = numbers[index], numbers[index + 1]
        result.extend((a * x + c * y + e, b * x + d * y + f))
    return pikepdf.Array(result)


def _rotate_page_clockwise(pdf, page) -> None:
    """Gira fisicamente uma página 90° sem rasterizar seu conteúdo."""
    media = _box(page, "/MediaBox")
    x0, y0, x1, y1 = media
    width = x1 - x0
    height = y1 - y0
    matrix = (0.0, -1.0, 1.0, 0.0, -y0, x1)
    prefix = pdf.make_stream(
        b"q\n0 -1 1 0 "
        + f"{-y0:.10f} {x1:.10f} cm\n".encode("ascii")
    )
    suffix = pdf.make_stream(b"\nQ\n")
    contents = page.obj.get("/Contents")
    if contents is None:
        page.obj.Contents = pikepdf.Array([prefix, suffix])
    elif isinstance(contents, pikepdf.Array):
        page.obj.Contents = pikepdf.Array([prefix, *contents, suffix])
    else:
        page.obj.Contents = pikepdf.Array([prefix, contents, suffix])

    for box_name in ("/MediaBox", "/CropBox", "/BleedBox", "/TrimBox", "/ArtBox"):
        box = page.obj.get(box_name)
        if box is not None:
            page.obj[box_name] = pikepdf.Array(
                _transform_rect_affine(box, matrix)
            )
    page.obj.MediaBox = pikepdf.Array([0, 0, height, width])

    for annotation in page.obj.get("/Annots", ()):
        if annotation.get("/Rect") is not None:
            annotation.Rect = pikepdf.Array(
                _transform_rect_affine(annotation.Rect, matrix)
            )
        if annotation.get("/QuadPoints") is not None:
            annotation.QuadPoints = _transform_points_affine(
                annotation.QuadPoints, matrix
            )


def normalize_page_rotation(pdf, page, additional_degrees: int = 0) -> None:
    """Converte /Rotate em conteúdo e caixas, deixando a página canônica."""
    current = int(page.obj.get("/Rotate", 0)) % 360
    additional = int(additional_degrees) % 360
    total = (current + additional) % 360
    if total % 90:
        raise GeometryError("A rotação deve ser múltipla de 90°.")
    if "/Rotate" in page.obj:
        del page.obj["/Rotate"]
    for _ in range(total // 90):
        _rotate_page_clockwise(pdf, page)


def _resize_format(pdf, page, settings: FormatSettings) -> None:
    if settings.width_mm <= 0 or settings.height_mm <= 0:
        raise GeometryError("As medidas do formato devem ser maiores que zero.")
    media = _box(page, "/MediaBox")
    old_width = media[2] - media[0]
    old_height = media[3] - media[1]
    new_width = settings.width_mm * MM_TO_PT
    new_height = settings.height_mm * MM_TO_PT
    sx = new_width / old_width
    sy = new_height / old_height
    if not settings.allow_distortion:
        sx = sy = min(sx, sy)
    ax, ay = _anchor_factors(settings.anchor)
    tx = (new_width - old_width * sx) * ax - media[0] * sx
    ty = (new_height - old_height * sy) * ay - media[1] * sy
    matrix = (sx, sy, tx, ty)
    _wrap_page_contents(pdf, page, matrix)

    for box_name in ("/CropBox", "/BleedBox", "/TrimBox", "/ArtBox"):
        box = page.obj.get(box_name)
        if box is not None:
            page.obj[box_name] = pikepdf.Array(_transform_rect(box, matrix))
    page.obj.MediaBox = pikepdf.Array([0, 0, new_width, new_height])

    annotations = page.obj.get("/Annots", ())
    for annotation in annotations:
        if annotation.get("/Rect") is not None:
            annotation.Rect = pikepdf.Array(_transform_rect(annotation.Rect, matrix))
        if annotation.get("/QuadPoints") is not None:
            annotation.QuadPoints = _transform_points(annotation.QuadPoints, matrix)


def _ui_box_to_pdf(
    settings: BoxSettings,
    media: tuple[float, float, float, float],
) -> list[float]:
    if settings.width_mm <= 0 or settings.height_mm <= 0:
        raise GeometryError("As medidas das caixas devem ser maiores que zero.")
    mx0, _my0, _mx1, my1 = media
    x0 = mx0 + settings.x_mm * MM_TO_PT
    y1 = my1 - settings.y_mm * MM_TO_PT
    return [
        x0,
        y1 - settings.height_mm * MM_TO_PT,
        x0 + settings.width_mm * MM_TO_PT,
        y1,
    ]


def _contains(outer, inner, tolerance=0.01) -> bool:
    return (
        inner[0] >= outer[0] - tolerance
        and inner[1] >= outer[1] - tolerance
        and inner[2] <= outer[2] + tolerance
        and inner[3] <= outer[3] + tolerance
    )


def _translate_page(pdf, page, tx: float, ty: float) -> None:
    if abs(tx) < 1e-9 and abs(ty) < 1e-9:
        return
    matrix = (1.0, 1.0, tx, ty)
    _wrap_page_contents(pdf, page, matrix)
    for box_name in ("/CropBox", "/BleedBox", "/TrimBox", "/ArtBox"):
        box = page.obj.get(box_name)
        if box is not None:
            page.obj[box_name] = pikepdf.Array(_transform_rect(box, matrix))
    annotations = page.obj.get("/Annots", ())
    for annotation in annotations:
        if annotation.get("/Rect") is not None:
            annotation.Rect = pikepdf.Array(_transform_rect(annotation.Rect, matrix))
        if annotation.get("/QuadPoints") is not None:
            annotation.QuadPoints = _transform_points(annotation.QuadPoints, matrix)


def _set_boxes(pdf, page, media_settings, trim_settings) -> None:
    current_media = _box(page, "/MediaBox")
    if media_settings is not None:
        new_media = _ui_box_to_pdf(media_settings, current_media)
        old_center_x = (current_media[0] + current_media[2]) / 2.0
        old_center_y = (current_media[1] + current_media[3]) / 2.0
        new_center_x = (new_media[0] + new_media[2]) / 2.0
        new_center_y = (new_media[1] + new_media[3]) / 2.0
        _translate_page(
            pdf, page,
            new_center_x - old_center_x,
            new_center_y - old_center_y,
        )
    else:
        new_media = list(current_media)
    new_trim = (
        _ui_box_to_pdf(trim_settings, new_media)
        if trim_settings is not None else list(_box(page, "/TrimBox", new_media))
    )
    if not _contains(new_media, new_trim):
        raise GeometryError("A TrimBox precisa ficar inteiramente dentro da MediaBox.")
    page.obj.MediaBox = pikepdf.Array(new_media)
    page.obj.TrimBox = pikepdf.Array(new_trim)
    # CropBox não pode ficar fora da nova MediaBox.
    crop = _box(page, "/CropBox", current_media)
    if not _contains(new_media, crop):
        page.obj.CropBox = pikepdf.Array(new_media)


def _crop_mark_segments(trim, settings: CropMarkSettings):
    x0, y0, x1, y1 = trim
    offset = settings.offset_mm * MM_TO_PT
    length = settings.length_mm * MM_TO_PT
    for x in (x0, x1):
        yield (x, y0 - offset, x, y0 - offset - length)
        yield (x, y1 + offset, x, y1 + offset + length)
    for y in (y0, y1):
        yield (x0 - offset, y, x0 - offset - length, y)
        yield (x1 + offset, y, x1 + offset + length, y)


def _add_crop_marks(pdf, page, settings: CropMarkSettings) -> None:
    if settings.offset_mm < 0 or settings.length_mm <= 0 or settings.thickness_pt <= 0:
        raise GeometryError("Os valores das marcas de corte são inválidos.")
    trim = _box(page, "/TrimBox", _box(page, "/MediaBox"))
    segments = tuple(_crop_mark_segments(trim, settings))
    commands = ["q", "0 0 0 1 K", f"{settings.thickness_pt:.4f} w"]
    commands.extend(
        f"{x0:.5f} {y0:.5f} m {x1:.5f} {y1:.5f} l S"
        for x0, y0, x1, y1 in segments
    )
    commands.append("Q")
    stream = pdf.make_stream(("\n".join(commands) + "\n").encode("ascii"))
    contents = page.obj.get("/Contents")
    if contents is None:
        page.obj.Contents = stream
    elif isinstance(contents, pikepdf.Array):
        contents.append(stream)
    else:
        page.obj.Contents = pikepdf.Array([contents, stream])


def _page_indexes(page_count: int, indexes: Iterable[int]) -> tuple[int, ...]:
    unique = tuple(dict.fromkeys(int(index) for index in indexes))
    if not unique or any(index < 0 or index >= page_count for index in unique):
        raise GeometryError("A seleção de páginas é inválida.")
    return unique


def _fully_outside(rect, trim) -> bool:
    return (
        rect[2] <= trim[0] or rect[0] >= trim[2]
        or rect[3] <= trim[1] or rect[1] >= trim[3]
    )


def _matrix_multiply(left, right):
    a, b, c, d, e, f = left
    g, h, i, j, k, l = right
    return (
        a * g + c * h, b * g + d * h,
        a * i + c * j, b * i + d * j,
        a * k + c * l + e, b * k + d * l + f,
    )


def _transform_xy(matrix, x, y):
    a, b, c, d, e, f = matrix
    return a * x + c * y + e, b * x + d * y + f


def _path_points(operator, operands):
    values = [float(value) for value in operands]
    if operator in {"m", "l"}:
        return [(values[0], values[1])]
    if operator == "c":
        return list(zip(values[::2], values[1::2]))
    if operator == "v":
        return list(zip(values[::2], values[1::2]))
    if operator == "y":
        return list(zip(values[::2], values[1::2]))
    if operator == "re":
        x, y, width, height = values
        return [(x, y), (x + width, y + height)]
    return []


def _remove_objects_outside_trim(pdf, indexes: tuple[int, ...]) -> None:
    """Remove apenas caminhos vetoriais comprovadamente externos à TrimBox.

    O conteúdo não é renderizado nem redimensionado. Textos, imagens, máscaras,
    transparências e objetos que tocam a TrimBox são preservados.
    """
    path_operators = {"m", "l", "c", "v", "y", "h", "re"}
    paint_operators = {"S", "s", "f", "F", "f*", "B", "B*", "b", "b*"}
    for index in indexes:
        page = pdf.pages[index]
        trim = _box(page, "/TrimBox", _box(page, "/MediaBox"))
        instructions = pikepdf.parse_content_stream(page)
        output = []
        buffered = []
        points = []
        current_matrix = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
        matrix_stack = []
        has_clip = False
        for instruction in instructions:
            operands, raw_operator = instruction
            operator = str(raw_operator)
            if operator == "q":
                matrix_stack.append(current_matrix)
            elif operator == "Q":
                current_matrix = (
                    matrix_stack.pop() if matrix_stack
                    else (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
                )
            elif operator == "cm" and len(operands) == 6:
                matrix = tuple(float(value) for value in operands)
                current_matrix = _matrix_multiply(current_matrix, matrix)

            if operator in path_operators:
                buffered.append(instruction)
                points.extend(
                    _transform_xy(current_matrix, x, y)
                    for x, y in _path_points(operator, operands)
                )
                continue
            if buffered:
                buffered.append(instruction)
                if operator in {"W", "W*"}:
                    has_clip = True
                    continue
                if operator not in paint_operators | {"n"}:
                    continue
                outside = False
                if points:
                    xs, ys = zip(*points)
                    bounds = (min(xs), min(ys), max(xs), max(ys))
                    outside = _fully_outside(bounds, trim)
                if has_clip or not outside or operator == "n":
                    output.extend(buffered)
                buffered = []
                points = []
                has_clip = False
                continue
            output.append(instruction)
        output.extend(buffered)
        page.obj.Contents = pdf.make_stream(
            pikepdf.unparse_content_stream(output)
        )


def apply_geometry(
    source_path: str | os.PathLike[str],
    output_path: str | os.PathLike[str],
    settings: GeometrySettings,
    page_indexes: Iterable[int],
) -> GeometryDocumentInfo:
    source = Path(source_path).expanduser().resolve()
    output = Path(output_path).expanduser().resolve()
    if source == output:
        raise GeometryError("Use um arquivo de saída diferente do PDF de origem.")
    info = inspect_geometry(source)
    indexes = _page_indexes(info.page_count, page_indexes)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.stem}_geometry.tmp.pdf")
    temporary.unlink(missing_ok=True)
    try:
        with pikepdf.Pdf.open(source) as pdf:
            for index in indexes:
                page = pdf.pages[index]
                normalize_page_rotation(pdf, page, settings.rotation_degrees)
                if settings.format is not None:
                    _resize_format(pdf, page, settings.format)
                if settings.media is not None or settings.trim is not None:
                    _set_boxes(pdf, page, settings.media, settings.trim)
            if settings.remove_outside_trim:
                _remove_objects_outside_trim(pdf, indexes)
            # Alterar conteúdo ou caixas invalida a conformidade formal,
            # embora OutputIntents e o perfil ICC continuem incorporados.
            for key in ("/GTS_PDFXVersion", "/GTS_PDFXConformance"):
                if key in pdf.docinfo:
                    del pdf.docinfo[key]
            pdf.save(temporary)
        if settings.crop_marks.enabled:
            marked = temporary.with_name(f".{output.stem}_marks.tmp.pdf")
            with pikepdf.Pdf.open(temporary) as pdf:
                for index in indexes:
                    _add_crop_marks(pdf, pdf.pages[index], settings.crop_marks)
                pdf.save(marked)
            os.replace(marked, temporary)
        os.replace(temporary, output)
    except GeometryError:
        temporary.unlink(missing_ok=True)
        raise
    except Exception as exc:
        temporary.unlink(missing_ok=True)
        raise GeometryError(f"Não foi possível aplicar a geometria: {exc}") from exc
    return inspect_geometry(output)
