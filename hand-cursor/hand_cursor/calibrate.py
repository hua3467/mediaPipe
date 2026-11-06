"""Interactive calibration: learns how the tracker is mounted relative to you.

Instead of assuming an orientation, it asks you to make a few movements and measures
them. That works the same for a tracker on the desk, above the desk, or on a monitor:
  1. use the tracker's current mode (as set in Ultraleap Control Panel), or optionally
     test every mode and keep the one that sees your hand best
  2. palm height while typing, and in your mouse position
  3. thumb-index distance, open and pinched
  4. which direction is "right" and which is "up" for the cursor
"""
from __future__ import annotations

import math
import threading
import time
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from .config import Calibration, Settings
from .frames import Frame, Hand
from .geometry import Vec3, dist, dot, mean, median, norm, reject, sub, unit
from .leap_source import MODES, mode_label

MIN_MOVE_MM = 30.0
MIN_PINCH_RANGE_MM = 25.0  # a relaxed open hand is usually 50 mm or more from a pinch
MIN_VISIBLE = 0.5
ATTEMPTS = 3

Log = Callable[[str], None]


class FrameBuffer:
    """Collects frames from the tracking thread while a calibration step records."""

    def __init__(self):
        self._lock = threading.Lock()
        self._frames: Optional[List[Frame]] = None

    def __call__(self, frame: Frame) -> None:
        with self._lock:
            if self._frames is not None:
                self._frames.append(frame)

    def record(self, seconds: float) -> List[Frame]:
        with self._lock:
            self._frames = []
        time.sleep(seconds)
        with self._lock:
            frames, self._frames = self._frames, None
        return frames


# ----- measurement helpers (pure, unit tested) -----

def hand_samples(frames: Sequence[Frame], side: str) -> List[Tuple[float, Hand]]:
    out = []
    for f in frames:
        for h in f.hands:
            if side == "any" or h.side == side:
                out.append((f.t, h))
                break
    return out


def visible_fraction(frames: Sequence[Frame], side: str) -> float:
    return len(hand_samples(frames, side)) / len(frames) if frames else 0.0


def motion_axis(samples: Sequence[Tuple[float, Vec3]], edge_s: float = 0.4) -> Tuple[Vec3, float]:
    """Direction and distance from where a movement started to where it came to rest."""
    if len(samples) < 2:
        return (0.0, 0.0, 0.0), 0.0
    t0, t1 = samples[0][0], samples[-1][0]
    start = mean(p for t, p in samples if t <= t0 + edge_s)
    end = mean(p for t, p in samples if t >= t1 - edge_s)
    v = sub(end, start)
    d = norm(v)
    return (unit(v) if d > 1e-6 else (0.0, 0.0, 0.0)), d


def mode_score(frames: Sequence[Frame], side: str) -> Tuple[float, float]:
    """(fraction of frames where the hand was seen, palm jitter in mm) while held still."""
    samples = hand_samples(frames, side)
    rate = len(samples) / len(frames) if frames else 0.0
    if len(samples) < 5:
        return rate, math.inf
    palms = [h.palm for _, h in samples]
    centre = mean(palms)
    jitter = math.sqrt(sum(dist(p, centre) ** 2 for p in palms) / len(palms))
    return rate, jitter


def best_mode(scores: Dict[str, Tuple[float, float]]) -> str:
    """Prefer the mode that sees the hand most often; break near-ties by steadiness."""
    return max(scores, key=lambda m: (round(scores[m][0] * 20), -scores[m][1]))


def _round(v: Vec3) -> Vec3:
    return tuple(round(c, 4) for c in v)  # type: ignore[return-value]


# ----- interactive steps -----

