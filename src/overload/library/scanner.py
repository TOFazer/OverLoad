"""Indexation des fichiers : scan, empreintes et métadonnées."""

from __future__ import annotations

import hashlib
import time
from pathlib import Path

from overload.library.models import MediaEntry, media_type_from_path

# Extensions à indexer par défaut — on ignore les .part etc.
IGNORED_SUFFIXES = frozenset({".part", ".tmp", ".crdownload", ".opdownload", ".!ut"})
IGNORED_NAMES = frozenset({"Thumbs.db", "desktop.ini", ".DS_Store"})


def _should_index(path: Path) -> bool:
    if path.name in IGNORED_NAMES:
        return False
    if path.suffix.lower() in IGNORED_SUFFIXES:
        return False
    return path.is_file()


def file_hash(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """SHA-256 complet du fichier (lecture par morceaux, sans charger en RAM)."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def file_hash_partial(path: Path, limit: int = 1024 * 1024) -> str:
    """Hash rapide des premiers ``limit`` octets — pour pré-trier les doublons."""
    h = hashlib.blake2b(digest_size=16)
    with path.open("rb") as f:
        data = f.read(limit)
        h.update(data)
    # On inclut la taille pour éviter les collisions entre fichiers de tailles différentes
    # mais avec même début (ex: vidéos tronquées).
    size = path.stat().st_size
    h.update(str(size).encode())
    return h.hexdigest()


def probe_duration(path: Path) -> float | None:
    """Tente de lire la durée via ffprobe si disponible, sinon None.

    Ne jamais échouer : la bibliothèque fonctionne sans FFmpeg.
    """
    import json
    import shutil
    import subprocess

    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    try:
        result = subprocess.run(
            [ffprobe, "-v", "quiet", "-print_format", "json", "-show_streams", "-show_format", str(path)],
            capture_output=True,
            timeout=5,
            text=True,
        )
        if result.returncode != 0:
            return None
        data = json.loads(result.stdout or "{}")
        # format.duration est la plus fiable
        fmt = data.get("format", {})
        if "duration" in fmt:
            try:
                return float(fmt["duration"])
            except (ValueError, TypeError):
                pass
        for stream in data.get("streams", []):
            if "duration" in stream:
                try:
                    return float(stream["duration"])
                except (ValueError, TypeError):
                    continue
    except Exception:
        return None
    return None


def probe_image_size(path: Path) -> tuple[int, int] | None:
    """Taille image via Pillow si dispo, sinon None."""
    try:
        from PIL import Image

        with Image.open(path) as im:
            return im.size  # (width, height)
    except Exception:
        return None


def scan_file(path: Path, *, compute_hash: bool = False, source_url: str | None = None) -> MediaEntry | None:
    """Construit une MediaEntry à partir d'un fichier sur disque, ou None si ignoré."""
    path = Path(path)
    if not _should_index(path):
        return None
    try:
        stat = path.stat()
    except OSError:
        return None

    media_type = media_type_from_path(path)
    duration: float | None = None
    width: int | None = None
    height: int | None = None

    if media_type.value in ("video", "audio"):
        duration = probe_duration(path)
    if media_type.value == "image":
        size_tuple = probe_image_size(path)
        if size_tuple:
            width, height = size_tuple

    entry = MediaEntry(
        path=path.resolve(),
        filename=path.name,
        media_type=media_type,
        extension=path.suffix.lower(),
        size=stat.st_size,
        mtime=stat.st_mtime,
        ctime=getattr(stat, "st_ctime", None),
        duration=duration,
        width=width,
        height=height,
        source_url=source_url,
        created_at=time.time(),
    )

    if compute_hash:
        try:
            entry.hash = file_hash(path)
            entry.hash_partial = file_hash_partial(path)
        except OSError:
            pass
    else:
        # hash partiel rapide pour pré-détection doublons sans lire tout le fichier
        try:
            entry.hash_partial = file_hash_partial(path)
        except OSError:
            pass

    return entry


def scan_directory(
    root: Path,
    *,
    recursive: bool = True,
    compute_hash: bool = False,
    follow_symlinks: bool = False,
) -> list[MediaEntry]:
    """Scanne un dossier et retourne toutes les entrées indexables."""
    root = Path(root)
    if not root.is_dir():
        return []

    pattern = "**/*" if recursive else "*"
    entries: list[MediaEntry] = []
    for p in root.glob(pattern):
        if p.is_symlink() and not follow_symlinks:
            continue
        if p.is_file():
            entry = scan_file(p, compute_hash=compute_hash)
            if entry:
                entries.append(entry)
    return entries


def index_directory(
    root: Path,
    store,
    *,
    recursive: bool = True,
    compute_hash: bool = False,
) -> int:
    """Scanne ``root`` et upsert dans ``store``. Retourne le nombre d'entrées ajoutées/mises à jour."""
    entries = scan_directory(root, recursive=recursive, compute_hash=compute_hash)
    for e in entries:
        store.upsert_entry(e)
    return len(entries)
