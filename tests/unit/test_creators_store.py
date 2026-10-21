from __future__ import annotations

import json
from pathlib import Path

import pytest

from overload.core.errors import OverloadError
from overload.creators.models import CreatorProject
from overload.creators.store import CreatorProjectsStore
from overload.creators.workspace import CreatorsWorkspace


def test_add_and_list_projects_newest_first(tmp_path):
    store = CreatorProjectsStore(tmp_path / "projects.json")
    p1 = store.add_project(name="Vlog", root_dir=tmp_path / "vlog", profile_id="premiere")
    p2 = store.add_project(name="Documentaire", root_dir=tmp_path / "doc", profile_id="resolve")
    assert [p.name for p in store.list_projects()] == ["Documentaire", "Vlog"]
    assert store.get(p1.id).profile_id == "premiere"
    assert store.get(p2.id).name == "Documentaire"


def test_projects_persist_across_reloads(tmp_path):
    path = tmp_path / "projects.json"
    store = CreatorProjectsStore(path)
    store.add_project(name="Vlog", root_dir=tmp_path / "vlog", profile_id="premiere")
    reloaded = CreatorProjectsStore(path)
    assert [p.name for p in reloaded.list_projects()] == ["Vlog"]


def test_add_project_same_root_updates_existing_entry(tmp_path):
    store = CreatorProjectsStore(tmp_path / "projects.json")
    store.add_project(name="Vlog", root_dir=tmp_path / "vlog", profile_id="premiere")
    updated = store.add_project(
        name="Vlog 2026", root_dir=tmp_path / "vlog", profile_id="resolve"
    )
    entries = store.list_projects()
    assert len(entries) == 1
    assert entries[0].name == "Vlog 2026"
    assert entries[0].profile_id == "resolve"
    assert updated.id == entries[0].id


def test_add_project_rejects_empty_name(tmp_path):
    store = CreatorProjectsStore(tmp_path / "projects.json")
    with pytest.raises(OverloadError, match="Nom de projet invalide"):
        store.add_project(name="  ", root_dir=tmp_path, profile_id="premiere")


def test_get_unknown_project_raises(tmp_path):
    store = CreatorProjectsStore(tmp_path / "projects.json")
    with pytest.raises(OverloadError, match="introuvable"):
        store.get("inconnu")


def test_remove_project_never_touches_disk(tmp_path):
    store = CreatorProjectsStore(tmp_path / "projects.json")
    project = store.add_project(name="Vlog", root_dir=tmp_path / "vlog", profile_id="premiere")
    (tmp_path / "vlog").mkdir()
    (tmp_path / "vlog" / "rush.mp4").write_text("précieux")
    assert store.remove_project(project.id) is True
    assert store.list_projects() == []
    assert store.remove_project(project.id) is False
    assert (tmp_path / "vlog" / "rush.mp4").read_text() == "précieux", "aucun fichier supprimé"


def test_touch_reorders_and_updates_timestamp(tmp_path):
    store = CreatorProjectsStore(tmp_path / "projects.json")
    p1 = store.add_project(name="A", root_dir=tmp_path / "a", profile_id="universel")
    p2 = store.add_project(name="B", root_dir=tmp_path / "b", profile_id="universel")
    store.touch(p1.id)
    assert [p.name for p in store.list_projects()] == ["A", "B"]
    assert store.get(p1.id).last_opened_at >= p2.last_opened_at


def test_store_survives_corrupted_json(tmp_path):
    path = tmp_path / "projects.json"
    path.write_text("{corrompu", encoding="utf-8")
    store = CreatorProjectsStore(path)
    assert store.list_projects() == []
    store.add_project(name="Neuf", root_dir=tmp_path / "n", profile_id="universel")
    assert json.loads(path.read_text(encoding="utf-8"))["projects"][0]["name"] == "Neuf"


def test_creator_project_roundtrip():
    project = CreatorProject(
        id="abc", name="N", root_dir="/tmp/n", profile_id="premiere",
        created_at="2026-10-21T00:00:00+00:00", last_opened_at="", notes="note",
    )
    assert CreatorProject.from_dict(project.to_dict()) == project
    assert project.path == Path("/tmp/n")


def test_workspace_creates_stores_under_creators_dir(tmp_path):
    workspace = CreatorsWorkspace(tmp_path / "data")
    assert (tmp_path / "data" / "creators").is_dir()
    assert workspace.projects.path == tmp_path / "data" / "creators" / "projects.json"
    assert workspace.profiles.path == tmp_path / "data" / "creators" / "profiles.json"
    assert workspace.preferences()["rename_template"]
    workspace.update_preferences(rename_template="{nom}")
    assert CreatorsWorkspace(tmp_path / "data").preferences()["rename_template"] == "{nom}"
    workspace.projects.add_project(name="P", root_dir=tmp_path / "p", profile_id="universel")
    assert [p.name for p in CreatorsWorkspace(tmp_path / "data").projects.list_projects()] == ["P"]
