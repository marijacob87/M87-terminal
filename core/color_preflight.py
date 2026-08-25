from __future__ import annotations

import hashlib
import os
import re
import shutil
import struct
import subprocess
import tempfile
from io import BytesIO
from pathlib import Path

import fitz
import pikepdf
from PIL import Image, ImageChops, ImageCms, ImageOps

from core.pdf_info import detect_colors


FOGRA39_LABEL = "Coated FOGRA39 (ISO 12647-2:2004)"
US_COATED_LABEL = "Standard US Coated (SWOP 2006)"
PREVIEW_MAX_EDGE = 7000

PROFILE_CANDIDATES = {
    FOGRA39_LABEL: (
        "CoatedFOGRA39.icc",
        "ISOcoated_v2_eci.icc",
        "ISOcoated_v2_300_eci.icc",
    ),
    US_COATED_LABEL: (
        "SWOP2006_Coated3v2.icc",
        "USWebCoatedSWOP.icc",
        "WebCoatedSWOP2006Grade3.icc",
    ),
}

PROFILE_DIRECTORIES = (
    Path("/Library/ColorSync/Profiles"),
    Path("/System/Library/ColorSync/Profiles"),
    Path.home() / "Library/ColorSync/Profiles",
)


class ColorPreflightError(RuntimeError):
    pass


def find_ghostscript() -> str | None:
    """Localiza o Ghostscript também quando o app é aberto pelo Finder."""
    discovered = shutil.which("gs")
    if discovered:
        return discovered
    for candidate in (
        Path("/opt/homebrew/bin/gs"),
        Path("/usr/local/bin/gs"),
        Path("/usr/bin/gs"),
    ):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def _profile_description(profile_bytes: bytes) -> str:
    try:
        profile = ImageCms.ImageCmsProfile(BytesIO(profile_bytes))
        return ImageCms.getProfileDescription(profile).strip()
    except Exception:
        return "Perfil ICC incorporado"


def find_profile(label: str) -> Path | None:
    candidates = PROFILE_CANDIDATES.get(label, ())
    for directory in PROFILE_DIRECTORIES:
        for filename in candidates:
            path = directory / filename
            if path.is_file():
                return path
    return None


def available_profiles() -> dict[str, str | None]:
    return {
        label: str(path) if (path := find_profile(label)) else None
        for label in PROFILE_CANDIDATES
    }


def _output_intents(pdf: pikepdf.Pdf) -> list[dict]:
    result = []
    for intent in pdf.Root.get("/OutputIntents", []):
        profile = intent.get("/DestOutputProfile")
        profile_bytes = profile.read_bytes() if profile is not None else b""
        identifier = str(intent.get("/OutputConditionIdentifier", "")).strip()
        info = str(intent.get("/Info", "")).strip()
        result.append({
            "identifier": identifier,
            "info": info,
            "profile": _profile_description(profile_bytes) if profile_bytes else "",
            "sha256": hashlib.sha256(profile_bytes).hexdigest() if profile_bytes else "",
        })
    return result


def _font_report(pdf: pikepdf.Pdf) -> list[dict]:
    fonts: dict[str, dict] = {}
    for page_number, page in enumerate(pdf.pages, start=1):
        resources = page.get("/Resources", {})
        for resource_name, font in resources.get("/Font", {}).items():
            base_name = str(font.get("/BaseFont", resource_name)).lstrip("/")
            descriptor = font.get("/FontDescriptor")
            if descriptor is None:
                descendants = font.get("/DescendantFonts", [])
                if descendants:
                    descriptor = descendants[0].get("/FontDescriptor")
            embedded = bool(
                descriptor is not None
                and any(descriptor.get(key) is not None for key in (
                    "/FontFile", "/FontFile2", "/FontFile3",
                ))
            )
            item = fonts.setdefault(base_name, {
                "name": base_name, "embedded": embedded, "pages": [],
            })
            item["embedded"] = item["embedded"] and embedded
            if page_number not in item["pages"]:
                item["pages"].append(page_number)
    return sorted(fonts.values(), key=lambda item: item["name"].casefold())


