"""The commands: calibrate, run, monitor, replay, settings."""
from __future__ import annotations

import math
import sys
import threading
import time
from typing import Optional

from .calibrate import FrameBuffer, run_calibration
from .config import (CALIBRATION_PATH, Calibration, Settings, load_calibration, load_settings,
                     save_calibration, settings_json)
from .engine import ENGAGED, Engine
from .feedback import Feedback
from .frames import Frame, Recorder, read_recording
from .keyboard import KeyMonitor
from .leap_source import LeapSource, mode_label
from .mouse import DryRunMouse, QuartzMouse

ACCESSIBILITY_HELP = """\
macOS hasn't allowed this app to control the mouse yet.
  Open System Settings > Privacy & Security > Accessibility and turn on the app you're
  running this from (Terminal, iTerm or Visual Studio Code). Then quit and reopen that
  app and try again. To test without controlling the mouse, add --dry-run."""

INPUT_MONITORING_HELP = """\
Note: typing detection is off because macOS hasn't allowed this app to see key presses.
  Mouse mode still turns off when you lower your hand. To also pause it whenever you
  type, open System Settings > Privacy & Security > Input Monitoring, turn on the app
  you're running this from, then quit and reopen it."""


def ready_text(s: Settings, c: Calibration, typing_detected: bool) -> str:
    height = c.raise_thresholds(s) is not None
    turn_on = f"raise your {s.hand} hand, open it, then" if height else f"open your {s.hand} hand, then"
    turn_off = (["type"] if typing_detected and s.typing_turns_off else []) + \
               (["lower your hand to the keyboard"] if height else []) + ["move your hand out of view"]
    turn_off_text = ", ".join(turn_off[:-1]) + (" or " if len(turn_off) > 1 else "") + turn_off[-1]
    return f"""\
Ready. To turn mouse mode on, {turn_on} pinch thumb and index and hold for a moment (tink).
To turn it off, {turn_off_text} (pop).
  pinch                       click (twice quickly: double-click)
  pinch, hold and move        drag / select text
  thumb-middle pinch + move   scroll, like a joystick: move further to scroll faster
  thumb-middle tap            right click
Press Ctrl+C to quit."""


def mode_mismatch_text(calibrated: str, current: str) -> str:
    return f"""\
Your calibration was made in {mode_label(calibrated)} mode, but the tracker is now in
{mode_label(current)} mode (as set in Ultraleap Control Panel). Hands are tracked differently in
each mode, so calibrate again in the current mode:
  python -m hand_cursor calibrate
Or, to switch the tracker back to {mode_label(calibrated)} for this run, add --mode {calibrated}."""


def _calibration(settings: Settings, mode: Optional[str]) -> Calibration:
    calibration = load_calibration()
    if calibration is None:
        print("No calibration found yet, so let's calibrate first.\n")
        calibration = _calibrate(settings, mode)
    return calibration


def _calibrate(settings: Settings, mode: Optional[str], test_modes: bool = False) -> Calibration:
    """Calibrates in `mode`, or in the tracker's current mode when mode is None."""
    buffer = FrameBuffer()
    with LeapSource(buffer, mode) as source:
        calibration = run_calibration(source, buffer, settings, fixed_mode=mode, test_modes=test_modes)
    save_calibration(calibration)
    print(f"\nSaved to {CALIBRATION_PATH}")
    return calibration


def cmd_calibrate(args) -> int:
    _calibrate(load_settings(), args.mode, args.test_modes)
    print("Next: `python -m hand_cursor view` or `monitor` to check tracking, then `python -m hand_cursor run`.")
    return 0


def _wire(engine: Engine, recorder: Optional[Recorder], gate: threading.Event):
    def on_frame(frame: Frame) -> None:
        if not gate.is_set():  # nothing reaches the mouse until the mode check has passed
            return
        if recorder:
            recorder.frame(frame)
        engine.process(frame)
    return on_frame


