"""Mesure de la vitesse réelle, du temps restant estimé et diagnostic réseau."""

from __future__ import annotations

import ssl
import threading
import time
import urllib.error
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from overload.core.errors import OverloadError
from overload.core.formatting import format_bytes


class IssueKind(StrEnum):
    CONNECTION_DROPPED = "connection_dropped"
    TIMEOUT = "timeout"
    DNS_ERROR = "dns_error"
    SERVER_BUSY = "server_busy"
    STALLED = "stalled"
    RANGE_UNSUPPORTED = "range_unsupported"
    TLS_ERROR = "tls_error"
    NETWORK_ERROR = "network_error"


@dataclass(frozen=True)
class ConnectionIssue:
    """Incident ou avertissement réseau observé sur un téléchargement."""

    kind: IssueKind
    message: str
    detail: str = ""
    attempt: int = 0
    offset_bytes: int = 0
    recoverable: bool = True
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            object.__setattr__(self, "timestamp", datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "message": self.message,
            "detail": self.detail,
            "attempt": self.attempt,
            "offset_bytes": self.offset_bytes,
            "offset_human": format_bytes(self.offset_bytes) if self.offset_bytes > 0 else "",
            "recoverable": self.recoverable,
            "timestamp": self.timestamp,
        }


def classify_error(
    exc: BaseException,
    *,
    offset_bytes: int = 0,
    attempt: int = 0,
) -> tuple[bool, ConnectionIssue | None]:
    """Détermine si `exc` est une panne réseau transitoire permettant une reprise auto.

    Retourne `(est_récupérable, incident_réseau_associé)`.
    Les erreurs permanentes (URL invalide, HTTP 404/403, adresse privée bloquée,
    disque plein, fichier vide) retournent `(False, ...)`.
    """
    cause = exc.__cause__
    msg = exc.what if isinstance(exc, OverloadError) else str(exc)
    detail = exc.cause if isinstance(exc, OverloadError) else str(exc)
    combined = f"{msg} {detail}".lower()

    if isinstance(cause, ssl.SSLError) or "ssl" in combined or "certificate" in combined:
        return (
            False,
            ConnectionIssue(
                kind=IssueKind.TLS_ERROR,
                message=(
                    "Erreur de sécurité HTTPS "
                    "(certificat invalide ou connexion chiffrée refusée)."
                ),
                detail=detail,
                attempt=attempt,
                offset_bytes=offset_bytes,
                recoverable=False,
            ),
        )

    if "nom de domaine introuvable" in combined or "résolution dns" in combined:
        return (
            True,
            ConnectionIssue(
                kind=IssueKind.DNS_ERROR,
                message=(
                    "Problème de résolution DNS — "
                    "connexion Internet instable ou domaine injoignable."
                ),
                detail=detail,
                attempt=attempt,
                offset_bytes=offset_bytes,
                recoverable=True,
            ),
        )

    if isinstance(cause, urllib.error.HTTPError):
        code = cause.code
        if code in (408, 429, 500, 502, 503, 504):
            label = (
                "Trop de requêtes (HTTP 429)"
                if code == 429
                else f"Serveur temporairement indisponible (HTTP {code})"
            )
            return (
                True,
                ConnectionIssue(
                    kind=IssueKind.SERVER_BUSY,
                    message=f"{label} — nouvelle tentative automatique prévue.",
                    detail=detail,
                    attempt=attempt,
                    offset_bytes=offset_bytes,
                    recoverable=True,
                ),
            )
        return (False, None)

    if isinstance(cause, TimeoutError) or "timed out" in combined or "délai" in combined:
        return (
            True,
            ConnectionIssue(
                kind=IssueKind.TIMEOUT,
                message="Délai d'attente réseau dépassé — le serveur ne répond plus.",
                detail=detail,
                attempt=attempt,
                offset_bytes=offset_bytes,
                recoverable=True,
            ),
        )

    if "interrompu" in combined or "incomplet" in combined:
        resume_note = (
            f" Reprise depuis {format_bytes(offset_bytes)}."
            if offset_bytes > 0
            else ""
        )
        return (
            True,
            ConnectionIssue(
                kind=IssueKind.CONNECTION_DROPPED,
                message=f"Connexion coupée pendant le transfert.{resume_note}",
                detail=detail,
                attempt=attempt,
                offset_bytes=offset_bytes,
                recoverable=True,
            ),
        )

    if "connexion impossible" in combined:
        return (
            True,
            ConnectionIssue(
                kind=IssueKind.NETWORK_ERROR,
                message="Impossible de joindre le serveur — vérification de la connexion en cours.",
                detail=detail,
                attempt=attempt,
                offset_bytes=offset_bytes,
                recoverable=True,
            ),
        )

    return (False, None)


