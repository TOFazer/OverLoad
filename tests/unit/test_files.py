from overload.downloads.files import (
    MAX_NAME_LENGTH,
    filename_from_url,
    is_inside,
    plan_destination,
    sanitize_filename,
)


def test_sanitize_removes_path_traversal():
    assert sanitize_filename("../../etc/passwd") == "passwd"
    assert sanitize_filename("..\\..\\Windows\\win.ini") == "win.ini"


def test_sanitize_replaces_invalid_windows_characters():
    assert sanitize_filename('a<b>c:d"e|f?g*.mp4') == "a_b_c_d_e_f_g_.mp4"


def test_sanitize_handles_reserved_names():
    assert sanitize_filename("CON.mp4") == "_CON.mp4"
    assert sanitize_filename("lpt1") == "_lpt1"


def test_sanitize_keeps_accents_and_spaces():
    assert sanitize_filename("Vidéo été 2026.mp4") == "Vidéo été 2026.mp4"


def test_sanitize_fallbacks_and_length():
    assert sanitize_filename("...") == "fichier"
    assert sanitize_filename("") == "fichier"
    long = sanitize_filename("x" * 400 + ".mkv")
    assert len(long) <= MAX_NAME_LENGTH
    assert long.endswith(".mkv")


def test_filename_from_url_decodes_and_strips_query():
    assert filename_from_url("https://example.com/dossier/Mon%20clip.mp4?token=1") == "Mon clip.mp4"


def test_plan_destination_never_overwrites(tmp_path):
    (tmp_path / "clip.mp4").write_bytes(b"original")
    chosen = plan_destination(tmp_path, "clip.mp4")
    assert chosen.name == "clip (2).mp4"
    assert (tmp_path / "clip.mp4").read_bytes() == b"original"


def test_plan_destination_avoids_pending_part_file(tmp_path):
    (tmp_path / "clip.mp4.part").write_bytes(b"partial")
    assert plan_destination(tmp_path, "clip.mp4").name == "clip (2).mp4"


def test_is_inside(tmp_path):
    assert is_inside(tmp_path, tmp_path / "a.mp4")
    assert not is_inside(tmp_path, tmp_path / ".." / "outside.mp4")