def _live(args, mouse, monitor: bool) -> int:
    settings = load_settings()
    calibration = _calibration(settings, args.mode)
    recorder = Recorder(args.record) if args.record else None
    keys = KeyMonitor(on_key=recorder.key if recorder else None)
    if not keys.start():
        print(INPUT_MONITORING_HELP + "\n")
    log = _status_safe_print if monitor else print
    engine = Engine(settings, calibration, mouse, keys, Feedback(settings.sounds, log))
    if isinstance(mouse, DryRunMouse):
        mouse.log = log
    gate = threading.Event()
    try:
        # Only switch the tracker's mode when asked to (--mode): it is shared with Ultraleap
        # Control Panel, so changing it behind your back would undo your choice there.
        with LeapSource(_wire(engine, recorder, gate), args.mode, log=log) as source:
            if source.mode is not None and source.mode != calibration.tracking_mode:
                if not args.mode:
                    print(mode_mismatch_text(calibration.tracking_mode, source.mode))
                    return 1
                print(f"Note: you calibrated in {mode_label(calibration.tracking_mode)} mode but asked for "
                      f"{mode_label(source.mode)}. If tracking feels off, calibrate in this mode.")
            gate.set()
            print(f"Tracking mode: {mode_label(source.mode)}." + (" Dry run: the real mouse is not touched."
                                                                if isinstance(mouse, DryRunMouse) else ""))
            print(ready_text(settings, calibration, keys.ok) + "\n")
            while True:  # tracking runs on the bindings' thread; Ctrl+C ends this loop
                if monitor:
                    _print_status(engine, calibration)
                time.sleep(0.1)
    except KeyboardInterrupt:
        pass
    finally:
        engine.shutdown()
        keys.stop()
        if recorder:
            recorder.close()
            print(f"\nRecording saved to {recorder.path}")
    print()
    return 0


def cmd_run(args) -> int:
    if args.dry_run:
        return _live(args, DryRunMouse(), monitor=False)
    if not QuartzMouse.has_permission(request=True):
        print(ACCESSIBILITY_HELP)
        return 1
    return _live(args, QuartzMouse(), monitor=False)


def cmd_monitor(args) -> int:
    return _live(args, DryRunMouse(), monitor=True)


def cmd_replay(args) -> int:
    settings = load_settings()
    calibration = load_calibration()
    if calibration is None:
        print("No calibration.json found; replaying with default (desktop) axes.")
        calibration = Calibration()
    mouse = DryRunMouse(show_moves=args.moves)
    last_key = [-math.inf]
    engine = Engine(settings, calibration, mouse, lambda: last_key[0], Feedback(sounds=False))
    frames = 0
    for item in read_recording(args.file):
        if isinstance(item, float):
            last_key[0] = item
        else:
            engine.process(item)
            frames += 1
    engine.shutdown()
    c = mouse.counts
    print(f"\n{frames} frames: {c['down']} button presses, {c['scroll']} scroll steps.")
    return 0


def cmd_settings(args) -> int:
    print(settings_json(load_settings()))
    return 0


# ----- monitor display -----

def _status_safe_print(message: str) -> None:
    sys.stdout.write("\r\033[K" + message + "\n")
    sys.stdout.flush()


def status_line(status: dict, calibration: Calibration) -> str:
    state = "MOUSE ON" if status.get("state") == ENGAGED else "mouse off"
    if not status.get("hand"):
        return f"no hand seen{'':60s}| {state}"
    x, y, z = status["palm"]
    parts = [f"{status['side']:5s} palm ({x:5.0f},{y:5.0f},{z:5.0f})"]
    lift = status.get("lift")
    if lift is not None and calibration.keyboard_level is not None and calibration.raised_level is not None:
        height = (lift - calibration.keyboard_level) / (calibration.raised_level - calibration.keyboard_level)
        parts.append(f"height {height:4.1f} ({'raised' if status['raised'] else 'lowered'})")
    parts.append(f"thumb-index {status['thumb_index']:3.0f}mm  thumb-middle {status['thumb_middle']:3.0f}mm")
    parts.append(f"pinch {status['pinch'] or '-':6s}")
    if status.get("arm"):
        parts.append(f"hold {status['arm']:4.0%}")
    flags = [name for name in ("typing", "dragging", "scrolling") if status.get(name)]
    return "  ".join(parts) + f" | {state}" + (f" ({', '.join(flags)})" if flags else "")


def _print_status(engine: Engine, calibration: Calibration) -> None:
    sys.stdout.write("\r\033[K" + status_line(engine.status, calibration))
    sys.stdout.flush()
