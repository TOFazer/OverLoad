from __future__ import annotations

import json
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)


def _make_app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def test_desktop_window_renders_tasks_history_and_settings(server, tmp_path):
    from overload.downloads.manager import DownloadManager
    from overload.history.store import DownloadHistoryStore
    from overload.settings.store import SettingsStore
    from overload.ui.desktop import create_main_window

    app = _make_app()
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
        win.refresh_all()
        app.processEvents()

        # La tâche apparaît dans une carte et l'historique est rafraîchi.
        assert snap.id in win._cards
        assert win._cards[snap.id].name.text() == snap.filename

        win.go_to("downloads")
        app.processEvents()
        assert win.stack.currentWidget() is win._pages["downloads"]

        win.go_to("settings")
        app.processEvents()
        assert win.stack.currentWidget() is win._pages["settings"]

        win.close()


def test_desktop_navigation_and_theme_switch(tmp_path):
    from overload.downloads.manager import DownloadManager
    from overload.history.store import DownloadHistoryStore
    from overload.settings.store import SettingsStore
    from overload.ui.desktop import create_main_window
    from overload.ui.theme import palette

    app = _make_app()
    settings_store = SettingsStore(tmp_path / "settings.json")
    with (
        DownloadHistoryStore(tmp_path / "library.db") as history,
        DownloadManager(tmp_path / "downloads", history=history) as manager,
    ):
        win = create_main_window(manager, history, settings_store, data_dir=tmp_path)
        win.show()
        app.processEvents()

        assert set(win._pages) == {
            "home",
            "downloads",
            "library",
            "creators",
            "history",
            "settings",
            "help",
        }
        win.go_to("home")
        app.processEvents()
        assert win.stack.currentWidget() is win._pages["home"]

        win.toggle_theme()
        app.processEvents()
        assert settings_store.get().theme == "light"
        assert win.tokens.text == palette("light", "forest").text

        win.set_appearance(accent="blue", ui_scale="large")
        app.processEvents()
        prefs = settings_store.get()
        assert prefs.accent == "blue"
        assert prefs.ui_scale == "large"
        assert win.tokens.accent_key == "blue"

        win.toggle_theme()
        app.processEvents()
        assert settings_store.get().theme == "dark"

        # Les cartes existantes sont re-thémées sans être recréées.
        win.close()


def test_desktop_download_from_composer_updates_ui(server, tmp_path):
    from overload.downloads.manager import DownloadManager
    from overload.history.store import DownloadHistoryStore
    from overload.settings.store import SettingsStore
    from overload.ui.desktop import create_main_window

    app = _make_app()
    settings_store = SettingsStore(tmp_path / "settings.json")
    with (
        DownloadHistoryStore(tmp_path / "library.db") as history,
        DownloadManager(
            tmp_path / "downloads", history=history, allow_private_hosts=True
        ) as manager,
    ):
        win = create_main_window(manager, history, settings_store, data_dir=tmp_path)
        win.show()
        app.processEvents()

        win.url_edit.setText(f"{server}/ok.bin")
        app.processEvents()
        win.download_from_composer()
        app.processEvents()

        assert win.url_edit.text() == ""
        assert len(manager.list_tasks()) == 1
        assert manager.wait_all(timeout=10)
        win.refresh_all()
        app.processEvents()
        win.close()


def test_desktop_failure_is_explained_in_french(tmp_path):
    from overload.downloads.manager import DownloadManager
    from overload.history.store import DownloadHistoryStore
    from overload.settings.store import SettingsStore
    from overload.ui.components import DownloadCard
    from overload.ui.desktop import create_main_window

    app = _make_app()
    settings_store = SettingsStore(tmp_path / "settings.json")
    with (
        DownloadHistoryStore(tmp_path / "library.db") as history,
        DownloadManager(tmp_path / "downloads", history=history) as manager,
    ):
        manager._allow_private_hosts = False
        win = create_main_window(manager, history, settings_store, data_dir=tmp_path)
        win.show()
        app.processEvents()

        snap = manager.enqueue("https://exemple.invalid/video.mp4")
        assert snap is not None
        assert manager.wait_all(timeout=20)
        win.refresh_all()
        app.processEvents()

        card = win._cards[snap.id]
        assert isinstance(card, DownloadCard)
        assert not card.failure.isHidden()
        assert "Échec" not in card.failure.title.text()
        assert card.failure._info is not None
        assert card.failure._info.action
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
    app = _make_app()
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


def test_desktop_v2_navigation_library_and_creators_hub(tmp_path):
    import time

    from overload.downloads.manager import DownloadManager
    from overload.history.store import DownloadHistoryStore
    from overload.settings.store import SettingsStore
    from overload.ui.desktop import create_main_window

    app = _make_app()
    settings_store = SettingsStore(tmp_path / "settings.json")
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    (downloads / "clip-bibliotheque.mp4").write_bytes(b"x" * 2048)
    (downloads / "piste-audio.mp3").write_bytes(b"x" * 512)
    with (
        DownloadHistoryStore(tmp_path / "library.db") as history,
        DownloadManager(downloads, history=history) as manager,
    ):
        win = create_main_window(manager, history, settings_store, data_dir=tmp_path)
        win.show()
        app.processEvents()

        # Toutes les pages v2.0 sont atteignables, historique et aide comprises.
        for key in ("downloads", "library", "creators", "history", "settings", "help", "home"):
            win.go_to(key)
            app.processEvents()
            assert win.stack.currentWidget() is win._pages[key]

        # L'ancien accès « analyzer » atterrit dans l'espace Créateurs.
        win.go_to("analyzer")
        app.processEvents()
        assert win._current_page == "creators"
        tabs = win.creators_widget.tabs
        assert tabs.tabText(tabs.currentIndex()) == "Analyse"

        # Le hub des créateurs bascule sur l'outil demandé.
        win.creators_widget.show_tool("tracks")
        app.processEvents()
        assert "Sous-titres" in win.creators_widget.tabs.tabText(
            win.creators_widget.tabs.currentIndex()
        )

        # La bibliothèque indexe les fichiers locaux du dossier de destination.
        win.go_to("library")
        deadline = time.monotonic() + 5
        while len(win._library_rows) < 2 and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.02)
        names = {row.item.name for row in win._library_rows}
        assert names == {"clip-bibliotheque.mp4", "piste-audio.mp3"}

        # Le filtre par type ne montre que la vidéo.
        win.library_filters.set_value("video", emit=True)
        app.processEvents()
        assert [row.item.name for row in win._library_rows] == ["clip-bibliotheque.mp4"]

        # « Analyser » depuis la bibliothèque préremplit l'analyse des Créateurs.
        win.analyze_path(downloads / "clip-bibliotheque.mp4")
        app.processEvents()
        assert win._current_page == "creators"
        analyzer_path = win.creators_widget.analyzer.findChild(
            QtWidgets.QLineEdit, "analyzerPath"
        )
        assert analyzer_path.text().endswith("clip-bibliotheque.mp4")
        win.close()
