"""Pinch detection and threshold helpers."""
from __future__ import annotations

from typing import Optional, Tuple

PinchEvent = Optional[Tuple[str, str]]  # ("start" | "end", "index" | "middle")


class Hysteresis:
    """A boolean that switches on above `on` and back off below `off` (on >= off)."""

    def __init__(self, on: float, off: float):
        if on < off:
            raise ValueError("on threshold must be >= off threshold")
        self.on, self.off = on, off
        self.state = False

    def update(self, value: float) -> bool:
        if not self.state and value > self.on:
            self.state = True
        elif self.state and value < self.off:
            self.state = False
        return self.state


class PinchTracker:
    """Detects thumb-index and thumb-middle pinches.

    A pinch starts once the nearer fingertip has stayed within `on` mm of the thumb
    for `confirm_s`. That finger is then locked in until it moves past `off` mm, so
    the other finger curling along can't switch the gesture halfway through.
    """

    def __init__(self, on_mm: float, off_mm: float, confirm_s: float = 0.03):
        if on_mm >= off_mm:
            raise ValueError("pinch on distance must be smaller than off distance")
        self.on, self.off, self.confirm_s = on_mm, off_mm, confirm_s
        self.kind: Optional[str] = None
        self._candidate_since: Optional[float] = None

    def update(self, thumb_index: float, thumb_middle: float, t: float) -> PinchEvent:
        if self.kind is not None:
            d = thumb_index if self.kind == "index" else thumb_middle
            if d > self.off:
                kind, self.kind = self.kind, None
                return ("end", kind)
            return None
        if min(thumb_index, thumb_middle) < self.on:
            if self._candidate_since is None:
                self._candidate_since = t
            if t - self._candidate_since >= self.confirm_s:
                self.kind = "index" if thumb_index <= thumb_middle else "middle"
                self._candidate_since = None
                return ("start", self.kind)
        else:
            self._candidate_since = None
        return None

    def reset(self) -> None:
        self.kind = self._candidate_since = None
