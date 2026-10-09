"""Téléchargement HTTP(S) direct, vérifié, reprenable et sans écrasement."""

from __future__ import annotations

import hashlib
import http.client
import json
import os
import re
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path

from overload.core.errors import OverloadError
from overload.downloads.netguard import pinned_handlers
from overload.downloads.urls import ALLOWED_SCHEMES, validate_direct_url

CHUNK_SIZE = 64 * 1024
MAX_BYTES = 10 * 1024**3
USER_AGENT = "OverLoad/0.1 (+https://github.com/TOFazer/OverLoad)"
ProgressCallback = Callable[[int, int | None], None]
_RANGE = re.compile(r"bytes (\d+)-(\d+)/(\d+)\Z")


class DownloadCancelled(OverloadError):
    """Annulation demandée : le fichier partiel est supprimé."""


class DownloadPaused(OverloadError):
    """Pause demandée : le fichier partiel est conservé."""


class _ValidatingRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, allow_private_hosts: bool) -> None:
        self._allow_private = allow_private_hosts

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        if urllib.parse.urlsplit(newurl).scheme.lower() not in ALLOWED_SCHEMES:
            raise OverloadError(
                "La redirection vers une autre source a été refusée.",
                "la nouvelle adresse n'utilise pas http ou https.",
            )
        validate_direct_url(newurl, allow_private_hosts=self._allow_private)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _open(url: str, *, offset: int, validator: str | None, allow_private_hosts: bool):  # noqa: ANN202
    headers = {"User-Agent": USER_AGENT}
    if offset:
        headers["Range"] = f"bytes={offset}-"
        if validator:
            headers["If-Range"] = validator
    opener = urllib.request.build_opener(
        *pinned_handlers(allow_private_hosts),
        _ValidatingRedirectHandler(allow_private_hosts),
    )
    return opener.open(urllib.request.Request(url, headers=headers), timeout=30)


def _metadata(part: Path) -> Path:
    return part.with_name(part.name + ".json")


