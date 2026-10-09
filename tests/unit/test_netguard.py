import socket

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
