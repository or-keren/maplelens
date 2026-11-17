"""When an EXP session tracks: the session state machine. Pure: no Qt, no meter.

`auto` (the default) tracks from the start, has no buttons, and never pauses; its 30-minute
split is the meter's (`split`). `manual` tracks only between Start and Pause or Reset, and
has no split: a session runs until Reset or quit.

Each event answers with a `Step`, what the EXP tool does with its meter: Pause closes it
and keeps its session for the next one; Start opens a fresh one, which takes a new
baseline, so EXP earned while paused is never credited.
"""

from dataclasses import dataclass
from enum import Enum

AUTO, MANUAL = "auto", "manual"
MODES = (AUTO, MANUAL)


class State(Enum):
    NOT_TRACKING = "not tracking"
    TRACKING = "tracking"
    PAUSED = "paused"


@dataclass(frozen=True)
class Step:
    """What the meter does after an event, in this order: `close` it (saving its segments);
    `carry` its session on to the next meter (else the session ends); `open` a fresh one."""

    close: bool = False
    carry: bool = False
    open: bool = False


NOTHING = Step(carry=True)  # the meter and its session go on as they are


class Session:
    def __init__(self, mode: str = AUTO):
        self.mode = mode
        self.state = State.TRACKING if mode == AUTO else State.NOT_TRACKING

    @property
    def split(self) -> bool:
        """Whether 30 minutes without counted EXP ends the session (auto only)."""
        return self.mode == AUTO

    def start(self) -> Step:
        """Manual Start: a new session, or the paused one goes on."""
        if self.mode == AUTO or self.state == State.TRACKING:
            return NOTHING
        paused = self.state == State.PAUSED
        self.state = State.TRACKING
        return Step(carry=paused, open=True)

    def pause(self) -> Step:
        """Manual Pause: nothing counts until Start; the session is kept."""
        if self.mode == AUTO or self.state != State.TRACKING:
            return NOTHING
        self.state = State.PAUSED
        return Step(close=True, carry=True)

    def reset(self) -> Step:
        """The session ends and is saved: manual Reset, or EXP turned off in Settings. In
        auto a fresh session tracks at once; in manual it waits for Start."""
        if self.mode == AUTO:
            return Step(close=True, open=True)
        was, self.state = self.state, State.NOT_TRACKING
        return Step(close=was == State.TRACKING)

    def gain(self) -> bool:
        """Whether EXP gained now counts: only while tracking."""
        return self.state == State.TRACKING

    def tick(self) -> Step:
        """Time passing, with or without the game (closed, minimized, MapleLens hidden): it
        never starts, pauses or ends a session. Auto's 30-minute split is the meter's."""
        return NOTHING

    def set_mode(self, mode: str) -> Step:
        """To manual: the running session ends and is saved, and nothing counts until Start
        (Daniel: choosing manual means "wait for my Start"). To auto: tracking starts if it
        wasn't, and a paused session goes on (auto has no button to unpause it)."""
        if mode == self.mode:
            return NOTHING
        self.mode = mode
        if mode == MANUAL:
            was, self.state = self.state, State.NOT_TRACKING
            return Step(close=was == State.TRACKING)
        if self.state == State.TRACKING:
            return NOTHING
        paused = self.state == State.PAUSED
        self.state = State.TRACKING
        return Step(carry=paused, open=True)
