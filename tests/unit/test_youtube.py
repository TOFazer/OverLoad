"""Tests unitaires de l'extracteur YouTube (sans réseau, `yt-dlp` simulé)."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from overload.core.errors import OverloadError
from overload.downloads.engine import DownloadCancelled, DownloadPaused
from overload.downloads.youtube import (
    MediaInfo,
    YoutubeExtractor,
    format_selector,
    is_youtube_url,
    normalize_quality,
    quality_label,
    verify_downloaded_media,
    youtube_video_id,
)

RAW_INFO = {
    "id": "dQw4w9WgXcQ",
    "title": "Démonstration: vidéo/YouTube ?",
    "uploader": "Chaîne de test",
    "duration": 212.5,
    "thumbnail": "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg",
    "webpage_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "formats": [
        {"format_id": "137", "vcodec": "avc1.640028", "height": 1080},
        {"format_id": "22", "vcodec": "avc1.64001F", "height": 720},
        {"format_id": "18", "vcodec": "avc1.42001E", "height": 360},
        {"format_id": "251", "vcodec": "none", "acodec": "opus", "height": None},
    ],
}


class FakeYDL:
    """Reproduit l'API minimale de `yt_dlp.YoutubeDL` utilisée par OverLoad."""

    instances: list[FakeYDL] = []
    write_bytes = b"video-binaire" * 64
    probe_calls = 0

    def __init__(self, options: dict) -> None:
        self.options = options
        self.destroyed = False
        FakeYDL.instances.append(self)

    def __enter__(self) -> FakeYDL:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.destroyed = True

    def extract_info(self, url: str, download: bool = False) -> dict:
        FakeYDL.probe_calls += 1
        return dict(RAW_INFO)

    def download(self, urls: list[str]) -> int:
        outtmpl = self.options["outtmpl"]["default"]
        stem = outtmpl.replace(".%(ext)s", "")
        hook = self.options["progress_hooks"][0]
        hook(
            {
                "status": "downloading",
                "filename": stem + ".f137.mp4",
                "downloaded_bytes": 128,
                "total_bytes": 512,
            }
        )
        hook(
            {
                "status": "downloading",
                "filename": stem + ".f137.mp4",
                "downloaded_bytes": 512,
                "total_bytes": 512,
            }
        )
        hook({"status": "finished", "filename": stem + ".f137.mp4", "total_bytes": 512})
        # Un fragment vidéo et un fragment audio restent sur le disque.
        Path(stem + ".f137.mp4").write_bytes(FakeYDL.write_bytes)
        Path(stem + ".f140.m4a").write_bytes(b"audio" * 32)
        for pp_hook in self.options.get("postprocessor_hooks") or []:
            pp_hook({"status": "started"})
            pp_hook({"status": "finished"})
        return 0


class FakeModule:
    YoutubeDL = FakeYDL


@pytest.fixture(autouse=True)
def _reset_fake() -> None:
    FakeYDL.instances.clear()
    FakeYDL.probe_calls = 0


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://youtube.com/watch?v=dQw4w9WgXcQ&t=42s", "dQw4w9WgXcQ"),
        ("https://youtu.be/dQw4w9WgXcQ?si=abc", "dQw4w9WgXcQ"),
        ("https://m.youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/embed/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ],
)
def test_youtube_urls_are_recognised(url, expected):
    assert youtube_video_id(url) == expected
    assert is_youtube_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/video.mp4",
        "https://www.youtube.com/@une-chaine",
        "https://www.youtube.com/playlist?list=PL123",
        "https://soundcloud.com/artiste/titre",
        "ftp://youtube.com/watch?v=dQw4w9WgXcQ",
        "",
    ],
)
def test_non_video_urls_are_rejected(url):
    assert youtube_video_id(url) is None
    assert is_youtube_url(url) is False


def test_quality_values_and_labels():
    assert normalize_quality(None) == "best"
    assert normalize_quality("1080p60") == "1080p"
    assert normalize_quality("720") == "720p"
    assert quality_label("best") == "Meilleure disponible"
    with pytest.raises(OverloadError):
        normalize_quality("ultra")


def test_format_selector_prefers_h264_mp4():
    selector = format_selector("1080p")
    assert "height<=1080" in selector
    assert "avc1" in selector
    assert selector != format_selector("best")


