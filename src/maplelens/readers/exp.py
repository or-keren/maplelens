"""EXP bar reader."""

import re

import numpy as np

from maplelens.readers import ExpValue, glyphs

# Value text box, relative to the exp_label anchor's top-left (normalized frame).
# It stops 1 px before the grey separator in front of the Cash Shop button, at every
# resolution. That holds about 16 chars; a 10-digit level-200 value (21 chars) would not
# fit, and how the game lays one out is unverified.
EXP_DX, EXP_DY, EXP_W, EXP_H = 25, 2, 100, 10
# Ink: the grey-white digits only; the status bar behind them stays below about 110.
# The green brackets around the % are left out (R and B stay low): they are dim, so
# their mask changed shape with the text's sub-pixel spot and no template set kept up.
EXP_INK_LO, EXP_INK_HI = (100, 120, 100), (255, 255, 255)
# Where the "[" was, the gap is 6 px or more; between glyphs it is at most 3.
EXP_SPACE_PX = 5

# Strict (R17): glyphs match their templates exactly, and the number needs proper
# thousands groups, so 1 px of noise reads None rather than a wrong value.
_EXP = re.compile(r"(\d{1,3}(?:,\d{3})*) (\d{1,3}\.\d\d)%", re.ASCII)


def parse_exp(text: str) -> ExpValue | None:
    """'23,605 81.45%' -> ExpValue(23605, 81.45); None if malformed or pct not in [0, 100)."""
    m = _EXP.fullmatch(text)
    if not m:
        return None
    pct = float(m[2])
    if not 0 <= pct < 100:
        return None
    return ExpValue(int(m[1].replace(",", "")), pct)


def read_exp(frame: np.ndarray, native: np.ndarray | None = None) -> ExpValue | None:
    """EXP value from a normalized frame, or None if the label or any glyph is unreadable.

    `native` is the same shot before normalizing: when no exact template fits, the
    glyphs are read from its pixels (glyphs.read_scaled).
    """
    y0 = max(0, frame.shape[0] - glyphs.STATUS_BAND)
    hit = glyphs.find_anchor(frame[y0:], "exp_label")
    if hit is None:
        return None
    x, y = hit[0] + EXP_DX, y0 + hit[1] + EXP_DY
    m = glyphs.mask(frame[y : y + EXP_H, x : x + EXP_W], EXP_INK_LO, EXP_INK_HI)
    text = glyphs.read_text(m, "exp_font", space_px=EXP_SPACE_PX)
    if text is None and native is not None:
        box = (x, y, EXP_W, EXP_H)
        text = glyphs.read_scaled(frame, native, box, "exp_font", EXP_SPACE_PX)
    return None if text is None else parse_exp(text)
