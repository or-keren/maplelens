"""Readers: screenshot -> value, plus the shared types and read_all."""

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


def read_all(frame: np.ndarray, t: float) -> Reading:
    """Read every field from one game frame. Submodules load here, not at import time."""
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
        exp.read_exp(img),
        level.read_level(img),
        job.read_job(img, frame),
        map_name.read_map_name(img, frame),
        None if view is None else view.fraction,
        view,
        stat_window.read_stat_window(img, frame, scale),
        skill_window.read_skill_window(img, frame, scale),
        quest_window.read_quest_window(img, frame, scale),
        quest_tracker.read_quest_tracker(img, frame, scale),
    )
