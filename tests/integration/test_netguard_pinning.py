import socket
from urllib.parse import urlsplit

from overload.downloads import netguard
from overload.downloads.engine import download_to
from overload.downloads.files import plan_destination


def test_connection_goes_only_to_validated_addresses(monkeypatch, server, tmp_path):
    """Le nom est résolu une fois ; la connexion utilise exactement cette adresse."""
    port = urlsplit(server).port
    calls = {"resolve": 0}
    real = socket.getaddrinfo

    def fake(host, p, *args, **kwargs):
        if host == "rebind.test":
            calls["resolve"] += 1
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", p))]
        return real(host, p, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", fake)
    seen = []
    real_connect = netguard._connect_to

    def recording(addresses, *args):
        seen.append(list(addresses))
        return real_connect(addresses, *args)

    monkeypatch.setattr(netguard, "_connect_to", recording)
    target = plan_destination(tmp_path, "file.bin")
    download_to(f"http://rebind.test:{port}/ok.bin", target, allow_private_hosts=True)
    assert target.stat().st_size > 0
    assert seen == [["127.0.0.1"]]
    assert calls["resolve"] == 1