def _is_composite_black(values) -> bool:
    try:
        c, m, y, k = (float(value) for value in values[-4:])
    except (TypeError, ValueError):
        return False
    return k > 0.0 and any(value > 0.005 for value in (c, m, y))


def _composite_black_report(pdf: pikepdf.Pdf) -> list[dict]:
    findings = []
    text_operators = {"Tj", "TJ", "'", '"'}
    fill_operators = {"f", "F", "f*", "B", "B*", "b", "b*"}
    stroke_operators = {"S", "s", "B", "B*", "b", "b*"}
    def scan(container, resources, visited):
        fill = (0.0, 0.0, 0.0, 1.0)
        stroke = (0.0, 0.0, 0.0, 1.0)
        in_text = False
        stack = []
        text_count = vector_count = 0
        try:
            instructions = pikepdf.parse_content_stream(container)
        except Exception:
            return 0, 0
        for operands, operator in instructions:
            op = str(operator)
            if op == "q":
                stack.append((fill, stroke, in_text))
                continue
            if op == "Q":
                if stack:
                    fill, stroke, in_text = stack.pop()
            elif op == "k" and len(operands) >= 4:
                fill = tuple(operands[-4:])
            elif op == "K" and len(operands) >= 4:
                stroke = tuple(operands[-4:])
            elif op == "BT":
                in_text = True
            elif op == "ET":
                in_text = False
            elif in_text and op in text_operators and _is_composite_black(fill):
                text_count += 1
            elif op in fill_operators and _is_composite_black(fill):
                vector_count += 1
            elif op in stroke_operators and _is_composite_black(stroke):
                vector_count += 1
            elif op == "Do" and operands:
                try:
                    xobject = resources.get("/XObject", {}).get(operands[-1])
                    object_id = tuple(xobject.objgen) if xobject is not None else None
                    if (
                        xobject is not None
                        and str(xobject.get("/Subtype", "")) == "/Form"
                        and object_id not in visited
                    ):
                        visited.add(object_id)
                        child_resources = xobject.get("/Resources", resources)
                        child_text, child_vector = scan(
                            xobject, child_resources, visited,
                        )
                        text_count += child_text
                        vector_count += child_vector
                except Exception:
                    pass
        return text_count, vector_count

    for page_number, page in enumerate(pdf.pages, start=1):
        text_count, vector_count = scan(
            page, page.get("/Resources", {}), set(),
        )
        if text_count:
            findings.append({
                "page": page_number,
                "kind": "text",
                "count": text_count,
                "message": f"Texto em preto composto ({text_count} ocorrência(s))",
            })
        if vector_count:
            findings.append({
                "page": page_number,
                "kind": "vector",
                "count": vector_count,
                "message": f"Vetor em preto composto ({vector_count} ocorrência(s))",
            })
    return findings


def _image_report(path: Path) -> list[dict]:
    document = fitz.open(path)
    images = []
    try:
        for page_number, page in enumerate(document, start=1):
            for index, image in enumerate(page.get_image_info(xrefs=True), start=1):
                bbox = fitz.Rect(image["bbox"])
                if bbox.width <= 0 or bbox.height <= 0:
                    continue
                dpi_x = image["width"] * 72.0 / bbox.width
                dpi_y = image["height"] * 72.0 / bbox.height
                images.append({
                    "page": page_number,
                    "index": index,
                    "xref": int(image.get("xref") or 0),
                    "width_px": int(image["width"]),
                    "height_px": int(image["height"]),
                    "dpi_x": round(dpi_x, 1),
                    "dpi_y": round(dpi_y, 1),
                    "dpi": round(min(dpi_x, dpi_y), 1),
                    "bbox": tuple(round(value, 2) for value in bbox),
                    "colorspace": image.get("cs-name") or "Não identificado",
                })
    finally:
        document.close()
    return images


