"""Skill window reader: the open job tab, unspent SP, each visible skill's level and + button."""

import difflib
import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import numpy as np

from maplelens.readers import glyphs, ocr, window
from maplelens.readers.window import UNREADABLE

# The window, 768-scale: size, and the anchors (template, offset from its top-left).
WIN_W, WIN_H = 193, 367
ANCHORS = [("skill_title", (6, 4)), ("skill_bottom", (6, 346))]
# Row centres (y) are ROW_Y0 + ROW_DY * i; the level strip and the name box start at
# LEVEL_X / NAME_X. The strip ends before the + buttons, whose outline would count as ink.
ROW_Y0, ROW_DY, ROWS = 122, 40, 6
LEVEL_X, LEVEL_W = 44, 80
NAME_X, NAME_W = 44, 120
SP_BOX = (83, 346, 26, 15)
# Centre of the single-arrow + button (the left of the pair), relative to the top-left.
PLUS_DX = 145
# Name ink: dark letters on the pale rows. Up to 130, not 110: at 2560x1440 the scaled
# letters' soft edges sit between the two, and strokes broken there lost Windows OCR a word.
NAME_INK_LO, NAME_INK_HI = (0, 0, 0), (130, 130, 130)


@dataclass(frozen=True)
class SkillRow:
    skill: int
    level: int
    plus: tuple[int, int]  # the single-arrow + button's centre, in frame coordinates


@dataclass(frozen=True)
class SkillWindow:
    tab: str
    sp: int
    rows: tuple[SkillRow, ...]


@cache
def _table() -> dict[str, dict]:
    path = Path(__file__).parents[1] / "data" / "classes.json"
    return json.loads(path.read_text("utf-8"))["skills"]


@cache
def known_skills() -> dict[str, list[tuple[int, str]]]:
    """Skill name -> every (id, job) that has it (a name is unique per job, not overall)."""
    out: dict[str, list[tuple[int, str]]] = {}
    for sid, s in _table().items():
        out.setdefault(s["name"], []).append((int(sid), s["job"]))
    return out


def _max(skill: int) -> int:
    return _table()[str(skill)]["max"]


def _snap(text: str, names) -> str | None:
    """The known name `text` is read from (one letter may be misread), else None."""
    if text in names:  # an exact read wins, even with a one-letter twin ("Max HP/MP Increase")
        return text
    near = difflib.get_close_matches(text, names, n=2, cutoff=0.8)
    if not near or abs(len(near[0]) - len(text)) > 1:
        return None
    if len(near) > 1:  # a twin name that scores nearly as well: don't guess
        sm = difflib.SequenceMatcher(None, text)
        ratios = []
        for n in near:
            sm.set_seq2(n)
            ratios.append(sm.ratio())
        if ratios[0] - ratios[1] < 0.1:
            return None
    return near[0]


def read_skill_window(
    frame: np.ndarray, native: np.ndarray | None = None, scale: float | None = None
) -> SkillWindow | str | None:
    """The skill window in `frame` (normalized), read from `native` (default `frame`).

    None if no window is found; UNREADABLE if one is but a field is covered or misread,
    a name is unknown, the rows share no single job, or a level exceeds its skill's max.
    Rows whose name line is blank are left out.
    """
    native = frame if native is None else native
    scale = native.shape[0] / frame.shape[0] if scale is None else scale
    hit = window.align(frame, native, scale, ANCHORS, (WIN_W, WIN_H))
    if hit is None:
        return None
    win, (wx, wy) = hit
    sp = window.read_number_text(win, SP_BOX)
    if sp is None or not sp.isdigit():
        return UNREADABLE
    names = known_skills()
    found = []  # (candidates [(id, job)], level text, row index)
    for i in range(ROWS):
        cy = ROW_Y0 + ROW_DY * i
        box = (wx + NAME_X, wy + cy - 26, NAME_W, 14)
        ink = glyphs.mask(ocr.crop(frame, native, box), NAME_INK_LO, NAME_INK_HI)
        if not ink.any():
            continue  # a blank row
        name = _snap(" ".join(ocr.read_lines(ink) or []), names)  # ink read as nothing: covered
        level = window.read_number_text(win, (LEVEL_X, cy - 7, LEVEL_W, 15))
        if name is None or level is None or not level.isdigit():
            return UNREADABLE
        found.append((names[name], int(level), i))
    tabs = set.intersection(*({job for _, job in c} for c, _, _ in found)) if found else set()
    if len(tabs) != 1:
        return UNREADABLE
    (tab,) = tabs
    rows = []
    h, w = frame.shape[:2]
    for cands, level, i in found:
        skill = next(sid for sid, job in cands if job == tab)
        plus = (wx + PLUS_DX, wy + ROW_Y0 + ROW_DY * i)
        if level > _max(skill) or not (0 <= plus[0] < w and 0 <= plus[1] < h):
            return UNREADABLE  # a ring must never point at an off-screen +
        rows.append(SkillRow(skill, level, plus))
    return SkillWindow(tab, int(sp), tuple(rows))
