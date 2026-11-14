"""Monster search: which maps a monster spawns on, and the search list with monsters in it."""

from collections import Counter
from dataclasses import dataclass

from maplelens.spawns import Monster, SpotData
from maplelens.tools.path_arrow.maps import MapInfo, search


@dataclass(frozen=True)
class Haunt:
    map_id: str
    count: int  # this monster's spawn spots on the map
    total: int  # all spawn spots on the map
    types: int  # different monsters on the map

    @property
    def share(self) -> int:
        return round(100 * self.count / self.total)


@dataclass(frozen=True)
class MonsterHit:
    id: str
    monster: Monster


def haunts(spots: SpotData, maps: dict[str, MapInfo], monster_id: str) -> list[Haunt]:
    """The maps in `maps` where the monster spawns: most spots first, then the higher
    share of the map's spots, then by map name."""
    found = []
    for map_id, m in spots.maps.items():
        if map_id not in maps:
            continue  # no route data: the arrow can't lead there
        per = Counter(mob for mob, _, _ in m.spawns)
        if per[monster_id]:
            found.append(Haunt(map_id, per[monster_id], len(m.spawns), len(per)))
    found.sort(key=lambda h: (-h.count, -h.count / h.total, maps[h.map_id].name))
    return found


def matches(
    maps: dict[str, MapInfo], spots: SpotData, text: str, limit: int = 8
) -> list[MapInfo | MonsterHit]:
    """`search`'s maps plus the monsters whose name contains `text` and that spawn on a
    map we can route to; names starting with `text` first, then A-Z, as `search` ranks."""
    t = text.strip().lower()
    if not t:
        return []
    hits: list[MapInfo | MonsterHit] = list(search(maps, text, limit=len(maps)))
    hits += [
        MonsterHit(i, mon)
        for i, mon in spots.monsters.items()
        if t in mon.name.lower() and haunts(spots, maps, i)
    ]

    def name(h: MapInfo | MonsterHit) -> str:
        return h.monster.name if isinstance(h, MonsterHit) else h.name

    hits.sort(key=lambda h: (not name(h).lower().startswith(t), name(h)))
    return hits[:limit]
