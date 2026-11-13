"""macOS: find the game window and grab its pixels. Window geometry and screen capture only."""

import functools
import time

import cv2
import numpy as np
import Quartz
from AppKit import NSMakeRect, NSScreen, NSWindow, NSWindowStyleMaskTitled


def set_dpi_aware() -> None:
    pass  # nothing to do on macOS


def window_entries(infos: list[dict]) -> list[tuple[int, str]]:
    """One (id, text) per window title and per owner name, front to back."""
    return [
        (info["kCGWindowNumber"], info[key])
        for info in infos
        for key in ("kCGWindowName", "kCGWindowOwnerName")
        if info.get(key)
    ]


def _infos() -> list[dict]:
    opts = Quartz.kCGWindowListOptionOnScreenOnly
    return list(Quartz.CGWindowListCopyWindowInfo(opts, Quartz.kCGNullWindowID) or [])


def _windows() -> list[tuple[int, str]]:
    return window_entries(_infos())


def list_windows() -> list[str]:
    out = []
    for i in _infos():
        owner, name = i.get("kCGWindowOwnerName"), i.get("kCGWindowName")
        if owner or name:
            out.append(f"{owner} — {name}" if owner and name else owner or name)
    return out


def window_titles() -> list[str]:
    """Titles find_window can match, each once, in window order."""
    return list(dict.fromkeys(t for _, t in _windows()))


def find_window(title: str, exact: bool = False) -> int | None:
    from maplelens.capture import pick_window  # late: capture imports this module

    return pick_window(_windows(), title, exact)


def window_title(wid: int) -> str:
    return next((t for h, t in _windows() if h == wid), "")


def client_rect_from(
    bounds: dict, onscreen: bool, title_pt: float, scale: float
) -> tuple[int, int, int, int] | None:
    """Window bounds in points -> client area (left, top, width, height) in pixels."""
    h = bounds["Height"] - title_pt
    if not onscreen or h <= 0 or bounds["Width"] <= 0:
        return None
    return (
        round(bounds["X"] * scale),
        round((bounds["Y"] + title_pt) * scale),
        round(bounds["Width"] * scale),
        round(h * scale),
    )


@functools.cache
def _title_bar_pt() -> float:
    frame = NSWindow.frameRectForContentRect_styleMask_(
        NSMakeRect(0, 0, 100, 100), NSWindowStyleMaskTitled
    )
    return frame.size.height - 100


def _screen_at(x: float, y: float):
    """NSScreen holding the CG point (x, y): CG has a top-left origin, NSScreen bottom-left."""
    screens = NSScreen.screens()
    ny = screens[0].frame().size.height - y
    for s in screens:
        f = s.frame()
        if (
            f.origin.x <= x < f.origin.x + f.size.width
            and f.origin.y < ny <= f.origin.y + f.size.height
        ):
            return s
    return NSScreen.mainScreen()


def client_rect(wid: int) -> tuple[int, int, int, int] | None:
    infos = Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionIncludingWindow, wid)
    info = next((i for i in infos or [] if i["kCGWindowNumber"] == wid), None)
    if info is None:
        return None
    b = info["kCGWindowBounds"]
    screen = _screen_at(b["X"] + 1, b["Y"] + 1)
    f = screen.frame()
    borderless = b["Width"] == f.size.width and b["Height"] == f.size.height
    return client_rect_from(
        b,
        bool(info.get("kCGWindowIsOnscreen")),
        0 if borderless else _title_bar_pt(),
        screen.backingScaleFactor(),
    )


DOUBLING_STEP = 8


