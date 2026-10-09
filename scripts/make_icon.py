"""Génère assets/overload.png et assets/overload.ico (à relancer après modification du dessin).

Usage : python scripts/make_icon.py
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[1]
SIZES = (16, 32, 48, 256)


def draw(size: int) -> QImage:
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    p = QPainter(image)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    s = float(size)
    grad = QLinearGradient(QPointF(0, 0), QPointF(s, s))
    grad.setColorAt(0.0, QColor("#2f6fed"))
    grad.setColorAt(1.0, QColor("#7b3ff2"))
    path = QPainterPath()
    path.addRoundedRect(QRectF(s * 0.04, s * 0.04, s * 0.92, s * 0.92), s * 0.22, s * 0.22)
    p.fillPath(path, grad)
    pen = QPen(QColor("#ffffff"), max(1.0, s * 0.09))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    # flèche de téléchargement : tige + pointe + base
    p.drawLine(QPointF(s * 0.5, s * 0.22), QPointF(s * 0.5, s * 0.62))
    p.drawLine(QPointF(s * 0.32, s * 0.48), QPointF(s * 0.5, s * 0.66))
    p.drawLine(QPointF(s * 0.68, s * 0.48), QPointF(s * 0.5, s * 0.66))
    p.drawLine(QPointF(s * 0.3, s * 0.78), QPointF(s * 0.7, s * 0.78))
    p.end()
    return image


def png_bytes(image: QImage) -> bytes:
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(QByteArray(buffer.data()))


def write_ico(path: Path, images: list[tuple[int, bytes]]) -> None:
    """ICO avec entrées PNG (format accepté par Windows Vista et plus récent)."""
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    directory = b""
    data = b""
    for size, blob in images:
        dim = 0 if size >= 256 else size
        directory += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(blob), offset)
        offset += len(blob)
        data += blob
    path.write_bytes(header + directory + data)


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv[:1])  # noqa: F841
    assets = ROOT / "assets"
    assets.mkdir(exist_ok=True)
    big = draw(256)
    big.save(str(assets / "overload.png"), "PNG")
    write_ico(assets / "overload.ico", [(s, png_bytes(draw(s))) for s in SIZES])
    print("assets/overload.png et assets/overload.ico écrits")
    return 0


if __name__ == "__main__":
    sys.exit(main())
