from __future__ import annotations

import pytest

from overload.core.errors import OverloadError
from overload.creators.models import EditingProfile, MediaKind
from overload.creators.profiles import BUILTIN_PROFILES, ProfileLibrary


def test_builtin_profiles_are_present_and_consistent():
    ids = [profile.id for profile in BUILTIN_PROFILES]
    assert set(ids) >= {"premiere", "resolve", "finalcut", "capcut", "universel"}
    assert len(ids) == len(set(ids)), "les identifiants de profils intégrés doivent être uniques"
    for profile in BUILTIN_PROFILES:
        assert profile.builtin is True
        folders = profile.folders()
        assert folders, f"le profil {profile.id} doit définir des dossiers"
        assert len(folders) == len(set(folders)), "pas de doublons de dossiers"
        assert profile.folder_for(MediaKind.VIDEO) in folders
        assert profile.folder_for(MediaKind.SUBTITLE) in folders
        assert profile.recommended_video and profile.recommended_audio


def test_library_lists_builtins_without_path():
    library = ProfileLibrary()
    names = [profile.name for profile in library.list_profiles()]
    assert any("Premiere" in name for name in names)
    assert library.default_profile().id == "universel"


def test_library_get_unknown_profile_raises():
    library = ProfileLibrary()
    with pytest.raises(OverloadError):
        library.get("inconnu")


def test_custom_profile_persists_and_reloads(tmp_path):
    path = tmp_path / "profiles.json"
    library = ProfileLibrary(path)
    created = library.add_custom(
        name="Montage YouTube",
        video_folder="Rushs",
        recommended_video="H.264 8 bits",
    )
    assert created.builtin is False
    assert created.id == "montage-youtube"

    reloaded = ProfileLibrary(path)
    assert reloaded.get("montage-youtube").video_folder == "Rushs"
    assert reloaded.get("montage-youtube").recommended_video == "H.264 8 bits"


def test_custom_profile_rejects_empty_and_duplicate_names(tmp_path):
    library = ProfileLibrary(tmp_path / "profiles.json")
    with pytest.raises(OverloadError):
        library.add_custom(name="   ")
    library.add_custom(name="Mon profil")
    with pytest.raises(OverloadError):
        library.add_custom(name="Mon profil")
    # Un nom identique à un profil intégré est refusé (identifiant réservé).
    with pytest.raises(OverloadError):
        library.add_custom(name="Premiere")


def test_remove_custom_profile_never_removes_builtins(tmp_path):
    library = ProfileLibrary(tmp_path / "profiles.json")
    library.add_custom(name="Temporaire")
    assert library.remove_custom("temporaire") is True
    assert library.remove_custom("temporaire") is False
    with pytest.raises(OverloadError, match="intégrés"):
        library.remove_custom("premiere")
    assert library.get("premiere").name == "Adobe Premiere Pro"


def test_profile_roundtrip_via_dict():
    profile = BUILTIN_PROFILES[0]
    restored = EditingProfile.from_dict(profile.to_dict())
    assert restored == profile
