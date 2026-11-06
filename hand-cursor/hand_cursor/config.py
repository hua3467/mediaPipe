"""Tunable settings and per-setup calibration, both stored as JSON next to the package."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Optional, Tuple

from .geometry import Vec3, dot

PROJECT_DIR = Path(__file__).resolve().parent.parent
SETTINGS_PATH = PROJECT_DIR / "settings.json"
CALIBRATION_PATH = PROJECT_DIR / "calibration.json"
MIN_RAISE_SPAN_MM = 60.0  # mouse position must be at least this far above typing position
MAX_LIFT_OVERLAP = 0.5  # ...and mostly above it, not along the cursor's right/up directions


@dataclass
class Settings:
    """Defaults live here. Override any of them in settings.json (see README)."""

    hand: str = "right"  # "right", "left" or "any"

    # Palm smoothing (One Euro filter, positions in mm).
    filter_min_cutoff: float = 1.0  # Hz. Lower = steadier cursor when the hand rests.
    filter_beta: float = 0.04  # Higher = less lag when the hand moves fast.
    filter_d_cutoff: float = 1.0

    # Pointer acceleration: cursor pixels per mm of hand movement grow with hand speed.
    gain_min: float = 2.5  # px/mm when moving slowly (precision)
    gain_max: float = 20.0  # px/mm when moving fast (reach)
    speed_low: float = 40.0  # mm/s where acceleration starts
    speed_high: float = 350.0  # mm/s where it reaches gain_max
    rest_speed: float = 6.0  # mm/s; slower motion is treated as tremor and ignored
    max_step_mm: float = 60.0  # bigger palm jumps between frames are treated as tracking glitches

    # Pinch detection, as fractions between your calibrated pinched and open distances.
    # Calibration measures a firm pinch; everyday pinches are looser, hence halfway.
    pinch_on_frac: float = 0.5
    pinch_off_frac: float = 0.75
    pinch_confirm_s: float = 0.03

    # Mouse mode on/off.
    engage_hold_s: float = 0.4  # how long to hold the pinch to turn mouse mode on
    engage_gap_s: float = 0.15  # flickers shorter than this don't restart the hold
    # Only a deliberate pinch turns mouse mode on: the hand must be tracked steadily and seen
    # open just before pinching. (Resting or half-visible hands can look "pinched".)
    engage_visible_s: float = 0.3
    engage_open_s: float = 0.15
    typing_turns_off: bool = True  # a key press ends mouse mode (False: only pauses it)
    raise_on_frac: float = 0.5  # how far from keyboard height to raised height counts as raised
    raise_off_frac: float = 0.3
    lower_grace_s: float = 0.25  # hand must stay lowered this long to turn mouse mode off
    lost_grace_s: float = 0.6  # tracking dropouts shorter than this are ignored
    typing_cooldown_s: float = 0.5  # how long after a key press you count as typing

    # Clicking and dragging.
    rewind_press_s: float = 0.08  # click where the cursor was just before the pinch moved it
    rewind_release_s: float = 0.05
    drag_slop_px: float = 10.0  # movement during a pinch below this is still a click
    release_freeze_s: float = 0.12  # ignore the hand jerk as the fingers open
    double_click_s: float = 0.5
    double_click_px: float = 8.0

    # Scrolling (thumb-middle pinch, works like a joystick).
    scroll_dead_mm: float = 10.0
    scroll_gain: float = 8.0
    scroll_power: float = 1.6
    scroll_max: float = 4000.0  # px/s
    scroll_invert: bool = False
    scroll_horizontal: bool = True
    tap_max_s: float = 0.3  # a shorter thumb-middle pinch that doesn't move is a right click

    sounds: bool = True


@dataclass
class Calibration:
    """Describes how the tracker is mounted relative to you. Written by `calibrate`."""

    tracking_mode: str = "desktop"
    right_axis: Vec3 = (1.0, 0.0, 0.0)  # tracker direction that moves the cursor right
    up_axis: Vec3 = (0.0, 0.0, -1.0)  # tracker direction that moves the cursor up
    lift_axis: Optional[Vec3] = None  # direction from typing position to mouse position
    keyboard_level: Optional[float] = None  # palm position along lift_axis while typing
    raised_level: Optional[float] = None  # ... and in the mouse position
    mouse_position: Optional[Vec3] = None  # palm position in the mouse pose (for the viewer)
    pinch_closed_mm: float = 20.0
    pinch_open_mm: float = 70.0

    def pinch_thresholds(self, s: Settings) -> Tuple[float, float]:
        span = self.pinch_open_mm - self.pinch_closed_mm
        return (self.pinch_closed_mm + s.pinch_on_frac * span,
                self.pinch_closed_mm + s.pinch_off_frac * span)

    def height_problem(self) -> Optional[str]:
        """Why hand height can't tell typing from mouse use here, or None if it can.

        Height only works when the mouse position is clearly *above* the typing position.
        If the two are close, or apart mostly sideways or along the direction that moves
        the cursor, ordinary pointing would flip the result."""
        if self.lift_axis is None or self.keyboard_level is None or self.raised_level is None:
            return "your hands weren't visible on the keyboard during calibration"
        span = self.raised_level - self.keyboard_level
        if span < MIN_RAISE_SPAN_MM:
            return f"your mouse position is only {span:.0f} mm from your typing position"
        if max(abs(dot(self.lift_axis, self.right_axis)), abs(dot(self.lift_axis, self.up_axis))) > MAX_LIFT_OVERLAP:
            return "your mouse position is beside your typing position more than above it"
        return None

    def raise_thresholds(self, s: Settings) -> Optional[Tuple[float, float]]:
        if self.height_problem() is not None:
            return None
        span = self.raised_level - self.keyboard_level
        return (self.keyboard_level + s.raise_on_frac * span,
                self.keyboard_level + s.raise_off_frac * span)


def load_settings(path: Path = SETTINGS_PATH) -> Settings:
    if not path.exists():
        return Settings()
    data = json.loads(path.read_text())
    valid = {f.name for f in fields(Settings)}
    unknown = set(data) - valid
    if unknown:
        raise ValueError(f"Unknown setting(s) in {path}: {', '.join(sorted(unknown))}. "
                         f"Valid names: {', '.join(sorted(valid))}")
    return Settings(**data)


def settings_json(s: Settings) -> str:
    return json.dumps(asdict(s), indent=2)


def load_calibration(path: Path = CALIBRATION_PATH) -> Optional[Calibration]:
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    for key in ("right_axis", "up_axis", "lift_axis", "mouse_position"):
        if data.get(key) is not None:
            data[key] = tuple(data[key])
    return Calibration(**data)


def save_calibration(c: Calibration, path: Path = CALIBRATION_PATH) -> None:
    path.write_text(json.dumps(asdict(c), indent=2) + "\n")
