import re
from pathlib import Path


_FILENAME_PATTERN = re.compile(
    r"^(?P<units>\d+)un\s+(?P<plans>\d+)(?:Planos|pl|p)_"
    r"(?P<material>[^_]+)_(?P<name>.+)_(?P<date>\d{8})$",
    re.IGNORECASE,
)


def filename_from_sheet_label(label: str) -> str:
    parts = [part.strip() for part in label.split("•")]
    if len(parts) != 4 or not all(parts):
        return f"{Path(label.strip()).stem}.pdf"
    production, material, name, date = parts
    production = re.sub(
        r"^(\d+un)\s+(\d+)\s*Planos$",
        r"\1 \2p",
        production,
        flags=re.IGNORECASE,
    )
    date = date.replace("/", "")
    return f"{production}_{material}_{name}_{date}.pdf"


def sheet_label_from_filename(filename: str) -> str:
    match = _FILENAME_PATTERN.match(Path(filename.strip()).stem)
    if not match:
        return Path(filename.strip()).stem
    production = f"{match.group('units')}un {match.group('plans')} Planos"
    date = match.group("date")
    formatted_date = f"{date[:2]}/{date[2:4]}/{date[4:]}"
    return (
        f"{production} • {match.group('material')} • "
        f"{match.group('name')} • {formatted_date}"
    )
