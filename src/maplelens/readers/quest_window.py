"""Quest window reader: which quest the game's quest window shows, and from which tab.

The details pane's header and the list rows show the quest's chain name, cut with "…"
when long; the quest's own name is the first grey line on the white body, never cut.
That line is trusted only when it snaps to a known Classic quest name: a scrolled pane
or another layout puts a description line there instead.

A quest with no chain (128 of the 343) has no such line: its name shows only in the
header and its list row. Then the selected list row is read, trusted only when it is a
known quest name and no chain's name, since a chained quest's row shows its chain's.
"""

import json
from dataclasses import dataclass
from functools import cache, lru_cache
from pathlib import Path

import numpy as np

from maplelens.readers import glyphs, map_name, ocr, window
from maplelens.readers.window import UNREADABLE

NAME_UNREADABLE = "name unreadable"  # a window is there; its name line isn't a known name


@dataclass(frozen=True)
class QuestOpen:
    name: str  # as read; it may match no quest in the data
    taken: bool | None  # True: the In Progress tab, False: Available, None: can't tell


# The window, 768-scale (548x397 at 1366x768, 770x556 at 1920x1080): size, and the anchor
# (the "QUEST" title bar, template, offset from its top-left). Coarse scores (grey
# TM_CCOEFF_NORMED on the normalized frame): the quest grabs 1.00 at 1366 and 0.858 at
# 1920; stat_a 0.53-0.56, skill_a at most 0.52, title_ellinia 0.45. The stat title clears
# window.COARSE_MIN, so it's the exact-spot ANCHOR_MIN and the tab gate that reject it.
WIN_W, WIN_H = 548, 397
ANCHORS = [("quest_title", (4, 7))]
# The tabs' rows and columns: Available, In Progress, Completed. The open one is pink:
# red over blue by PINK_RB. Measured: about 935 pink px on the open tab, at most 73 on
# the others (their edges, at 1920x1080); PINK_MIN sits well between. No pink tab: not
# a quest window.
TAB_Y = (24, 42)
TABS_X = ((4, 78), (78, 150), (150, 222))
TAKEN = (False, True, None)  # None: the Completed tab, nothing to help with
PINK_RB, PINK_MIN = 40, 400
# The details body (x, y, w, h), left of its scrollbar and under the blue header block.
BODY = (256, 106, 268, 256)
# Ink, to find the lines: the grey text (51 on In Progress, 102 on Available); blue
# and red words have one channel at 255. The quest's name is the first ink line whose row
# above is the body's white (the Quest Summary box above it is beige, 213-225).
INK_LO, INK_HI = (0, 0, 0), (150, 150, 150)
WHITE = 245
# The OCR's mask keeps the bold strokes' soft edges too: on the grabs, at 6 sub-pixel
# offsets each, Windows OCR read every name exactly from 200 to 210; 190 and 215 lost
# letters ("Cal (Is", "Filho").
OCR_INK_HI = (205, 205, 205)
# The list pane (x, y, w, h), left of its scrollbar. The selected row is ROW_BLUE (BGR),
# about 190 px wide, white text; the region rows are lighter (200,176,156) or brown
# (109,148,176). The selected row: the pane's rows with ROW_MIN px within ROW_TOL of
# ROW_BLUE (about 192 above and below the text, as few as 23 through it), first to last,
# at most ROW_H tall (18 measured), so two blue things never read as one row.
LIST = (8, 46, 216, 316)
ROW_BLUE, ROW_TOL, ROW_MIN, ROW_H = (153, 102, 51), 8, 100, 20
# The row's text mask, every channel at least this: on the six grabs, at 6 sub-pixel
# offsets each, Windows OCR read every row exactly from 115 to 130; 110 dropped an
# apostrophe, 135 read ':' as '.'.
ROW_INK_LO = (125, 125, 125)
CUT = ".…"  # a cut name ends in "…", which the OCR reads as one to three dots


@cache
def known_quest_names() -> frozenset[str]:
    """The quests' names, and the Classic quests left out on purpose ("other_names")."""
    raw = json.loads((Path(__file__).parents[1] / "data" / "quests.json").read_text("utf-8"))
    return frozenset(q["name"] for q in raw["quests"]) | frozenset(raw["other_names"])


@cache
def chain_names() -> frozenset[str]:
    """The quest chains' names: a chained quest's header and list row show its chain's."""
    raw = json.loads((Path(__file__).parents[1] / "data" / "quests.json").read_text("utf-8"))
    return frozenset(raw["chain_names"])


