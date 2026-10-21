import pytest

from overload.core.errors import OverloadError
from overload.core.paths import open_folder
from overload.history.store import DownloadHistoryStore


def test_history_persists_across_reopen_and_never_deletes_files(tmp_path):
    media = tmp_path / "video.mp4"
    media.write_bytes(b"media-bytes")
    db_file = tmp_path / "library.db"

    with DownloadHistoryStore(db_file) as store:
        created = store.record(
            task_id="t-1",
            url="https://example.com/video.mp4",
            filename="video.mp4",
            destination_path=media,
            status="completed",
            size_bytes=len(b"media-bytes"),
            average_speed_bps=500_000,
            duration_seconds=2.0,
            retries_used=1,
        )
        entry_id = created.id

    with DownloadHistoryStore(db_file) as reopened:
        entries = reopened.list_entries(status="completed", query="video")
        assert len(entries) == 1
        assert entries[0].id == entry_id
        assert entries[0].file_exists is True
        assert entries[0].retries_used == 1

        reopened.clear()
        assert reopened.list_entries() == []
        # Règle fondamentale OverLoad : le fichier sur disque n'est jamais supprimé
        assert media.read_bytes() == b"media-bytes"


def test_open_folder_selects_file_or_falls_back_to_existing_parent(tmp_path):
    seen: list[tuple[object, bool]] = []

    def fake_opener(target, *, select_file: bool) -> None:
        seen.append((target, select_file))

    media = tmp_path / "clip.mp4"
    media.write_bytes(b"ok")

    folder = open_folder(media, opener=fake_opener)
    assert folder == tmp_path.resolve()
    assert seen[-1] == (media.resolve(), True)

    # Si le fichier a été déplacé mais que le dossier existe toujours, on ouvre le dossier parent
    media.unlink()
    folder2 = open_folder(media, opener=fake_opener)
    assert folder2 == tmp_path.resolve()
    assert seen[-1] == (tmp_path.resolve(), False)

    # Si même le dossier parent n'existe plus, erreur lisible
    with pytest.raises(OverloadError, match="introuvable"):
        open_folder(tmp_path / "disparu" / "clip.mp4", opener=fake_opener)
