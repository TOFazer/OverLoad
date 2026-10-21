from __future__ import annotations

from datetime import UTC, datetime

import pytest

from overload.core.errors import OverloadError
from overload.creators.renaming import (
    DEFAULT_TEMPLATE,
    TEMPLATE_HELP,
    apply_renaming,
    preview_renaming,
    render_filename,
)
from overload.downloads.duplicates import DuplicatePolicy

MOMENT = datetime(2026, 10, 21, 14, 30, tzinfo=UTC)


def _files(tmp_path, *names: str):
    made = []
    for name in names:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(name)
        made.append(path)
    return made


def test_render_filename_applies_all_tokens(tmp_path):
    original = _files(tmp_path, "rush final.MP4")[0]
    rendered = render_filename(
        "{projet}_{nom}_{type}_{numero:03}{ext}",
        original=original,
        project_name="Vlog: octobre?",
        number=7,
        now=MOMENT,
    )
    assert rendered == "Vlog octobre_rush final_Video_007.mp4"


def test_render_filename_keeps_extension_without_ext_token(tmp_path):
    original = _files(tmp_path, "plan.pdf")[0]
    rendered = render_filename(
        "{date}_{nom}", original=original, project_name="", number=1, now=MOMENT
    )
    assert rendered == "2026-10-21_plan.pdf"


def test_render_filename_date_time_and_folder_tokens(tmp_path):
    original = _files(tmp_path / "CameraA", "clip001.mov")[0]
    rendered = render_filename(
        "{annee}{mois}{jour}_{heure}_{origine}_{numero}",
        original=original,
        number=3,
        now=MOMENT,
    )
    assert rendered == "20261021_14h30_CameraA_3.mov"
    padded = render_filename(
        "{origine}_{numero:04}", original=original, number=3, now=MOMENT
    )
    assert padded == "CameraA_0003.mov"


def test_render_filename_rejects_empty_template(tmp_path):
    original = _files(tmp_path, "a.mp4")[0]
    with pytest.raises(OverloadError, match="vide"):
        render_filename("   ", original=original)


def test_render_filename_rejects_template_without_usable_output(tmp_path):
    original = _files(tmp_path, "a.mp4")[0]
    with pytest.raises(OverloadError, match="aucun nom"):
        render_filename("{inconnu}", original=original)


def test_render_filename_strips_separators_left_by_empty_tokens(tmp_path):
    original = _files(tmp_path, "a.mp4")[0]
    rendered = render_filename(
        "{projet}_{nom}", original=original, project_name="", number=1, now=MOMENT
    )
    assert rendered == "a.mp4"


def test_template_help_documents_all_tokens():
    for token in ("{projet}", "{nom}", "{type}", "{numero:03}", "{ext}", "{date}"):
        assert token in TEMPLATE_HELP
    assert "{numero" in DEFAULT_TEMPLATE


def test_preview_renaming_is_read_only_and_sorted(tmp_path):
    files = _files(tmp_path, "b.mp4", "a.mp4")
    steps = preview_renaming(files, "{numero:02}_{nom}", project_name="P", now=MOMENT)
    assert [s.new_path.name for s in steps] == ["01_b.mp4", "02_a.mp4"]
    assert all(s.status == "ok" for s in steps)
    assert all(p.exists() for p in files), "l'aperçu ne doit rien modifier"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["a.mp4", "b.mp4"]


def test_preview_marks_unchanged_and_conflicts(tmp_path):
    files = _files(tmp_path, "final.mp4", "existing.mp4")
    (tmp_path / "renamed.mp4").write_text("déjà pris")
    # Modèle identité : le nom produit est identique, rien à faire.
    steps = preview_renaming(files, "{nom}", project_name="", now=MOMENT)
    assert all(s.status == "inchangé" for s in steps)
    # Modèle constant : collision avec le fichier déjà présent sur le disque.
    steps = preview_renaming(files, "renamed", project_name="", now=MOMENT)
    statuses = {s.original.name: s.status for s in steps}
    assert statuses["final.mp4"] == "conflit"
    assert statuses["existing.mp4"] == "conflit"


def test_preview_resolves_same_name_within_batch(tmp_path):
    f1 = _files(tmp_path, "premiere.mp4")[0]
    f2 = _files(tmp_path, "seconde.mp4")[0]
    steps = preview_renaming([f1, f2], "constant", project_name="", now=MOMENT)
    assert steps[0].status == "ok"
    assert steps[1].status == "conflit"
    assert steps[1].new_path.name == "constant (2).mp4"


def test_apply_renaming_renames_in_place_without_overwrite(tmp_path):
    files = _files(tmp_path, "un.mp4", "deux.mp4")
    result = apply_renaming(files, "{numero:02}{ext}", project_name="", now=MOMENT)
    assert len(result.renamed) == 2
    assert sorted(p.name for p in tmp_path.iterdir()) == ["01.mp4", "02.mp4"]
    assert (tmp_path / "01.mp4").read_text() == "un.mp4"


def test_apply_renaming_never_overwrites_existing_file(tmp_path):
    files = _files(tmp_path, "source.mp4")
    (tmp_path / "cible.mp4").write_text("contenu précieux")
    result = apply_renaming(files, "cible", project_name="", now=MOMENT)
    assert (tmp_path / "cible.mp4").read_text() == "contenu précieux"
    assert (tmp_path / "cible (2).mp4").read_text() == "source.mp4"
    assert len(result.renamed) == 1


def test_apply_renaming_skip_policy_leaves_conflicts_untouched(tmp_path):
    files = _files(tmp_path, "source.mp4")
    (tmp_path / "cible.mp4").write_text("contenu précieux")
    result = apply_renaming(
        files, "cible", project_name="", conflict_policy=DuplicatePolicy.SKIP, now=MOMENT
    )
    assert (tmp_path / "cible.mp4").read_text() == "contenu précieux"
    assert (tmp_path / "source.mp4").read_text() == "source.mp4", "fichier laissé intact"
    assert result.renamed == []
    assert result.skipped and "existe déjà" in result.skipped[0][1]


def test_apply_renaming_reports_failures(tmp_path):
    files = _files(tmp_path, "verrouillé.mp4")
    result = apply_renaming(files, "{nom}_{numero}", project_name="", now=MOMENT)
    assert len(result.renamed) == 1
    assert result.failed == []
    assert result.total == 1