class _Steps:
    def __init__(self, source, buffer, side: str, log: Log, ask: Callable[[str], str],
                 sleep: Callable[[float], None]):
        self.source, self.buffer, self.side = source, buffer, side
        self.log, self.ask, self.sleep = log, ask, sleep

    def prompt(self, text: str) -> None:
        self.log("")
        self.log(text)
        self.ask("  Press Enter, then get into position... ")
        for i in (3, 2, 1):
            self.log(f"  {i}")
            self.sleep(1.0)

    def record(self, seconds: float, go: str = "  Recording, hold still...") -> List[Tuple[float, Hand]]:
        self.log(go)
        return hand_samples(self.buffer.record(seconds), self.side)

    def choose_mode(self, modes: Sequence[str]) -> str:
        self.prompt(f"Step 1/6: Raise your {self.side} hand into the position where you'd use it as a "
                    "mouse:\n  elbow resting, hand relaxed above the desk, fingers apart. "
                    "Hold it there for about 10 seconds\n  while each tracking mode is tested.")
        scores = {}
        for mode in modes:
            self.source.set_mode(mode)
            self.sleep(1.0)  # give the tracker a moment to switch
            scores[mode] = mode_score(self.buffer.record(2.0), self.side)
            rate, jitter = scores[mode]
            steadiness = "-" if math.isinf(jitter) else f"{jitter:.1f} mm"
            self.log(f"  {mode_label(mode):13s} hand seen in {rate:4.0%} of frames, jitter {steadiness}")
        mode = best_mode(scores)
        self.source.set_mode(mode)
        self.log(f"  Using {mode_label(mode)} mode. If another mode looked better in Ultraleap Control "
                 "Panel, set it there and calibrate again without --test-modes.")
        if scores[mode][0] < MIN_VISIBLE:
            self.log("  Warning: tracking is weak in every mode. Check that the tracker can see your "
                     "hand, and that no shiny surface or sunlight is in its view.")
        return mode

    def keyboard(self) -> Optional[Vec3]:
        self.prompt("Step 2/6: Put both hands on the keyboard as if typing, and keep them there.")
        self.log("  Recording, hold still...")
        frames = self.buffer.record(2.5)
        if visible_fraction(frames, self.side) < MIN_VISIBLE:
            self.log(f"  Your {self.side} hand isn't visible while typing. That's fine: mouse mode "
                     "turns on only when the tracker sees your raised hand.")
            return None
        return median([h.palm for _, h in hand_samples(frames, self.side)])

    def raised(self) -> Tuple[Vec3, float]:
        for _ in range(ATTEMPTS):
            self.prompt(f"Step 3/6: Raise your {self.side} hand to your mouse position. Relax it, "
                        "with your thumb and index finger clearly apart (not pinching).")
            samples = self.record(2.5)
            if len(samples) >= 10:
                return median([h.palm for _, h in samples]), median_float(h.thumb_index for _, h in samples)
            self.log("  Couldn't see your hand. Let's try again.")
        raise RuntimeError("calibration failed: the hand was not visible in the mouse position")

    def pinch(self, open_mm: float) -> Optional[float]:
        """Returns the pinched distance, or None if it is too close to the open hand, in
        which case the open hand (step 3) needs measuring again."""
        for _ in range(ATTEMPTS):
            self.prompt("Step 4/6: Same position, now pinch your thumb and index fingertips together "
                        "and hold the pinch.")
            samples = self.record(2.0)
            if len(samples) < 10:
                self.log("  Couldn't see your hand. Let's try again.")
                continue
            closed = median_float(h.thumb_index for _, h in samples)
            if open_mm - closed >= MIN_PINCH_RANGE_MM:
                return closed
            self.log(f"  The pinch ({closed:.0f} mm) is too close to your open hand ({open_mm:.0f} mm) "
                     "to tell them apart reliably. Let's measure the open hand again: this time "
                     "spread your thumb and index finger further apart.")
            return None
        raise RuntimeError("calibration failed: the hand was not visible while pinching")

    def direction(self, step: str, what: str, avoid: Optional[Vec3] = None) -> Vec3:
        for _ in range(ATTEMPTS):
            self.prompt(f"{step}: From your mouse position, when you see GO, move your hand about "
                        f"10 cm {what},\n  then hold it still until recording ends.")
            samples = self.record(3.0, go="  GO")
            axis, distance = motion_axis([(t, h.palm) for t, h in samples])
            if distance < MIN_MOVE_MM:
                self.log(f"  Only {distance:.0f} mm of movement was seen. Move a bit further.")
                continue
            if avoid is not None:
                perpendicular = reject(axis, avoid)
                if norm(perpendicular) < 0.5:
                    self.log("  That was almost the same direction as before. Try again.")
                    continue
                axis = unit(perpendicular)
            return axis
        raise RuntimeError(f"calibration failed: could not measure the {what} direction")


