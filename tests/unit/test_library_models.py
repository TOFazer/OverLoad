from pathlib import Path

from overload.library.models import (
    MediaType,
    human_duration,
    human_size,
    media_type_from_extension,
    media_type_from_path,
)


def test_media_type_from_extension():
    assert media_type_from_extension(".mp4") == MediaType.VIDEO
    assert media_type_from_extension(".MP4") == MediaType.VIDEO
    assert media_type_from_extension(".mp3") == MediaType.AUDIO
    assert media_type_from_extension(".jpg") == MediaType.IMAGE
    assert media_type_from_extension(".png") == MediaType.IMAGE
    assert media_type_from_extension(".txt") == MediaType.OTHER
    assert media_type_from_extension(".unknown") == MediaType.OTHER


def test_media_type_from_path():
    assert media_type_from_path(Path("clip.mkv")) == MediaType.VIDEO
    assert media_type_from_path(Path("song.flac")) == MediaType.AUDIO
    assert media_type_from_path(Path("photo.heic")) == MediaType.IMAGE


def test_human_size():
    assert human_size(500) == "500 o"
    assert "Ko" in human_size(2048)
    assert "Mo" in human_size(5 * 1024 * 1024)
    assert "Go" in human_size(3 * 1024 * 1024 * 1024)


def test_human_duration():
    assert human_duration(45) == "45s"
    assert human_duration(90) == "1m 30s"
    assert human_duration(3723) == "1h 02m 03s"
