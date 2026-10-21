"""Les releases doivent embarquer leur propre version, sans édition manuelle."""

from __future__ import annotations

import importlib.util
import shutil
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "release_version", ROOT / "scripts" / "set_release_version.py"
)
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


@pytest.mark.parametrize(
    ("tag", "expected"),
    [
        ("v1.2.3", ("1.2.3", "1.2.3", "1.2.3.0")),
        ("0.0.0", ("0.0.0", "0.0.0", "0.0.0.0")),
        ("v65535.2.9", ("65535.2.9", "65535.2.9", "65535.2.9.0")),
        ("v2.0.0-alpha.0", ("2.0.0a0", "2.0.0-alpha.0", "2.0.0.0")),
        ("v2.0.0-beta.2", ("2.0.0b2", "2.0.0-beta.2", "2.0.0.0")),
        ("v2.0.0-rc.1", ("2.0.0rc1", "2.0.0-rc.1", "2.0.0.0")),
    ],
)
def test_release_version_formats(tag, expected):
    assert release.release_versions(tag) == expected


@pytest.mark.parametrize(
    "tag",
    [
        "latest", "v1.2", "v01.2.3", "v1.2.3.4", "v1.2.3\n", " v1.2.3",
        "v1.2.3-preview.1", "v1.2.3-rc.01", "v65536.0.0", "v1.65536.0",
        "v1.2.65536", 'v1.2.3"; echo bad', "../v1.2.3",
    ],
)
def test_invalid_release_tags_are_rejected(tag):
    with pytest.raises(ValueError):
        release.release_versions(tag)


def copy_version_files(tmp_path):
    for relative in ("pyproject.toml", "src/overload/__init__.py", "packaging/OverLoad.iss"):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)


@pytest.mark.parametrize("tag", ["v1.2.3", "v2.0.0-rc.1"])
def test_all_versions_are_updated_together(tmp_path, tag):
    copy_version_files(tmp_path)
    release.set_release_version(tag, root=tmp_path)
    python_version, display_version, numeric_version = release.release_versions(tag)
    project = tomllib.loads((tmp_path / "pyproject.toml").read_text(encoding="utf-8"))
    assert project["project"]["version"] == python_version
    assert f'__version__ = "{python_version}"' in (
        tmp_path / "src/overload/__init__.py"
    ).read_text(encoding="utf-8")
    installer = (tmp_path / "packaging/OverLoad.iss").read_text(encoding="utf-8")
    assert f'#define MyAppVersion "{display_version}"' in installer
    assert f'#define MyAppNumericVersion "{numeric_version}"' in installer
    assert "VersionInfoVersion={#MyAppNumericVersion}" in installer
    # Même identité pour permettre l'installation d'une nouvelle version par-dessus l'ancienne.
    assert "AppId={{8D4F51B2-6C19-4C7A-A2B8-9F0E1D45A711}" in installer
    assert 'OutputBaseFilename=OverLoad-Setup' in installer


def test_missing_declaration_does_not_partially_update_files(tmp_path):
    copy_version_files(tmp_path)
    installer = tmp_path / "packaging/OverLoad.iss"
    installer.write_text("; plus de déclaration de version\n", encoding="utf-8")
    before = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    with pytest.raises(ValueError, match="absente ou ambiguë"):
        release.set_release_version("v1.2.3", root=tmp_path)
    assert all(path.read_bytes() == content for path, content in before.items())


def test_version_preparation_can_be_repeated(tmp_path):
    copy_version_files(tmp_path)
    release.set_release_version("v1.2.3", root=tmp_path)
    release.set_release_version("v1.2.4", root=tmp_path)
    project = tomllib.loads((tmp_path / "pyproject.toml").read_text(encoding="utf-8"))
    assert project["project"]["version"] == "1.2.4"
