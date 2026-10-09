"""Formatage lisible des tailles, vitesses et durées (français)."""

from __future__ import annotations

_UNITS = ("o", "Ko", "Mo", "Go", "To")


def format_bytes(value: float | int | None) -> str:
    if value is None:
        return "—"
    size = float(value)
    for unit in _UNITS:
        if size < 1024 or unit == _UNITS[-1]:
            return f"{size:.0f} {unit}" if unit == "o" else f"{size:.1f} {unit}".replace(".", ",")
        size /= 1024
    return "—"


def format_speed(bytes_per_second: float | None) -> str:
    if not bytes_per_second or bytes_per_second <= 0:
        return "—"
    return f"{format_bytes(bytes_per_second)}/s"


def format_duration(seconds: float | None) -> str:
    if seconds is None or seconds < 0:
        return "—"
    total = int(round(seconds))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours} h {minutes:02d} min"
    if minutes:
        return f"{minutes} min {secs:02d} s"
    return f"{secs} s"