def _postscript_name(value: str) -> str:
    """Cria um nome PostScript; colorantes complexos precisam de ``cvn``."""
    safe = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_."
    raw = value.encode("utf-8")
    if raw and all(byte in safe for byte in raw):
        return "/" + raw.decode("ascii")
    escaped = "".join(
        chr(byte) if 32 <= byte <= 126 and byte not in b"()\\"
        else f"\\{byte:03o}"
        for byte in raw
    )
    return f"({escaped}) cvn"


def _psd_color_metadata(
    resources: bytes,
) -> tuple[list[str], list[tuple[float, ...]], bytes | None]:
    names_data = colors_data = b""
    icc_profile = None
    position = 0
    while position + 12 <= len(resources):
        if resources[position:position + 4] != b"8BIM":
            break
        resource_id = struct.unpack(">H", resources[position + 4:position + 6])[0]
        position += 6
        name_size = resources[position]
        position += 1 + name_size
        if (1 + name_size) % 2:
            position += 1
        size = struct.unpack(">I", resources[position:position + 4])[0]
        position += 4
        payload = resources[position:position + size]
        position += size + size % 2
        if resource_id == 0x03EE:
            names_data = payload
        elif resource_id == 0x03EF:
            colors_data = payload
        elif resource_id == 0x040F:
            icc_profile = payload
    names = []
    position = 0
    while position < len(names_data):
        size = names_data[position]
        position += 1
        raw_name = names_data[position:position + size]
        position += size
        decoded = bytearray()
        index = 0
        while index < len(raw_name):
            if raw_name[index:index + 1] == b"#" and index + 2 < len(raw_name):
                try:
                    decoded.append(int(raw_name[index + 1:index + 3], 16))
                    index += 3
                    continue
                except ValueError:
                    pass
            decoded.append(raw_name[index])
            index += 1
        try:
            names.append(bytes(decoded).decode("utf-8"))
        except UnicodeDecodeError:
            names.append(bytes(decoded).decode("mac_roman", errors="replace"))
    colors = []
    for position in range(0, len(colors_data) - 13, 14):
        color_space = struct.unpack(">H", colors_data[position:position + 2])[0]
        values = struct.unpack(">HHHH", colors_data[position + 2:position + 10])
        if color_space != 2:
            raise ColorPreflightError("Cor spot PSD não está descrita em CMYK.")
        colors.append(tuple((65535 - value) / 65535.0 for value in values))
    return names, colors, icc_profile


def _read_raw_psd_planes(
    path: Path,
) -> tuple[
    tuple[int, int], list[Image.Image], list[str],
    list[tuple[float, ...]], bytes | None,
]:
    data = path.read_bytes()
    if len(data) < 30 or data[:4] != b"8BPS" or data[4:6] != b"\x00\x01":
        raise ColorPreflightError("Ghostscript produziu um PSD inválido.")
    channels = struct.unpack(">H", data[12:14])[0]
    height, width = struct.unpack(">II", data[14:22])
    depth, color_mode = struct.unpack(">HH", data[22:26])
    if depth != 8 or color_mode != 4:
        raise ColorPreflightError("A prévia PSD não está em CMYK de 8 bits.")
    position = 26
    color_mode_size = struct.unpack(">I", data[position:position + 4])[0]
    position += 4 + color_mode_size
    resources_size = struct.unpack(">I", data[position:position + 4])[0]
    position += 4
    resources = data[position:position + resources_size]
    position += resources_size
    layer_size = struct.unpack(">I", data[position:position + 4])[0]
    position += 4 + layer_size
    if position + 2 > len(data):
        raise ColorPreflightError("Dados de imagem PSD ausentes.")
    compression = struct.unpack(">H", data[position:position + 2])[0]
    position += 2
    if compression != 0:
        raise ColorPreflightError("Compressão PSD inesperada na prévia.")
    plane_size = width * height
    expected = position + channels * plane_size
    if expected > len(data):
        raise ColorPreflightError("Planos de cor PSD incompletos.")
    planes = [
        Image.frombytes(
            "L", (width, height),
            data[position + index * plane_size:position + (index + 1) * plane_size],
        )
        for index in range(channels)
    ]
    spot_names, spot_colors, icc_profile = _psd_color_metadata(resources)
    return (width, height), planes, spot_names, spot_colors, icc_profile


