"""Détection des doublons.

Exigences produit :
- détecter sans supprimer automatiquement (jamais de unlink ici) ;
- rapide même avec des milliers de fichiers (pré-filtre par taille + hash partiel) ;
- signaler les groupes et le gaspillage d'espace.
"""

from __future__ import annotations

from collections import defaultdict

from overload.library.models import DuplicateGroup, MediaEntry


def find_duplicates_by_hash(entries: list[MediaEntry]) -> list[DuplicateGroup]:
    """Groupes par empreinte complète (hash).

    Seules les entrées avec ``hash`` renseigné sont prises en compte.
    """
    buckets: dict[str, list[MediaEntry]] = defaultdict(list)
    for e in entries:
        if e.hash:
            buckets[e.hash].append(e)

    groups: list[DuplicateGroup] = []
    for h, items in buckets.items():
        if len(items) >= 2:
            groups.append(DuplicateGroup(hash=h, entries=sorted(items, key=lambda x: x.path.name)))
    # Plus gros gaspillage d'abord
    groups.sort(key=lambda g: g.wasted_bytes, reverse=True)
    return groups


def find_duplicates_by_size_and_partial(entries: list[MediaEntry]) -> list[DuplicateGroup]:
    """Heuristique rapide : même taille + même hash_partiel = probable doublon.

    Utile quand le hash complet n'a pas encore été calculé.
    """
    buckets: dict[tuple[int, str], list[MediaEntry]] = defaultdict(list)
    for e in entries:
        if e.hash_partial:
            buckets[(e.size, e.hash_partial)].append(e)

    groups: list[DuplicateGroup] = []
    for (size, h_partial), items in buckets.items():
        if len(items) >= 2:
            groups.append(DuplicateGroup(hash=f"partial:{size}:{h_partial}", entries=sorted(items, key=lambda x: x.path.name)))
    groups.sort(key=lambda g: g.wasted_bytes, reverse=True)
    return groups


def find_duplicates(entries: list[MediaEntry], *, use_partial: bool = True) -> list[DuplicateGroup]:
    """Point d'entrée principal : hash complet prioritaire, sinon partiel."""
    # 1) D'abord les vrais doublons (hash complet)
    full = find_duplicates_by_hash(entries)
    if full:
        # Vérifier si certains groupes partiels recoupent déjà les full — on évite les doublons de groupes
        remaining = [e for e in entries if not e.hash or not any(e in g.entries for g in full)]
        if use_partial and remaining:
            partial = find_duplicates_by_size_and_partial(remaining)
            # Filtrer les partiels qui recoupent un groupe complet ? Déjà fait via remaining
            return full + partial
        return full
    if use_partial:
        return find_duplicates_by_size_and_partial(entries)
    return []


def find_duplicates_in_store(store, *, use_partial: bool = True, compute_missing_hash: bool = False) -> list[DuplicateGroup]:
    """Recherche directement dans le store ; peut calculer les hash manquants.

    ``compute_missing_hash`` : si True, pour les groupes suspects (même taille), on calcule le hash complet
    à la volée pour confirmer. Attention : peut être lent sur disque réseau.
    """
    from overload.library.scanner import file_hash

    entries = store.all_entries()
    if compute_missing_hash:
        # Pour les groupes de même taille (>=2), calculer le hash complet si absent
        from collections import defaultdict

        size_groups: dict[int, list[MediaEntry]] = defaultdict(list)
        for e in entries:
            size_groups[e.size].append(e)
        for _size, bucket in size_groups.items():
            if len(bucket) >= 2:
                for e in bucket:
                    if not e.hash:
                        p = e.path
                        if p.exists():
                            try:
                                e.hash = file_hash(p)
                                # Mettre à jour la base
                                store.upsert_entry(e)
                            except OSError:
                                pass

        entries = store.all_entries()

    return find_duplicates(entries, use_partial=use_partial)
