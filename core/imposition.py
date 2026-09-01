from __future__ import annotations

import math
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF

from core.pdf_preservation import (
    PdfPreservationError,
    preserve_output_intents,
)

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
    output_intent_preserved: bool = False
    source_pdfx: str = ""


def _rect_close(a: fitz.Rect, b: fitz.Rect, tolerance_pt: float = 0.15) -> bool:
    return all(abs(x - y) <= tolerance_pt for x, y in zip(a, b))


def effective_bleed_rect(page: fitz.Page) -> fitz.Rect:
    """Retorna a BleedBox original completa, limitada apenas pela MediaBox."""
    return fitz.Rect(page.bleedbox) & fitz.Rect(page.mediabox)


def _property_ocg_names(doc: fitz.Document, page: fitz.Page) -> dict[str, str]:
    """Relaciona propriedades de conteúdo marcado aos nomes visíveis das OCGs."""
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
    """Remove blocos completos /OC /Property BDC ... EMC das camadas selecionadas."""
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
                # Fluxo malformado: preserva o restante intacto para não danificar a arte.
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
    """Remove camadas de marcas do PDF, preservando a arte e toda a BleedBox.

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
    """Abre o PDF e remove da memória as camadas originais de marcas gráficas."""
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
    bottom_margin_extra_mm: float = 0.0,
) -> list[LayoutOption]:
    if min(paper_width_mm, paper_height_mm, trim_width_mm, trim_height_mm) <= 0:
        return []

    usable_w = max(0.0, paper_width_mm - 2.0 * margin_mm)
    usable_h = max(
        0.0, paper_height_mm - 2.0 * margin_mm - bottom_margin_extra_mm
    )
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
    bottom_margin_extra_mm: float = 0.0,
) -> LayoutOption | None:
    """Cria uma grade manual centralizada e retorna None quando ela não cabe."""
    if min(paper_width_mm, paper_height_mm, trim_width_mm, trim_height_mm) <= 0:
        return None
    if columns < 1 or rows < 1:
        return None

    item_w, item_h = (trim_height_mm, trim_width_mm) if rotated else (trim_width_mm, trim_height_mm)
    usable_w = max(0.0, paper_width_mm - 2.0 * margin_mm)
    usable_h = max(
        0.0, paper_height_mm - 2.0 * margin_mm - bottom_margin_extra_mm
    )
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


def transform_duplex_back_slots(
    values: list,
    rows: int,
    columns: int,
    paper_width_mm: float,
    paper_height_mm: float,
    flip_long_edge: bool,
) -> list:
    """Converte a grade lógica do verso para as coordenadas físicas do PDF.

    A interface mostra frente e verso em posições correspondentes. Para que
    essas posições coincidam depois da virada, o PDF do verso precisa ser
    espelhado no eixo determinado pela orientação e pela borda escolhida.
    """
    if rows < 1 or columns < 1 or len(values) != rows * columns:
        return list(values)
    matrix = [
        list(values[row * columns:(row + 1) * columns])
        for row in range(rows)
    ]
    portrait = paper_height_mm >= paper_width_mm
    mirror_columns = flip_long_edge == portrait
    if mirror_columns:
        matrix = [list(reversed(row)) for row in matrix]
    else:
        matrix = list(reversed(matrix))
    return [value for row in matrix for value in row]

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
    # inferior→esquerda e esquerda→superior.
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
    distance_mm: float = 3.0,
    thickness_pt: float = 0.25,
) -> None:
    """Desenha marcas de corte somente no perímetro externo da grade imposta.

    Every trim boundary is indicated, but the marks live only above/below or
    left/right of the complete montage, never between positioned pages.
    """
    length = length_mm * MM_TO_PT
    distance = distance_mm * MM_TO_PT
    width = max(0.1, thickness_pt)
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
        # Em modo repetir, "quantidade" é a tiragem total desejada.
        # Ex.: 500 unidades / 4 por folha = 125 planos, independentemente
        # do número de páginas do PDF usado como origem.
        return math.ceil(quantity_each / items_per_sheet)
    imposed_pages_per_set = math.ceil(page_count / items_per_sheet)
    return imposed_pages_per_set * quantity_each


def build_imposition_groups(
    mode: str,
    page_count: int,
    items_per_sheet: int,
) -> list[list[int | None]]:
    """Organiza as páginas de origem nas posições de cada folha.

    No modo ``stacked``, cada posição recebe um bloco contínuo de páginas.
    Assim, ao cortar uma grade, as pilhas já ficam em ordem de numeração.
    """
    if page_count < 1 or items_per_sheet < 1:
        return []
    if mode == "repeat":
        return [[page_index] * items_per_sheet for page_index in range(page_count)]

    sheets = math.ceil(page_count / items_per_sheet)
    if mode == "stacked":
        return [
            [
                sheet_index + slot_index * sheets
                if sheet_index + slot_index * sheets < page_count
                else None
                for slot_index in range(items_per_sheet)
            ]
            for sheet_index in range(sheets)
        ]

    return [
        [
            source_index if source_index < page_count else None
            for source_index in range(
                start, start + items_per_sheet,
            )
        ]
        for start in range(0, page_count, items_per_sheet)
    ]


def _safe_filename_part(value: str, fallback: str) -> str:
    clean = " ".join(str(value).strip().split())
    for char in '<>:"/\\|?*':
        clean = clean.replace(char, "-")
    return clean.strip(" .-") or fallback


def automatic_filename(
    source_path: str | os.PathLike[str],
    quantity: int,
    plans: int,
    material: str,
    each_artwork: bool = False,
) -> str:
    stem = _safe_filename_part(Path(source_path).stem, "Arquivo")
    clean_material = _safe_filename_part(material, "Material")
    date_text = datetime.now().strftime("%d%m%Y")
    # ``plans`` representa a quantidade de folhas de produção por página/arte.
    # Em PDFs frente e verso, ambas as páginas usam a mesma tiragem; somá-las
    # produziria um nome incompatível com o lançamento 10+10 na planilha.
    production_text = f"{quantity}un {plans}p"
    return f"{production_text}_{clean_material}_{stem}_{date_text}.pdf"


def automatic_sheet_label(
    source_path: str | os.PathLike[str],
    quantity: int,
    plans: int,
    material: str,
    each_artwork: bool = False,
) -> str:
    """Texto padrão usado para identificar cada folha imposta."""
    stem = _safe_filename_part(Path(source_path).stem, "Arquivo")
    clean_material = _safe_filename_part(material, "Material")
    date_text = datetime.now().strftime("%d/%m/%Y")
    return f"{quantity}un {plans} Planos • {clean_material} • {stem} • {date_text}"


def _draw_sheet_label(
    page: fitz.Page,
    layout: LayoutOption,
    text: str,
) -> None:
    """Desenha uma única identificação no topo direito da folha imposta."""
    label = " ".join(str(text).split())
    if not label:
        return
    font_name = "helv"
    font_size = 10.0
    right_x = (layout.paper_width_mm - 50.0) * MM_TO_PT
    text_width = fitz.get_text_length(label, fontname=font_name, fontsize=font_size)
    left_x = max(3.0 * MM_TO_PT, right_x - text_width)

    # A base fica dentro da faixa superior livre e termina 0,5 mm antes
    # do primeiro TrimBox. Com a margem padrão de 5 mm, o texto fica
    # visualmente a cerca de 3 mm do topo sem nunca entrar na arte.
    first_trim_top = layout.start_y_mm * MM_TO_PT
    baseline_y = min(8.2 * MM_TO_PT, first_trim_top - 0.5 * MM_TO_PT)
    if baseline_y - font_size < 0.5 * MM_TO_PT:
        return

    page.insert_text(
        fitz.Point(left_x, baseline_y),
        label,
        fontname=font_name,
        fontsize=font_size,
        color=(0.0, 0.0, 0.0),
        overlay=True,
    )

def export_imposition(
    source_path: str | os.PathLike[str],
    output_path: str | os.PathLike[str],
    layout: LayoutOption,
    gutter_mm: float,
    mode: str,
    quantity_each: int,
    crop_marks: bool = True,
    fill_order: str = "rows",
    identify_sheets: bool = True,
    sheet_label: str = "",
    crop_mark_offset_mm: float = 3.0,
    crop_mark_length_mm: float = 5.0,
    crop_mark_thickness_pt: float = 0.25,
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
        source_metadata = {
            key: value
            for key, value in source.metadata.items()
            if value and key in {
                "title",
                "author",
                "subject",
                "keywords",
                "creator",
            }
        }
        if source_metadata:
            output.set_metadata(source_metadata)

        page_groups = build_imposition_groups(
            mode, source.page_count, layout.total
        )

        # PyMuPDF may otherwise honour a restrictive source CropBox even when
        # Como clip=BleedBox é fornecido, expõe temporariamente a MediaBox completa
        # na memória para manter o bleed original disponível no posicionamento vetorial.
        for source_page in source:
            try:
                source_page.set_cropbox(source_page.mediabox)
            except Exception:
                pass

        for group in page_groups:
            out_page = output.new_page(width=paper_w_pt, height=paper_h_pt)
            for slot_index, source_index in enumerate(group):
                if source_index is None:
                    continue
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
                _draw_outer_crop_marks(
                    out_page,
                    layout,
                    gutter_mm,
                    length_mm=crop_mark_length_mm,
                    distance_mm=crop_mark_offset_mm,
                    thickness_pt=crop_mark_thickness_pt,
                )

            if identify_sheets and sheet_label.strip():
                _draw_sheet_label(out_page, layout, sheet_label)

            # Páginas novas já nascem com MediaBox, CropBox, TrimBox e
            # BleedBox coincidentes com o tamanho completo da folha.

        # garbage=4 / deflate mantém vetores, fontes, CMYK, spot colors e transparências.
        output.save(out_path, garbage=4, deflate=True, clean=False)
        preservation = preserve_output_intents(src_path, out_path)
    except PdfPreservationError as exc:
        try:
            if out_path.exists():
                out_path.unlink()
        except OSError:
            pass
        raise ImpositionError(str(exc)) from exc
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
        output_intent_preserved=preservation.output_intent_preserved,
        source_pdfx=preservation.source_pdfx,
    )


def export_manual_imposition(
    source_path: str | os.PathLike[str],
    output_path: str | os.PathLike[str],
    layout: LayoutOption,
    gutter_mm: float,
    front_pages: list[int | None],
    back_pages: list[int | None] | None = None,
    front_rotations: list[int] | None = None,
    back_rotations: list[int] | None = None,
    crop_marks: bool = True,
    crop_mark_offset_mm: float = 3.0,
    crop_mark_length_mm: float = 5.0,
    crop_mark_thickness_pt: float = 0.25,
) -> ExportSummary:
    """Exporta uma folha manual, usando índices de página baseados em zero.

    A ordem recebida corresponde exatamente à grade mostrada na tela, da
    esquerda para a direita e de cima para baixo. ``None`` mantém o slot vazio.
    """
    src_path = Path(source_path).expanduser().resolve()
    out_path = Path(output_path).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sides = [list(front_pages)]
    rotations = [list(front_rotations or [0] * layout.total)]
    if back_pages is not None:
        sides.append(list(back_pages))
        rotations.append(list(back_rotations or [0] * layout.total))
    if any(len(side) != layout.total for side in sides):
        raise ImpositionError("A quantidade de posições não corresponde à grade.")
    if any(len(side_rotations) != layout.total for side_rotations in rotations):
        raise ImpositionError("A quantidade de rotações não corresponde à grade.")

    try:
        source = open_pdf_for_imposition(src_path)
    except Exception as exc:
        raise ImpositionError(f"Não foi possível abrir o PDF para exportar: {exc}") from exc

    output = fitz.open()
    try:
        for value in (page for side in sides for page in side if page is not None):
            if value < 0 or value >= source.page_count:
                raise ImpositionError(f"A página {value + 1} não existe no PDF.")

        for source_page in source:
            try:
                source_page.set_cropbox(source_page.mediabox)
            except Exception:
                pass

        for side_index, side in enumerate(sides):
            out_page = output.new_page(
                width=layout.paper_width_mm * MM_TO_PT,
                height=layout.paper_height_mm * MM_TO_PT,
            )
            for slot_index, source_index in enumerate(side):
                if source_index is None:
                    continue
                row, col = divmod(slot_index, layout.columns)
                trim_dest = _trim_rect_for_slot(layout, row, col, gutter_mm)
                src_page = source[source_index]
                src_trim = fitz.Rect(src_page.trimbox)
                src_bleed = effective_bleed_rect(src_page)
                bleed_dest = _bleed_destination(
                    trim_dest, src_trim, src_bleed, layout.rotated
                )
                out_page.show_pdf_page(
                    bleed_dest,
                    source,
                    source_index,
                    keep_proportion=True,
                    overlay=True,
                    rotate=(
                        (90 if layout.rotated else 0)
                        + rotations[side_index][slot_index]
                    ) % 360,
                    clip=src_bleed,
                )
            if crop_marks:
                _draw_outer_crop_marks(
                    out_page,
                    layout,
                    gutter_mm,
                    length_mm=crop_mark_length_mm,
                    distance_mm=crop_mark_offset_mm,
                    thickness_pt=crop_mark_thickness_pt,
                )

        output.save(out_path, garbage=4, deflate=True, clean=False)
        preservation = preserve_output_intents(src_path, out_path)
    except PdfPreservationError as exc:
        if out_path.exists():
            out_path.unlink()
        raise ImpositionError(str(exc)) from exc
    except Exception as exc:
        if out_path.exists():
            out_path.unlink()
        if isinstance(exc, ImpositionError):
            raise
        raise ImpositionError(f"Não foi possível gerar a imposição: {exc}") from exc
    finally:
        output.close()
        source.close()

    return ExportSummary(
        output_path=out_path,
        requested_quantity=1,
        plans=1,
        imposed_pages=len(sides),
        items_per_sheet=layout.total,
        output_intent_preserved=preservation.output_intent_preserved,
        source_pdfx=preservation.source_pdfx,
    )
