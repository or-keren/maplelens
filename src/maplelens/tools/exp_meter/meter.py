"""EXP rate, idle time and per-map/class/level segments from a stream of readings."""

import json
from collections import deque
from dataclasses import dataclass, field, replace
from functools import cache
from pathlib import Path
from statistics import median, quantiles

from maplelens.gamedata import load_game, load_spots
from maplelens.readers import ExpValue, Reading

_DATA = Path(__file__).parents[2] / "data"


@cache
def monster_free_maps() -> frozenset[str]:
    """Titles ("Street / Name") of the towns where no monster spawns: EXP gained there is a
    quest's reward, never a kill's."""
    maps = json.loads((_DATA / "maps.json").read_text("utf-8"))
    stats = load_spots().monsters  # a monster that gives no EXP (jump-quest ones) is no kill
    spawns = {
        m
        for mob in load_game().mobs.values()
        if str(mob.id) in stats and stats[str(mob.id)].exp > 0
        for m, n in mob.spawns.items()
        if n > 0
    }
    return frozenset(
        f"{m['street']} / {m['name']}" for m in maps if m["town"] and m["id"] not in spawns
    )


@dataclass
class Rate:
    exp_per_min: float
    pct_per_min: float
    minutes_to_level: float | None
    paused: bool = False  # no gain for longer than the idle cutoff: the numbers are the last ones
    early: bool = False  # under a minute of active time: a rough first estimate


@dataclass
class SessionRate:
    exp_per_min: float | None  # None under a minute of active time
    active_s: float


# More than this between counted gains ends the session: the next one starts a new one
SESSION_BREAK_S = 1800


@dataclass
class Segment:
    start: float
    end: float
    map_name: str
    job: str
    level: int
    exp: int = 0
    pct: float = 0.0
    active_s: float = 0.0
    # (t, raw, pct, gap) gains, as in ExpMeter._window; exp, pct and active_s are summed from them
    gains: list[tuple[float, int, float, float]] = field(default_factory=list, repr=False)


# A map, job or level that stops reading in a frame that shows the game keeps its value this
# long: a window over the minimap, or a misread, isn't the player leaving it.
HOLD_S = 120


class _Confirmed:
    """A field's value, which only changes once the same raw value arrives twice in a row;
    with `hold_s`, None only after it has read None for that long in frames at times `t`."""

    def __init__(self, hold_s: float = 0):
        self.last = self.value = None
        self.hold_s = hold_s
        self._none_since: float | None = None

    def update(self, v, t: float | None = None) -> bool:
        if v is not None or t is None:
            self._none_since = None
        elif self.value is not None and self.hold_s:
            if self._none_since is None:
                self._none_since = t
            if t - self._none_since < self.hold_s:
                return False
        changed = v == self.last and v != self.value
        if changed:
            self.value = v
        self.last = v
        return changed


# This many jumps in a row are real (a 2x event, a party, a richer map), not misreads
_JUMPS_TO_ACCEPT = 3
# A gap this many times a long usual one between gains (the 90th percentile, so the wait between
# pulls of several kills each counts as usual), and this long, is a break (buffs, walking,
# looting), not training, even under the idle cutoff; a wait for the respawn is shorter.
# ponytail: a break is only found while breaks are under 10% of the gains
_BREAK_FACTOR, _BREAK_MIN_S = 10, 30


def _totals(gains, idle_cutoff_s: float) -> tuple[int, float, float]:
    """(exp, %, active s) of (t, raw, pct, gap) gains, leaving out each gain after a break:
    its gap and its EXP, as for the first gain after an idle stretch."""
    gaps = [g[3] for g in gains]
    cutoff = idle_cutoff_s
    if len(gaps) >= 10:  # enough gaps to know the pace (the break's own among them)
        cutoff = min(cutoff, max(_BREAK_MIN_S, _BREAK_FACTOR * quantiles(gaps, n=10)[-1]))
    kept = [g for g in gains if g[3] <= cutoff]
    return sum(g[1] for g in kept), sum(g[2] for g in kept), sum(g[3] for g in kept)


