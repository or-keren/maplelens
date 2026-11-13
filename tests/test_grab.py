import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "grab", Path(__file__).parent.parent / "scripts" / "grab.py"
)
grab = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(grab)


def test_screen_crop_picks_the_screen_and_offsets():
    # (x, y, logical w, logical h, dpr): Qt keeps each screen's native top-left
    screens = [(0, 0, 2048, 1152, 1.25), (2560, 0, 1920, 1080, 1.0)]
    assert grab.screen_crop((320, 180, 1920, 1080), screens) == (0, (320, 180, 1920, 1080))
    assert grab.screen_crop((2660, 50, 800, 600), screens) == (1, (100, 50, 800, 600))
    assert grab.screen_crop((-5000, 0, 10, 10), screens) is None


def test_screen_crop_uses_the_physical_size():
    # 2048 logical px at 1.25 is 2560 physical: x = 2500 is still on the first screen
    screens = [(0, 0, 2048, 1152, 1.25), (2560, 0, 1920, 1080, 1.0)]
    assert grab.screen_crop((2500, 0, 50, 50), screens) == (0, (2500, 0, 50, 50))
