"""Template matching on screenshots: find an anchor, read bitmap-font text."""

import math
from functools import cache
from pathlib import Path

import cv2
import numpy as np

TEMPLATES = Path(__file__).parent / "templates"
BASE_H = 768
NEAR = 2  # find_anchor looks this many normalized px around its last spot first
# Bottom rows of a normalized frame that hold the status bar (EXP, level, job):
# anchors there are searched in this band only.
STATUS_BAND = 60
# Glyph file stems that are not the character itself. A stem may carry a variant
# suffix after '_' (e.g. 3_1366.png): one char can have several templates.
CHAR_NAMES = {
    "comma": ",",
    "dot": ".",
    "pct": "%",
    "plus": "+",
    "lpar": "(",
    "rpar": ")",
    "slash": "/",
}

# read_scaled: ink is the min of B, G, R at or above SCALED_INK (light digits; the status
# bar and the green brackets stay lower). On Mac fullscreen grabs (1512x850) the right
# char scored 0.76 or more and beat the next by 0.148 or more; the bars are set lower.
SCALED_INK = 150
SCALED_MIN = 0.6
SCALED_MARGIN = 0.04

Font = list[tuple[str, np.ndarray]]  # (char, ink mask) per template file

_images: dict[str, np.ndarray] = {}
_fonts: dict[str, Font] = {}
_anchors: dict[str, list[str]] = {}
_last_hit: dict[str, tuple[int, tuple[int, int]]] = {}  # name -> (variant, spot)
_scaled_reads: dict[tuple, str | None] = {}  # read_scaled's inputs -> its result


def clear_cache() -> None:
    _images.clear()
    _fonts.clear()
    _anchors.clear()
    _last_hit.clear()
    _scaled_reads.clear()
    _scaled_font.cache_clear()


def imread(path: Path, flags: int) -> np.ndarray | None:
    """Image at `path`, or None if missing or unreadable.

    fromfile + imdecode: imread fails on non-ASCII paths on Windows.
    """
    if not path.is_file():
        return None
    return cv2.imdecode(np.fromfile(path, np.uint8), flags)


def load(name: str) -> np.ndarray:
    """templates/<name>.png as BGR, cached."""
    if name not in _images:
        img = imread(TEMPLATES / f"{name}.png", cv2.IMREAD_COLOR)
        if img is None:
            raise FileNotFoundError(TEMPLATES / f"{name}.png")
        _images[name] = img
    return _images[name]


def load_all() -> int:
    """Read every template under TEMPLATES (anchors and font glyphs); the number read.

    Raises FileNotFoundError if there are none, or if one can't be read.
    """
    anchors = sorted(TEMPLATES.glob("*.png"))
    for p in anchors:
        load(p.stem)
    fonts = [d.name for d in sorted(TEMPLATES.iterdir()) if d.is_dir()]
    n = len(anchors) + sum(len(_font(f)) for f in fonts)
    if not n:
        raise FileNotFoundError(f"no templates in {TEMPLATES}")
    return n


def normalize(frame: np.ndarray) -> np.ndarray:
    """Resize to height BASE_H, keeping aspect. A frame already that high is returned as is."""
    h, w = frame.shape[:2]
    if h == BASE_H:
        return frame
    return cv2.resize(frame, (round(w * BASE_H / h), BASE_H), interpolation=cv2.INTER_AREA)


def _anchor_names(name: str) -> list[str]:
    """Template stems for anchor `name`: <name>.png and variants <name>_<digits>.png."""
    if name not in _anchors:
        paths = [TEMPLATES / f"{name}.png", *sorted(TEMPLATES.glob(f"{name}_[0-9]*.png"))]
        _anchors[name] = [p.stem for p in paths if p.exists()]
        if not _anchors[name]:
            raise FileNotFoundError(TEMPLATES / f"{name}.png")
    return _anchors[name]


