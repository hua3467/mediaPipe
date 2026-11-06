"""Reads hands from an Ultraleap / Leap Motion device through the official `leap` bindings.

Everything Leap-specific lives in this file. The rest of the app only sees Frame/Hand,
so another tracker (for example MediaPipe on a webcam) could be added here later.
"""
from __future__ import annotations

import threading
import time
from contextlib import ExitStack
from typing import Callable, List, Optional

from .frames import Frame, Hand

# The tracker's own tracking mode. It is one setting shared by every app on the Mac,
# including Ultraleap Control Panel, and it persists after the app that set it exits.
MODES = ("desktop", "hmd", "screentop")
MODE_LABELS = {"desktop": "Desktop", "hmd": "Head-mounted", "screentop": "Screentop"}
RESYNC_S = 0.25
IMAGE_MAX_FPS = 15
MODE_CONFIRM_S = 3.0
_MODE_NAMES = {"desktop": "Desktop", "hmd": "HMD", "screentop": "ScreenTop"}  # in the bindings
_MODE_FROM_LEAP = {name: mode for mode, name in _MODE_NAMES.items()}


def mode_label(mode: Optional[str]) -> str:
    return MODE_LABELS.get(mode, "unknown") if mode else "unknown"

SETUP_HINT = "Run scripts/setup.sh inside hand-cursor (see README)."


class LeapUnavailable(RuntimeError):
    pass


def _import_leap():
    try:
        import leap
    except Exception as e:  # ImportError, or the compiled module failing to load
        raise LeapUnavailable(f"The Ultraleap Python bindings could not be loaded ({e}). {SETUP_HINT}") from e
    return leap


def _vec(v) -> tuple:
    return (float(v.x), float(v.y), float(v.z))


def _finger(d) -> tuple:
    return (_vec(d.metacarpal.prev_joint), _vec(d.metacarpal.next_joint), _vec(d.proximal.next_joint),
            _vec(d.intermediate.next_joint), _vec(d.distal.next_joint))


def convert_hand(h) -> Hand:
    fingers = (h.thumb, h.index, h.middle, h.ring, h.pinky)
    return Hand(
        side="left" if "left" in str(h.type).lower() else "right",
        palm=_vec(h.palm.position),
        thumb=_vec(h.thumb.distal.next_joint),
        index=_vec(h.index.distal.next_joint),
        middle=_vec(h.middle.distal.next_joint),
        palm_width=float(h.palm.width),
        confidence=float(h.confidence),
        pinch_strength=float(h.pinch_strength),
        grab_strength=float(h.grab_strength),
        joints=tuple(_finger(d) for d in fingers),
        arm=(_vec(h.arm.prev_joint), _vec(h.arm.next_joint)),
        normal=_vec(h.palm.normal),
        direction=_vec(h.palm.direction),
    )


