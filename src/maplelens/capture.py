"""Find the game window and grab its pixels. Window geometry and screen capture only."""

import sys

import numpy as np

# Black bars: a row is one when under BAR_LIT of its pixels are brighter than DARK.
# Measured on a Mac fullscreen grab: bars are 0, the picture's darkest rows 94% lit.
DARK, BAR_LIT = 8, 0.05
# The top bar may be this much taller than the bottom one (128 vs 132 rows measured).
TOP_SLACK = 4
STATUS_ROWS = 20  # bottom rows of the picture that decide its columns
ROW_STEP = 8
ASPECT_SLACK = 0.02  # the picture left between bars is the game's 16:9 (3024x1700: 0.1%)


def picture_box(frame: np.ndarray) -> tuple[int, int, int, int]:
    """(x, y, w, h) of the game's picture in `frame`, without the black bars a fullscreen
    game adds on a screen of another shape (16:9 on a Mac's 16:10 screen).

    The status bar is never black, so rows are cut only when a bar lies under it, and the
    top bar only up to TOP_SLACK rows taller: a black sky at the top of a map stays.
    Columns are cut where the status bar's rows are black, if that leaves the game's 16:9;
    else only the rows are: on a small map the status bar is narrower than the picture,
    and the minimap and windows stay out at its edges. Neither 16:9 is no bars at all: a
    loading screen with only its title or status bar lit.
    """
    h, w = frame.shape[:2]
    # Rows from every ROW_STEP-th column: a bar is black all across, a sample tells
    rows = np.flatnonzero((frame[:, ::ROW_STEP].max(axis=2) > DARK).mean(axis=1) >= BAR_LIT)
    if rows.size == 0:
        return 0, 0, w, h
    y1 = rows[-1] + 1
    y0 = min(rows[0], h - y1 + TOP_SLACK) if y1 < h else 0
    cols = np.flatnonzero((frame[max(y0, y1 - STATUS_ROWS) : y1].max(axis=2) > DARK).any(axis=0))
    x0, x1 = (cols[0], cols[-1] + 1) if cols.size else (0, w)
    for box in ((x0, y0, x1 - x0, y1 - y0), (0, y0, w, y1 - y0)):
        if abs(box[2] * 9 / (box[3] * 16) - 1) <= ASPECT_SLACK:
            return tuple(int(v) for v in box)
    return 0, 0, w, h


def pick_window(titles: list[tuple[int, str]], title: str, exact: bool = False) -> int | None:
    """Exact title match wins; otherwise (unless `exact`) the first substring match."""
    hit = next((h for h, t in titles if t == title), None)
    if hit is not None or exact:
        return hit
    return next((h for h, t in titles if title in t), None)


if sys.platform == "win32":
    from maplelens.capture_win import (
        client_rect,
        ensure_access,
        find_window,
        grab,
        has_access,
        list_windows,
        request_access,
        set_dpi_aware,
        window_title,
        window_titles,
    )
elif sys.platform == "darwin":
    from maplelens.capture_mac import (  # noqa: F401
        client_rect,
        ensure_access,
        find_window,
        grab,
        has_access,
        list_windows,
        request_access,
        set_dpi_aware,
        window_title,
        window_titles,
    )
