"""Intégration YouTube : gestionnaire, file d'attente et API Web (extracteur simulé)."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

import pytest

from overload.core.errors import OverloadError
from overload.downloads.manager import DownloadManager
from overload.downloads.state import TaskState
from overload.downloads.youtube import MediaInfo
from overload.ui.web.server import create_web_server

VIDEO_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


class FakeExtractor:
    """Extracteur YouTube en mémoire, sans réseau ni FFmpeg."""

    def __init__(self) -> None:
        self.download_calls: list[dict] = []
        self.probe_calls = 0
        self.probe_error: OverloadError | None = None

    def available(self) -> bool:
        return True

    def probe(self, url: str) -> MediaInfo:
        self.probe_calls += 1
        if self.probe_error is not None:
            raise self.probe_error
        return MediaInfo(
            url=url,
            video_id="dQw4w9WgXcQ",
            title="Mon film: démo / test ?",
            uploader="Studio OverLoad",
            duration_seconds=90.0,
            thumbnail_url="https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg",
            heights=(1080, 720, 360),
        )

    def download(
        self,
        url: str,
        target,
        *,
        quality=None,
        progress=None,
        cancel_event=None,
        pause_event=None,
        max_rate_bps=None,
        timeout=None,
    ):
        self.download_calls.append(
            {
                "url": url,
                "target": target,
                "quality": quality,
                "max_rate_bps": max_rate_bps,
            }
        )
        if progress is not None:
            progress(1024, 4096)
            progress(4096, 4096)
        target.write_bytes(b"mp4" * 1024)
        return MediaInfo(url=url, video_id="dQw4w9WgXcQ", title="Mon film")


@pytest.fixture
def youtube_manager(tmp_path):
    extractor = FakeExtractor()
    manager = DownloadManager(
        tmp_path / "downloads",
        youtube=extractor,
        auto_retry=False,
    )
    yield manager, extractor
    manager.shutdown()


def test_enqueue_youtube_resolves_title_quality_and_finishes(youtube_manager):
    manager, extractor = youtube_manager
    snap = manager.enqueue(VIDEO_URL, quality="720p")

    assert snap is not None
    assert snap.provider == "youtube"
    assert snap.quality == "720p"
    assert snap.filename == "Mon film_ démo _ test _.mp4"
    assert snap.target_path.parent == manager.settings().destination_dir

    assert manager.wait_all(timeout=10)
    final = manager.get_task(snap.id)
    assert final.state is TaskState.COMPLETED
    assert final.progress_percent == pytest.approx(100.0)
    assert final.target_path.is_file()
    assert final.target_path.stat().st_size == 3072
    assert final.media_title.startswith("Mon film")

    assert extractor.download_calls
    call = extractor.download_calls[-1]
    assert call["quality"] == "720p"
    assert call["target"] == snap.target_path
    assert call["max_rate_bps"] is None


def test_youtube_quality_defaults_to_best(youtube_manager):
    manager, _ = youtube_manager
    snap = manager.enqueue(VIDEO_URL)
    assert snap is not None
    assert snap.quality == "best"
    assert manager.wait_all(timeout=10)


def test_probe_failure_rejects_the_link(tmp_path):
    extractor = FakeExtractor()
    extractor.probe_error = OverloadError(
        "Cette vidéo YouTube est privée.",
        "son propriétaire ne l'a pas rendue publique.",
        "Utilisez une vidéo publique.",
    )
    manager = DownloadManager(tmp_path / "dl", youtube=extractor, auto_retry=False)
    try:
        with pytest.raises(OverloadError, match="privée"):
            manager.enqueue(VIDEO_URL)
        result = manager.enqueue_batch(VIDEO_URL)
        assert result.added == []
        assert result.rejected and "privée" in result.rejected[0].error
        assert manager.list_tasks() == []
    finally:
        manager.shutdown()


def test_inspect_batch_does_not_use_the_network_for_youtube(youtube_manager):
    manager, extractor = youtube_manager
    result = manager.inspect_batch(f"{VIDEO_URL}\nhttps://exemple.com/film.mp4")
    assert [item["provider"] for item in result["valid"]] == ["youtube", "http"]
    assert result["valid"][0]["filename"] == "YouTube dQw4w9WgXcQ.mp4"
    assert extractor.probe_calls == 0


def test_inspect_media_returns_qualities_and_suggested_name(youtube_manager):
    manager, _ = youtube_manager
    info = manager.inspect_media(VIDEO_URL)
    assert info["provider"] == "youtube"
    assert info["title"].startswith("Mon film")
    assert info["qualities"][0]["value"] == "best"
    assert {"value": "1080p", "label": "1080p (Full HD)"} in info["qualities"]
    assert info["suggested_filename"] == "Mon film_ démo _ test _.mp4"
    assert info["extractor_available"] is True


def test_inspect_media_rejects_direct_file_links(youtube_manager):
    manager, _ = youtube_manager
    with pytest.raises(OverloadError, match="YouTube"):
        manager.inspect_media("https://exemple.com/film.mp4")


def test_batch_applies_quality_to_youtube_links(youtube_manager):
    manager, extractor = youtube_manager
    result = manager.enqueue_batch(VIDEO_URL, quality="480p")
    assert len(result.added) == 1
    assert result.added[0].quality == "480p"
    assert manager.wait_all(timeout=10)
    assert extractor.download_calls[-1]["quality"] == "480p"


def _http_json(base: str, method: str, path: str, body: dict | None = None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        f"{base}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


@pytest.fixture
def youtube_web(tmp_path):
    server = create_web_server(
        destination_dir=tmp_path / "downloads",
        db_path=tmp_path / "library.db",
        host="127.0.0.1",
        port=0,
        youtube=FakeExtractor(),
    )
    server.enable_os_open = False
    server.start_background()
    yield server
    server.manager.shutdown()
    server.history.close()
    server.shutdown()


def test_web_media_info_and_youtube_download(youtube_web):
    base = youtube_web.url
    query = urllib.parse.urlencode({"url": VIDEO_URL})
    code, payload = _http_json(base, "GET", f"/api/media/info?{query}")
    assert code == 200
    assert payload["provider"] == "youtube"
    assert payload["title"].startswith("Mon film")

    code, payload = _http_json(
        base,
        "POST",
        "/api/downloads",
        {"url": VIDEO_URL, "quality": "1080p"},
    )
    assert code == 201
    assert payload["task"]["provider"] == "youtube"
    assert payload["task"]["quality"] == "1080p"

    code, state = _http_json(base, "GET", "/api/state")
    assert code == 200
    assert state["youtube"]["available"] is True
    assert state["youtube"]["qualities"][0]["value"] == "best"
    assert youtube_web.manager.wait_all(timeout=10)


def test_web_media_info_rejects_non_youtube_url(youtube_web):
    query = urllib.parse.urlencode({"url": "https://exemple.com/film.mp4"})
    code, payload = _http_json(youtube_web.url, "GET", f"/api/media/info?{query}")
    assert code == 400
    assert "YouTube" in payload["error"]
