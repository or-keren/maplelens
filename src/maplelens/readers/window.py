"""Shared by the draggable-window readers (stat, skill): align on the window, read digits.

The game draws these windows at screen-pixel positions, so after glyphs.normalize a
window's glyphs differ at every sub-pixel offset and exact-mask templates fail. Instead:
align() finds the native start that makes the window land on the 768-scale pixel grid,
and read_number_text() correlates grey glyph templates (templates/window_font/).
"""

import math

import cv2
import numpy as np

from maplelens.readers import glyphs

UNREADABLE = "unreadable"  # a window was found but a field could not be read

# An anchor is first found on the normalized frame (grey TM_CCOEFF_NORMED): it must score
# COARSE_MIN there, then ANCHOR_MIN at its exact spot after alignment. Stat fixtures, coarse:
# 1.00 at 768, 0.60-0.97 at 1080/1440 depending on the sub-pixel offset; covered or
# off-screen 0.2-0.3; the best score on any non-stat fixture 0.42. At its exact spot after
# alignment: 0.88 (1080), 0.91 (1440), 1.00 (768).
COARSE_MIN = 0.5
ANCHOR_MIN = 0.7
# A glyph needs this score. Accepted glyphs scored 1.0 at 768 and 0.825-0.97 at 1080/1440.
GLYPH_MIN = 0.8
# No other char may score within this of an accepted glyph within 1 px, at any score.
# Smallest runner-up gaps measured on the stat fixtures: 0.157 (768), 0.116 (1080),
# 0.090 (1440, the level's glyphs). 0.07 leaves 0.02 of slack at 1440: thin, so a
# new resolution's fixtures need their gaps checked.
GLYPH_MARGIN = 0.07
# Outside the glyphs a strip must be its background: within BG_TOL of the median grey.
# Measured on the stat fixtures: 0 at every scale (flat 222 fields, 255 for the AP box),
# so 12 only leaves room for resampling noise at other offsets.
BG_TOL = 12
GLYPH_H = 13
INK = 90  # grey below this is ink (dark digits on a light field)

_fonts: dict[str, list[tuple[str, np.ndarray]]] = {}


