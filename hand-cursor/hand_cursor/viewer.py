"""A live view of what the tracker sees, in your browser:  python -m hand_cursor view

Shows the infrared camera images, the tracked hands in 3D with your calibration drawn in,
tracking quality, and the gesture engine's state, so you can place the tracker and check
calibration. The real mouse is never touched: gestures drive a simulated cursor.

The page is served on 127.0.0.1 only. Data reaches it as Server-Sent Events (/events);
camera images are fetched as PNG (/camera.png).
"""
from __future__ import annotations

import json
import math
import struct
import threading
import time
import webbrowser
import zlib
from collections import deque
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from .calibrate import best_mode
from .config import (CALIBRATION_PATH, SETTINGS_PATH, Calibration, Settings, load_calibration,
                     load_settings)
from .engine import ENGAGED, Engine
from .feedback import Feedback
from .frames import Frame, Hand
from .geometry import dist, mean, norm
from .keyboard import KeyMonitor
from .leap_source import MODES, LeapSource, mode_label
from .mouse import DryRunMouse

PAGE = Path(__file__).resolve().parent / "web" / "viewer.html"
STREAM_HZ = 30
STATS_WINDOW_S = 3.0
RELOAD_CHECK_S = 1.0
SCAN_SETTLE_S = 1.0
SCAN_MEASURE_S = 2.0


