import threading

import pytest

from overload.core.errors import OverloadError
from overload.downloads.engine import DownloadCancelled, download_to
from tests.integration.conftest import PAYLOAD


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
    import json

    (tmp_path / "video.bin.part.json").write_text(json.dumps({
        "url": f"{server}/ok.bin", "validator": '"fixture-v1"',
        "size": 200_000, "total": len(PAYLOAD),
    }))
    target = tmp_path / "video.bin"
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


def test_pause_preserves_partial_and_resumes(server, tmp_path):
    from overload.downloads.engine import DownloadPaused

    pause = threading.Event()
    target = tmp_path / "pause.bin"

    def progress(done, total):
        if done > 0:
            pause.set()

    with pytest.raises(DownloadPaused):
        download_to(
            f"{server}/ok.bin", target, allow_private_hosts=True,
            pause_event=pause, progress=progress,
        )
    assert 0 < (tmp_path / "pause.bin.part").stat().st_size < len(PAYLOAD)
    assert (tmp_path / "pause.bin.part.json").exists()
    download_to(f"{server}/ok.bin", target, allow_private_hosts=True)
    assert target.read_bytes() == PAYLOAD
    assert not (tmp_path / "pause.bin.part.json").exists()


def test_partial_without_provenance_restarts_safely(server, tmp_path):
    (tmp_path / "unsafe.bin.part").write_bytes(b"malicious bytes")
    target = tmp_path / "unsafe.bin"
    download_to(f"{server}/ok.bin", target, allow_private_hosts=True)
    assert target.read_bytes() == PAYLOAD


def test_server_ignores_range_restarts_not_appends(server, tmp_path):
    pause = threading.Event()
    from overload.downloads.engine import DownloadPaused

    target = tmp_path / "ignored.bin"
    with pytest.raises(DownloadPaused):
        download_to(
            f"{server}/no-range.bin", target, allow_private_hosts=True,
            pause_event=pause, progress=lambda done, total: pause.set() if done else None,
        )
    download_to(f"{server}/no-range.bin", target, allow_private_hosts=True)
    assert target.read_bytes() == PAYLOAD


def test_bad_content_range_is_not_appended(server, tmp_path):
    import json

    target = tmp_path / "bad.bin"
    part = tmp_path / "bad.bin.part"
    part.write_bytes(PAYLOAD[:10])
    (tmp_path / "bad.bin.part.json").write_text(json.dumps({
        "url": f"{server}/bad-range.bin", "validator": '"fixture-v1"',
        "size": 10, "total": len(PAYLOAD),
    }))
    with pytest.raises(OverloadError, match="reprise invalide"):
        download_to(f"{server}/bad-range.bin", target, allow_private_hosts=True)
    assert part.read_bytes() == PAYLOAD[:10]


def test_reject_html_and_size_limit(server, tmp_path):
    with pytest.raises(OverloadError, match="page Web"):
        download_to(f"{server}/html", tmp_path / "page.mp4", allow_private_hosts=True)
    with pytest.raises(OverloadError, match="volumineux"):
        download_to(f"{server}/ok.bin", tmp_path / "large.bin", max_bytes=99,
                    allow_private_hosts=True)
    assert not (tmp_path / "large.bin.part").exists()


def test_sha256_mismatch_does_not_publish(server, tmp_path):
    target = tmp_path / "hash.bin"
    with pytest.raises(OverloadError, match="SHA-256 différente"):
        download_to(f"{server}/ok.bin", target, sha256="0" * 64, allow_private_hosts=True)
    assert not target.exists()
    assert not (tmp_path / "hash.bin.part").exists()
