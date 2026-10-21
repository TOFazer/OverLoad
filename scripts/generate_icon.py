"""Génère `assets/overload.ico` (icône multi-résolution Windows) en pur Python standard."""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ICON_PATH = ROOT / "assets" / "overload.ico"

# Polygone de l'éclair normalisé sur [0, 1] x [0, 1]
_BOLT = [
    (0.56, 0.13),
    (0.25, 0.54),
    (0.47, 0.54),
    (0.41, 0.87),
    (0.75, 0.45),
    (0.53, 0.45),
]


def _point_in_poly(x: float, y: float, poly: list[tuple[float, float]]) -> bool:
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-9) + xi):
            inside = not inside
        j = i
    return inside


def _in_rounded_rect(nx: float, ny: float, radius: float = 0.23) -> bool:
    cx = min(max(nx, radius), 1.0 - radius)
    cy = min(max(ny, radius), 1.0 - radius)
    dx = nx - cx
    dy = ny - cy
    return (dx * dx + dy * dy) <= (radius * radius)


def _render_png(size: int) -> bytes:
    raw_rows = bytearray()
    samples = ((-0.25, -0.25), (0.25, -0.25), (-0.25, 0.25), (0.25, 0.25))

    for py in range(size):
        raw_rows.append(0)  # filtre PNG = None
        for px in range(size):
            r_sum = g_sum = b_sum = a_sum = 0.0
            for ox, oy in samples:
                nx = (px + 0.5 + ox) / size
                ny = (py + 0.5 + oy) / size
                if not _in_rounded_rect(nx, ny):
                    continue
                if _point_in_poly(nx, ny, _BOLT):
                    r_sum += 255.0
                    g_sum += 255.0
                    b_sum += 255.0
                else:
                    t = (nx + ny) * 0.5
                    r_sum += 245.0 * (1.0 - t) + 234.0 * t
                    g_sum += 158.0 * (1.0 - t) + 88.0 * t
                    b_sum += 11.0 * (1.0 - t) + 12.0 * t
                a_sum += 255.0
            raw_rows.extend(
                (
                    int(r_sum / 4.0),
                    int(g_sum / 4.0),
                    int(b_sum / 4.0),
                    int(a_sum / 4.0),
                )
            )

    def chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    idat = zlib.compress(bytes(raw_rows), level=9)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", idat)
        + chunk(b"IEND", b"")
    )


def generate_ico(output: Path = ICON_PATH) -> Path:
    sizes = (16, 32, 48, 256)
    frames = [(s, _render_png(s)) for s in sizes]
    header = struct.pack("<HHH", 0, 1, len(frames))
    offset = 6 + 16 * len(frames)
    entries = bytearray()
    payloads = bytearray()

    for s, png in frames:
        w_byte = 0 if s >= 256 else s
        entries.extend(struct.pack("<BBBBHHII", w_byte, w_byte, 0, 0, 1, 32, len(png), offset))
        payloads.extend(png)
        offset += len(png)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(header + bytes(entries) + bytes(payloads))
    return output


if __name__ == "__main__":
    written = generate_ico()
    print(f"Icône générée : {written} ({written.stat().st_size} octets)")
