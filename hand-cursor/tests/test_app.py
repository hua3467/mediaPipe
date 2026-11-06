"""run/monitor must not switch the tracker's mode behind your back."""
import math
from types import SimpleNamespace as NS

import pytest

from hand_cursor import app
from hand_cursor.config import Calibration, Settings
from hand_cursor.frames import Frame
from hand_cursor.mouse import DryRunMouse

from conftest import make_hand


class FakeSource:
    instance = None
    tracker_mode = "screentop"  # as set in Ultraleap Control Panel

    def __init__(self, on_frame, mode=None, log=print):
        self.on_frame, self.requested = on_frame, mode
        FakeSource.instance = self

    def __enter__(self):
        self.mode = self.requested or FakeSource.tracker_mode
        self.on_frame(Frame(0.01, (make_hand(),)))  # a frame arriving before the mode check
        return self

    def __exit__(self, *exc):
        pass


class FakeEngine:
    frames = []

    def __init__(self, *args, **kwargs):
        FakeEngine.frames = []

    def process(self, frame):
        FakeEngine.frames.append(frame)

    def shutdown(self):
        pass


@pytest.fixture
def live(monkeypatch):
    monkeypatch.setattr(app, "LeapSource", FakeSource)
    monkeypatch.setattr(app, "Engine", FakeEngine)
    monkeypatch.setattr(app, "load_settings", lambda: Settings(sounds=False))
    monkeypatch.setattr(app, "load_calibration", lambda: Calibration(tracking_mode="desktop"))
    monkeypatch.setattr(app, "KeyMonitor", lambda on_key=None: NS(start=lambda: True, stop=lambda: None,
                                                                  ok=True, __call__=lambda: -math.inf))

    def sleep_then_quit(_):  # one frame arrives while running, then Ctrl+C
        FakeSource.instance.on_frame(Frame(0.02, (make_hand(),)))
        raise KeyboardInterrupt
    monkeypatch.setattr(app.time, "sleep", sleep_then_quit)


def test_run_refuses_a_calibration_from_another_mode(live, capsys):
    result = app._live(NS(mode=None, record=None), DryRunMouse(log=lambda m: None), monitor=False)
    out = capsys.readouterr().out
    assert result == 1
    assert "made in Desktop mode, but the tracker is now in" in out and "Screentop" in out
    assert FakeEngine.frames == []  # nothing reached the mouse


def test_run_with_explicit_mode_switches_and_runs(live, capsys):
    result = app._live(NS(mode="desktop", record=None), DryRunMouse(log=lambda m: None), monitor=False)
    assert result == 0
    assert [f.t for f in FakeEngine.frames] == [0.02]  # only frames after the check
    assert "Tracking mode: Desktop" in capsys.readouterr().out
