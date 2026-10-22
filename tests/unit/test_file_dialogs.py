"""Sélecteurs de fichiers : le dossier de départ ne doit jamais être « n'importe où »."""

import sys
import types

from overload.core.paths import dialog_start_dir
from overload.ui import filedialogs


def test_dialog_start_dir_prefers_existing_directory(tmp_path):
    folder = tmp_path / "medias"
    folder.mkdir()
    assert dialog_start_dir(folder) == folder.resolve()
    assert dialog_start_dir(str(folder)) == folder.resolve()


def test_dialog_start_dir_uses_parent_of_file(tmp_path):
    media = tmp_path / "clip.mp4"
    media.write_bytes(b"ok")
    assert dialog_start_dir(media) == tmp_path.resolve()
    # Fichier pas encore créé (ex. nom déjà saisi) : on ouvre quand même son dossier.
    assert dialog_start_dir(tmp_path / "nouveau.mp4") == tmp_path.resolve()


def test_dialog_start_dir_falls_back_when_preferred_is_unusable(tmp_path):
    fallback = tmp_path / "telechargements"
    fallback.mkdir()
    assert dialog_start_dir("", fallback=fallback) == fallback.resolve()
    assert dialog_start_dir("   ", fallback=fallback) == fallback.resolve()
    assert (
        dialog_start_dir(tmp_path / "disparu" / "profond" / "clip.mp4", fallback=fallback)
        == fallback.resolve()
    )


def test_dialog_start_dir_never_returns_empty_or_missing(tmp_path, monkeypatch):
    monkeypatch.setattr("overload.core.paths.Path.home", classmethod(lambda cls: tmp_path))
    start = dialog_start_dir(None)
    assert start == tmp_path.resolve()
    assert start.is_dir()


class _FakeQFileDialog:
    """Double de QFileDialog : enregistre le dossier de départ demandé."""

    calls: list[tuple[str, str]] = []
    next_open = ""
    next_dir = ""
    next_save = ""

    @staticmethod
    def getOpenFileName(parent, title, start, name_filter):  # noqa: N802 - API Qt
        _FakeQFileDialog.calls.append(("open", start))
        return _FakeQFileDialog.next_open, name_filter

    @staticmethod
    def getExistingDirectory(parent, title, start):  # noqa: N802 - API Qt
        _FakeQFileDialog.calls.append(("dir", start))
        return _FakeQFileDialog.next_dir

    @staticmethod
    def getSaveFileName(parent, title, start, name_filter):  # noqa: N802 - API Qt
        _FakeQFileDialog.calls.append(("save", start))
        return _FakeQFileDialog.next_save, name_filter


def _install_fake_qt(monkeypatch):
    pyside = types.ModuleType("PySide6")
    widgets = types.ModuleType("PySide6.QtWidgets")
    widgets.QFileDialog = _FakeQFileDialog
    pyside.QtWidgets = widgets
    monkeypatch.setitem(sys.modules, "PySide6", pyside)
    monkeypatch.setitem(sys.modules, "PySide6.QtWidgets", widgets)
    _FakeQFileDialog.calls = []
    filedialogs.reset_last_dir()


def test_wrappers_open_dialog_in_the_fields_directory(tmp_path, monkeypatch):
    _install_fake_qt(monkeypatch)
    media_dir = tmp_path / "rushes"
    media_dir.mkdir()
    current = media_dir / "plan1.mp4"
    current.write_bytes(b"ok")
    chosen = media_dir / "plan2.mp4"
    chosen.write_bytes(b"ok")
    _FakeQFileDialog.next_open = str(chosen)

    try:
        result = filedialogs.choose_open_file(None, "Choisir", preferred=str(current))
        assert result == str(chosen)
        # Le sélecteur démarre dans le dossier du fichier déjà indiqué…
        assert _FakeQFileDialog.calls == [("open", str(media_dir.resolve()))]

        # …et le suivant rouvre au même endroit (mémoire de session).
        _FakeQFileDialog.next_dir = ""
        assert filedialogs.choose_directory(None, "Dossier") == ""
        assert _FakeQFileDialog.calls[-1] == ("dir", str(media_dir.resolve()))
    finally:
        filedialogs.reset_last_dir()


def test_save_wrapper_prefills_suggested_filename(tmp_path, monkeypatch):
    _install_fake_qt(monkeypatch)
    export_dir = tmp_path / "exports"
    export_dir.mkdir()
    suggested = export_dir / "inventaire-overload.csv"
    _FakeQFileDialog.next_save = str(suggested)

    try:
        result = filedialogs.choose_save_file(None, "Exporter", suggested=suggested)
        assert result == str(suggested)
        assert _FakeQFileDialog.calls == [("save", str(suggested))]
    finally:
        filedialogs.reset_last_dir()


def test_session_remembers_last_chosen_directory(tmp_path):
    filedialogs.reset_last_dir()
    try:
        chosen = tmp_path / "projets"
        chosen.mkdir()
        media = chosen / "rush.mp4"
        media.write_bytes(b"ok")

        # Aucune préférence : repli explicite (dossier de destination simulé).
        assert filedialogs._start_dir(None, tmp_path) == str(tmp_path.resolve())

        filedialogs._remember(str(media))
        # Ensuite, le sélecteur rouvre là où l'utilisateur vient de choisir.
        assert filedialogs._start_dir(None, tmp_path) == str(chosen.resolve())
        # Mais un champ déjà rempli reste prioritaire.
        other = tmp_path / "ailleurs"
        other.mkdir()
        assert filedialogs._start_dir(other, tmp_path) == str(other.resolve())
    finally:
        filedialogs.reset_last_dir()
