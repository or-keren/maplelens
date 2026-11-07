"""Draw the MapleLens icon: a cream maple leaf on a warm orange tile.

Writes, from one drawing:
  src/maplelens/data/icon.ico  the app, Setup, shortcuts, uninstall entry and tray (16-256 px)
  packaging/mac/icon.icns      for the Mac app, once there is one (16-1024 px)
  docs/icon.png                the README header
  docs/social-preview.png      GitHub's link preview, 1280x640; uploaded by hand under
                               the repo's Settings > Social preview

Usage: uv run python scripts/make_icon.py
"""

import os
import struct
import sys
from pathlib import Path

from PySide6.QtCore import QBuffer, QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QGuiApplication,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
)

REPO = Path(__file__).resolve().parent.parent

# Right half of the leaf in a 100x100 box, top tip to where the stem starts; mirrored for
# the left half. The stem is drawn on its own so the small sizes can leave it out.
HALF_LEAF = [
    (50, 4), (53.5, 11), (58, 9), (57, 19), (62, 17), (58, 33), (68, 26), (71, 20),
    (75, 25), (85, 18), (82, 31), (88, 32), (80, 40), (93, 44), (78, 52), (81, 60),
    (70, 58), (64, 62), (58, 58), (52, 66),
]  # fmt: skip
TILT = -12  # degrees; a tilted leaf reads as a leaf, an upright one as a flag
TOP, BOTTOM = "#FFA23A", "#E5482A"  # the tile's gradient
CREAM = "#FFF6E8"
DARK = "#2A1D18"  # the social preview's background, so the tile stands out

ICO_SIZES = (16, 24, 32, 48, 64, 256)
# ICNS entry types by pixel size; 32, 64, 256, 512 and 1024 also serve as @2x of the
# size below.
ICNS_TYPES = [
    (b"icp4", 16), (b"icp5", 32), (b"ic11", 32), (b"ic12", 64), (b"ic07", 128),
    (b"ic08", 256), (b"ic13", 256), (b"ic09", 512), (b"ic14", 512), (b"ic10", 1024),
]  # fmt: skip
ROUND = (Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)


def ico_bytes(pngs: dict[int, bytes]) -> bytes:
    """An .ico holding one PNG per size (Vista and later read PNG entries)."""
    head = struct.pack("<HHH", 0, 1, len(pngs))
    offset = len(head) + 16 * len(pngs)
    entries, data = b"", b""
    for size, png in sorted(pngs.items()):
        entries += struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(png), offset)
        offset += len(png)
        data += png
    return head + entries + data


def icns_bytes(entries: list[tuple[bytes, bytes]]) -> bytes:
    """An .icns from (type, png) pairs: each block is type, big-endian length, data."""
    body = b"".join(t + struct.pack(">I", 8 + len(png)) + png for t, png in entries)
    return b"icns" + struct.pack(">I", 8 + len(body)) + body


def draw_leaf(p: QPainter, small: bool) -> None:
    """The leaf in its 100x100 box. A round-joined outline in the fill colour rounds the
    points off a little; small sizes get a thicker one and no stem."""
    color = QColor(CREAM)
    p.setPen(QPen(color, 4 if small else 2.5, *ROUND))
    p.setBrush(color)
    p.translate(50, 50)
    p.rotate(TILT)
    p.translate(-50, -50)
    left = [(100 - x, y) for x, y in reversed(HALF_LEAF[1:-1])]
    p.drawPolygon(QPolygonF([QPointF(x, y) for x, y in HALF_LEAF + left]))
    if not small:
        stem = QPainterPath(QPointF(50, 60))
        stem.quadTo(QPointF(51, 76), QPointF(46, 89))
        p.setPen(QPen(color, 4.5, *ROUND))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(stem)


def warm(rect: QRectF) -> QLinearGradient:
    g = QLinearGradient(rect.topLeft(), rect.bottomLeft())
    g.setColorAt(0, QColor(TOP))
    g.setColorAt(1, QColor(BOTTOM))
    return g


def icon(size: int, mac: bool = False) -> QImage:
    img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(size / 100, size / 100)
    # Apple's grid puts the tile 824 px wide in a 1024 canvas; Windows fills the square.
    tile = QRectF(10, 10, 80, 80) if mac else QRectF(1, 1, 98, 98)
    radius = tile.width() * (0.225 if mac else 0.2)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(warm(tile))
    p.drawRoundedRect(tile, radius, radius)
    small = size <= 24  # stem dropped, leaf grown: at 16 px the stem is a smudge
    k = tile.width() / 100 * (0.86 if small else 0.72)
    middle = 35 if small else 47  # the leaf's vertical middle, with or without the stem
    p.translate(tile.center().x() - 50 * k, tile.center().y() - middle * k)
    p.scale(k, k)
    draw_leaf(p, small)
    p.end()
    return img


def social() -> QImage:
    w, h = 1280, 640
    img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.fillRect(QRectF(0, 0, w, h), QColor(DARK))
    p.drawImage(QPointF(140, 160), icon(320).convertToFormat(img.format()))
    p.setPen(QColor(CREAM))
    font = QFont()
    font.setPixelSize(120)
    font.setWeight(QFont.Weight.Bold)
    p.setFont(font)
    p.drawText(QRectF(520, 190, 720, 150), Qt.AlignmentFlag.AlignVCenter, "MapleLens")
    font.setPixelSize(38)
    font.setWeight(QFont.Weight.Medium)
    p.setFont(font)
    p.drawText(
        QRectF(524, 340, 720, 110),
        Qt.AlignmentFlag.AlignTop,
        "An open-source overlay\nfor MapleStory Classic",
    )
    p.end()
    return img


def png(img: QImage) -> bytes:
    buf = QBuffer()
    buf.open(QBuffer.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    return bytes(buf.data())


def main() -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    QGuiApplication(sys.argv)
    out = {
        REPO / "src" / "maplelens" / "data" / "icon.ico": ico_bytes(
            {s: png(icon(s)) for s in ICO_SIZES}
        ),
        REPO / "packaging" / "mac" / "icon.icns": icns_bytes(
            [(t, png(icon(s, mac=True))) for t, s in ICNS_TYPES]
        ),
        REPO / "docs" / "icon.png": png(icon(256)),
        REPO / "docs" / "social-preview.png": png(social()),
    }
    for path, data in out.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        print(f"wrote {path.relative_to(REPO)} ({len(data):,} bytes)")


if __name__ == "__main__":
    main()
