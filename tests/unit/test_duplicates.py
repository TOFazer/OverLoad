from overload.downloads.duplicates import DuplicateSource, detect_duplicate
from overload.downloads.urls import parse_url_list
from overload.history.store import DownloadHistoryStore


def test_parse_url_list_handles_comments_blanks_and_inline_links():
    raw = """
    # Liste de médias à récupérer
    https://example.com/un.mp4

    https://example.com/deux.mp4 ; https://example.com/trois.mp3
    """
    parsed = parse_url_list(raw)
    assert [u for _, u in parsed] == [
        "https://example.com/un.mp4",
        "https://example.com/deux.mp4",
        "https://example.com/trois.mp3",
    ]


def test_detects_existing_file_on_disk(tmp_path):
    (tmp_path / "film.mp4").write_bytes(b"123456")
    dup = detect_duplicate("https://example.com/film.mp4", tmp_path)
    assert dup is not None
    assert dup.source is DuplicateSource.EXISTING_FILE
    assert dup.existing_size == 6


def test_detects_active_task_in_queue(tmp_path):
    dup = detect_duplicate(
        "https://example.com/film.mp4",
        tmp_path,
        active_items=[("t1", "https://example.com/film.mp4", tmp_path / "film.mp4")],
    )
    assert dup is not None
    assert dup.source is DuplicateSource.ACTIVE_TASK
    assert dup.task_id == "t1"


def test_detects_resumable_partial_file(tmp_path):
    (tmp_path / "film.mp4.part").write_bytes(b"partial-content")
    dup = detect_duplicate("https://example.com/film.mp4", tmp_path)
    assert dup is not None
    assert dup.source is DuplicateSource.PARTIAL_FILE
    assert dup.resumable is True


def test_detects_history_entry_only_if_file_still_exists(tmp_path):
    other_dir = tmp_path / "archive"
    other_dir.mkdir()
    saved = other_dir / "ancien_nom.mp4"
    saved.write_bytes(b"contenu")

    with DownloadHistoryStore(tmp_path / "library.db") as store:
        store.record(
            task_id="old1",
            url="https://example.com/film.mp4",
            filename="ancien_nom.mp4",
            destination_path=saved,
            status="completed",
            size_bytes=7,
        )
        dup = detect_duplicate("https://example.com/film.mp4", tmp_path, history=store)
        assert dup is not None
        assert dup.source is DuplicateSource.HISTORY_FILE

        # Si le fichier a été supprimé depuis, il ne doit plus bloquer le re-téléchargement
        saved.unlink()
        assert detect_duplicate("https://example.com/film.mp4", tmp_path, history=store) is None
