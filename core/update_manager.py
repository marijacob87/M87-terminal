"""Instala pacotes de atualização locais do M87 com backup único."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable, Iterable


PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKUP_DIR = PROJECT_ROOT / "backup"
LAST_BACKUP = BACKUP_DIR / "ultimo_backup.zip"
MANIFEST_NAME = "update.json"


class UpdateError(RuntimeError):
    """Erro seguro e apresentável durante a atualização."""


@dataclass(frozen=True)
class UpdatePackage:
    zip_path: Path
    package_root: str
    name: str
    version: str
    description: str
    files: tuple[str, ...]
    restart: bool = True

    @property
    def file_count(self) -> int:
        return len(self.files)


def _safe_relative_path(value: str) -> str:
    normalized = value.replace("\\", "/").strip("/")
    path = PurePosixPath(normalized)

    if not normalized or path.is_absolute() or ".." in path.parts:
        raise UpdateError(f"Caminho inválido no pacote: {value}")

    if path.name in {"", ".DS_Store"} or "__MACOSX" in path.parts:
        raise UpdateError(f"Arquivo inválido no pacote: {value}")

    return path.as_posix()


def _find_manifest(names: Iterable[str]) -> tuple[str, str]:
    candidates = []

    for raw_name in names:
        name = raw_name.replace("\\", "/").strip("/")
        if not name:
            continue
        if name == MANIFEST_NAME:
            candidates.append(("", name))
        elif name.endswith("/" + MANIFEST_NAME) and name.count("/") == 1:
            root, _ = name.split("/", 1)
            candidates.append((root, name))

    if len(candidates) != 1:
        raise UpdateError(
            "O ZIP precisa conter um único update.json na raiz do pacote."
        )

    return candidates[0]


def inspect_update(zip_path: str | os.PathLike[str]) -> UpdatePackage:
    """Valida o ZIP sem alterar o projeto e devolve seus metadados."""
    path = Path(zip_path).expanduser().resolve()

    if not path.is_file() or path.suffix.lower() != ".zip":
        raise UpdateError("O arquivo selecionado não é um ZIP válido.")

    try:
        with zipfile.ZipFile(path, "r") as archive:
            names = archive.namelist()
            package_root, manifest_member = _find_manifest(names)

            try:
                manifest = json.loads(
                    archive.read(manifest_member).decode("utf-8")
                )
            except (KeyError, UnicodeDecodeError, json.JSONDecodeError) as error:
                raise UpdateError("O update.json está ausente ou inválido.") from error

            listed_files = manifest.get("files")
            if not isinstance(listed_files, list) or not listed_files:
                raise UpdateError(
                    "O update.json precisa listar os arquivos em 'files'."
                )

            files = tuple(_safe_relative_path(str(item)) for item in listed_files)
            if len(set(files)) != len(files):
                raise UpdateError("O pacote possui arquivos repetidos.")

            archive_files = {
                item.replace("\\", "/").strip("/")
                for item in names
                if item and not item.endswith("/")
            }

            missing = []
            for relative in files:
                member = f"{package_root}/{relative}" if package_root else relative
                if member not in archive_files:
                    missing.append(relative)

            if missing:
                preview = ", ".join(missing[:3])
                raise UpdateError(f"Arquivos ausentes no pacote: {preview}")

            return UpdatePackage(
                zip_path=path,
                package_root=package_root,
                name=str(manifest.get("name") or "Atualização M87").strip(),
                version=str(manifest.get("version") or "").strip(),
                description=str(manifest.get("description") or "").strip(),
                files=files,
                restart=bool(manifest.get("restart", True)),
            )
    except zipfile.BadZipFile as error:
        raise UpdateError("O ZIP está corrompido ou incompleto.") from error


def _member_name(package: UpdatePackage, relative: str) -> str:
    return (
        f"{package.package_root}/{relative}"
        if package.package_root
        else relative
    )


def _create_backup(package: UpdatePackage) -> int:
    """Guarda somente os arquivos existentes que serão substituídos."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    temporary_backup = BACKUP_DIR / "ultimo_backup.tmp.zip"
    backed_up = 0

    try:
        with zipfile.ZipFile(
            temporary_backup,
            "w",
            compression=zipfile.ZIP_DEFLATED,
        ) as archive:
            for relative in package.files:
                source = PROJECT_ROOT / Path(relative)
                if source.is_file():
                    archive.write(source, arcname=relative)
                    backed_up += 1

        os.replace(temporary_backup, LAST_BACKUP)
    finally:
        if temporary_backup.exists():
            temporary_backup.unlink(missing_ok=True)

    return backed_up



def _unique_trash_destination(source: Path) -> Path:
    """Escolhe um nome livre na Lixeira sem sobrescrever outro pacote."""
    trash_dir = Path.home() / ".Trash"
    trash_dir.mkdir(parents=True, exist_ok=True)

    destination = trash_dir / source.name
    if not destination.exists():
        return destination

    stem = source.stem
    suffix = source.suffix
    index = 2

    while True:
        destination = trash_dir / f"{stem} {index}{suffix}"
        if not destination.exists():
            return destination
        index += 1


def _move_package_to_trash(zip_path: Path) -> tuple[bool, str]:
    """Move o ZIP instalado para a Lixeira do usuário."""
    try:
        if not zip_path.exists():
            return False, "O pacote original não foi encontrado."

        destination = _unique_trash_destination(zip_path)
        shutil.move(str(zip_path), str(destination))
        return True, destination.name
    except OSError as error:
        return False, str(error)

def install_update(
    package: UpdatePackage,
    progress: Callable[[str], None] | None = None,
) -> int:
    """Cria backup único, valida a extração e substitui os arquivos."""
    notify = progress or (lambda _message: None)

    notify("• Criando backup...")
    _create_backup(package)

    staging_parent = Path(
        tempfile.mkdtemp(prefix="m87_update_", dir=str(PROJECT_ROOT.parent))
    )
    staging_root = staging_parent / "conteudo"
    staging_root.mkdir(parents=True, exist_ok=True)

    try:
        notify("• Extraindo atualização...")
        with zipfile.ZipFile(package.zip_path, "r") as archive:
            for relative in package.files:
                member = _member_name(package, relative)
                target = staging_root / Path(relative)
                target.parent.mkdir(parents=True, exist_ok=True)

                with archive.open(member, "r") as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)

        for relative in package.files:
            staged = staging_root / Path(relative)
            if not staged.is_file():
                raise UpdateError(f"Falha ao extrair: {relative}")

        notify("• Substituindo arquivos...")
        installed = 0

        for relative in package.files:
            staged = staging_root / Path(relative)
            destination = PROJECT_ROOT / Path(relative)
            destination.parent.mkdir(parents=True, exist_ok=True)

            temporary_destination = destination.with_name(
                destination.name + ".m87_update_tmp"
            )
            shutil.copy2(staged, temporary_destination)
            os.replace(temporary_destination, destination)
            installed += 1
            notify(f"✓ {relative}")

        notify("• Movendo pacote para a Lixeira...")
        moved, detail = _move_package_to_trash(package.zip_path)
        if moved:
            notify("✓ Pacote movido para a Lixeira")
        else:
            notify(f"⚠ Atualização concluída, mas o ZIP não foi movido: {detail}")

        return installed
    except OSError as error:
        raise UpdateError(f"Não foi possível instalar a atualização: {error}") from error
    finally:
        shutil.rmtree(staging_parent, ignore_errors=True)