def _combine_coverage(base: Image.Image, amount: Image.Image) -> Image.Image:
    remaining = ImageChops.multiply(ImageOps.invert(base), ImageOps.invert(amount))
    return ImageOps.invert(remaining)


def _cmyk_preview_to_rgb(composite: Image.Image, icc_profile: bytes) -> Image.Image:
    try:
        source = ImageCms.ImageCmsProfile(BytesIO(icc_profile))
        destination = ImageCms.createProfile("sRGB")
        intent = ImageCms.getDefaultIntent(source)
        if intent not in range(4):
            intent = 1
        return ImageCms.profileToProfile(
            composite, source, destination,
            renderingIntent=intent, outputMode="RGB",
        )
    except Exception as error:
        raise ColorPreflightError(
            "Não foi possível aplicar o perfil ICC à prévia de separações."
        ) from error


def _compose_psd_preview(
    path: Path,
    selected_process: set[str],
    expected_spots: list[str],
) -> Image.Image:
    size, planes, spot_names, spot_colors, icc_profile = _read_raw_psd_planes(path)
    if len(planes) < 4:
        raise ColorPreflightError("A prévia PSD não contém os quatro planos CMYK.")
    process_names = ("Cyan", "Magenta", "Yellow", "Black")
    channels = [
        ImageOps.invert(plane) if name in selected_process
        else Image.new("L", size, 0)
        for name, plane in zip(process_names, planes[:4])
    ]
    spot_planes = planes[4:]
    if len(spot_planes) != len(spot_names) or len(spot_names) != len(spot_colors):
        raise ColorPreflightError("Quantidade inesperada de chapas spot na prévia.")
    selected_spots = {name.casefold() for name in expected_spots}
    available_spots = {name.casefold() for name in spot_names}
    if not selected_spots.issubset(available_spots):
        missing = sorted(selected_spots - available_spots)
        raise ColorPreflightError(
            "Chapa(s) spot ausente(s) na prévia: " + ", ".join(missing)
        )
    for name, equivalent, plane in zip(spot_names, spot_colors, spot_planes):
        if name.casefold() not in selected_spots:
            continue
        coverage = ImageOps.invert(plane)
        for index, fraction in enumerate(equivalent):
            if fraction > 0:
                amount = coverage.point(
                    lambda value, scale=fraction: round(value * scale)
                )
                channels[index] = _combine_coverage(channels[index], amount)
    composite = Image.merge("CMYK", channels)
    if icc_profile is None:
        raise ColorPreflightError("A prévia de separações não contém perfil ICC.")
    return _cmyk_preview_to_rgb(composite, icc_profile)


def _spot_equivalents(output: bytes) -> dict[str, tuple[float, ...]]:
    result = {}
    pattern = re.compile(
        r'^%%SeparationColor: "(.*)" 100% ink = '
        r'(\d+) (\d+) (\d+) (\d+) CMYK$',
        re.MULTILINE,
    )
    text = output.decode("utf-8", errors="replace")
    for match in pattern.finditer(text):
        values = tuple(min(1.0, int(value) / 32760.0) for value in match.groups()[1:])
        result[match.group(1).casefold()] = values
    return result