class LeapSource:
    """Calls on_frame(Frame) for every tracking frame, on the bindings' polling thread.

    Usage:
        with LeapSource(engine.process) as source:  # keeps the tracker's current mode
            ...  # frames arrive in the background; source.mode is the tracker's mode
    """

    def __init__(self, on_frame: Callable[[Frame], None], mode: Optional[str] = None,
                 log: Callable[[str], None] = print,
                 on_images: Optional[Callable[[int, int, List[bytes]], None]] = None,
                 on_mode: Optional[Callable[[Optional[str]], None]] = None):
        """mode: switch the tracker to this mode on connect. None leaves it as it is (as set
        in Ultraleap Control Panel, or by the last app that changed it).
        on_images, if given, receives the infrared camera images as
        (width, height, [left, right]) 8-bit grayscale buffers, at most IMAGE_MAX_FPS.
        on_mode, if given, is told whenever the tracker's mode changes, by any app."""
        if mode is not None and mode not in MODES:
            raise ValueError(f"tracking mode must be one of {', '.join(MODES)}")
        self.on_frame = on_frame
        self.on_images = on_images
        self.on_mode = on_mode
        self.requested = mode
        self.mode: Optional[str] = None  # what the tracker reports, not what was asked for
        self.log = log
        self._mode_changed = threading.Condition()
        self._clock_offset: Optional[float] = None
        self._last_image = 0.0
        self._image_failed = False
        self._stack = ExitStack()

    def __enter__(self) -> "LeapSource":
        leap = self._leap = _import_leap()
        self._conn = leap.Connection()
        self._conn.add_listener(_make_listener(leap, self))
        try:
            self._stack.enter_context(self._conn.open())
        except Exception as e:
            raise LeapUnavailable(
                "Could not connect to the Ultraleap tracking service. Check that Ultraleap "
                f"Hand Tracking is installed and running and the device is plugged in ({e}).") from e
        current = self.current_mode()
        if self.requested and self.requested != current:
            self.log(f"Switching the tracker from {mode_label(current)} to {mode_label(self.requested)} "
                     "mode (this also changes it in Ultraleap Control Panel).")
            self.set_mode(self.requested)
        if self.on_images is not None:
            try:
                from leap.enums import PolicyFlag
                self._conn.set_policy_flags([PolicyFlag.Images])
            except Exception as e:
                self.log(f"Camera images unavailable: {e}")
        return self

    def __exit__(self, *exc) -> None:
        self._stack.close()

    def current_mode(self) -> Optional[str]:
        """Asks the tracker which mode it is in."""
        try:
            mode = _MODE_FROM_LEAP.get(self._conn.get_tracking_mode().name)
        except Exception as e:
            self.log(f"Could not read the tracker's mode: {e}")
            return self.mode
        self._note_mode(mode)
        return mode

    def set_mode(self, mode: str) -> None:
        """Switches the tracker's mode and waits until the tracker confirms the change.
        The change is global: Ultraleap Control Panel and other apps see it too."""
        tracking_mode = getattr(self._leap.TrackingMode, _MODE_NAMES[mode], None)
        if tracking_mode is None:
            available = ", ".join(str(m) for m in self._leap.TrackingMode)
            raise LeapUnavailable(f"This Ultraleap version has no {mode} mode (it has: {available}).")
        with self._mode_changed:
            self._conn.set_tracking_mode(tracking_mode)
            confirmed = self._mode_changed.wait_for(lambda: self.mode == mode, MODE_CONFIRM_S)
        if not confirmed:
            raise LeapUnavailable(f"The tracker did not switch to {mode_label(mode)} mode "
                                  f"(it reports {mode_label(self.mode)}).")

    def _note_mode(self, mode: Optional[str]) -> None:
        with self._mode_changed:
            changed, self.mode = mode != self.mode, mode
            self._mode_changed.notify_all()
        if changed and self.on_mode:
            self.on_mode(mode)

    def _frame_time(self, event) -> float:
        """Map the device's capture timestamp (microseconds) onto time.monotonic().

        Capture timestamps give exact spacing between frames, even when the bindings
        deliver them in bursts, which keeps speed-based pointer acceleration stable. The
        offset stays fixed so the spacing is preserved; it is re-anchored only if the two
        clocks disagree by more than RESYNC_S (a stall, or clock drift over long sessions).
        """
        now = time.monotonic()
        ts = getattr(event, "timestamp", None)
        if not ts:
            return now
        ts *= 1e-6
        if self._clock_offset is None or abs(now - ts - self._clock_offset) > RESYNC_S:
            self._clock_offset = now - ts
        return ts + self._clock_offset

    def _tracking(self, event) -> None:
        hands = tuple(convert_hand(h) for h in event.hands)
        self.on_frame(Frame(self._frame_time(event), hands))

    def _lost(self, what: str) -> None:
        self.log(f"Ultraleap {what} lost")
        self.on_frame(Frame(time.monotonic(), ()))

    def _images(self, event) -> None:
        now = time.monotonic()
        if self.on_images is None or self._image_failed or now - self._last_image < 1.0 / IMAGE_MAX_FPS:
            return
        self._last_image = now
        try:
            from leapc_cffi import ffi

            buffers, width, height = [], 0, 0
            for image in event.image:
                raw = image._data  # the bindings don't wrap pixel data, so read the C struct
                props = raw.properties
                if props.bpp != 1:
                    raise ValueError(f"unsupported image format ({props.bpp} bytes per pixel)")
                width, height = props.width, props.height
                pixels = ffi.cast("uint8_t *", raw.data) + raw.offset
                buffers.append(bytes(ffi.buffer(pixels, width * height)))
        except Exception as e:
            self._image_failed = True
            self.log(f"Camera images unavailable: {e}")
            return
        self.on_images(width, height, buffers)


def _make_listener(leap, source: LeapSource):
    class _Listener(leap.Listener):
        def on_tracking_event(self, event):
            source._tracking(event)

        def on_image_event(self, event):
            source._images(event)

        def on_tracking_mode_event(self, event):  # sent for changes made by any app
            source._note_mode(_MODE_FROM_LEAP.get(event.current_tracking_mode.name))

        def on_device_event(self, event):
            source.log("Ultraleap device connected")

        def on_device_lost_event(self, event):
            source._lost("device")

        def on_connection_lost_event(self, event):
            source._lost("service connection")

        def on_error(self, error):
            source.log(f"Ultraleap error: {error}")

    return _Listener()
