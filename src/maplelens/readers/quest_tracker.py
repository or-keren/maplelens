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
from dataclasses import dataclass
from functools import cache, lru_cache
from pathlib import Path

import cv2
import numpy as np

from maplelens.gamedata import load_game
from maplelens.readers import glyphs, map_name, ocr, quest_window, window
from maplelens.readers.window import UNREADABLE

PARTLY = "tracker partly read"  # found, but fewer blocks read than its count, or one garbled


@dataclass(frozen=True)
class TrackerLine:
    have: int
    need: int
    text: str  # the target's name, snapped to a known item or monster name, else as read


@dataclass(frozen=True)
class TrackerQuest:
    name: str  # the one known quest name it reads as (a cut name gives the full name)
    lines: tuple[TrackerLine, ...]


@dataclass(frozen=True)
class Tracker:
    count: int  # the n in "Quest Helper (n/5)"
    minimized: bool
    quests: tuple[TrackerQuest, ...]  # () when minimized; len == count when read


# The anchor: the "Quest Helper" title text, cut from tracker_a_1366x768_100.png (the 768
# look), 3 px right of and 4 px under the window's top-left. Coarse scores: 1.00 at 1366,
# 0.90-0.91 on the 1920 fixtures; below 0.4 on every other fixture. The Mac client draws
# the title a little differently (Q, "st H"): there it scored 0.70-0.76, at ANCHOR_MIN, and
# picked a half-pixel-off start at 2x. tracker_title_mac is cut from a 2732x1536 Mac grab;
# its text starts a pixel further right of the panel's corner than Windows' does.
ANCHORS = [("tracker_title", (3, 4)), ("tracker_title_mac", (4, 4))]
# The panel's width (borders included), and a window tall enough for 5 blocks with spare
# target lines: below the panel, align's crop is the map or black.
PANEL_W, WIN_H = 222, 340
# Ink: max over channels of (pixel / brightest in its 3x3) below this; the max channel
# alone (one ratio) let coloured map edges through as ink. Over a black map (the panel's
# body at its darkest, 85) the glyphs' edge pixels are paler: tracker_two reads at every
# offset with 0.55-0.6, and is broken at 0.525 and 0.65. On the grabs (67 frames, 1920x1080,
# blue sky, grass, hay, ropes and bricks behind the panel) 0.5-0.55 read 37 panels whole,
# 0.575 36 and 0.6 35 (the rest PARTLY; none misread at any of these). So the middle of
# the dark panel's range.
INK_RATIO = 0.575
# Glyphs (window.read_number_text's way): a glyph scores GLYPH_MIN, and no other char
# scores within GLYPH_MARGIN of it within 1 px. Clean reads score 1.0; 6 and 8 differ by
# two pixels and score 0.933 on each other, so the margin sits under their 0.067 gap. On
# the grabs and fixtures (416 lines) the smallest accepted gap was 0.067; no misread.
GLYPH_MIN, GLYPH_MARGIN = 0.8, 0.05
INK_MIN = 2  # ink pixels that make a column count (a stray map pixel is 1)
NUMBERS_X, NUMBERS_W = 6, 64  # where "have / need" starts, and room for "999 / 999 X"
# "have / need" sits at fixed columns (template x in the NUMBERS_X strip), the same on all
# lines read on the grabs and fixtures: the first have digit at HAVE_X, digits ADVANCE
# apart, "/" SLASH_DX after the last have digit, the first need digit NEED_DX after "/",
# and the text's first ink TEXT_GAP columns after the need's last digit's x (measured 10,
# 11 or 12, "1" and wide digits alike). A digit's ink starts 1 column after its x, so a
# need's next digit but one starts at 2 ADVANCE + 1 = 13: with the middle of "200" hidden,
# the "0" left isn't taken for the text. So a digit lost under the map leaves a gap where
# a glyph should be, and the line doesn't read.
HAVE_X, ADVANCE, SLASH_DX, NEED_DX = 3, 6, 9, 6
TEXT_GAP = (10, 12)
COUNT_X, COUNT_Y, COUNT_W = 75, 6, 14  # the title's n, right after its "("
# Rows: block i's name at FIRST_Y + 48i; a target line LINE_DY under the name or the line
# above it; the next name NAME_DY under the last line.
FIRST_Y, LINE_DY, NAME_DY = 26, 16, 32
TEXT_X0, TEXT_X1 = 4, 205  # text columns, left of the unfollow button (208-218)
TEXT_H = 13  # a text box: from 2 rows over a line's ink rows, descenders included
# Every block's name row has an unfollow button (templates/tracker_unfollow.png, its ink,
# right of TEXT_X1): it tells a name from a target line, and finds a block past the
# count. Scores (TM_CCOEFF_NORMED on the ink): 0.74-1.0 on every block of the fixtures
# and grabs, the button half covered included; at most 0.25 a block below the last one.
UNFOLLOW_X, UNFOLLOW_MIN = 202, 0.5
# A row under a block's last line holds no ink but a further line: at most 3 ink columns
# (stray map pixels) seen in the gap between blocks.
GAP_INK = 6
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
    game = load_game()
    quests = _data()["quests"]
    mobs = {m for q in quests for m, _ in q["mobs"]}
    items = {i for q in quests for i, _ in q["items"]}  # start items too: letters show
    return frozenset(game.mobs[m].name for m in mobs) | frozenset(game.items[i].name for i in items)


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
        # a wider char's scores end sooner: none there is no rival
        rival = max(s[max(a - 1, 0) : a + 2].max(initial=-1) for c, _, s in scores if c != ch)
        chosen.append((a, tw, ch, sc - rival))
    return sorted(chosen)


