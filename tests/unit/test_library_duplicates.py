import time
from pathlib import Path

from overload.library.db import LibraryStore
from overload.library.duplicates import find_duplicates, find_duplicates_in_store
from overload.library.models import MediaEntry, MediaType
from overload.library.scanner import file_hash


def _e(path, h=None, size=100, hp=None):
    return MediaEntry(
        path=Path(path),
        filename=Path(path).name,
        media_type=MediaType.VIDEO,
        extension=".mp4",
        size=size,
        mtime=time.time(),
        hash=h,
        hash_partial=hp,
    )


def test_find_duplicates_by_hash():
    a = _e("a.mp4", h="abc", size=100)
    b = _e("b.mp4", h="abc", size=100)
    c = _e("c.mp4", h="xyz", size=200)
    groups = find_duplicates([a, b, c], use_partial=False)
    assert len(groups) == 1
    assert len(groups[0].entries) == 2
    assert groups[0].hash == "abc"


def test_find_duplicates_by_partial():
    a = _e("a.mp4", size=100, hp="p1")
    b = _e("b.mp4", size=100, hp="p1")
    c = _e("c.mp4", size=200, hp="p1")  # taille différente -> pas doublon
    groups = find_duplicates([a, b, c], use_partial=True)
    assert len(groups) == 1
    assert len(groups[0].entries) == 2


def test_no_false_positive_if_no_hash():
    a = _e("a.mp4", size=100, hp=None)
    b = _e("b.mp4", size=100, hp=None)
    groups = find_duplicates([a, b])
    assert len(groups) == 0


def test_duplicates_never_deletes_files(tmp_path):
    """Garantie : la détection ne supprime rien sur disque."""
    f1 = tmp_path / "a.mp4"
    f2 = tmp_path / "b.mp4"
    f1.write_bytes(b"same content")
    f2.write_bytes(b"same content")
    store = LibraryStore(tmp_path / "lib.db")
    # Simule indexation avec hash
    for p in (f1, f2):
        h = file_hash(p)
        e = MediaEntry(path=p, filename=p.name, media_type=MediaType.VIDEO, extension=".mp4", size=p.stat().st_size, mtime=p.stat().st_mtime, hash=h)
        store.upsert_entry(e)
    groups = find_duplicates_in_store(store)
    assert len(groups) == 1
    # Les fichiers sont toujours là
    assert f1.exists() and f2.exists()
    store.close()


def test_wasted_bytes():
    a = _e("a.mp4", h="abc", size=1000)
    b = _e("b.mp4", h="abc", size=1000)
    c = _e("c.mp4", h="abc", size=1000)
    groups = find_duplicates([a, b, c], use_partial=False)
    assert groups[0].wasted_bytes == 2000
