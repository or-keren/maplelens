"""The session state machine: every row of the spec's rules table, in both modes."""

import pytest

from maplelens.tools.exp_meter.session import AUTO, MANUAL, NOTHING, Session, State, Step

NOT, ON, PAUSED = State.NOT_TRACKING, State.TRACKING, State.PAUSED


def _manual(state: State) -> Session:
    s = Session(MANUAL)
    if state != NOT:
        s.start()
    if state == PAUSED:
        s.pause()
    return s


# App starts


def test_auto_tracks_from_the_start():
    s = Session()
    assert (s.mode, s.state, s.split) == (AUTO, ON, True)


def test_manual_waits_for_start():
    s = Session(MANUAL)
    assert (s.state, s.split) == (NOT, False)
    assert not s.gain()  # not tracking records nothing


# Start


def test_manual_start_opens_a_new_session():
    s = Session(MANUAL)
    assert s.start() == Step(open=True)
    assert s.state == ON and s.gain()


def test_manual_start_after_pause_goes_on_with_the_session():
    s = _manual(PAUSED)
    assert s.start() == Step(carry=True, open=True)
    assert s.state == ON


def test_manual_start_while_tracking_does_nothing():
    s = _manual(ON)
    assert s.start() == NOTHING
    assert s.state == ON


def test_auto_has_no_start():
    s = Session()
    assert s.start() == NOTHING
    assert s.state == ON


# Pause


def test_manual_pause_closes_and_keeps_the_session():
    s = _manual(ON)
    assert s.pause() == Step(close=True, carry=True)
    assert s.state == PAUSED
    assert not s.gain()  # nothing counts until Start


@pytest.mark.parametrize("state", [NOT, PAUSED])
def test_manual_pause_when_not_tracking_does_nothing(state):
    s = _manual(state)
    assert s.pause() == NOTHING
    assert s.state == state


def test_auto_never_pauses():
    s = Session()
    assert s.pause() == NOTHING
    assert s.state == ON


# Reset (the button in manual; EXP turned off in Settings, in both modes)


def test_manual_reset_while_tracking_saves_and_stops():
    s = _manual(ON)
    assert s.reset() == Step(close=True)  # closed: saved; no carry: the session ends
    assert s.state == NOT


def test_manual_reset_while_paused_ends_the_held_session():
    s = _manual(PAUSED)
    assert s.reset() == Step()  # the meter closed and saved at Pause; the session ends
    assert s.state == NOT


def test_manual_reset_when_not_tracking_stays():
    s = Session(MANUAL)
    assert s.reset() == Step()
    assert s.state == NOT


def test_auto_reset_saves_and_tracks_afresh():
    s = Session()
    assert s.reset() == Step(close=True, open=True)
    assert s.state == ON


# 30 minutes with no counted EXP, the game closed or minimized, Hide: time alone never
# moves the session; auto's split is the meter's


@pytest.mark.parametrize(
    ("mode", "state"), [(AUTO, ON), (MANUAL, NOT), (MANUAL, ON), (MANUAL, PAUSED)]
)
def test_time_passing_never_moves_the_session(mode, state):
    s = Session(AUTO) if mode == AUTO else _manual(state)
    for _ in range(3):
        assert s.tick() == NOTHING
    assert s.state == state


def test_only_auto_splits_after_thirty_minutes():
    assert Session(AUTO).split
    assert not Session(MANUAL).split


@pytest.mark.parametrize(
    ("mode", "state", "counts"),
    [(AUTO, ON, True), (MANUAL, NOT, False), (MANUAL, ON, True), (MANUAL, PAUSED, False)],
)
def test_a_gain_counts_only_while_tracking(mode, state, counts):
    s = Session(AUTO) if mode == AUTO else _manual(state)
    assert s.gain() is counts
    assert s.state == state  # a gain never starts or ends a session


# Switching mode


def test_auto_to_manual_ends_the_session_and_waits_for_start():
    s = Session()
    assert s.set_mode(MANUAL) == Step(close=True)  # saved, and not carried on
    assert (s.state, s.split) == (State.NOT_TRACKING, False)
    assert not s.gain()  # nothing counts until Start
    assert s.start() == Step(open=True)  # a new session


@pytest.mark.parametrize("state", [ON, PAUSED])
def test_manual_to_auto_keeps_the_session_tracking(state):
    s = _manual(state)
    step = s.set_mode(AUTO)
    assert (s.state, s.split) == (ON, True)
    assert step == (NOTHING if state == ON else Step(carry=True, open=True))


def test_manual_to_auto_starts_tracking():
    s = Session(MANUAL)
    assert s.set_mode(AUTO) == Step(open=True)
    assert s.state == ON


def test_setting_the_same_mode_does_nothing():
    s = _manual(PAUSED)
    assert s.set_mode(MANUAL) == NOTHING
    assert s.state == PAUSED