class ExpMeter:
    def __init__(self, idle_cutoff_s: float = 90, jump_factor: float = 5, window_s: float = 300):
        self.idle_cutoff_s = idle_cutoff_s
        self.jump_factor = jump_factor
        self.window_s = window_s
        self._exp, self._level, self._job, self._map = fields = (
            _Confirmed(),
            *(_Confirmed(HOLD_S) for _ in range(3)),
        )
        self._fields = fields
        self._base: tuple[ExpValue, int | None] | None = None  # last non-None exp and its level
        # (t, raw, pct, gap) gains whose gap since the previous exp event is under the cutoff
        self._window: deque[tuple[float, int, float, float]] = deque()
        self._event_t: float | None = None  # last accepted gain
        self._recent: deque[float] = deque(maxlen=50)  # pct of the last counted gains
        self._jumps = 0  # jumps rejected in a row
        self._seg: Segment | None = None
        self._closed: list[Segment] = []
        self._last_event_t: float | None = None  # the segment's clock: its start or last gain
        # the session's gains, one list per segment: each learns its own pace for the break
        # filter, as History's segments do, so a slow map's kills aren't breaks next to a fast one's
        self._session: list[list[tuple[float, int, float, float]]] = []
        self._session_seg: Segment | None = None  # whose gains the last list holds

    def feed(self, r: Reading | None) -> None:
        t = r.t if r else None
        vals = (r.exp, r.level, r.job, r.map_name) if r else (None,) * 4
        exp_ch, *_ = (f.update(v, t) for f, v in zip(self._fields, vals, strict=True))

        level = self._level.value
        ctx = (self._map.value, self._job.value, level)

        # 1. exp change, credited to the segment open now (a level-up's wrap goes to the old level)
        # the baseline is the last confirmed non-None exp; an unreadable bar never resets it
        if exp_ch and self._exp.value is not None:
            if self._base is not None:
                self._on_exp(*self._base, None in ctx, t)
            self._base = (self._exp.value, level)

        # 2. close on a confirmed change to a different non-None value, then open
        seg = self._seg
        if seg and any(
            c is not None and c != s
            for c, s in zip(ctx, (seg.map_name, seg.job, seg.level), strict=True)
        ):
            self._close(t)
        if self._seg is None and None not in ctx:
            self._seg = Segment(t, t, *ctx[:2], level)
            self._last_event_t = t

        # 3. map, job or level confirmed unreadable (HOLD_S of it): pause accrual, keep the segment
        if None in ctx:
            self._last_event_t = None

    def _gain(self, old: ExpValue, old_level) -> tuple[float, float] | None:
        """(exp, %) gained since `old`, or None for a death, a misread or a spike."""
        new, level = self._exp.value, self._level.value
        gain = None
        if old_level is None or level is None:
            return None
        if level == old_level:
            if new.raw >= old.raw and new.pct >= old.pct:  # a drop at the same level is a death
                gain = (new.raw - old.raw, new.pct - old.pct)
        elif level > old_level:
            # ponytail: level-up needs the level and the % drop to confirm on the same feed;
            # a level misread at that moment counts the wrap as a death. Look at the level
            # one feed later if that shows up.
            base = old.raw / (old.pct / 100) - old.raw if old.pct else 0
            gain = (round(base) + new.raw, (100 - old.pct) + new.pct)
        if gain and len(self._recent) >= 10:
            med = median(self._recent)
            if med > 0 and gain[1] > self.jump_factor * med:
                self._jumps += 1
                if self._jumps < _JUMPS_TO_ACCEPT:
                    return None
                self._recent.clear()  # learn the new size from here
        if gain:
            self._jumps = 0
        return gain

    def _on_exp(self, old: ExpValue, old_level, paused: bool, t: float) -> None:
        if self._map.value in monster_free_maps():
            # a quest's reward: not a gain, nor a jump to learn from, and the walk to the NPC
            # is not training, so the next kill only starts the clock again
            # ponytail: a quest handed in on a field still counts; tell it by the NPC's dialog
            self._event_t = self._last_event_t = None
            return
        gain = self._gain(old, old_level)
        if gain:
            self._recent.append(gain[1])
            # the first gain, or one after an idle stretch, only starts the clock: no time, no exp
            if self._event_t is not None and (gap := t - self._event_t) <= self.idle_cutoff_s:
                self._window.append((t, *gain, gap))
                active = sum(g[3] for g in self._window)
                while active - self._window[0][3] >= self.window_s:  # last window_s of active time
                    active -= self._window.popleft()[3]
            self._event_t = t
        seg = self._seg
        if seg and not paused:  # gains while paused count in the live rate only
            if gain:
                # the same gain as the live rate's, timed from the segment's own clock
                last = self._last_event_t
                if last is not None and (gap := t - last) <= self.idle_cutoff_s:
                    seg.gains.append((t, *gain, gap))
                    if self._session and t - self._session[-1][-1][0] > SESSION_BREAK_S:
                        self._session = []
                    if not self._session or self._session_seg is not seg:
                        self._session.append([])
                        self._session_seg = seg
                    self._session[-1].append(seg.gains[-1])
                self._last_event_t = t
            seg.end = t

    def _close(self, t: float) -> None:
        if self._seg:
            self._seg.end = t
            self._closed.append(self._summed(self._seg))
        self._seg = self._last_event_t = None

    def _summed(self, seg: Segment) -> Segment:
        exp, pct, active = _totals(seg.gains, self.idle_cutoff_s)
        return replace(seg, exp=exp, pct=pct, active_s=active)

    def rate(self, now: float) -> Rate | None:
        """EXP per minute of active time over the last `window_s` of it; None before the
        first timed gain (the second kill), `early` under a minute."""
        exp_sum, pct_sum, active = _totals(self._window, self.idle_cutoff_s)
        if active <= 0:
            return None
        minutes = active / 60
        pct_per_min = pct_sum / minutes
        exp = self._exp.value
        left = (100 - exp.pct) / pct_per_min if exp and pct_per_min > 0 else None
        paused = self._event_t is None or now - self._event_t > self.idle_cutoff_s
        return Rate(exp_sum / minutes, pct_per_min, left, paused, early=active < 60)

    def session(self) -> SessionRate | None:
        """Active EXP per minute since the session began: the sum of its segments' totals;
        None before its first counted gain."""
        if not self._session:
            return None
        # ponytail: re-sums every segment's gains each tick; cache closed segments' totals if
        # long sessions show up in a profile
        totals = [_totals(gains, self.idle_cutoff_s) for gains in self._session]
        exp, active = sum(t[0] for t in totals), sum(t[2] for t in totals)
        return SessionRate(exp / active * 60 if active >= 60 else None, active)

    @property
    def job(self) -> str | None:
        return self._job.value

    @property
    def level(self) -> int | None:
        return self._level.value

    def pop_closed(self) -> list[Segment]:
        closed, self._closed = self._closed, []
        return closed

    def open_segment(self) -> Segment | None:
        return self._summed(self._seg) if self._seg else None

    def close(self, now: float) -> None:
        self._close(now)