def _plus(win: np.ndarray) -> bool:
    """Whether the minimize button shows "+" (see PLUS)."""
    x, y, w, h = PLUS
    px = win[y : y + h, x : x + w].astype(int)
    return (px[..., 0] - px[..., 2] <= BLUE_RB).sum() >= PLUS_MIN


def _count(ink: np.ndarray) -> int | None:
    """The title's n, or None. The title's font differs from the lines' in its "/" and in
    a pixel of 3 and 5, but its digits still score on the lines' templates, with margins
    of at least 0.135 on the grabs and fixtures at every offset (0 to 5 all seen). The
    Mac's title is a pixel wider before the n, so it sits at 1 there."""
    g = _glyphs(ink[COUNT_Y - 3 : COUNT_Y + 12, COUNT_X : COUNT_X + COUNT_W])
    ok = g and g[0][0] in (0, 1) and g[0][2].isdigit() and g[0][3] >= GLYPH_MARGIN
    return int(g[0][2]) if ok else None


def _digits(at: dict, x: int) -> list:
    """The glyphs of `at` (template x -> glyph) that are digits from `x`, ADVANCE apart."""
    out = []
    while x in at and at[x][2].isdigit():
        out.append(at[x])
        x += ADVANCE
    return out


def _line(ink: np.ndarray, y: int) -> tuple[int, int, int] | bool:
    """(have, need, x where the text starts) of the target line whose ink rows start at
    `y`; else True if a digit or "/" still shows at a line's columns (a line that doesn't
    read), False if not (or past the window). Every glyph must sit at its column (see
    HAVE_X), every ink column up to the need's end must be a glyph's, and the text must
    start TEXT_GAP after it."""
    if y < 3 or y + 12 > ink.shape[0]:
        return False
    band = ink[y - 3 : y + 12, NUMBERS_X : NUMBERS_X + NUMBERS_W]
    at = {g[0]: g for g in _glyphs(band)}
    slashes = (HAVE_X + SLASH_DX, HAVE_X + ADVANCE + SLASH_DX)
    seen = HAVE_X in at or any(x in at and at[x][2] == "/" for x in slashes)
    have = _digits(at, HAVE_X)
    slash = at.get(have[-1][0] + SLASH_DX) if have else None
    need = _digits(at, slash[0] + NEED_DX) if slash and slash[2] == "/" else []
    seq = [*have, slash, *need]
    if not need or min(g[3] for g in seq) < GLYPH_MARGIN:
        return seen
    cols = band[3:11].sum(axis=0) >= INK_MIN
    end = need[-1][0] + need[-1][1] - 1  # the need's last template column
    covered = np.zeros(end, bool)
    for a, w, _, _ in seq:
        covered[a : a + w] = True
    text = np.flatnonzero(cols[end:]) + end - need[-1][0]  # from the need's last digit's x
    if (cols[:end] & ~covered).any() or not (text.size and TEXT_GAP[0] <= text[0] <= TEXT_GAP[1]):
        return True
    have_n, need_n = (int("".join(g[2] for g in part)) for part in (have, need))
    return have_n, need_n, NUMBERS_X + end + 3


def _unfollow(ink: np.ndarray, y: int) -> bool:
    """Whether the name row starting at `y` has its unfollow button."""
    t = cv2.cvtColor(glyphs.load("tracker_unfollow"), cv2.COLOR_BGR2GRAY).astype(np.float32)
    band = ink[max(y - 5, 0) : y + 12, UNFOLLOW_X:PANEL_W]
    if band.shape[0] < t.shape[0]:
        return False
    strip = np.where(band, 0, 255).astype(np.float32)
    return cv2.matchTemplate(strip, t, cv2.TM_CCOEFF_NORMED).max() >= UNFOLLOW_MIN


