"""Character level reader."""

import numpy as np

from maplelens.readers import glyphs

# Digit boxes, relative to the lv_label anchor's top-left (normalized frame).
# Wide enough for three boxes; the class line starts a few px further right.
LV_DX, LV_DY, LV_W, LV_H = 24, 1, 47, 14
# Ink: the light digits; the orange boxes behind them stay below about 60 in blue.
LV_INK_LO, LV_INK_HI = (100, 100, 100), (255, 255, 255)
# Strict (R17): real digits match their templates pixel-exactly at every resolution;
# 1 px of noise reads None, never a wrong level. The templates for all ten digits are
# made by scripts/make_level_font.py, for 1366x768, 1920x1080 and 2560x1440 only.


def parse_level(text: str) -> int | None:
    """Digits only, 1..200, else None."""
    if not (text.isascii() and text.isdigit()):
        return None
    level = int(text)
    return level if 1 <= level <= 200 else None


def read_level(frame: np.ndarray, native: np.ndarray | None = None) -> int | None:
    """Character level from a normalized frame, or None if unreadable.

    `native`: the same shot before normalizing, read when no exact template fits.
    """
    y0 = max(0, frame.shape[0] - glyphs.STATUS_BAND)
    hit = glyphs.find_anchor(frame[y0:], "lv_label")
    if hit is None:
        return None
    x, y = hit[0] + LV_DX, y0 + hit[1] + LV_DY
    m = glyphs.mask(frame[y : y + LV_H, x : x + LV_W], LV_INK_LO, LV_INK_HI)
    text = glyphs.read_text(m, "level_font", space_px=LV_W)
    if text is None and native is not None:
        text = glyphs.read_scaled(frame, native, (x, y, LV_W, LV_H), "level_font", LV_W)
    return None if text is None else parse_level(text)
