
from overload.library.scanner import file_hash, file_hash_partial, scan_directory, scan_file


def test_scan_file_detects_type(tmp_path):
    f = tmp_path / "video.mp4"
    f.write_bytes(b"fake video content")
    entry = scan_file(f)
    assert entry is not None
    assert entry.media_type.value == "video"
    assert entry.size == len(b"fake video content")
    assert entry.extension == ".mp4"


def test_scan_ignores_part_files(tmp_path):
    f = tmp_path / "video.mp4.part"
    f.write_bytes(b"partial")
    assert scan_file(f) is None


def test_scan_directory_recursive(tmp_path):
    (tmp_path / "a.mp4").write_bytes(b"a")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "b.mp3").write_bytes(b"b")
    entries = scan_directory(tmp_path, recursive=True)
    assert len(entries) == 2
    entries2 = scan_directory(tmp_path, recursive=False)
    # non récursif : seul a.mp4 au root (glob *)
    assert any(e.filename == "a.mp4" for e in entries2)


def test_file_hash(tmp_path):
    f = tmp_path / "f.bin"
    f.write_bytes(b"hello world")
    h = file_hash(f)
    assert len(h) == 64  # sha256 hex
    h2 = file_hash(f)
    assert h == h2
    # partial
    p = file_hash_partial(f)
    assert p


def test_file_hash_distinguishes_different_sizes(tmp_path):
    # Même début mais tailles différentes -> partial différent grâce à size inclus
    f1 = tmp_path / "f1.bin"
    f2 = tmp_path / "f2.bin"
    f1.write_bytes(b"x" * 2048)
    f2.write_bytes(b"x" * 2049)
    assert file_hash_partial(f1) != file_hash_partial(f2)
