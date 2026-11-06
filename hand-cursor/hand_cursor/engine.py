"""Turns tracked hand frames into mouse actions.

Two states:
  idle     mouse mode is off.
  engaged  the hand moves the cursor; pinches click, drag, select and scroll.

To engage, open the hand, then pinch thumb and index and hold for `engage_hold_s` (with
the hand raised, if the calibration found a clear height difference between typing and
mouse positions). The open-then-pinch requirement matters: a resting or half-visible hand
can read as "pinched" without anyone pinching. The engaging pinch never clicks. Mouse mode ends when you type, when the hand leaves the tracker's
view, or when you lower it to the keyboard (again, only if height is usable).
"""
from __future__ import annotations

import math
import statistics
import threading
from collections import deque
from dataclasses import dataclass
from typing import Callable, Optional, Protocol, Sequence, Tuple

from .config import Calibration, Settings
from .filters import OneEuroFilter
from .frames import Frame, Hand
from .geometry import dist, dot
from .gestures import Hysteresis, PinchTracker
from .pointer import PointerGain

IDLE = "idle"
ENGAGED = "engaged"
REACQUIRE_GAP_S = 0.1  # after a gap this long, the next frame is a fresh start, not motion
GLITCH_FRAMES = 3  # a palm jump must persist this many frames before it is believed
PINCH_MEDIAN_FRAMES = 3
HISTORY_S = 0.5

Point = Tuple[float, float]


class Mouse(Protocol):
    def position(self) -> Point: ...
    def clamp(self, x: float, y: float, prev: Point) -> Point: ...
    def move(self, x: float, y: float, button: Optional[str] = None, clicks: int = 1) -> None: ...
    def down(self, button: str, x: float, y: float, clicks: int = 1) -> None: ...
    def up(self, button: str, x: float, y: float, clicks: int = 1) -> None: ...
    def scroll(self, dx: int, dy: int) -> None: ...


@dataclass
class _Press:
    t: float
    pos: Point
    clicks: int
    slop: Point = (0.0, 0.0)
    dragging: bool = False


@dataclass
class _Scroll:
    t: float
    anchor: Point
    max_offset: float = 0.0
    remainder: Point = (0.0, 0.0)


