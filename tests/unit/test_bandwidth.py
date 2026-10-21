import threading
import time

from overload.downloads.bandwidth import BandwidthLimiter


def test_unlimited_limiter_never_blocks():
    limiter = BandwidthLimiter(limit_bps=None)
    assert limiter.limit_bps is None
    assert limiter.recommended_chunk_size(65536) == 65536
    assert limiter.acquire(1_000_000) is None


def test_limiter_enforces_global_rate_across_threads():
    limit = 200 * 1024  # 200 Ko/s au total
    limiter = BandwidthLimiter(limit_bps=limit)
    total_acquired = 0
    lock = threading.Lock()

    def worker() -> None:
        nonlocal total_acquired
        for _ in range(4):
            assert limiter.acquire(25 * 1024) is None
            with lock:
                total_acquired += 25 * 1024

    t0 = time.monotonic()
    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.monotonic() - t0

    assert total_acquired == 200 * 1024
    # Avec une rafale initiale de 0,25 s (50 Ko), les 150 Ko restants prennent ~0,75 s.
    assert elapsed >= 0.55


def test_pause_and_cancel_events_interrupt_limiter_immediately():
    limiter = BandwidthLimiter(limit_bps=2 * 1024)  # 2 Ko/s très lent
    limiter.acquire(2 * 1024)  # vide le seau

    pause = threading.Event()
    result: list[str | None] = []

    def waiter() -> None:
        result.append(limiter.acquire(64 * 1024, pause_event=pause))

    t0 = time.monotonic()
    t = threading.Thread(target=waiter)
    t.start()
    time.sleep(0.03)
    pause.set()
    limiter.wake_all()
    t.join(timeout=1.0)

    assert not t.is_alive()
    assert time.monotonic() - t0 < 0.5
    assert result == ["paused"]
