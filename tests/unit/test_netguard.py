import socket
import ssl
import urllib.request
from types import SimpleNamespace

import pytest

from overload.core.errors import OverloadError
from overload.downloads import netguard
from overload.downloads.netguard import is_public_ip, resolve_checked


@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1",
        "10.1.2.3",
        "172.16.0.1",
        "192.168.0.1",
        "169.254.169.254",
        "100.64.0.1",  # CGNAT
        "0.0.0.0",
        "224.0.0.1",
        "::1",
        "fe80::1",
        "fc00::1",
        "::ffff:127.0.0.1",  # IPv4 mappée sur bouclage
        "::ffff:10.0.0.1",
        "not-an-ip",
    ],
)
def test_non_public_addresses_are_refused(ip):
    assert not is_public_ip(ip)


@pytest.mark.parametrize("ip", ["93.184.216.34", "8.8.8.8", "2606:4700:4700::1111"])
def test_public_addresses_are_accepted(ip):
    assert is_public_ip(ip)


def _fake_resolver(monkeypatch, answers):
    real = socket.getaddrinfo

    def fake(host, port, *args, **kwargs):
        if host == "rebind.test":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port)) for ip in answers]
        return real(host, port, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", fake)


def test_mixed_answer_is_refused_even_if_one_address_is_public(monkeypatch):
    _fake_resolver(monkeypatch, ["93.184.216.34", "127.0.0.1"])
    with pytest.raises(OverloadError, match="privée"):
        resolve_checked("rebind.test", 80, allow_private=False)


def test_public_answer_is_returned(monkeypatch):
    _fake_resolver(monkeypatch, ["93.184.216.34", "93.184.216.34"])
    assert resolve_checked("rebind.test", 80, allow_private=False) == ["93.184.216.34"]


def test_private_answer_allowed_only_explicitly(monkeypatch):
    _fake_resolver(monkeypatch, ["127.0.0.1"])
    assert resolve_checked("rebind.test", 80, allow_private=True) == ["127.0.0.1"]


def test_unresolvable_host_gives_readable_error():
    with pytest.raises(OverloadError, match="introuvable"):
        resolve_checked("nonexistent.invalid", 80, allow_private=False)


def test_refused_resolution_never_opens_a_socket(monkeypatch, tmp_path):
    from overload.downloads.engine import download_to

    _fake_resolver(monkeypatch, ["10.9.8.7"])

    def forbidden(*args, **kwargs):
        raise AssertionError("aucune connexion ne doit être tentée")

    monkeypatch.setattr(netguard, "_connect_to", forbidden)
    with pytest.raises(OverloadError):
        download_to("http://rebind.test/file.bin", tmp_path / "file.bin")
    assert list(tmp_path.iterdir()) == []


def test_https_handler_uses_a_secure_context_without_check_hostname(monkeypatch):
    """Régression v1.0.0 : `check_hostname` n'était plus accepté par
    `HTTPSConnection` depuis Python 3.12 ; le contexte SSL porte déjà la
    vérification du certificat et du nom d'hôte."""
    handler = netguard._PinnedHTTPSHandler(allow_private=False)
    assert handler._context.verify_mode == ssl.CERT_REQUIRED
    assert handler._context.check_hostname is True

    captured = {}

    def fake_do_open(http_class, req, **kwargs):
        captured["http_class"] = http_class
        captured["kwargs"] = kwargs

    monkeypatch.setattr(handler, "do_open", fake_do_open)
    handler.https_open(urllib.request.Request("https://example.com/file.bin"))

    assert set(captured["kwargs"]) == {"context"}
    assert captured["kwargs"]["context"] is handler._context


def test_https_connect_verifies_the_original_hostname(monkeypatch):
    """Le certificat est vérifié contre le nom d'origine, jamais contre l'IP."""
    resolved = []
    wrapped = {}

    def fake_resolve(host, port, *, allow_private):
        resolved.append((host, port, allow_private))
        return ["93.184.216.34"]

    def wrap_socket(sock, server_hostname=None):
        wrapped["server_hostname"] = server_hostname
        wrapped["sock"] = sock
        return "tls-socket"

    context = SimpleNamespace(
        verify_mode=ssl.CERT_REQUIRED,
        check_hostname=True,
        post_handshake_auth=None,
        wrap_socket=wrap_socket,
    )

    monkeypatch.setattr(netguard, "resolve_checked", fake_resolve)
    monkeypatch.setattr(netguard, "_connect_to", lambda *args: "raw-socket")

    connection = netguard._PinnedHTTPSConnection(
        "example.com", allow_private=False, context=context
    )
    connection.connect()

    assert resolved == [("example.com", 443, False)]
    assert wrapped == {"server_hostname": "example.com", "sock": "raw-socket"}
    assert connection.sock == "tls-socket"
