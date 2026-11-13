import contextlib
import time
import types

import numpy as np
import pytest

from maplelens import reader
from maplelens.readers import Reading

JOB = (42, (0, 0, 800, 600), 5.0, frozenset())
READING = Reading(5.0, None, None, None, None)


def _wait(r, timeout=20.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        got = r.take()
        if got is not None:
            return got
        time.sleep(0.02)
    raise AssertionError("no answer")


def test_inline_reader_answers_at_once():
    r = reader.InlineReader(work=repr)
    r.ask(JOB)
    assert r.take() == repr(JOB)
    assert r.take() is None


def test_inline_reader_returns_the_error():
    r = reader.InlineReader(work=int)
    r.ask(JOB)
    assert isinstance(r.take(), TypeError)


def test_process_reader_round_trip():
    r = reader.ProcessReader(work=repr)
    try:
        r.ask(JOB)
        r.ask((1, 2, 3, 4))  # busy: ignored
        assert _wait(r) == repr(JOB)
        time.sleep(0.5)
        assert r.take() is None
    finally:
        r.close()


def test_process_reader_returns_the_childs_error():
    r = reader.ProcessReader(work=int)
    try:
        r.ask(JOB)
        assert isinstance(_wait(r), TypeError)
    finally:
        r.close()


def test_process_reader_restarts_a_dead_child():
    r = reader.ProcessReader(work=repr)
    try:
        r.ask(JOB)
        assert _wait(r) == repr(JOB)
        r._proc.kill()
        r._proc.join()
        r.ask(JOB)
        assert _wait(r) == repr(JOB)
    finally:
        r.close()


def test_process_reader_gives_up_on_a_stuck_child():
    r = reader.ProcessReader(work=time.sleep, stuck_s=0.5)
    try:
        r.ask(60)
        time.sleep(1)
        old = r._proc
        r.ask(60)
        assert r._proc.pid != old.pid
        assert not old.is_alive()
    finally:
        r.close()


def test_process_reader_answers_every_tick():
    r = reader.ProcessReader(work=repr)
    try:
        got = []
        end = time.monotonic() + 20
        i = 0
        while time.monotonic() < end and len(got) < 4:
            r.ask(i)
            a = r.take()
            if a is not None:
                got.append(a)
            elif got:
                raise AssertionError("a tick was skipped")
            i += 1
            time.sleep(0.3)
        assert len(got) == 4
        n = int(got[1])  # jobs asked while the child started were ignored; after that, no gaps
        assert got[1:] == [repr(n + k) for k in range(3)]
    finally:
        r.close()


def test_read_game_trims_the_black_bars(monkeypatch):
    frame = np.zeros((600, 800, 3), np.uint8)
    frame[75:525] = 60  # a 16:9 picture
    seen = []
    monkeypatch.setattr(reader.capture, "grab", lambda hwnd, r: frame)
    monkeypatch.setattr(
        reader, "read_all", lambda f, now, due=None: seen.append(f.shape) or READING
    )
    assert reader.read_game(JOB) == ((0, 75, 800, 450), READING)
    assert seen == [(450, 800, 3)]


class _Conn:
    """A pipe end that is always readable and hands out `value`, or raises it."""

    def __init__(self, value):
        self.value = value
        self.sent = []

    def poll(self):
        return True

    def recv(self):
        if isinstance(self.value, _Boom):
            raise ValueError("won't unpickle")
        return self.value

    def send(self, x):
        self.sent.append(x)


class _Boom:
    pass


def test_collect_keeps_an_untaken_answer():
    r = reader.ProcessReader(work=repr)
    r._conn = _Conn("new")
    r._sent_at = 1.0
    r._held = "old"
    r._collect()
    assert r._held == "old"


def test_an_answer_that_wont_unpickle_leaves_the_reader_idle():
    r = reader.ProcessReader(work=repr)
    r._conn = _Conn(_Boom())
    r._sent_at = 1.0
    with contextlib.suppress(ValueError):
        r._collect()
    assert r._sent_at is None
    r._held = None
    r._proc = types.SimpleNamespace(is_alive=lambda: True)
    r.ask(JOB)
    assert r._conn.sent == [JOB]


def test_serve_reports_the_answer_that_wont_pickle():
    class Conn:
        def __init__(self):
            self.sent = []
            self.jobs = iter([1])

        def recv(self):
            try:
                return next(self.jobs)
            except StopIteration:
                raise EOFError from None

        def send(self, x):
            if not isinstance(x, RuntimeError):
                raise TypeError("cannot pickle")
            self.sent.append(x)

    c = Conn()
    reader.serve(c, lambda job: "the answer")
    assert "the answer" in str(c.sent[0]) and "cannot pickle" not in str(c.sent[0])


class _OneJob:
    def __init__(self, fail=None):
        self.sent, self.fail, self.jobs = [], fail, iter([(1,)])

    def recv(self):
        try:
            return next(self.jobs)
        except StopIteration:
            raise EOFError from None

    def send(self, x):
        if self.fail:
            raise self.fail
        self.sent.append(x)


def test_serve_adds_the_helpers_traceback_to_the_error():
    c = _OneJob()
    reader.serve(c, int)
    notes = "".join(c.sent[0].__notes__)
    assert "in the helper" in notes and "work(job)" in notes


def test_serve_returns_quietly_when_the_parent_is_gone():
    reader.serve(_OneJob(fail=BrokenPipeError()), repr)


def test_process_reader_retries_after_the_child_fails_to_start(monkeypatch):
    import multiprocessing

    cls = multiprocessing.get_context("spawn").Process
    real, calls = cls.start, []

    def start(self):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("bootstrapping")
        real(self)

    monkeypatch.setattr(cls, "start", start)
    r = reader.ProcessReader(work=repr)
    try:
        with pytest.raises(RuntimeError, match="bootstrapping"):
            r.ask(JOB)
        r.ask(JOB)
        assert _wait(r) == repr(JOB)
    finally:
        r.close()