@lru_cache(maxsize=256)
def _listed(text: str) -> str | None:
    """The known quest name a list row's `text` shows, else None. A cut text ("…") must
    start exactly one quest's or chain's name. A chain's name is never read as a quest's:
    12 chains share their name with one of their own quests (Mai's Training), and which
    one a row shows can't be told."""
    if text.endswith(tuple(CUT)):
        start = text.rstrip(CUT)
        names = [n for n in known_quest_names() | chain_names() if n.startswith(start)]
        name = names[0] if len(names) == 1 else None
    else:
        name = _snap(text)
    return None if name is None or name in chain_names() else name


@lru_cache(maxsize=256)
def _snap(text: str) -> str | None:
    """The known quest name `text` reads as, else None."""
    name = map_name.snap_title(text, known_quest_names())
    return name if name in known_quest_names() else None


def _tab(win: np.ndarray) -> int | None:
    """Index of the open (pink) tab in TABS_X, or None if no single tab is pink."""
    px = win[TAB_Y[0] : TAB_Y[1]].astype(int)
    pink = px[..., 2] - px[..., 0] > PINK_RB
    counts = [int(pink[:, a:b].sum()) for a, b in TABS_X]
    best = int(np.argmax(counts))
    return best if counts[best] >= PINK_MIN else None


def _name_line(win: np.ndarray) -> tuple[int, int] | None:
    """Rows (first, last) of the window holding the quest's name, or None."""
    x, y, w, h = BODY
    body = win[y : y + h, x : x + w]
    rows = np.flatnonzero(glyphs.mask(body, INK_LO, INK_HI).any(axis=1))
    for run in np.split(rows, np.flatnonzero(np.diff(rows) > 1) + 1):
        if run.size and run[0] > 0 and (np.median(body[run[0] - 1], axis=0) >= WHITE).all():
            return y + int(run[0]), y + int(run[-1])
    return None


def _row(win: np.ndarray) -> tuple[int, int, int, int] | None:
    """The selected list row's text box (x, y, w, h of the window), or None."""
    x, y, w, h = LIST
    blue = (np.abs(win[y : y + h, x : x + w].astype(int) - ROW_BLUE).max(axis=2)) <= ROW_TOL
    rows = np.flatnonzero(blue.sum(axis=1) >= ROW_MIN)
    if rows.size == 0 or rows[-1] - rows[0] >= ROW_H:
        return None
    cols = np.flatnonzero(blue[rows].any(axis=0))
    # 2 px in from the blue's edge, so ocr.crop's margin stays off the white around it.
    return x + cols[0] + 2, y + rows[0] + 2, cols[-1] - cols[0] - 3, rows[-1] - rows[0] - 3


def _read(
    frame: np.ndarray, native: np.ndarray, box: tuple[int, int, int, int], lo: tuple, hi: tuple
) -> str | None:
    """The text in `box` (normalized x, y, w, h) inked from `lo` to `hi`, or None when the
    OCR has none or marks what it cannot read (replacement or control characters)."""
    lines = ocr.read_lines(glyphs.mask(ocr.crop(frame, native, box), lo, hi))
    text = " ".join(lines or []).strip()
    return text if text.isprintable() and "\ufffd" not in text else None


def read_quest_window(
    frame: np.ndarray, native: np.ndarray | None = None, scale: float | None = None
) -> QuestOpen | str | None:
    """The quest window in `frame` (normalized), read from `native` (default `frame`).

    None if no window is found, no tab is open (pink) or it's the Completed tab;
    UNREADABLE if one is but the frame's edge cuts its details body; NAME_UNREADABLE if
    neither the name line nor the selected list row reads as a known quest name (the
    text is scrolled, or no row is selected).

    Limit: the "QUEST" title is the anchor, at the window's top-left, so a window dragged
    past the frame's left or top edge isn't found and reads None, as if closed.
    """
    native = frame if native is None else native
    scale = native.shape[0] / frame.shape[0] if scale is None else scale
    hit = window.align(frame, native, scale, ANCHORS, (WIN_W, WIN_H))
    if hit is None:
        return None
    win, (wx, wy) = hit
    tab = _tab(win)
    if tab is None or TAKEN[tab] is None:
        return None
    x, y, w, h = BODY
    fh, fw = frame.shape[:2]
    if not (0 <= wx + x <= fw - w and 0 <= wy + y <= fh - h):
        return UNREADABLE
    name = None
    if line := _name_line(win):
        box = (wx + x, wy + line[0], w, line[1] - line[0] + 1)
        text = _read(frame, native, box, INK_LO, OCR_INK_HI)
        name = text and _snap(text)
    if not name and (row := _row(win)):
        box = (wx + row[0], wy + row[1], row[2], row[3])
        text = _read(frame, native, box, ROW_INK_LO, (255, 255, 255))
        name = text and _listed(text)
    return QuestOpen(name, TAKEN[tab]) if name else NAME_UNREADABLE
