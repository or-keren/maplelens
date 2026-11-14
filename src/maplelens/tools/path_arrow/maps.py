"""The bundled map data: portals, minimap geometry, cab links and minimap pictures."""

import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import cv2
import numpy as np

DATA = Path(__file__).parents[2] / "data" / "maps.json"
# One PNG per map, named by map id: the whole minimap picture, without markers.
PICTURES = Path(__file__).parents[2] / "data" / "minimaps"


@dataclass(frozen=True)
class Portal:
    x: int
    y: int
    to: str
    hidden: bool = False  # no spiral on the minimap: walk there and press up


@dataclass(frozen=True)
class Cab:
    x: int
    y: int
    to: tuple[str, ...]


@dataclass(frozen=True)
class Minimap:
    w: int
    h: int
    cx: int
    cy: int


@dataclass(frozen=True)
class MapInfo:
    id: str
    street: str
    name: str
    town: bool
    minimap: Minimap | None
    portals: tuple[Portal, ...]
    cab: Cab | None
    npcs: tuple[tuple[int, int], ...] = ()  # world positions; the minimap marks them

    @property
    def title(self) -> str:
        return f"{self.street} / {self.name}"


def load(path: Path = DATA) -> dict[str, MapInfo]:
    maps = {}
    for e in json.loads(path.read_text(encoding="utf-8")):
        cab = e.get("cab")
        maps[e["id"]] = MapInfo(
            e["id"],
            e["street"],
            e["name"],
            e["town"],
            Minimap(**e["minimap"]) if e["minimap"] else None,
            tuple(Portal(**p) for p in e["portals"]),
            Cab(cab["x"], cab["y"], tuple(cab["to"])) if cab else None,
            tuple((n["x"], n["y"]) for n in e["npcs"]),
        )
    return maps


@cache
def picture(map_id: str) -> np.ndarray | None:
    """The map's whole minimap picture (BGRA), or None if we don't ship one.

    Alpha 255 marks the solid map art; the rest is see-through in the game.
    """
    path = PICTURES / f"{map_id}.png"
    if not path.is_file():
        return None
    # fromfile + imdecode: imread fails on non-ASCII paths
    img = cv2.imdecode(np.fromfile(path, np.uint8), cv2.IMREAD_UNCHANGED)
    return img if img.shape[2] == 4 else cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)


def find(maps: dict[str, MapInfo], title: str, previous: str | None) -> MapInfo | None:
    """The map with this title; if several share it, the one `previous` leads to."""
    hits = [m for m in maps.values() if m.title == title]
    if len(hits) <= 1:
        return hits[0] if hits else None
    prev = maps.get(previous) if previous else None
    if prev is None:
        return None
    linked = [m for m in hits if any(p.to == m.id for p in prev.portals)]
    return linked[0] if len(linked) == 1 else None
