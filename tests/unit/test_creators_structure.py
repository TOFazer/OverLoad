from __future__ import annotations

import json

import pytest

from overload.creators.fsutil import (
    classify_file,
    expand_sources,
    iter_media_files,
    sanitize_name,
    unique_path,
)
from overload.creators.models import MediaKind
from overload.creators.profiles import BUILTIN_PROFILES
from overload.creators.structure import (
    MANIFEST_FILENAME,
    README_FILENAME,
    create_project_structure,
    execute_import,
    plan_import,
)
from overload.downloads.duplicates import DuplicatePolicy


@pytest.fixture()
def premiere():
    return next(p for p in BUILTIN_PROFILES if p.id == "premiere")


# ---------------------------------------------------------------- sanitation
def test_sanitize_name_removes_windows_forbidden_characters():
    assert sanitize_name('a<b>c:"d/e\\f|g?h*i') == "a b c d e f g h i"
    assert sanitize_name("nom. ") == "nom"
    assert sanitize_name("   ") == "Sans titre"
    assert sanitize_name("x" * 300) == "x" * 80
    assert sanitize_name("Vlog \x01octobre") == "Vlog octobre"


def test_unique_path_appends_numbered_suffixes(tmp_path):
    first = tmp_path / "video.mp4"
    first.write_text("a")
    assert unique_path(tmp_path / "video.mp4") == tmp_path / "video (2).mp4"
    (tmp_path / "video (2).mp4").write_text("b")
    assert unique_path(tmp_path / "video.mp4") == tmp_path / "video (3).mp4"
    assert unique_path(tmp_path / "autre.mp4") == tmp_path / "autre.mp4"


def test_classify_file_by_extension():
    assert classify_file("rush.MP4") is MediaKind.VIDEO
    assert classify_file("voix.wav") is MediaKind.AUDIO
    assert classify_file("banniere.PNG") is MediaKind.IMAGE
    assert classify_file("sous-titres.srt") is MediaKind.SUBTITLE
    assert classify_file("notes.txt") is MediaKind.OTHER


def test_iter_media_files_skips_hidden_and_temporary(tmp_path):
    (tmp_path / ".cache").mkdir()
    (tmp_path / ".cache" / "hidden.mp4").write_text("x")
    (tmp_path / "encours.mp4.part").write_text("x")
    (tmp_path / "ok.mp4").write_text("x")
    (tmp_path / "sous").mkdir()
    (tmp_path / "sous" / "profond.mov").write_text("x")
    assert sorted(p.name for p in iter_media_files(tmp_path)) == ["ok.mp4", "profond.mov"]
    assert sorted(p.name for p in iter_media_files(tmp_path, recursive=False)) == ["ok.mp4"]


def test_expand_sources_mixes_files_and_folders_without_duplicates(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "f1.mp4").write_text("1")
    (tmp_path / "f2.wav").write_text("2")
    files = expand_sources(
        [tmp_path / "a", tmp_path / "f2.wav", tmp_path / "a", tmp_path / "inconnu"]
    )
    assert len(files) == 2


# ---------------------------------------------------------------- structure
def test_create_project_structure_builds_full_folder_tree(tmp_path, premiere):
    root = tmp_path / "Projets" / "Vlog"
    created = create_project_structure(root, project_name="Vlog", profile=premiere)
    assert root.is_dir()
    names = {p.name for p in created}
    assert {"01_Rushes", "02_Audio", "06_Exports"} <= names
    readme = root / README_FILENAME
    manifest = root / MANIFEST_FILENAME
    assert readme.is_file()
    assert "Vlog" in readme.read_text(encoding="utf-8")
    assert "Premiere" in readme.read_text(encoding="utf-8")
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["projet"] == "Vlog"
    assert payload["profil"] == "premiere"
    assert "jamais déplacés" in payload["regles"][0]


def test_create_project_structure_never_overwrites_existing_files(tmp_path, premiere):
    root = tmp_path / "projet"
    create_project_structure(root, project_name="P1", profile=premiere)
    readme = root / README_FILENAME
    readme.write_text("contenu personnalisé", encoding="utf-8")
    create_project_structure(root, project_name="P2", profile=premiere)
    assert readme.read_text(encoding="utf-8") == "contenu personnalisé"


