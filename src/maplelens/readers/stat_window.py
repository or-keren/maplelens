"""Stat window reader: level, unspent AP and the four stats, plus where the + buttons are."""

import re
from dataclasses import dataclass

import numpy as np

from maplelens.readers import window
from maplelens.readers.window import UNREADABLE

# The window, 768-scale: size, and the anchors (template, offset from its top-left).
WIN_W, WIN_H = 182, 278
ANCHORS = [("stat_title", (4, 7)), ("stat_bottom", (7, 258))]
# Value strips (x, w) and row centres (y), relative to the window's top-left. A strip is
# 15 rows tall and ends before the + buttons, whose dark outline would count as ink.
VAL_X, VAL_W = 55, 85
AP_X, AP_W = 89, 26
ROW_Y = {"level": 85, "STR": 181, "DEX": 199, "INT": 217, "LUK": 235, "ap": 264}
# Centre of the single-arrow + button (the left of the pair), relative to the top-left.
PLUS_DX = 152
STATS = ("STR", "DEX", "INT", "LUK")


@dataclass(frozen=True)
class StatWindow:
    level: int
    ap: int
    base: dict[str, int]
    total: dict[str, int]
    plus: dict[str, tuple[int, int]]  # + button centre per stat, in frame coordinates


def parse_stat(text: str) -> tuple[int, int] | None:
    """(base, total) from "25" or "124(122+2)" (only when 122 + 2 == 124), else None."""
    m = re.fullmatch(r"(\d+)(?:\((\d+)\+(\d+)\))?", text)
    if m is None:
        return None
    if m[2] is None:
        return int(m[1]), int(m[1])
    return (int(m[2]), int(m[1])) if int(m[2]) + int(m[3]) == int(m[1]) else None


def _box(x: int, cy: int, w: int) -> tuple[int, int, int, int]:
    return x, cy - 7, w, 15


def read_stat_window(
    frame: np.ndarray, native: np.ndarray | None = None, scale: float | None = None
) -> StatWindow | str | None:
    """The stat window in `frame` (normalized), read from `native` (default `frame`).

    None if no window is found; UNREADABLE if one is but a field is covered or
    misread, or the AP don't add up (R13).
    """
    native = frame if native is None else native
    scale = native.shape[0] / frame.shape[0] if scale is None else scale
    hit = window.align(frame, native, scale, ANCHORS, (WIN_W, WIN_H))
    if hit is None:
        return None
    win, (wx, wy) = hit
    texts = {
        k: window.read_number_text(
            win, _box(AP_X if k == "ap" else VAL_X, y, AP_W if k == "ap" else VAL_W)
        )
        for k, y in ROW_Y.items()
    }
    try:
        level, ap = int(texts["level"]), int(texts["ap"])
        parsed = {k: parse_stat(texts[k]) for k in STATS}
    except (TypeError, ValueError):
        return UNREADABLE
    if None in parsed.values() or level < 1:
        return UNREADABLE
    base = {k: p[0] for k, p in parsed.items()}
    if sum(base.values()) + ap > 25 + 5 * (level - 1):
        return UNREADABLE
    plus = {k: (wx + PLUS_DX, wy + ROW_Y[k]) for k in STATS}
    h, w = frame.shape[:2]
    if not all(0 <= x < w and 0 <= y < h for x, y in plus.values()):
        return UNREADABLE  # a ring must never point at an off-screen +
    return StatWindow(level, ap, base, {k: p[1] for k, p in parsed.items()}, plus)
