import time
from pathlib import Path

from overload.library.models import MediaEntry, MediaType
from overload.library.organizer import (
    OrganizerConfig,
    destination_for,
    ensure_unique_destination,
    organize_file,
)


def _e(name, media_type, mtime=None):
    mtime = mtime or time.time()
    return MediaEntry(
        path=Path(name),
        filename=Path(name).name,
        media_type=media_type,
        extension=Path(name).suffix.lower(),
        size=1000,
        mtime=mtime,
    )


def test_classify_by_type(tmp_path):
    cfg = OrganizerConfig(base_directory=str(tmp_path), date_template="")
    e = _e("clip.mp4", MediaType.VIDEO)
    dest = destination_for(e, cfg, root=tmp_path)
    assert "Vidéos" in str(dest)
    assert dest.name == "clip.mp4"


def test_classify_by_extension_override(tmp_path):
    cfg = OrganizerConfig(
        base_directory=str(tmp_path),
        date_template="",
        extension_overrides={".mp3": "Musiques/Podcasts"},
    )
    e = _e("song.mp3", MediaType.AUDIO)
    dest = destination_for(e, cfg, root=tmp_path)
    assert "Podcasts" in str(dest)


def test_classify_by_date(tmp_path):
    # 15 mars 2024
    import datetime

    dt = datetime.datetime(2024, 3, 15, 10, 0, 0)
    cfg = OrganizerConfig(base_directory=str(tmp_path), date_template="%Y/%m")
    e = _e("photo.jpg", MediaType.IMAGE, mtime=dt.timestamp())
    dest = destination_for(e, cfg, root=tmp_path)
    assert "2024" in str(dest)
    assert "03" in str(dest)
    assert "Images" in str(dest)


def test_organizer_custom_folders(tmp_path):
    cfg = OrganizerConfig(
        base_directory=str(tmp_path / "triage"),
        folders={"video": "MesVidéos", "audio": "MaZik", "image": "Pix", "other": "Divers"},
        date_template="",
    )
    e = _e("doc.pdf", MediaType.OTHER)
    dest = destination_for(e, cfg)
    assert "Divers" in str(dest)
    # Le dossier custom est respecté
    assert dest.parent.name == "Divers"


def test_ensure_unique_never_overwrites(tmp_path):
    dest = tmp_path / "clip.mp4"
    dest.write_bytes(b"original")
    unique = ensure_unique_destination(dest)
    assert unique.name == "clip (2).mp4"
    unique.write_bytes(b"second")
    assert dest.read_bytes() == b"original"


def test_organize_moves_file(tmp_path):
    src = tmp_path / "source" / "video.mp4"
    src.parent.mkdir(parents=True)
    src.write_bytes(b"content")
    cfg = OrganizerConfig(base_directory=str(tmp_path / "dest"), date_template="")
    result = organize_file(src, cfg, move=True)
    assert result.exists()
    assert not src.exists()
    assert result.read_bytes() == b"content"
    assert "Vidéos" in str(result)


def test_organize_never_overwrites_destination(tmp_path):
    src = tmp_path / "video.mp4"
    src.write_bytes(b"new")
    cfg = OrganizerConfig(base_directory=str(tmp_path / "out"), date_template="")
    # Pré-créer la destination
    dest_dir = tmp_path / "out" / "Vidéos"
    dest_dir.mkdir(parents=True)
    (dest_dir / "video.mp4").write_bytes(b"old")
    result = organize_file(src, cfg, move=True)
    assert result.name == "video (2).mp4"
    assert (dest_dir / "video.mp4").read_bytes() == b"old"


def test_preview_organize(tmp_path):
    from overload.library.organizer import preview_organize

    cfg = OrganizerConfig(base_directory=str(tmp_path), date_template="")
    entries = [_e("a.mp4", MediaType.VIDEO), _e("b.jpg", MediaType.IMAGE)]
    preview = preview_organize(entries, cfg, root=tmp_path)
    assert len(preview) == 2
    for e, dest in preview:
        assert dest.name == e.filename
