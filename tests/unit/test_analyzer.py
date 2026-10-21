from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from overload.media import analyzer


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("30000/1001", 29.97002997002997),
        ("0/0", None),
        ("N/A", None),
        ("25", 25.0),
        ("nan", None),
        ("1/0", None),
    ],
)
def test_fps(value, expected):
    assert analyzer.fps(value) == expected


def test_empty_file(tmp_path):
    path = tmp_path / "empty.mp4"
    path.touch()
    assert analyzer.analyze(path).integrity == "Fichier vide"


def test_missing_file(tmp_path):
    with pytest.raises(ValueError, match="existant"):
        analyzer.analyze(tmp_path / "missing")


def test_metadata_and_decode(tmp_path, monkeypatch):
    path = tmp_path / "film échantillon.mkv"
    path.write_bytes(b"media")
    metadata = {
        "format": {"format_name": "matroska,webm", "bit_rate": "1000000"},
        "streams": [
            {
                "index": 0,
                "codec_type": "video",
                "codec_name": "hevc",
                "pix_fmt": "yuv422p10le",
                "avg_frame_rate": "24/1",
                "r_frame_rate": "30/1",
                "width": 1920,
                "height": 1080,
            },
            {"index": 1, "codec_type": "audio", "codec_name": "dts"},
            {"index": 2, "codec_type": "subtitle", "codec_name": "ass"},
        ],
    }
    calls = []

    def run(name, args, timeout):
        calls.append((name, args))
        return (0, json.dumps(metadata), "") if name == "ffprobe" else (0, "", "")

    monkeypatch.setattr(analyzer, "_run", run)
    report = analyzer.analyze(path)
    assert report.metadata == metadata
    assert "sans erreur" in report.integrity
    assert "10 bits" in report.explanation()
    assert "cadence variable" in report.explanation()
    assert "sous-titres" in report.explanation()
    assert "remuxage" in report.explanation()
    assert [c[0] for c in calls] == ["ffprobe", "ffmpeg"]
    assert str(path) in calls[0][1]
    assert calls[1][1][calls[1][1].index("-protocol_whitelist") + 1] == "file"


@pytest.mark.parametrize("mode", ["bad_probe", "bad_decode", "timeout", "quick"])
def test_integrity_failures(tmp_path, monkeypatch, mode):
    path = tmp_path / "media.mp4"
    path.write_bytes(b"data")

    def run(name, args, timeout):
        if mode == "timeout":
            raise subprocess.TimeoutExpired(name, timeout)
        if mode == "bad_probe":
            return 1, "", "moov atom not found"
        if name == "ffprobe":
            return 0, json.dumps({"streams": [{"codec_type": "audio", "codec_name": "aac"}]}), ""
        return 1, "", "corrupt packet"

    monkeypatch.setattr(analyzer, "_run", run)
    report = analyzer.analyze(path, deep=mode != "quick")
    expected = {
        "bad_probe": "Illisible",
        "bad_decode": "Erreurs",
        "timeout": "Indéterminée",
        "quick": "Non vérifiée",
    }
    assert report.integrity.startswith(expected[mode])


def test_bundled_tool_preferred(tmp_path, monkeypatch):
    (tmp_path / "tools").mkdir()
    tool = tmp_path / "tools" / "ffprobe.exe"
    tool.touch()
    monkeypatch.setattr(analyzer.sys, "_MEIPASS", str(tmp_path), raising=False)
    assert analyzer.tool_path("ffprobe") == str(tool)


def test_unavailable_tool(monkeypatch):
    monkeypatch.setattr(analyzer.shutil, "which", lambda _: None)
    with pytest.raises(RuntimeError, match="introuvable"):
        analyzer.tool_path("nonexistent_tool")


def test_decode_timeout(tmp_path, monkeypatch):
    path = tmp_path / "video.mp4"
    path.write_bytes(b"data")

    def run(name, args, timeout):
        if name == "ffprobe":
            return 0, '{"streams": []}', ""
        raise subprocess.TimeoutExpired(name, timeout)

    monkeypatch.setattr(analyzer, "_run", run)
    assert "délai maximal" in analyzer.analyze(path).integrity


def test_real_wave_if_tools_available(tmp_path):
    import wave

    try:
        analyzer.tool_path("ffprobe")
        analyzer.tool_path("ffmpeg")
    except RuntimeError:
        pytest.skip("FFmpeg non installé")
    path = tmp_path / "voix test.wav"
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(b"\x00\x00" * 8000)
    report = analyzer.analyze(Path(path))
    assert report.metadata["streams"][0]["codec_name"] == "pcm_s16le"
    assert "sans erreur" in report.integrity
