"""Reading the game: grab, trim, read. In this process, or in a child that macOS doesn't slow."""

import multiprocessing
import time
import traceback
from collections.abc import Callable

from maplelens import capture
from maplelens.readers import Reading, read_all

Rect = tuple[int, int, int, int]
Job = tuple[int, Rect, float, frozenset[str]]  # (hwnd, rect, now, due)
Answer = tuple[Rect, Reading]


def read_game(job: Job) -> Answer:
    """Grab the window, leave out fullscreen black bars, read it: the trimmed rect and reading."""
    hwnd, rect, now, due = job
    frame = capture.grab(hwnd, rect)
    x, y, w, h = capture.picture_box(frame)
    return (rect[0] + x, rect[1] + y, w, h), read_all(frame[y : y + h, x : x + w], now, due)


class InlineReader:
    """Does the work in `ask`, here."""

    def __init__(self, work: Callable = read_game):
        self._work = work
        self._answer: Answer | Exception | None = None

    def ask(self, job: Job) -> None:
        try:
            self._answer = self._work(job)
        except Exception as e:
            self._answer = e

    def take(self) -> Answer | Exception | None:
        answer, self._answer = self._answer, None
        return answer

    def close(self) -> None:
        pass


def serve(conn, work: Callable) -> None:
    """The child's loop: answer each job with the result or the error, until the parent closes."""
    while True:
        try:
            job = conn.recv()
        except EOFError:
            return
        try:
            answer = work(job)
        except Exception as e:
            e.add_note("in the helper:\n" + "".join(traceback.format_tb(e.__traceback__)))
            answer = e
        try:
            conn.send(answer)
        except OSError:  # the parent is gone
            return
        except Exception:  # an answer that won't pickle
            conn.send(RuntimeError(repr(answer)))


class ProcessReader:
    """Does the work in a child process, started on the first `ask`; `take` never blocks.

    A job is in flight from its `ask` until its answer is collected. A child that died, or
    has had a job in flight for `stuck_s`, is killed and replaced on the next `ask`.
    """

    def __init__(self, work: Callable = read_game, stuck_s: float = 30.0):
        self._work = work
        self._stuck_s = stuck_s
        self._proc = None
        self._conn = None
        self._held: Answer | Exception | None = None
        self._sent_at: float | None = None  # when the unanswered job went out

    def _collect(self) -> None:
        if self._conn is None or self._sent_at is None or self._held is not None:
            return
        try:
            if self._conn.poll():
                self._sent_at = None  # even if recv raises: the reader stays able to send
                self._held = self._conn.recv()
        except (EOFError, OSError):  # the child is gone
            self._kill()

    def _kill(self) -> None:
        if self._proc is not None:
            if self._proc.is_alive():  # a Process that never started has nothing to kill
                self._proc.kill()
                self._proc.join()
            self._conn.close()
        self._proc = self._conn = self._held = self._sent_at = None

    def ask(self, job: Job) -> None:
        self._collect()
        if self._proc is not None:
            stuck = self._sent_at is not None and time.monotonic() - self._sent_at > self._stuck_s
            if stuck or not self._proc.is_alive():
                self._kill()
        if self._proc is None:
            ctx = multiprocessing.get_context("spawn")
            self._conn, child = ctx.Pipe()
            try:
                proc = ctx.Process(target=serve, args=(child, self._work), daemon=True)
                proc.start()
            except BaseException:  # leave no child, so the next ask tries again
                self._conn.close()
                child.close()
                self._conn = None
                raise
            self._proc = proc
            child.close()  # so the child's recv ends when this side closes
        if self._sent_at is None:
            try:
                self._conn.send(job)
                self._sent_at = time.monotonic()
            except (BrokenPipeError, OSError):
                self._kill()

    def take(self) -> Answer | Exception | None:
        self._collect()
        answer, self._held = self._held, None
        return answer

    def close(self) -> None:
        if self._proc is None:
            return
        self._conn.close()
        self._proc.join(1)
        if self._proc.is_alive():
            self._proc.kill()
            self._proc.join()
        self._proc = self._conn = self._held = self._sent_at = None
