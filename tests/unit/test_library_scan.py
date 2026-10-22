"""Tests de la bibliothèque locale : classement, analyse de dossier, filtres."""

from __future__ import annotations

import os

import pytest

from overload.core.errors import OverloadError
from overload.library.scan import classify, filter_files, scan_library


def test_classify_covers_media_kinds():
    assert classify("clip.MP4") == "video"
    assert classify("film.mkv") == "video"
    assert classify("musique.flac") == "audio"
    assert classify("photo.jpg") == "image"
    assert classify("film.srt") == "subtitle"
    assert classify("projet.zip") == "archive"
    assert classify("notes.pdf") == "file"
    assert classify("sans_extension") == "file"


def test_scan_library_indexes_real_files_and_ignores_partials(tmp_path):
    (tmp_path / "a.mp4").write_bytes(b"1234")
    (tmp_path / "b.mp3").write_bytes(b"123456")
    (tmp_path / "en-cours.mp4.part").write_bytes(b"12")  # partiel : ignoré
    (tmp_path / ".cache.mp4").write_bytes(b"12")  # caché : ignoré
    sub = tmp_path / "rushs"
    sub.mkdir()
    (sub / "c.mov").write_bytes(b"12345678")

    scan = scan_library(tmp_path)
    names = {item.name for item in scan.files}
    assert names == {"a.mp4", "b.mp3", "c.mov"}
    assert scan.total_size == 4 + 6 + 8
    assert scan.counts() == {"video": 2, "audio": 1}
    assert scan.truncated is False
    # Tri par défaut du scan : plus récents d'abord.
    mtimes = [item.modified_at for item in scan.files]
    assert mtimes == sorted(mtimes, reverse=True)

    flat = scan_library(tmp_path, recursive=False)
    assert {item.name for item in flat.files} == {"a.mp4", "b.mp3"}


def test_scan_library_limit_marks_truncated(tmp_path):
    for index in range(5):
        (tmp_path / f"f{index}.mp4").write_bytes(b"x")
    scan = scan_library(tmp_path, limit=3)
    assert len(scan.files) == 3
    assert scan.truncated is True


def test_scan_library_missing_folder_is_explained(tmp_path):
    with pytest.raises(OverloadError):
        scan_library(tmp_path / "disparu")


def test_filter_files_by_kind_query_and_sort(tmp_path):
    video = tmp_path / "Vacances.mp4"
    video.write_bytes(b"x" * 10)
    audio = tmp_path / "interview.wav"
    audio.write_bytes(b"x" * 50)
    other = tmp_path / "budget.txt"
    other.write_bytes(b"x")
    os.utime(video, (1000, 1000))
    os.utime(audio, (2000, 2000))
    os.utime(other, (500, 500))

    files = scan_library(tmp_path).files
    assert [f.name for f in filter_files(files, kind="video")] == ["Vacances.mp4"]
    assert [f.name for f in filter_files(files, query="VACAN")] == ["Vacances.mp4"]
    assert [f.name for f in filter_files(files, sort="recent")][0] == "interview.wav"
    assert [f.name for f in filter_files(files, sort="size")][0] == "interview.wav"
    assert [f.name for f in filter_files(files, sort="name")] == [
        "budget.txt",
        "interview.wav",
        "Vacances.mp4",
    ]
