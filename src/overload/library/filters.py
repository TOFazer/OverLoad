"""Critères de filtre haut-niveau pour l'UI et l'API.

Permet les combinaisons :
- recherche texte (nom, chemin)
- type (vidéo/audio/image/autre)
- taille (min/max)
- date (après/avant — timestamp ou datetime)
- durée (min/max secondes)
- extension

Le plus : retrouver un fichier de plusieurs mois = recherche texte + filtre date large.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from overload.library.models import MediaType


def _to_timestamp(value: datetime | float | int | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.timestamp()
    return float(value)


@dataclass
class FilterCriteria:
    """Ensemble de filtres combinés par ET."""

    query: str | None = None
    media_types: list[MediaType] | None = None
    min_size: int | None = None
    max_size: int | None = None
    after: datetime | float | None = None
    before: datetime | float | None = None
    min_duration: float | None = None
    max_duration: float | None = None
    extensions: list[str] | None = None
    only_duplicates: bool = False  # si True, on ne garde que les doublons (post-filtre)
    order_by: str = "mtime"
    descending: bool = True
    limit: int | None = None
    offset: int = 0

    def normalized(self) -> dict:
        """Pour passer à LibraryStore.search()."""
        return {
            "query": self.query.strip() if self.query and self.query.strip() else None,
            "media_types": self.media_types,
            "min_size": self.min_size,
            "max_size": self.max_size,
            "after": _to_timestamp(self.after),
            "before": _to_timestamp(self.before),
            "min_duration": self.min_duration,
            "max_duration": self.max_duration,
            "extension": self.extensions[0] if self.extensions and len(self.extensions) == 1 else None,
            "order_by": self.order_by,
            "descending": self.descending,
            "limit": self.limit,
            "offset": self.offset,
        }

    def matches(self, entry) -> bool:
        """Vérification en mémoire (pour les tests hors DB ou filtrage supplémentaire)."""
        if self.query:
            q = self.query.lower()
            if q not in entry.filename.lower() and q not in str(entry.path).lower():
                return False
        if self.media_types and entry.media_type not in self.media_types:
            return False
        if self.min_size is not None and entry.size < self.min_size:
            return False
        if self.max_size is not None and entry.size > self.max_size:
            return False
        after_ts = _to_timestamp(self.after)
        before_ts = _to_timestamp(self.before)
        if after_ts is not None and entry.mtime < after_ts:
            return False
        if before_ts is not None and entry.mtime > before_ts:
            return False
        if self.min_duration is not None:
            if entry.duration is None or entry.duration < self.min_duration:
                return False
        if self.max_duration is not None:
            if entry.duration is None or entry.duration > self.max_duration:
                return False
        if self.extensions:
            if entry.extension.lower() not in [e.lower() for e in self.extensions]:
                return False
        return True


# Presets pratiques pour l'UI (barre de filtres rapides).
FILTER_PRESETS: dict[str, FilterCriteria] = {
    "videos": FilterCriteria(media_types=[MediaType.VIDEO]),
    "musiques": FilterCriteria(media_types=[MediaType.AUDIO]),
    "images": FilterCriteria(media_types=[MediaType.IMAGE]),
    "recents": FilterCriteria(order_by="mtime", descending=True, limit=50),
    "volumineux": FilterCriteria(order_by="size", descending=True, limit=50),
    "doublons": FilterCriteria(only_duplicates=True),
}


def apply_filter(entries: Iterable, criteria: FilterCriteria) -> list:
    """Filtre en mémoire + tri."""
    filtered = [e for e in entries if criteria.matches(e)]

    reverse = criteria.descending
    key = criteria.order_by
    if key == "size":
        filtered.sort(key=lambda e: e.size, reverse=reverse)
    elif key == "filename":
        filtered.sort(key=lambda e: e.filename.lower(), reverse=reverse)
    elif key == "duration":
        filtered.sort(key=lambda e: (e.duration if e.duration is not None else -1), reverse=reverse)
    elif key == "media_type":
        filtered.sort(key=lambda e: e.media_type.value, reverse=reverse)
    else:  # mtime par défaut
        filtered.sort(key=lambda e: e.mtime, reverse=reverse)

    if criteria.offset:
        filtered = filtered[criteria.offset :]
    if criteria.limit is not None:
        filtered = filtered[: criteria.limit]
    return filtered