# ---------------------------------------------------------------- plan + copy
def _make_sources(tmp_path):
    src = tmp_path / "originaux"
    (src / "camera A").mkdir(parents=True)
    (src / "camera A" / "rush 001.mp4").write_text("video-a")
    (src / "camera A" / "rush 001.mp4").write_text("video-a2")
    (src / "musique.wav").write_text("audio")
    (src / "photo.jpg").write_text("image")
    (src / "st fr.srt").write_text("st")
    (src / "notes.txt").write_text("doc")
    return src


def test_plan_import_classifies_files_into_profile_folders(tmp_path, premiere):
    src = _make_sources(tmp_path)
    root = tmp_path / "projet"
    plan = plan_import([src], root, premiere, project_name="Vlog")
    by_dest = {step.destination.relative_to(root).as_posix(): step for step in plan}
    assert "01_Rushes/rush 001.mp4" in by_dest
    assert "02_Audio/musique.wav" in by_dest
    assert "03_Images/photo.jpg" in by_dest
    assert "04_Sous-titres/st fr.srt" in by_dest
    assert all(step.status == "prêt" for step in plan)
    # Le plan n'écrit rien sur le disque.
    assert not root.exists()


def test_plan_import_flags_existing_destinations_as_collisions(tmp_path, premiere):
    src = _make_sources(tmp_path)
    root = tmp_path / "projet"
    (root / "01_Rushes").mkdir(parents=True)
    (root / "01_Rushes" / "rush 001.mp4").write_text("déjà là")
    plan = plan_import([src], root, premiere)
    collision = next(s for s in plan if s.destination.name == "rush 001.mp4")
    assert collision.collision is True
    assert collision.status == "conflit"


def test_plan_import_renames_with_template_and_numbers_duplicates(tmp_path, premiere):
    src = _make_sources(tmp_path)
    root = tmp_path / "projet"
    plan = plan_import(
        [src],
        root,
        premiere,
        project_name="Vlog",
        rename_template="{projet}_{numero:03}{ext}",
    )
    dests = [step.destination.name for step in plan]
    assert any(d.startswith("Vlog_") for d in dests)
    assert len(dests) == len(set(dests)), "aucun doublon de destination au sein du lot"


def test_execute_import_copies_without_touching_originals(tmp_path, premiere):
    src = _make_sources(tmp_path)
    original = src / "camera A" / "rush 001.mp4"
    original_content = original.read_text()
    root = tmp_path / "projet"
    plan = plan_import([src], root, premiere)
    result = execute_import(plan)
    assert len(result.copied) == len(plan)
    assert not result.failed and not result.skipped
    assert original.read_text() == original_content, "l'original doit rester intact"
    assert (root / "01_Rushes" / "rush 001.mp4").read_text() == original_content
    assert (src / "musique.wav").exists(), (
        "aucun original ne doit disparaître (copie, pas déplacement)"
    )


def test_execute_import_skip_policy_never_overwrites(tmp_path, premiere):
    src = _make_sources(tmp_path)
    root = tmp_path / "projet"
    (root / "02_Audio").mkdir(parents=True)
    target = root / "02_Audio" / "musique.wav"
    target.write_text("ancien contenu")
    plan = plan_import([src], root, premiere)
    result = execute_import(plan, collision_policy=DuplicatePolicy.SKIP)
    assert target.read_text() == "ancien contenu", "rien ne doit être écrasé"
    assert any(reason.startswith("la destination existe déjà") for _src, reason in result.skipped)
    assert all(dst != target for _src, dst in result.copied)


def test_execute_import_rename_policy_creates_numbered_copy(tmp_path, premiere):
    src = _make_sources(tmp_path)
    root = tmp_path / "projet"
    (root / "02_Audio").mkdir(parents=True)
    (root / "02_Audio" / "musique.wav").write_text("ancien")
    plan = plan_import([src], root, premiere)
    result = execute_import(plan, collision_policy=DuplicatePolicy.RENAME)
    assert (root / "02_Audio" / "musique.wav").read_text() == "ancien"
    assert (root / "02_Audio" / "musique (2).wav").read_text() == "audio"
    assert len(result.copied) == len(plan)


def test_execute_import_reports_failures_without_raising(tmp_path, premiere, monkeypatch):
    src = _make_sources(tmp_path)
    root = tmp_path / "projet"
    plan = plan_import([src], root, premiere)
    monkeypatch.setattr(
        "overload.creators.structure.shutil.copy2",
        lambda *_a, **_k: (_ for _ in ()).throw(OSError("disque plein")),
    )
    result = execute_import(plan)
    assert len(result.failed) == len(plan)
    assert all(err == "disque plein" for _src, err in result.failed)