def _gray(img: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def _cut(img: np.ndarray, x: int, y: int, w: int, h: int) -> np.ndarray:
    """img[y:y+h, x:x+w], black where that lies outside img."""
    out = np.zeros((h, w, 3), img.dtype)
    x0, y0, x1, y1 = max(x, 0), max(y, 0), min(x + w, img.shape[1]), min(y + h, img.shape[0])
    if x1 > x0 and y1 > y0:
        out[y0 - y : y1 - y, x0 - x : x1 - x] = img[y0:y1, x0:x1]
    return out


def align(
    frame: np.ndarray,
    native: np.ndarray,
    scale: float,
    anchors: list[tuple[str, tuple[int, int]]],
    size: tuple[int, int],
) -> tuple[np.ndarray, tuple[int, int]] | None:
    """The window as a 768-scale BGR image of `size` (w, h), and its top-left in `frame`.

    `frame` is the normalized frame, `native` the pixels it came from (`scale` = native /
    frame). The window is found on `frame` by its best anchor (template name, offset from
    the window's top-left); then each native start within 2 frame px is tried, the native
    crop scaled by exactly 1/scale, and the start whose anchor matches best at its exact
    spot wins. None if no anchor scores ANCHOR_MIN.
    """
    g = _gray(frame)
    top = (ANCHOR_MIN, None, 0, 0)  # (score at its exact spot, anchor, native x0, y0)
    for name, (ax, ay) in anchors:
        t = _gray(glyphs.load(name))
        th, tw = t.shape
        if g.shape[0] < th or g.shape[1] < tw:
            continue
        _, sc, _, loc = cv2.minMaxLoc(cv2.matchTemplate(g, t, cv2.TM_CCOEFF_NORMED))
        if sc < COARSE_MIN:
            continue
        ox, oy = (loc[0] - ax) * scale, (loc[1] - ay) * scale
        k = 0 if scale == 1 else math.ceil(2 * scale)
        cw, ch = math.ceil((ax + tw + 1) * scale) + 1, math.ceil((ay + th + 1) * scale) + 1
        for ky in range(-k, k + 1):
            for kx in range(-k, k + 1):
                x0, y0 = int(ox) + kx, int(oy) + ky
                w = _gray(
                    cv2.resize(
                        _cut(native, x0, y0, cw, ch),
                        None,
                        fx=1 / scale,
                        fy=1 / scale,
                        interpolation=cv2.INTER_AREA,
                    )
                )
                patch = w[ay : ay + th, ax : ax + tw]
                if patch.shape != t.shape:
                    continue
                s = cv2.matchTemplate(patch, t, cv2.TM_CCOEFF_NORMED)[0, 0]
                if s > top[0]:
                    top = (s, name, x0, y0)
    if top[1] is None:
        return None
    _, _, x0, y0 = top
    cw, ch = math.ceil(size[0] * scale) + 1, math.ceil(size[1] * scale) + 1
    win = cv2.resize(
        _cut(native, x0, y0, cw, ch), None, fx=1 / scale, fy=1 / scale, interpolation=cv2.INTER_AREA
    )[: size[1], : size[0]]
    return win, (round(x0 / scale), round(y0 / scale))


def font(name: str = "window_font") -> list[tuple[str, np.ndarray]]:
    """The grey glyph templates in templates/<name>/ as (char, float32 image), cached."""
    if name not in _fonts:
        _fonts[name] = [
            (
                glyphs.CHAR_NAMES.get(p.stem, p.stem),
                glyphs.imread(p, cv2.IMREAD_GRAYSCALE).astype(np.float32),
            )
            for p in sorted((glyphs.TEMPLATES / name).glob("*.png"))
        ]
    return _fonts[name]


def read_number_text(win: np.ndarray, box: tuple[int, int, int, int]) -> str | None:
    """The digits and signs in `box` (x, y, w, h of `win`), or None.

    Every ink column of the box must belong to a glyph that scores GLYPH_MIN and beats
    every other char at that spot by GLYPH_MARGIN. The box's top and bottom rows are not
    checked for ink (its border may lie there).
    """
    x, y, w, h = box
    strip = _gray(win[y : y + h, x : x + w]).astype(np.float32)
    if strip.shape[0] < GLYPH_H or strip.shape[1] < 3:
        return None
    chosen = _accepted(strip)
    if chosen is None:
        return None
    ink = np.flatnonzero((strip[1:-1] < INK).any(axis=0))
    if ink.size == 0 or not all(any(a <= i < b for a, b, _ in chosen) for i in ink):
        return None
    # Everything outside the glyphs must be the field's background: a light overlay
    # without a border would hide text and leave no ink to notice.
    bg = np.ones(strip.shape, bool)
    bg[:2] = bg[-2:] = False  # the field's own edge may lie on the strip's border rows
    bg[:, :3] = False  # and its left edge on the first columns
    for a, b, _ in chosen:
        bg[:, a - 1 : b + 1] = False
    if bg.any() and (np.abs(strip[bg] - np.median(strip[bg])) > BG_TOL).any():
        return None
    return "".join(c for _, _, c in chosen)


def _accepted(strip: np.ndarray) -> list[tuple[int, int, str]] | None:
    """Non-overlapping glyphs (ink start, ink end, char), left to right; None if one is
    ambiguous (another char within GLYPH_MARGIN of it, within 1 px, at any score)."""
    scores = {}
    for ch, t in font():
        if strip.shape[1] >= t.shape[1]:
            r = cv2.matchTemplate(strip, t, cv2.TM_CCOEFF_NORMED).max(axis=0)
            scores.setdefault(ch, []).append((t.shape[1], r))
    cands = []
    for ch, rows in scores.items():
        for tw, s in rows:
            peaks = (s >= GLYPH_MIN) & (s >= np.r_[-1, s[:-1]]) & (s >= np.r_[s[1:], -1])
            cands += [(float(s[i]), i + 1, i + tw - 1, ch) for i in np.flatnonzero(peaks)]
    chosen: list[tuple[int, int, str]] = []
    for sc, a, b, ch in sorted(cands, reverse=True):
        if any(a < cb and b > ca for ca, cb, _ in chosen):
            continue
        rivals = (
            s[max(a - 2, 0) : a + 1].max(initial=-1)
            for c, r in scores.items()
            for _, s in r
            if c != ch
        )
        if any(v > sc - GLYPH_MARGIN for v in rivals):
            return None
        chosen.append((a, b, ch))
    return sorted(chosen)
