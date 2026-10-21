import time
from pathlib import Path

from overload.library.models import MediaEntry, MediaType
from overload.library.thumbnails import is_thumbnail_fresh, thumbnail_path_for


def test_thumbnail_path_deterministic(tmp_path):
    e = MediaEntry(Path("video.mp4"), "video.mp4", MediaType.VIDEO, ".mp4", 1000, time.time())
    t1 = thumbnail_path_for(e, tmp_path)
    t2 = thumbnail_path_for(e, tmp_path)
    assert t1 == t2
    assert t1.suffix == ".jpg"


def test_is_thumbnail_fresh(tmp_path):
    now = time.time()
    e = MediaEntry(Path("a.mp4"), "a.mp4", MediaType.VIDEO, ".mp4", 100, now - 100)
    thumb = tmp_path / "thumb.jpg"
    thumb.write_bytes(b"fake")
    # thumb plus récent que source -> fresh
    import os

    os.utime(thumb, (now, now))
    assert is_thumbnail_fresh(thumb, e) is True
    # source plus récente -> pas fresh
    e2 = MediaEntry(Path("a.mp4"), "a.mp4", MediaType.VIDEO, ".mp4", 100, now + 100)
    assert is_thumbnail_fresh(thumb, e2) is False


def test_generate_thumbnail_without_pillow_graceful(tmp_path):
    """Doit ne jamais lever, même sans Pillow/ffmpeg."""
    from overload.library.thumbnails import generate_thumbnail

    f = tmp_path / "audio.mp3"
    f.write_bytes(b"fake audio")
    e = MediaEntry(f.resolve(), "audio.mp3", MediaType.AUDIO, ".mp3", 10, time.time())
    thumb = tmp_path / "thumbs" / "t.jpg"
    # Peut retourner None ou un chemin, mais pas d'exception
    result = generate_thumbnail(e, thumb)
    assert result is None or isinstance(result, Path)
