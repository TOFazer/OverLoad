"""Génération de vignettes pour la grille.

- Images : miniature redimensionnée via Pillow si disponible.
- Vidéos : extraction d'une frame via FFmpeg si disponible, sinon placeholder couleur.
- Audios : placeholder avec icône note de musique.
- Autres : placeholder générique.

Les vignettes sont mises en cache dans ``<data>/thumbnails/`` et régénérées
uniquement si le fichier source est plus récent.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path

from overload.library.models import MediaEntry, MediaType

THUMB_SIZE = (320, 180)  # 16:9 par défaut pour la grille
THUMB_QUALITY = 85


def thumbnail_cache_dir(data_dir: Path) -> Path:
    p = Path(data_dir) / "thumbnails"
    p.mkdir(parents=True, exist_ok=True)
    return p


def thumbnail_path_for(entry: MediaEntry, cache_dir: Path) -> Path:
    """Nom déterministe : hash du chemin + mtime -> évite les collisions et invalide au besoin."""
    key = f"{entry.path}:{entry.mtime}:{entry.size}".encode()
    name = hashlib.blake2b(key, digest_size=10).hexdigest() + ".jpg"
    return Path(cache_dir) / name


def is_thumbnail_fresh(thumb: Path, entry: MediaEntry) -> bool:
    if not thumb.exists():
        return False
    try:
        # Si le fichier source a été modifié après la vignette, refaire.
        return thumb.stat().st_mtime >= entry.mtime
    except OSError:
        return False


def generate_thumbnail(entry: MediaEntry, thumb_path: Path) -> Path | None:
    """Tente de créer la vignette, retourne le chemin ou None si impossible."""
    thumb_path.parent.mkdir(parents=True, exist_ok=True)
    if is_thumbnail_fresh(thumb_path, entry):
        return thumb_path

    try:
        if entry.media_type == MediaType.IMAGE:
            if _thumb_image(entry.path, thumb_path):
                return thumb_path
        elif entry.media_type == MediaType.VIDEO:
            if _thumb_video(entry.path, thumb_path):
                return thumb_path
        # Fallback : placeholder (audio, échec, ou autre)
        if _thumb_placeholder(entry, thumb_path):
            return thumb_path
    except Exception:
        # Ne jamais planter l'indexation pour une vignette.
        return None
    return None


def _thumb_image(source: Path, dest: Path) -> bool:
    try:
        from PIL import Image, ImageOps

        with Image.open(source) as im:
            # Corrige l'orientation EXIF
            im = ImageOps.exif_transpose(im)
            if im.mode in ("RGBA", "LA", "P"):
                # Fond blanc pour éviter transparence noire en JPEG
                bg = Image.new("RGB", im.size, "white")
                if im.mode == "P":
                    im = im.convert("RGBA")
                bg.paste(im, mask=im.split()[-1] if im.mode in ("RGBA", "LA") else None)
                im = bg
            elif im.mode != "RGB":
                im = im.convert("RGB")
            im.thumbnail(THUMB_SIZE)
            im.save(dest, "JPEG", quality=THUMB_QUALITY)
            return True
    except Exception:
        return _thumb_placeholder_image_fallback(dest)


def _thumb_video(source: Path, dest: Path) -> bool:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return False
    try:
        # Extrait une frame à 10% de la durée, ou à 1s par défaut, en 320px de large.
        result = subprocess.run(
            [
                ffmpeg,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-ss",
                "1",
                "-i",
                str(source),
                "-frames:v",
                "1",
                "-vf",
                f"scale={THUMB_SIZE[0]}:-1",
                str(dest),
            ],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0 and dest.exists()
    except Exception:
        return False


def _thumb_placeholder(entry: MediaEntry, dest: Path) -> bool:
    # Placeholder coloré selon le type
    colors = {
        MediaType.VIDEO: (37, 99, 235),  # bleu
        MediaType.AUDIO: (16, 185, 129),  # vert
        MediaType.IMAGE: (249, 115, 22),  # orange
        MediaType.OTHER: (107, 114, 128),  # gris
    }
    color = colors.get(entry.media_type, (107, 114, 128))
    return _create_color_placeholder(dest, color, entry.extension or entry.media_type.value)


def _create_color_placeholder(dest: Path, color: tuple[int, int, int], label: str) -> bool:
    try:
        from PIL import Image, ImageDraw, ImageFont

        img = Image.new("RGB", THUMB_SIZE, color)
        draw = ImageDraw.Draw(img)
        # Texte centré : extension ou type
        text = label.upper().lstrip(".")[:8]
        try:
            # Police par défaut, taille adaptée
            font = ImageFont.load_default()
        except Exception:
            font = None
        # Calcul bbox pour centrer
        bbox = draw.textbbox((0, 0), text, font=font) if hasattr(draw, "textbbox") else (0, 0, len(text) * 6, 10)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        x = (THUMB_SIZE[0] - w) // 2
        y = (THUMB_SIZE[1] - h) // 2
        draw.text((x, y), text, fill="white", font=font)
        img.save(dest, "JPEG", quality=THUMB_QUALITY)
        return True
    except Exception:
        # Sans Pillow : on ne peut pas créer d'image ; on laisse l'UI afficher une icône.
        return False


def _thumb_placeholder_image_fallback(dest: Path) -> bool:
    return _create_color_placeholder(dest, (249, 115, 22), "image")


def ensure_thumbnails(entries: list[MediaEntry], cache_dir: Path) -> dict[str, Path]:
    """Génère les vignettes manquantes pour une liste d'entrées. Retourne mapping path->thumb."""
    result: dict[str, Path] = {}
    for e in entries:
        thumb = thumbnail_path_for(e, cache_dir)
        generated = generate_thumbnail(e, thumb)
        if generated:
            e.thumbnail_path = generated
            result[str(e.path)] = generated
    return result
