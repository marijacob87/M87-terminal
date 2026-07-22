from __future__ import annotations

import math
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

import fitz  # PyMuPDF

MM_TO_PT = 72.0 / 25.4
PT_TO_MM = 25.4 / 72.0


class ImpositionError(RuntimeError):
    pass


@dataclass(frozen=True)
class PdfGeometry:
    trim_width_mm: float
    trim_height_mm: float
    page_count: int
    bleed_left_mm: float
    bleed_top_mm: float
    bleed_right_mm: float
    bleed_bottom_mm: float
    has_minimum_bleed: bool


@dataclass(frozen=True)
class LayoutOption:
    rotated: bool
    columns: int
    rows: int
    total: int
    item_width_mm: float
    item_height_mm: float
    occupied_width_mm: float
    occupied_height_mm: float
    start_x_mm: float
    start_y_mm: float
    utilization: float
    paper_width_mm: float
    paper_height_mm: float

    @property
    def orientation_label(self) -> str:
        return "Arte rotacionada 90°" if self.rotated else "Arte normal"


@dataclass(frozen=True)
class ExportSummary:
    output_path: Path
    requested_quantity: int
    plans: int
    imposed_pages: int
    items_per_sheet: int


def _rect_close(a: fitz.Rect, b: fitz.Rect, tolerance_pt: float = 0.15) -> bool:
    return all(abs(x - y) <= tolerance_pt for x, y in zip(a, b))


def effective_bleed_rect(page: fitz.Page) -> fitz.Rect:
    """Return the complete original BleedBox, limited only by MediaBox."""
    return fitz.Rect(page.bleedbox) & fitz.Rect(page.mediabox)


def _property_ocg_names(doc: fitz.Document, page: fitz.Page) -> dict[str, str]:
    """Map page marked-content property names to their OCG display names."""
    import re

    page_object = doc.xref_object(page.xref, compressed=False)
    match = re.search(r"/Properties\s*<<(.*?)>>", page_object, flags=re.S)
    if not match:
        return {}

    result: dict[str, str] = {}
    for prop, xref_text in re.findall(r"/(\w+)\s+(\d+)\s+0\s+R", match.group(1)):
        try:
            ocg_object = doc.xref_object(int(xref_text), compressed=False)
        except Exception:
            continue
        name_match = re.search(r"/Name\s*\((.*?)\)", ocg_object, flags=re.S)
        if name_match:
            result[prop] = name_match.group(1)
    return result


def _remove_marked_content_blocks(stream: bytes, properties: set[str]) -> bytes:
    """Remove complete /OC /Property BDC ... EMC blocks for selected layers."""
    import re

    if not properties:
        return stream

    token_pattern = re.compile(rb"/OC\s+/([A-Za-z0-9_]+)\s+BDC|\bBMC\b|\bBDC\b|\bEMC\b")
    output = bytearray()
    cursor = 0
    pos = 0

    while True:
        match = token_pattern.search(stream, pos)
        if not match:
            output.extend(stream[cursor:])
            break

        prop = match.group(1)
        if prop is None or prop.decode("latin1") not in properties:
            pos = match.end()
            continue

        output.extend(stream[cursor:match.start()])
        depth = 1
        scan = match.end()
        while depth:
            nested = token_pattern.search(stream, scan)
            if not nested:
                # Malformed stream: keep the untouched tail rather than damage artwork.
                output.extend(stream[match.start():])
                return bytes(output)
            token = nested.group(0)
            if token.endswith(b"BDC") or token == b"BMC":
                depth += 1
            elif token == b"EMC":
                depth -= 1
            scan = nested.end()

        cursor = scan
        pos = scan

    return bytes(output)


def remove_original_printer_marks(doc: fitz.Document) -> None:
    """Remove PDF mark layers while leaving artwork and the entire BleedBox intact.

    Illustrator and other prepress applications commonly put crop / registration
    marks in Optional Content Groups named ``Marks & Bleeds``. Removing that
    marked-content block is object-level cleanup: no white rectangles are drawn
    and no bleed artwork is clipped or rasterized.
    """
    for page in doc:
        mapping = _property_ocg_names(doc, page)
        target_properties = {
            prop for prop, name in mapping.items()
            if "mark" in name.casefold() or "bleed" in name.casefold()
        }
        if not target_properties:
            continue
        for xref in page.get_contents():
            try:
                original = doc.xref_stream(xref)
                cleaned = _remove_marked_content_blocks(original, target_properties)
                if cleaned != original:
                    doc.update_stream(xref, cleaned)
            except Exception:
                continue


