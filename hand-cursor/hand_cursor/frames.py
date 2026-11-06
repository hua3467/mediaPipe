"""Tracker-independent hand data, plus JSONL recording and replay."""
from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Optional, Tuple, Union

from .geometry import Vec3, dist


@dataclass(frozen=True)
class Hand:
    """One tracked hand. Positions are in millimetres in the tracker's coordinates."""

    side: str  # "left" or "right"
    palm: Vec3
    thumb: Vec3  # fingertip positions
    index: Vec3
    middle: Vec3
    palm_width: float = 80.0
    confidence: float = 1.0
    # The tracker's own 0..1 estimates of pinching (thumb to any finger) and fist-making.
    # Recorded for analysis; the engine uses fingertip distances instead.
    pinch_strength: Optional[float] = field(default=None, compare=False)
    grab_strength: Optional[float] = field(default=None, compare=False)
    # Full skeleton, used only by the viewer (not recorded): 5 fingers from thumb to
    # pinky, each as 5 points from the base of the hand to the fingertip.
    joints: Optional[Tuple[Tuple[Vec3, ...], ...]] = field(default=None, compare=False, repr=False)
    arm: Optional[Tuple[Vec3, Vec3]] = field(default=None, compare=False, repr=False)  # elbow, wrist
    normal: Optional[Vec3] = field(default=None, compare=False, repr=False)  # out of the palm
    direction: Optional[Vec3] = field(default=None, compare=False, repr=False)  # palm toward fingers

    @property
    def thumb_index(self) -> float:
        return dist(self.thumb, self.index)

    @property
    def thumb_middle(self) -> float:
        return dist(self.thumb, self.middle)


@dataclass(frozen=True)
class Frame:
    t: float  # seconds on the time.monotonic() clock
    hands: Tuple[Hand, ...] = ()


def _r(v: Vec3) -> list:
    return [round(c, 2) for c in v]


def _hand_to_json(h: Hand) -> dict:
    d = {
        "side": h.side,
        "palm": _r(h.palm),
        "thumb": _r(h.thumb),
        "index": _r(h.index),
        "middle": _r(h.middle),
        "palm_width": round(h.palm_width, 2),
        "confidence": round(h.confidence, 3),
    }
    if h.pinch_strength is not None:
        d["pinch_strength"] = round(h.pinch_strength, 3)
    if h.grab_strength is not None:
        d["grab_strength"] = round(h.grab_strength, 3)
    return d


def frame_to_json(frame: Frame) -> dict:
    return {"type": "frame", "t": round(frame.t, 5), "hands": [_hand_to_json(h) for h in frame.hands]}


def frame_from_json(d: dict) -> Frame:
    hands = tuple(
        Hand(
            side=h["side"],
            palm=tuple(h["palm"]),
            thumb=tuple(h["thumb"]),
            index=tuple(h["index"]),
            middle=tuple(h["middle"]),
            palm_width=h.get("palm_width", 80.0),
            confidence=h.get("confidence", 1.0),
            pinch_strength=h.get("pinch_strength"),
            grab_strength=h.get("grab_strength"),
        )
        for h in d["hands"]
    )
    return Frame(t=d["t"], hands=hands)


class Recorder:
    """Writes frames and key presses to a JSONL file; safe to call from several threads."""

    def __init__(self, path: Union[str, Path]):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.path.open("w")
        self._lock = threading.Lock()

    def frame(self, frame: Frame) -> None:
        self._write(frame_to_json(frame))

    def key(self, t: float) -> None:
        self._write({"type": "key", "t": round(t, 5)})

    def _write(self, record: dict) -> None:
        with self._lock:
            if not self._file.closed:
                self._file.write(json.dumps(record) + "\n")

    def close(self) -> None:
        with self._lock:
            self._file.close()


def read_recording(path: Union[str, Path]) -> Iterator[Union[Frame, float]]:
    """Yields Frame objects, and a float timestamp for each recorded key press."""
    with Path(path).open() as f:
        for line in f:
            if not line.strip():
                continue
            record = json.loads(line)
            if record["type"] == "key":
                yield float(record["t"])
            else:
                yield frame_from_json(record)
