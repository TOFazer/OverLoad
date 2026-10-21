from __future__ import annotations

import http.server
import re
import threading
import time

import pytest

from overload.downloads.duplicates import DuplicateDetectedError, DuplicatePolicy
from overload.downloads.manager import DownloadManager
from overload.downloads.state import TaskState
from overload.history.store import DownloadHistoryStore
from tests.integration.conftest import PAYLOAD


@pytest.fixture
def smart_server():
    """Serveur HTTP local instrumenté : simultanéité mesurée, flux lents et pannes simulées."""
    stats = {
        "active": 0,
        "peak": 0,
        "flaky_hits": 0,
        "range_headers": [],
    }
    lock = threading.Lock()

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args: object) -> None:
            pass

        def do_GET(self) -> None:  # noqa: N802
            with lock:
                stats["active"] += 1
                stats["peak"] = max(stats["peak"], stats["active"])
            try:
                range_hdr = self.headers.get("Range")
                start = 0
                status = 200
                if range_hdr:
                    with lock:
                        stats["range_headers"].append(range_hdr)
                    match = re.match(r"bytes=(\d+)-", range_hdr)
                    if match:
                        start = int(match.group(1))
                        status = 206

                if self.path.startswith("/slow/"):
                    body = PAYLOAD[start:]
                    self.send_response(status)
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Accept-Ranges", "bytes")
                    self.end_headers()
                    step = 32 * 1024
                    for offset in range(0, len(body), step):
                        try:
                            self.wfile.write(body[offset : offset + step])
                            self.wfile.flush()
                        except OSError:
                            return
                        time.sleep(0.015)
                    return

                if self.path == "/flaky.bin":
                    with lock:
                        stats["flaky_hits"] += 1
                        attempt = stats["flaky_hits"]
                    body = PAYLOAD[start:]
                    self.send_response(status)
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Accept-Ranges", "bytes")
                    self.end_headers()
                    if attempt <= 2:
                        # Coupe volontairement la connexion après 128 Ko sur les 2 premiers essais
                        self.wfile.write(body[: 128 * 1024])
                        self.wfile.flush()
                        self.close_connection = True
                        return
                    self.wfile.write(body)
                    return

                if self.path.startswith("/fast/"):
                    body = PAYLOAD[start:]
                    self.send_response(status)
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Accept-Ranges", "bytes")
                    self.end_headers()
                    self.wfile.write(body)
                    return

                self.send_error(404)
            finally:
                with lock:
                    stats["active"] -= 1

    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    host, port = httpd.server_address
    yield f"http://{host}:{port}", stats
    httpd.shutdown()
    httpd.server_close()


def test_respects_configurable_concurrency_limit(smart_server, tmp_path):
    base_url, stats = smart_server
    with DownloadManager(
        tmp_path,
        max_concurrent=2,
        allow_private_hosts=True,
    ) as manager:
        for i in range(5):
            manager.enqueue(f"{base_url}/slow/media-{i}.bin")
        assert manager.wait_all(timeout=20)
        assert manager.peak_concurrent <= 2
        assert stats["peak"] <= 2
        assert all(t.state is TaskState.COMPLETED for t in manager.list_tasks())


def test_pause_and_resume_preserves_partial_bytes_via_http_range(smart_server, tmp_path):
    base_url, stats = smart_server
    with DownloadManager(tmp_path, max_concurrent=1, allow_private_hosts=True) as manager:
        snap = manager.enqueue(f"{base_url}/slow/film.bin")
        assert snap is not None

        # Attend qu'au moins un premier bloc soit écrit dans .part
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            cur = manager.get_task(snap.id)
            if cur.downloaded_bytes >= 64 * 1024:
                break
            time.sleep(0.02)

        manager.pause_task(snap.id)
        deadline = time.monotonic() + 5.0
        while (
            time.monotonic() < deadline
            and manager.get_task(snap.id).state is not TaskState.PAUSED
        ):
            time.sleep(0.02)

        paused = manager.get_task(snap.id)
        assert paused.state is TaskState.PAUSED
        assert paused.part_exists is True
        saved_before_resume = paused.downloaded_bytes
        assert 0 < saved_before_resume < len(PAYLOAD)

        manager.resume_task(snap.id)
        assert manager.wait_all(timeout=15)

        done = manager.get_task(snap.id)
        assert done.state is TaskState.COMPLETED
        assert (tmp_path / "film.bin").read_bytes() == PAYLOAD
        assert any(h.startswith("bytes=") for h in stats["range_headers"])


