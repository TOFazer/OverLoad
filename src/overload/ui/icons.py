"""Icônes vectorielles dessinées avec QPainter (aucune ressource externe).

Le jeu d'icônes est volontairement homogène : traits de 1,7 px, extrémités
arrondies, grille de 24 × 24. Les icônes sont teintées à la volée selon le thème
et la couleur d'accent, puis mises en cache.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
)

_CACHE: dict[tuple[str, str, int, float], QIcon] = {}


def _pen(color: str, width: float) -> QPen:
    pen = QPen(QColor(color), width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def _rounded_rect(painter: QPainter, x: float, y: float, w: float, h: float, r: float) -> None:
    painter.drawRoundedRect(QRectF(x, y, w, h), r, r)


def draw_glyph(painter: QPainter, name: str, color: str, width: float = 1.7) -> None:
    """Dessine une icône dans un repère 24 × 24 (le painter est déjà mis à l'échelle)."""
    painter.setPen(_pen(color, width))
    painter.setBrush(Qt.BrushStyle.NoBrush)

    if name == "home":
        painter.drawPolyline(
            QPolygonF(
                [
                    QPointF(3.5, 10.5),
                    QPointF(12, 3.5),
                    QPointF(20.5, 10.5),
                ]
            )
        )
        painter.drawPolyline(
            QPolygonF(
                [
                    QPointF(5.5, 9.5),
                    QPointF(5.5, 20),
                    QPointF(18.5, 20),
                    QPointF(18.5, 9.5),
                ]
            )
        )
        _rounded_rect(painter, 9.8, 14, 4.4, 6, 1.2)
    elif name == "download":
        painter.drawLine(QPointF(12, 3.5), QPointF(12, 15))
        painter.drawPolyline(QPolygonF([QPointF(7, 10.5), QPointF(12, 15.5), QPointF(17, 10.5)]))
        painter.drawPolyline(
            QPolygonF(
                [
                    QPointF(4, 16.5),
                    QPointF(4, 19.5),
                    QPointF(20, 19.5),
                    QPointF(20, 16.5),
                ]
            )
        )
    elif name == "upload":
        painter.drawLine(QPointF(12, 20), QPointF(12, 8.5))
        painter.drawPolyline(QPolygonF([QPointF(7, 13), QPointF(12, 8), QPointF(17, 13)]))
        painter.drawPolyline(
            QPolygonF(
                [
                    QPointF(4, 6),
                    QPointF(4, 3.5),
                    QPointF(20, 3.5),
                    QPointF(20, 6),
                ]
            )
        )
    elif name == "film":
        _rounded_rect(painter, 3, 4.5, 18, 15, 2.5)
        painter.drawLine(QPointF(8, 4.5), QPointF(8, 19.5))
        painter.drawLine(QPointF(16, 4.5), QPointF(16, 19.5))
        painter.setBrush(QColor(color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPolygon(QPolygonF([QPointF(10.6, 9), QPointF(14.2, 12), QPointF(10.6, 15)]))
    elif name == "settings":
        painter.drawEllipse(QPointF(12, 12), 3.1, 3.1)
        for i in range(8):
            angle = math.radians(i * 45)
            inner, outer = 6.0, 9.1
            painter.drawLine(
                QPointF(12 + inner * math.cos(angle), 12 + inner * math.sin(angle)),
                QPointF(12 + outer * math.cos(angle), 12 + outer * math.sin(angle)),
            )
    elif name == "search":
        painter.drawEllipse(QPointF(10.5, 10.5), 5.8, 5.8)
        painter.drawLine(QPointF(15, 15), QPointF(20, 20))
    elif name == "sun":
        painter.drawEllipse(QPointF(12, 12), 4.1, 4.1)
        for i in range(8):
            angle = math.radians(i * 45)
            painter.drawLine(
                QPointF(12 + 6.6 * math.cos(angle), 12 + 6.6 * math.sin(angle)),
                QPointF(12 + 8.7 * math.cos(angle), 12 + 8.7 * math.sin(angle)),
            )
    elif name == "moon":
        outer = QPainterPath()
        outer.addEllipse(QRectF(3.5, 3.5, 17, 17))
        inner = QPainterPath()
        inner.addEllipse(QRectF(8.4, 2.2, 15.5, 15.5))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(color))
        painter.drawPath(outer.subtracted(inner))
    elif name == "folder":
        path = QPainterPath(QPointF(3, 6.4))
        path.lineTo(8.4, 6.4)
        path.lineTo(10.2, 8.4)
        path.lineTo(21, 8.4)
        path.lineTo(21, 19)
        path.lineTo(3, 19)
        path.closeSubpath()
        painter.drawPath(path)
    elif name == "pause":
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(color))
        _rounded_rect(painter, 7, 5.5, 3.4, 13, 1.4)
        _rounded_rect(painter, 13.6, 5.5, 3.4, 13, 1.4)
    elif name == "play":
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(color))
        painter.drawPolygon(QPolygonF([QPointF(8, 5), QPointF(19, 12), QPointF(8, 19)]))
    elif name == "x":
        painter.drawLine(QPointF(6, 6), QPointF(18, 18))
        painter.drawLine(QPointF(18, 6), QPointF(6, 18))
    elif name == "refresh":
        painter.drawArc(QRectF(4, 4, 16, 16), 40 * 16, 285 * 16)
        painter.drawPolyline(
            QPolygonF([QPointF(17.2, 3.4), QPointF(18.2, 8.2), QPointF(13.4, 7.6)])
        )
    elif name == "trash":
        painter.drawLine(QPointF(4, 6.5), QPointF(20, 6.5))
        painter.drawPolyline(
            QPolygonF([QPointF(9, 6.5), QPointF(9.5, 3.8), QPointF(14.5, 3.8), QPointF(15, 6.5)])
        )
        painter.drawPolyline(
            QPolygonF(
                [
                    QPointF(6, 6.5),
                    QPointF(7, 20.2),
                    QPointF(17, 20.2),
                    QPointF(18, 6.5),
                ]
            )
        )
        painter.drawLine(QPointF(10.2, 10), QPointF(10.6, 16.8))
        painter.drawLine(QPointF(13.8, 10), QPointF(13.4, 16.8))
    elif name == "check":
        painter.drawPolyline(
            QPolygonF([QPointF(4.5, 12.5), QPointF(9.5, 17.5), QPointF(19.5, 6.5)])
        )
    elif name == "alert":
        painter.drawPolyline(
            QPolygonF([QPointF(12, 3.5), QPointF(21.5, 20.2), QPointF(2.5, 20.2), QPointF(12, 3.5)])
        )
        painter.drawLine(QPointF(12, 9), QPointF(12, 14))
        painter.setBrush(QColor(color))
        painter.drawEllipse(QPointF(12, 17.2), 0.9, 0.9)
    elif name == "info":
        painter.drawEllipse(QPointF(12, 12), 8.6, 8.6)
        painter.drawLine(QPointF(12, 10.7), QPointF(12, 16.4))
        painter.setBrush(QColor(color))
        painter.drawEllipse(QPointF(12, 7.7), 0.95, 0.95)
    elif name == "chevron-right":
        painter.drawPolyline(QPolygonF([QPointF(9.5, 5.5), QPointF(16, 12), QPointF(9.5, 18.5)]))
    elif name == "chevron-down":
        painter.drawPolyline(QPolygonF([QPointF(5.5, 9.5), QPointF(12, 16), QPointF(18.5, 9.5)]))
    elif name == "plus":
        painter.drawLine(QPointF(12, 5), QPointF(12, 19))
        painter.drawLine(QPointF(5, 12), QPointF(19, 12))
    elif name == "image":
        _rounded_rect(painter, 3.5, 4.5, 17, 15, 2.4)
        painter.drawEllipse(QPointF(9, 9.7), 1.8, 1.8)
        painter.drawPolyline(
            QPolygonF(
                [
                    QPointF(5.5, 17.5),
                    QPointF(10.5, 12.5),
                    QPointF(14, 15.6),
                    QPointF(16.8, 12.8),
                    QPointF(19.5, 15.5),
                ]
            )
        )
    elif name == "music":
        painter.drawLine(QPointF(9.5, 17.5), QPointF(9.5, 6.5))
        painter.drawLine(QPointF(9.5, 6.5), QPointF(18, 4.5))
        painter.drawLine(QPointF(18, 4.5), QPointF(18, 15))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(color))
        painter.drawEllipse(QPointF(7, 18), 2.6, 2.1)
        painter.drawEllipse(QPointF(15.5, 15.7), 2.6, 2.1)
    elif name == "file":
        path = QPainterPath(QPointF(6, 3.5))
        path.lineTo(14.5, 3.5)
        path.lineTo(19, 8)
        path.lineTo(19, 20.5)
        path.lineTo(6, 20.5)
        path.closeSubpath()
        painter.drawPath(path)
        painter.drawPolyline(QPolygonF([QPointF(14.5, 3.5), QPointF(14.5, 8), QPointF(19, 8)]))
        painter.drawLine(QPointF(9, 13), QPointF(16, 13))
        painter.drawLine(QPointF(9, 16.5), QPointF(14, 16.5))
    elif name == "link":
        painter.save()
        painter.translate(12, 12)
        painter.rotate(-45)
        _rounded_rect(painter, -9.5, -3, 9.5, 6, 2.8)
        _rounded_rect(painter, 0, -3, 9.5, 6, 2.8)
        painter.drawLine(QPointF(-2, 0), QPointF(2, 0))
        painter.restore()
    elif name == "sparkle":
        path = QPainterPath(QPointF(12, 2.8))
        path.cubicTo(12.6, 8.4, 15.6, 11.4, 21.2, 12)
        path.cubicTo(15.6, 12.6, 12.6, 15.6, 12, 21.2)
        path.cubicTo(11.4, 15.6, 8.4, 12.6, 2.8, 12)
        path.cubicTo(8.4, 11.4, 11.4, 8.4, 12, 2.8)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(color))
        painter.drawPath(path)
    elif name == "shield":
        path = QPainterPath(QPointF(12, 2.8))
        path.lineTo(19.5, 6)
        path.lineTo(19.5, 11.4)
        path.cubicTo(19.5, 16.1, 16.6, 19.6, 12, 21.4)
        path.cubicTo(7.4, 19.6, 4.5, 16.1, 4.5, 11.4)
        path.lineTo(4.5, 6)
        path.closeSubpath()
        painter.drawPath(path)
        painter.drawPolyline(
            QPolygonF([QPointF(8.7, 11.8), QPointF(11.2, 14.2), QPointF(15.5, 9.4)])
        )
    elif name == "clock":
        painter.drawEllipse(QPointF(12, 12), 8.6, 8.6)
        painter.drawLine(QPointF(12, 7), QPointF(12, 12.4))
        painter.drawLine(QPointF(12, 12.4), QPointF(15.6, 14.4))
    elif name == "sliders":
        for index, y in enumerate((7.0, 12.0, 17.0)):
            painter.drawLine(QPointF(4, y), QPointF(20, y))
            knob = (15.5, 8.5, 12.5)[index]
            painter.setBrush(QColor(color))
            painter.drawEllipse(QPointF(knob, y), 2.0, 2.0)
            painter.setBrush(Qt.BrushStyle.NoBrush)
    elif name == "gauge":
        painter.drawArc(QRectF(4, 5, 16, 16), 200 * 16, 140 * 16)
        painter.drawLine(QPointF(12, 13), QPointF(16.4, 8.8))
        painter.setBrush(QColor(color))
        painter.drawEllipse(QPointF(12, 13), 1.1, 1.1)
    elif name == "monitor":
        _rounded_rect(painter, 3, 4.5, 18, 12, 2)
        painter.drawLine(QPointF(12, 16.5), QPointF(12, 20))
        painter.drawLine(QPointF(8, 20.5), QPointF(16, 20.5))
    elif name == "palette":
        painter.drawEllipse(QPointF(12, 12), 8.6, 8.6)
        painter.setBrush(QColor(color))
        for x, y in ((8.4, 9.2), (12, 7.4), (15.6, 9.2)):
            painter.drawEllipse(QPointF(x, y), 1.15, 1.15)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawArc(QRectF(8.5, 11.5, 9, 7.5), 190 * 16, 160 * 16)
    elif name == "external":
        painter.drawPolyline(
            QPolygonF(
                [
                    QPointF(13, 4.5),
                    QPointF(19.5, 4.5),
                    QPointF(19.5, 11),
                ]
            )
        )
        painter.drawLine(QPointF(19, 5), QPointF(11.5, 12.5))
        painter.drawPolyline(
            QPolygonF(
                [
                    QPointF(17, 14),
                    QPointF(17, 19.5),
                    QPointF(4.5, 19.5),
                    QPointF(4.5, 7),
                    QPointF(10, 7),
                ]
            )
        )
    elif name == "list":
        painter.setBrush(QColor(color))
        for y in (6.5, 12, 17.5):
            painter.drawEllipse(QPointF(5.5, y), 1.15, 1.15)
            painter.drawLine(QPointF(9.5, y), QPointF(19.5, y))
    elif name == "database":
        painter.drawEllipse(QPointF(12, 6), 7.5, 3.1)
        painter.drawLine(QPointF(4.5, 6), QPointF(4.5, 18))
        painter.drawLine(QPointF(19.5, 6), QPointF(19.5, 18))
        painter.drawArc(QRectF(4.5, 14.9, 15, 6.2), 180 * 16, 180 * 16)
        painter.drawArc(QRectF(4.5, 10.4, 15, 6.2), 180 * 16, 180 * 16)
    elif name == "wifi":
        painter.drawArc(QRectF(3, 6, 18, 14), 40 * 16, 100 * 16)
        painter.drawArc(QRectF(6.4, 9.4, 11.2, 9), 40 * 16, 100 * 16)
        painter.setBrush(QColor(color))
        painter.drawEllipse(QPointF(12, 17.4), 1.4, 1.4)
    elif name == "hard-drive":
        _rounded_rect(painter, 3, 5, 18, 14, 2.4)
        painter.drawLine(QPointF(3, 13.5), QPointF(21, 13.5))
        painter.setBrush(QColor(color))
        painter.drawEllipse(QPointF(17.2, 16.6), 0.95, 0.95)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(QPointF(6.5, 16.6), QPointF(12.5, 16.6))
    elif name == "wand":
        painter.drawLine(QPointF(5, 19), QPointF(15, 9))
        painter.drawLine(QPointF(15, 9), QPointF(17, 7))
        painter.drawLine(QPointF(17.5, 4), QPointF(17.5, 6.5))
        painter.drawLine(QPointF(16.25, 5.25), QPointF(18.75, 5.25))
        painter.drawLine(QPointF(20.2, 12), QPointF(20.2, 14))
        painter.drawLine(QPointF(19.2, 13), QPointF(21.2, 13))
    elif name == "copy":
        _rounded_rect(painter, 8, 8, 12, 12, 2)
        painter.drawPolyline(
            QPolygonF(
                [
                    QPointF(16, 8),
                    QPointF(16, 4),
                    QPointF(4, 4),
                    QPointF(4, 16),
                    QPointF(8, 16),
                ]
            )
        )
    elif name == "eye":
        path = QPainterPath(QPointF(2.5, 12))
        path.cubicTo(6, 6.8, 9, 5.4, 12, 5.4)
        path.cubicTo(15, 5.4, 18, 6.8, 21.5, 12)
        path.cubicTo(18, 17.2, 15, 18.6, 12, 18.6)
        path.cubicTo(9, 18.6, 6, 17.2, 2.5, 12)
        painter.drawPath(path)
        painter.drawEllipse(QPointF(12, 12), 3, 3)
    elif name == "edit":
        painter.drawPolyline(
            QPolygonF(
                [
                    QPointF(4, 20),
                    QPointF(5.4, 15.2),
                    QPointF(16.4, 4.2),
                    QPointF(19.8, 7.6),
                    QPointF(8.8, 18.6),
                    QPointF(4, 20),
                ]
            )
        )
        painter.drawLine(QPointF(14.2, 6.4), QPointF(17.6, 9.8))
    elif name == "zap":
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(color))
        painter.drawPolygon(
            QPolygonF(
                [
                    QPointF(13.4, 2.6),
                    QPointF(5.8, 13.4),
                    QPointF(11.1, 13.4),
                    QPointF(9.8, 21.4),
                    QPointF(18.4, 10.2),
                    QPointF(12.9, 10.2),
                ]
            )
        )
    else:  # pragma: no cover - secours
        painter.drawEllipse(QPointF(12, 12), 8, 8)


def _render(name: str, color: str, size: int, width: float) -> QPixmap:
    dpr = 2
    pix = QPixmap(size * dpr, size * dpr)
    pix.fill(Qt.GlobalColor.transparent)
    pix.setDevicePixelRatio(dpr)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.scale(size / 24.0, size / 24.0)
    draw_glyph(painter, name, color, width)
    painter.end()
    return pix


def icon(name: str, color: str = "#F3F5F9", size: int = 20, width: float = 1.7) -> QIcon:
    """Retourne une QIcon teintée, mise en cache."""
    key = (name, color, size, width)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached
    result = QIcon(_render(name, color, size, width))
    _CACHE[key] = result
    return result


def pixmap(name: str, color: str, size: int = 20, width: float = 1.7) -> QPixmap:
    return _render(name, color, size, width)


def clear_icon_cache() -> None:
    _CACHE.clear()
