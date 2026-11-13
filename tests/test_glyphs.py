from pathlib import Path

import cv2
import numpy as np
import pytest

from maplelens.readers import glyphs

CHARS = {**{str(d): str(d) for d in range(10)}, "comma": ","}


@pytest.fixture
def templates(tmp_path, monkeypatch):
    monkeypatch.setattr(glyphs, "TEMPLATES", tmp_path)
    glyphs.clear_cache()
    yield tmp_path
    glyphs.clear_cache()


@pytest.fixture
def font(templates):
    """Synthetic font `f`: ink masks drawn with cv2.putText. Returns {char: bool mask}."""
    (templates / "f").mkdir()
    out = {}
    for name, ch in CHARS.items():
        canvas = np.zeros((60, 60), np.uint8)
        cv2.putText(canvas, ch, (5, 45), cv2.FONT_HERSHEY_SIMPLEX, 1.0, 255, 2)
        ys, xs = np.nonzero(canvas > 127)
        crop = canvas[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]
        cv2.imwrite(str(templates / "f" / f"{name}.png"), crop)
        out[ch] = crop > 127
    return out


def line(font, text, gap=1, space=8):
    """Lay glyph masks left to right; ' ' is a `space`-wide empty gap."""
    h = max(m.shape[0] for m in font.values())
    parts = []
    for ch in text:
        if ch == " ":
            parts.append(np.zeros((h, space - gap), bool))
            continue
        m = np.zeros((h, font[ch].shape[1]), bool)
        m[: font[ch].shape[0]] = font[ch]
        parts += [m, np.zeros((h, gap), bool)]
    return np.hstack(parts)


def noise(h, w, seed):
    return np.random.default_rng(seed).integers(0, 256, (h, w, 3), dtype=np.uint8)


def test_normalize_scales_to_768():
    out = glyphs.normalize(np.zeros((1440, 2560, 3), np.uint8))
    assert out.shape == (768, round(2560 * 768 / 1440), 3)
    frame = np.zeros((768, 1366, 3), np.uint8)
    assert glyphs.normalize(frame) is frame


def test_find_anchor_recovers_after_move(templates):
    cv2.imwrite(str(templates / "exp_label.png"), noise(20, 30, 1))
    anchor = noise(20, 30, 1)
    frame = np.zeros((768, 1366, 3), np.uint8)
    frame[0:20, 0:30] = anchor
    assert glyphs.find_anchor(frame, "exp_label") == (0, 0)
    moved = np.zeros((768, 1366, 3), np.uint8)
    moved[300:320, 500:530] = anchor
    assert glyphs.find_anchor(moved, "exp_label") == (500, 300)
    assert glyphs.find_anchor(moved, "exp_label") == (500, 300)  # cached spot, same answer


def test_find_anchor_missing_is_none(templates):
    cv2.imwrite(str(templates / "exp_label.png"), noise(20, 30, 1))
    assert glyphs.find_anchor(noise(768, 1366, 2), "exp_label") is None


def test_mask_range():
    img = np.array([[[10, 20, 30], [10, 20, 31], [9, 20, 30]]], np.uint8)
    m = glyphs.mask(img, (10, 20, 30), (10, 20, 30))
    assert m.dtype == bool
    assert m.tolist() == [[True, False, False]]


def test_read_text_reads_digits_and_space(font):
    assert glyphs.read_text(line(font, "12,3 45"), "f", space_px=6) == "12,3 45"


def test_glyph_one_px_off_is_none(font):
    """Matching is exact (R17): one extra ink row, or one flipped pixel, reads None."""
    seven = font["7"]
    assert glyphs.read_text(seven, "f", space_px=6) == "7"
    assert glyphs.read_text(np.vstack([seven, seven[-1:]]), "f", space_px=6) is None
    flipped = seven.copy()
    flipped[0, 0] = ~flipped[0, 0]
    assert glyphs.read_text(flipped, "f", space_px=6) is None


def test_unknown_glyph_is_none(font):
    ok = line(font, "1")
    blob = np.ones((ok.shape[0], 10), bool)
    assert glyphs.read_text(blob, "f", space_px=6) is None
    assert glyphs.read_text(np.hstack([ok, blob]), "f", space_px=6) is None


