"""Profils dédiés aux formats et arborescences des logiciels de montage.

Chaque profil décrit :
- la structure de dossiers créée pour un nouveau projet vidéo ;
- les conteneurs et codecs recommandés pour importer sereinement les médias
  dans le logiciel de montage correspondant.

Les profils intégrés ne peuvent pas être supprimés ; l'utilisateur peut en
revanche créer ses propres profils personnalisés (persistés en JSON).
"""

from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path

from overload.core.errors import OverloadError
from overload.creators.models import EditingProfile

SCHEMA_VERSION = 1

BUILTIN_PROFILES: tuple[EditingProfile, ...] = (
    EditingProfile(
        id="premiere",
        name="Adobe Premiere Pro",
        description="Structure et formats conseillés pour Premiere Pro (Windows / Mac).",
        video_folder="01_Rushes",
        audio_folder="02_Audio",
        image_folder="03_Images",
        subtitle_folder="04_Sous-titres",
        project_folder="05_Projets_Premiere",
        export_folder="06_Exports",
        extra_folders=("07_Graphismes",),
        recommended_container="MP4 ou MOV (MXF pour la diffusion broadcast)",
        recommended_video="H.264 4:2:0 8 bits, ou ProRes 422 / DNxHR pour un montage fluide",
        recommended_audio="AAC ou PCM 16/24 bits, 48 kHz",
        notes=(
            "Premiere Pro importe nativement la plupart des fichiers, mais le MKV n'est pas "
            "pris en charge et le HEVC 10 bits peut demander une extension. Les sous-titres "
            "intégrés à un conteneur sont souvent ignorés : importez un fichier .srt séparé."
        ),
        builtin=True,
    ),
    EditingProfile(
        id="resolve",
        name="DaVinci Resolve",
        description="Structure et formats conseillés pour DaVinci Resolve (gratuit ou Studio).",
        video_folder="01_Medias",
        audio_folder="02_Audio",
        image_folder="03_Images",
        subtitle_folder="04_Sous-titres",
        project_folder="05_Projets_Resolve",
        export_folder="06_Exports",
        extra_folders=("07_Versions_intermediaires",),
        recommended_container="MOV ou MP4 (MXF accepté)",
        recommended_video="ProRes 422/HQ, DNxHR/HQ ou H.264 8 bits (Rec.709 en version gratuite)",
        recommended_audio="PCM 24 bits 48 kHz de préférence",
        notes=(
            "La version gratuite de Resolve décode mal certains H.264/H.265 10 bits 4:2:2 : "
            "si la lecture saccade, transcodez une copie en DNxHR ou ProRes. Resolve accepte "
            "les sous-titres .srt importés directement dans la timeline."
        ),
        builtin=True,
    ),
    EditingProfile(
        id="finalcut",
        name="Final Cut Pro (Mac)",
        description="Structure et formats conseillés pour Final Cut Pro sur Mac.",
        video_folder="01_Medias_originaux",
        audio_folder="02_Sons_et_musiques",
        image_folder="03_Graphismes",
        subtitle_folder="04_Sous-titres",
        project_folder="05_Bibliotheques_FCP",
        export_folder="06_Exports",
        recommended_container="MOV",
        recommended_video="ProRes 422 (ou H.264 8 bits pour des rushs légers)",
        recommended_audio="PCM ou AAC, 48 kHz",
        notes=(
            "Final Cut Pro refuse l'AVI et le MKV. Privilégiez le ProRes dans un MOV et "
            "rencontrez moins de surprises à l'import."
        ),
        builtin=True,
    ),
    EditingProfile(
        id="capcut",
        name="CapCut / montage débutant",
        description="Structure simple pour CapCut, Shotcut ou une découverte du montage.",
        video_folder="Videos",
        audio_folder="Musiques",
        image_folder="Images",
        subtitle_folder="Sous-titres",
        project_folder="Projets",
        export_folder="Exports",
        recommended_container="MP4",
        recommended_video="H.264 4:2:0 8 bits — le plus universel",
        recommended_audio="AAC 48 kHz",
        notes=(
            "Gardez des noms de fichiers simples, sans accents ni caractères spéciaux, pour "
            "éviter tout souci d'importation."
        ),
        builtin=True,
    ),
    EditingProfile(
        id="universel",
        name="Universel (tout logiciel)",
        description="Arborescence classique utilisable avec n'importe quel logiciel de montage.",
        video_folder="01_Videos",
        audio_folder="02_Audio",
        image_folder="03_Images",
        subtitle_folder="04_Sous-titres",
        project_folder="05_Projets",
        export_folder="06_Exports",
        extra_folders=("07_Documents",),
        recommended_container="MP4 (ou MOV)",
        recommended_video="H.264 8 bits pour la compatibilité maximale",
        recommended_audio="AAC ou PCM 48 kHz",
        notes=(
            "Ce profil neutre convient quand le logiciel de montage n'est pas encore décidé."
        ),
        builtin=True,
    ),
)