def _compose_separation_tiffs(
    root: Path,
    colorants: list[str] | tuple[str, ...],
    spot_equivalents: dict[str, tuple[float, ...]],
    icc_profile: bytes,
) -> Image.Image:
    plate_files = {}
    for plate_path in root.glob("page(*).tif"):
        stem = plate_path.stem
        if stem.startswith("page(") and stem.endswith(")"):
            plate_files[stem[5:-1].casefold()] = plate_path
    if not plate_files:
        raise ColorPreflightError("Ghostscript não produziu arquivos de chapa.")
    first = Image.open(next(iter(plate_files.values()))).convert("L")
    channels = [Image.new("L", first.size, 0) for _ in range(4)]
    process_indexes = {"cyan": 0, "magenta": 1, "yellow": 2, "black": 3}
    for name in colorants:
        key = name.casefold()
        plate_path = plate_files.get(key)
        if plate_path is None:
            raise ColorPreflightError(f"Chapa ausente na prévia: {name}")
        coverage = ImageOps.invert(Image.open(plate_path).convert("L"))
        if key in process_indexes:
            channels[process_indexes[key]] = coverage
            continue
        equivalent = spot_equivalents.get(key)
        if equivalent is None:
            raise ColorPreflightError(f"Equivalência CMYK ausente para {name}.")
        for index, fraction in enumerate(equivalent):
            if fraction > 0:
                amount = coverage.point(
                    lambda value, scale=fraction: round(value * scale)
                )
                channels[index] = _combine_coverage(channels[index], amount)
    return _cmyk_preview_to_rgb(Image.merge("CMYK", channels), icc_profile)


def _embedded_cmyk_output_profile(path: Path) -> bytes | None:
    try:
        with pikepdf.Pdf.open(path) as pdf:
            for intent in pdf.Root.get("/OutputIntents", []):
                profile = intent.get("/DestOutputProfile")
                if profile is not None and int(profile.get("/N", 0)) == 4:
                    return profile.read_bytes()
    except (OSError, pikepdf.PdfError, ValueError, TypeError):
        return None
    return None


def _preview_output_profile(path: Path) -> bytes:
    embedded = _embedded_cmyk_output_profile(path)
    if embedded is not None:
        return embedded
    fallback = find_profile(FOGRA39_LABEL)
    if fallback is None:
        raise ColorPreflightError(
            "O PDF não contém OutputIntent e o perfil Coated FOGRA39 não está instalado."
        )
    return fallback.read_bytes()


def render_separation_preview(
    pdf_path: str | os.PathLike[str],
    page_number: int,
    colorants: list[str] | tuple[str, ...],
    dpi: int = 180,
) -> bytes:
    """Renderiza um composto somente com as chapas selecionadas."""
    path = Path(pdf_path).expanduser().resolve()
    ghostscript = find_ghostscript()
    if ghostscript is None:
        raise ColorPreflightError("Ghostscript não está instalado.")
    with fitz.open(path) as document:
        if not 1 <= page_number <= document.page_count:
            raise ColorPreflightError("Página fora do intervalo do PDF.")
        page_rect = document[page_number - 1].rect
    longest_edge = max(page_rect.width, page_rect.height)
    render_dpi = min(dpi, PREVIEW_MAX_EDGE * 72.0 / longest_edge)
    if not colorants:
        width = max(1, round(page_rect.width * render_dpi / 72))
        height = max(1, round(page_rect.height * render_dpi / 72))
        image = Image.new("RGB", (width, height), "white")
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()
    with tempfile.TemporaryDirectory(prefix="m87_separations_") as directory:
        root = Path(directory)
        output = root / "page.tif"
        output_profile = _preview_output_profile(path)
        profile_path = root / "document-output.icc"
        profile_path.write_bytes(output_profile)
        environment = os.environ.copy()
        environment["XDG_CACHE_HOME"] = str(root / "cache")
        command = [
            ghostscript, "-dSAFER", "-dBATCH", "-dNOPAUSE",
            "-sDEVICE=tiffsep", f"-r{render_dpi:.4f}", "-dMaxSpots=60",
            "-dPrintSpotCMYK",
            f"-sDefaultCMYKProfile={profile_path}",
            f"-sOutputICCProfile={profile_path}",
            f"-dFirstPage={page_number}", f"-dLastPage={page_number}",
            f"-sOutputFile={output}", str(path),
        ]
        completed = subprocess.run(
            command, capture_output=True, timeout=120, env=environment,
        )
        if completed.returncode != 0:
            details = (completed.stderr or completed.stdout).decode(
                "utf-8", errors="replace"
            ).strip()
            raise ColorPreflightError(
                f"Não foi possível renderizar as separações. {details[-800:]}"
            )
        diagnostic = completed.stdout + b"\n" + completed.stderr
        image = _compose_separation_tiffs(
            root, colorants, _spot_equivalents(diagnostic), output_profile,
        )
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()


