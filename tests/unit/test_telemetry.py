import urllib.error
from email.message import Message

from overload.core.errors import OverloadError
from overload.core.formatting import format_bytes, format_duration, format_speed
from overload.downloads.telemetry import IssueKind, SpeedEstimator, classify_error


class _FakeClock:
    def __init__(self, now: float = 100.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, delta: float) -> None:
        self.now += delta


def test_formatting_helpers():
    assert format_bytes(512) == "512 o"
    assert format_bytes(1024 * 1024) == "1,00 Mo"
    assert format_speed(2 * 1024 * 1024) == "2,00 Mo/s"
    assert format_speed(0) == "0 o/s"
    assert format_duration(0.4) == "< 1 s"
    assert format_duration(125) == "2 min 05 s"
    assert format_duration(None) == "Indéterminé"


def test_speed_estimator_tracks_real_rate_eta_and_stall():
    clock = _FakeClock()
    est = SpeedEstimator(window_seconds=2.0, stall_threshold_seconds=4.0, clock=clock)
    est.start()

    clock.advance(1.0)
    est.record_bytes(1_000_000)
    speed, eta, _ = est.snapshot(remaining_bytes=3_000_000)
    assert 950_000 <= speed <= 1_050_000
    assert eta is not None and 2.5 <= eta <= 3.5
    assert est.is_stalled()[0] is False

    # Aucune donnée pendant 5 s : la vitesse retombe à 0 et le blocage est détecté
    clock.advance(5.0)
    speed_after, eta_after, _ = est.snapshot(remaining_bytes=3_000_000)
    assert speed_after == 0.0
    assert eta_after is None
    stalled, secs = est.is_stalled()
    assert stalled is True
    assert secs >= 5.0


def test_classify_error_distinguishes_transient_and_permanent():
    drop_err = OverloadError("Téléchargement interrompu.", "la connexion a été coupée")
    ok, issue = classify_error(drop_err, offset_bytes=512 * 1024, attempt=1)
    assert ok is True
    assert issue is not None and issue.kind is IssueKind.CONNECTION_DROPPED

    http_503 = urllib.error.HTTPError("https://example.com/a.mp4", 503, "Busy", Message(), None)
    try:
        raise OverloadError("Le serveur a refusé la demande.", "réponse HTTP 503.") from http_503
    except OverloadError as wrapped_503:
        ok503, issue503 = classify_error(wrapped_503)
    assert ok503 is True
    assert issue503 is not None and issue503.kind is IssueKind.SERVER_BUSY

    http_404 = urllib.error.HTTPError("https://example.com/a.mp4", 404, "Missing", Message(), None)
    try:
        raise OverloadError("Fichier introuvable.", "le serveur a répondu 404.") from http_404
    except OverloadError as wrapped_404:
        ok404, _ = classify_error(wrapped_404)
    assert ok404 is False
