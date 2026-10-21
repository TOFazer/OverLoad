"""Mise en forme lisible des tailles, vitesses et durées."""

from __future__ import annotations

import math

_UNITS = ("o", "Ko", "Mo", "Go", "To")


def format_bytes(num_bytes: int | float | None) -> str:
    """Formate un nombre d'octets en unité lisible (ex. « 1,50 Mo »)."""
    if num_bytes is None or num_bytes < 0:
        return "Inconnue"
    value = float(num_bytes)
    if value < 1024:
        return f"{int(value)} o"
    unit_index = 0
    while value >= 1024 and unit_index < len(_UNITS) - 1:
        value /= 1024.0
        unit_index += 1
    formatted = f"{value:.2f}".replace(".", ",")
    return f"{formatted} {_UNITS[unit_index]}"


def format_speed(bytes_per_second: float | None) -> str:
    """Formate une vitesse en octets/seconde (ex. « 2,40 Mo/s »)."""
    if bytes_per_second is None or bytes_per_second <= 0 or math.isnan(bytes_per_second):
        return "0 o/s"
    return f"{format_bytes(bytes_per_second)}/s"


def format_duration(seconds: float | None) -> str:
    """Formate un temps restant estimé en français lisible."""
    if seconds is None or math.isnan(seconds) or math.isinf(seconds) or seconds < 0:
        return "Indéterminé"
    if seconds < 1:
        return "< 1 s"
    total = int(round(seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours > 0:
        if minutes > 0:
            return f"{hours} h {minutes:02d} min"
        return f"{hours} h"
    if minutes > 0:
        return f"{minutes} min {secs:02d} s"
    return f"{secs} s"
