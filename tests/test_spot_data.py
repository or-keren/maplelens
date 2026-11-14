import os

import pytest

from maplelens.gamedata import PICTURES, load_spots
from maplelens.tools.class_helper.data import load


def test_every_training_spot_has_spawn_data():
    spots, classes = load_spots(), load()
    ids = {t.place.map_id for p in classes.jobs.values() for t in p.training if t.place.map_id}
    assert ids and ids <= spots.maps.keys()


def test_every_spawning_monster_has_stats_and_a_picture():
    spots = load_spots()
    for m in spots.maps.values():
        for mob, _, _ in m.spawns:
            assert mob in spots.monsters and spots.icon(mob), mob


def test_every_map_with_spawns_has_a_picture_and_they_lie_inside_it():
    spots = load_spots()
    for map_id, m in spots.maps.items():
        if m.spawns:
            assert spots.picture(map_id), map_id
        assert all(0 <= x <= m.size[0] and 0 <= y <= m.size[1] for _, x, y in m.spawns), map_id


def test_map_pictures_stay_under_10_mb():
    assert sum(p.stat().st_size for p in PICTURES.glob("*.webp")) < 10_000_000


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def test_qt_reads_a_map_picture(qapp):  # the qwebp plugin is there
    from PySide6.QtGui import QPixmap

    path = next(PICTURES.glob("*.webp"))
    assert not QPixmap(str(path)).isNull()
