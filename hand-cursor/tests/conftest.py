"""Test helpers: a fake mouse and a simulated hand that feeds frames to the engine."""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hand_cursor.config import Calibration, Settings  # noqa: E402
from hand_cursor.engine import ENGAGED, Engine  # noqa: E402
from hand_cursor.frames import Frame, Hand  # noqa: E402
from hand_cursor.pointer import clamp_to_displays  # noqa: E402

# Desktop-style axes: x right, y up away from the tracker, -z forward (cursor up).
# Typing height 100 mm, mouse position 200 mm. Pinch registers < 36 mm, releases > 51 mm.
CALIBRATION = Calibration(
    tracking_mode="desktop", right_axis=(1.0, 0.0, 0.0), up_axis=(0.0, 0.0, -1.0),
    lift_axis=(0.0, 1.0, 0.0), keyboard_level=100.0, raised_level=200.0,
    pinch_closed_mm=15.0, pinch_open_mm=75.0)

OPEN_INDEX, OPEN_MIDDLE, PINCHED = 75.0, 85.0, 10.0


class FakeMouse:
    def __init__(self, start=(500.0, 500.0)):
        self.pos = start
        self.events = []

    def position(self):
        return self.pos

    def clamp(self, x, y, prev):
        return clamp_to_displays(x, y, [(0.0, 0.0, 1920.0, 1080.0)], prev)

    def move(self, x, y, button=None, clicks=1):
        self.pos = (x, y)
        self.events.append(("move", x, y, button, clicks))

    def down(self, button, x, y, clicks=1):
        self.pos = (x, y)
        self.events.append(("down", button, x, y, clicks))

    def up(self, button, x, y, clicks=1):
        self.pos = (x, y)
        self.events.append(("up", button, x, y, clicks))

    def scroll(self, dx, dy):
        self.events.append(("scroll", dx, dy))

    def of(self, kind):
        return [e for e in self.events if e[0] == kind]


def make_hand(x=0.0, up=0.0, height=200.0, d_index=OPEN_INDEX, d_middle=OPEN_MIDDLE, side="right"):
    palm = (x, height, -up)
    thumb = (x, height, -up + 40.0)
    return Hand(side=side, palm=palm, thumb=thumb,
                index=(thumb[0] + d_index, thumb[1], thumb[2]),
                middle=(thumb[0], thumb[1] + d_middle, thumb[2]))


class Sim:
    """A hand at 100 frames per second. Attributes persist between calls."""

    def __init__(self, engine, dt=0.01):
        self.engine, self.dt, self.t = engine, dt, 0.0
        self.x, self.up, self.height = 0.0, 0.0, 200.0
        self.d_index, self.d_middle = OPEN_INDEX, OPEN_MIDDLE

    def _set(self, kw):
        for key, value in kw.items():
            setattr(self, key, value)

    def _frame(self):
        self.t += self.dt
        hand = make_hand(self.x, self.up, self.height, self.d_index, self.d_middle)
        self.engine.process(Frame(self.t, (hand,)))

    def hold(self, seconds, **kw):
        self._set(kw)
        for _ in range(round(seconds / self.dt)):
            self._frame()

    def move(self, seconds, dx=0.0, dup=0.0, **kw):
        self._set(kw)
        n = round(seconds / self.dt)
        x0, up0 = self.x, self.up
        for i in range(1, n + 1):
            self.x, self.up = x0 + dx * i / n, up0 + dup * i / n
            self._frame()

    def gone(self, seconds):
        for _ in range(round(seconds / self.dt)):
            self.t += self.dt
            self.engine.process(Frame(self.t, ()))

    def engage(self):
        self.hold(0.3, d_index=OPEN_INDEX)  # seen open first...
        self.hold(0.6, d_index=PINCHED)  # ...then a held pinch
        self.hold(0.3, d_index=OPEN_INDEX)
        assert self.engine.state == ENGAGED

    def click(self, down=0.12, up=0.15):
        self.hold(down, d_index=PINCHED)
        self.hold(up, d_index=OPEN_INDEX)


@pytest.fixture
def rig():
    """(sim, mouse, keys) where keys[0] is the time of the last key press."""
    mouse = FakeMouse()
    keys = [-math.inf]
    engine = Engine(Settings(sounds=False), CALIBRATION, mouse, lambda: keys[0])
    return Sim(engine), mouse, keys