def _best(img: np.ndarray, tpls: list[np.ndarray], threshold: float):
    """(variant, top-left) of the best match in `img` scoring >= threshold, else None."""
    best, hit = threshold, None
    for i, tpl in enumerate(tpls):
        if img.shape[0] < tpl.shape[0] or img.shape[1] < tpl.shape[1]:
            continue
        _, score, _, loc = cv2.minMaxLoc(cv2.matchTemplate(img, tpl, cv2.TM_CCOEFF_NORMED))
        if score >= best:
            best, hit = score, (i, loc)
    return hit


def _near(frame: np.ndarray, tpls: list[np.ndarray], last, threshold: float):
    """Best match within NEAR px of `last` = (variant, spot), or None.

    A peak on an edge of that box may continue outside it, so it doesn't count (edges at
    the frame's own edge excepted: nothing continues past those).
    """
    i, (x, y) = last
    th, tw = tpls[i].shape[:2]
    fh, fw = frame.shape[:2]
    x0, y0 = max(x - NEAR, 0), max(y - NEAR, 0)
    x1, y1 = min(x + tw + NEAR, fw), min(y + th + NEAR, fh)
    hit = _best(frame[y0:y1, x0:x1], tpls, threshold)
    if hit is None:
        return None
    j, (lx, ly) = hit
    h, w = tpls[j].shape[:2]
    on_edge = (
        (lx == 0 and x0 > 0)
        or (ly == 0 and y0 > 0)
        or (lx + w == x1 - x0 and x1 < fw)
        or (ly + h == y1 - y0 and y1 < fh)
    )
    return None if on_edge else (j, (x0 + lx, y0 + ly))


def find_anchor(frame: np.ndarray, name: str, threshold: float = 0.9) -> tuple[int, int] | None:
    """Top-left of the best match of anchor `name` (any variant) scoring >= threshold, else None."""
    tpls = [load(n) for n in _anchor_names(name)]
    hit = name in _last_hit and _near(frame, tpls, _last_hit[name], threshold)
    hit = hit or _best(frame, tpls, threshold)
    if not hit:
        _last_hit.pop(name, None)
        return None
    _last_hit[name] = hit
    return hit[1]


def mask(img: np.ndarray, lo: tuple[int, int, int], hi: tuple[int, int, int]) -> np.ndarray:
    """Bool mask of pixels with BGR inside [lo, hi]."""
    return cv2.inRange(img, np.array(lo, np.uint8), np.array(hi, np.uint8)) > 0


def _font(font: str) -> Font:
    if font not in _fonts:
        paths = sorted((TEMPLATES / font).glob("*.png"))
        if not paths:
            raise FileNotFoundError(f"no glyph PNGs in {TEMPLATES / font}")
        glyphs = []
        for p in paths:
            img = imread(p, cv2.IMREAD_GRAYSCALE)
            if img is None:
                raise FileNotFoundError(f"cannot read glyph {p}")
            name = p.stem.split("_")[0]
            glyphs.append((CHAR_NAMES.get(name, name), img > 127))
        _fonts[font] = glyphs
    return _fonts[font]


def _match(glyph: np.ndarray, templates: Font) -> str | None:
    """Char of the template with exactly this ink shape, else None.

    Strict (R17): a glyph 1 px off reads None, never a neighbouring char.
    """
    for ch, t in templates:
        if glyph.shape == t.shape and np.array_equal(glyph, t):
            return ch
    return None


def _rows(m: np.ndarray) -> np.ndarray:
    rows = np.flatnonzero(m.any(axis=1))
    return m[rows[0] : rows[-1] + 1]


def _split(run: np.ndarray, templates: Font) -> str | None:
    """Cut a run of touching glyphs into template matches."""
    widest = max(t.shape[1] for _, t in templates)
    w = run.shape[1]
    best = {0: ""}  # columns read so far -> text
    for i in range(w):
        if i not in best:
            continue
        for j in range(i + 1, min(w, i + widest) + 1):
            ch = _match(_rows(run[:, i:j]), templates)
            if ch and j not in best:
                best[j] = best[i] + ch
    return best.get(w)