def analyze_color_preflight(pdf_path: str | os.PathLike[str]) -> dict:
    path = Path(pdf_path).expanduser().resolve()
    if not path.is_file() or path.suffix.casefold() != ".pdf":
        raise ColorPreflightError("Selecione um arquivo PDF válido.")
    pdf_bytes = path.read_bytes()
    try:
        with pikepdf.Pdf.open(path) as pdf:
            intents = _output_intents(pdf)
            fonts = _font_report(pdf)
            composite_black = _composite_black_report(pdf)
            pdfx = str(pdf.docinfo.get("/GTS_PDFXVersion", "")).strip()
            page_count = len(pdf.pages)
        images = _image_report(path)
        colors = detect_colors(pdf_bytes)
    except Exception as error:
        raise ColorPreflightError(f"Não foi possível analisar as cores: {error}") from error

    low_resolution = [image for image in images if image["dpi"] < 72.0]
    profile_name = "Sem OutputIntent/ICC de saída"
    if intents:
        profile_name = (
            intents[0]["profile"] or intents[0]["identifier"]
            or intents[0]["info"] or "OutputIntent sem identificação"
        )
    return {
        "path": str(path),
        "name": path.name,
        "pages": page_count,
        "pdfx": pdfx,
        "colors": colors,
        "output_intents": intents,
        "profile_name": profile_name,
        "profiles_available": available_profiles(),
        "images": images,
        "low_resolution": low_resolution,
        "fonts": fonts,
        "unembedded_fonts": [font for font in fonts if not font["embedded"]],
        "composite_black": composite_black,
    }


def _page_boxes(path: Path) -> list[dict[str, tuple[float, ...] | None]]:
    names = ("MediaBox", "CropBox", "TrimBox", "BleedBox", "ArtBox")
    with pikepdf.Pdf.open(path) as pdf:
        return [{
            name: tuple(float(value) for value in page.get(f"/{name}"))
            if page.get(f"/{name}") is not None else None
            for name in names
        } for page in pdf.pages]