def _save_metadata(path: Path, data: dict) -> None:
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_text(json.dumps(data), encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _load_metadata(path: Path, url: str, offset: int) -> dict | None:
    if not offset:
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if (
            isinstance(data, dict) and data.get("url") == url
            and isinstance(data.get("validator"), str) and data["validator"]
            and (data.get("total") is None or
                 isinstance(data["total"], int) and offset <= data["total"])
        ):
            return data
    except (OSError, ValueError, AttributeError):
        pass
    return None


def _failure(exc: Exception) -> OverloadError:
    return OverloadError(
        "Connexion ou écriture impossible.",
        str(getattr(exc, "reason", exc)),
        "Vérifiez la connexion, l'espace disque et les droits, puis réessayez.",
    )


def download_to(
    url: str,
    target: Path,
    *,
    expected_size: int | None = None,
    sha256: str | None = None,
    max_bytes: int = MAX_BYTES,
    allow_private_hosts: bool = False,
    progress: ProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
    pause_event: threading.Event | None = None,
) -> Path:
    """Télécharge vers target ; les .part ne sont repris que pour la même URL et version.

    ``allow_private_hosts`` est réservé aux tests : ne jamais l'exposer à une URL non fiable.
    La taille et le hachage optionnel s'appliquent au fichier complet, pas à chaque réponse.
    """
    clean_url = validate_direct_url(url, allow_private_hosts=allow_private_hosts)
    target = Path(target)
    part = target.with_name(target.name + ".part")
    meta_path = _metadata(part)
    if not isinstance(max_bytes, int) or max_bytes <= 0:
        raise ValueError("max_bytes doit être positif")
    if expected_size is not None and (expected_size < 0 or expected_size > max_bytes):
        raise OverloadError("Taille attendue non autorisée.")
    if sha256 is not None and not re.fullmatch(r"[0-9a-fA-F]{64}", sha256):
        raise OverloadError("Empreinte SHA-256 invalide.")
    if target.exists() or target.is_symlink():
        raise OverloadError("Un fichier porte déjà ce nom.", action="Choisissez un autre nom.")
    if not target.parent.is_dir():
        raise OverloadError("Le dossier de destination est introuvable.")
    if part.is_symlink() or meta_path.is_symlink():
        raise OverloadError("Fichier partiel non fiable.", "un lien symbolique est présent.")

    offset = part.stat().st_size if part.exists() else 0
    metadata = _load_metadata(meta_path, clean_url, offset)
    # Pas de preuve que ce .part appartient à cette URL/version : ne jamais l'ajouter au fichier.
    if offset and metadata is None:
        offset = 0
    if offset > max_bytes:
        raise OverloadError("Le fichier partiel dépasse la limite de taille.")
    try:
        try:
            response = _open(
                clean_url, offset=offset,
                validator=metadata["validator"] if metadata else None,
                allow_private_hosts=allow_private_hosts,
            )
        except urllib.error.HTTPError as exc:
            if exc.code == 416 and offset:
                # Ressource modifiée ou plage non acceptée. Repartir de zéro sans concaténer.
                offset = 0
                response = _open(clean_url, offset=0, validator=None,
                                 allow_private_hosts=allow_private_hosts)
            else:
                raise
        with response:
            status = getattr(response, "status", 200)
            if offset and status != 206:
                offset = 0  # Range ignoré / If-Range non satisfait : tronquer l'ancien .part.
            if status == 206:
                match = _RANGE.fullmatch(response.headers.get("Content-Range", ""))
                if not match or int(match[1]) != offset or int(match[2]) < offset:
                    raise OverloadError(
                        "Réponse de reprise invalide.", action="Réessayez plus tard."
                    )
                range_total = int(match[3])
                if int(match[2]) >= range_total:
                    raise OverloadError("Réponse de reprise invalide.")
                if offset and metadata and metadata.get("total") not in (None, range_total):
                    raise OverloadError(
                    "Le fichier distant a changé.", action="Annulez puis recommencez."
                )
            else:
                range_total = None
            content_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
            if content_type in ("text/html", "application/xhtml+xml"):
                raise OverloadError(
                    "Cette adresse renvoie une page Web, pas un fichier direct.",
                    action="Utilisez l'URL directe du fichier, si son téléchargement est autorisé.",
                )
            length = response.headers.get("Content-Length")
            if length is not None and (not length.isdigit() or int(length) < 0):
                raise OverloadError("Taille annoncée par le serveur invalide.")
            remaining = int(length) if length is not None else None
            if status == 206 and remaining is not None and remaining != int(match[2]) - offset + 1:
                raise OverloadError("Réponse de reprise invalide.", "taille de plage incohérente.")
            total = range_total if status == 206 else remaining
            if total is not None and total > max_bytes:
                raise OverloadError("Fichier trop volumineux.", f"limite : {max_bytes} octets.")
            if expected_size is not None and total is not None and expected_size != total:
                raise OverloadError("La taille du fichier a changé.")

            validator = response.headers.get("ETag", "")
            if validator.startswith("W/"):
                validator = ""
            validator = validator or response.headers.get("Last-Modified", "")
            if status == 206 and metadata and validator and validator != metadata["validator"]:
                raise OverloadError(
                    "Le fichier distant a changé.", action="Annulez puis recommencez."
                )
            if not offset:
                _save_metadata(meta_path, {
                    "url": clean_url, "validator": validator, "total": total, "size": 0,
                })
            received = offset
            with part.open("ab" if offset else "wb") as handle:
                if progress:
                    progress(received, total or expected_size)
                while True:
                    if cancel_event is not None and cancel_event.is_set():
                        raise DownloadCancelled("Téléchargement annulé.")
                    if pause_event is not None and pause_event.is_set():
                        raise DownloadPaused("Téléchargement en pause.")
                    try:
                        chunk = response.read(CHUNK_SIZE)
                    except (OSError, http.client.HTTPException) as exc:
                        raise OverloadError(
                            "Téléchargement interrompu.",
                            "le fichier partiel est conservé pour reprise.",
                            "Relancez le téléchargement.",
                        ) from exc
                    if not chunk:
                        break
                    if received + len(chunk) > max_bytes:
                        raise OverloadError(
                            "Fichier trop volumineux.", f"limite : {max_bytes} octets."
                        )
                    handle.write(chunk)
                    received += len(chunk)
                    if progress:
                        progress(received, total or expected_size)
                handle.flush()
                os.fsync(handle.fileno())
        # Une réponse complète mais trop courte reste partielle ; une pause peut la reprendre.
        _verify(part, received, total, expected_size)
        if sha256 is not None:
            digest = hashlib.sha256()
            with part.open("rb") as handle:
                for block in iter(lambda: handle.read(CHUNK_SIZE), b""):
                    digest.update(block)
            if digest.hexdigest() != sha256.lower():
                part.unlink(missing_ok=True)
                meta_path.unlink(missing_ok=True)
                raise OverloadError(
                    "Empreinte SHA-256 différente.", action="Vérifiez la source du fichier."
                )
        if target.exists():
            raise OverloadError("Un fichier porte déjà ce nom.", action="Choisissez un autre nom.")
        # Windows : rename ne remplace pas un fichier existant (y compris sur exFAT).
        # POSIX : hardlink assure la même propriété ; puis retrait du .part.
        try:
            if sys.platform == "win32":
                os.rename(part, target)
            else:
                os.link(part, target)
                part.unlink()
        except FileExistsError as exc:
            raise OverloadError("Un fichier porte déjà ce nom.") from exc
        meta_path.unlink(missing_ok=True)
        return target
    except DownloadCancelled:
        part.unlink(missing_ok=True)
        meta_path.unlink(missing_ok=True)
        raise
    except DownloadPaused:
        if part.exists():
            _update_size(meta_path, part)
        raise
    except urllib.error.HTTPError as exc:
        raise _http_error(exc) from exc
    except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException) as exc:
        if part.exists():
            _update_size(meta_path, part)
        raise _failure(exc) from exc
    except OverloadError:
        if part.exists():
            _update_size(meta_path, part)
        raise
    finally:
        if not part.exists():
            meta_path.unlink(missing_ok=True)


