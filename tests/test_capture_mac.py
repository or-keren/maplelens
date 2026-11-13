import pytest

pytest.importorskip("Quartz")
import Quartz

from maplelens import capture_mac
from maplelens.capture import pick_window

INFOS = [
    {
        "kCGWindowNumber": 7,
        "kCGWindowOwnerName": "MapleStory Classic World",
        "kCGWindowName": "MapleStory",
    },
    {
        "kCGWindowNumber": 9,
        "kCGWindowOwnerName": "Google Chrome",
        "kCGWindowName": "MapleStory Classic Thief Guide",
    },
]
BOUNDS = {"X": 0, "Y": 0, "Width": 1366, "Height": 796}


def test_window_entries_title_and_owner():
    entries = capture_mac.window_entries(INFOS)
    assert pick_window(entries, "MapleStory") == 7
    assert pick_window(entries, "MapleStory Classic World") == 7


def test_client_rect_retina():
    assert capture_mac.client_rect_from(BOUNDS, True, 28, 2) == (0, 56, 2732, 1536)


def test_client_rect_scale_1():
    b = {**BOUNDS, "X": 1512}
    assert capture_mac.client_rect_from(b, True, 28, 1) == (1512, 28, 1366, 768)


def test_client_rect_no_title_bar():
    assert capture_mac.client_rect_from(BOUNDS, True, 0, 2) == (0, 0, 2732, 1592)


def test_client_rect_offscreen_is_none():
    assert capture_mac.client_rect_from(BOUNDS, False, 28, 2) is None
    assert capture_mac.client_rect_from({**BOUNDS, "Height": 28}, True, 28, 2) is None


def test_ensure_access_prints_once_when_denied(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(Quartz, "CGPreflightScreenCaptureAccess", lambda: False)
    monkeypatch.setattr(Quartz, "CGRequestScreenCaptureAccess", lambda: calls.append(1))
    assert capture_mac.ensure_access() is False
    assert calls == [1]
    out = capsys.readouterr().out
    assert "Screen Recording" in out and "System Settings" in out


def test_crop_bgr_cuts_title_and_flips():
    import numpy as np

    rgb = np.zeros((10, 8, 3), np.uint8)
    rgb[9, 0] = (1, 2, 3)
    out = capture_mac.crop_bgr(rgb, (0, 0, 6, 7))
    assert out.shape == (7, 6, 3) and out[6, 0].tolist() == [3, 2, 1]


def test_crop_bgr_shrunk_window_raises():
    import numpy as np

    with pytest.raises(RuntimeError):
        capture_mac.crop_bgr(np.zeros((10, 8, 3), np.uint8), (0, 0, 8, 11))
    with pytest.raises(RuntimeError):
        capture_mac.crop_bgr(np.zeros((10, 8, 3), np.uint8), (0, 0, 9, 10))


def _retina_window(game, title_px, shift):
    """A Retina window image: title bar, then the game pixel-doubled, `shift` rows lower."""
    import numpy as np

    doubled = game.repeat(2, axis=0).repeat(2, axis=1)
    h = title_px + len(doubled)
    rgb = np.full((h, doubled.shape[1], 3), 60, np.uint8)
    rgb[title_px + shift :] = doubled[: h - title_px - shift]
    return rgb, doubled


def test_crop_bgr_finds_game_one_retina_pixel_low():
    import numpy as np

    game = np.random.default_rng(0).integers(0, 256, (40, 30, 3), np.uint8)
    for shift in (0, 1):
        rgb, doubled = _retina_window(game, 8, shift)
        out = capture_mac.crop_bgr(rgb, (0, 0, 60, 80))
        assert np.array_equal(out, doubled[:, :, ::-1]), shift


def test_crop_bgr_keeps_top_without_doubling():
    import numpy as np

    rgb = np.random.default_rng(1).integers(0, 256, (90, 60, 3), np.uint8)
    rgb[40:60] = 0  # flat rows are equal in both phases
    out = capture_mac.crop_bgr(rgb, (0, 0, 60, 80))
    assert np.array_equal(out, rgb[10:, :, ::-1])


def test_has_access_and_request_access_wrap_quartz(monkeypatch):
    calls = []
    monkeypatch.setattr(capture_mac, "_access", {})
    monkeypatch.setattr(Quartz, "CGPreflightScreenCaptureAccess", lambda: True)
    monkeypatch.setattr(Quartz, "CGRequestScreenCaptureAccess", lambda: calls.append(1))
    assert capture_mac.has_access() is True
    capture_mac.request_access()
    assert calls == [1]


def test_has_access_asks_macos_at_most_every_10_s(monkeypatch):
    # asked on every tick, it jammed the service every capture goes through
    asked = []
    monkeypatch.setattr(capture_mac, "_access", {})
    monkeypatch.setattr(Quartz, "CGPreflightScreenCaptureAccess", lambda: asked.append(1) or False)
    assert [capture_mac.has_access(t) for t in (0, 0.5, 9.9)] == [False] * 3
    assert len(asked) == 1
    capture_mac.has_access(10)
    assert len(asked) == 2