def open_pdf_for_imposition(path: str | os.PathLike[str]) -> fitz.Document:
    """Open a PDF and remove original printer-mark layers in memory."""
    doc = fitz.open(Path(path).expanduser().resolve())
    remove_original_printer_marks(doc)
    return doc


def inspect_pdf(path: str | os.PathLike[str]) -> PdfGeometry:
    pdf_path = Path(path).expanduser().resolve()
    if not pdf_path.exists() or pdf_path.suffix.lower() != ".pdf":
        raise ImpositionError("Selecione um arquivo PDF válido.")

    try:
        doc = fitz.open(pdf_path)
    except Exception as exc:
        raise ImpositionError(f"Não foi possível abrir o PDF: {exc}") from exc

    try:
        if doc.needs_pass:
            raise ImpositionError("O PDF é protegido por senha.")
        if doc.page_count < 1:
            raise ImpositionError("O PDF não possui páginas.")

        first = doc[0]
        first_trim = fitz.Rect(first.trimbox)
        first_bleed = effective_bleed_rect(first)
        bleed_values = [
            (first_trim.x0 - first_bleed.x0) * PT_TO_MM,
            (first_trim.y0 - first_bleed.y0) * PT_TO_MM,
            (first_bleed.x1 - first_trim.x1) * PT_TO_MM,
            (first_bleed.y1 - first_trim.y1) * PT_TO_MM,
        ]
        has_minimum_bleed = all(value >= 2.99 for value in bleed_values)

        for index in range(1, doc.page_count):
            page = doc[index]
            page_trim = fitz.Rect(page.trimbox)
            if not _rect_close(page_trim, first_trim):
                raise ImpositionError(
                    "As páginas possuem TrimBox diferentes. Padronize o PDF antes de montar."
                )
            page_bleed = effective_bleed_rect(page)
            page_bleed_values = (
                (page_trim.x0 - page_bleed.x0) * PT_TO_MM,
                (page_trim.y0 - page_bleed.y0) * PT_TO_MM,
                (page_bleed.x1 - page_trim.x1) * PT_TO_MM,
                (page_bleed.y1 - page_trim.y1) * PT_TO_MM,
            )
            has_minimum_bleed = has_minimum_bleed and all(
                value >= 2.99 for value in page_bleed_values
            )

        return PdfGeometry(
            trim_width_mm=first_trim.width * PT_TO_MM,
            trim_height_mm=first_trim.height * PT_TO_MM,
            page_count=doc.page_count,
            bleed_left_mm=max(0.0, (first_trim.x0 - first_bleed.x0) * PT_TO_MM),
            bleed_top_mm=max(0.0, (first_trim.y0 - first_bleed.y0) * PT_TO_MM),
            bleed_right_mm=max(0.0, (first_bleed.x1 - first_trim.x1) * PT_TO_MM),
            bleed_bottom_mm=max(0.0, (first_bleed.y1 - first_trim.y1) * PT_TO_MM),
            has_minimum_bleed=has_minimum_bleed,
        )
    finally:
        doc.close()


