#!/usr/bin/env python3
"""Servidor privado mínimo para a PWA do Planner.

Uso local/LAN:
    M87_PLANNER_WORKSPACE_KEY='uma-chave-longa' python3 scripts/planner_web_server.py

Em produção, execute atrás de HTTPS. Este módulo não expõe os dados sem a
chave enviada no cabeçalho X-M87-Workspace-Key.
"""

from __future__ import annotations

import hmac
import json
import os
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / "web" / "planner"
DATA_PATH = Path(os.environ.get("M87_PLANNER_DATA", str(ROOT / "planner-remote.json")))
WORKSPACE_KEY = os.environ.get("M87_PLANNER_WORKSPACE_KEY", "")


def read_data():
    try:
        with DATA_PATH.open(encoding="utf-8") as file:
            return json.load(file)
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "weeks": {}, "approvals": []}


def write_data(payload):
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = DATA_PATH.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
        file.flush()
        os.fsync(file.fileno())
    temporary.replace(DATA_PATH)


class PlannerHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def _authorized(self):
        supplied = self.headers.get("X-M87-Workspace-Key", "")
        return bool(WORKSPACE_KEY) and hmac.compare_digest(supplied, WORKSPACE_KEY)

    def _send_json(self, status, payload):
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self):
        if self.path.rstrip("/") == "/api/planner":
            if not self._authorized():
                self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
                return
            self._send_json(HTTPStatus.OK, read_data())
            return
        super().do_GET()

    def do_PUT(self):
        if self.path.rstrip("/") != "/api/planner":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        if not self._authorized():
            self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length))
        except (ValueError, json.JSONDecodeError):
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "invalid_json"})
            return
        if not isinstance(payload, dict) or not isinstance(payload.get("weeks"), dict):
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "invalid_planner"})
            return
        write_data(payload)
        self._send_json(HTTPStatus.OK, {"ok": True})


def main():
    if not WORKSPACE_KEY:
        raise SystemExit("Defina M87_PLANNER_WORKSPACE_KEY antes de iniciar o servidor.")
    host = os.environ.get("M87_PLANNER_HOST", "127.0.0.1")
    port = int(os.environ.get("M87_PLANNER_PORT", "8787"))
    server = ThreadingHTTPServer((host, port), PlannerHandler)
    print(f"M87 Planner disponível em http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
