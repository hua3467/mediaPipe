"""Runs the whole interactive calibration against a scripted fake tracker."""
import pytest

from hand_cursor.app import status_line
from hand_cursor.calibrate import best_mode, motion_axis, run_calibration
from hand_cursor.config import Settings
from hand_cursor.frames import Frame

from conftest import CALIBRATION, make_hand


def still(n, side="right", **hand):
    return [Frame(i * 0.01, (make_hand(side=side, **hand),)) for i in range(n)]


def movement(n, start, end, **hand):
    """Hold at start, move, hold at end; positions are (x, up, height)."""
    frames = []
    for i in range(n):
        k = min(1.0, max(0.0, (i - n * 0.2) / (n * 0.3)))
        x, up, height = (s + (e - s) * k for s, e in zip(start, end))
        frames.append(Frame(i * 0.01, (make_hand(x=x, up=up, height=height, **hand),)))
    return frames


class FakeSource:
    def __init__(self, mode=None):
        self.mode = mode  # the tracker's current mode; None = unknown
        self.modes = []

    def set_mode(self, mode):
        self.modes.append(mode)
        self.mode = mode


class ScriptedBuffer:
    def __init__(self, recordings):
        self.recordings = list(recordings)

    def record(self, seconds):
        return self.recordings.pop(0)


def test_full_calibration_measures_the_setup():
    buffer = ScriptedBuffer([
        still(200, side="left"),  # desktop mode: hand reported as the wrong side
        still(200),  # hmd: seen every frame
        still(200)[::2] + [Frame(9, ())] * 100,  # screentop: seen half the time
        still(250, height=100.0),  # typing
        still(250, height=200.0, d_index=70.0),  # mouse position, open
        still(200, height=200.0, d_index=15.0),  # pinched
        movement(300, (0, 0, 200), (80, 0, 200)),  # move right
        movement(300, (80, 0, 200), (80, 70, 200)),  # move "up" (forward, -z)
    ])
    source, log = FakeSource(), []
    c = run_calibration(source, buffer, Settings(), log=log.append, ask=lambda _: "",
                        sleep=lambda _: None)
    assert c.tracking_mode == "hmd" and source.modes[-1] == "hmd"
    assert c.right_axis == pytest.approx((1, 0, 0))
    assert c.up_axis == pytest.approx((0, 0, -1))
    assert c.lift_axis == pytest.approx((0, 1, 0))
    assert (c.keyboard_level, c.raised_level) == (100.0, 200.0)
    assert (c.pinch_closed_mm, c.pinch_open_mm) == (15.0, 70.0)


def test_calibrates_in_the_trackers_current_mode_without_switching():
    buffer = ScriptedBuffer([
        still(250, height=100.0), still(250, d_index=70.0), still(200, d_index=15.0),
        movement(300, (0, 0, 200), (80, 0, 200)),
        movement(300, (80, 0, 200), (80, 70, 200)),
    ])
    source = FakeSource(mode="screentop")
    c = run_calibration(source, buffer, Settings(), log=lambda _: None, ask=lambda _: "",
                        sleep=lambda _: None)
    assert c.tracking_mode == "screentop" and source.modes == []


def test_too_closed_open_hand_is_measured_again():
    buffer = ScriptedBuffer([
        still(250, height=100.0),
        still(250, d_index=35.0), still(200, d_index=12.0),  # like a cramped open hand: too close
        still(250, d_index=70.0), still(200, d_index=12.0),  # second try, fingers spread
        movement(300, (0, 0, 200), (80, 0, 200)),
        movement(300, (80, 0, 200), (80, 70, 200)),
    ])
    log = []
    c = run_calibration(FakeSource(mode="screentop"), buffer, Settings(), log=log.append,
                        ask=lambda _: "", sleep=lambda _: None)
    assert (c.pinch_closed_mm, c.pinch_open_mm) == (12.0, 70.0)
    assert any("measure the open hand again" in line for line in log)


def test_calibration_without_visible_typing_hands_skips_height():
    buffer = ScriptedBuffer([
        [Frame(i * 0.01, ()) for i in range(250)],  # hands at keyboard not visible
        still(250, d_index=70.0),
        still(200, d_index=15.0),
        movement(300, (0, 0, 200), (80, 0, 200)),
        movement(300, (80, 0, 200), (80, 70, 200)),
    ])
    c = run_calibration(FakeSource(), buffer, Settings(), log=lambda _: None, ask=lambda _: "",
                        sleep=lambda _: None, fixed_mode="desktop")
    assert c.lift_axis is None and c.raise_thresholds(Settings()) is None


def test_up_direction_is_made_perpendicular_to_right():
    buffer = ScriptedBuffer([
        still(250, height=100.0), still(250, d_index=70.0), still(200, d_index=15.0),
        movement(300, (0, 0, 200), (80, 0, 200)),
        movement(300, (80, 0, 200), (110, 70, 200)),  # "up" with some sideways drift
    ])
    c = run_calibration(FakeSource(), buffer, Settings(), log=lambda _: None, ask=lambda _: "",
                        sleep=lambda _: None, fixed_mode="desktop")
    assert c.up_axis == pytest.approx((0, 0, -1), abs=1e-3)


def test_motion_axis_and_best_mode():
    samples = [(f.t, f.hands[0].palm) for f in movement(300, (0, 0, 200), (0, 0, 120))]
    axis, distance = motion_axis(samples)
    assert axis == pytest.approx((0, -1, 0)) and distance == pytest.approx(80, abs=1)
    assert best_mode({"a": (0.98, 2.0), "b": (0.99, 0.5), "c": (0.5, 0.1)}) == "b"


def test_status_line_formats():
    status = {"hand": True, "state": "engaged", "side": "right", "palm": (1, 2, 3), "lift": 180.0,
              "raised": True, "thumb_index": 50.0, "thumb_middle": 60.0, "pinch": None,
              "typing": False, "dragging": True, "scrolling": False}
    line = status_line(status, CALIBRATION)
    assert "MOUSE ON" in line and "height  0.8 (raised)" in line and "(dragging)" in line
    assert "no hand" in status_line({"hand": False, "state": "idle"}, CALIBRATION)
