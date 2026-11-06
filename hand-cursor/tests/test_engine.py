from hand_cursor.config import Calibration, Settings
from hand_cursor.engine import ENGAGED, IDLE, Engine

from conftest import CALIBRATION, OPEN_INDEX, OPEN_MIDDLE, PINCHED, FakeMouse, Sim


# ----- turning mouse mode on and off -----

def test_short_pinch_does_not_engage(rig):
    sim, mouse, _ = rig
    sim.click(down=0.2)
    assert sim.engine.state == IDLE


def test_held_pinch_engages_without_clicking(rig):
    sim, mouse, _ = rig
    sim.engage()
    assert mouse.of("down") == [] and mouse.of("up") == []


def test_no_engage_with_hand_at_keyboard_height(rig):
    sim, _, _ = rig
    sim.hold(1.0, height=100.0, d_index=PINCHED)
    assert sim.engine.state == IDLE


def test_no_engage_while_typing(rig):
    sim, _, keys = rig
    for _ in range(10):  # keep typing for a second while pinching
        keys[0] = sim.t
        sim.hold(0.1, d_index=PINCHED)
    assert sim.engine.state == IDLE


def test_a_hand_that_already_looks_pinched_does_not_engage(rig):
    sim, _, _ = rig
    sim.hold(1.0, height=200.0, d_index=PINCHED)  # e.g. resting, or tracked badly as "pinched"
    assert sim.engine.state == IDLE
    sim.hold(0.3, d_index=OPEN_INDEX)  # a deliberate open-then-pinch does
    sim.hold(0.6, d_index=PINCHED)
    assert sim.engine.state == ENGAGED


def test_raising_an_already_pinched_hand_needs_a_fresh_pinch(rig):
    sim, _, _ = rig
    sim.hold(0.3, height=100.0)
    sim.hold(1.0, height=100.0, d_index=PINCHED)  # pinched while lowered
    sim.hold(0.6, height=200.0)
    assert sim.engine.state == IDLE


def test_a_flickering_hand_does_not_engage(rig):
    sim, _, _ = rig
    for _ in range(6):  # in view 0.2 s, out of view 0.15 s, like a hand at the edge of view
        sim.hold(0.05, d_index=OPEN_INDEX)
        sim.hold(0.15, d_index=PINCHED)
        sim.gone(0.15)
    assert sim.engine.state == IDLE


def test_lowering_hand_disengages(rig):
    sim, _, _ = rig
    sim.engage()
    sim.hold(0.6, height=100.0)
    assert sim.engine.state == IDLE


def test_lost_hand_disengages_and_releases_button(rig):
    sim, mouse, _ = rig
    sim.engage()
    sim.hold(0.1, d_index=PINCHED)
    assert len(mouse.of("down")) == 1
    sim.gone(1.0)
    assert sim.engine.state == IDLE
    assert len(mouse.of("up")) == 1


def test_brief_dropout_keeps_drag_alive(rig):
    sim, mouse, _ = rig
    sim.engage()
    sim.hold(0.1, d_index=PINCHED)
    sim.move(0.5, dx=30)
    sim.gone(0.3)
    sim.move(0.5, dx=30)
    assert sim.engine.state == ENGAGED
    assert mouse.of("up") == []
    sim.hold(0.2, d_index=OPEN_INDEX)
    assert len(mouse.of("up")) == 1


def test_shutdown_releases_held_button(rig):
    sim, mouse, _ = rig
    sim.engage()
    sim.hold(0.1, d_index=PINCHED)
    sim.engine.shutdown()
    assert len(mouse.of("up")) == 1


# ----- pointer movement -----

def test_cursor_moves_relative_and_in_the_right_direction(rig):
    sim, mouse, _ = rig
    sim.engage()
    start = mouse.pos
    sim.move(1.0, dx=20, dup=20)
    sim.hold(0.5)
    x, y = mouse.pos
    assert x > start[0] + 20  # hand right -> cursor right
    assert y < start[1] - 20  # hand up -> cursor up (screen y grows downward)


