import threading

import pytest

from overload.core.errors import OverloadError
from overload.downloads.engine import DownloadCancelled, download_to
from tests.conftest import PAYLOAD


def _target(tmp_path, name="video.bin"):
    from overload.downloads.files import plan_destination

    return plan_destination(tmp_path, name)


def test_successful_download_writes_exact_content(server, tmp_path):
    target = download_to(f"{server}/ok.bin", _target(tmp_path), allow_private_hosts=True)
    assert target.read_bytes() == PAYLOAD
    assert not (tmp_path / "video.bin.part").exists()


def test_progress_is_reported(server, tmp_path):
    seen = []
    download_to(
        f"{server}/ok.bin",
        _target(tmp_path),
        allow_private_hosts=True,
        progress=lambda done, total: seen.append((done, total)),
    )
    assert seen[-1] == (len(PAYLOAD), len(PAYLOAD))


def test_private_host_refused_by_default(server, tmp_path):
    with pytest.raises(OverloadError):
        download_to(f"{server}/ok.bin", _target(tmp_path))
    assert not (tmp_path / "video.bin").exists()


def test_empty_file_is_never_declared_complete(server, tmp_path):
    with pytest.raises(OverloadError, match="vide"):
        download_to(f"{server}/empty.bin", _target(tmp_path), allow_private_hosts=True)
    assert list(tmp_path.iterdir()) == []


def test_truncated_download_is_incomplete_and_kept_for_resume(server, tmp_path):
    target = _target(tmp_path)
    with pytest.raises(OverloadError, match="incomplet"):
        download_to(f"{server}/truncated.bin", target, allow_private_hosts=True)
    assert not target.exists()
    assert (tmp_path / "video.bin.part").stat().st_size == 100 * 1024


def test_resume_completes_partial_file(server, tmp_path):
    part = tmp_path / "video.bin.part"
    part.write_bytes(PAYLOAD[:200_000])
    target = _target(tmp_path)
    download_to(f"{server}/ok.bin", target, allow_private_hosts=True)
    assert target.read_bytes() == PAYLOAD


def test_existing_file_is_never_overwritten(server, tmp_path):
    existing = tmp_path / "video.bin"
    existing.write_bytes(b"precious")
    with pytest.raises(OverloadError, match="déjà ce nom"):
        download_to(f"{server}/ok.bin", existing, allow_private_hosts=True)
    assert existing.read_bytes() == b"precious"


def test_http_404_gives_readable_error(server, tmp_path):
    with pytest.raises(OverloadError, match="introuvable"):
        download_to(f"{server}/missing.bin", _target(tmp_path), allow_private_hosts=True)


def test_redirect_to_non_http_scheme_is_refused(server, tmp_path):
    with pytest.raises(OverloadError, match="redirection"):
        download_to(f"{server}/redirect-file", _target(tmp_path), allow_private_hosts=True)


def test_missing_destination_folder(server, tmp_path):
    with pytest.raises(OverloadError, match="introuvable"):
        download_to(f"{server}/ok.bin", tmp_path / "absent" / "x.bin", allow_private_hosts=True)


def test_cancel_removes_partial_file(server, tmp_path):
    cancel = threading.Event()
    target = _target(tmp_path)

    def progress(done, total):
        cancel.set()  # annulation dès le premier bloc reçu

    with pytest.raises(DownloadCancelled):
        download_to(
            f"{server}/ok.bin",
            target,
            allow_private_hosts=True,
            progress=progress,
            cancel_event=cancel,
        )
    assert not target.exists()
    assert not (tmp_path / "video.bin.part").exists()
