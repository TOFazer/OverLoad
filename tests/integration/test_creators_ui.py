from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)


def _make_app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _patch_dialogs(monkeypatch):
    """Neutralise les boîtes de dialogue bloquantes pour les tests automatisés."""
    monkeypatch.setattr(
        QtWidgets.QMessageBox,
        "information",
        staticmethod(lambda *a, **k: QtWidgets.QMessageBox.StandardButton.Ok),
    )
    monkeypatch.setattr(
        QtWidgets.QMessageBox,
        "warning",
        staticmethod(lambda *a, **k: QtWidgets.QMessageBox.StandardButton.Ok),
    )
    monkeypatch.setattr(
        QtWidgets.QMessageBox,
        "question",
        staticmethod(
            lambda *a, **k: QtWidgets.QMessageBox.StandardButton.Yes
        ),
    )


def test_creators_widget_has_all_sections(tmp_path):
    from overload.ui.creators import create_creators_widget

    app = _make_app()
    widget = create_creators_widget(data_dir=tmp_path / "data")
    widget.show()
    app.processEvents()
    tabs = widget.findChild(QtWidgets.QTabWidget, "creatorsTabs")
    assert tabs is not None
    labels = [tabs.tabText(i) for i in range(tabs.count())]
    assert any("Mes projets" in label for label in labels)
    assert any("Préparer mon projet" in label for label in labels)
    assert any("Renommer" in label for label in labels)
    assert any("Sous-titres" in label for label in labels)
    assert any("Inventaire" in label for label in labels)
    assert any("Profils" in label for label in labels)
    widget.close()


def test_create_project_from_form_builds_structure(tmp_path, monkeypatch):
    from overload.ui.creators import create_creators_widget

    _patch_dialogs(monkeypatch)
    app = _make_app()
    widget = create_creators_widget(data_dir=tmp_path / "data")
    widget.show()
    app.processEvents()

    videos = tmp_path / "Videos"
    videos.mkdir()
    widget.findChild(QtWidgets.QLineEdit, "creatorsProjectName").setText("Vlog Test")
    widget.findChild(QtWidgets.QLineEdit, "creatorsProjectParent").setText(str(videos))
    combo = widget.findChild(QtWidgets.QComboBox, "creatorsProjectProfile")
    combo.setCurrentIndex(combo.findData("premiere"))
    widget.findChild(QtWidgets.QPushButton, "creatorsProjectCreate").click()
    app.processEvents()

    root = videos / "Vlog Test"
    assert root.is_dir()
    assert (root / "01_Rushes").is_dir()
    assert (root / "04_Sous-titres").is_dir()
    assert (root / "LISEZ-MOI.txt").is_file()
    assert (root / "overload-projet.json").is_file()

    from overload.creators.workspace import CreatorsWorkspace

    workspace = CreatorsWorkspace(tmp_path / "data")
    projects = workspace.projects.list_projects()
    assert len(projects) == 1
    assert projects[0].name == "Vlog Test"
    assert projects[0].profile_id == "premiere"
    widget.close()


def test_prepare_project_plans_and_copies_without_touching_originals(tmp_path, monkeypatch):
    from overload.ui.creators import create_creators_widget

    _patch_dialogs(monkeypatch)
    app = _make_app()
    widget = create_creators_widget(data_dir=tmp_path / "data")
    widget.show()
    app.processEvents()

    tabs = widget.findChild(QtWidgets.QTabWidget, "creatorsTabs")
    tabs.setCurrentIndex(1)
    app.processEvents()

    sources = tmp_path / "originaux"
    sources.mkdir()
    (sources / "rush.mp4").write_text("video")
    (sources / "musique.wav").write_text("audio")
    dest = tmp_path / "projet"

    sources_edit = widget.findChild(QtWidgets.QPlainTextEdit, "creatorsPrepareSources")
    sources_edit.setPlainText(f"{sources}\n")
    widget.findChild(QtWidgets.QLineEdit, "creatorsPrepareFolder").setText(str(dest))

    import time

    widget.findChild(QtWidgets.QPushButton, "creatorsPreparePlan").click()
    preview = widget.findChild(QtWidgets.QPlainTextEdit, "creatorsPreparePreview")
    deadline = time.monotonic() + 5
    while "musique.wav" not in preview.toPlainText() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.02)
    assert "musique.wav" in preview.toPlainText()
    assert "rush.mp4" in preview.toPlainText()

    run_btn = widget.findChild(QtWidgets.QPushButton, "creatorsPrepareRun")
    assert run_btn.isEnabled()
    run_btn.click()
    deadline = time.monotonic() + 5
    while not (dest / "02_Audio" / "musique.wav").exists() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.02)

    # Profil « Universel » appliqué à un nouveau dossier : 01_Videos / 02_Audio / …
    assert (dest / "01_Videos" / "rush.mp4").read_text() == "video"
    assert (dest / "02_Audio" / "musique.wav").read_text() == "audio"
    assert (sources / "rush.mp4").read_text() == "video", "l'original reste intact"
    assert (sources / "musique.wav").exists(), "aucun original déplacé"
    widget.close()


