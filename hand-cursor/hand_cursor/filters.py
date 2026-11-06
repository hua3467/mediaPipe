"""One Euro filter (Casiez et al., CHI 2012) for 3D points."""
from __future__ import annotations

import math
from typing import Optional

from .geometry import Vec3, add, norm, scale, sub


def _alpha(cutoff_hz: float, dt: float) -> float:
    tau = 1.0 / (2.0 * math.pi * cutoff_hz)
    return 1.0 / (1.0 + tau / dt)


class OneEuroFilter:
    """Smooths heavily while the hand is still and lightly while it moves fast.

    The cutoff follows the speed of the whole point (mm/s), so all three axes are
    smoothed together and diagonal motion isn't distorted.
    """

    def __init__(self, min_cutoff: float, beta: float, d_cutoff: float = 1.0):
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff
        self.reset()

    def reset(self) -> None:
        self._x: Optional[Vec3] = None
        self._dx: Vec3 = (0.0, 0.0, 0.0)
        self._t = 0.0

    def __call__(self, x: Vec3, t: float) -> Vec3:
        if self._x is None:
            self._x, self._t = x, t
            return x
        dt = max(t - self._t, 1e-4)
        self._t = t
        raw_dx = scale(sub(x, self._x), 1.0 / dt)
        self._dx = add(self._dx, scale(sub(raw_dx, self._dx), _alpha(self.d_cutoff, dt)))
        cutoff = self.min_cutoff + self.beta * norm(self._dx)
        self._x = add(self._x, scale(sub(x, self._x), _alpha(cutoff, dt)))
        return self._x
