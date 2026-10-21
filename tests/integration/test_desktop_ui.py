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
        win = create_main_window(manager, history, settings_store)
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
