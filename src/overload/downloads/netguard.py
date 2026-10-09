"""Garde réseau : vérifie l'adresse IP réellement contactée.

Protection contre le DNS rebinding : pour chaque connexion, le nom de domaine
est résolu une seule fois, toutes les adresses obtenues sont contrôlées, puis
la connexion ne se fait QU'AUX adresses validées. Le nom d'origine reste
utilisé pour le SNI et la vérification du certificat HTTPS.

Limite assumée : pas de proxy système. Un proxy résoudrait le nom à notre
place, ce qui rendrait ce contrôle inopérant ; le proxy est donc désactivé
pour les téléchargements (une prise en charge explicite viendra plus tard).
"""

from __future__ import annotations

import http.client
import ipaddress
import socket
import ssl
import urllib.request

from overload.core.errors import OverloadError


def is_public_ip(address: str) -> bool:
    """Vrai uniquement pour une adresse IP publique routable."""
    try:
        ip = ipaddress.ip_address(address.split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped  # ::ffff:127.0.0.1 est une adresse locale
    return ip.is_global and not ip.is_multicast


def resolve_checked(host: str, port: int, *, allow_private: bool) -> list[str]:
    """Résout `host` une seule fois et retourne les adresses à utiliser.

    Lève OverloadError si une seule des adresses est non publique (sauf
    allow_private, réservé aux tests et aux serveurs locaux explicitement voulus).
    """
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise OverloadError(
            "Nom de domaine introuvable.",
            f"la résolution DNS de « {host} » a échoué.",
            "Vérifiez l'adresse et votre connexion Internet.",
        ) from exc

    addresses: list[str] = []
    for *_, sockaddr in infos:
        ip = sockaddr[0]
        if not allow_private and not is_public_ip(ip):
            raise OverloadError(
                "Cette adresse mène à une machine locale ou privée.",
                "le nom résout vers une adresse non publique.",
                "Utilisez l'adresse publique du fichier.",
            )
        if ip not in addresses:
            addresses.append(ip)
    if not addresses:
        raise OverloadError(
            "Nom de domaine introuvable.",
            f"aucune adresse pour « {host} ».",
            "Vérifiez l'adresse.",
        )
    return addresses


def _connect_to(addresses: list[str], port: int, timeout, source_address):  # noqa: ANN001, ANN202
    last_error: OSError | None = None
    for ip in addresses:
        try:
            return socket.create_connection((ip, port), timeout, source_address)
        except OSError as exc:
            last_error = exc
    raise last_error or OSError("aucune adresse joignable")


class _PinnedHTTPConnection(http.client.HTTPConnection):
    def __init__(self, host, *, allow_private: bool, **kwargs) -> None:  # noqa: ANN001
        super().__init__(host, **kwargs)
        self._allow_private = allow_private

    def connect(self) -> None:
        addresses = resolve_checked(self.host, self.port, allow_private=self._allow_private)
        self.sock = _connect_to(addresses, self.port, self.timeout, self.source_address)


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host, *, allow_private: bool, **kwargs) -> None:  # noqa: ANN001
        super().__init__(host, **kwargs)
        self._allow_private = allow_private

    def connect(self) -> None:
        addresses = resolve_checked(self.host, self.port, allow_private=self._allow_private)
        raw = _connect_to(addresses, self.port, self.timeout, self.source_address)
        # Le certificat est vérifié contre le nom d'origine, pas contre l'IP.
        self.sock = self._context.wrap_socket(raw, server_hostname=self.host)


class _PinnedHTTPHandler(urllib.request.HTTPHandler):
    def __init__(self, allow_private: bool) -> None:
        super().__init__()
        self._allow_private = allow_private

    def http_open(self, req):  # noqa: ANN001, ANN202
        return self.do_open(
            lambda host, **kw: _PinnedHTTPConnection(host, allow_private=self._allow_private, **kw),
            req,
        )


class _PinnedHTTPSHandler(urllib.request.HTTPSHandler):
    def __init__(self, allow_private: bool) -> None:
        super().__init__(context=ssl.create_default_context())
        self._allow_private = allow_private

    def https_open(self, req):  # noqa: ANN001, ANN202
        return self.do_open(
            lambda host, **kw: _PinnedHTTPSConnection(
                host, allow_private=self._allow_private, **kw
            ),
            req,
            context=self._context,
            check_hostname=self._check_hostname,
        )


def pinned_handlers(allow_private: bool) -> list[urllib.request.BaseHandler]:
    """Gestionnaires HTTP/HTTPS qui contrôlent l'adresse avant chaque connexion."""
    return [
        urllib.request.ProxyHandler({}),  # aucun proxy : voir la note du module
        _PinnedHTTPHandler(allow_private),
        _PinnedHTTPSHandler(allow_private),
    ]