def median_float(values) -> float:
    vs = sorted(values)
    n = len(vs)
    return vs[n // 2] if n % 2 else (vs[n // 2 - 1] + vs[n // 2]) / 2


def run_calibration(source, buffer, settings: Settings, log: Log = print,
                    ask: Callable[[str], str] = input, sleep: Callable[[float], None] = time.sleep,
                    fixed_mode: Optional[str] = None, test_modes: bool = False,
                    modes: Sequence[str] = MODES) -> Calibration:
    side = settings.hand if settings.hand != "any" else "right"
    steps = _Steps(source, buffer, side, log, ask, sleep)
    log("Calibration takes about a minute. Each step tells you where to put your hand,\n"
        "waits for Enter, counts down, then records for a few seconds.")

    if fixed_mode:
        source.set_mode(fixed_mode)
        mode = fixed_mode
        log(f"\nStep 1/6: Using {mode_label(mode)} mode (given on the command line).")
    elif test_modes or getattr(source, "mode", None) is None:
        mode = steps.choose_mode(modes)
    else:
        mode = source.mode
        log(f"\nStep 1/6: Using the tracker's current mode, {mode_label(mode)} (as set in Ultraleap "
            "Control Panel).\n  To compare all modes instead, run calibrate with --test-modes.")

    keyboard = steps.keyboard()
    for _ in range(ATTEMPTS):
        raised, open_mm = steps.raised()
        closed_mm = steps.pinch(open_mm)
        if closed_mm is not None:
            break
    else:
        raise RuntimeError("calibration failed: could not tell a pinch from an open hand. Check in "
                           "`python -m hand_cursor view` that the tracker sees your fingers clearly.")
    right = steps.direction("Step 5/6", "to the RIGHT")
    up = steps.direction("Step 6/6", "in the direction that should move the cursor UP the screen\n"
                         "  (for example forward, away from you)", avoid=right)

    lift_axis = keyboard_level = raised_level = None
    if keyboard is not None and norm(sub(raised, keyboard)) > 1.0:
        lift_axis = unit(sub(raised, keyboard))
        keyboard_level, raised_level = dot(keyboard, lift_axis), dot(raised, lift_axis)

    calibration = Calibration(
        tracking_mode=mode,
        right_axis=_round(right),
        up_axis=_round(up),
        lift_axis=_round(lift_axis) if lift_axis else None,
        keyboard_level=round(keyboard_level, 1) if keyboard_level is not None else None,
        raised_level=round(raised_level, 1) if raised_level is not None else None,
        mouse_position=tuple(round(c, 1) for c in raised),
        pinch_closed_mm=round(closed_mm, 1),
        pinch_open_mm=round(open_mm, 1),
    )
    on, off = calibration.pinch_thresholds(settings)
    log(f"\nPinch registers below {on:.0f} mm and releases above {off:.0f} mm "
        f"(yours: {closed_mm:.0f} mm pinched, {open_mm:.0f} mm open).")
    problem = calibration.height_problem()
    if problem:
        log(f"Hand height won't be used, because {problem}. That's fine: mouse mode turns on with a "
            "held pinch,\nand off when you type or move your hand out of the tracker's view.")
    else:
        log("Hand height is used too: mouse mode only turns on with your hand raised, and turns off "
            "when you lower it\nto the keyboard, type, or move it out of view.")
    return calibration
