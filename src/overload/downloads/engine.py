"""Moteur de téléchargement HTTP(S) direct.

Garanties :
- le contenu est écrit dans « nom.part » puis renommé seulement après vérification ;
- un fichier vide ou plus court que prévu n'est jamais déclaré terminé ;
- une interruption laisse le « .part » pour une reprise (HTTP Range) ;
- un fichier existant n'est jamais écrasé ;
- chaque redirection est validée à nouveau.
"""

from __future__ import annotations

import http.client
import os
import threading
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path

from overload.core.errors import OverloadError
from overload.downloads.urls import ALLOWED_SCHEMES, validate_direct_url

CHUNK_SIZE = 64 * 1024
USER_AGENT = "OverLoad/0.1 (+https://github.com/TOFazer/OverLoad)"

ProgressCallback = Callable[[int, int | None], None]


class DownloadCancelled(OverloadError):
    """L'utilisateur a annulé le téléchargement ; le .part est supprimé."""


class _ValidatingRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, allow_private_hosts: bool) -> None:
        self._allow_private = allow_private_hosts

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        if urllib.parse.urlsplit(newurl).scheme.lower() not in ALLOWED_SCHEMES:
            raise OverloadError(
                "La redirection vers une autre source a été refusée.",
                "la nouvelle adresse n'utilise pas http ou https.",
                "Vérifiez l'adresse d'origine.",
            )
        validate_direct_url(newurl, allow_private_hosts=self._allow_private)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _open(url: str, *, offset: int, allow_private_hosts: bool):  # noqa: ANN202
    headers = {"User-Agent": USER_AGENT}
    if offset > 0:
        headers["Range"] = f"bytes={offset}-"
    opener = urllib.request.build_opener(_ValidatingRedirectHandler(allow_private_hosts))
    return opener.open(urllib.request.Request(url, headers=headers), timeout=30)


def download_to(
    url: str,
    target: Path,
    *,
    expected_size: int | None = None,
    allow_private_hosts: bool = False,
    progress: ProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
) -> Path:
    """Télécharge `url` vers `target` (chemin choisi via plan_destination).

    Lève OverloadError en cas d'échec ; le fichier `target` n'existe alors pas.
    """
    clean_url = validate_direct_url(url, allow_private_hosts=allow_private_hosts)
    target = Path(target)
    part = target.with_name(target.name + ".part")

    if target.exists():
        raise OverloadError(
            "Un fichier porte déjà ce nom.",
            "le téléchargement ne remplace jamais un fichier existant.",
            "Choisissez un autre nom de fichier.",
        )
    if not target.parent.is_dir():
        raise OverloadError(
            "Le dossier de destination est introuvable.",
            "il a été supprimé ou il n'est pas accessible.",
            "Choisissez un autre dossier dans les paramètres.",
        )

    offset = part.stat().st_size if part.exists() else 0
    try:
        response = _open(clean_url, offset=offset, allow_private_hosts=allow_private_hosts)
    except urllib.error.HTTPError as exc:
        if exc.code == 416 and offset > 0:
            # Le .part est déjà complet ou invalide : on repart de zéro.
            part.unlink(missing_ok=True)
            offset = 0
            response = _open(clean_url, offset=0, allow_private_hosts=allow_private_hosts)
        else:
            raise _http_error(exc) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise OverloadError(
            "Connexion impossible ou interrompue.",
            str(getattr(exc, "reason", exc)),
            "Vérifiez votre connexion puis relancez le téléchargement.",
        ) from exc

    with response:
        status = getattr(response, "status", 200)
        if offset > 0 and status != 206:
            # Le serveur ignore Range : on recommence proprement.
            offset = 0
        length_header = response.headers.get("Content-Length")
        remaining = int(length_header) if length_header and length_header.isdigit() else None
        total = (offset + remaining) if remaining is not None else expected_size
        mode = "ab" if offset > 0 else "wb"
        received = offset

        with part.open(mode) as handle:
            while True:
                if cancel_event is not None and cancel_event.is_set():
                    handle.close()
                    part.unlink(missing_ok=True)
                    raise DownloadCancelled("Téléchargement annulé.")
                try:
                    chunk = response.read(CHUNK_SIZE)
                except (OSError, http.client.HTTPException) as exc:
                    raise OverloadError(
                        "Téléchargement interrompu.",
                        "la connexion a été coupée ; le fichier partiel est conservé pour reprise.",
                        "Relancez le téléchargement pour reprendre là où il s'est arrêté.",
                    ) from exc
                if not chunk:
                    break
                try:
                    handle.write(chunk)
                except OSError as exc:
                    raise OverloadError(
                        "Écriture impossible pendant le téléchargement.",
                        str(exc),
                        "Vérifiez l'espace disque et les droits du dossier, puis relancez.",
                    ) from exc
                received += len(chunk)
                if progress is not None:
                    progress(received, total)
            handle.flush()
            os.fsync(handle.fileno())

    _verify(part, received=received, expected_total=total, expected_size=expected_size)
    if target.exists():
        part.unlink(missing_ok=True)
        raise OverloadError(
            "Un fichier porte déjà ce nom.",
            "il a été créé pendant le téléchargement.",
            "Choisissez un autre nom de fichier.",
        )
    os.replace(part, target)
    return target


def _http_error(exc: urllib.error.HTTPError) -> OverloadError:
    if 300 <= exc.code < 400:
        # urllib refuse lui-même les redirections non HTTP(S) et lève une 3xx.
        return OverloadError(
            "La redirection vers une autre adresse a été refusée.",
            f"réponse HTTP {exc.code} vers une destination non autorisée.",
            "Vérifiez l'adresse d'origine.",
        )
    if exc.code in (401, 403):
        return OverloadError(
            "Accès refusé à ce fichier.",
            f"le serveur a répondu {exc.code}.",
            "Ce fichier n'est peut-être pas accessible publiquement.",
        )
    if exc.code == 404:
        return OverloadError(
            "Fichier introuvable.",
            "le serveur a répondu 404.",
            "Vérifiez que l'adresse est correcte et toujours en ligne.",
        )
    return OverloadError(
        "Le serveur a refusé la demande.",
        f"réponse HTTP {exc.code}.",
        "Réessayez plus tard ou vérifiez l'adresse.",
    )


def _verify(
    part: Path, *, received: int, expected_total: int | None, expected_size: int | None
) -> None:
    actual = part.stat().st_size if part.exists() else 0
    if actual == 0 or received == 0:
        part.unlink(missing_ok=True)
        raise OverloadError(
            "Le fichier téléchargé est vide.",
            "le serveur n'a envoyé aucune donnée.",
            "Vérifiez l'adresse ou réessayez plus tard.",
        )
    if expected_size is not None and actual != expected_size:
        raise OverloadError(
            "Le fichier téléchargé est incomplet.",
            f"{actual} octets reçus, {expected_size} attendus.",
            "Relancez le téléchargement pour reprendre.",
        )
    if expected_total is not None and actual != expected_total:
        raise OverloadError(
            "Le fichier téléchargé est incomplet.",
            f"{actual} octets reçus, {expected_total} annoncés par le serveur.",
            "Relancez le téléchargement pour reprendre.",
        )
