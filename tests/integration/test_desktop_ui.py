from __future__ import annotations

import json
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)


def test_desktop_window_renders_tasks_history_and_settings(server, tmp_path):
    from overload.downloads.manager import DownloadManager
    from overload.history.store import DownloadHistoryStore
    from overload.settings.store import SettingsStore
    from overload.ui.desktop import create_main_window

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    settings_store = SettingsStore(tmp_path / "settings.json")
    with (
        DownloadHistoryStore(tmp_path / "library.db") as history,
        DownloadManager(
            tmp_path / "downloads",
            history=history,
            allow_private_hosts=True,
        ) as manager,
    ):
        win = create_main_window(manager, history, settings_store, data_dir=tmp_path)
        win.show()
        app.processEvents()

        snap = manager.enqueue(f"{server}/ok.bin")
        assert snap is not None
        assert manager.wait_all(timeout=10)

        app.processEvents()
        win.close()


def test_exe_entry_self_test_mode(tmp_path):
    from overload.exe_entry import main as exe_main

    report = tmp_path / "selftest.json"
    code = exe_main(["--self-test", "--self-test-out", str(report)])
    assert code == 0
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["status"] == "ok"


def test_analyzer_widget_background_result(tmp_path, monkeypatch):
    import time

    from overload.media.analyzer import Report
    from overload.ui import analyzer

    sample = tmp_path / "film.mp4"
    sample.write_bytes(b"test")
    monkeypatch.setattr(
        analyzer,
        "analyze",
        lambda path, deep: Report(
            path,
            {
                "streams": [
                    {
                        "index": 0,
                        "codec_type": "video",
                        "codec_name": "h264",
                        "width": 1920,
                        "height": 1080,
                        "avg_frame_rate": "25/1",
                    }
                ]
            },
            "Lecture test terminée",
        ),
    )
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    widget = analyzer.create_analyzer_widget()
    widget.findChild(QtWidgets.QLineEdit, "analyzerPath").setText(str(sample))
    button = widget.findChild(QtWidgets.QPushButton, "analyzerStart")
    button.click()
    assert not button.isEnabled()
    deadline = time.monotonic() + 5
    while not button.isEnabled() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert button.isEnabled()
    text = widget.findChild(QtWidgets.QPlainTextEdit, "analyzerOutput").toPlainText()
    assert "1920 × 1080" in text
    assert "25.000" in text
    assert "h264" in text
    widget.close()
