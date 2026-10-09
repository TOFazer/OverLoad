import time

import pytest

from overload.core.settings import Settings, load_settings
from overload.downloads.manager import DownloadManager
from overload.downloads.state import TaskState
from tests.conftest import PAYLOAD


@pytest.fixture
def window_factory(qapp, tmp_path):
    created = []

    def make(download_dir=None, allow_private=False):
        from overload.app.main_window import MainWindow

        folder = download_dir or (tmp_path / "dl")
        settings = Settings(download_dir=str(folder))
        manager = DownloadManager(max_workers=2, allow_private_hosts=allow_private)
        window = MainWindow(settings, tmp_path / "settings.json", manager)
        created.append((window, manager))
        return window

    yield make
    for window, manager in created:
        window._timer.stop()
        manager.shutdown()
        window.deleteLater()


def test_window_has_four_sections_and_opens_on_saved_section(window_factory):
    window = window_factory()
    assert window.stack.count() == 4
    assert window.nav.count() == 4
    assert window.nav.currentRow() == 0  # accueil par défaut


def test_empty_url_shows_clear_message_and_creates_no_task(window_factory):
    window = window_factory()
    window.home.url_input.setText("   ")
    window.home.download_button.click()
    assert "collez une adresse" in window.home.message.text().lower()
    assert window._manager.snapshot() == []


def test_local_address_is_refused_in_interface(window_factory, tmp_path):
    window = window_factory()
    window.home.url_input.setText("http://127.0.0.1:9/ok.bin")
    window.home.download_button.click()
    assert window.home.message.text().startswith("Erreur :")
    assert "locale" in window.home.message.text()
    assert window._manager.snapshot() == []
    assert window.home.url_input.text() == "http://127.0.0.1:9/ok.bin"  # non effacée


def test_download_from_interface_completes_and_lists_task(window_factory, server, tmp_path):
    window = window_factory(allow_private=True, download_dir=tmp_path / "dl")
    window.home.url_input.setText(f"{server}/ok.bin")
    window.home.download_button.click()
    assert window.home.message.text().startswith("Téléchargement ajouté")
    assert window.home.url_input.text() == ""
    end = time.monotonic() + 10
    while time.monotonic() < end:
        window.refresh()
        views = window._manager.snapshot()
        if views and views[0].state is TaskState.COMPLETED:
            break
        qapp_process(window)
    view = window._manager.snapshot()[0]
    assert view.state is TaskState.COMPLETED
    assert view.result_path.read_bytes() == PAYLOAD
    assert window.downloads.table.rowCount() == 1
    assert window.downloads.table.item(0, 2).text() == "Terminé"


def qapp_process(window):
    from PySide6.QtWidgets import QApplication

    QApplication.processEvents()
    time.sleep(0.02)


def test_action_buttons_follow_task_state(window_factory, server, tmp_path):
    window = window_factory(allow_private=True, download_dir=tmp_path / "dl")
    task_id = window._manager.submit(f"{server}/ok.bin", tmp_path / "dl")
    end = time.monotonic() + 10
    while window._manager.get(task_id).state is not TaskState.COMPLETED and time.monotonic() < end:
        time.sleep(0.02)
    window.refresh()
    window.downloads.table.selectRow(0)
    buttons = window.downloads._buttons
    assert buttons["open_file"].isEnabled()
    assert not buttons["cancel"].isEnabled()
    assert not buttons["retry"].isEnabled()


def test_settings_save_persists_and_applies_folder(window_factory, tmp_path):
    window = window_factory()
    new_folder = tmp_path / "nouveau"
    window.settings_page.folder.setText(str(new_folder))
    window.settings_page.parallel.setValue(3)
    window.settings_page._save()
    assert new_folder.is_dir()
    saved = load_settings(tmp_path / "settings.json")
    assert saved.download_dir == str(new_folder)
    assert saved.max_parallel == 3
    assert window.settings.download_dir == str(new_folder)


def test_settings_refuse_unwritable_folder_with_message(window_factory, tmp_path):
    window = window_factory()
    blocker = tmp_path / "fichier"
    blocker.write_text("pas un dossier", encoding="utf-8")
    window.settings_page.folder.setText(str(blocker / "sous-dossier"))
    window.settings_page._save()
    assert window.settings_page.message.text().startswith("Erreur")
    assert not (blocker / "sous-dossier").exists()