def png_gray(width: int, height: int, images: List[bytes]) -> bytes:
    """Encode 8-bit grayscale images, placed side by side, as a PNG (stdlib only)."""
    rows = (b"\x00" + b"".join(img[y * width:(y + 1) * width] for img in images) for y in range(height))

    def chunk(tag: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + tag + body + struct.pack(">I", zlib.crc32(tag + body))

    header = struct.pack(">IIBBBBB", width * len(images), height, 8, 0, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
            + chunk(b"IDAT", zlib.compress(b"".join(rows), 1)) + chunk(b"IEND", b""))


def _r(v, digits: int = 1):
    return [round(c, digits) for c in v]


def _hand_json(h: Hand) -> dict:
    d = {"side": h.side, "palm": _r(h.palm), "tips": [_r(h.thumb), _r(h.index), _r(h.middle)],
         "thumb_index": round(h.thumb_index, 1), "thumb_middle": round(h.thumb_middle, 1)}
    if h.joints:
        d["fingers"] = [[_r(p) for p in finger] for finger in h.joints]
    if h.arm:
        d["arm"] = [_r(h.arm[0]), _r(h.arm[1])]
    if h.normal:
        d["normal"] = _r(h.normal, 3)
    if h.direction:
        d["direction"] = _r(h.direction, 3)
    return d


def _json_safe(value):
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


class _PageMouse(DryRunMouse):
    """Simulated mouse that reports its clicks and scrolls to the page."""

    def __init__(self, sink: Callable[[dict], None], size: Tuple[int, int]):
        super().__init__(log=lambda message: None, size=size)
        self.sink = sink

    def down(self, button, x, y, clicks=1):
        super().down(button, x, y, clicks)
        self.sink({"kind": "down", "button": button, "x": round(x), "y": round(y), "clicks": clicks})

    def up(self, button, x, y, clicks=1):
        super().up(button, x, y, clicks)
        self.sink({"kind": "up", "button": button, "x": round(x), "y": round(y), "clicks": clicks})

    def scroll(self, dx, dy):
        super().scroll(dx, dy)
        self.sink({"kind": "scroll", "dx": dx, "dy": dy})


class ViewerState:
    """Everything the page shows. Fed by the tracker thread, read by the page streams."""

    def __init__(self, screen: Tuple[int, int] = (1920, 1080), mode: Optional[str] = None,
                 settings_path: Path = SETTINGS_PATH, calibration_path: Path = CALIBRATION_PATH,
                 last_key_time: Callable[[], float] = lambda: -math.inf):
        self._lock = threading.RLock()  # engine callbacks re-enter while a frame is processed
        self.screen = screen
        self._last_key_time = last_key_time
        self.mode = mode
        self._paths = (settings_path, calibration_path)
        self._mtimes: Tuple = ()
        self._checked_at = 0.0
        self._frames: deque = deque()  # (t, palm of the controlling hand or None)
        self._latest: Optional[Frame] = None
        self._latest_at = 0.0
        self._events: deque = deque(maxlen=100)
        self._seq = 0
        self._images: Optional[Tuple[int, int, int, List[bytes]]] = None
        self._image_seq = 0
        self._png: Tuple[int, Optional[bytes]] = (-1, None)
        self.scan: Dict = {"running": False, "current": None, "results": {}, "best": None}
        self.config_version = 0
        self._load_config()

    # ----- configuration -----

    def _load_config(self) -> None:
        settings_path, calibration_path = self._paths
        try:
            settings = load_settings(settings_path)
        except ValueError as e:
            self.add_event({"kind": "info", "text": str(e)})
            settings = Settings()
        self.settings = settings
        self.calibration = load_calibration(calibration_path)
        self.mouse = _PageMouse(self.add_event, self.screen)
        feedback = Feedback(settings.sounds, log=lambda message: None)

        def on_state(state: str) -> None:
            feedback(state)
            self.add_event({"kind": "mode", "on": state == ENGAGED})

        self.engine = Engine(settings, self.calibration or Calibration(), self.mouse,
                             last_key_time=self._last_key_time, on_state=on_state)
        self._mtimes = tuple(p.stat().st_mtime if p.exists() else None for p in self._paths)
        self.config_version += 1

    def reload_if_changed(self) -> None:
        now = time.monotonic()
        with self._lock:
            if now - self._checked_at < RELOAD_CHECK_S:
                return
            self._checked_at = now
            mtimes = tuple(p.stat().st_mtime if p.exists() else None for p in self._paths)
            if mtimes != self._mtimes:
                self._load_config()
                self.add_event({"kind": "info", "text": "Calibration or settings changed; reloaded."})

    def config(self) -> dict:
        with self._lock:
            s, c = self.settings, self.calibration
            pinch_on, pinch_off = (c or Calibration()).pinch_thresholds(s)
            return _json_safe({
                "type": "config",
                "calibrated": c is not None,
                "calibration": asdict(c) if c else None,
                "hand": s.hand,
                "pinch": {"on": pinch_on, "off": pinch_off,
                          "closed": (c or Calibration()).pinch_closed_mm,
                          "open": (c or Calibration()).pinch_open_mm},
                "raise": {"on": s.raise_on_frac, "off": s.raise_off_frac}
                if c and c.raise_thresholds(s) else None,
                "height_problem": c.height_problem() if c else None,
                "screen": list(self.screen),
                "modes": list(MODES),
            })

    # ----- inputs (tracker thread) -----

    def on_frame(self, frame: Frame) -> None:
        with self._lock:
            self.engine.process(frame)
            self._latest, self._latest_at = frame, time.monotonic()
            hand = self._controlling(frame)
            self._frames.append((frame.t, hand.palm if hand else None))
            while self._frames and self._frames[0][0] < frame.t - STATS_WINDOW_S:
                self._frames.popleft()

    def on_images(self, width: int, height: int, images: List[bytes]) -> None:
        with self._lock:
            self._image_seq += 1
            self._images = (self._image_seq, width, height, images)

    def add_event(self, event: dict) -> None:
        with self._lock:
            self._seq += 1
            self._events.append(dict(event, seq=self._seq))

    def _controlling(self, frame: Frame) -> Optional[Hand]:
        wanted = [h for h in frame.hands if self.settings.hand in ("any", h.side)]
        return wanted[0] if wanted else None

    # ----- outputs (page threads) -----

    def camera_png(self) -> Optional[bytes]:
        with self._lock:
            images = self._images
            cached_seq, cached = self._png
        if images is None:
            return None
        seq, width, height, buffers = images
        if seq == cached_seq:
            return cached
        png = png_gray(width, height, buffers)
        with self._lock:
            self._png = (seq, png)
        return png

    def latest_seq(self) -> int:
        with self._lock:
            return self._seq

    def stats(self, window_s: float = 2.0, since: Optional[float] = None) -> dict:
        with self._lock:
            if not self._frames:
                return {"fps": 0.0, "seen": 0.0, "jitter_mm": None, "distance_mm": None}
            t_end = self._frames[-1][0]
            start = since if since is not None else t_end - window_s
            window = [(t, p) for t, p in self._frames if t >= start]
            last_second = [t for t, _ in self._frames if t >= t_end - 1.0]
            fps = (len(last_second) - 1) / (last_second[-1] - last_second[0]) if len(last_second) > 1 else 0.0
            seen = sum(p is not None for _, p in window) / len(window) if window else 0.0
            still = [p for t, p in self._frames if t >= t_end - 0.5 and p is not None]
            jitter = None
            if len(still) >= 10:
                centre = mean(still)
                jitter = math.sqrt(sum(dist(p, centre) ** 2 for p in still) / len(still))
            palm = self._frames[-1][1]
            return {"fps": round(fps, 1), "seen": round(seen, 3),
                    "jitter_mm": round(jitter, 2) if jitter is not None else None,
                    "distance_mm": round(norm(palm)) if palm else None}

    def snapshot(self, since_seq: int) -> dict:
        with self._lock:
            frame = self._latest
            events = [e for e in self._events if e["seq"] > since_seq]
            status = dict(self.engine.status)
            message = {
                "type": "state",
                "mode": self.mode,
                "age_s": round(time.monotonic() - self._latest_at, 2) if frame else None,
                "hands": [_hand_json(h) for h in frame.hands] if frame else [],
                "engine": status,
                "cursor": [round(self.mouse.pos[0]), round(self.mouse.pos[1])],
                "stats": self.stats(),
                "scan": self.scan,
                "has_images": self._images is not None,
                "events": events,
                "last_seq": self._seq,
            }
        return _json_safe(message)

    # ----- tracking mode -----

    def mode_changed(self, mode: Optional[str]) -> None:
        """The tracker's mode changed: from this page, another app, or Ultraleap Control Panel."""
        with self._lock:
            if mode == self.mode:
                return
            self.mode = mode
            self._frames.clear()
            self.add_event({"kind": "info", "text": f"Tracking mode: {mode_label(mode)}"})

    def run_scan(self, set_mode: Callable[[str], None], sleep: Callable[[float], None] = time.sleep) -> None:
        """Try every tracking mode while you hold your hand still; keep the best one."""
        with self._lock:
            if self.scan["running"]:
                return
            self.scan = {"running": True, "current": None, "results": {}, "best": None}
        scores = {}
        for mode in MODES:
            set_mode(mode)
            with self._lock:
                self.scan["current"] = mode
            sleep(SCAN_SETTLE_S)
            with self._lock:
                started = self._frames[-1][0] if self._frames else None
            sleep(SCAN_MEASURE_S)
            result = self.stats(since=started) if started is not None else {"seen": 0.0, "jitter_mm": None}
            jitter = result["jitter_mm"]
            scores[mode] = (result["seen"], jitter if jitter is not None else math.inf)
            with self._lock:
                self.scan["results"][mode] = {"seen": result["seen"], "jitter_mm": jitter}
        best = best_mode(scores)
        set_mode(best)
        with self._lock:
            self.scan.update(running=False, current=None, best=best)
            self.add_event({"kind": "info", "text": f"Mode test finished: {mode_label(best)} sees your hand most"})


# ----- HTTP -----

class _Handler(BaseHTTPRequestHandler):
    server: "ViewerServer"

    def log_message(self, format, *args):  # keep the terminal quiet
        pass

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            self._send(200, "text/html; charset=utf-8", PAGE.read_bytes())
        elif path == "/events":
            self._stream()
        elif path == "/camera.png":
            png = self.server.state.camera_png()
            if png is None:
                self._send(204, "text/plain", b"")
            else:
                self._send(200, "image/png", png)
        else:
            self._send(404, "text/plain", b"not found")

    def do_POST(self):
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length).decode("utf-8", "replace").strip() if length else ""
        if path == "/mode":
            if body not in MODES:
                self._send(400, "text/plain", f"mode must be one of {', '.join(MODES)}".encode())
                return
            try:
                self.server.set_mode(body)
            except Exception as e:
                self._send(500, "text/plain", str(e).encode())
                return
            self._send(200, "application/json", json.dumps({"mode": body}).encode())
        elif path == "/scan":
            threading.Thread(target=self.server.state.run_scan, args=(self.server.set_mode,),
                             daemon=True).start()
            self._send(202, "application/json", b'{"started": true}')
        else:
            self._send(404, "text/plain", b"not found")

    def _send(self, code: int, content_type: str, body: bytes) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _stream(self) -> None:
        state = self.server.state
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        sent_config, since = -1, state.latest_seq()
        try:
            while not self.server.stopping.is_set():
                state.reload_if_changed()
                if state.config_version != sent_config:
                    sent_config = state.config_version
                    self._event(state.config())
                message = state.snapshot(since)
                since = message["last_seq"]
                self._event(message)
                self.server.stopping.wait(1.0 / STREAM_HZ)
        except (BrokenPipeError, ConnectionResetError):
            pass  # the page was closed

    def _event(self, message: dict) -> None:
        self.wfile.write(b"data: " + json.dumps(message, separators=(",", ":")).encode() + b"\n\n")
        self.wfile.flush()


class ViewerServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, state: ViewerState, set_mode: Callable[[str], None], port: int = 0):
        super().__init__(("127.0.0.1", port), _Handler)
        self.state = state
        self.stopping = threading.Event()

        def _set_mode(mode: str) -> None:
            set_mode(mode)
            state.mode_changed(mode)
        self.set_mode = _set_mode

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server_address[1]}/"

    def start(self) -> "ViewerServer":
        threading.Thread(target=self.serve_forever, name="viewer-http", daemon=True).start()
        return self

    def stop(self) -> None:
        self.stopping.set()
        self.shutdown()
        self.server_close()


def _open_server(state: ViewerState, set_mode: Callable[[str], None], port: int) -> ViewerServer:
    for candidate in range(port, port + 10):
        try:
            return ViewerServer(state, set_mode, candidate)
        except OSError:
            continue  # port in use; try the next one
    raise RuntimeError(f"no free port between {port} and {port + 9}")


def _screen_size() -> Tuple[int, int]:
    try:
        import Quartz

        bounds = Quartz.CGDisplayBounds(Quartz.CGMainDisplayID())
        return int(bounds.size.width), int(bounds.size.height)
    except Exception:
        return 1920, 1080


def cmd_view(args) -> int:
    keys = KeyMonitor()  # so typing ends mouse mode here exactly as it does in `run`
    if not keys.start():
        print("Note: typing detection is off (no Input Monitoring permission), so typing won't "
              "turn mouse mode off on this page.")
    state = ViewerState(_screen_size(), mode=None, last_key_time=keys)
    log = lambda message: state.add_event({"kind": "info", "text": message})  # noqa: E731
    on_images = None if args.no_images else state.on_images
    # Without --mode the tracker keeps the mode it's in (as set in Ultraleap Control Panel).
    with LeapSource(state.on_frame, args.mode, log=log, on_images=on_images,
                    on_mode=state.mode_changed) as source:
        state.mode_changed(source.mode)
        server = _open_server(state, source.set_mode, args.port).start()
        print(f"Tracking mode: {mode_label(source.mode)} (change it on the page or in Ultraleap Control Panel)")
        print(f"Tracker view: {server.url}")
        print("The real mouse is not touched. Press Ctrl+C to stop.")
        if not args.no_browser:
            webbrowser.open(server.url)
        try:
            while True:
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
        finally:
            server.stop()
            keys.stop()
    print()
    return 0
