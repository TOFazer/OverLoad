import time
from pathlib import Path

from overload.library.db import LibraryStore
from overload.library.models import MediaEntry, MediaType


def _entry(path="video.mp4", media_type=MediaType.VIDEO, size=1000, mtime=None, extra=None):
    mtime = mtime or time.time()
    return MediaEntry(
        path=Path(path),
        filename=Path(path).name,
        media_type=media_type,
        extension=Path(path).suffix.lower(),
        size=size,
        mtime=mtime,
        duration=extra.get("duration") if extra else None,
    )


def test_upsert_and_search(tmp_path):
    store = LibraryStore(tmp_path / "lib.db")
    now = time.time()
    store.upsert_entry(_entry("a.mp4", MediaType.VIDEO, 1000, now))
    store.upsert_entry(_entry("b.mp3", MediaType.AUDIO, 2000, now - 86400))
    store.upsert_entry(_entry("c.jpg", MediaType.IMAGE, 500, now - 86400 * 60))

    # Recherche texte
    assert len(store.search(query="a.mp4")) == 1
    assert len(store.search(query="mp4")) == 1

    # Filtre type
    assert len(store.search(media_types=[MediaType.VIDEO])) == 1
    assert len(store.search(media_types=[MediaType.AUDIO, MediaType.IMAGE])) == 2

    # Filtre taille
    assert len(store.search(min_size=1500)) == 1
    assert len(store.search(max_size=1000)) == 2

    # Filtre date : après = récents
    assert len(store.search(after=now - 1000)) == 1
    assert len(store.search(before=now - 86400 * 30)) == 1  # c.jpg il y a 60 jours

    # Tri
    ordered = store.search(order_by="size", descending=True)
    assert ordered[0].size == 2000

    store.close()


def test_retrouver_fichier_de_plusieurs_mois(tmp_path):
    """Le plus : retrouver un fichier téléchargé il y a plusieurs mois."""
    store = LibraryStore(tmp_path / "lib.db")
    now = time.time()
    # Fichier de 4 mois
    four_months = now - 120 * 86400
    store.upsert_entry(_entry("vacances_ete_2024.mp4", MediaType.VIDEO, 800_000_000, four_months))
    store.upsert_entry(_entry("clip_recent.mp4", MediaType.VIDEO, 100_000, now))
    # Recherche par mot-clé + filtre date large
    results = store.search(query="vacances", after=four_months - 1000, before=now)
    assert len(results) == 1
    assert results[0].filename == "vacances_ete_2024.mp4"
    # Filtre date : il y a plus d'un an ne doit pas le trouver
    assert len(store.search(before=now - 200 * 86400)) == 0
    store.close()


def test_remove_missing(tmp_path):
    store = LibraryStore(tmp_path / "lib.db")
    real = tmp_path / "real.mp4"
    real.write_bytes(b"x" * 100)
    store.upsert_entry(_entry(str(real), MediaType.VIDEO, 100, time.time()))
    ghost = Path("/tmp/ghost_overload_test_nonexistent_xyz.mp4")
    store.upsert_entry(_entry(str(ghost), MediaType.VIDEO, 100, time.time()))
    assert store.count() == 2
    removed = store.remove_missing()
    assert removed == 1
    assert store.count() == 1
    store.close()


def test_stats(tmp_path):
    store = LibraryStore(tmp_path / "lib.db")
    store.upsert_entry(_entry("a.mp4", MediaType.VIDEO, 1000))
    store.upsert_entry(_entry("b.mp3", MediaType.AUDIO, 2000))
    s = store.stats()
    assert s["total"] == 2
    assert s["total_bytes"] == 3000
    assert "video" in s["by_type"]
    store.close()


def test_upsert_mise_a_jour(tmp_path):
    store = LibraryStore(tmp_path / "lib.db")
    p = tmp_path / "file.mp4"
    p.write_bytes(b"abc")
    e = _entry(str(p), MediaType.VIDEO, 3)
    store.upsert_entry(e)
    assert store.count() == 1
    # Mise à jour même chemin, taille différente
    e2 = _entry(str(p), MediaType.VIDEO, 999)
    store.upsert_entry(e2)
    assert store.count() == 1
    got = store.get_by_path(p)
    assert got is not None
    assert got.size == 999
    store.close()
