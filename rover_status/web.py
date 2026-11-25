# SPDX-License-Identifier: MulanPSL-2.0
"""Small read-only HTTP dashboard for the rover status service."""

from __future__ import annotations

import json
import logging
import socketserver
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .core import format_line
from .dashboard import DASHBOARD_HTML

log = logging.getLogger(__name__)


class StatusHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def server_bind(self) -> None:
        socketserver.TCPServer.server_bind(self)
        host, port = self.server_address[:2]
        self.server_name = host
        self.server_port = port


def local_ips() -> list[str]:
    try:
        result = subprocess.run(
            ["hostname", "-I"], capture_output=True, text=True, timeout=2)
        return [
            item for item in result.stdout.split()
            if ":" not in item and not item.startswith("127.")
        ]
    except Exception:  # noqa: BLE001
        return []


def make_handler(provider):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            route = self.path.split("?", 1)[0].rstrip("/") or "/"
            try:
                if route in ("/", "/index.html"):
                    data = provider()
                    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
                    body = DASHBOARD_HTML.replace("__INITIAL_STATUS__", payload).encode()
                    ctype = "text/html; charset=utf-8"
                    status_code = 200
                elif route == "/status":
                    data = provider()
                    body = json.dumps(data, ensure_ascii=False, indent=2).encode()
                    ctype = "application/json; charset=utf-8"
                    status_code = 200
                elif route == "/text":
                    body = (format_line(provider()) + "\n").encode()
                    ctype = "text/plain; charset=utf-8"
                    status_code = 200
                else:
                    body = b"not found\n"
                    ctype = "text/plain; charset=utf-8"
                    status_code = 404
            except Exception as exc:  # noqa: BLE001
                log.exception("dashboard request failed")
                body = json.dumps({"error": str(exc)}).encode()
                ctype = "application/json; charset=utf-8"
                status_code = 500
            self.send_response(status_code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt: str, *args) -> None:
            pass

    return Handler
