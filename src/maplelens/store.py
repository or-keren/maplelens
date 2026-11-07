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
    "path_taxi": True,
    "update_check": True,  # the installed Windows app asks GitHub for new versions
    "update_dismissed": None,  # the version whose notice line the player closed
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