class SpeedEstimator:
    """Estime la vitesse réelle sur fenêtre glissante, le temps restant et les blocages."""

    def __init__(
        self,
        *,
        window_seconds: float = 3.0,
        stall_threshold_seconds: float = 4.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._window = max(0.5, window_seconds)
        self._stall_threshold = max(1.0, stall_threshold_seconds)
        self._clock = clock
        self._lock = threading.Lock()
        self._samples: deque[tuple[float, int]] = deque()
        self._started_at: float | None = None
        self._last_data_at: float | None = None
        self._ewma_bps: float = 0.0

    def start(self) -> None:
        now = self._clock()
        with self._lock:
            self._samples.clear()
            self._started_at = now
            self._last_data_at = now
            self._ewma_bps = 0.0

    def reset(self) -> None:
        with self._lock:
            self._samples.clear()
            self._started_at = None
            self._last_data_at = None
            self._ewma_bps = 0.0

    def record_bytes(self, delta_bytes: int) -> None:
        if delta_bytes <= 0:
            return
        now = self._clock()
        with self._lock:
            if self._started_at is None:
                self._started_at = now
            self._last_data_at = now
            self._samples.append((now, delta_bytes))
            self._prune_locked(now)
            instant = self._window_speed_locked(now)
            if self._ewma_bps <= 0:
                self._ewma_bps = instant
            else:
                self._ewma_bps = 0.35 * instant + 0.65 * self._ewma_bps

    def snapshot(self, *, remaining_bytes: int | None) -> tuple[float, float | None, float]:
        """Retourne `(vitesse_réelle_bps, eta_secondes, secondes_sans_données)`."""
        now = self._clock()
        with self._lock:
            self._prune_locked(now)
            idle = (now - self._last_data_at) if self._last_data_at is not None else 0.0
            instant = self._window_speed_locked(now)
            if idle > 1.5 and instant == 0.0:
                self._ewma_bps = 0.0
            eta: float | None = None
            rate_for_eta = self._ewma_bps if self._ewma_bps > 0 else instant
            if remaining_bytes is not None:
                if remaining_bytes <= 0:
                    eta = 0.0
                elif rate_for_eta > 1.0:
                    eta = remaining_bytes / rate_for_eta
            return (instant, eta, idle)

    def is_stalled(self) -> tuple[bool, float]:
        """Vrai si aucune donnée n'a été reçue depuis au moins `stall_threshold_seconds`."""
        now = self._clock()
        with self._lock:
            if self._last_data_at is None:
                return (False, 0.0)
            idle = max(0.0, now - self._last_data_at)
            return (idle >= self._stall_threshold, idle)

    def _prune_locked(self, now: float) -> None:
        cutoff = now - self._window
        while self._samples and self._samples[0][0] < cutoff:
            self._samples.popleft()

    def _window_speed_locked(self, now: float) -> float:
        if not self._samples:
            return 0.0
        total_bytes = sum(b for _, b in self._samples)
        first_ts = self._samples[0][0]
        span = max(now - first_ts, min(0.25, self._window))
        if self._started_at is not None:
            span = max(span, min(now - self._started_at, self._window))
        return total_bytes / max(span, 0.05)
