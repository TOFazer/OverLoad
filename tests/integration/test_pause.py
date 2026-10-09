import threading

import pytest

from overload.downloads.engine import DownloadPaused, download_to
from overload.downloads.files import plan_destination
from tests.conftest import PAYLOAD


def test_pause_keeps_partial_file_and_resume_completes(server, tmp_path):
    pause = threading.Event()
    target = plan_destination(tmp_path, "pause.bin")
    calls = {"n": 0}

    def progress(done, total):
        calls["n"] += 1
        if calls["n"] == 2:
            pause.set()

    with pytest.raises(DownloadPaused):
        download_to(
            f"{server}/ok.bin",
            target,
            allow_private_hosts=True,
            progress=progress,
            pause_event=pause,
        )
    part = tmp_path / "pause.bin.part"
    assert part.exists() and 0 < part.stat().st_size < len(PAYLOAD)
    assert not target.exists()

    download_to(f"{server}/ok.bin", target, allow_private_hosts=True)
    assert target.read_bytes() == PAYLOAD
    assert not part.exists()
