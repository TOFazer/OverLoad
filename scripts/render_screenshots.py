"""Génère les captures d'écran de référence de l'interface OverLoad.

Usage (développement) :

    python scripts/render_screenshots.py

Le script démarre un petit serveur HTTP local pour simuler deux téléchargements
en cours, remplit un historique de démonstration et enregistre les visuels dans
`docs/design/`. Aucun fichier n'est écrit hors du dossier temporaire et du
dossier `docs/design/`.
"""

from __future__ import annotations

import http.server
import os
import socketserver
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "design"
sys.path.insert(0, str(ROOT / "src"))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen" if sys.platform != "win32" else "windows")


def _make_image(path: Path, first: str, second: str, label: str) -> None:
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QColor, QFont, QImage, QLinearGradient, QPainter

    image = QImage(960, 600, QImage.Format.Format_RGB32)
    painter = QPainter(image)
    gradient = QLinearGradient(0, 0, 960, 600)
    gradient.setColorAt(0.0, QColor(first))
    gradient.setColorAt(1.0, QColor(second))
    painter.fillRect(0, 0, 960, 600, gradient)
    painter.setPen(QColor(255, 255, 255, 225))
    font = painter.font()
    font.setPixelSize(64)
    font.setWeight(QFont.Weight.Bold)
    painter.setFont(font)
    painter.drawText(QRectF(0, 0, 960, 600), 0x84, label)
    painter.end()
    image.save(str(path))


class _SlowHandler(http.server.BaseHTTPRequestHandler):
    payload = b""

    def do_GET(self) -> None:  # noqa: N802
        data = self.payload
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        for offset in range(0, len(data), 65536):
            try:
                self.wfile.write(data[offset : offset + 65536])
                self.wfile.flush()
            except OSError:
                return
            time.sleep(0.05)

    def log_message(self, *args) -> None:  # noqa: ANN002
        pass


def _build_demo(tmp: Path):
    from overload.downloads.manager import DownloadManager
    from overload.history.store import DownloadHistoryStore
    from overload.settings.store import SettingsStore

    downloads = tmp / "OverLoad"
    downloads.mkdir(parents=True, exist_ok=True)
    _make_image(downloads / "DSC_0421.jpg", "#8B5CF6", "#38BDF8", "PHOTO 0421")
    _make_image(downloads / "Moodboard ete.jpg", "#F43F5E", "#FBBF24", "MOODBOARD")
    (downloads / "Soundtrack - Nuit.wav").write_bytes(b"RIFF" + os.urandom(2_400_000))
    (downloads / "Rushes - sequence 04.mkv").write_bytes(os.urandom(120_000))
    (downloads / "archive-projet.zip").write_bytes(b"PK" + os.urandom(800_000))

    payload = tmp / "flux.bin"
    payload.write_bytes(os.urandom(48_000_000))
    _SlowHandler.payload = payload.read_bytes()
    server = socketserver.TCPServer(("127.0.0.1", 0), _SlowHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    store = SettingsStore(tmp / "settings.json")
    history = DownloadHistoryStore(tmp / "library.db")
    manager = DownloadManager(
        downloads,
        history=history,
        allow_private_hosts=True,
        max_concurrent=3,
    )
    entries = [
        ("DSC_0421.jpg", "completed", 0, ""),
        ("Moodboard ete.jpg", "completed", 0, ""),
        ("Soundtrack - Nuit.wav", "completed", 0, ""),
        ("Rushes - sequence 04.mkv", "completed", 2, ""),
        ("archive-projet.zip", "cancelled", 0, ""),
        (
            "Film documentaire 4K.mkv",
            "failed",
            3,
            "Le serveur a refusé la demande.\n"
            "Cause probable : réponse HTTP 503.\n"
            "Action : Réessayez plus tard ou vérifiez l'adresse.",
        ),
    ]
    for name, status, retries, error in entries:
        path = downloads / name
        history.record(
            task_id=f"demo-{name}",
            url=f"https://exemple.com/{name}",
            filename=name,
            destination_path=path,
            status=status,
            size_bytes=path.stat().st_size if path.is_file() else 1_240_000_000,
            average_speed_bps=4_400_000,
            duration_seconds=32,
            retries_used=retries,
            error_message=error,
        )
    port = server.server_address[1]
    from overload.downloads.duplicates import DuplicatePolicy

    manager.enqueue(
        f"http://127.0.0.1:{port}/flux.bin",
        filename="Documentaire - montage final.mkv",
        duplicate_policy=DuplicatePolicy.RENAME,
    )
    manager.enqueue(
        f"http://127.0.0.1:{port}/flux.bin?a=2",
        filename="Podcast - episode 12.mp3",
        duplicate_policy=DuplicatePolicy.RENAME,
    )
    return store, history, manager, server


def main() -> int:
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    from overload.ui.desktop import create_main_window

    OUTPUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="overload-shots-") as temp:
        tmp = Path(temp)
        store, history, manager, server = _build_demo(tmp)
        time.sleep(1.2)
        window = create_main_window(manager, history, store, data_dir=tmp)
        window.resize(1280, 860)
        window.show()
        app.processEvents()
        window.refresh_all()
        app.processEvents()

        def shot(name: str) -> None:
            # Laisse la transition d'opacité (170 ms) et la mise en page se terminer.
            deadline = time.monotonic() + 1.2
            while time.monotonic() < deadline:
                app.processEvents()
                time.sleep(0.05)
            window.grab().save(str(OUTPUT / name))
            print(f"Capture : docs/design/{name}", flush=True)

        window.go_to("home")
        shot("accueil.png")

        window.go_to("downloads")
        shot("telechargements.png")

        window.downloads_view.set_value("history", emit=True)
        shot("historique.png")

        window.set_appearance(theme="light", accent="blue")
        window.go_to("home")
        shot("theme-clair.png")

        window.set_appearance(theme="dark", accent="violet")
        window.go_to("settings")
        shot("parametres.png")

        window.go_to("creators")
        shot("createurs.png")

        # Laisse Qt terminer les extractions de miniatures avant les captures finales.
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline and window.thumbnails._pending:
            app.processEvents()
            time.sleep(0.05)
        window.go_to("home")
        shot("accueil.png")

        window.close()
        # Arrête proprement les deux transferts de démonstration : chaque worker
        # enregistre son résultat avant la fermeture de l'historique.
        for snapshot in manager.list_tasks():
            try:
                manager.cancel_task(snapshot.id)
            except Exception:  # noqa: BLE001 - capture de démonstration uniquement
                continue
        manager.wait_all(timeout=20)
        manager.shutdown()
        server.shutdown()
        server.server_close()
        history.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