class Engine:
    def __init__(self, settings: Settings, calibration: Calibration, mouse: Mouse,
                 last_key_time: Callable[[], float] = lambda: -math.inf,
                 on_state: Optional[Callable[[str], None]] = None):
        self.s = settings
        self.c = calibration
        self.mouse = mouse
        self._last_key_time = last_key_time
        self._on_state = on_state or (lambda state: None)
        self._lock = threading.Lock()

        self._filter = OneEuroFilter(settings.filter_min_cutoff, settings.filter_beta,
                                     settings.filter_d_cutoff)
        self._pinch = PinchTracker(*calibration.pinch_thresholds(settings), settings.pinch_confirm_s)
        raise_levels = calibration.raise_thresholds(settings)
        self._raised = Hysteresis(*raise_levels) if raise_levels else None
        self._gain = PointerGain(settings)

        self.state = IDLE
        self.cursor: Point = (0.0, 0.0)
        self.status: dict = {"hand": False, "state": IDLE}
        self._history: deque = deque()  # (t, x, y) of recent cursor positions
        self._press: Optional[_Press] = None
        self._scroll: Optional[_Scroll] = None
        self._last_click: Optional[Tuple[float, Point, int]] = None
        self._swallow = False  # the engaging pinch must be released before anything clicks
        self._arm_since: Optional[float] = None
        self._arm_gap_since: Optional[float] = None
        self._lowered_since: Optional[float] = None
        self._pinch_samples: deque = deque(maxlen=PINCH_MEDIAN_FRAMES)
        self._visible_since = 0.0  # tracked continuously since
        self._open_since: Optional[float] = None  # hand seen not pinching since
        self._pinch_from_open = False  # the current pinch started from a visibly open hand
        self._last_seen: Optional[float] = None
        self._last_palm = None
        self._glitches = 0
        self._prev_plane: Optional[Point] = None
        self._prev_t = 0.0
        self._freeze_until = -math.inf
        self._still_frames = 0

    # ----- public -----

    def process(self, frame: Frame) -> None:
        with self._lock:
            self._process(frame)

    def shutdown(self) -> None:
        """Release anything held, so a button is never left stuck down."""
        with self._lock:
            self._end_actions()

    # ----- per frame -----

    def _process(self, frame: Frame) -> None:
        t = frame.t
        hand = self._select(frame.hands)
        if hand is None:
            self.status = {"hand": False, "state": self.state}
            if self._last_seen is not None and t - self._last_seen > self.s.lost_grace_s:
                self._hand_lost()
            return

        fresh = self._last_seen is None or t - self._last_seen > REACQUIRE_GAP_S
        if not fresh and dist(hand.palm, self._last_palm) > self.s.max_step_mm:
            self._glitches += 1
            if self._glitches < GLITCH_FRAMES:
                return  # an isolated tracking outlier: skip it before it reaches the filter
            fresh = True  # the hand really is somewhere else now
        self._glitches = 0
        if fresh:  # start over here, so the jump doesn't turn into cursor motion
            self._filter.reset()
            self._prev_plane = None
            self._pinch_samples.clear()
            self._visible_since, self._open_since = t, None
        self._last_seen = t
        self._last_palm = hand.palm

        palm = self._filter(hand.palm, t)
        plane = (dot(palm, self.c.right_axis), dot(palm, self.c.up_axis))
        lift = dot(palm, self.c.lift_axis) if self._raised else None
        raised = self._raised.update(lift) if self._raised else True
        # A 3-frame median (~25 ms) removes single-frame fingertip spikes that would
        # otherwise end a pinch, or start one, by accident.
        self._pinch_samples.append((hand.thumb_index, hand.thumb_middle))
        thumb_index = statistics.median(s[0] for s in self._pinch_samples)
        thumb_middle = statistics.median(s[1] for s in self._pinch_samples)
        event = self._pinch.update(thumb_index, thumb_middle, t)
        if self._pinch.kind is None:
            if self._open_since is None:
                self._open_since = t
            self._pinch_from_open = False
        elif event and event[0] == "start":
            opened_for = t - self._open_since if self._open_since is not None else 0.0
            # A flicker in the middle of the engage hold keeps counting as the same pinch.
            self._pinch_from_open = opened_for >= self.s.engage_open_s or self._arm_since is not None
            self._open_since = None
        typing = t - self._last_key_time() < self.s.typing_cooldown_s

        delta = None
        if self._prev_plane is not None and t > self._prev_t:
            delta = (plane[0] - self._prev_plane[0], plane[1] - self._prev_plane[1], t - self._prev_t)
        self._prev_plane, self._prev_t = plane, t

        if self.state == IDLE:
            self._idle_step(t, raised, typing)
        else:
            self._engaged_step(t, raised, typing, event, plane, delta)

        arming = self.state == IDLE and self._arm_since is not None
        self.status = {
            "hand": True, "state": self.state, "side": hand.side, "palm": hand.palm,
            "lift": lift, "raised": raised, "height_used": self._raised is not None,
            "steady": t - self._visible_since >= self.s.engage_visible_s,
            "thumb_index": thumb_index, "thumb_middle": thumb_middle,
            "pinch": self._pinch.kind, "pinch_from_open": self._pinch_from_open, "typing": typing,
            "arm": min(1.0, (t - self._arm_since) / self.s.engage_hold_s) if arming else 0.0,
            "dragging": bool(self._press and self._press.dragging),
            "scrolling": self._scroll is not None,
        }

    def _select(self, hands: Sequence[Hand]) -> Optional[Hand]:
        wanted = [h for h in hands if self.s.hand == "any" or h.side == self.s.hand]
        if not wanted:
            return None
        if len(wanted) == 1 or self._last_palm is None:
            return max(wanted, key=lambda h: h.confidence)
        return min(wanted, key=lambda h: dist(h.palm, self._last_palm))

    def _idle_step(self, t: float, raised: bool, typing: bool) -> None:
        steady = t - self._visible_since >= self.s.engage_visible_s
        if typing:
            self._arm_since = self._arm_gap_since = None
        elif raised and steady and self._pinch.kind == "index" and self._pinch_from_open:
            self._arm_gap_since = None
            if self._arm_since is None:
                self._arm_since = t  # the hold counts from when you're both raised and pinching
            if t - self._arm_since >= self.s.engage_hold_s:
                self._engage(t)
        elif self._arm_since is not None:
            # Tolerate a brief flicker of the pinch or height reading during the hold.
            if self._arm_gap_since is None:
                self._arm_gap_since = t
            if t - self._arm_gap_since > self.s.engage_gap_s:
                self._arm_since = self._arm_gap_since = None

    def _engaged_step(self, t, raised, typing, event, plane, delta) -> None:
        if not raised:
            if self._lowered_since is None:
                self._lowered_since = t
            if t - self._lowered_since >= self.s.lower_grace_s:
                self._disengage()
                return
        else:
            self._lowered_since = None

        if event and event[0] == "end" and self._swallow:
            self._swallow, event = False, None
        if typing:
            if self.s.typing_turns_off:
                self._disengage()
            else:
                self._end_actions()  # just pause until typing stops
            return

        if event and not self._swallow:
            kind_of_event, finger = event
            if kind_of_event == "start" and self._press is None and self._scroll is None:
                if finger == "index":
                    self._start_press(t)
                else:
                    self._scroll = _Scroll(t, plane)
            elif kind_of_event == "end":
                if finger == "index" and self._press:
                    self._end_press(t)
                elif finger == "middle" and self._scroll:
                    self._end_scroll(t)

        if self._scroll:
            self._scroll_step(plane, delta)
            return
        if delta is None or t < self._freeze_until:
            return

        mdx, mdy = self._gain(*delta)
        press = self._press
        if press and not press.dragging:
            press.slop = (press.slop[0] + mdx, press.slop[1] + mdy)
            if math.hypot(*press.slop) > self.s.drag_slop_px:
                press.dragging = True
            return
        self._move_by(t, mdx, mdy)

    # ----- state changes -----

    def _engage(self, t: float) -> None:
        self.state = ENGAGED
        self._arm_since = self._arm_gap_since = self._lowered_since = None
        self._swallow = True
        self.cursor = self.mouse.position()
        self._history.clear()
        self._remember(t)
        self._on_state(ENGAGED)

    def _disengage(self) -> None:
        self._end_actions()
        self.state = IDLE
        self._swallow = False
        self._arm_since = self._arm_gap_since = self._lowered_since = None
        self._on_state(IDLE)

    def _hand_lost(self) -> None:
        if self.state == ENGAGED:
            self._disengage()
        self._pinch.reset()
        self._filter.reset()
        self._pinch_samples.clear()
        self._arm_since = self._arm_gap_since = None
        self._last_seen = None
        self._prev_plane = None

    def _end_actions(self) -> None:
        """Release a held button where the cursor is, and cancel any scroll."""
        if self._press:
            x, y = self.cursor
            self.mouse.up("left", x, y, self._press.clicks)
            self._press = None
        self._scroll = None

    # ----- cursor -----

    def _move_by(self, t: float, mdx: float, mdy: float) -> None:
        x, y = self.cursor
        nx, ny = self.mouse.clamp(x + mdx, y + mdy, (x, y))
        if abs(nx - x) < 0.01 and abs(ny - y) < 0.01:
            self._still_frames += 1
            if self._press is None and self._still_frames == 2:
                self._adopt_os_cursor(t)
            return
        self._still_frames = 0
        self.cursor = (nx, ny)
        if self._press:
            self.mouse.move(nx, ny, "left", self._press.clicks)
        else:
            self.mouse.move(nx, ny)
        self._remember(t)

    def _adopt_os_cursor(self, t: float) -> None:
        """If you moved the real mouse or trackpad, continue from where it left the cursor."""
        ox, oy = self.mouse.position()
        if math.hypot(ox - self.cursor[0], oy - self.cursor[1]) > 3.0:
            self.cursor = (ox, oy)
            self._history.clear()
            self._remember(t)

    def _remember(self, t: float) -> None:
        self._history.append((t, self.cursor[0], self.cursor[1]))
        while len(self._history) > 1 and self._history[0][0] < t - HISTORY_S:
            self._history.popleft()

    def _position_at(self, t: float) -> Point:
        """Cursor position at time t, so a click lands where you were pointing before the
        pinch itself nudged the hand."""
        pos = self.cursor
        for ht, hx, hy in reversed(self._history):
            pos = (hx, hy)
            if ht <= t:
                break
        return pos

    # ----- click and drag -----

    def _start_press(self, t: float) -> None:
        pos = self._position_at(t - self.s.rewind_press_s)
        clicks = 1
        last = self._last_click
        if (last and t - last[0] <= self.s.double_click_s
                and math.hypot(pos[0] - last[1][0], pos[1] - last[1][1]) <= self.s.double_click_px):
            clicks = last[2] + 1
        if pos != self.cursor:
            self.mouse.move(*pos)
        self.cursor = pos
        self.mouse.down("left", pos[0], pos[1], clicks)
        self._press = _Press(t, pos, clicks)
        self._last_click = (t, pos, clicks)
        self._remember(t)

    def _end_press(self, t: float) -> None:
        press, self._press = self._press, None
        if press.dragging:
            pos = self._position_at(t - self.s.rewind_release_s)
            if pos != self.cursor:
                self.mouse.move(pos[0], pos[1], "left", press.clicks)
            self._last_click = None
        else:
            pos = press.pos
        self.cursor = pos
        self.mouse.up("left", pos[0], pos[1], press.clicks)
        self._freeze_until = t + self.s.release_freeze_s
        self._remember(t)

    # ----- scroll and right click -----

    def _scroll_rate(self, offset_mm: float) -> float:
        excess = abs(offset_mm) - self.s.scroll_dead_mm
        if excess <= 0:
            return 0.0
        return math.copysign(min(self.s.scroll_max, self.s.scroll_gain * excess ** self.s.scroll_power),
                             offset_mm)

    def _scroll_step(self, plane: Point, delta) -> None:
        sc = self._scroll
        ox, oy = plane[0] - sc.anchor[0], plane[1] - sc.anchor[1]
        sc.max_offset = max(sc.max_offset, math.hypot(ox, oy))
        if delta is None:
            return
        if not self.s.scroll_horizontal:
            ox = 0.0
        elif abs(ox) > abs(oy):
            oy = 0.0  # lock to the dominant direction
        else:
            ox = 0.0
        sign = -1.0 if self.s.scroll_invert else 1.0
        dt = delta[2]
        fx = sc.remainder[0] + sign * self._scroll_rate(ox) * dt
        fy = sc.remainder[1] + sign * self._scroll_rate(oy) * dt
        ix, iy = int(fx), int(fy)
        sc.remainder = (fx - ix, fy - iy)
        if ix or iy:
            self.mouse.scroll(ix, iy)

    def _end_scroll(self, t: float) -> None:
        sc, self._scroll = self._scroll, None
        if t - sc.t <= self.s.tap_max_s and sc.max_offset < self.s.scroll_dead_mm:
            x, y = self.cursor
            self.mouse.down("right", x, y, 1)
            self.mouse.up("right", x, y, 1)
        self._freeze_until = t + self.s.release_freeze_s
