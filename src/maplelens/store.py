"""Settings file and data folder."""

import copy
import json
import os
import sys
from pathlib import Path

DEFAULTS = {
    "window_title": None,
    "idle_cutoff_s": 90,
    "jump_factor": 5,
    "boxes": {},
    "tab_width": None,  # the box's tabs, once the player has dragged its corner
    "pin_exp": False,  # the EXP line on every other tab
    "path_taxi": True,
    "class_builds": {},  # job -> the build name picked in the Class tab
    "class_marks": True,  # the AP/SP marks on the game's stat and skill windows
    "update_check": True,  # the installed Windows app asks GitHub for new versions
    "update_dismissed": None,  # the version whose notice line the player closed
    "quests_tracked": [],  # quest ids, in tracking order
    "quests_followed": [],  # quest ids seen in the game's Quest Helper; they leave with it
    "quests_expanded": None,  # the tracked quest shown open in the Quests tab
    "quests_closest": {},  # quest id (as text) -> True: Closest, False: Best; once switched
    "quest_rewards_open": False,  # the Quests tab's reward details shown, for every quest
    # the tools, each turned on or off in Settings
    "exp_on": True,
    "path_on": True,
    "class_on": True,
    "quests_on": True,
    "arrow_on": True,  # the path arrow over the character; off keeps the route list
    "arrow_size": 36,  # logical px, the arrow's square (ARROW_SIZES)
    "arrow_color": "#ffcc33",  # one of ARROW_COLORS; the box's yellow at first
}

ARROW_SIZES = range(24, 73, 4)  # the arrow sizes Settings offers, in px
# The arrow colours Settings offers, each with its name (a swatch's tooltip): bright, so
# they read over the game's maps, with the arrow's dark outline
ARROW_COLORS = {
    "#ffcc33": "Yellow",
    "#ffffff": "White",
    "#ff5a5a": "Red",
    "#5ee07a": "Green",
    "#4fd8ff": "Cyan",
    "#ff7ad9": "Pink",
}


def _arrow_size(value: object) -> object:
    """An arrow size, clamped into ARROW_SIZES and rounded to its step; None if not a number."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    lo, hi, step = ARROW_SIZES.start, ARROW_SIZES[-1], ARROW_SIZES.step
    return lo + int((min(max(value, lo), hi) - lo) / step + 0.5) * step  # halves round up


def _is_bool(value: object) -> bool:
    return isinstance(value, bool)


# key -> a check of a saved value; one that fails it loads as its default
CHECKS = {
    "exp_on": _is_bool,
    "path_on": _is_bool,
    "class_on": _is_bool,
    "quests_on": _is_bool,
    "arrow_on": _is_bool,
    "arrow_color": lambda value: isinstance(value, str) and value in ARROW_COLORS,
}
# key -> a fix of a saved value: the value to keep, or None for the default
FIXES = {"arrow_size": _arrow_size}


def data_dir() -> Path:
    if sys.platform == "darwin":
        d = Path.home() / "Library/Application Support/MapleLens"
    else:
        d = Path(os.environ["APPDATA"]) / "MapleLens"
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_settings(path: Path) -> dict:
    settings = copy.deepcopy(DEFAULTS)
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return settings
    if isinstance(saved, dict):
        settings.update(saved)
    return clean(settings)


def clean(settings: dict) -> dict:
    """Put back the default of each checked key whose value is wrong: a hand edit, or an
    old version's file, never breaks startup. Keys without a check are left as they are."""
    for key, ok in CHECKS.items():
        if not ok(settings[key]):
            settings[key] = copy.deepcopy(DEFAULTS[key])
    for key, fix in FIXES.items():
        fixed = fix(settings[key])
        settings[key] = DEFAULTS[key] if fixed is None else fixed
    return settings


def save_settings(path: Path, settings: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, indent=2), encoding="utf-8")