def _text(frame: np.ndarray, native: np.ndarray, box, ink: np.ndarray, snap) -> str:
    """The text in `box` (normalized x, y, w, h) as `snap` names it, else as first read;
    '' if none. `ink` is the box's ink, and the read is kept by it, so the map moving
    behind the panel costs no OCR; but a name that snaps to nothing is read again next
    time (ocr.read_lines caches by mask), as it makes the panel PARTLY."""
    key = ink.tobytes() + snap.__name__.encode()
    if key in _words:
        return _words[key]
    c = ocr.crop(frame, native, box).astype(np.float32)
    ratio = (c / np.maximum(cv2.dilate(c, np.ones((OCR_BG, OCR_BG), np.uint8)), 1)).max(axis=2)
    reads = []
    for r in OCR_RATIOS:
        reads.append(" ".join(ocr.read_lines(ratio < r) or []).strip())
        if snap(reads[-1]):
            break
    name = snap(reads[-1])
    if name or snap is _target:
        if len(_words) >= 64:
            _words.clear()
        _words[key] = name or reads[0]
    return name or reads[0]


def read_quest_tracker(
    frame: np.ndarray, native: np.ndarray | None = None, scale: float | None = None
) -> Tracker | str | None:
    """The Quest Helper in `frame` (normalized), read from `native` (default `frame`).

    None if there's no panel; UNREADABLE if the frame's edge cuts it; PARTLY if its
    count doesn't read, or fewer blocks read than the count (one covered, a name that
    snaps to no known quest, or a line's numbers that don't read). A "+" (minimize)
    button means minimized, but "Quest Helper (0/5)" shows one too and reads as an
    open, empty panel.

    Limit: the title is the anchor, at the panel's left, so a panel past the frame's
    left edge isn't found and reads None (past the top, the rows that remain still read).
    """
    native = frame if native is None else native
    scale = native.shape[0] / frame.shape[0] if scale is None else scale
    hit = window.align(frame, native, scale, ANCHORS, (PANEL_W, WIN_H))
    if hit is None:
        return None
    win, at = hit
    fw = frame.shape[1]
    if at[0] < 0 or at[0] + PANEL_W > fw + 1:  # 1 px of slack: the panel may touch the edge
        return UNREADABLE
    ink = _ink(win)
    n = _count(ink)
    if n is None or n > 5:
        return PARTLY
    if n == 0:  # a 0 misread from a busy title would hide blocks: check below it
        return PARTLY if _unfollow(ink, FIRST_Y) else Tracker(0, False, ())
    if _plus(win):
        return Tracker(n, True, ())
    quests = _blocks(frame, native, ink, at, n)
    return quests if isinstance(quests, str) else Tracker(n, False, quests)


def _blocks(frame: np.ndarray, native: np.ndarray, ink: np.ndarray, at, n: int):
    """The panel's `n` quest blocks, top down; UNREADABLE if the frame's bottom cuts a
    row to read; PARTLY if a block doesn't read or the rows don't fit `n` blocks:
    - a name row with no unfollow button, or a name that snaps to no known quest (every
      Classic quest has one, so it's garbled, and the quest it really is would look
      unfollowed);
    - a first line whose numbers don't read;
    - a row under a block's last line showing a line's digits, or any ink between two
      blocks (a further line that doesn't read);
    - a block past the count (its title digit misread low).
    The check for a block past the count is skipped past the frame: the panel sits at
    the frame's top, so that's only a short crop."""
    known = quest_window.known_quest_names()

    def seen(y: int) -> bool:  # the frame shows the row from `y`
        return at[1] + y + TEXT_H <= frame.shape[0]

    def text(x: int, y: int, snap) -> str:  # the text line from (x, y) to TEXT_X1
        box = (at[0] + x, at[1] + y - 2, TEXT_X1 - x, TEXT_H)
        return _text(frame, native, box, ink[y - 2 : y - 2 + TEXT_H, x:TEXT_X1], snap)

    quests, y = [], FIRST_Y
    for i in range(n):
        if not seen(y + LINE_DY):
            return UNREADABLE
        name = _unfollow(ink, y) and text(TEXT_X0, y, _name)
        if name not in known:
            return PARTLY
        lines, y = [], y + LINE_DY
        while seen(y) and isinstance(line := _line(ink, y), tuple):
            lines.append(TrackerLine(line[0], line[1], text(line[2], y, _target)))
            y += LINE_DY
        if not seen(y):
            return UNREADABLE
        gap = i < n - 1 and (ink[y : y + 10, TEXT_X0:TEXT_X1].sum(axis=0) >= INK_MIN).sum()
        if not lines or line or gap >= GAP_INK:
            return PARTLY
        quests.append(TrackerQuest(name, tuple(lines)))
        y += NAME_DY - LINE_DY
    return PARTLY if seen(y) and _unfollow(ink, y) else tuple(quests)
