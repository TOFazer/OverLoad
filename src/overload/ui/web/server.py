"""Serveur HTTP local sans dépendance externe pour l'interface OverLoad.

Conforme à l'architecture cible : ce module ne contient aucune logique métier
de téléchargement ; il expose simplement `DownloadManager` et `DownloadHistoryStore`
à l'interface graphique via des routes JSON relatives (`/api/...`).
"""

from __future__ import annotations

import http.server
import json
import mimetypes
import os
import re
import threading
import time
import urllib.parse
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from overload.core.errors import OverloadError
from overload.core.formatting import format_bytes
from overload.core.paths import open_folder
from overload.downloads.duplicates import DuplicateDetectedError, DuplicatePolicy
from overload.downloads.files import PART_SUFFIX, is_inside, sanitize_filename
from overload.downloads.manager import DownloadManager
from overload.history.store import DownloadHistoryStore

STATIC_DIR = Path(__file__).parent / "static"


class DemoMediaServer:
    """Serveur de fichiers synthétiques de démonstration avec HTTP Range et coupures simulées."""

    CATALOG: dict[str, tuple[int, float]] = {
        "documentaire-nature-1080p.mp4": (4 * 1024 * 1024, 1.35 * 1024 * 1024),
        "podcast-episode-42.mp3": (2_600_000, 1.10 * 1024 * 1024),
        "rushs-montage-camera-a.mov": (6 * 1024 * 1024, 1.60 * 1024 * 1024),
        "archive-ressources-studio.zip": (3_200_000, 1.25 * 1024 * 1024),
        "conference-keynote-hd.mp4": (3_600_000, 1.20 * 1024 * 1024),
    }

    def __init__(self, host: str = "127.0.0.1", port: int = 0) -> None:
        self._flaky_attempts: dict[str, int] = {}
        self._lock = threading.Lock()
        parent = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args: object) -> None:
                pass

            def do_GET(self) -> None:  # noqa: N802
                parsed = urllib.parse.urlsplit(self.path)
                parts = [p for p in parsed.path.split("/") if p]
                if len(parts) < 2:
                    self.send_error(404)
                    return
                mode, raw_name = parts[0], parts[-1]
                spec = parent.CATALOG.get(raw_name)
                if spec is None or mode not in {"media", "flaky"}:
                    self.send_error(404)
                    return

                total_size, pace_bps = spec
                start = 0
                status = 200
                range_header = self.headers.get("Range")
                if range_header:
                    match = re.match(r"bytes=(\d+)-", range_header)
                    if match:
                        start = min(int(match.group(1)), total_size)
                        status = 206

                remaining = max(0, total_size - start)
                cut_after: int | None = None
                if mode == "flaky":
                    key = f"{raw_name}:{parsed.query}"
                    with parent._lock:
                        attempt = parent._flaky_attempts.get(key, 0) + 1
                        parent._flaky_attempts[key] = attempt
                    if attempt == 1:
                        cut_after = int(total_size * 0.42)

                self.send_response(status)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(remaining))
                self.send_header("Accept-Ranges", "bytes")
                self.end_headers()

                block = 32 * 1024
                pattern = (bytes(range(256)) * 128)[:block]
                sent = 0
                target_bytes = cut_after if cut_after is not None else remaining
                try:
                    while sent < target_bytes:
                        chunk_len = min(block, target_bytes - sent)
                        self.wfile.write(pattern[:chunk_len])
                        self.wfile.flush()
                        sent += chunk_len
                        time.sleep(chunk_len / pace_bps)
                except OSError:
                    return
                if cut_after is not None:
                    self.close_connection = True

        self._httpd = http.server.ThreadingHTTPServer((host, port), Handler)
        self._thread = threading.Thread(
            target=self._httpd.serve_forever,
            name="overload-demo-media",
            daemon=True,
        )
        self._thread.start()

    @property
    def endpoint(self) -> tuple[str, int]:
        host, port = self._httpd.server_address[:2]
        return (str(host), int(port))

    @property
    def base_url(self) -> str:
        host, port = self.endpoint
        return f"http://{host}:{port}"

    def presets(self) -> dict[str, Any]:
        base = self.base_url
        nonce = int(time.time() * 1000) % 100_000
        return {
            "enabled": True,
            "single_url": f"{base}/media/documentaire-nature-1080p.mp4",
            "flaky_url": f"{base}/flaky/conference-keynote-hd.mp4?run={nonce}",
            "batch_urls": [
                f"{base}/media/documentaire-nature-1080p.mp4",
                f"{base}/media/podcast-episode-42.mp3",
                f"{base}/media/rushs-montage-camera-a.mov",
                f"{base}/media/archive-ressources-studio.zip",
            ],
        }

    def close(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()


class OverloadWebServer:
    """Serveur HTTP local exposant l'application Web OverLoad et son API REST."""

    def __init__(
        self,
        manager: DownloadManager,
        history: DownloadHistoryStore,
        *,
        host: str = "0.0.0.0",
        port: int = 8000,
        demo_server: DemoMediaServer | None = None,
        enable_os_open: bool = True,
    ) -> None:
        self.manager = manager
        self.history = history
        self.demo_server = demo_server
        self.enable_os_open = enable_os_open
        self._httpd = http.server.ThreadingHTTPServer((host, port), self._make_handler())

    @property
    def server_address(self) -> tuple[str, int]:
        addr = self._httpd.server_address
        return (str(addr[0]), int(addr[1]))

    @property
    def url(self) -> str:
        host, port = self.server_address
        display_host = "127.0.0.1" if host == "0.0.0.0" else host
        return f"http://{display_host}:{port}"

    def serve_forever(self) -> None:
        self._httpd.serve_forever()

    def start_background(self) -> threading.Thread:
        thread = threading.Thread(
            target=self._httpd.serve_forever,
            name="overload-web-ui",
            daemon=True,
        )
        thread.start()
        return thread

    def shutdown(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()
        if self.demo_server is not None:
            self.demo_server.close()

    def _inspect_directory(self, folder: Path, highlight: Path | None = None) -> dict[str, Any]:
        entries: list[dict[str, Any]] = []
        if folder.is_dir():
            for child in sorted(folder.iterdir(), key=lambda p: p.name.lower()):
                try:
                    stat = child.stat()
                except OSError:
                    continue
                is_part = child.name.endswith(PART_SUFFIX)
                entries.append(
                    {
                        "name": child.name,
                        "path": str(child),
                        "is_dir": child.is_dir(),
                        "is_part": is_part,
                        "size_bytes": stat.st_size,
                        "size_human": format_bytes(stat.st_size),
                        "modified_at": datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(),
                        "highlighted": (
                            highlight is not None and child.resolve() == highlight.resolve()
                        ),
                        "download_url": (
                            f"/api/files/{urllib.parse.quote(child.name)}"
                            if child.is_file() and not is_part
                            else None
                        ),
                    }
                )
        return {
            "folder": str(folder),
            "highlighted_name": highlight.name if highlight is not None else None,
            "entries": entries,
        }

    def _make_handler(self):  # noqa: ANN202
        app = self

        class RequestHandler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args: object) -> None:
                pass

            def _send_json(self, status: int, payload: Any) -> None:
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def _read_json(self) -> dict[str, Any]:
                length = int(self.headers.get("Content-Length", "0") or 0)
                if length <= 0:
                    return {}
                raw = self.rfile.read(min(length, 2 * 1024 * 1024))
                try:
                    data = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise OverloadError("Requête JSON invalide.", str(exc)) from exc
                return data if isinstance(data, dict) else {}

            def _serve_static(self, rel_path: str) -> None:
                clean = rel_path.lstrip("/") or "index.html"
                candidate = (STATIC_DIR / clean).resolve()
                if not is_inside(STATIC_DIR, candidate) or not candidate.is_file():
                    self.send_error(404)
                    return
                content = candidate.read_bytes()
                mime, _ = mimetypes.guess_type(candidate.name)
                content_type = mime or "application/octet-stream"
                if content_type.startswith(("text/", "application/javascript")):
                    content_type += "; charset=utf-8"
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(content)))
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                self.wfile.write(content)

            def _serve_downloaded_file(self, encoded_name: str) -> None:
                dest_dir = app.manager.settings().destination_dir
                safe_name = sanitize_filename(urllib.parse.unquote(encoded_name))
                candidate = (dest_dir / safe_name).resolve()
                if not is_inside(dest_dir, candidate) or not candidate.is_file():
                    self._send_json(404, {"error": "Fichier introuvable dans le dossier."})
                    return
                size = candidate.stat().st_size
                mime, _ = mimetypes.guess_type(candidate.name)
                self.send_response(200)
                self.send_header("Content-Type", mime or "application/octet-stream")
                self.send_header("Content-Length", str(size))
                disp = urllib.parse.quote(candidate.name)
                self.send_header(
                    "Content-Disposition",
                    f"attachment; filename*=UTF-8''{disp}",
                )
                self.end_headers()
                with candidate.open("rb") as fh:
                    while chunk := fh.read(64 * 1024):
                        self.wfile.write(chunk)

            def do_GET(self) -> None:  # noqa: N802
                parsed = urllib.parse.urlsplit(self.path)
                path = parsed.path
                query = urllib.parse.parse_qs(parsed.query)

                try:
                    if path == "/api/state":
                        state = app.manager.status_overview()
                        state["history"] = [
                            e.to_dict() for e in app.history.list_entries(limit=100)
                        ]
                        state["demo"] = (
                            app.demo_server.presets()
                            if app.demo_server is not None
                            else {"enabled": False}
                        )
                        self._send_json(200, state)
                        return

                    if path == "/api/history":
                        status_filter = (query.get("status") or [None])[0]
                        q = (query.get("q") or [None])[0]
                        items = [
                            e.to_dict()
                            for e in app.history.list_entries(status=status_filter, query=q)
                        ]
                        self._send_json(200, {"items": items})
                        return

                    if path.startswith("/api/files/"):
                        self._serve_downloaded_file(path.removeprefix("/api/files/"))
                        return

                    if path.startswith("/api/"):
                        self._send_json(404, {"error": "Route API inconnue."})
                        return

                    self._serve_static(path)
                except OverloadError as exc:
                    self._send_json(
                        400,
                        {"error": exc.what, "cause": exc.cause, "action": exc.action},
                    )

            def do_POST(self) -> None:  # noqa: N802
                path = urllib.parse.urlsplit(self.path).path
                try:
                    body = self._read_json()

                    if path == "/api/downloads":
                        snap = app.manager.enqueue(
                            str(body.get("url", "")),
                            filename=body.get("filename") or None,
                            duplicate_policy=body.get("duplicate_policy") or None,
                            start_paused=bool(body.get("start_paused", False)),
                        )
                        self._send_json(
                            201 if snap is not None else 200,
                            {
                                "skipped": snap is None,
                                "task": snap.to_dict() if snap is not None else None,
                            },
                        )
                        return

                    if path == "/api/downloads/inspect":
                        text = body.get("text", "")
                        result = app.manager.inspect_batch(str(text))
                        self._send_json(200, result)
                        return

                    if path == "/api/downloads/batch":
                        result = app.manager.enqueue_batch(
                            str(body.get("text", "")),
                            duplicate_policy=body.get("duplicate_policy") or None,
                            start_paused=bool(body.get("start_paused", False)),
                        )
                        self._send_json(200, result.to_dict())
                        return

                    if path == "/api/downloads/pause-all":
                        items = [t.to_dict() for t in app.manager.pause_all()]
                        self._send_json(200, {"tasks": items})
                        return

                    if path == "/api/downloads/resume-all":
                        items = [t.to_dict() for t in app.manager.resume_all()]
                        self._send_json(200, {"tasks": items})
                        return

                    if path == "/api/downloads/clear-finished":
                        removed = app.manager.clear_finished()
                        self._send_json(200, {"removed": removed})
                        return

                    task_match = re.match(
                        r"^/api/downloads/([a-zA-Z0-9_-]+)/(pause|resume|retry|cancel|remove)$",
                        path,
                    )
                    if task_match:
                        task_id, action = task_match.groups()
                        if action == "pause":
                            snap = app.manager.pause_task(task_id)
                            self._send_json(200, {"task": snap.to_dict()})
                        elif action == "resume":
                            snap = app.manager.resume_task(task_id)
                            self._send_json(200, {"task": snap.to_dict()})
                        elif action == "retry":
                            snap = app.manager.retry_task(task_id)
                            self._send_json(200, {"task": snap.to_dict()})
                        elif action == "cancel":
                            snap = app.manager.cancel_task(task_id)
                            self._send_json(200, {"task": snap.to_dict()})
                        elif action == "remove":
                            app.manager.remove_task(task_id)
                            self._send_json(200, {"removed": True})
                        return

                    if path == "/api/settings":
                        if "max_concurrent" in body:
                            app.manager.set_max_concurrent(int(body["max_concurrent"]))
                        if "speed_limit_bps" in body:
                            raw_limit = body["speed_limit_bps"]
                            limit = int(raw_limit) if raw_limit not in (None, "", 0, "0") else None
                            app.manager.set_speed_limit_bps(limit)
                        if "auto_retry" in body or "max_retries" in body:
                            current = app.manager.settings()
                            app.manager.set_auto_retry(
                                bool(body.get("auto_retry", current.auto_retry)),
                                max_retries=(
                                    int(body["max_retries"])
                                    if "max_retries" in body
                                    else current.max_retries
                                ),
                            )
                        if "duplicate_policy" in body:
                            app.manager.set_duplicate_policy(str(body["duplicate_policy"]))
                        if "destination_dir" in body and str(body["destination_dir"]).strip():
                            app.manager.set_destination_dir(str(body["destination_dir"]).strip())
                        self._send_json(200, {"settings": app.manager.settings().to_dict()})
                        return

                    if path == "/api/open-folder":
                        target_highlight: Path | None = None
                        if body.get("task_id"):
                            snap = app.manager.get_task(str(body["task_id"]))
                            target_highlight = (
                                snap.target_path if snap.target_path.exists() else None
                            )
                            target_arg = snap.target_path
                        elif body.get("history_id"):
                            entry = app.history.get_entry(str(body["history_id"]))
                            ep = Path(entry.destination_path)
                            target_highlight = ep if ep.exists() else None
                            target_arg = ep
                        elif body.get("path"):
                            p = Path(str(body["path"]))
                            target_highlight = p if p.is_file() else None
                            target_arg = p
                        else:
                            target_arg = app.manager.settings().destination_dir

                        opened_native = False
                        has_display = bool(
                            os.name == "nt"
                            or os.environ.get("DISPLAY")
                            or os.environ.get("WAYLAND_DISPLAY")
                        )
                        if app.enable_os_open and has_display:
                            folder = open_folder(target_arg)
                            opened_native = True
                        else:
                            folder = open_folder(target_arg, opener=lambda *_a, **_kw: None)

                        listing = app._inspect_directory(folder, highlight=target_highlight)
                        listing["opened_native"] = opened_native
                        self._send_json(200, listing)
                        return

                    self._send_json(404, {"error": "Route API inconnue."})
                except DuplicateDetectedError as dup_exc:
                    self._send_json(
                        409,
                        {
                            "conflict": True,
                            "error": dup_exc.what,
                            "cause": dup_exc.cause,
                            "action": dup_exc.action,
                            "duplicate": dup_exc.match.to_dict(),
                        },
                    )
                except OverloadError as exc:
                    self._send_json(
                        400,
                        {"error": exc.what, "cause": exc.cause, "action": exc.action},
                    )

            def do_DELETE(self) -> None:  # noqa: N802
                path = urllib.parse.urlsplit(self.path).path
                try:
                    if path == "/api/history":
                        removed = app.history.clear()
                        self._send_json(200, {"removed": removed})
                        return
                    entry_match = re.match(r"^/api/history/([a-zA-Z0-9_-]+)$", path)
                    if entry_match:
                        ok = app.history.remove_entry(entry_match.group(1))
                        self._send_json(200, {"removed": ok})
                        return
                    self._send_json(404, {"error": "Route API inconnue."})
                except OverloadError as exc:
                    self._send_json(
                        400,
                        {"error": exc.what, "cause": exc.cause, "action": exc.action},
                    )

        return RequestHandler


def create_web_server(
    *,
    destination_dir: Path | None = None,
    db_path: Path | None = None,
    host: str = "0.0.0.0",
    port: int = 8000,
    demo_lab: bool = False,
    max_concurrent: int = 3,
    duplicate_policy: DuplicatePolicy = DuplicatePolicy.ASK,
) -> OverloadWebServer:
    """Fabrique un serveur Web OverLoad prêt à l'emploi."""
    from overload.core.paths import default_data_dir, default_downloads_dir

    downloads_folder = destination_dir or default_downloads_dir()
    history_db = db_path or (default_data_dir() / "library.db")
    history = DownloadHistoryStore(history_db)
    demo = DemoMediaServer() if demo_lab else None
    allowed_endpoints = (demo.endpoint,) if demo is not None else ()
    manager = DownloadManager(
        downloads_folder,
        history=history,
        max_concurrent=max_concurrent,
        duplicate_policy=duplicate_policy,
        allowed_local_endpoints=allowed_endpoints,
    )
    return OverloadWebServer(
        manager,
        history,
        host=host,
        port=port,
        demo_server=demo,
    )
