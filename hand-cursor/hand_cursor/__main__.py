"""Command line: python -m hand_cursor <command>"""
from __future__ import annotations

import argparse
import sys

from .leap_source import MODES, LeapUnavailable


def main(argv=None) -> int:
    from . import app, viewer

    parser = argparse.ArgumentParser(
        prog="python -m hand_cursor",
        description="Use your hand as a mouse with an Ultraleap / Leap Motion tracker.")
    sub = parser.add_subparsers(dest="command", required=True)

    mode_note = ("The tracking mode is the tracker's own setting, shared with Ultraleap Control Panel; "
                 "by default it is left as you set it there.")
    p = sub.add_parser("calibrate", help="learn how the tracker is mounted (run this first)",
                       description=mode_note)
    p.add_argument("--mode", choices=MODES, help="switch the tracker to this mode and calibrate in it")
    p.add_argument("--test-modes", action="store_true",
                   help="try every tracking mode and keep the one that sees your hand most")
    p.set_defaults(func=app.cmd_calibrate)

    p = sub.add_parser("run", help="control the mouse with your hand", description=mode_note)
    p.add_argument("--mode", choices=MODES, help="switch the tracker to this mode first")
    p.add_argument("--dry-run", action="store_true", help="print mouse actions instead of performing them")
    p.add_argument("--record", metavar="FILE", help="also save the tracking data to a .jsonl file")
    p.set_defaults(func=app.cmd_run)

    p = sub.add_parser("monitor", help="live tracking and gesture readout; the real mouse is not touched",
                       description=mode_note)
    p.add_argument("--mode", choices=MODES, help="switch the tracker to this mode first")
    p.add_argument("--record", metavar="FILE", help="also save the tracking data to a .jsonl file")
    p.set_defaults(func=app.cmd_monitor)

    p = sub.add_parser("view", help="see what the tracker sees, live in your browser (placement, calibration)",
                       description=mode_note)
    p.add_argument("--mode", choices=MODES, help="switch the tracker to this mode first")
    p.add_argument("--port", type=int, default=8765, help="local port for the page (default 8765)")
    p.add_argument("--no-browser", action="store_true", help="don't open the browser automatically")
    p.add_argument("--no-images", action="store_true", help="don't stream the infrared camera images")
    p.set_defaults(func=viewer.cmd_view)

    p = sub.add_parser("replay", help="run a recording through the gestures again (dry run)")
    p.add_argument("file")
    p.add_argument("--moves", action="store_true", help="also print every cursor movement")
    p.set_defaults(func=app.cmd_replay)

    p = sub.add_parser("settings", help="print the current settings as JSON")
    p.set_defaults(func=app.cmd_settings)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (LeapUnavailable, RuntimeError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
