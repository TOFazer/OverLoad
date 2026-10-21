from pathlib import Path

from overload.library.preview import preview_info


def test_preview_info_image(tmp_path):
    f = tmp_path / "photo.jpg"
    f.write_bytes(b"not a real jpg but we test fallback")
    # Même sans Pillow/ffprobe, preview_info doit retourner des infos de base sans planter
    info = preview_info(f)
    assert info["filename"] == "photo.jpg"
    assert "size" in info
    assert "mtime_human" in info


def test_preview_info_nonexistent_raises():
    import pytest

    from overload.core.errors import OverloadError

    # .part ignoré -> OverloadError
    p = Path("/tmp/nonexistent_overload_xyz.mp4.part")
    with pytest.raises(OverloadError):
        preview_info(p)
