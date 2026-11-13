"""Map name reader: the minimap's title, as "<region> / <name>".

The title has two forms. Normal: a "MINI MAP" header bar, then region and name on two
text lines. Minimized (and small indoor maps): one bar reading "Region : Name".
"""

import json
import re
from collections.abc import Collection
from difflib import SequenceMatcher
from functools import cache, lru_cache
from pathlib import Path

import numpy as np

from maplelens.readers import glyphs, ocr

# Normalized-frame area searched for the anchors (the minimap starts top-left).
# ponytail: a minimap dragged out of this band reads None; widen it if players do
BAND_W, BAND_H = 700, 200

# Normal form: text box relative to the minimap_title anchor ("MINI MAP" label).
# It holds both lines and stops 1 row above the panel's bottom edge.
TITLE_DX, TITLE_DY, TITLE_H = 40, 18, 31
# The box ends where the panel's plain blue stops on its first row (no text there):
# the minimap widens to fit long names, so the width varies by map.
PANEL = (204, 187, 153)
# Ink: the white letters (red >= 175); the panel is 153, the letters' outline darker.
TITLE_INK_LO, TITLE_INK_HI = (0, 0, 175), (255, 255, 255)

# Bar form: the minimap_bar anchor is the bar's grey "- + WORLD" buttons; the text sits
# to their left, from the bar's left end, found the same way along its plain top row.
BAR_DY, BAR_H = 1, 13
BAR = (221, 221, 221)
# Ink: the dark grey letters on the light grey bar.
BAR_INK_LO, BAR_INK_HI = (0, 0, 0), (150, 150, 150)
# Max per-channel step from PANEL / BAR that still counts as plain background.
BG_TOL = 6

# Both OCRs misread letters (Vision: "Sumset", "Harhor"; Windows: "Eflinia"), so the
# text snaps to the known titles: to the only title one letter away, else to one with a
# similarity of at least SNAP_MIN and a lead of SNAP_LEAD over the runner-up.
SNAP_MIN, SNAP_LEAD = 0.9, 0.1
# Vision reads a trailing roman numeral as digits.
ROMAN = {"1": "I", "11": "II", "111": "III"}
# What tells numbered sibling maps apart: digits and roman numerals.
NUMBERS = re.compile(r"\d+|\b[IVX]+\b")


@cache
def known_titles() -> frozenset[str]:
    data = Path(__file__).parents[1] / "data" / "maps.json"
    return frozenset(f"{m['street']} / {m['name']}" for m in json.loads(data.read_text("utf-8")))


def _one_letter_apart(a: str, b: str) -> bool:
    """Different strings that one changed, added or dropped letter would make equal."""
    # n: how many leading characters match
    n = next((i for i, (x, y) in enumerate(zip(a, b, strict=False)) if x != y), min(len(a), len(b)))
    return a[n + 1 :] == b[n + 1 :] or a[n + 1 :] == b[n:] or a[n:] == b[n + 1 :]


def snap_title(text: str, titles: Collection[str]) -> str:
    """`text` as the known title it most clearly resembles, else unchanged."""
    if text in titles:
        return text
    roman = re.sub(r"\b(1|11|111)$", lambda m: ROMAN[m[1]], text)
    if roman in titles:
        return roman
    # Windows OCR can drop a title's last word ("The Forest North of" for "... of Ellinia"),
    # sometimes with a case slip too ("The field Up North of").
    cut = [t for t in titles if t.casefold().startswith(text.casefold() + " ")]
    if len(cut) == 1:
        return cut[0]
    # Similarity can't part titles that nearly contain each other: "The Rafn-Forest East of
    # Henesys" scores 0.98 on The Rain-Forest East of Henesys, 0.94 on The Forest East of.
    # Never across a number: "Ice Valley U" is one letter from Ice Valley I but may be II.
    numbers = NUMBERS.findall(text)
    near = [t for t in titles if _one_letter_apart(text, t) and NUMBERS.findall(t) == numbers]
    if len(near) == 1:
        return near[0]
    scored = sorted(((SequenceMatcher(None, text, t).ratio(), t) for t in titles), reverse=True)
    if len(scored) < 2:
        return text
    (best, title), (second, _) = scored[:2]
    return title if best >= SNAP_MIN and best - second >= SNAP_LEAD else text


@lru_cache(maxsize=256)
def _snap(text: str) -> str:
    return snap_title(text, known_titles())


def _plain(row: np.ndarray, colour: tuple[int, int, int]) -> int:
    """Count of leading pixels in `row` within BG_TOL of `colour`."""
    ok = (np.abs(row.astype(int) - colour) <= BG_TOL).all(axis=1)
    return int(np.argmin(ok)) if not ok.all() else len(ok)


def _ink_rows(m: np.ndarray) -> int:
    """Count of runs of ink rows, split by empty pixel rows."""
    rows = np.flatnonzero(m.any(axis=1))
    return 0 if rows.size == 0 else 1 + int(np.count_nonzero(np.diff(rows) > 1))


def _lines(frame, native, box, lo, hi) -> list[str] | None:
    lines = ocr.read_lines(glyphs.mask(ocr.crop(frame, native, box), lo, hi))
    # OCR marks what it cannot read with replacement or control characters.
    return lines if lines and all(t.isprintable() and "\ufffd" not in t for t in lines) else None


def _normal(frame: np.ndarray, native: np.ndarray, x: int, y: int) -> str | None:
    x, y = x + TITLE_DX, y + TITLE_DY
    w = _plain(frame[y, x:], PANEL)
    if w == 0:
        return None
    # A window over the title merges the text rows; then OCR could read the window's title.
    if _ink_rows(glyphs.mask(frame[y : y + TITLE_H, x : x + w], TITLE_INK_LO, TITLE_INK_HI)) != 2:
        return None
    lines = _lines(frame, native, (x, y, w, TITLE_H), TITLE_INK_LO, TITLE_INK_HI)
    return " / ".join(lines) if lines and len(lines) == 2 else None


def _bar(frame: np.ndarray, native: np.ndarray, x: int, y: int) -> str | None:
    y += BAR_DY
    w = _plain(frame[y, x - 2 :: -1], BAR) if x >= 2 else 0
    if w == 0:
        return None
    lines = _lines(frame, native, (x - 1 - w, y, w, BAR_H), BAR_INK_LO, BAR_INK_HI)
    text = " ".join(lines or [])
    if text.count(":") != 1:
        return None
    region, name = (part.strip() for part in text.split(":"))
    return f"{region} / {name}" if region and name else None


def read_map_name(frame: np.ndarray, native: np.ndarray | None = None) -> str | None:
    """Map as "<region> / <name>" from a normalized frame, or None if unreadable.

    `native` is the same shot before normalizing (default: `frame`); OCR reads its pixels.
    """
    native = frame if native is None else native
    band = frame[:BAND_H, :BAND_W]
    hit = glyphs.find_anchor(band, "minimap_title")
    if hit is not None:
        name = _normal(frame, native, *hit)
    else:
        hit = glyphs.find_anchor(band, "minimap_bar")
        name = None if hit is None else _bar(frame, native, *hit)
    return None if name is None else _snap(name)
