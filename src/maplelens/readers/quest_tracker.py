"""Quest Helper reader: the game's panel of followed quests, at the game window's top right.

The panel is see-through: the map shows behind its black text. The game draws it at the
768 look and scales that up, so once window.align has put the panel back on the 768 grid
its glyphs come back pixel for pixel: a pixel is ink when all three channels are well
below the brightest around it (black text darkens every channel alike; the map behind
rarely does). Numbers ("have / need", the title's count) are read from those glyphs with
templates/tracker_font/ (cut from 1920x1080 grabs; 9 is 6 turned around); words (quest
names, targets) by the system OCR on the native pixels, then snapped to the names in
data/quests.json.

Layout, 768 scale, from the window's top-left (the title anchor's offset): the title's
count on rows 6-13; block i's bold name from row 26+48i, its first target line 16 rows
lower (each block seen so far has one line; more are taken 16 rows apart); the panel's
bottom at 12+48n.
"""

import json
import re
from dataclasses import dataclass
from functools import cache, lru_cache
from pathlib import Path

import cv2
import numpy as np

from maplelens.readers import map_name, ocr, quest_window, window
from maplelens.readers.window import UNREADABLE

PARTLY = "tracker partly read"  # found, but fewer blocks read than its count, or one garbled


@dataclass(frozen=True)
class TrackerLine:
    have: int
    need: int
    text: str  # the target's name, snapped to a known item or monster name, else as read


@dataclass(frozen=True)
class TrackerQuest:
    name: str  # snapped to the one known quest name it reads as (a cut name gives the
    # full name); else as read, a cut name keeping its trailing dots
    lines: tuple[TrackerLine, ...]


@dataclass(frozen=True)
class Tracker:
    count: int  # the n in "Quest Helper (n/5)"
    minimized: bool
    quests: tuple[TrackerQuest, ...]  # () when minimized; len == count when read


# The anchor: the "Quest Helper" title text, cut from tracker_a_1366x768_100.png (the 768
# look), 3 px right of and 4 px under the window's top-left. Coarse scores: 1.00 at 1366,
# 0.90-0.91 on the 1920 fixtures; below 0.4 on every other fixture.
ANCHORS = [("tracker_title", (3, 4))]
# The panel's width (borders included), and a window tall enough for 5 blocks with spare
# target lines: below the panel, align's crop is the map or black.
PANEL_W, WIN_H = 222, 340
# Ink: max over channels of (pixel / brightest in its 3x3) below this. On the grabs (67
# frames, 1920x1080, blue sky, grass, hay, ropes and bricks behind the panel) 0.5 gave the
# glyphs the game draws at 768 with the fewest stray pixels; the max channel alone (one
# ratio) let coloured map edges through as ink.
INK_RATIO = 0.5
# Glyphs (window.read_number_text's way): a glyph scores GLYPH_MIN, and no other char
# scores within GLYPH_MARGIN of it within 1 px. Clean reads score 1.0; 6 and 8 differ by
# two pixels and score 0.933 on each other, so the margin sits under their 0.067 gap. On
# the grabs and fixtures (416 lines) the smallest accepted gap was 0.067; no misread.
GLYPH_MIN, GLYPH_MARGIN = 0.8, 0.05
ADVANCE = 6  # digits are monospaced: 5 px wide, 1 apart
WORD_GAP = 3  # empty columns after the need's last digit ("30 Red": 4, "0 / 1 Arwen": 6)
INK_MIN = 2  # ink pixels that make a column count (a stray map pixel is 1)
NUMBERS_X, NUMBERS_W = 6, 64  # where "have / need" starts, and room for "99 / 99"
COUNT_X, COUNT_Y, COUNT_W = 75, 6, 14  # the title's n, right after its "("
# Rows: block i's name at FIRST_Y + 48i; a target line LINE_DY under the name or the line
# above it; the next name NAME_DY under the last line. The panel's bottom: TOP_H + BLOCK_H n.
FIRST_Y, LINE_DY, NAME_DY = 26, 16, 32
TOP_H, BLOCK_H = 12, 48
TEXT_X0, TEXT_X1 = 4, 205  # text columns, left of the unfollow button (208-218)
TEXT_H = 13  # a text box: from 2 rows over a line's ink rows, descenders included
# The minimize button (blue, x 195-204, y 5-14): "+" shows a white upright in its centre
# (rows 6-8, columns 198-201); "-" has none. Measured: 4 non-blue pixels with +, 0 with -.
PLUS = (198, 6, 4, 3)
BLUE_RB, PLUS_MIN = 80, 2
# OCR masks of the native pixels at ocr.SCALE: a pixel is ink when every channel is below
# a ratio of the brightest in its OCR_BG square; the next ratio is tried while the text
# snaps to no known name. On the fixtures at every offset, 0.6 alone read every name but
# one ("The Filing Ector"), and 0.55 read that one. On the grabs (busy maps behind the
# panel) the three read 393 names and 397 targets of 416; the rest snapped to nothing,
# but for one "Maple Leaf" half hidden that read "Leaf" (an item).
OCR_RATIOS, OCR_BG = (0.6, 0.55, 0.65), 9
CUT = ".…"  # a cut name ends in "…", which the OCR reads as one to three dots

