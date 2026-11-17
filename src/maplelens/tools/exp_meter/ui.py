"""The EXP meter tool: a tab with live numbers and a History window."""

import sqlite3
import time
from collections.abc import Callable, Collection

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from maplelens.overlay import (
    ACCENT,
    LABEL_COLOR,
    LABEL_PT,
    TAB_W,
    VALUE_COLOR,
    VALUE_PT,
    FloatingWindow,
    primary_button,
    secondary_button,
    setting_choice,
    text_label,
)
from maplelens.readers import Reading
from maplelens.tools.exp_meter.history import MIN_VISIT_S, best_maps, history, save_segment
from maplelens.tools.exp_meter.meter import ExpMeter
from maplelens.tools.exp_meter.session import AUTO, MANUAL, Session, State, Step
from maplelens.tools.exp_meter.text import (
    PAUSED,
    PRESS_START,
    Column,
    best_lines,
    box_lines,
    format_duration,
    format_last,
    pin_text,
    short_name,
)

_FLUSH_S = 60
_UNREAD_S = 10  # the bar unreadable this long, with the game found: say so
_COLUMNS = ["Map", "Class", "Lvl", "Avg EXP/h", "Avg %/h", "Active time", "Last there"]
START, PAUSE, RESUME, RESET = "Start", "Pause", "Resume", "Reset"
SESSIONS = "Sessions"
# The EXP card's choices, and the line under each
SESSION_MODES = {AUTO: "Track automatically", MANUAL: "Track when I press Start"}
SESSION_HINTS = {
    AUTO: "A session ends after 30 minutes without EXP",
    MANUAL: "Start, Pause and Reset on the EXP tab",
}


class _Item(QTableWidgetItem):
    """A cell that sorts by a value instead of by its text."""

    def __init__(self, text: str, key):
        super().__init__(text)
        self.key = key

    def __lt__(self, other):
        return self.key < other.key


JobLine = Callable[[str], Collection[str]]


class HistoryWindow(FloatingWindow):
    """The "Best for you now" strip above the per-map/class/level table."""

    def __init__(self, conn: sqlite3.Connection, job_line: JobLine = lambda j: {j}):
        super().__init__()
        self._conn, self._job_line = conn, job_line
        self.setWindowTitle("MapleLens — EXP history")
        self._best = QGridLayout()
        self._best.setColumnStretch(3, 1)  # keep the strip's three columns together on the left
        self._best.setHorizontalSpacing(24)
        self._table = table = QTableWidget(0, len(_COLUMNS))
        table.setHorizontalHeaderLabels(_COLUMNS)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.verticalHeader().hide()
        table.setSortingEnabled(True)
        layout = QVBoxLayout(self)
        layout.addLayout(self._best)
        layout.addWidget(table, 1)
        self.resize(880, 460)

    def _show_best(self, job: str | None, level: int | None) -> None:
        while self._best.count():
            self._best.takeAt(0).widget().deleteLater()
        rows = best_maps(self._conn, self._job_line(job), level) if job and level else []
        head, lines = best_lines(job, level, rows)
        title = QLabel(head)
        title.setStyleSheet("font-weight: bold")
        self._best.addWidget(title, 0, 0, 1, 3)
        for i, cells in enumerate(lines, 1):
            for col, text in enumerate(cells):
                self._best.addWidget(QLabel(text), i, col)

    def refresh(self, job: str | None = None, level: int | None = None) -> None:
        now = time.time()
        self._show_best(job, level)
        table = self._table
        table.setSortingEnabled(False)  # otherwise rows reshuffle while being filled
        rows = history(self._conn)
        table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            short = short_name(r.map_name)
            cells = [
                (short, short),
                (r.job, r.job),
                (str(r.level), r.level),
                (f"{r.exp_per_min * 60:,.0f}", r.exp_per_min),
                (f"{r.pct_per_min * 60:.2f}%", r.pct_per_min),
                (format_duration(r.active_s / 60), r.active_s),
                (format_last(r.last, now), r.last),
            ]
            for col, (text, key) in enumerate(cells):
                table.setItem(i, col, _Item(text, key))
            table.item(i, 0).setToolTip(r.map_name)
        table.setSortingEnabled(True)
        table.sortItems(len(_COLUMNS) - 1, Qt.DescendingOrder)
        table.resizeColumnToContents(0)  # map names in full