def test_fast_motion_travels_further_than_slow(rig):
    sim, mouse, _ = rig
    sim.engage()
    x0 = mouse.pos[0]
    sim.move(2.0, dx=20)  # 10 mm/s
    sim.hold(0.5)
    slow = mouse.pos[0] - x0
    x1 = mouse.pos[0]
    sim.move(0.1, dx=-20)  # 200 mm/s, back the other way
    sim.hold(0.5)
    fast = x1 - mouse.pos[0]
    assert 30 < slow < 60  # about gain_min (2.5 px/mm) x 20 mm
    assert fast > 2.5 * slow


def test_still_hand_does_not_drift(rig):
    sim, mouse, _ = rig
    sim.engage()
    before = len(mouse.of("move"))
    sim.hold(2.0)
    assert len(mouse.of("move")) == before


def test_single_frame_tracking_glitch_is_ignored(rig):
    sim, mouse, _ = rig
    sim.engage()
    start = mouse.pos
    sim.hold(0.01, x=500.0)  # one wild frame
    sim.hold(0.5, x=0.0)
    assert abs(mouse.pos[0] - start[0]) < 1 and abs(mouse.pos[1] - start[1]) < 1


def test_typing_turns_mouse_mode_off(rig):
    sim, mouse, keys = rig
    sim.engage()
    sim.hold(0.1, d_index=PINCHED)  # in the middle of a drag
    keys[0] = sim.t
    before = len(mouse.of("move"))
    sim.move(0.3, dx=30)
    assert sim.engine.state == IDLE
    assert len(mouse.of("move")) == before and len(mouse.of("up")) == 1  # button released


def test_typing_only_pauses_when_configured():
    mouse, keys = FakeMouse(), [-1e9]
    engine = Engine(Settings(sounds=False, typing_turns_off=False), CALIBRATION, mouse, lambda: keys[0])
    sim = Sim(engine)
    sim.engage()
    keys[0] = sim.t
    before = len(mouse.of("move"))
    sim.move(0.3, dx=30)
    assert engine.state == ENGAGED and len(mouse.of("move")) == before


def test_brief_pinch_flicker_does_not_restart_the_hold(rig):
    sim, _, _ = rig
    sim.hold(0.3, d_index=OPEN_INDEX)
    sim.hold(0.25, d_index=PINCHED)
    sim.hold(0.06, d_index=OPEN_INDEX)  # tracking loses the pinch for a moment
    sim.hold(0.2, d_index=PINCHED)
    assert sim.engine.state == ENGAGED  # about 0.5 s in total, not 0.4 s after the flicker


def test_one_frame_fingertip_spike_does_not_end_a_drag(rig):
    sim, mouse, _ = rig
    sim.engage()
    sim.hold(0.1, d_index=PINCHED)
    sim.move(0.3, dx=20)
    sim.hold(0.01, d_index=OPEN_INDEX)  # a single bad fingertip estimate
    sim.move(0.3, dx=20, d_index=PINCHED)
    assert mouse.of("up") == []


def test_without_usable_height_a_held_pinch_engages_anywhere():
    sideways = Calibration(**{**CALIBRATION.__dict__, "lift_axis": (0.66, 0.56, -0.51)})
    engine = Engine(Settings(sounds=False), sideways, FakeMouse())
    sim = Sim(engine)
    sim.hold(0.3, height=100.0)
    sim.hold(0.6, height=100.0, d_index=PINCHED)  # at "keyboard height"
    assert engine.state == ENGAGED and engine.status["height_used"] is False
    sim.hold(1.0, height=100.0, d_index=OPEN_INDEX)
    assert engine.state == ENGAGED  # lowering the hand doesn't matter either


# ----- clicking, dragging, selecting -----

