from __future__ import annotations

from pathlib import Path

import pytest

from overload.core.errors import OverloadError
from overload.creators.models import MediaKind, MediaScan
from overload.creators.scan import (
    INVENTORY_COLUMNS,
    export_inventory_csv,
    probe_metadata,
    scan_file,
    scan_tree,
)

FFPROBE_SAMPLE = {
    "format": {
        "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
        "duration": "42.25",
        "bit_rate": "8500000",
    },
    "streams": [
        {
            "index": 0,
            "codec_type": "video",
            "codec_name": "h264",
            "width": 3840,
            "height": 2160,
            "avg_frame_rate": "30000/1001",
        },
        {"index": 1, "codec_type": "audio", "codec_name": "aac"},
        {"index": 2, "codec_type": "subtitle", "codec_name": "subrip"},
    ],
}


@pytest.fixture()
def media_tree(tmp_path):
    folder = tmp_path / "medias"
    (folder / "rushs").mkdir(parents=True)
    (folder / "rushs" / "rush 4K.mp4").write_bytes(b"x" * 1000)
    (folder / "voix off.wav").write_bytes(b"y" * 500)
    (folder / "banniere.png").write_bytes(b"z" * 100)
    (folder / "notes.txt").write_bytes(b"n")
    return folder


def test_scan_tree_without_probe_inventories_all_media(media_tree):
    rows = scan_tree(media_tree, probe=False)
    by_name = {row.path.name: row for row in rows}
    assert set(by_name) == {"rush 4K.mp4", "voix off.wav", "banniere.png", "notes.txt"}
    assert by_name["rush 4K.mp4"].kind.label == "Vidéo"
    assert by_name["voix off.wav"].kind.label == "Audio"
    assert by_name["banniere.png"].kind.label == "Image"
    assert by_name["rush 4K.mp4"].size_bytes == 1000
    assert by_name["rush 4K.mp4"].modified_at, "date de modification relevée"


def test_scan_tree_non_recursive(media_tree):
    rows = scan_tree(media_tree, recursive=False, probe=False)
    assert {row.path.name for row in rows} == {"voix off.wav", "banniere.png", "notes.txt"}


def test_scan_tree_rejects_missing_folder(tmp_path):
    with pytest.raises(OverloadError, match="Dossier introuvable"):
        scan_tree(tmp_path / "absent", probe=False)


def test_scan_tree_reports_progress(media_tree):
    events = []
    scan_tree(
        media_tree,
        probe=False,
        progress=lambda done, total, name: events.append((done, total, name)),
    )
    assert events
    assert events[-1][0] == events[-1][1] == 4


def test_scan_file_enriches_with_ffprobe_metadata(tmp_path, monkeypatch):
    media = tmp_path / "film.mp4"
    media.write_bytes(b"data")
    monkeypatch.setattr(
        "overload.creators.scan.probe_metadata",
        lambda path, timeout=60: FFPROBE_SAMPLE,
    )
    row = scan_file(media)
    assert row.container.startswith("mov")
    assert row.duration_seconds == pytest.approx(42.25)
    assert row.video_codec == "h264"
    assert row.audio_codec == "aac"
    assert row.resolution == "3840×2160"
    assert row.fps == pytest.approx(29.97, rel=1e-3)
    assert row.video_tracks == 1 and row.audio_tracks == 1 and row.subtitle_tracks == 1
    assert row.bitrate_bps == 8_500_000
    assert row.probe_error == ""
    assert row.duration_human() == "00:42.250"


def test_scan_file_falls_back_gracefully_without_ffprobe(tmp_path, monkeypatch):
    media = tmp_path / "film.mp4"
    media.write_bytes(b"data")
    monkeypatch.setattr("overload.creators.scan.probe_metadata", lambda path, timeout=60: None)
    row = scan_file(media)
    assert row.video_codec == "" and row.resolution == ""
    assert "indisponibles" in row.probe_error
    assert row.duration_human() == "—"


def test_scan_file_maps_download_source(tmp_path):
    media = tmp_path / "film.mp4"
    media.write_bytes(b"data")
    row = scan_file(media, sources={str(media): "https://exemple.com/film.mp4"}, probe=False)
    assert row.source == "https://exemple.com/film.mp4"


def test_probe_metadata_returns_none_on_ffprobe_failure(tmp_path, monkeypatch):
    media = tmp_path / "film.mp4"
    media.write_bytes(b"data")
    monkeypatch.setattr(
        "overload.creators.scan.run_tool", lambda name, args, timeout=60: (1, "", "err")
    )
    assert probe_metadata(media) is None
    monkeypatch.setattr(
        "overload.creators.scan.run_tool",
        lambda name, args, timeout=60: (0, "pas du tout du json", ""),
    )
    assert probe_metadata(media) is None


def test_export_inventory_csv_writes_excel_friendly_file(tmp_path, media_tree):
    rows = scan_tree(media_tree, probe=False)
    out = tmp_path / "inventaire.csv"
    created = export_inventory_csv(rows, out)
    raw = created.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf"), "BOM UTF-8 pour Excel"
    text = raw.decode("utf-8-sig")
    lines = text.splitlines()
    assert lines[0].split(";") == INVENTORY_COLUMNS
    row_line = next(line for line in lines if line.startswith("rush 4K.mp4;"))
    assert "Vidéo" in row_line
    assert "1000" in row_line
    assert "medias" in row_line


def test_export_inventory_csv_escapes_semicolons_and_never_overwrites(tmp_path):
    row = MediaScan(path=Path("a;b.mp4"), kind=MediaKind.VIDEO, size_bytes=10, modified_at="")
    out = tmp_path / "liste.csv"
    out.write_text("ancien contenu")
    created = export_inventory_csv([row], out)
    assert created != out
    assert out.read_text() == "ancien contenu"
    assert '"a;b.mp4"' in created.read_text(encoding="utf-8-sig")


def test_export_inventory_csv_appends_csv_suffix(tmp_path):
    row = MediaScan(path=Path("a.mp4"), kind=MediaKind.VIDEO, size_bytes=1, modified_at="")
    created = export_inventory_csv([row], tmp_path / "liste")
    assert created.suffix == ".csv"
