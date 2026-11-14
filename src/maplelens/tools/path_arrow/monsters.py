"""Monster search: the monsters matching a name, and the maps each one spawns on."""

from collections import Counter
from dataclasses import dataclass

from maplelens.spawns import Monster, SpotData
from maplelens.tools.path_arrow.maps import MapInfo

# OSMS's ids for the copies of monsters made for quests, party quests and events (the
# job-advancement maps' Lv 30 Fire Boar, the Kerning PQ's King Slime). Field bosses sit
# in the 700000s and stay.
SPECIAL_FROM = 800000


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


def find_monsters(
    maps: dict[str, MapInfo], spots: SpotData, text: str, limit: int = 8
) -> list[MonsterHit]:
    """Monsters whose name contains `text` and that spawn on a map we can route to, special
    copies left out; names starting with `text` first, then A-Z, as `search` ranks maps."""
    t = text.strip().lower()
    if not t:
        return []
    hits = [
        MonsterHit(i, mon)
        for i, mon in spots.monsters.items()
        if t in mon.name.lower() and not _special(i) and haunts(spots, maps, i)
    ]
    hits.sort(key=lambda h: (not h.monster.name.lower().startswith(t), h.monster.name))
    return hits[:limit]


def _special(monster_id: str) -> bool:
    """A quest, party-quest or event copy: OSMS numbers them from SPECIAL_FROM."""
    return monster_id.isdigit() and int(monster_id) >= SPECIAL_FROM
