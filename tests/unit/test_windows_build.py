"""Le build direct doit préparer ses dépendances sans compter sur le workflow CI."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

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
