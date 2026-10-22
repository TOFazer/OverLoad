"""Point d'entrée en ligne de commande et d'interface d'OverLoad."""

from __future__ import annotations

import argparse
import os
import signal
import sys
import webbrowser
from pathlib import Path

from overload.core.errors import OverloadError
from overload.core.paths import default_data_dir, default_downloads_dir
from overload.downloads.duplicates import DuplicatePolicy
from overload.downloads.manager import DownloadManager
from overload.history.store import DownloadHistoryStore
from overload.ui.desktop import is_pyside6_available, launch_desktop_app
from overload.ui.web.server import create_web_server


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="overload",
        description="OverLoad — Gestionnaire de téléchargements intelligent.",
    )
    sub = parser.add_subparsers(dest="command")

    serve_p = sub.add_parser("serve", help="Démarre l'interface Web locale d'OverLoad.")
    serve_p.add_argument("--host", default="0.0.0.0", help="Adresse d'écoute HTTP.")
    serve_p.add_argument("--port", type=int, default=8000, help="Port d'écoute HTTP.")
    serve_p.add_argument("--dest", type=Path, default=None, help="Dossier de téléchargements.")
    serve_p.add_argument(
        "--demo-lab",
        action="store_true",
        help="Active le banc d'essai intégré (médias synthétiques et coupure réseau simulée).",
    )
    serve_p.add_argument(
        "--open-browser",
        action="store_true",
        help="Ouvre automatiquement le navigateur Web local.",
    )

    dl_p = sub.add_parser("download", help="Télécharge un ou plusieurs liens en ligne de commande.")
    dl_p.add_argument(
        "urls",
        nargs="+",
        help="Vidéos YouTube publiques ou adresses directes HTTP(S) à télécharger.",
    )
    dl_p.add_argument("--dest", type=Path, default=None, help="Dossier de destination.")
    dl_p.add_argument("--max-concurrent", type=int, default=3)
    dl_p.add_argument("--speed-limit-kbps", type=int, default=0)
    dl_p.add_argument(
        "--quality",
        default="best",
        help="Qualité YouTube : best (défaut), 2160p, 1440p, 1080p, 720p, 480p, 360p.",
    )

    batch_p = sub.add_parser("batch", help="Télécharge tous les liens d'un fichier texte.")
    batch_p.add_argument("file", type=Path, help="Fichier .txt contenant une adresse par ligne.")
    batch_p.add_argument("--dest", type=Path, default=None, help="Dossier de destination.")
    batch_p.add_argument("--max-concurrent", type=int, default=3)
    batch_p.add_argument("--speed-limit-kbps", type=int, default=0)
    batch_p.add_argument(
        "--quality",
        default="best",
        help="Qualité YouTube appliquée aux liens vidéo du fichier.",
    )

    return parser


def _run_serve(args: argparse.Namespace) -> int:
    server = create_web_server(
        destination_dir=args.dest,
        host=args.host,
        port=args.port,
        demo_lab=args.demo_lab,
    )
    stop_called = False

    def handle_signal(*_a: object) -> None:
        nonlocal stop_called
        if stop_called:
            return
        stop_called = True
        server.manager.shutdown()
        server.history.close()
        server.shutdown()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    print(f"OverLoad est démarré sur {server.url}", flush=True)
    if args.open_browser:
        webbrowser.open(server.url)
    try:
        server.serve_forever()
    finally:
        handle_signal()
    return 0


def _run_cli_batch(
    urls_source: str | list[str],
    *,
    dest: Path | None,
    max_concurrent: int,
    speed_limit_kbps: int,
    quality: str = "best",
) -> int:
    folder = dest or default_downloads_dir()
    limit_bps = speed_limit_kbps * 1024 if speed_limit_kbps > 0 else None
    with (
        DownloadHistoryStore(default_data_dir() / "library.db") as history,
        DownloadManager(
            folder,
            history=history,
            max_concurrent=max_concurrent,
            speed_limit_bps=limit_bps,
            duplicate_policy=DuplicatePolicy.SKIP,
        ) as manager,
    ):
        res = manager.enqueue_batch(urls_source, quality=quality)
        print(
            f"{len(res.added)} ajouté(s), {len(res.skipped_duplicates)} doublon(s) ignoré(s), "
            f"{len(res.rejected)} rejeté(s).",
            flush=True,
        )
        manager.wait_all(timeout=3600)
        overview = manager.status_overview()
        print(
            f"Terminés : {overview['counts']['completed']} · "
            f"Échecs : {overview['counts']['failed']}",
            flush=True,
        )
        return 1 if overview["counts"]["failed"] > 0 else 0


def main(argv: list[str] | None = None) -> int:
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115

    raw_args = list(sys.argv[1:] if argv is None else argv)
    if "--self-test" in raw_args:
        from overload.exe_entry import main as exe_main

        return exe_main(raw_args)

    parser = _build_parser()
    args = parser.parse_args(raw_args)
    try:
        if args.command == "serve":
            return _run_serve(args)
        if args.command == "download":
            return _run_cli_batch(
                args.urls,
                dest=args.dest,
                max_concurrent=args.max_concurrent,
                speed_limit_kbps=args.speed_limit_kbps,
                quality=args.quality,
            )
        if args.command == "batch":
            if not args.file.is_file():
                raise OverloadError(
                    "Fichier de liens introuvable.",
                    f"le chemin « {args.file} » n'existe pas.",
                )
            text = args.file.read_text(encoding="utf-8", errors="ignore")
            return _run_cli_batch(
                text,
                dest=args.dest,
                max_concurrent=args.max_concurrent,
                speed_limit_kbps=args.speed_limit_kbps,
                quality=args.quality,
            )

        has_display = bool(
            os.name == "nt" or os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
        )
        if has_display and is_pyside6_available():
            return launch_desktop_app()

        ns = argparse.Namespace(
            host="127.0.0.1",
            port=8000,
            dest=None,
            demo_lab=False,
            open_browser=has_display,
        )
        return _run_serve(ns)
    except OverloadError as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
