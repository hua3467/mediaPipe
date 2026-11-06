"""Notices typing anywhere on the Mac, so mouse mode can pause while you type.

Uses a listen-only Quartz event tap: it only sees that a key went down, never changes
or blocks keystrokes, and never stores which key it was. macOS requires Input
Monitoring permission for the app running Python.
"""
from __future__ import annotations

import math
import threading
import time
from typing import Callable, Optional


class KeyMonitor:
    def __init__(self, on_key: Optional[Callable[[float], None]] = None):
        self.last_key_time = -math.inf
        self._on_key = on_key
        self._tap = None
        self._loop = None
        self._ready = threading.Event()
        self.ok = False

    def __call__(self) -> float:
        return self.last_key_time

    def start(self) -> bool:
        """Starts listening in a background thread. Returns False if permission is missing."""
        thread = threading.Thread(target=self._run, name="key-monitor", daemon=True)
        thread.start()
        self._ready.wait(timeout=3.0)
        return self.ok

    def stop(self) -> None:
        if self._loop is not None:
            import Quartz

            Quartz.CFRunLoopStop(self._loop)

    def _run(self) -> None:
        import Quartz as Q

        self._tap = Q.CGEventTapCreate(
            Q.kCGSessionEventTap, Q.kCGHeadInsertEventTap, Q.kCGEventTapOptionListenOnly,
            1 << Q.kCGEventKeyDown, self._callback, None)
        if self._tap is None:  # no Input Monitoring permission
            if hasattr(Q, "CGRequestListenEventAccess"):
                Q.CGRequestListenEventAccess()
            self._ready.set()
            return
        source = Q.CFMachPortCreateRunLoopSource(None, self._tap, 0)
        self._loop = Q.CFRunLoopGetCurrent()
        Q.CFRunLoopAddSource(self._loop, source, Q.kCFRunLoopCommonModes)
        Q.CGEventTapEnable(self._tap, True)
        self.ok = True
        self._ready.set()
        Q.CFRunLoopRun()

    def _callback(self, proxy, event_type, event, refcon):
        import Quartz as Q

        if event_type in (Q.kCGEventTapDisabledByTimeout, Q.kCGEventTapDisabledByUserInput):
            Q.CGEventTapEnable(self._tap, True)
        elif event_type == Q.kCGEventKeyDown:
            flags = Q.CGEventGetFlags(event)
            # Shortcuts like Cmd+C are part of mouse work (copy what you just selected), not typing.
            if not flags & (Q.kCGEventFlagMaskCommand | Q.kCGEventFlagMaskControl):
                self.last_key_time = time.monotonic()
                if self._on_key:
                    self._on_key(self.last_key_time)
        return event