def test_quick_pinch_clicks_in_place(rig):
    sim, mouse, _ = rig
    sim.engage()
    sim.click()
    downs, ups = mouse.of("down"), mouse.of("up")
    assert downs == [("down", "left", 500.0, 500.0, 1)]
    assert ups == [("up", "left", 500.0, 500.0, 1)]


def test_two_quick_pinches_double_click(rig):
    sim, mouse, _ = rig
    sim.engage()
    sim.click()
    sim.click()
    assert [e[4] for e in mouse.of("down")] == [1, 2]


def test_slow_pinches_are_separate_clicks(rig):
    sim, mouse, _ = rig
    sim.engage()
    sim.click()
    sim.hold(0.6)
    sim.click()
    assert [e[4] for e in mouse.of("down")] == [1, 1]


def test_pinch_and_move_drags(rig):
    sim, mouse, _ = rig
    sim.engage()
    sim.hold(0.1, d_index=PINCHED)
    sim.move(1.0, dx=40)
    sim.hold(0.2, d_index=OPEN_INDEX)
    down, up = mouse.of("down")[0], mouse.of("up")[0]
    drags = [e for e in mouse.of("move") if e[3] == "left"]
    assert drags, "moves while pinched should be drag events"
    assert up[2] > down[2] + 50


def test_tiny_movement_during_pinch_is_still_a_click(rig):
    sim, mouse, _ = rig
    sim.engage()
    sim.hold(0.05, d_index=PINCHED)
    sim.move(0.1, dx=2)  # 2 mm wobble, ~5 px
    sim.hold(0.15, d_index=OPEN_INDEX)
    down, up = mouse.of("down")[0], mouse.of("up")[0]
    assert (down[2], down[3]) == (up[2], up[3])
    assert not [e for e in mouse.of("move") if e[3] == "left"]


def test_click_lands_where_the_cursor_was_before_the_pinch(rig):
    sim, mouse, _ = rig
    sim.engage()
    sim.move(0.5, dx=50)  # moving right steadily...
    furthest = mouse.pos[0]
    sim.move(0.1, dx=10, d_index=PINCHED)  # ...and pinching on the way
    down = mouse.of("down")[0]
    assert down[2] < furthest


# ----- scrolling and right click -----

def test_middle_pinch_scrolls_like_a_joystick(rig):
    sim, mouse, _ = rig
    sim.engage()
    moves_before = len(mouse.of("move"))
    sim.hold(0.1, d_middle=PINCHED)
    sim.move(0.3, dup=30)
    sim.hold(0.5)
    scrolls = mouse.of("scroll")
    assert sum(e[2] for e in scrolls) > 100  # hand up -> scroll up
    assert all(e[1] == 0 for e in scrolls)  # locked to vertical
    assert len(mouse.of("move")) == moves_before  # cursor stays put
    sim.hold(0.2, d_middle=OPEN_MIDDLE)
    assert mouse.of("down") == []  # moved, so it was not a right click


def test_scroll_speed_grows_with_distance(rig):
    sim, mouse, _ = rig
    sim.engage()
    sim.hold(0.1, d_middle=PINCHED)
    sim.move(0.2, dup=15)
    n = len(mouse.of("scroll"))
    sim.hold(0.5)
    near = sum(e[2] for e in mouse.of("scroll")[n:])
    sim.move(0.2, dup=20)  # now 35 mm out
    n = len(mouse.of("scroll"))
    sim.hold(0.5)
    far = sum(e[2] for e in mouse.of("scroll")[n:])
    assert far > 3 * near > 0


def test_middle_tap_right_clicks(rig):
    sim, mouse, _ = rig
    sim.engage()
    sim.hold(0.15, d_middle=PINCHED)
    sim.hold(0.2, d_middle=OPEN_MIDDLE)
    assert [(e[0], e[1]) for e in mouse.events if e[0] in ("down", "up")] == [
        ("down", "right"), ("up", "right")]
