"""Validation des URL de téléchargement.

Version 1 : seules les URL HTTP(S) qui pointent directement vers un fichier
sont acceptées. Aucun extracteur de plateforme n'est utilisé.

Limite connue : la validation porte sur l'URL et sur les adresses littérales
(IP ou localhost). Elle ne protège pas contre un nom de domaine qui résout
vers une adresse privée (DNS rebinding) ; ce point sera traité au niveau de
la connexion en Phase 1 suivante.
"""

from __future__ import annotations

import ipaddress
from urllib.parse import urlsplit

from overload.core.errors import OverloadError

ALLOWED_SCHEMES = frozenset({"http", "https"})
MAX_URL_LENGTH = 2048
_BLOCKED_HOST_NAMES = frozenset({"localhost"})
_BLOCKED_HOST_SUFFIXES = (".local", ".localhost", ".internal")


def _is_private_literal(host: str) -> bool:
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def validate_direct_url(url: str, *, allow_private_hosts: bool = False) -> str:
    """Retourne l'URL nettoyée, ou lève OverloadError si elle n'est pas acceptable."""
    if not isinstance(url, str):
        raise OverloadError("Adresse invalide.", "la valeur n'est pas du texte.")

    cleaned = url.strip()
    if not cleaned:
        raise OverloadError(
            "Aucune adresse n'a été saisie.",
            action="Collez une adresse de fichier.",
        )
    if len(cleaned) > MAX_URL_LENGTH:
        raise OverloadError(
            "Adresse trop longue.",
            f"plus de {MAX_URL_LENGTH} caractères.",
            "Vérifiez que l'adresse est complète.",
        )

    try:
        parts = urlsplit(cleaned)
    except ValueError as exc:
        raise OverloadError("Adresse mal formée.", str(exc), "Vérifiez l'adresse copiée.") from exc

    if parts.scheme.lower() not in ALLOWED_SCHEMES:
        raise OverloadError(
            "Ce type d'adresse n'est pas pris en charge.",
            f"protocole « {parts.scheme or 'absent'} ».",
            "Utilisez une adresse commençant par https:// ou http://.",
        )
    if parts.username is not None or parts.password is not None:
        raise OverloadError(
            "L'adresse contient des identifiants.",
            "un nom d'utilisateur ou un mot de passe figure dans l'URL.",
            "Retirez-les de l'adresse : OverLoad ne les utilise pas.",
        )

    host = (parts.hostname or "").lower().rstrip(".")
    if not host:
        raise OverloadError("Adresse incomplète.", "nom de domaine absent.", "Vérifiez l'adresse.")

    if not allow_private_hosts:
        if host in _BLOCKED_HOST_NAMES or host.endswith(_BLOCKED_HOST_SUFFIXES):
            raise OverloadError(
                "Cette adresse désigne une machine locale ou privée.",
                "les adresses locales ne sont pas autorisées.",
                "Utilisez l'adresse publique du fichier.",
            )
        if _is_private_literal(host):
            raise OverloadError(
                "Cette adresse désigne une machine locale ou privée.",
                "les adresses IP privées ou de bouclage ne sont pas autorisées.",
                "Utilisez l'adresse publique du fichier.",
            )

    return cleaned