_words: dict[bytes, str] = {}  # crisp glyphs of a text box -> its snapped text


@cache
def _data() -> dict:
    return json.loads((Path(__file__).parents[1] / "data" / "quests.json").read_text("utf-8"))


@cache
def target_names() -> frozenset[str]:
    """The items' and monsters' names a target line can show."""
    raw = _data()
    return frozenset(v["name"] for k in ("items", "mobs") for v in raw[k].values())


@lru_cache(maxsize=256)
def _name(text: str) -> str | None:
    """The one known quest name `text` reads as, else None. A cut name (trailing dots)
    gives the one known name it starts, else the one it snaps to among the known names
    cut to its length."""
    known = quest_window.known_quest_names()
    if not text.endswith(tuple(CUT)):
        name = map_name.snap_title(text, known)
        return name if name in known else None
    start = text.rstrip(CUT).rstrip()
    names = [n for n in known if n.startswith(start)]
    if len(names) == 1:
        return names[0]
    cut: dict[str, list[str]] = {}
    for n in known:
        cut.setdefault(n[: len(start)], []).append(n)
    full = cut.get(map_name.snap_title(start, cut), [])
    return full[0] if len(full) == 1 else None


@lru_cache(maxsize=256)
def _target(text: str) -> str | None:
    """The known item or monster name `text` reads as, else None."""
    name = map_name.snap_title(text, target_names())
    return name if name in target_names() else None


def _ink(win: np.ndarray) -> np.ndarray:
    """Bool image of the panel's black ink (see INK_RATIO)."""
    v = win.astype(np.float32)
    bright = cv2.dilate(v, np.ones((3, 3), np.uint8))
    return (v / np.maximum(bright, 1)).max(axis=2) < INK_RATIO


def _glyphs(band: np.ndarray) -> list[tuple[int, int, str, float]]:
    """Non-overlapping glyphs in an ink `band` (template x, width, char, margin over the
    best other char within 1 px), left to right."""
    strip = np.where(band, 0, 255).astype(np.float32)
    scores = [
        (ch, t.shape[1], cv2.matchTemplate(strip, t, cv2.TM_CCOEFF_NORMED).max(axis=0))
        for ch, t in window.font("tracker_font")
    ]
    cands = []
    for ch, tw, s in scores:
        peaks = (s >= GLYPH_MIN) & (s >= np.r_[-1, s[:-1]]) & (s >= np.r_[s[1:], -1])
        cands += [(float(s[i]), int(i), tw, ch) for i in np.flatnonzero(peaks)]
    chosen: list[tuple[int, int, str, float]] = []
    for sc, a, tw, ch in sorted(cands, reverse=True):
        # ink spans are the template less its 1 px of background each side
        if any(a + 1 < b + bw - 1 and b + 1 < a + tw - 1 for b, bw, _, _ in chosen):
            continue
        rival = max(s[max(a - 1, 0) : a + 2].max() for c, _, s in scores if c != ch)
        chosen.append((a, tw, ch, sc - rival))
    return sorted(chosen)


def _plus(win: np.ndarray) -> bool:
    """Whether the minimize button shows "+" (see PLUS)."""
    x, y, w, h = PLUS
    px = win[y : y + h, x : x + w].astype(int)
    return (px[..., 0] - px[..., 2] <= BLUE_RB).sum() >= PLUS_MIN


def _count(ink: np.ndarray) -> int | None:
    """The title's n, or None. The title's font differs from the lines' in its "/" and in
    a pixel of 3 and 5, but its digits still score 0.88-1.0 on the lines' templates, with
    margins of at least 0.119 (0, 1, 3, 4 and 5 seen; 2 not yet)."""
    g = _glyphs(ink[COUNT_Y - 3 : COUNT_Y + 12, COUNT_X : COUNT_X + COUNT_W])
    ok = g and g[0][0] == 0 and g[0][2].isdigit() and g[0][3] >= GLYPH_MARGIN
    return int(g[0][2]) if ok else None


