import pytest

from overload.core.errors import OverloadError
from overload.downloads.urls import validate_direct_url


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/video.mp4",
        "http://example.org/files/audio%20piste.mp3",
        "  https://example.com/a.webm  ",
    ],
)
def test_accepts_direct_http_urls(url):
    assert validate_direct_url(url) == url.strip()


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/a.mp4",
        "file:///C:/Windows/win.ini",
        "javascript:alert(1)",
        "data:text/plain,hello",
        "example.com/a.mp4",
    ],
)
def test_rejects_unsupported_schemes(url):
    with pytest.raises(OverloadError) as info:
        validate_direct_url(url)
    assert info.value.action


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/a.mp4",
        "http://127.0.0.1:8000/a.mp4",
        "http://192.168.1.10/a.mp4",
        "http://10.0.0.5/a.mp4",
        "http://169.254.169.254/latest/meta-data",
        "http://[::1]/a.mp4",
        "http://printer.local/a.mp4",
    ],
)
def test_rejects_local_and_private_hosts(url):
    with pytest.raises(OverloadError):
        validate_direct_url(url)


def test_private_hosts_allowed_only_when_explicit():
    assert validate_direct_url("http://127.0.0.1/a.mp4", allow_private_hosts=True)


def test_rejects_credentials_in_url():
    with pytest.raises(OverloadError, match="identifiants"):
        validate_direct_url("https://user:secret@example.com/a.mp4")


@pytest.mark.parametrize("url", ["", "   ", "https://", "https://" + "a" * 2100 + ".com/x"])
def test_rejects_empty_or_incomplete(url):
    with pytest.raises(OverloadError):
        validate_direct_url(url)
