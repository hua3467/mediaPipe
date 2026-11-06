"""Mouse output: real macOS events through Quartz, or a simulated mouse for dry runs."""
from __future__ import annotations

import math
import time
from typing import Callable, List, Optional, Tuple

from .pointer import Rect, clamp_to_displays

Point = Tuple[float, float]
DISPLAY_REFRESH_S = 2.0


class QuartzMouse:
    """Posts real mouse events. macOS only delivers them if the app running Python
    (Terminal, VS Code, ...) has Accessibility permission."""

    def __init__(self):
        import Quartz

        self.Q = Quartz
        self._buttons = {
            "left": (Quartz.kCGEventLeftMouseDown, Quartz.kCGEventLeftMouseUp,
                     Quartz.kCGEventLeftMouseDragged, Quartz.kCGMouseButtonLeft),
            "right": (Quartz.kCGEventRightMouseDown, Quartz.kCGEventRightMouseUp,
                      Quartz.kCGEventRightMouseDragged, Quartz.kCGMouseButtonRight),
        }
        self._displays: List[Rect] = []
        self._displays_at = -math.inf

    @staticmethod
    def has_permission(request: bool = False) -> bool:
        import Quartz

        if Quartz.CGPreflightPostEventAccess():
            return True
        if request:
            Quartz.CGRequestPostEventAccess()  # shows the system prompt once
        return False

    def position(self) -> Point:
        loc = self.Q.CGEventGetLocation(self.Q.CGEventCreate(None))
        return (loc.x, loc.y)

    def displays(self) -> List[Rect]:
        now = time.monotonic()
        if now - self._displays_at > DISPLAY_REFRESH_S:  # monitors can be plugged in or out
            err, ids, count = self.Q.CGGetActiveDisplayList(16, None, None)
            if err == 0:
                rects = [self.Q.CGDisplayBounds(i) for i in ids[:count]]
                self._displays = [(r.origin.x, r.origin.y, r.size.width, r.size.height) for r in rects]
            self._displays_at = now
        return self._displays

    def clamp(self, x: float, y: float, prev: Point) -> Point:
        return clamp_to_displays(x, y, self.displays(), prev)

    def _post(self, event_type: int, x: float, y: float, button: int, clicks: int) -> None:
        Q = self.Q
        ev = Q.CGEventCreateMouseEvent(None, event_type, (x, y), button)
        Q.CGEventSetIntegerValueField(ev, Q.kCGMouseEventClickState, clicks)
        Q.CGEventPost(Q.kCGHIDEventTap, ev)

    def move(self, x: float, y: float, button: Optional[str] = None, clicks: int = 1) -> None:
        if button is None:
            self._post(self.Q.kCGEventMouseMoved, x, y, self.Q.kCGMouseButtonLeft, 0)
        else:
            _, _, dragged, b = self._buttons[button]
            self._post(dragged, x, y, b, clicks)

    def down(self, button: str, x: float, y: float, clicks: int = 1) -> None:
        down, _, _, b = self._buttons[button]
        self._post(down, x, y, b, clicks)

    def up(self, button: str, x: float, y: float, clicks: int = 1) -> None:
        _, up, _, b = self._buttons[button]
        self._post(up, x, y, b, clicks)

    def scroll(self, dx: int, dy: int) -> None:
        """Positive dy scrolls the view up; positive dx scrolls it right."""
        Q = self.Q
        ev = Q.CGEventCreateScrollWheelEvent(None, Q.kCGScrollEventUnitPixel, 2, int(dy), int(-dx))
        Q.CGEventPost(Q.kCGHIDEventTap, ev)


class DryRunMouse:
    """A simulated mouse that prints what it would do. Nothing is sent to macOS."""

    def __init__(self, log: Callable[[str], None] = print, size: Tuple[int, int] = (1920, 1080),
                 show_moves: bool = False):
        self.log = log
        self.show_moves = show_moves
        self.pos: Point = (size[0] / 2, size[1] / 2)
        self._displays: List[Rect] = [(0.0, 0.0, float(size[0]), float(size[1]))]
        self._scrolled = [0, 0]
        self._scroll_logged_at = 0.0
        self.counts = {"down": 0, "up": 0, "scroll": 0}

    def position(self) -> Point:
        return self.pos

    def clamp(self, x: float, y: float, prev: Point) -> Point:
        return clamp_to_displays(x, y, self._displays, prev)

    def move(self, x: float, y: float, button: Optional[str] = None, clicks: int = 1) -> None:
        self.pos = (x, y)
        if self.show_moves:
            self.log(f"{'drag' if button else 'move'} ({x:.0f}, {y:.0f})")

    def down(self, button: str, x: float, y: float, clicks: int = 1) -> None:
        self._flush_scroll()
        self.pos = (x, y)
        self.counts["down"] += 1
        self.log(f"{button} down at ({x:.0f}, {y:.0f})" + (f"  [click {clicks}]" if clicks > 1 else ""))

    def up(self, button: str, x: float, y: float, clicks: int = 1) -> None:
        self.pos = (x, y)
        self.counts["up"] += 1
        self.log(f"{button} up   at ({x:.0f}, {y:.0f})")

    def scroll(self, dx: int, dy: int) -> None:
        self.counts["scroll"] += 1
        self._scrolled[0] += dx
        self._scrolled[1] += dy
        if time.monotonic() - self._scroll_logged_at > 0.25:
            self._flush_scroll()

    def _flush_scroll(self) -> None:
        if any(self._scrolled):
            self.log(f"scroll {self._scrolled[1]:+d} px vertical, {self._scrolled[0]:+d} px horizontal")
            self._scrolled = [0, 0]
        self._scroll_logged_at = time.monotonic()
