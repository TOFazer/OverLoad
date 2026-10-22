"""Le build direct doit préparer ses dépendances sans compter sur le workflow CI."""

from __future__ import annotations

import importlib.util
import sys
import tomllib
from pathlib import Path
from types import SimpleNamespace

import pytest

from overload import __version__

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "build_windows.py"
spec = importlib.util.spec_from_file_location("windows_build", SCRIPT)
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


def test_existing_tools_do_not_download(tmp_path, monkeypatch):
    monkeypatch.setattr(build, "ROOT", tmp_path)
    tools = tmp_path / "tools"
    tools.mkdir()
    for name in ("ffmpeg.exe", "ffprobe.exe"):
        (tools / name).touch()
    monkeypatch.setitem(sys.modules, "prepare_ffmpeg", None)
    build.ensure_media_tools()


def test_missing_tools_are_prepared(tmp_path, monkeypatch):
    monkeypatch.setattr(build, "ROOT", tmp_path)
    calls = []

    def prepare():
        calls.append(True)
        tools = tmp_path / "tools"
        tools.mkdir()
        for name in ("ffmpeg.exe", "ffprobe.exe"):
            (tools / name).touch()

    monkeypatch.setitem(sys.modules, "prepare_ffmpeg", SimpleNamespace(prepare=prepare))
    monkeypatch.syspath_prepend(str(tmp_path))
    build.ensure_media_tools()
    assert calls == [True]


def test_incomplete_preparation_fails_early(tmp_path, monkeypatch):
    monkeypatch.setattr(build, "ROOT", tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setitem(sys.modules, "prepare_ffmpeg", SimpleNamespace(prepare=lambda: None))
    with pytest.raises(RuntimeError, match="ffmpeg.exe"):
        build.ensure_media_tools()


def test_release_version_is_synchronised_everywhere():
    """Le paquet, le pyproject et l'installateur Inno Setup doivent partager
    la même version, sinon l'exécutable et la release publiée divergent."""
    root = SCRIPT.parents[1]
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    installer = (root / "packaging" / "OverLoad.iss").read_text(encoding="utf-8")
    assert pyproject["project"]["version"] == __version__
    assert f'#define MyAppVersion "{__version__}"' in installer


def test_redesigned_ui_modules_are_bundled():
    """L'interface native est importée dynamiquement : PyInstaller doit la voir."""
    for module in (
        "overload.ui.window",
        "overload.ui.components",
        "overload.ui.icons",
        "overload.ui.failure_text",
        "overload.ui.theme",
    ):
        assert module in build.HIDDEN_IMPORTS
    spec = (SCRIPT.parents[1] / "OverLoad.spec").read_text(encoding="utf-8")
    assert '"overload.ui.window"' in spec
    assert '"overload.ui.icons"' in spec


def test_youtube_extractor_is_bundled_in_the_exe():
    """yt-dlp doit être collecté en entier : il charge ses extracteurs à l'exécution."""
    assert "overload.downloads.youtube" in build.HIDDEN_IMPORTS
    assert "yt_dlp" in build.HIDDEN_IMPORTS
    source = SCRIPT.read_text(encoding="utf-8")
    assert '"--collect-submodules", "yt_dlp"' in source
    spec = (SCRIPT.parents[1] / "OverLoad.spec").read_text(encoding="utf-8")
    assert '"overload.downloads.youtube"' in spec
    assert 'collect_submodules("yt_dlp")' in spec
