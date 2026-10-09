"""Point d'entrée : interface graphique ou téléchargement direct en ligne de commande."""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path

from overload.core.errors import OverloadError
from overload.downloads.engine import download_to
from overload.downloads.files import destination_for_url, filename_from_url
from overload.downloads.urls import validate_direct_url


def data_directory() -> Path:
    root = os.environ.get("APPDATA") if sys.platform == "win32" else None
    return (Path(root) if root else Path.home() / ".config") / "OverLoad-Dev"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="OverLoad — fichiers directs HTTP(S)")
    sub = parser.add_subparsers(dest="command")
    get = sub.add_parser("download", help="télécharger un fichier direct")
    get.add_argument("url", help="URL directe HTTP(S) du fichier")
    get.add_argument("--folder", type=Path, default=Path.home() / "Downloads")
    get.add_argument("--name", help="nom de fichier local (facultatif)")
    get.add_argument("--sha256", help="empreinte SHA-256 attendue (facultatif)")
    args = parser.parse_args(argv)
    if args.command == "download":
        try:
            url = validate_direct_url(args.url)
            folder = args.folder.expanduser().resolve()
            folder.mkdir(parents=True, exist_ok=True)
            target = destination_for_url(folder, args.name or filename_from_url(url), url)

            def show_progress(done: int, total: int | None) -> None:
                label = f"{done}/{total} octets" if total else f"{done} octets"
                print(f"\r{label}", end="", file=sys.stderr, flush=True)

            result = download_to(url, target, sha256=args.sha256, progress=show_progress)
            print(f"\nTéléchargé : {result}")
            if args.sha256 is None:
                # Pas une preuve d'authenticité : permet seulement de comparer ultérieurement.
                digest = hashlib.sha256()
                with result.open("rb") as handle:
                    for block in iter(lambda: handle.read(1024 * 1024), b""):
                        digest.update(block)
                digest = digest.hexdigest()
                print(f"SHA-256 : {digest}")
            return 0
        except (OverloadError, OSError) as exc:
            print(f"\nErreur : {exc}", file=sys.stderr)
            return 1

    try:
        from overload.ui.main import launch
    except ImportError as exc:
        print(
            "Interface indisponible : installez PySide6 (pip install -e \".[gui]\") "
            "et les bibliothèques graphiques du système.", file=sys.stderr
        )
        print(exc, file=sys.stderr)
        return 2
    return launch()


if __name__ == "__main__":
    sys.exit(main())