@cache
def _scaled_font(font: str, s: float) -> list[tuple[str, np.ndarray]]:
    """`font`'s masks as grey images (1 px of background around), scaled by `s`."""
    return [
        (ch, cv2.resize(np.pad(t * np.float32(255), 1), None, fx=s, fy=s)) for ch, t in _font(font)
    ]


def read_scaled(
    frame: np.ndarray, native: np.ndarray, box: tuple[int, int, int, int], font: str, space_px: int
) -> str | None:
    """Light text in `box` (x, y, w, h of the normalized `frame`), read from `native` (the
    same shot at any size) with `font`; None if any glyph is unsure.

    For a game resolution no exact template fits (Mac fullscreen draws 1512x850): glyphs
    are cut where the native pixels show ink, and each must match one char by grey
    correlation SCALED_MIN and beat every other char by SCALED_MARGIN.
    """
    s = native.shape[0] / frame.shape[0]
    x, y, w, h = box
    x0, x1 = int(x * s), int((x + w) * s)
    text = native[int(y * s) : int((y + h) * s), x0:x1].min(axis=2)
    # 2 px above and below, so a glyph can slide onto its template
    strip = native[max(0, int((y - 2) * s)) : int((y + h + 2) * s), x0:x1].min(axis=2)
    key = (font, round(s, 3), space_px, strip.shape, strip.tobytes())
    if key in _scaled_reads:
        return _scaled_reads[key]
    out = _read_scaled(strip.astype(np.float32), text, s, font, space_px)
    if len(_scaled_reads) >= 64:
        _scaled_reads.clear()
    _scaled_reads[key] = out
    return out


def _read_scaled(
    strip: np.ndarray, text: np.ndarray, s: float, font: str, space_px: int
) -> str | None:
    cols = np.flatnonzero((text >= SCALED_INK).any(axis=0))
    if cols.size == 0:
        return None
    templates = _scaled_font(font, round(s, 3))
    widest = max(t.shape[1] for _, t in templates)
    pad = math.ceil(2 * s)
    out, prev_end = "", None
    for run in np.split(cols, np.flatnonzero(np.diff(cols) > 1) + 1):
        a, b = run[0], run[-1] + 1
        if b - a > widest:  # touching glyphs: no single char fits
            return None
        if prev_end is not None and a - prev_end >= space_px * s:
            out += " "
        prev_end = b
        patch = strip[:, max(0, a - pad) : b + pad]
        best: dict[str, float] = {}
        for ch, t in templates:
            if patch.shape[0] >= t.shape[0] and patch.shape[1] >= t.shape[1]:
                sc = float(cv2.matchTemplate(patch, t, cv2.TM_CCOEFF_NORMED).max())
                best[ch] = max(best.get(ch, -1.0), sc)
        top = sorted(best.items(), key=lambda kv: kv[1], reverse=True)
        if not top or top[0][1] < SCALED_MIN:
            return None
        if len(top) > 1 and top[0][1] - top[1][1] < SCALED_MARGIN:
            return None
        out += top[0][0]
    return out


def read_text(m: np.ndarray, font: str, space_px: int) -> str | None:
    """Read a bool ink mask with the bitmap font `font`; None if any glyph is unknown."""
    templates = _font(font)
    cols = np.flatnonzero(m.any(axis=0))
    if cols.size == 0:
        return None
    # Runs of ink columns: split where consecutive ink columns are not adjacent.
    runs = np.split(cols, np.flatnonzero(np.diff(cols) > 1) + 1)
    out = ""
    prev_end = None
    for run in runs:
        x0, x1 = run[0], run[-1] + 1
        if prev_end is not None and x0 - prev_end >= space_px:
            out += " "
        prev_end = x1
        sub = m[:, x0:x1]
        # Glyphs can touch after the resize to BASE_H; then cut the run by templates.
        text = _match(_rows(sub), templates) or _split(sub, templates)
        if text is None:
            return None
        out += text
    return out
