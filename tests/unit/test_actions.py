from pathlib import Path

import pytest

from overload.core.errors import OverloadError
from overload.downloads import actions


def test_dangerous_extensions_are_detected_case_insensitively():
    assert actions.is_dangerous(Path("setup.EXE"))
    assert actions.is_dangerous(Path("script.ps1"))
    assert actions.is_dangerous(Path("installer.msi"))
    assert not actions.is_dangerous(Path("video.mp4"))


def test_open_refuses_executables_without_launching(tmp_path, monkeypatch):
    target = tmp_path / "virus.exe"
    target.write_bytes(b"MZ")
    launched = []
    monkeypatch.setattr(actions, "_open_with_default_app", lambda p: launched.append(p))
    with pytest.raises(OverloadError, match="n'ouvre pas"):
        actions.open_file(target, tmp_path)
    assert launched == []


def test_open_refuses_file_outside_download_folder(tmp_path, monkeypatch):
    outside = tmp_path / "other" / "video.mp4"
    outside.parent.mkdir()
    outside.write_bytes(b"x")
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    launched = []
    monkeypatch.setattr(actions, "_open_with_default_app", lambda p: launched.append(p))
    with pytest.raises(OverloadError, match="pas dans le dossier"):
        actions.open_file(outside, downloads)
    assert launched == []


def test_open_regular_file_inside_folder_launches_it(tmp_path, monkeypatch):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"x")
    launched = []
    monkeypatch.setattr(actions, "_open_with_default_app", lambda p: launched.append(p))
    actions.open_file(video, tmp_path)
    assert launched == [video]


def test_open_missing_file_is_readable_error(tmp_path):
    with pytest.raises(OverloadError, match="n'existe plus"):
        actions.open_file(tmp_path / "gone.mp4", tmp_path)


def test_open_folder_missing_is_readable_error(tmp_path):
    with pytest.raises(OverloadError, match="introuvable"):
        actions.open_folder(tmp_path / "absent")