def game_top(rgb: np.ndarray, top: int) -> int:
    """`top`, or `top + 1` when the game sits one backing pixel lower.

    On Retina the game draws at point size and shows pixel-doubled, so its rows come in
    equal pairs. The game's own surface can sit half a point below the title bar (seen
    after the window moved), which puts the pairs at odd rows from `top`.
    """
    # Every DOUBLING_STEP-th column decides as well as all of them, at a fraction of the cost
    a, b = rgb[top:-1, ::DOUBLING_STEP, :3], rgb[top + 1 :, ::DOUBLING_STEP, :3]
    eq = (a == b).all(axis=(1, 2))
    even, odd = int(eq[0::2].sum()), int(eq[1::2].sum())
    # Flat rows are equal in both phases; only doubled content gives one phase a clear lead.
    return top + 1 if odd > len(eq) // 4 and odd > 2 * even else top


def crop_bgr(rgb: np.ndarray, rect: tuple[int, int, int, int]) -> np.ndarray:
    """RGB (or RGBX) frame -> BGR client area: rect[3] rows from the game's top, left
    rect[2] columns."""
    h, w = rgb.shape[:2]
    if rect[3] > h or rect[2] > w:
        raise RuntimeError("window shrank since its size was read")
    top = game_top(rgb, h - rect[3])
    code = cv2.COLOR_RGBA2BGR if rgb.shape[2] == 4 else cv2.COLOR_RGB2BGR
    out = cv2.cvtColor(rgb[top : top + rect[3], : rect[2]], code)  # a numpy flip: 15x slower
    if len(out) < rect[3]:  # the window cuts the game's last backing row: its pair repeats it
        out = np.vstack([out, out[-1:]])
    return np.ascontiguousarray(out)


def grab(wid: int, rect: tuple[int, int, int, int]) -> np.ndarray:
    img = Quartz.CGWindowListCreateImage(
        Quartz.CGRectNull,
        Quartz.kCGWindowListOptionIncludingWindow,
        wid,
        Quartz.kCGWindowImageBoundsIgnoreFraming,
    )
    if img is None:
        raise RuntimeError("window capture failed")
    w, h = Quartz.CGImageGetWidth(img), Quartz.CGImageGetHeight(img)
    srgb = Quartz.CGColorSpaceCreateWithName(Quartz.kCGColorSpaceSRGB)  # readers expect sRGB
    ctx = Quartz.CGBitmapContextCreate(None, w, h, 8, w * 4, srgb, Quartz.kCGImageAlphaNoneSkipLast)
    Quartz.CGContextDrawImage(ctx, Quartz.CGRectMake(0, 0, w, h), img)
    buf = Quartz.CGBitmapContextGetData(ctx).as_buffer(w * h * 4)
    rgb = np.frombuffer(buf, np.uint8).reshape(h, w, 4)  # RGBX: crop_bgr drops the X
    return crop_bgr(rgb, rect)


# Asking for Screen Recording access goes through the same macOS service as every capture
# (window captures run through ScreenCaptureKit's helper now): asked on each tick, it jammed
# that service within 30 s while the game was in front, and every capture on the Mac, ours
# and others', waited 30 s and failed. Asked every 10 s, captures kept working.
ACCESS_CHECK_S = 10
_access: dict[str, float | bool] = {}  # "at": when it was last asked, "ok": the answer


def has_access(now: float | None = None) -> bool:
    """Whether MapleLens may record the screen, asked at most once per ACCESS_CHECK_S."""
    now = time.monotonic() if now is None else now
    if not _access or now - _access["at"] >= ACCESS_CHECK_S:
        _access.update(at=now, ok=bool(Quartz.CGPreflightScreenCaptureAccess()))
    return bool(_access["ok"])


def request_access() -> None:
    Quartz.CGRequestScreenCaptureAccess()


def ensure_access() -> bool:
    if has_access():
        return True
    request_access()
    print(
        "MapleLens needs Screen Recording permission to read the game window. It captures\n"
        "only that window's pixels, nothing else.\n"
        "macOS grants it to the app that started MapleLens (for example Terminal): allow it\n"
        "in System Settings > Privacy & Security > Screen & System Audio Recording,\n"
        "then run MapleLens again."
    )
    return False