def _slugify(name: str) -> str:
    """Transforme un nom lisible en identifiant sûr (ex. « Mon Profil » → « mon-profil »)."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug or "profil"


class ProfileLibrary:
    """Registre des profils de montage : intégrés + personnalisés (JSON atomique)."""

    def __init__(self, path: Path | str | None = None) -> None:
        self._path = Path(path) if path is not None else None
        self._lock = threading.RLock()
        self._custom: dict[str, EditingProfile] = {}
        if self._path is not None:
            self._load()

    @property
    def path(self) -> Path | None:
        return self._path

    def list_profiles(self) -> list[EditingProfile]:
        """Tous les profils disponibles : intégrés d'abord, puis personnalisés (ordre d'ajout)."""
        with self._lock:
            return [*BUILTIN_PROFILES, *self._custom.values()]

    def builtin_ids(self) -> set[str]:
        return {p.id for p in BUILTIN_PROFILES}

    def get(self, profile_id: str) -> EditingProfile:
        with self._lock:
            for profile in self.list_profiles():
                if profile.id == profile_id:
                    return profile
        raise OverloadError(
            "Profil de montage introuvable.",
            f"le profil « {profile_id} » n'existe plus.",
            "Choisissez un autre profil dans la liste.",
        )

    def default_profile(self) -> EditingProfile:
        return BUILTIN_PROFILES[-1]

    def add_custom(
        self,
        *,
        name: str,
        description: str = "",
        video_folder: str = "01_Videos",
        audio_folder: str = "02_Audio",
        image_folder: str = "03_Images",
        subtitle_folder: str = "04_Sous-titres",
        project_folder: str = "05_Projets",
        export_folder: str = "06_Exports",
        extra_folders: list[str] | None = None,
        recommended_container: str = "",
        recommended_video: str = "",
        recommended_audio: str = "",
        notes: str = "",
    ) -> EditingProfile:
        """Crée et enregistre un profil personnalisé (jamais un profil intégré)."""
        cleaned_name = name.strip()
        if not cleaned_name:
            raise OverloadError(
                "Nom de profil invalide.",
                "le nom du profil est vide.",
                "Saisissez un nom lisible, par exemple « Montage YouTube 2026 ».",
            )
        profile = EditingProfile(
            id=_slugify(cleaned_name),
            name=cleaned_name,
            description=description.strip(),
            video_folder=video_folder.strip() or "01_Videos",
            audio_folder=audio_folder.strip() or "02_Audio",
            image_folder=image_folder.strip() or "03_Images",
            subtitle_folder=subtitle_folder.strip() or "04_Sous-titres",
            project_folder=project_folder.strip() or "05_Projets",
            export_folder=export_folder.strip() or "06_Exports",
            extra_folders=tuple(f.strip() for f in (extra_folders or []) if f.strip()),
            recommended_container=recommended_container.strip(),
            recommended_video=recommended_video.strip(),
            recommended_audio=recommended_audio.strip(),
            notes=notes.strip(),
            builtin=False,
        )
        with self._lock:
            if profile.id in self.builtin_ids():
                raise OverloadError(
                    "Ce nom de profil est réservé.",
                    f"un profil intégré utilise déjà l'identifiant « {profile.id} ».",
                    "Choisissez un autre nom.",
                )
            if profile.id in self._custom:
                raise OverloadError(
                    "Un profil personnalisé porte déjà ce nom.",
                    f"le profil « {cleaned_name} » existe déjà.",
                    "Modifiez-le ou choisissez un autre nom.",
                )
            self._custom[profile.id] = profile
            self._save_locked()
            return profile

    def remove_custom(self, profile_id: str) -> bool:
        """Retire un profil personnalisé ; refuse toujours de supprimer un profil intégré."""
        with self._lock:
            if profile_id in self.builtin_ids():
                raise OverloadError(
                    "Les profils intégrés ne peuvent pas être supprimés.",
                    f"« {profile_id} » fait partie des profils fournis par OverLoad.",
                    "Vous pouvez créer un profil personnalisé adapté à votre place de travail.",
                )
            removed = self._custom.pop(profile_id, None)
            if removed is not None:
                self._save_locked()
            return removed is not None

    def _load(self) -> None:
        assert self._path is not None
        if not self._path.is_file():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(raw, dict):
            return
        entries = raw.get("profiles", [])
        if not isinstance(entries, list):
            return
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            profile = EditingProfile.from_dict({**entry, "builtin": False})
            if profile.id and profile.id not in self.builtin_ids():
                self._custom[profile.id] = profile

    def _save_locked(self) -> None:
        if self._path is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": SCHEMA_VERSION,
            "profiles": [p.to_dict() for p in self._custom.values()],
        }
        tmp = self._path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self._path)
