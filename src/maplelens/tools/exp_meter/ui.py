"""The EXP meter tool: a tab with live numbers and a History window."""

import sqlite3
import sys
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
    native_setup,
    secondary_button,
    text_label,
)
from maplelens.readers import Reading
from maplelens.tools.exp_meter.history import MIN_VISIT_S, best_maps, history, save_segment
from maplelens.tools.exp_meter.meter import ExpMeter
from maplelens.tools.exp_meter.text import (
    Column,
    best_lines,
    box_lines,
    format_duration,
    format_last,
    short_name,
)

_FLUSH_S = 60
_UNREAD_S = 10  # the bar unreadable this long, with the game found: say so
_COLUMNS = ["Map", "Class", "Lvl", "Avg EXP/h", "Avg %/h", "Active time", "Last there"]


class _Item(QTableWidgetItem):
    """A cell that sorts by a value instead of by its text."""

    def __init__(self, text: str, key):
        super().__init__(text)
        self.key = key

    def __lt__(self, other):
        return self.key < other.key


JobLine = Callable[[str], Collection[str]]


class HistoryWindow(QWidget):
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
        self.setAttribute(Qt.WA_QuitOnClose, False)  # closing it must not end the app
        # Over the game, leaving it the keyboard, as the box does. On the Mac, native_setup
        # makes it a panel that does both.
        self.setWindowFlag(Qt.Tool)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        if sys.platform != "darwin":
            self.setWindowFlag(Qt.WindowStaysOnTopHint)
            self.setWindowFlag(Qt.WindowDoesNotAcceptFocus)
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

    def showEvent(self, event):
        native_setup(self)
        super().showEvent(event)


class ExpMeterTool:
    def __init__(self, settings: dict, conn: sqlite3.Connection, job_line: JobLine = lambda j: {j}):
        self._conn = conn
        self._meter = ExpMeter(settings["idle_cutoff_s"], settings["jump_factor"])
        self._last_flush: float | None = None
        self._exp_seen: float | None = None  # last tick the bar was read, or the game was gone
        self._history = HistoryWindow(conn, job_line)
        self.title = "EXP"
        self.tab = QWidget()
        self.tab.setFixedWidth(TAB_W)  # same box width as the other tabs
        self._lines = QVBoxLayout(self.tab)
        self._lines.setContentsMargins(0, 4, 0, 0)
        self._lines.setSpacing(0)
        self._button_row = secondary_button("History", self._show_history)
        self._shape: list[list[int]] | None = None  # values per row of what's shown
        self._texts: list[QLabel] = []
        self._show(box_lines(None, None, True))

    def set_tab_w(self, width: int) -> None:
        self.tab.setFixedWidth(width)

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
        self._history.refresh(self._meter.job, self._meter.level)
        self._history.show()
        self._history.raise_()

    def _save(self, now: float, *, flush_open: bool) -> None:
        def kept(seg) -> bool:
            return seg.end - seg.start >= MIN_VISIT_S

        for seg in self._meter.pop_closed():
            if kept(seg):
                save_segment(self._conn, seg)
        if flush_open and (seg := self._meter.open_segment()) and kept(seg):
            save_segment(self._conn, seg)
            self._last_flush = now

    def update(self, r: Reading | None, _game_rect: tuple | None, now: float) -> None:
        self._meter.feed(r)
        if self._last_flush is None:
            self._last_flush = now
        self._save(now, flush_open=now - self._last_flush >= _FLUSH_S)
        if r is None or r.exp is not None or self._exp_seen is None:
            self._exp_seen = now
        unread = now - self._exp_seen > _UNREAD_S
        self._show(box_lines(self._meter.rate(now), self._meter.session(), r is None, unread))
        self._texts[0].setStyleSheet(f"color: {ACCENT if unread else LABEL_COLOR};")

    def shutdown(self, now: float) -> None:
        self._meter.close(now)
        self._save(now, flush_open=False)
