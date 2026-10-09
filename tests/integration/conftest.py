"""Serveur HTTP local de test : fichiers normaux, reprise, coupure, vide, redirection."""

from __future__ import annotations

import http.server
import re
import threading

import pytest

PAYLOAD = bytes(range(256)) * 4096  # 1 Mio, contenu reconnaissable


class _Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):  # silence
        pass

    def _send_file(
        self, data: bytes, *, truncate_at: int | None = None,
        ignore_range: bool = False, wrong_range: bool = False,
    ) -> None:
        range_header = self.headers.get("Range")
        status, start = 200, 0
        if range_header and not ignore_range:
            match = re.match(r"bytes=(\d+)-", range_header)
            if match:
                start = int(match.group(1))
                status = 206
        body = data[start:]
        self.send_response(status)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("ETag", '"fixture-v1"')
        if status == 206:
            begin = start + 1 if wrong_range else start
            self.send_header("Content-Range", f"bytes {begin}-{len(data) - 1}/{len(data)}")
        self.end_headers()
        if truncate_at is not None:
            self.wfile.write(body[:truncate_at])
            self.wfile.flush()
            self.close_connection = True
            return
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        if self.path == "/ok.bin":
            self._send_file(PAYLOAD)
        elif self.path == "/truncated.bin":
            # Annonce 1 Mio, coupe après 100 Ko.
            self._send_file(PAYLOAD, truncate_at=100 * 1024)
        elif self.path == "/no-range.bin":
            self._send_file(PAYLOAD, ignore_range=True)
        elif self.path == "/bad-range.bin":
            self._send_file(PAYLOAD, wrong_range=True)
        elif self.path == "/html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html>not a file</html>")
        elif self.path == "/empty.bin":
            self._send_file(b"")
        elif self.path == "/redirect-file":
            self.send_response(302)
            self.send_header("Location", "file:///etc/passwd")
            self.send_header("Content-Length", "0")
            self.end_headers()
        else:
            self.send_error(404)


@pytest.fixture(scope="session")
def server():
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    httpd.handle_error = lambda *args: None  # annulation et coupure prévues dans les tests
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    host, port = httpd.server_address
    yield f"http://{host}:{port}"
    httpd.shutdown()
    httpd.server_close()