def test_automatic_retry_and_resume_after_network_drops(smart_server, tmp_path):
    base_url, stats = smart_server
    with (
        DownloadHistoryStore(tmp_path / "library.db") as history,
        DownloadManager(
            tmp_path,
            history=history,
            auto_retry=True,
            max_retries=3,
            retry_initial_delay=0.06,
            allow_private_hosts=True,
        ) as manager,
    ):
        snap = manager.enqueue(f"{base_url}/flaky.bin")
        assert snap is not None
        assert manager.wait_all(timeout=15)

        final = manager.get_task(snap.id)
        assert final.state is TaskState.COMPLETED
        assert final.retry_count == 2
        assert len(final.issues) >= 2
        assert (tmp_path / "flaky.bin").read_bytes() == PAYLOAD
        assert stats["flaky_hits"] == 3

        entries = history.list_entries()
        assert len(entries) == 1
        assert entries[0].retries_used == 2


def test_permanent_404_error_does_not_waste_retries(smart_server, tmp_path):
    base_url, _ = smart_server
    with DownloadManager(
        tmp_path,
        auto_retry=True,
        max_retries=4,
        retry_initial_delay=0.05,
        allow_private_hosts=True,
    ) as manager:
        snap = manager.enqueue(f"{base_url}/introuvable.bin")
        assert snap is not None
        assert manager.wait_all(timeout=10)

        failed = manager.get_task(snap.id)
        assert failed.state is TaskState.FAILED
        assert failed.retry_count == 0
        assert "introuvable" in failed.error_message.lower()


def test_duplicate_detection_policies_and_batch_submission(smart_server, tmp_path):
    base_url, _ = smart_server
    with (
        DownloadHistoryStore(tmp_path / "library.db") as history,
        DownloadManager(
            tmp_path,
            history=history,
            duplicate_policy=DuplicatePolicy.ASK,
            allow_private_hosts=True,
        ) as manager,
    ):
        first = manager.enqueue(f"{base_url}/fast/doc.bin")
        assert first is not None
        assert manager.wait_all(timeout=10)

        # En mode ASK : signale le fichier déjà présent
        with pytest.raises(DuplicateDetectedError) as dup_info:
            manager.enqueue(f"{base_url}/fast/doc.bin")
        assert dup_info.value.match.filename == "doc.bin"

        # En mode SKIP : ignore proprement
        assert (
            manager.enqueue(f"{base_url}/fast/doc.bin", duplicate_policy=DuplicatePolicy.SKIP)
            is None
        )

        # En mode RENAME : télécharge une copie numérotée « doc (2).bin »
        copy_snap = manager.enqueue(
            f"{base_url}/fast/doc.bin", duplicate_policy=DuplicatePolicy.RENAME
        )
        assert copy_snap is not None
        assert copy_snap.filename == "doc (2).bin"
        assert manager.wait_all(timeout=10)
        assert (tmp_path / "doc (2).bin").read_bytes() == PAYLOAD

        # Lot mixte : 2 nouveaux valides + 1 doublon + 1 URL invalide + commentaire
        batch_text = f"""
        # Lot mixte
        {base_url}/fast/lot-a.bin
        {base_url}/fast/doc.bin
        ftp://example.com/non-supporte.bin
        {base_url}/fast/lot-b.bin
        """
        batch = manager.enqueue_batch(batch_text, duplicate_policy=DuplicatePolicy.SKIP)
        assert len(batch.added) == 2
        assert len(batch.skipped_duplicates) == 1
        assert len(batch.rejected) == 1
        assert manager.wait_all(timeout=10)
        assert (tmp_path / "lot-a.bin").is_file()
        assert (tmp_path / "lot-b.bin").is_file()