class PinLine(QWidget):
    """The pinned line under the other tabs: "EXP", the rate and time to level, and a
    yellow angle that goes to the EXP tab."""

    def __init__(self, on_click: Callable[[], None]):
        super().__init__()
        self._on_click = on_click
        self.setCursor(Qt.PointingHandCursor)
        self._text = text_label("", LABEL_PT, VALUE_COLOR)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 4, 0, 0)
        row.setSpacing(6)
        row.addWidget(text_label("EXP", LABEL_PT, LABEL_COLOR))
        row.addWidget(self._text)
        row.addStretch()
        row.addWidget(text_label("\u203a", LABEL_PT + 2, ACCENT, bold=True))  # as a Row's
        self.hide()  # until the box shows it

    def set_text(self, text: str, accent: bool) -> None:
        self._text.setText(text)
        self._text.setStyleSheet(f"color: {ACCENT if accent else VALUE_COLOR};")

    def text(self) -> str:
        return self._text.text()

    # It takes its press, as a button does, so the box doesn't start a drag.
    def mousePressEvent(self, event):
        event.setAccepted(event.button() == Qt.LeftButton)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.rect().contains(event.position().toPoint()):
            self._on_click()


class ExpMeterTool:
    def __init__(  # noqa: PLR0913 - the callbacks are keywords, wired by the app
        self,
        settings: dict,
        conn: sqlite3.Connection,
        job_line: JobLine = lambda j: {j},
        *,
        save: Callable[[], None] = lambda: None,
        show_pin: Callable[[bool], None] = lambda _on: None,
        open_tab: Callable[[], None] = lambda: None,
    ):
        self._conn = conn
        self._settings, self._save_settings, self._show_pin = settings, save, show_pin
        self.pin_line = PinLine(open_tab)  # the box's footer: on every tab but this one
        self._session = Session(settings["exp_session_mode"])
        # measuring while tracking; while paused, the closed meter holds the session (its
        # segments saved), which the next Start carries on; else None
        self._meter: ExpMeter | None = None
        self._held: ExpMeter | None = None
        self._paused_rate = None  # the live rate at Pause, kept on screen until Resume
        self._tracked_s = 0.0  # manual mode's timer: time tracked before the current stretch
        self._since: float | None = None  # when the current stretch of tracking began
        if self._session.state == State.TRACKING:
            self._meter = self._new_meter(())
        self._last_flush: float | None = None
        self._exp_seen: float | None = None  # last tick the bar was read, or the game was gone
        self._waiting, self._unread = True, False  # as of the last tick
        self._history = HistoryWindow(conn, job_line)
        self.title = "EXP"
        self.tab = QWidget()
        self.tab.setFixedWidth(TAB_W)  # same box width as the other tabs
        self._lines = QVBoxLayout(self.tab)
        self._lines.setContentsMargins(0, 4, 0, 0)
        self._lines.setSpacing(0)
        self._pin = secondary_button("", self._toggle_pin)
        self._label_pin()
        # manual mode's Start or Pause, and Reset, over History and Pin; the same buttons in
        # every state, so the tab never changes height but by mode
        self._start = primary_button(START, lambda: self.start(time.time()))
        self._pause = secondary_button(PAUSE, lambda: self.pause(time.time()))
        self._reset = secondary_button(RESET, lambda: self.reset(time.time()))
        self._session_row = _row(self._start, self._pause, self._reset)
        self._button_row = QWidget()
        rows = QVBoxLayout(self._button_row)
        rows.setContentsMargins(0, 0, 0, 0)
        rows.setSpacing(6)
        rows.addWidget(self._session_row)  # hidden in auto: no space, no spacing
        rows.addWidget(_row(secondary_button("History", self._show_history), self._pin))
        self._shape: list[list[int]] | None = None  # values per row of what's shown
        self._texts: list[QLabel] = []
        self._show_buttons()
        self._refresh(time.time())  # waiting for game, never blank, even before a tick

    def _new_meter(self, carry) -> ExpMeter:
        s, split = self._settings, self._session.split
        return ExpMeter(s["idle_cutoff_s"], s["jump_factor"], carry=carry, split=split)

    def set_tab_w(self, width: int) -> None:
        self.tab.setFixedWidth(width)

    @property
    def pinned(self) -> bool:
        return bool(self._settings["pin_exp"])

    def _label_pin(self) -> None:
        self._pin.setText("Unpin" if self.pinned else "Pin")

    def _toggle_pin(self) -> None:
        self._settings["pin_exp"] = not self.pinned
        self._label_pin()
        self._show_pin(self.pinned)  # first: a failed save (a locked file) loses only that
        self._save_settings()

    def _show(self, rows: list[list[Column]]) -> None:
        texts = [t for row in rows for label, values in row for t in (label, *values)]
        shape = [[len(values) for _, values in row] for row in rows]
        if shape == self._shape:  # same rows: new text only, or the box blinks each tick
            for w, t in zip(self._texts, texts, strict=True):
                w.setText(t)
            return
        self._shape = shape
        while self._lines.count():  # rebuild: the label/value rows are few and cheap
            item = self._lines.takeAt(0)
            if (w := item.widget()) and w is not self._button_row:
                w.deleteLater()
        self._texts = []
        for row in rows:
            # several columns share the row in equal parts of the tab's width, never widening it
            box = QWidget()
            side = QHBoxLayout(box)
            side.setContentsMargins(0, 0, 0, 0)
            side.setSpacing(8)
            for label, values in row:
                column = QVBoxLayout()
                column.setSpacing(0)
                ws = [text_label(label, LABEL_PT, LABEL_COLOR)]
                ws += [text_label(v, VALUE_PT, VALUE_COLOR, bold=True) for v in values]
                for w in ws:
                    if len(row) > 1:
                        w.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
                    column.addWidget(w)
                side.addLayout(column, 1)
                self._texts += ws
            self._lines.addWidget(box)
            self._lines.addSpacing(6)
        self._lines.addWidget(self._button_row)

    def _show_history(self) -> None:
        meter = self._meter or self._held
        self._history.refresh(*((meter.job, meter.level) if meter else (None, None)))
        self._history.open()

    def _save(self, now: float, *, flush_open: bool) -> None:
        def kept(seg) -> bool:
            return seg.end - seg.start >= MIN_VISIT_S

        if self._meter is None:
            return

        for seg in self._meter.pop_closed():
            if kept(seg):
                save_segment(self._conn, seg)
        if flush_open and (seg := self._meter.open_segment()) and kept(seg):
            save_segment(self._conn, seg)
            self._last_flush = now

    def update(self, r: Reading | None, _game_rect: tuple | None, now: float) -> None:
        if self._meter is not None:  # not tracking or paused: nothing is recorded
            self._meter.feed(r)
            if self._last_flush is None:
                self._last_flush = now
            self._save(now, flush_open=now - self._last_flush >= _FLUSH_S)
        if r is None or r.exp is not None or self._exp_seen is None:
            self._exp_seen = now
        self._waiting, self._unread = r is None, now - self._exp_seen > _UNREAD_S
        self._refresh(now)

    def _refresh(self, now: float) -> None:
        """The tab and the pinned line, from the last tick's game and bar."""
        held = {State.NOT_TRACKING: PRESS_START, State.PAUSED: PAUSED}.get(self._session.state)
        meter = self._meter or self._held
        rate = self._meter.rate(now) if self._meter else None
        if self._session.state == State.PAUSED:
            rate = self._paused_rate
        session = meter.session() if meter else None
        timer = self._timer(now) if self._session.mode == MANUAL else None
        self._show(box_lines(rate, session, self._waiting, self._unread, held, timer=timer))
        accent = self._unread and not self._waiting and not held
        self._texts[0].setStyleSheet(f"color: {ACCENT if accent else LABEL_COLOR};")
        self.pin_line.set_text(*pin_text(rate, self._waiting, self._unread, held))

    def _do(self, step: Step, now: float) -> None:
        """Carry out a session event's step on the meter."""
        if step.close and self._meter is not None:
            self._meter.close(now)
            self._save(now, flush_open=False)  # the open segment, as on quit
            self._held, self._meter = self._meter, None
        if not step.carry:
            self._held = None  # the session ended; its segments are saved
        if self._session.state != State.PAUSED:
            self._paused_rate = None
        if step.open:
            self._meter = self._new_meter(self._held.session_parts() if self._held else ())
            self._held = None
            self._last_flush = None
        self._run_clock(now)
        self._show_buttons()

    def _run_clock(self, now: float) -> None:
        """Manual mode's timer follows the session: it runs while tracking, holds while
        paused, and goes back to 0:00 once the session ends."""
        state = self._session.state
        if self._since is not None and state != State.TRACKING:
            self._tracked_s += now - self._since
            self._since = None
        if state == State.NOT_TRACKING:
            self._tracked_s = 0.0
        if state == State.TRACKING and self._since is None:
            self._since = now

    def _timer(self, now: float) -> float | None:
        """Seconds tracked in this session, pauses left out; None before Start."""
        if self._session.state == State.NOT_TRACKING:
            return None
        return self._tracked_s + (now - self._since if self._since is not None else 0.0)

    def _show_buttons(self) -> None:
        state = self._session.state
        self._session_row.setVisible(self._session.mode == MANUAL)
        self._start.setVisible(state != State.TRACKING)
        self._start.setText(RESUME if state == State.PAUSED else START)
        self._pause.setVisible(state == State.TRACKING)
        self._reset.setEnabled(state != State.NOT_TRACKING)

    def start(self, now: float) -> None:
        """Manual Start, or Resume after a Pause: a new session, or the paused one goes on,
        its live rate measured afresh."""
        self._do(self._session.start(), now)
        self._refresh(now)

    def pause(self, now: float) -> None:
        """Manual Pause: the visit is saved and nothing counts until Resume; the numbers
        stay on screen as they were."""
        if self._meter is not None and self._session.state == State.TRACKING:
            self._paused_rate = self._meter.rate(now)
        self._do(self._session.pause(), now)
        self._refresh(now)

    def reset(self, now: float) -> None:
        """Manual Reset: the session ends and is saved; nothing is tracked until Start."""
        self._do(self._session.reset(), now)
        self._refresh(now)

    def set_session_mode(self, mode: str) -> None:
        """The EXP card's choice: a running session carries on (session.py)."""
        if mode == self._settings["exp_session_mode"]:
            return
        now = time.time()
        self._settings["exp_session_mode"] = mode
        self._do(self._session.set_mode(mode), now)
        if self._meter is not None:
            self._meter.set_split(self._session.split, now)
        self._refresh(now)
        self._save_settings()

    def settings_section(self) -> QWidget:
        """The EXP section of the Settings window: how sessions start and end."""
        section = QWidget()
        rows = QVBoxLayout(section)
        rows.setContentsMargins(0, 0, 0, 0)
        rows.setSpacing(2)
        rows.addWidget(QLabel(SESSIONS))
        choices = setting_choice(
            SESSION_MODES, self._settings["exp_session_mode"], self.set_session_mode
        )
        for mode, choice in zip(SESSION_MODES, choices, strict=True):
            rows.addSpacing(4)
            rows.addWidget(choice)
            hint = QLabel(SESSION_HINTS[mode])
            hint.setObjectName("hint")
            hint.setContentsMargins(22, 0, 0, 0)  # under the choice's text, past its ring
            rows.addWidget(hint)
        return section

    def shutdown(self, now: float) -> None:
        if self._meter is not None:
            self._meter.close(now)
            self._save(now, flush_open=False)

    def stop(self, now: float) -> None:
        """Turned off in Settings: the session ends and is saved, as on quit; in auto a fresh
        one starts when it's on again, in manual it waits for Start."""
        self._do(self._session.reset(), now)
        self._last_flush = self._exp_seen = None
        self._waiting, self._unread = True, False
        self._refresh(now)


def _row(*buttons: QWidget) -> QWidget:
    """Buttons side by side in equal parts of the tab's width."""
    row = QWidget()
    line = QHBoxLayout(row)
    line.setContentsMargins(0, 0, 0, 0)
    line.setSpacing(8)
    for b in buttons:
        line.addWidget(b, 1)
    return row
