from __future__ import annotations

import os
import shutil
import subprocess
import time
import uuid
from pathlib import Path


KONICA_SHARE_URL = "smb://GUEST:@192.168.1.235/KONICA%20PROVA%20FV"
KONICA_MOUNT_POINT = Path("/Volumes/KONICA PROVA FV")


class KonicaSpoolError(RuntimeError):
    pass


def ensure_konica_mounted(
    mount_point: Path = KONICA_MOUNT_POINT,
    share_url: str = KONICA_SHARE_URL,
) -> Path:
    mount_point = Path(mount_point)
    if mount_point.is_dir() and os.access(mount_point, os.W_OK):
        return mount_point

    try:
        result = subprocess.run(
            ["/usr/bin/osascript", "-e", f'mount volume "{share_url}"'],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise KonicaSpoolError(f"Não foi possível conectar à Hot Folder: {exc}") from exc

    if result.returncode:
        message = result.stderr.strip() or result.stdout.strip() or "erro desconhecido"
        raise KonicaSpoolError(f"Não foi possível conectar à Hot Folder: {message}")

    for _attempt in range(30):
        if mount_point.is_dir() and os.access(mount_point, os.W_OK):
            return mount_point
        time.sleep(0.1)
    raise KonicaSpoolError("A Hot Folder foi conectada, mas não está disponível para escrita.")


def _available_destination(folder: Path, filename: str) -> Path:
    source_name = Path(filename).name
    stem = Path(source_name).stem or "M87"
    suffix = Path(source_name).suffix or ".pdf"
    candidate = folder / f"{stem}{suffix}"
    counter = 2
    while candidate.exists():
        candidate = folder / f"{stem} ({counter}){suffix}"
        counter += 1
    return candidate


def send_pdf_to_hold(
    source: str | Path,
    mount_point: Path = KONICA_MOUNT_POINT,
) -> Path:
    source = Path(source).expanduser().resolve()
    if not source.is_file() or source.suffix.casefold() != ".pdf":
        raise KonicaSpoolError("O arquivo enviado à Konica precisa ser um PDF válido.")

    folder = ensure_konica_mounted(Path(mount_point))
    destination = _available_destination(folder, source.name)
    temporary = folder / f".m87-{uuid.uuid4().hex}.upload"
    try:
        shutil.copyfile(source, temporary)
        if temporary.stat().st_size != source.stat().st_size:
            raise KonicaSpoolError("A cópia para a Konica ficou incompleta.")
        os.replace(temporary, destination)
    except KonicaSpoolError:
        raise
    except OSError as exc:
        raise KonicaSpoolError(f"Não foi possível enviar o PDF à Konica: {exc}") from exc
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
    return destination