def test_gap_below_space_px_is_no_space(font):
    assert glyphs.read_text(line(font, "1 2", space=5), "f", space_px=6) == "12"
    assert glyphs.read_text(line(font, "1 2", space=6), "f", space_px=6) == "1 2"


def test_glyph_two_px_off_is_none(font):
    seven = font["7"]
    assert glyphs.read_text(np.vstack([seven, seven[-2:]]), "f", space_px=6) is None


def test_missing_font_raises(templates):
    with pytest.raises(FileNotFoundError, match="nofont"):
        glyphs.read_text(np.ones((5, 5), bool), "nofont", space_px=6)


def test_read_text_splits_touching_glyphs(font):
    # At 2560x1440 the normalized EXP digits touch, with no empty column between them.
    assert glyphs.read_text(line(font, "2,30", gap=0), "f", space_px=6) == "2,30"


def test_find_anchor_recovers_after_move_fixture():
    glyphs.clear_cache()
    fix = cv2.imread(str(Path(__file__).parent / "fixtures/screens/exp_a_2560x1440_100.png"))
    h, w = fix.shape[:2]
    ax, ay = glyphs.find_anchor(fix, "exp_label")
    frame = np.zeros((768, 1366, 3), np.uint8)
    frame[:h, :w] = fix
    assert glyphs.find_anchor(frame, "exp_label") == (ax, ay)
    moved = np.zeros((768, 1366, 3), np.uint8)
    moved[300 : 300 + h, 500 : 500 + w] = fix
    assert glyphs.find_anchor(moved, "exp_label") == (500 + ax, 300 + ay)


def test_glyph_variants_share_a_char(templates):
    (templates / "v").mkdir()
    a = np.zeros((5, 4), np.uint8)
    a[:, 0] = a[-1] = 255  # an L
    b = np.zeros((5, 4), np.uint8)
    b[0] = b[:, -1] = 255  # its mirror image, upside down
    cv2.imwrite(str(templates / "v" / "comma.png"), a)
    cv2.imwrite(str(templates / "v" / "comma_b.png"), b)
    m = np.hstack([a, np.zeros((5, 3)), b]) > 0
    assert glyphs.read_text(m, "v", space_px=9) == ",,"


def _write_png(path, img):
    # imencode + tofile: imwrite, like imread, fails on non-ASCII paths on Windows
    assert cv2.imencode(".png", img)[1].tofile(path) is None


def test_templates_load_from_non_ascii_folder(tmp_path, monkeypatch):
    # The installed app lives under C:\Users\<name>\..., and <name> may be non-ASCII.
    root = tmp_path / "דניאל"
    (root / "f").mkdir(parents=True)
    anchor = noise(6, 8, seed=1)
    _write_png(root / "a.png", anchor)
    glyph = np.full((5, 1), 255, np.uint8)  # a 1
    _write_png(root / "f" / "1.png", glyph)
    monkeypatch.setattr(glyphs, "TEMPLATES", root)
    glyphs.clear_cache()
    try:
        assert np.array_equal(glyphs.load("a"), anchor)
        assert glyphs.read_text(glyph > 0, "f", space_px=9) == "1"
    finally:
        glyphs.clear_cache()


def test_missing_template_raises(templates):
    with pytest.raises(FileNotFoundError):
        glyphs.load("nope")


def _band():
    img = cv2.imread(
        str(Path(__file__).parent / "fixtures/screens/fullscreen_exp_a_3024x1700_100.png")
    )
    return cv2.resize(img, None, fx=768 / 1700, fy=768 / 1700, interpolation=cv2.INTER_AREA)


def _cold(frame):
    glyphs.clear_cache()
    return glyphs.find_anchor(frame, "exp_label")


def test_find_anchor_looks_near_its_last_spot(monkeypatch):
    band = _band()
    glyphs.clear_cache()
    first = glyphs.find_anchor(band, "exp_label")
    assert first is not None
    calls = []
    real = cv2.matchTemplate
    monkeypatch.setattr(
        glyphs.cv2,
        "matchTemplate",
        lambda img, tpl, m: calls.append(img.shape[:2]) or real(img, tpl, m),
    )
    assert glyphs.find_anchor(band, "exp_label") == first
    assert calls
    for name in glyphs._anchor_names("exp_label"):
        th, tw = glyphs.load(name).shape[:2]
        assert all(h <= th + 2 * glyphs.NEAR and w <= tw + 2 * glyphs.NEAR for h, w in calls)


