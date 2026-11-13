"""Readers: screenshot -> value, plus the shared types and read_all."""

from collections.abc import Collection
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from maplelens.readers.minimap_pos import MinimapView
    from maplelens.readers.quest_tracker import Tracker
    from maplelens.readers.quest_window import QuestOpen
    from maplelens.readers.skill_window import SkillWindow
    from maplelens.readers.stat_window import StatWindow


@dataclass(frozen=True)
class ExpValue:
    raw: int
    pct: float


@dataclass(frozen=True)
class Reading:
    t: float
    exp: ExpValue | None
    level: int | None
    job: str | None
    map_name: str | None
    player: tuple[float, float] | None = None  # see minimap_pos.read_player
    minimap: "MinimapView | None" = None  # see minimap_pos.read_view
    stats: "StatWindow | str | None" = None  # see stat_window.read_stat_window
    skills: "SkillWindow | str | None" = None  # see skill_window.read_skill_window
    quest: "QuestOpen | str | None" = None  # the quest window; None: none open
    tracker: "Tracker | str | None" = None  # see quest_tracker.read_quest_tracker


# The windows that may not be on screen, each its own field. The minimap isn't one: the
# path arrow needs its map name every tick (a miss reads as "open the minimap").
OPTIONAL = ("stats", "skills", "quest", "tracker")
GRACE = 4  # ticks a part stays due after it was last on screen


def due(turn: int, seen_at: dict[str, int]) -> frozenset[str]:
    """The parts to read this turn: those seen within GRACE turns, plus one in turn.

    An open window is read every tick; a closed one is searched for on one tick in four.
    """
    recent = {p for p in OPTIONAL if p in seen_at and turn - seen_at[p] <= GRACE}
    return frozenset(recent | {OPTIONAL[turn % len(OPTIONAL)]})


def found(r: Reading) -> set[str]:
    """The parts of OPTIONAL that `r` saw on screen."""
    return {p for p in OPTIONAL if getattr(r, p) is not None}


def read_all(frame: np.ndarray, t: float, due: Collection[str] = OPTIONAL) -> Reading:
    """Read one game frame: EXP, level, job and the minimap always, each window of
    OPTIONAL if in `due` (else its field is None). Submodules load here, not at import time."""
    from maplelens.readers import (
        exp,
        glyphs,
        job,
        level,
        map_name,
        minimap_pos,
        quest_tracker,
        quest_window,
        skill_window,
        stat_window,
    )

    img = glyphs.normalize(frame)
    scale = frame.shape[0] / glyphs.BASE_H
    view = minimap_pos.read_view(img)
    return Reading(
        t,
        exp.read_exp(img, frame),
        level.read_level(img, frame),
        job.read_job(img, frame),
        map_name.read_map_name(img, frame),
        None if view is None else view.fraction,
        view,
        stat_window.read_stat_window(img, frame, scale) if "stats" in due else None,
        skill_window.read_skill_window(img, frame, scale) if "skills" in due else None,
        quest_window.read_quest_window(img, frame, scale) if "quest" in due else None,
        quest_tracker.read_quest_tracker(img, frame, scale) if "tracker" in due else None,
    )
