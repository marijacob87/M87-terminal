from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

import pikepdf

from core.geometry import normalize_page_rotation


@dataclass(frozen=True)
class PageSpec:
    source: Path
    page_index: int
    rotation: int = 0


def page_specs(path: str | Path) -> list[PageSpec]:
    source = Path(path).expanduser().resolve()
    with pikepdf.Pdf.open(source) as pdf:
        return [PageSpec(source, index) for index in range(len(pdf.pages))]


def rotated(spec: PageSpec, degrees: int) -> PageSpec:
    return replace(spec, rotation=(spec.rotation + degrees) % 360)


def reorder_pages(
    pages: list[PageSpec], selected_rows: list[int], target: int,
) -> tuple[list[PageSpec], int]:
    rows = sorted({int(row) for row in selected_rows if 0 <= int(row) < len(pages)})
    if not rows:
        return list(pages), 0
    selected = set(rows)
    moving = [pages[row] for row in rows]
    remaining = [page for index, page in enumerate(pages) if index not in selected]
    insertion = int(target) - sum(row < int(target) for row in rows)
    insertion = max(0, min(insertion, len(remaining)))
    reordered = remaining[:insertion] + moving + remaining[insertion:]
    if len(reordered) != len(pages):
        raise RuntimeError("A reordenação alterou indevidamente a quantidade de páginas.")
    return reordered, insertion


def save_pages(
    base_path: str | Path,
    pages: list[PageSpec],
    output_path: str | Path,
) -> Path:
    if not pages:
        raise ValueError("O PDF precisa manter pelo menos uma página.")

    base = Path(base_path).expanduser().resolve()
    output = Path(output_path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    sources: dict[Path, pikepdf.Pdf] = {}
    try:
        for source in {item.source for item in pages}:
            sources[source] = pikepdf.Pdf.open(source)

        with pikepdf.Pdf.open(base) as result:
            del result.pages[:]
            for spec in pages:
                source_page = sources[spec.source].pages[spec.page_index]
                copied = pikepdf.Page(result.copy_foreign(source_page.obj))
                normalize_page_rotation(result, copied, spec.rotation)
                result.pages.append(copied)
            result.save(output)
    finally:
        for pdf in sources.values():
            pdf.close()
    return output


def split_pages(
    base_path: str | Path,
    pages: list[PageSpec],
    output_dir: str | Path,
    pages_per_file: int,
) -> list[Path]:
    if pages_per_file < 1:
        raise ValueError("A quantidade de páginas por arquivo deve ser maior que zero.")

    base = Path(base_path).expanduser().resolve()
    folder = Path(output_dir).expanduser().resolve()
    outputs = []
    for start in range(0, len(pages), pages_per_file):
        number = start // pages_per_file + 1
        output = folder / f"{base.stem}_parte_{number:02d}.pdf"
        suffix = 2
        while output.exists():
            output = folder / f"{base.stem}_parte_{number:02d}_{suffix}.pdf"
            suffix += 1
        save_pages(base, pages[start : start + pages_per_file], output)
        outputs.append(output)
    return outputs