def _numbers(ink: np.ndarray, y: int) -> tuple[int, int, int] | None:
    """(have, need, x after the need) of the "have / need" whose ink rows start at `y`,
    or None. Every ink column up to the need's end must be a glyph's, digits one ADVANCE
    apart, and WORD_GAP empty columns must follow."""
    band = ink[y - 3 : y + 12, NUMBERS_X : NUMBERS_X + NUMBERS_W]
    seq, part = [], 0  # part 0: have digits, 1: the slash, 2: need digits
    for g in _glyphs(band):
        a, _, ch, _ = g
        if part == 0 and seq and ch == "/":
            part = 1
        elif part == 1 and ch.isdigit():
            part = 2
        elif not (ch.isdigit() and part in (0, 2) and (not seq or a - seq[-1][0] == ADVANCE)):
            break
        seq.append(g)
    m = re.fullmatch(r"(\d+)/(\d+)", "".join(g[2] for g in seq))
    if not m or min(g[3] for g in seq) < GLYPH_MARGIN:
        return None
    cols = band[3:11].sum(axis=0) >= INK_MIN
    end = seq[-1][0] + seq[-1][1] - 1  # the need's last template column
    covered = np.zeros(end, bool)
    for a, w, _, _ in seq:
        covered[a : a + w] = True
    if (cols[:end] & ~covered).any() or cols[end : end + WORD_GAP].any():
        return None
    return int(m[1]), int(m[2]), NUMBERS_X + end + WORD_GAP


def _text(frame: np.ndarray, native: np.ndarray, box, ink: np.ndarray, snap) -> str:
    """The text in `box` (normalized x, y, w, h) as `snap` names it, else as first read;
    '' if none. `ink` is the box's ink: a snapped text is kept by it, so the map moving
    behind the panel costs no OCR; one that didn't snap is read again next time
    (ocr.read_lines caches by mask)."""
    key = ink.tobytes() + snap.__name__.encode()
    if key in _words:
        return _words[key]
    c = ocr.crop(frame, native, box).astype(np.float32)
    ratio = (c / np.maximum(cv2.dilate(c, np.ones((OCR_BG, OCR_BG), np.uint8)), 1)).max(axis=2)
    first = None
    for r in OCR_RATIOS:
        text = " ".join(ocr.read_lines(ratio < r) or []).strip()
        first = text if first is None else first
        if name := snap(text):
            if len(_words) >= 64:
                _words.clear()
            _words[key] = name
            return name
    return first


def read_quest_tracker(
    frame: np.ndarray, native: np.ndarray | None = None, scale: float | None = None
) -> Tracker | str | None:
    """The Quest Helper in `frame` (normalized), read from `native` (default `frame`).

    None if there's no panel; UNREADABLE if the frame's edge cuts it; PARTLY if its
    count doesn't read, or fewer blocks read than the count (one covered, or a name or
    a line's numbers that don't read). A "+" (minimize) button means minimized, but
    "Quest Helper (0/5)" shows one too and reads as an open, empty panel.

    Limit: the title is the anchor, at the panel's left, so a panel past the frame's
    left or top edge isn't found and reads None.
    """
    native = frame if native is None else native
    scale = native.shape[0] / frame.shape[0] if scale is None else scale
    hit = window.align(frame, native, scale, ANCHORS, (PANEL_W, WIN_H))
    if hit is None:
        return None
    win, at = hit
    fh, fw = frame.shape[:2]
    if at[0] < 0 or at[0] + PANEL_W > fw:
        return UNREADABLE
    ink = _ink(win)
    n = _count(ink)
    if n is None or n > 5:
        return PARTLY
    if n == 0:
        return Tracker(0, False, ())
    if _plus(win):
        return Tracker(n, True, ())
    if at[1] + TOP_H + BLOCK_H * n > fh:
        return UNREADABLE
    quests = _blocks(frame, native, ink, at, n)
    return Tracker(n, False, quests) if quests else PARTLY


def _blocks(frame: np.ndarray, native: np.ndarray, ink: np.ndarray, at, n: int):
    """The panel's `n` quest blocks, top down, or None if one doesn't read (an empty
    name, or a first line whose numbers don't read)."""

    def text(x: int, y: int, snap) -> str:  # the text line from (x, y) to TEXT_X1
        box = (at[0] + x, at[1] + y - 2, TEXT_X1 - x, TEXT_H)
        return _text(frame, native, box, ink[y - 2 : y - 2 + TEXT_H, x:TEXT_X1], snap)

    quests, y = [], FIRST_Y
    for _ in range(n):
        name = ink[y : y + 10, TEXT_X0:TEXT_X1].any() and text(TEXT_X0, y, _name)
        lines, y = [], y + LINE_DY
        while name and (nums := _numbers(ink, y)):
            lines.append(TrackerLine(nums[0], nums[1], text(nums[2], y, _target)))
            y += LINE_DY
        if not lines:
            return None
        quests.append(TrackerQuest(name, tuple(lines)))
        y += NAME_DY - LINE_DY
    return tuple(quests)
