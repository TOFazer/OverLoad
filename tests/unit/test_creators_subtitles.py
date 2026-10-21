from __future__ import annotations

import json
from pathlib import Path

import pytest

from overload.core.errors import OverloadError
from overload.creators.subtitles import (
    create_srt_template,
    extract_audio_track,
    extract_subtitle_track,
    parse_tracks,
    probe_tracks,
)

FFPROBE_SAMPLE = {
    "format": {"format_name": "mov,mp4,m4a,3gp,3g2,mj2", "duration": "83.5"},
    "streams": [
        {
            "index": 0,
            "codec_type": "video",
            "codec_name": "h264",
            "width": 1920,
            "height": 1080,
            "disposition": {"default": 1},
        },
        {
            "index": 1,
            "codec_type": "audio",
            "codec_name": "aac",
            "channels": 2,
            "sample_rate": "48000",
            "tags": {"language": "fra", "title": "VF"},
            "disposition": {"default": 1},
        },
        {
            "index": 2,
            "codec_type": "audio",
            "codec_name": "ac3",
            "channels": 6,
            "tags": {"language": "eng"},
            "disposition": {"forced": 1},
        },
        {
            "index": 3,
            "codec_type": "subtitle",
            "codec_name": "subrip",
            "tags": {"language": "fra"},
            "disposition": {},
        },
        {"index": 4, "codec_type": "data", "codec_name": "tmcd"},
    ],
}


def test_parse_tracks_extracts_kinds_ordinals_and_details():
    container, duration, tracks = parse_tracks(FFPROBE_SAMPLE)
    assert container.startswith("mov")
    assert duration == pytest.approx(83.5)
    assert [t.kind for t in tracks] == ["video", "audio", "audio", "subtitle"]
    assert [t.kind_index for t in tracks] == [0, 0, 1, 0], "numérotation par type"
    subtitle = tracks[3]
    assert subtitle.codec == "subrip"
    assert subtitle.language == "fra"
    audio2 = tracks[2]
    assert audio2.channels == 6
    assert audio2.is_forced is True
    assert "Sous-titres #1" in subtitle.summary()
    assert "6 canal(aux)" in audio2.summary()


def test_parse_tracks_with_empty_metadata():
    container, duration, tracks = parse_tracks({})
    assert container == ""
    assert duration is None
    assert tracks == ()


def test_probe_tracks_requires_existing_file(tmp_path):
    with pytest.raises(OverloadError, match="introuvable"):
        probe_tracks(tmp_path / "absent.mp4")


def test_probe_tracks_parses_ffprobe_json(tmp_path, monkeypatch):
    media = tmp_path / "film.mp4"
    media.write_bytes(b"media")

    def fake_run(name, args, timeout=60):
        assert name == "ffprobe"
        assert "-show_streams" in args
        return 0, json.dumps(FFPROBE_SAMPLE), ""

    monkeypatch.setattr("overload.creators.subtitles.run_tool", fake_run)
    report = probe_tracks(media)
    assert report.path == media
    assert "1 piste(s) vidéo" in report.summary()
    assert "2 piste(s) audio" in report.summary()
    assert "1 piste(s) de sous-titres" in report.summary()
    assert len(report.of_kind("audio")) == 2
    assert len(report.of_kind("subtitle")) == 1


def test_probe_tracks_raises_on_ffprobe_error(tmp_path, monkeypatch):
    media = tmp_path / "film.mp4"
    media.write_bytes(b"corrompu")
    monkeypatch.setattr(
        "overload.creators.subtitles.run_tool",
        lambda name, args, timeout=60: (1, "", "Invalid data found when processing input"),
    )
    with pytest.raises(OverloadError, match="pistes"):
        probe_tracks(media)


def test_extract_subtitle_track_builds_correct_ffmpeg_call(tmp_path, monkeypatch):
    media = tmp_path / "film.mkv"
    media.write_bytes(b"media")
    captured = {}

    def fake_run(name, args, timeout=1800):
        captured["args"] = args
        Path(args[-1]).write_text("1\n00:00:00,000 --> 00:00:01,000\nBonjour\n")
        return 0, "", ""

    monkeypatch.setattr("overload.creators.subtitles.run_tool", fake_run)
    result = extract_subtitle_track(media, 1, tmp_path)
    args = captured["args"]
    assert args[args.index("-map") + 1] == "0:s:1", "sélecteur de piste de sous-titres"
    assert args[args.index("-c:s") + 1] == "srt"
    assert str(media) in args
    assert result.name.endswith(".srt")
    assert "sous-titres 02" in result.name


def test_extract_audio_track_builds_wav_pcm_call(tmp_path, monkeypatch):
    media = tmp_path / "film.mp4"
    media.write_bytes(b"media")
    captured = {}

    def fake_run(name, args, timeout=1800):
        captured["args"] = args
        Path(args[-1]).write_bytes(b"RIFF")
        return 0, "", ""

    monkeypatch.setattr("overload.creators.subtitles.run_tool", fake_run)
    result = extract_audio_track(media, 0, tmp_path, base_name="Narration")
    args = captured["args"]
    assert args[args.index("-map") + 1] == "0:a:0"
    assert args[args.index("-c:a") + 1] == "pcm_s16le"
    assert result.name == "Narration - audio 01.wav"


def test_extract_never_overwrites_existing_output(tmp_path, monkeypatch):
    media = tmp_path / "film.mp4"
    media.write_bytes(b"media")
    (tmp_path / "film - sous-titres 01.srt").write_text("ancien")

    def fake_run(name, args, timeout=1800):
        out = Path(args[-1])
        out.write_text("nouveau")
        return 0, "", ""

    monkeypatch.setattr("overload.creators.subtitles.run_tool", fake_run)
    result = extract_subtitle_track(media, 0, tmp_path)
    assert result.name == "film - sous-titres 01 (2).srt"
    assert (tmp_path / "film - sous-titres 01.srt").read_text() == "ancien"


def test_extract_failure_raises_user_error(tmp_path, monkeypatch):
    media = tmp_path / "film.mp4"
    media.write_bytes(b"media")
    monkeypatch.setattr(
        "overload.creators.subtitles.run_tool",
        lambda name, args, timeout=1800: (1, "", "Invalid argument"),
    )
    with pytest.raises(OverloadError, match="extraction"):
        extract_subtitle_track(media, 0, tmp_path)


def test_create_srt_template_writes_utf8_skeleton(tmp_path):
    target = tmp_path / "sous-titres" / "film.srt"
    created = create_srt_template(target, title="Mon film")
    content = created.read_text(encoding="utf-8")
    assert created == target
    assert created.parent.is_dir()
    assert content.count("-->") >= 4, "plusieurs repères de temps d'exemple"
    assert "Mon film" in content
    assert "UTF-8" in content


def test_create_srt_template_forces_srt_extension_and_unique(tmp_path):
    first = create_srt_template(tmp_path / "modele.txt")
    assert first.suffix == ".srt"
    second = create_srt_template(tmp_path / "modele.txt")
    assert second.name == "modele (2).srt"