def _install_output_intent(path: Path, profile_path: Path, label: str) -> None:
    temporary = path.with_name(f".{path.stem}.icc{path.suffix}")
    temporary.unlink(missing_ok=True)
    try:
        with pikepdf.Pdf.open(path) as pdf:
            profile_bytes = profile_path.read_bytes()
            stream = pdf.make_stream(profile_bytes)
            stream.N = 4
            stream.Alternate = pikepdf.Name.DeviceCMYK
            intent = pdf.make_indirect(pikepdf.Dictionary({
                "/Type": pikepdf.Name.OutputIntent,
                "/S": pikepdf.Name.GTS_PDFX,
                "/OutputConditionIdentifier": label,
                "/Info": label,
                "/DestOutputProfile": stream,
            }))
            pdf.Root.OutputIntents = pikepdf.Array([intent])
            for key in ("/GTS_PDFXVersion", "/GTS_PDFXConformance"):
                if key in pdf.docinfo:
                    del pdf.docinfo[key]
            pdf.save(temporary)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def convert_pdf_to_cmyk(
    source_path: str | os.PathLike[str],
    output_path: str | os.PathLike[str],
    profile_label: str = FOGRA39_LABEL,
) -> dict:
    source = Path(source_path).expanduser().resolve()
    output = Path(output_path).expanduser().resolve()
    profile = find_profile(profile_label)
    ghostscript = find_ghostscript()
    if not source.is_file():
        raise ColorPreflightError("O PDF de origem não foi encontrado.")
    if source == output:
        raise ColorPreflightError("Use Salvar Como; o original não pode ser sobrescrito.")
    if profile is None:
        raise ColorPreflightError(f"Perfil obrigatório não encontrado: {profile_label}.")
    if ghostscript is None:
        raise ColorPreflightError("Ghostscript não está instalado.")
    output.parent.mkdir(parents=True, exist_ok=True)
    source_boxes = _page_boxes(source)
    source_report = analyze_color_preflight(source)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output.stem}_CMYK_", suffix=".pdf", dir=output.parent,
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    temporary.unlink(missing_ok=True)
    rgb_profile = Path("/System/Library/ColorSync/Profiles/sRGB Profile.icc")
    command = [
        ghostscript, "-dSAFER", "-dBATCH", "-dNOPAUSE",
        "-sDEVICE=pdfwrite", "-dCompatibilityLevel=1.7",
        "-dAutoRotatePages=/None", "-dColorConversionStrategy=/CMYK",
        "-dProcessColorModel=/DeviceCMYK", "-dOverrideICC=true",
        "-dPreserveSeparation=false", "-dConvertCMYKImagesToRGB=false",
        "-dDownsampleColorImages=false", "-dDownsampleGrayImages=false",
        "-dDownsampleMonoImages=false", "-dDetectDuplicateImages=true",
        f"-sDefaultCMYKProfile={profile}", f"-sOutputICCProfile={profile}",
        f"--permit-file-read={profile}",
        f"-sOutputFile={temporary}",
    ]
    if rgb_profile.is_file():
        command.append(f"-sDefaultRGBProfile={rgb_profile}")
        command.append(f"--permit-file-read={rgb_profile}")
    command.append(str(source))
    try:
        with tempfile.TemporaryDirectory(
            prefix=".m87_font_cache_", dir=output.parent
        ) as cache_directory:
            environment = os.environ.copy()
            environment["XDG_CACHE_HOME"] = cache_directory
            completed = subprocess.run(
                command, capture_output=True, text=True, timeout=600,
                env=environment,
            )
        if completed.returncode != 0 or not temporary.is_file():
            details = "\n".join(
                value.strip() for value in (completed.stdout, completed.stderr)
                if value.strip()
            )
            raise ColorPreflightError(f"A conversão CMYK falhou. {details[-1600:]}")
        _install_output_intent(temporary, profile, profile_label)
        output_report = analyze_color_preflight(temporary)
        if output_report["pages"] != source_report["pages"]:
            raise ColorPreflightError("Validação falhou: a quantidade de páginas mudou.")
        if _page_boxes(temporary) != source_boxes:
            raise ColorPreflightError("Validação falhou: uma ou mais caixas do PDF mudaram.")
        if output_report["colors"]["RGB"]:
            raise ColorPreflightError("Validação falhou: ainda há objetos RGB na saída.")
        source_uses_color = (
            source_report["colors"]["RGB"]
            or source_report["colors"]["CMYK"]
            or bool(source_report["colors"]["SPOTS"])
        )
        if source_uses_color and not output_report["colors"]["CMYK"]:
            raise ColorPreflightError(
                "Validação falhou: a saída não declarou conteúdo CMYK verificável."
            )
        before_dpi = sorted(image["dpi"] for image in source_report["images"])
        after_dpi = sorted(image["dpi"] for image in output_report["images"])
        if len(after_dpi) < len(before_dpi):
            raise ColorPreflightError("Validação falhou: imagens foram removidas ou combinadas.")
        for before, after in zip(before_dpi, after_dpi):
            if after + 0.6 < before:
                raise ColorPreflightError(
                    f"Validação falhou: DPI efetivo caiu de {before:.1f} para {after:.1f}."
                )
        os.replace(temporary, output)
        return {
            "output": str(output), "profile": profile_label,
            "images": len(output_report["images"]),
            "minimum_dpi": min(after_dpi) if after_dpi else None,
        }
    finally:
        temporary.unlink(missing_ok=True)
