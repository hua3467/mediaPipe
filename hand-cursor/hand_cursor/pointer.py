"""Mouse-style relative pointer mapping."""
from __future__ import annotations

import math
from typing import Sequence, Tuple

from .config import Settings

Rect = Tuple[float, float, float, float]  # x, y, width, height in screen points


def smoothstep(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return x * x * (3.0 - 2.0 * x)


class PointerGain:
    """Pointer acceleration: slow hand motion moves the cursor finely, fast motion far.

    Like a mouse, the hand only ever moves a few centimetres; speed decides how far the
    cursor travels.
    """

    def __init__(self, s: Settings):
        self.s = s

    def gain(self, speed: float) -> float:
        s = self.s
        k = smoothstep((speed - s.speed_low) / max(s.speed_high - s.speed_low, 1e-6))
        return s.gain_min + (s.gain_max - s.gain_min) * k

    def __call__(self, dx_mm: float, dy_mm: float, dt: float) -> Tuple[float, float]:
        """Hand movement (mm, +y = up) to cursor movement (px, +y = down the screen)."""
        speed = math.hypot(dx_mm, dy_mm) / max(dt, 0.004)
        if speed < self.s.rest_speed:
            return (0.0, 0.0)
        g = self.gain(speed)
        return (g * dx_mm, -g * dy_mm)


def _inside(x: float, y: float, r: Rect) -> bool:
    return r[0] <= x < r[0] + r[2] and r[1] <= y < r[1] + r[3]


def _gap(p: Tuple[float, float], r: Rect) -> float:
    dx = max(r[0] - p[0], 0.0, p[0] - (r[0] + r[2]))
    dy = max(r[1] - p[1], 0.0, p[1] - (r[1] + r[3]))
    return math.hypot(dx, dy)


def clamp_to_displays(x: float, y: float, displays: Sequence[Rect],
                      prev: Tuple[float, float]) -> Tuple[float, float]:
    """Keep the cursor on screen. It may cross onto another display, but never into
    the gaps between displays."""
    if not displays or any(_inside(x, y, r) for r in displays):
        return (x, y)
    home = next((r for r in displays if _inside(prev[0], prev[1], r)), None)
    if home is None:
        home = min(displays, key=lambda r: _gap(prev, r))
    return (min(max(x, home[0]), home[0] + home[2] - 1),
            min(max(y, home[1]), home[1] + home[3] - 1))
