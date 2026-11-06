import random

import pytest

from hand_cursor.config import Calibration, Settings
from hand_cursor.filters import OneEuroFilter
from hand_cursor.frames import Frame, Hand, Recorder, read_recording
from hand_cursor.gestures import Hysteresis, PinchTracker
from hand_cursor.pointer import PointerGain, clamp_to_displays

from conftest import make_hand


def test_filter_steadies_a_resting_hand():
    random.seed(1)
    f = OneEuroFilter(1.0, 0.04)
    out = [f((random.uniform(-1, 1), 0.0, 0.0), i * 0.01)[0] for i in range(300)]
    raw_spread, out_spread = 2.0, max(out[100:]) - min(out[100:])
    assert out_spread < 0.3 * raw_spread


def test_filter_keeps_up_with_fast_motion():
    f = OneEuroFilter(1.0, 0.04)
    for i in range(51):  # 300 mm/s for half a second
        x = f((3.0 * i, 0.0, 0.0), i * 0.01)[0]
    assert 150.0 - x < 8.0  # lag under 8 mm


def test_pointer_gain_acceleration_curve():
    s = Settings()
    g = PointerGain(s)
    assert g(0.03, 0.0, 0.01) == (0.0, 0.0)  # 3 mm/s: resting tremor
    assert g(0.2, 0.0, 0.01)[0] == pytest.approx(0.2 * s.gain_min)  # 20 mm/s
    assert g(5.0, 0.0, 0.01)[0] == pytest.approx(5.0 * s.gain_max)  # 500 mm/s
    assert g(0.0, 1.0, 0.01)[1] < 0  # hand up -> cursor up the screen


def test_clamp_allows_crossing_displays_but_not_gaps():
    displays = [(0, 0, 1920, 1080), (1920, 0, 1440, 900)]
    assert clamp_to_displays(1950, 500, displays, (1900, 500)) == (1950, 500)
    assert clamp_to_displays(1950, 1000, displays, (1900, 1000)) == (1919, 1000)
    assert clamp_to_displays(-50, -50, displays, (10, 10)) == (0, 0)


def test_pinch_needs_confirmation_and_locks_finger():
    p = PinchTracker(36, 51, confirm_s=0.03)
    assert p.update(30, 80, 0.00) is None
    assert p.update(30, 80, 0.02) is None
    assert p.update(30, 80, 0.03) == ("start", "index")
    assert p.update(60, 20, 0.04) == ("end", "index")  # index opened past 51 mm
    assert p.update(60, 20, 0.05) is None
    assert p.update(60, 20, 0.08) == ("start", "middle")


def test_pinch_hysteresis_ignores_wobble():
    p = PinchTracker(36, 51, confirm_s=0.0)
    assert p.update(30, 80, 0.0) == ("start", "index")
    assert p.update(45, 80, 0.1) is None  # between thresholds: still pinching
    assert p.update(52, 80, 0.2) == ("end", "index")


def test_hysteresis():
    h = Hysteresis(on=150, off=130)
    assert [h.update(v) for v in (100, 160, 140, 120, 140)] == [False, True, True, False, False]


def test_calibration_thresholds():
    s = Settings()
    c = Calibration(pinch_closed_mm=15, pinch_open_mm=75, lift_axis=(0, 1, 0),
                    keyboard_level=100, raised_level=200)
    assert c.pinch_thresholds(s) == pytest.approx((45.0, 60.0))
    assert c.raise_thresholds(s) == pytest.approx((150.0, 130.0))
    assert Calibration().raise_thresholds(s) is None


def test_height_is_only_used_when_mouse_position_is_clearly_above_typing():
    up_axis, right_axis = (0, 0, -1), (1, 0, 0)
    good = Calibration(right_axis=right_axis, up_axis=up_axis, lift_axis=(0, 1, 0),
                       keyboard_level=100, raised_level=200)
    assert good.height_problem() is None
    small = Calibration(right_axis=right_axis, up_axis=up_axis, lift_axis=(0, 1, 0),
                        keyboard_level=100, raised_level=154)
    assert "only 54 mm" in small.height_problem() and small.raise_thresholds(Settings()) is None
    # Like the first Screentop calibration: the mouse position was mostly beside the typing one.
    sideways = Calibration(right_axis=right_axis, up_axis=up_axis, lift_axis=(0.66, 0.56, -0.51),
                           keyboard_level=100, raised_level=200)
    assert "beside" in sideways.height_problem()


def test_recording_round_trip(tmp_path):
    path = tmp_path / "rec.jsonl"
    rec = Recorder(path)
    hand = make_hand(x=12.25, d_index=30)
    frame = Frame(1.5, (Hand(**{**hand.__dict__, "pinch_strength": 0.8, "grab_strength": 0.1}),))
    rec.frame(frame)
    rec.key(1.6)
    rec.frame(Frame(1.7, ()))
    rec.close()
    items = list(read_recording(path))
    assert items[0] == frame and items[1] == pytest.approx(1.6) and items[2] == Frame(1.7, ())
    assert (items[0].hands[0].pinch_strength, items[0].hands[0].grab_strength) == (0.8, 0.1)
