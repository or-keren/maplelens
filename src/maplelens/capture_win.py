"""Windows: find the game window and grab its pixels. Window geometry and screen capture only."""

import asyncio
import contextlib
import ctypes
import time
from ctypes import wintypes

import numpy as np

user32 = ctypes.windll.user32
_ENUM_PROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsIconic.argtypes = [wintypes.HWND]
user32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
dwmapi = ctypes.windll.dwmapi
dwmapi.DwmGetWindowAttribute.argtypes = [
    wintypes.HWND,
    wintypes.DWORD,
    ctypes.c_void_p,
    wintypes.DWORD,
]
_DWMWA_EXTENDED_FRAME_BOUNDS = 9  # the window as drawn: what a window capture holds

_PER_MONITOR_AWARE_V2 = -4


def set_dpi_aware() -> None:
    with contextlib.suppress(OSError):  # Qt may have set it already
        user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(_PER_MONITOR_AWARE_V2))


def _windows() -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []

    def visit(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            buf = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, buf, 256)
            if buf.value:
                found.append((hwnd, buf.value))
        return True

    user32.EnumWindows(_ENUM_PROC(visit), 0)
    return found


def list_windows() -> list[str]:
    return [title for _, title in _windows()]


def window_titles() -> list[str]:
    """Titles find_window can match, each once, in window order."""
    return list(dict.fromkeys(t for _, t in _windows()))


def find_window(title: str, exact: bool = False) -> int | None:
    from maplelens.capture import pick_window  # late: capture imports this module

    return pick_window(_windows(), title, exact)


def window_title(hwnd: int) -> str:
    return next((t for h, t in _windows() if h == hwnd), "")


def client_rect(hwnd: int) -> tuple[int, int, int, int] | None:
    if user32.IsIconic(hwnd):
        return None
    r = wintypes.RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(r)):
        return None
    origin = wintypes.POINT(0, 0)
    if not user32.ClientToScreen(hwnd, ctypes.byref(origin)):
        return None
    if r.right <= 0 or r.bottom <= 0:
        return None
    return origin.x, origin.y, r.right, r.bottom


class _Session:
    """A running capture of one window: its own pixels, never what's drawn over it.

    So MapleLens's windows over the game stay out of the readers, yet show to everyone
    else (stream and screenshot apps).
    """

    def __init__(self, hwnd: int):
        from winrt.windows.graphics.capture import Direct3D11CaptureFramePool
        from winrt.windows.graphics.capture.interop import create_for_window
        from winrt.windows.graphics.directx import DirectXPixelFormat
        from winrt.windows.graphics.directx.direct3d11.interop import create_direct3d11_device

        self.hwnd = hwnd
        self._fmt = DirectXPixelFormat.B8_G8_R8_A8_UINT_NORMALIZED
        self._device = create_direct3d11_device()
        item = create_for_window(hwnd)
        self._size = item.size
        self._pool = Direct3D11CaptureFramePool.create_free_threaded(
            self._device, self._fmt, 1, self._size
        )
        self._session = self._pool.create_capture_session(item)
        self._session.is_cursor_capture_enabled = False
        with contextlib.suppress(OSError):  # Windows 10 before 2104 always draws it
            self._session.is_border_required = False  # no yellow frame round the game
        self._session.start_capture()
        self.last: np.ndarray | None = None  # BGRA, the whole window

    def frame(self) -> np.ndarray:
        """The newest frame, or the last one if the game drew nothing new since."""
        frame = self._pool.try_get_next_frame()
        for _ in range(50):  # the first frame takes a few ms to arrive
            if frame is not None or self.last is not None:
                break
            time.sleep(0.01)
            frame = self._pool.try_get_next_frame()
        if frame is None:
            if self.last is None:
                raise RuntimeError("window capture gave no frame")
            return self.last
        try:
            self.last = _pixels(frame.surface)
            size = frame.content_size
            if (size.width, size.height) != (self._size.width, self._size.height):
                self._size = size  # resized: later frames come at the new size
                self._pool.recreate(self._device, self._fmt, 1, size)
        finally:
            frame.close()
        return self.last

    def close(self) -> None:
        self._session.close()
        self._pool.close()


def _pixels(surface) -> np.ndarray:
    from winrt.windows.graphics.imaging import SoftwareBitmap
    from winrt.windows.storage.streams import Buffer

    async def copy():
        return await SoftwareBitmap.create_copy_from_surface_async(surface)

    bmp = asyncio.run(copy())  # not get(): it refuses to block the Qt main thread
    buf = Buffer(bmp.pixel_width * bmp.pixel_height * 4)
    bmp.copy_to_buffer(buf)
    return np.frombuffer(buf, np.uint8).reshape(bmp.pixel_height, bmp.pixel_width, 4)


def _frame_origin(hwnd: int) -> tuple[int, int]:
    r = wintypes.RECT()
    if dwmapi.DwmGetWindowAttribute(
        hwnd, _DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(r), ctypes.sizeof(r)
    ):
        raise RuntimeError("window frame bounds unavailable")
    return r.left, r.top


_live: _Session | None = None


def grab(hwnd: int, rect: tuple[int, int, int, int]) -> np.ndarray:
    """The client area of window `hwnd` (screen rect `rect`) as BGR."""
    global _live  # noqa: PLW0603 - one capture session per process, reused across grabs
    if _live is None or _live.hwnd != hwnd:
        if _live is not None:
            _live.close()
        _live = _Session(hwnd)
    img = _live.frame()
    fx, fy = _frame_origin(hwnd)  # the capture holds the window frame; cut to the client
    x, y = rect[0] - fx, rect[1] - fy
    w, h = rect[2], rect[3]
    if x < 0 or y < 0 or y + h > img.shape[0] or x + w > img.shape[1]:
        raise RuntimeError("window size changed since its frame was captured")
    return np.ascontiguousarray(img[y : y + h, x : x + w, :3])  # BGRA -> BGR


def ensure_access() -> bool:
    return True
