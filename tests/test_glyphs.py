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
