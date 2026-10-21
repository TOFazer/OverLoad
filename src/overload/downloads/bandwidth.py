"""Limitation globale de bande passante (algorithme du seau à jetons).

Un seul limiteur est partagé entre tous les téléchargements actifs afin que
le débit cumulé ne sature jamais la connexion Internet de l'utilisateur.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

MIN_SLICE_BYTES = 4 * 1024
BURST_WINDOW_SECONDS = 0.25


class BandwidthLimiter:
    """Limiteur de débit global thread-safe et réactif aux pauses/annulations."""

    def __init__(
        self,
        limit_bps: int | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._cond = threading.Condition()
        self._clock = clock
        self._limit_bps: int | None = None
        self._tokens: float = 0.0
        self._last_refill: float = self._clock()
        self.set_limit_bps(limit_bps)

    @property
    def limit_bps(self) -> int | None:
        with self._cond:
            return self._limit_bps

    def set_limit_bps(self, limit_bps: int | None) -> None:
        """Modifie la limite globale (en octets/s) immédiatement, ou `None` / `0` pour illimité."""
        with self._cond:
            now = self._clock()
            if limit_bps is None or limit_bps <= 0:
                self._limit_bps = None
                self._tokens = 0.0
            else:
                rate = max(1024, int(limit_bps))
                self._limit_bps = rate
                self._tokens = min(float(rate) * BURST_WINDOW_SECONDS, float(rate))
            self._last_refill = now
            self._cond.notify_all()

    def recommended_chunk_size(self, default_chunk: int) -> int:
        """Adapte la taille des lectures réseau pour éviter des à-coups à bas débit."""
        with self._cond:
            rate = self._limit_bps
        if rate is None:
            return default_chunk
        target = rate // 8
        return max(MIN_SLICE_BYTES, min(default_chunk, target))

    def acquire(
        self,
        num_bytes: int,
        *,
        cancel_event: threading.Event | None = None,
        pause_event: threading.Event | None = None,
    ) -> str | None:
        """Attend les jetons nécessaires pour `num_bytes`.

        Retourne `"cancelled"` ou `"paused"` immédiatement si l'un des événements
        est déclenché pendant l'attente, sinon `None`.
        """
        if num_bytes <= 0:
            return None

        with self._cond:
            while True:
                if cancel_event is not None and cancel_event.is_set():
                    return "cancelled"
                if pause_event is not None and pause_event.is_set():
                    return "paused"

                rate = self._limit_bps
                if rate is None:
                    return None

                now = self._clock()
                elapsed = max(0.0, now - self._last_refill)
                self._last_refill = now
                max_burst = max(float(num_bytes), float(rate) * BURST_WINDOW_SECONDS)
                self._tokens = min(max_burst, self._tokens + elapsed * float(rate))

                if self._tokens >= num_bytes:
                    self._tokens -= num_bytes
                    return None

                deficit = num_bytes - self._tokens
                wait_seconds = min(0.05, deficit / float(rate))
                self._cond.wait(timeout=max(0.005, wait_seconds))

    def refund(self, unused_bytes: int) -> None:
        """Restitue les jetons non consommés lorsque la lecture socket est partielle."""
        if unused_bytes <= 0:
            return
        with self._cond:
            rate = self._limit_bps
            if rate is None:
                return
            max_burst = float(rate) * BURST_WINDOW_SECONDS
            self._tokens = min(max_burst, self._tokens + unused_bytes)
            self._cond.notify_all()

    def wake_all(self) -> None:
        """Réveille immédiatement tous les ouvriers en attente (pause, annulation, arrêt)."""
        with self._cond:
            self._cond.notify_all()
