"""monsters.json: each map's monster spawn spots and the monsters' stats (from OSMS).

Shared by the Class tool (the training spot card) and the Path tool (monster search).
"""

import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path

SPOTS = Path(__file__).parent / "data" / "monsters.json"
PICTURES = Path(__file__).parent / "data" / "map_pictures"
ICONS = Path(__file__).parent / "data" / "monster_icons"


@dataclass(frozen=True)
class Monster:
    name: str
    level: int
    hp: int
    exp: int


@dataclass(frozen=True)
class MapSpawns:
    size: tuple[int, int]  # the shipped picture's pixels
    cap: int | None
    spawns: tuple[tuple[str, int, int], ...]  # (monster id, x, y) in the picture's pixels
    respawn: dict[str, tuple[float, float]]  # monster id -> (shortest, longest) seconds


@dataclass(frozen=True)
class SpotData:
    maps: dict[str, MapSpawns]
    monsters: dict[str, Monster]
    pictures: Path
    icons: Path

    def picture(self, map_id: str) -> Path | None:
        p = self.pictures / f"{map_id}.webp"
        return p if p.is_file() else None

    def icon(self, monster: str) -> Path | None:
        p = self.icons / f"{monster}.png"
        return p if p.is_file() else None


@cache
def load_spots(path: Path = SPOTS, pictures: Path = PICTURES, icons: Path = ICONS) -> SpotData:
    raw = json.loads(path.read_text("utf-8"))
    maps = {
        i: MapSpawns(
            (m["size"][0], m["size"][1]),
            m.get("cap"),
            tuple((mob, x, y) for mob, x, y in m["spawns"]),
            {mob: (lo, hi) for mob, (lo, hi) in m.get("respawn", {}).items()},
        )
        for i, m in raw["maps"].items()
    }
    monsters = {
        i: Monster(m["name"], m["level"], m["hp"], m["exp"]) for i, m in raw["monsters"].items()
    }
    return SpotData(maps, monsters, pictures, icons)
