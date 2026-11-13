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
    "path_taxi": True,
    "class_builds": {},  # job -> the build name picked in the Class tab
    "class_marks": True,  # the AP/SP marks on the game's stat and skill windows
    "update_check": True,  # the installed Windows app asks GitHub for new versions
    "update_dismissed": None,  # the version whose notice line the player closed
    "quests_tracked": [],  # quest ids, in tracking order
    "quests_followed": [],  # quest ids seen in the game's Quest Helper; they leave with it
    "quests_expanded": None,  # the tracked quest shown open in the Quests tab
    "quests_closest": {},  # quest id (as text) -> True: Closest, False: Best; once switched
}


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
    return settings


def save_settings(path: Path, settings: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, indent=2), encoding="utf-8")