@pytest.mark.parametrize("dx", [1, 5])
def test_find_anchor_follows_a_moved_anchor(dx):
    band = _band()
    moved = np.pad(band, ((0, 0), (dx, 0), (0, 0)), mode="edge")[:, :-dx]
    glyphs.clear_cache()
    glyphs.find_anchor(band, "exp_label")
    warm = glyphs.find_anchor(moved, "exp_label")
    assert warm is not None
    assert warm == _cold(moved)


def test_find_anchor_searches_again_when_the_anchor_is_gone():
    band = _band()
    glyphs.clear_cache()
    cold = glyphs.find_anchor(band, "exp_label")
    assert glyphs.find_anchor(np.zeros_like(band), "exp_label") is None
    assert "exp_label" not in glyphs._last_hit
    assert glyphs.find_anchor(band, "exp_label") == cold


def _recorded(monkeypatch):
    calls = []
    real = cv2.matchTemplate
    monkeypatch.setattr(
        glyphs.cv2,
        "matchTemplate",
        lambda img, tpl, m: calls.append(img.shape[:2]) or real(img, tpl, m),
    )
    return calls


def _padded():
    return np.pad(_band(), ((20, 20), (20, 20), (0, 0)), mode="edge")


def _shift(img, dx, dy):
    m = np.float32([[1, 0, dx], [0, 1, dy]])
    return cv2.warpAffine(img, m, (img.shape[1], img.shape[0]), borderMode=cv2.BORDER_REPLICATE)


def _is_near(calls):
    th, tw = glyphs.load("exp_label_1366").shape[:2]
    return all(h <= th + 2 * glyphs.NEAR and w <= tw + 2 * glyphs.NEAR for h, w in calls)


@pytest.mark.parametrize("dx, dy", [(2, 0), (-2, 0), (0, 2), (0, -2)])
def test_find_anchor_ignores_a_peak_on_the_boxs_edge(monkeypatch, dx, dy):
    # Anchor well inside the frame: a peak on a box edge may continue outside, so search all.
    band = _padded()
    moved = _shift(band, dx, dy)
    glyphs.clear_cache()
    glyphs.find_anchor(band, "exp_label")
    calls = _recorded(monkeypatch)
    warm = glyphs.find_anchor(moved, "exp_label")
    assert not _is_near(calls)  # a full search ran
    assert warm == _cold(moved)


def test_find_anchor_accepts_a_peak_on_the_frames_right_edge(monkeypatch):
    frame = _padded()[:, :48]  # the template ends at the frame's right edge
    glyphs.clear_cache()
    assert glyphs.find_anchor(frame, "exp_label") == (22, 21)
    calls = _recorded(monkeypatch)
    assert glyphs.find_anchor(_shift(frame, 1, 0), "exp_label") == (23, 21)
    assert _is_near(calls)


def test_find_anchor_accepts_a_peak_on_the_frames_edge(monkeypatch):
    band = _band()
    glyphs.clear_cache()
    assert glyphs.find_anchor(band[:, 1:], "exp_label") == (1, 1)
    calls = _recorded(monkeypatch)
    assert glyphs.find_anchor(band[:, 2:], "exp_label") == (0, 1)
    assert _is_near(calls)


def test_read_scaled_reads_the_same_digits_once(monkeypatch):
    from maplelens.readers.exp import read_exp

    glyphs.clear_cache()
    native = cv2.imread(
        str(Path(__file__).parent / "fixtures/screens/fullscreen_exp_a_3024x1700_100.png"),
        cv2.IMREAD_COLOR,
    )
    frame = cv2.resize(native, None, fx=768 / 1700, fy=768 / 1700, interpolation=cv2.INTER_AREA)
    first = read_exp(frame, native)
    assert first is not None
    calls = []
    real = cv2.matchTemplate
    monkeypatch.setattr(cv2, "matchTemplate", lambda *a, **k: calls.append(1) or real(*a, **k))
    assert read_exp(frame, native) == first
    assert len(calls) <= 3
    glyphs.clear_cache()
