"""Player position reader: the yellow "you" dot and the NPC markers on the minimap.

The minimap's map area sits in a white frame under the title. The map picture fills the
frame's height; when it is narrower than the window it is centred on see-through padding.
"""

from dataclasses import dataclass, field

import cv2
import numpy as np

from maplelens.readers import glyphs, map_name

# Frame rows relative to the minimap_title anchor: the map area's first row.
MAP_DY = 66
# The frame's white side line runs 2 px left of the anchor, down to 2 rows past the map.
SIDE_DX, SIDE_PAST = -2, 2
# The map area ends 3 px before the title box's end (map_name's plain-panel width).
RIGHT_PAD = 3
# Min channel of the frame's white lines; padding over a bright scene stays below it.
WHITE = 245
# Padding edges: columns where at least half the rows step by this much (max channel)
# from the next column. Fixtures: 80+ at real edges, under 35 inside full-width maps.
EDGE_STEP = 60
# Left and right padding may differ by this much (odd widths, resizing).
EDGE_SLACK = 2
# The dot's yellow fill (BGR); the party marker's orange has green under 160, its "+"
# blue under 25. Normalized, the fill is a 6x6 disc of 23-24 px at every resolution;
# yellow map art (Henesys roofs: 7x5, 6x4) fails the size or the squareness.
DOT_LO, DOT_HI = (25, 180, 200), (110, 255, 255)
DOT_SIDE = (5, 7)
DOT_SQUARE = 1  # max width - height difference
DOT_AREA = (18, 28)
# Its fill is orange-yellow: R over G by 23-26 (mean over the blob) on every fixture and Mac
# grab. A Mac's fullscreen stretches the picture 1.107x and blurs the dot to 6x5 of 19-21
# px, a Henesys roof's size, but the roofs are green-yellow (R - G = -15).
DOT_RG = 10
# NPC markers: green (BGR) ovals, 4x7 px of 20-23 px normalized at 2560 (Kerning City,
# Henesys, Perion, Lith Harbor). Partly covered ones (3x7) are dropped.
NPC_LO, NPC_HI = (0, 170, 0), (90, 255, 90)
NPC_W, NPC_H = 4, (6, 7)
NPC_AREA = (18, 24)
# Portal spirals: a grey ring round a blue centre. The blue (B at least PORTAL_B and
# PORTAL_BR over R), closed by 3x3, is an 8x8 blob of 51-52 px normalized at 1366, 1920
# and 2560; Lith Harbor's sea gives only smaller bits.
PORTAL_B, PORTAL_BR = 140, 80
PORTAL_SIDE, PORTAL_AREA = 8, (48, 56)


@dataclass(frozen=True)
class MinimapView:
    """What the minimap window shows, in px of its visible map area."""

    size: tuple[int, int]
    dot: tuple[float, float]  # the "you" dot's centre
    npcs: tuple[tuple[float, float], ...]  # NPC marker centres
    portals: tuple[tuple[float, float], ...] = ()  # portal spiral centres
    # The map area itself (normalized BGR, `size` px), for matching against a map picture.
    pixels: np.ndarray | None = field(default=None, compare=False, repr=False)

    @property
    def fraction(self) -> tuple[float, float]:
        """The dot as (fx, fy) fractions of the visible map area."""
        return self.dot[0] / self.size[0], self.dot[1] / self.size[1]