def test_probe_returns_metadata_and_uses_cache(tmp_path):
    extractor = YoutubeExtractor(module=FakeModule, ffmpeg_dir=tmp_path)
    info = extractor.probe("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert isinstance(info, MediaInfo)
    assert info.title.startswith("Démonstration")
    assert info.uploader == "Chaîne de test"
    assert info.heights == (1080, 720, 360)
    assert info.duration_seconds == pytest.approx(212.5)
    assert info.thumbnail_url.endswith("hqdefault.jpg")

    payload = info.to_dict(quality="720p")
    assert payload["qualities"][0] == {"value": "best", "label": "Meilleure disponible"}
    assert {"value": "1080p", "label": "1080p (Full HD)"} in payload["qualities"]

    extractor.probe("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert FakeYDL.probe_calls == 1


def test_probe_rejects_non_youtube_url():
    extractor = YoutubeExtractor(module=FakeModule)
    with pytest.raises(OverloadError, match="YouTube"):
        extractor.probe("https://example.com/film.mp4")


def test_download_writes_merged_mp4_and_reports_progress(tmp_path):
    extractor = YoutubeExtractor(
        module=FakeModule,
        ffmpeg_dir=tmp_path,
        ffprobe_available=lambda: False,
    )
    target = tmp_path / "video.mp4"
    samples: list[tuple[int, int | None]] = []
    info = extractor.download(
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        target,
        quality="720p",
        progress=lambda done, total: samples.append((done, total)),
    )
    assert info.video_id == "dQw4w9WgXcQ"
    assert target.is_file() and target.stat().st_size == len(FakeYDL.write_bytes)
    assert samples and samples[-1][0] == 512
    assert all(done <= (total or 512) for done, total in samples if total)
    # Les fragments et fichiers temporaires ne traînent pas dans le dossier final.
    leftovers = [p.name for p in tmp_path.iterdir() if p.name != "video.mp4"]
    assert leftovers == []

    options = FakeYDL.instances[-1].options
    assert options["merge_output_format"] == "mp4"
    assert options["format"] == format_selector("720p")
    assert options["outtmpl"]["default"].endswith(".%(ext)s")
    assert options["postprocessors"][0]["key"] == "FFmpegVideoRemuxer"


def test_download_honours_cancel_and_pause(tmp_path):
    extractor = YoutubeExtractor(module=FakeModule, ffprobe_available=lambda: False)
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(DownloadCancelled):
        extractor.download(
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            tmp_path / "annule.mp4",
            cancel_event=cancel,
        )
    assert not (tmp_path / "annule.mp4").exists()

    pause = threading.Event()
    pause.set()
    with pytest.raises(DownloadPaused):
        extractor.download(
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            tmp_path / "pause.mp4",
            pause_event=pause,
        )


def test_download_refuses_to_overwrite(tmp_path):
    extractor = YoutubeExtractor(module=FakeModule)
    target = tmp_path / "existe.mp4"
    target.write_bytes(b"deja la")
    with pytest.raises(OverloadError, match="déjà"):
        extractor.download("https://www.youtube.com/watch?v=dQw4w9WgXcQ", target)


def test_missing_yt_dlp_produces_a_clear_error(tmp_path, monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "yt_dlp":
            raise ImportError("absent")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    extractor = YoutubeExtractor()
    assert extractor.available() is False
    with pytest.raises(OverloadError, match="yt-dlp"):
        extractor.probe("https://www.youtube.com/watch?v=dQw4w9WgXcQ")


def test_error_translation_covers_common_youtube_failures():
    extractor = YoutubeExtractor(module=FakeModule)
    private = extractor._translate_error(
        Exception("ERROR: Private video. Sign in if you've been granted access")
    )
    assert "privée" in private.what
    age = extractor._translate_error(Exception("Sign in to confirm your age"))
    assert "majeur" in age.what
    unavailable = extractor._translate_error(Exception("ERROR: Video unavailable"))
    assert "disponible" in unavailable.what
    network = extractor._translate_error(Exception("Unable to download webpage: timed out"))
    assert "Connexion" in network.what


def test_verify_rejects_empty_and_missing_files(tmp_path):
    with pytest.raises(OverloadError, match="n'a pas été créé"):
        verify_downloaded_media(tmp_path / "absent.mp4", ffprobe_available=lambda: False)
    empty = tmp_path / "vide.mp4"
    empty.write_bytes(b"")
    with pytest.raises(OverloadError, match="vide"):
        verify_downloaded_media(empty, ffprobe_available=lambda: False)
    assert not empty.exists()


def test_verify_accepts_a_real_video_stream(tmp_path, monkeypatch):
    from overload.media import analyzer

    sample = tmp_path / "ok.mp4"
    sample.write_bytes(b"0" * 128)
    payload = (
        '{"streams": [{"codec_type": "video", "codec_name": "h264"},'
        ' {"codec_type": "audio", "codec_name": "aac"}],'
        ' "format": {"duration": "212.5"}}'
    )
    monkeypatch.setattr(analyzer, "run_tool", lambda *args, **kwargs: (0, payload, ""))
    report = verify_downloaded_media(sample, ffprobe_available=lambda: True)
    assert report["verified"] is True
    assert report["video_streams"] == 1
    assert report["duration_seconds"] == pytest.approx(212.5)


def test_verify_rejects_an_audio_only_file(tmp_path, monkeypatch):
    from overload.media import analyzer

    sample = tmp_path / "audio.mp4"
    sample.write_bytes(b"0" * 128)
    monkeypatch.setattr(
        analyzer,
        "run_tool",
        lambda *args, **kwargs: (0, '{"streams": [{"codec_type": "audio"}]}', ""),
    )
    with pytest.raises(OverloadError, match="piste vidéo"):
        verify_downloaded_media(sample, ffprobe_available=lambda: True)
