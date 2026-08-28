#!/usr/bin/env python3
"""Envia uma cópia do Planner local para a API privada publicada no Cloudflare."""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.export_planner_to_web import export_data


def upload(endpoint, payload, pairing_key):
    request = Request(
        endpoint.rstrip("/") + "/api/planner",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="PUT",
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "X-M87-Workspace-Key": pairing_key,
            "User-Agent": "M87-Planner-Importer/1.0",
        },
    )
    with urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", required=True, help="URL pública, sem /api/planner")
    parser.add_argument("--storage-dir", type=Path)
    args = parser.parse_args()

    pairing_key = getpass.getpass("Chave de pareamento do Cloudflare: ").strip()
    if not pairing_key:
        raise SystemExit("A chave de pareamento é obrigatória.")
    try:
        result = upload(args.endpoint, export_data(args.storage_dir), pairing_key)
    except HTTPError as error:
        if error.code == 401:
            raise SystemExit("Chave de pareamento inválida.") from error
        raise SystemExit(f"Servidor respondeu {error.code}: {error.read().decode('utf-8', 'replace')}") from error
    except URLError as error:
        raise SystemExit(f"Não foi possível conectar: {error.reason}") from error
    if not result.get("ok"):
        raise SystemExit("O servidor não confirmou a importação.")
    print("Planner enviado com sucesso para a base compartilhada.")


if __name__ == "__main__":
    main()