def calculate_layouts(
    paper_width_mm: float,
    paper_height_mm: float,
    trim_width_mm: float,
    trim_height_mm: float,
    gutter_mm: float,
    margin_mm: float,
) -> list[LayoutOption]:
    if min(paper_width_mm, paper_height_mm, trim_width_mm, trim_height_mm) <= 0:
        return []

    usable_w = max(0.0, paper_width_mm - 2.0 * margin_mm)
    usable_h = max(0.0, paper_height_mm - 2.0 * margin_mm)
    options: list[LayoutOption] = []

    for rotated, item_w, item_h in (
        (False, trim_width_mm, trim_height_mm),
        (True, trim_height_mm, trim_width_mm),
    ):
        columns = int((usable_w + gutter_mm) // (item_w + gutter_mm))
        rows = int((usable_h + gutter_mm) // (item_h + gutter_mm))
        if columns < 1 or rows < 1:
            continue
        occupied_w = columns * item_w + max(0, columns - 1) * gutter_mm
        occupied_h = rows * item_h + max(0, rows - 1) * gutter_mm
        start_x = margin_mm + (usable_w - occupied_w) / 2.0
        start_y = margin_mm + (usable_h - occupied_h) / 2.0
        total = columns * rows
        utilization = (total * trim_width_mm * trim_height_mm) / (
            paper_width_mm * paper_height_mm
        ) * 100.0
        options.append(
            LayoutOption(
                rotated=rotated,
                columns=columns,
                rows=rows,
                total=total,
                item_width_mm=item_w,
                item_height_mm=item_h,
                occupied_width_mm=occupied_w,
                occupied_height_mm=occupied_h,
                start_x_mm=start_x,
                start_y_mm=start_y,
                utilization=utilization,
                paper_width_mm=paper_width_mm,
                paper_height_mm=paper_height_mm,
            )
        )

    # Mesma regra do MON: quantidade, aproveitamento e, no empate, arte normal.
    options.sort(
        key=lambda x: (x.total, x.utilization, not x.rotated),
        reverse=True,
    )
    return options[:2]



def build_custom_layout(
    paper_width_mm: float,
    paper_height_mm: float,
    trim_width_mm: float,
    trim_height_mm: float,
    gutter_mm: float,
    margin_mm: float,
    columns: int,
    rows: int,
    rotated: bool,
) -> LayoutOption | None:
    """Build a centered manual grid, returning None when it does not fit."""
    if min(paper_width_mm, paper_height_mm, trim_width_mm, trim_height_mm) <= 0:
        return None
    if columns < 1 or rows < 1:
        return None

    item_w, item_h = (trim_height_mm, trim_width_mm) if rotated else (trim_width_mm, trim_height_mm)
    usable_w = max(0.0, paper_width_mm - 2.0 * margin_mm)
    usable_h = max(0.0, paper_height_mm - 2.0 * margin_mm)
    occupied_w = columns * item_w + max(0, columns - 1) * gutter_mm
    occupied_h = rows * item_h + max(0, rows - 1) * gutter_mm
    if occupied_w > usable_w + 1e-6 or occupied_h > usable_h + 1e-6:
        return None

    start_x = margin_mm + (usable_w - occupied_w) / 2.0
    start_y = margin_mm + (usable_h - occupied_h) / 2.0
    total = columns * rows
    utilization = (total * trim_width_mm * trim_height_mm) / (paper_width_mm * paper_height_mm) * 100.0
    return LayoutOption(
        rotated=rotated,
        columns=columns,
        rows=rows,
        total=total,
        item_width_mm=item_w,
        item_height_mm=item_h,
        occupied_width_mm=occupied_w,
        occupied_height_mm=occupied_h,
        start_x_mm=start_x,
        start_y_mm=start_y,
        utilization=utilization,
        paper_width_mm=paper_width_mm,
        paper_height_mm=paper_height_mm,
    )

def _placement_rects(layout: LayoutOption) -> Iterable[tuple[int, fitz.Rect]]:
    index = 0
    for row in range(layout.rows):
        for col in range(layout.columns):
            x0 = layout.start_x_mm + col * (layout.item_width_mm + 0.0)
            # Add gutter separately to avoid cumulative floating surprises.
            x0 += col * 0.0
            y0 = layout.start_y_mm + row * (layout.item_height_mm + 0.0)
            y0 += row * 0.0
            # Actual step is reconstructed from occupied geometry below by caller.
            yield index, fitz.Rect(
                x0 * MM_TO_PT,
                y0 * MM_TO_PT,
                (x0 + layout.item_width_mm) * MM_TO_PT,
                (y0 + layout.item_height_mm) * MM_TO_PT,
            )
            index += 1


def _trim_rect_for_slot(layout: LayoutOption, row: int, col: int, gutter_mm: float) -> fitz.Rect:
    x0 = layout.start_x_mm + col * (layout.item_width_mm + gutter_mm)
    y0 = layout.start_y_mm + row * (layout.item_height_mm + gutter_mm)
    return fitz.Rect(
        x0 * MM_TO_PT,
        y0 * MM_TO_PT,
        (x0 + layout.item_width_mm) * MM_TO_PT,
        (y0 + layout.item_height_mm) * MM_TO_PT,
    )


def _bleed_destination(trim_dest: fitz.Rect, source_trim: fitz.Rect, source_bleed: fitz.Rect, rotated: bool) -> fitz.Rect:
    left = max(0.0, source_trim.x0 - source_bleed.x0)
    top = max(0.0, source_trim.y0 - source_bleed.y0)
    right = max(0.0, source_bleed.x1 - source_trim.x1)
    bottom = max(0.0, source_bleed.y1 - source_trim.y1)

    if not rotated:
        return fitz.Rect(
            trim_dest.x0 - left,
            trim_dest.y0 - top,
            trim_dest.x1 + right,
            trim_dest.y1 + bottom,
        )

    # After clockwise 90° rotation: top->right, right->bottom,
    # bottom->left and left->top.
    return fitz.Rect(
        trim_dest.x0 - bottom,
        trim_dest.y0 - left,
        trim_dest.x1 + top,
        trim_dest.y1 + right,
    )


def _draw_outer_crop_marks(
    page: fitz.Page,
    layout: LayoutOption,
    gutter_mm: float,
    length_mm: float = 5.0,
    distance_mm: float = 5.0,
    thickness_mm: float = 0.08,
) -> None:
    """Draw cut marks only around the outside perimeter of the imposed grid.

    Every trim boundary is indicated, but the marks live only above/below or
    left/right of the complete montage, never between positioned pages.
    """
    length = length_mm * MM_TO_PT
    distance = distance_mm * MM_TO_PT
    width = max(0.1, thickness_mm * MM_TO_PT)
    black = (0.0, 0.0, 0.0)

    left = layout.start_x_mm * MM_TO_PT
    top = layout.start_y_mm * MM_TO_PT
    right = (layout.start_x_mm + layout.occupied_width_mm) * MM_TO_PT
    bottom = (layout.start_y_mm + layout.occupied_height_mm) * MM_TO_PT

    x_boundaries: list[float] = []
    for col in range(layout.columns):
        x0 = (layout.start_x_mm + col * (layout.item_width_mm + gutter_mm)) * MM_TO_PT
        x1 = x0 + layout.item_width_mm * MM_TO_PT
        x_boundaries.extend((x0, x1))

    y_boundaries: list[float] = []
    for row in range(layout.rows):
        y0 = (layout.start_y_mm + row * (layout.item_height_mm + gutter_mm)) * MM_TO_PT
        y1 = y0 + layout.item_height_mm * MM_TO_PT
        y_boundaries.extend((y0, y1))

    # Remove coincident boundaries while preserving numeric stability.
    x_boundaries = sorted({round(value, 4) for value in x_boundaries})
    y_boundaries = sorted({round(value, 4) for value in y_boundaries})

    shape = page.new_shape()
    for x in x_boundaries:
        shape.draw_line(fitz.Point(x, top - distance - length), fitz.Point(x, top - distance))
        shape.draw_line(fitz.Point(x, bottom + distance), fitz.Point(x, bottom + distance + length))
    for y in y_boundaries:
        shape.draw_line(fitz.Point(left - distance - length, y), fitz.Point(left - distance, y))
        shape.draw_line(fitz.Point(right + distance, y), fitz.Point(right + distance + length, y))
    shape.finish(color=black, width=width)
    shape.commit(overlay=True)


def calculate_plans(mode: str, page_count: int, items_per_sheet: int, quantity_each: int) -> int:
    if items_per_sheet < 1 or quantity_each < 1:
        return 0
    if mode == "repeat":
        return page_count * math.ceil(quantity_each / items_per_sheet)
    imposed_pages_per_set = math.ceil(page_count / items_per_sheet)
    return imposed_pages_per_set * quantity_each


def _safe_filename_part(value: str, fallback: str) -> str:
    clean = " ".join(str(value).strip().split())
    for char in '<>:"/\\|?*':
        clean = clean.replace(char, "-")
    return clean.strip(" .-") or fallback


def automatic_filename(source_path: str | os.PathLike[str], quantity: int, plans: int,
                       material: str) -> str:
    stem = _safe_filename_part(Path(source_path).stem, "Arquivo")
    clean_material = _safe_filename_part(material, "Material")
    date_text = datetime.now().strftime("%d%m%Y")
    return f"{quantity}un {plans}Planos - {clean_material} - {stem} X_{date_text}.pdf"


def export_imposition(
    source_path: str | os.PathLike[str],
    output_path: str | os.PathLike[str],
    layout: LayoutOption,
    gutter_mm: float,
    mode: str,
    quantity_each: int,
    crop_marks: bool = True,
    fill_order: str = "rows",
) -> ExportSummary:
    src_path = Path(source_path).expanduser().resolve()
    out_path = Path(output_path).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        source = open_pdf_for_imposition(src_path)
    except Exception as exc:
        raise ImpositionError(f"Não foi possível abrir o PDF para exportar: {exc}") from exc

    output = fitz.open()
    try:
        paper_w_pt = layout.paper_width_mm * MM_TO_PT
        paper_h_pt = layout.paper_height_mm * MM_TO_PT

        if mode == "repeat":
            page_groups = [[page_index] * layout.total for page_index in range(source.page_count)]
        else:
            page_groups = [
                list(range(start, min(start + layout.total, source.page_count)))
                for start in range(0, source.page_count, layout.total)
            ]

        # PyMuPDF may otherwise honour a restrictive source CropBox even when
        # clip=BleedBox is supplied. Expose the complete MediaBox in-memory so
        # the original bleed remains available for vector placement.
        for source_page in source:
            try:
                source_page.set_cropbox(source_page.mediabox)
            except Exception:
                pass

        for group in page_groups:
            out_page = output.new_page(width=paper_w_pt, height=paper_h_pt)
            for slot_index, source_index in enumerate(group):
                if fill_order == "columns":
                    col, row = divmod(slot_index, layout.rows)
                else:
                    row, col = divmod(slot_index, layout.columns)
                trim_dest = _trim_rect_for_slot(layout, row, col, gutter_mm)
                src_page = source[source_index]
                src_trim = fitz.Rect(src_page.trimbox)
                src_bleed = effective_bleed_rect(src_page)
                bleed_dest = _bleed_destination(trim_dest, src_trim, src_bleed, layout.rotated)

                out_page.show_pdf_page(
                    bleed_dest,
                    source,
                    source_index,
                    keep_proportion=True,
                    overlay=True,
                    rotate=90 if layout.rotated else 0,
                    clip=src_bleed,
                )

            if crop_marks:
                _draw_outer_crop_marks(out_page, layout, gutter_mm)

            # Páginas novas já nascem com MediaBox, CropBox, TrimBox e
            # BleedBox coincidentes com o tamanho completo da folha.

        # garbage=4 / deflate mantém vetores, fontes, CMYK, spot colors e transparências.
        output.save(out_path, garbage=4, deflate=True, clean=False)
    except Exception as exc:
        try:
            if out_path.exists():
                out_path.unlink()
        except OSError:
            pass
        if isinstance(exc, ImpositionError):
            raise
        raise ImpositionError(f"Não foi possível gerar a imposição: {exc}") from exc
    finally:
        output.close()
        source.close()

    page_count = inspect_pdf(src_path).page_count
    plans = calculate_plans(mode, page_count, layout.total, quantity_each)
    return ExportSummary(
        output_path=out_path,
        requested_quantity=quantity_each,
        plans=plans,
        imposed_pages=len(page_groups),
        items_per_sheet=layout.total,
    )


def open_in_acrobat(path: str | os.PathLike[str]) -> None:
    pdf_path = str(Path(path).expanduser().resolve())
    try:
        subprocess.Popen(["open", "-a", "Adobe Acrobat", pdf_path])
    except Exception:
        subprocess.Popen(["open", pdf_path])
