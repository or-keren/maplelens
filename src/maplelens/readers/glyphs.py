"""Template matching on screenshots: find an anchor, read bitmap-font text."""

from pathlib import Path

import cv2
import numpy as np

TEMPLATES = Path(__file__).parent / "templates"
BASE_H = 768
# A cached anchor spot is trusted only on a pixel-exact match.
EXACT = 0.9999
# Bottom rows of a normalized frame that hold the status bar (EXP, level, job):
# anchors there are searched in this band only.
STATUS_BAND = 60
# Glyph file stems that are not the character itself. A stem may carry a variant
# suffix after '_' (e.g. 3_1366.png): one char can have several templates.
CHAR_NAMES = {
    "comma": ",",
    "dot": ".",
    "pct": "%",
    "lbr": "[",
    "rbr": "]",
}

Font = list[tuple[str, np.ndarray]]  # (char, ink mask) per template file

_images: dict[str, np.ndarray] = {}
_fonts: dict[str, Font] = {}
_anchors: dict[str, list[str]] = {}
_last_hit: dict[str, tuple[int, tuple[int, int]]] = {}  # name -> (variant, spot)


def clear_cache() -> None:
    _images.clear()
    _fonts.clear()
    _anchors.clear()
    _last_hit.clear()


def _imread(path: Path, flags: int) -> np.ndarray | None:
    """Image at `path`, or None if missing or unreadable.

    fromfile + imdecode: imread fails on non-ASCII paths on Windows.
    """
    if not path.is_file():
        return None
    return cv2.imdecode(np.fromfile(path, np.uint8), flags)


def load(name: str) -> np.ndarray:
    """templates/<name>.png as BGR, cached."""
    if name not in _images:
        img = _imread(TEMPLATES / f"{name}.png", cv2.IMREAD_COLOR)
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


def find_anchor(frame: np.ndarray, name: str, threshold: float = 0.9) -> tuple[int, int] | None:
    """Top-left of the best match of anchor `name` (any variant) scoring >= threshold, else None."""
    tpls = [load(n) for n in _anchor_names(name)]
    # Fast path: a pixel-exact match at the last spot cannot be beaten (ties aside).
    if name in _last_hit:
        i, (x, y) = _last_hit[name]
        th, tw = tpls[i].shape[:2]
        crop = frame[y : y + th, x : x + tw]
        same = crop.shape == tpls[i].shape
        if same and cv2.matchTemplate(crop, tpls[i], cv2.TM_CCOEFF_NORMED)[0, 0] >= EXACT:
            return x, y
    best, hit = threshold, None
    for i, tpl in enumerate(tpls):
        if frame.shape[0] < tpl.shape[0] or frame.shape[1] < tpl.shape[1]:
            continue
        _, score, _, loc = cv2.minMaxLoc(cv2.matchTemplate(frame, tpl, cv2.TM_CCOEFF_NORMED))
        if score >= best:
            best, hit = score, (i, loc)
    if hit is None:
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
            img = _imread(p, cv2.IMREAD_GRAYSCALE)
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
