"""Tells you when mouse mode turns on or off, with a short system sound."""
from __future__ import annotations

import os
import subprocess
from typing import Callable

from .engine import ENGAGED, IDLE

SOUNDS = {
    ENGAGED: "/System/Library/Sounds/Tink.aiff",
    IDLE: "/System/Library/Sounds/Pop.aiff",
}


class Feedback:
    def __init__(self, sounds: bool = True, log: Callable[[str], None] = print):
        self.sounds = sounds
        self.log = log

    def __call__(self, state: str) -> None:
        self.log("mouse mode ON" if state == ENGAGED else "mouse mode off")
        path = SOUNDS.get(state)
        if self.sounds and path and os.path.exists(path):
            subprocess.Popen(["afplay", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
