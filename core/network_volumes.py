import re
import subprocess
from concurrent.futures import ThreadPoolExecutor


NETWORK_VOLUMES = (
    {
        "key": "MIM",
        "label": "MIM",
        "host": "jv100-160",
        "url": "smb://jv100-160/Pasta Mimaki",
        "mount_path": "/Volumes/Pasta Mimaki",
        "aliases": ("MIM", "MIMAKI", "JV", "JV100"),
    },
    {
        "key": "PFI",
        "label": "PFI",
        "host": "pfi",
        "url": "smb://pfi/Trabalhos PFI",
        "mount_path": "/Volumes/Trabalhos PFI",
        "aliases": ("PFI",),
    },
    {
        "key": "NAS",
        "label": "NAS",
        "host": "NAS310BDA.local",
        "url": "smb://NAS310BDA._smb._tcp.local/Trabalhos",
        "mount_path": "/Volumes/Trabalhos",
        "aliases": ("NAS", "ARQUIVOS", "TRABALHOS"),
    },
)


def select_network_volumes(target=None):
    """Devolve todas as unidades ou somente a indicada por nome/alias."""
    if not target or target.strip().upper() in {"TODAS", "TUDO", "ALL"}:
        return NETWORK_VOLUMES

    normalized = target.strip().upper()
    return tuple(
        volume
        for volume in NETWORK_VOLUMES
        if normalized == volume["key"] or normalized in volume["aliases"]
    )


def _mounted_smb_paths():
    try:
        result = subprocess.run(
            ["mount"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return set()

    return {
        match.group(1)
        for line in result.stdout.splitlines()
        if "(smbfs," in line
        for match in [re.search(r" on (.+) \(smbfs,", line)]
        if match
    }


def _mount_responds(path, timeout):
    try:
        result = subprocess.run(
            ["/usr/bin/stat", "-f", "%d", path],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def get_network_status(timeout=1.2):
    """Confirma que cada volume SMB está montado e acessível no macOS."""
    mounted_paths = _mounted_smb_paths()

    def is_available(volume):
        path = volume["mount_path"]
        if path not in mounted_paths:
            return False
        try:
            return _mount_responds(path, timeout)
        except Exception:
            return False

    with ThreadPoolExecutor(max_workers=len(NETWORK_VOLUMES)) as executor:
        results = executor.map(is_available, NETWORK_VOLUMES)

    return {
        volume["key"]: available
        for volume, available in zip(NETWORK_VOLUMES, results)
    }