def _update_size(meta_path: Path, part: Path) -> None:
    try:
        data = json.loads(meta_path.read_text(encoding="utf-8"))
        data["size"] = part.stat().st_size
        _save_metadata(meta_path, data)
    except (OSError, ValueError, AttributeError):
        pass  # sans métadonnées valides, la prochaine tentative recommence à zéro


def _http_error(exc: urllib.error.HTTPError) -> OverloadError:
    if 300 <= exc.code < 400:
        return OverloadError("La redirection a été refusée.", f"réponse HTTP {exc.code}.")
    if exc.code in (401, 403):
        return OverloadError("Accès refusé à ce fichier.", f"réponse HTTP {exc.code}.")
    if exc.code == 404:
        return OverloadError("Fichier introuvable.", "réponse HTTP 404.")
    return OverloadError("Le serveur a refusé la demande.", f"réponse HTTP {exc.code}.")


def _verify(part: Path, received: int, total: int | None, expected_size: int | None) -> None:
    actual = part.stat().st_size if part.exists() else 0
    if not actual or not received:
        part.unlink(missing_ok=True)
        raise OverloadError("Le fichier téléchargé est vide.")
    if actual != received:
        raise OverloadError("Le fichier téléchargé est incomplet.")
    for expected in (total, expected_size):
        if expected is not None and (received != expected or actual != expected):
            raise OverloadError(
                "Le fichier téléchargé est incomplet.",
                f"{received} octets reçus, {expected} attendus.",
                "Relancez le téléchargement pour reprendre.",
            )