def _map_area(frame: np.ndarray, x: int, y: int) -> tuple[int, int, int, int] | None:
    """(x0, y0, x1, y1) of the map picture, or None if the frame isn't intact."""
    y0 = y + MAP_DY
    w = map_name._plain(frame[y + map_name.TITLE_DY, x + map_name.TITLE_DX :], map_name.PANEL)
    x0, x1 = x, x + map_name.TITLE_DX + w - RIGHT_PAD
    side = frame[y0:, x + SIDE_DX].min(axis=1) >= WHITE
    y1 = y0 + (int(np.argmin(side)) if not side.all() else len(side)) - SIDE_PAST
    if y1 - y0 < 10 or x1 - x0 < 20 or y1 + 1 >= frame.shape[0]:
        return None
    # A window over the map breaks the frame's bottom line (or the right one).
    if frame[y1 + 1, x0:x1].min() < WHITE or frame[y0:y1, x1 + 2].min() < WHITE:
        return None
    a = frame[y0:y1, x0:x1].astype(int)
    step = np.median(np.abs(np.diff(a, axis=1)).max(axis=2), axis=0)  # col i | i+1
    edges = np.flatnonzero(step >= EDGE_STEP) + 1
    width = x1 - x0
    pairs = [
        (step[left - 1] + step[right - 1], left, right)
        for left in edges[edges < width // 2]
        for right in edges[edges > width // 2]
        if abs(left - (width - right)) <= EDGE_SLACK
    ]
    if pairs:
        _, left, right = max(pairs)
        x0, x1 = x0 + left, x0 + right
    return x0, y0, x1, y1


def _blobs(img, lo, hi) -> list[tuple[int, int, int, np.ndarray]]:
    """(w, h, area, centre) of each colour blob; centres are pixel edges, not indices."""
    m = glyphs.mask(img, lo, hi).astype(np.uint8)
    n, _, stats, centres = cv2.connectedComponentsWithStats(m, connectivity=8)
    return [
        (*stats[i, cv2.CC_STAT_WIDTH : cv2.CC_STAT_AREA + 1], centres[i] + 0.5) for i in range(1, n)
    ]


def _portals(img: np.ndarray) -> tuple[tuple[float, float], ...]:
    b, r = img[:, :, 0].astype(int), img[:, :, 2].astype(int)
    blue = ((b >= PORTAL_B) & (b - r >= PORTAL_BR)).astype(np.uint8)
    blue = cv2.morphologyEx(blue, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    n, _, stats, centres = cv2.connectedComponentsWithStats(blue, connectivity=8)
    return tuple(
        (float(centres[i][0] + 0.5), float(centres[i][1] + 0.5))
        for i in range(1, n)
        if stats[i, cv2.CC_STAT_WIDTH] == PORTAL_SIDE == stats[i, cv2.CC_STAT_HEIGHT]
        and PORTAL_AREA[0] <= stats[i, cv2.CC_STAT_AREA] <= PORTAL_AREA[1]
    )


def _orange(img: np.ndarray, c, w: int, h: int) -> bool:
    """Whether the dot-coloured blob of size w x h centred at `c` is orange-yellow (DOT_RG)."""
    x0, y0 = round(c[0] - w / 2), round(c[1] - h / 2)
    box = img[max(y0, 0) : y0 + h, max(x0, 0) : x0 + w].astype(int)
    px = box[glyphs.mask(box, DOT_LO, DOT_HI)]
    return px.size > 0 and (px[:, 2] - px[:, 1]).mean() >= DOT_RG


def read_view(frame: np.ndarray) -> MinimapView | None:
    """The minimap's map area size, "you" dot, NPC markers and portal spirals, or None.

    `frame` is normalized. None when the minimap is closed, minimized, covered, or the
    dot isn't found exactly once.
    """
    hit = glyphs.find_anchor(frame[: map_name.BAND_H, : map_name.BAND_W], "minimap_title")
    area = None if hit is None else _map_area(frame, *hit)
    if area is None:
        return None
    x0, y0, x1, y1 = area
    img = frame[y0:y1, x0:x1]
    dots = [
        c
        for w, h, px, c in _blobs(img, DOT_LO, DOT_HI)
        if DOT_SIDE[0] <= min(w, h)
        and max(w, h) <= DOT_SIDE[1]
        and abs(w - h) <= DOT_SQUARE
        and DOT_AREA[0] <= px <= DOT_AREA[1]
        and _orange(img, c, w, h)
    ]
    if len(dots) != 1:
        return None
    npcs = tuple(
        (float(c[0]), float(c[1]))
        for w, h, px, c in _blobs(img, NPC_LO, NPC_HI)
        if w == NPC_W and NPC_H[0] <= h <= NPC_H[1] and NPC_AREA[0] <= px <= NPC_AREA[1]
    )
    dot = (float(dots[0][0]), float(dots[0][1]))
    return MinimapView((int(x1 - x0), int(y1 - y0)), dot, npcs, _portals(img), img.copy())


def read_player(frame: np.ndarray) -> tuple[float, float] | None:
    """The "you" dot's centre as (fx, fy) fractions of the minimap's map area, or None.

    Valid only on maps that fit the minimap window.
    """
    v = read_view(frame)
    return None if v is None else v.fraction