def test_rename_page_live_preview_and_apply(tmp_path, monkeypatch):
    from overload.ui.creators import create_creators_widget

    _patch_dialogs(monkeypatch)
    app = _make_app()
    widget = create_creators_widget(data_dir=tmp_path / "data")
    widget.show()
    app.processEvents()

    tabs = widget.findChild(QtWidgets.QTabWidget, "creatorsTabs")
    tabs.setCurrentIndex(2)
    app.processEvents()

    folder = tmp_path / "lots"
    folder.mkdir()
    (folder / "b.mp4").write_text("1")
    (folder / "a.mp4").write_text("2")

    sources_edit = widget.findChild(QtWidgets.QPlainTextEdit, "creatorsRenameSources")
    sources_edit.setPlainText(f"{folder / 'b.mp4'}\n{folder / 'a.mp4'}")
    widget.findChild(QtWidgets.QLineEdit, "creatorsRenameProject").setText("Projet")
    template = widget.findChild(QtWidgets.QLineEdit, "creatorsRenameTemplate")
    template.setText("{projet}_{numero:02}{ext}")

    preview = widget.findChild(QtWidgets.QPlainTextEdit, "creatorsRenamePreview")
    preview_lbl = widget.findChild(QtWidgets.QLabel, "creatorsRenameStatus")
    import time

    deadline = time.monotonic() + 5
    while "Projet_01.mp4" not in preview.toPlainText() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.02)
    assert "Projet_01.mp4" in preview.toPlainText()
    assert "Projet_02.mp4" in preview.toPlainText()
    assert sorted(p.name for p in folder.iterdir()) == ["a.mp4", "b.mp4"], "aperçu sans effet"

    widget.findChild(QtWidgets.QPushButton, "creatorsRenameApply").click()
    deadline = time.monotonic() + 5
    while "renommé(s)" not in preview_lbl.text() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.02)
    assert sorted(p.name for p in folder.iterdir()) == ["Projet_01.mp4", "Projet_02.mp4"]
    assert (folder / "Projet_01.mp4").read_text() == "1"
    assert "2 fichier(s) renommé(s)" in preview_lbl.text()
    widget.close()


def test_inventory_page_scans_and_exports_csv(tmp_path, monkeypatch):
    from overload.ui.creators import create_creators_widget

    _patch_dialogs(monkeypatch)
    monkeypatch.setattr(
        "PySide6.QtWidgets.QFileDialog.getSaveFileName",
        staticmethod(lambda *a, **k: (str(tmp_path / "inventaire.csv"), "CSV (*.csv)")),
    )
    app = _make_app()
    widget = create_creators_widget(data_dir=tmp_path / "data")
    widget.show()
    app.processEvents()

    tabs = widget.findChild(QtWidgets.QTabWidget, "creatorsTabs")
    tabs.setCurrentIndex(4)
    app.processEvents()

    folder = tmp_path / "medias"
    folder.mkdir()
    (folder / "clip.mp4").write_bytes(b"x" * 10)
    (folder / "son.wav").write_bytes(b"y" * 5)

    widget.findChild(QtWidgets.QLineEdit, "creatorsInventoryFolder").setText(str(folder))
    widget.findChild(QtWidgets.QPushButton, "creatorsInventoryScan").click()

    table = widget.findChild(QtWidgets.QTableWidget, "creatorsInventoryTable")
    export_btn = widget.findChild(QtWidgets.QPushButton, "creatorsInventoryExport")
    open_export_btn = widget.findChild(QtWidgets.QPushButton, "creatorsInventoryOpenExport")
    import time

    deadline = time.monotonic() + 10
    while not export_btn.isEnabled() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.02)
    assert export_btn.isEnabled()
    assert table.rowCount() == 2

    export_btn.click()
    csv_file = tmp_path / "inventaire.csv"
    # Attend la fin complète du travail d'arrière-plan (le bouton s'active en dernier).
    deadline = time.monotonic() + 5
    while not open_export_btn.isEnabled() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.02)
    assert open_export_btn.isEnabled()
    content = csv_file.read_text(encoding="utf-8-sig")
    assert "clip.mp4" in content and "son.wav" in content
    assert "Codec vidéo" in content
    widget.close()


def test_profiles_page_creates_custom_profile(tmp_path, monkeypatch):
    from overload.ui.creators import create_creators_widget

    _patch_dialogs(monkeypatch)
    app = _make_app()
    widget = create_creators_widget(data_dir=tmp_path / "data")
    widget.show()
    app.processEvents()

    tabs = widget.findChild(QtWidgets.QTabWidget, "creatorsTabs")
    tabs.setCurrentIndex(5)
    app.processEvents()

    widget.findChild(QtWidgets.QLineEdit, "creatorsProfileName").setText("Mon studio")
    widget.findChild(QtWidgets.QLineEdit, "creatorsProfile_video_folder").setText("Rushs")
    widget.findChild(QtWidgets.QLineEdit, "creatorsProfileContainer").setText("MP4")
    widget.findChild(QtWidgets.QPushButton, "creatorsProfileSave").click()
    app.processEvents()

    from overload.creators.workspace import CreatorsWorkspace

    workspace = CreatorsWorkspace(tmp_path / "data")
    profile = workspace.profiles.get("mon-studio")
    assert profile.video_folder == "Rushs"
    assert profile.recommended_container == "MP4"
    assert profile.builtin is False
    widget.close()
