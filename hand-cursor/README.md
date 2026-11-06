# hand-cursor

Use your hand as a mouse on macOS with an Ultraleap / Leap Motion tracker. It clicks,
drags, selects text, scrolls and right-clicks in any app. It works like a mouse, not a
touchscreen: small, relaxed hand movements move the cursor, and fast movements carry it
further. Mouse mode stays off while you type.

## Gestures

| Do this | To |
|---|---|
| **Open** your right hand, then **pinch thumb and index and hold** for a moment | Turn mouse mode on (you hear a *tink*). This pinch never clicks. |
| Move the relaxed hand | Move the cursor |
| Quick thumb-index pinch | Click. Two quick pinches double-click. |
| Thumb-index pinch, hold and move | Drag, or select text. Double-pinch and drag selects whole words. |
| Thumb-middle pinch, hold and move up/down | Scroll. Works like a joystick: move further from where you pinched to scroll faster. |
| Quick thumb-middle tap | Right click |
| Type, or take your hand out of the tracker's view | Turn mouse mode off (*pop*). The cursor stays where it is. Shortcuts with Cmd or Ctrl, such as Cmd+C, don't count as typing. |

Mouse mode needs a deliberate open-then-pinch: a resting or half-visible hand can look
"pinched" to the tracker, and that alone never turns it on. If calibration finds your
mouse position clearly *above* your typing position, the hand must also be raised, and
lowering it to the keyboard turns mouse mode off. Calibration tells you which applies.

The most relaxed posture is your elbow resting on the desk or an armrest, moving only the
wrist and fingers. You don't need to reach. Because movement is relative, you can
reposition the hand by taking it out of view and back, like lifting a mouse.

## Setup

1. **Install Ultraleap Hand Tracking** (the "Hyperion" software) for your Mac from
   <https://www.ultraleap.com/downloads/leap-motion-controller-2>, and plug in the tracker.
2. **Build the environment.** This creates `.venv` and installs the macOS bindings and
   Ultraleap's Python bindings. Ultraleap 6.2 ships the bindings' compiled module for
   Python 3.12, and the script uses it when your Python matches. For any other Python
   version it compiles the module, which needs the Xcode command line tools.
   ```sh
   cd hand-cursor
   ./scripts/setup.sh
   source .venv/bin/activate
   ```
3. **Grant permissions** under System Settings > Privacy & Security to the app you run
   this from (Terminal, iTerm or Visual Studio Code), then quit and reopen that app:
   - **Accessibility**: required, so it can move the cursor and click.
   - **Input Monitoring**: optional. It lets mouse mode pause when you type. It only
     notices that *a* key was pressed, never which one.
4. **Pick the tracking mode in Ultraleap Control Panel.** It tells the tracker how it's
   mounted. For a tracker above your desk or screen, facing you, choose **Screentop**.
   Use the Control Panel's hand view to check that both hands are tracked steadily and
   labelled with the right side.
5. **Calibrate** (about a minute):
   ```sh
   python -m hand_cursor calibrate
   ```
   It calibrates in the mode you picked. Then it measures your typing and mouse positions,
   your pinch, and which hand movements mean "right" and "up". That works for any mounting,
   including a tracker above the desk looking down. The result is saved to
   `calibration.json`. Re-run it if you move the tracker, change how you sit, or change
   the tracking mode.

   `--mode desktop|hmd|screentop` switches the tracker to a mode first. `--test-modes`
   tries all three and keeps the one that sees your hand most often. That's only a rough
   guide, because a mode can see a hand often and still track the fingers badly.
6. **Check tracking without touching the real mouse:**
   ```sh
   python -m hand_cursor monitor
   ```
   A live line shows the palm position, hand height (0 = typing, 1 = mouse position),
   both pinch distances and the mouse-mode state. Clicks and scrolls are printed instead
   of performed.
7. **Use it:**
   ```sh
   python -m hand_cursor run
   ```
   Press Ctrl+C to quit. Any held mouse button is released on exit.

**About the tracking mode:** it's a setting of the tracker itself, shared by every app
including Ultraleap Control Panel, and it persists. hand-cursor never changes it unless
you ask, either with `--mode` or with the mode buttons on the `view` page. If your
calibration was made in a different mode than the tracker is in now, `run` and `monitor`
stop and ask you to calibrate again.

## See what the tracker sees

```sh
python -m hand_cursor view
```

This opens a live page in your browser (served from your Mac only, at
<http://127.0.0.1:8765>). It never touches the real mouse. It shows:

- **Infrared cameras:** both of the tracker's cameras, so you can check its field of view
  and spot glare. A bright patch usually means something near the tracker is reflecting
  its infrared light.
- **3D view:** your hands as skeletons, with the calibration drawn in: keyboard height,
  the height above which mouse mode can turn on, and the hand directions that move the
  cursor right and up. Drag to rotate, scroll to zoom. The view is levelled from your
  calibration: the plane your hand moved in, right and forward, is taken as the desk.
  Before you calibrate, it levels itself from the first hands it sees. If it ever looks
  tilted, rest both hands palm-down as if typing and press **Level**. **Flip** turns it
  upside down.
- **Tracking quality:** how often the hand is seen, distance from the tracker, and
  jitter while you hold still.
- **Gestures:** hand height and both pinch distances against their thresholds, plus
  mouse-mode state. A simulated screen and event log let you try clicks, drags and
  scrolling.
- **Tracking mode:** shows the tracker's current mode, including changes made in
  Ultraleap Control Panel, and lets you switch it. **Test all modes** compares how often
  each mode sees your hand while you hold it still. A banner warns when your calibration
  was made in a different mode.

Leave it open while you run `calibrate` in a terminal. The page picks up the new
calibration as soon as it's saved. The same goes for edits to `settings.json`.

## Tracker placement

- A Leap Motion Controller 2 tracks to about 110 cm, so mounting it overhead about 75 cm
  above your hands is within range. Accuracy drops toward the edge of that range. If
  `monitor` shows the hand flickering in and out, move the tracker closer.
- Infrared reflections from glossy desks, glass or direct sunlight cause most tracking
  problems. A matte surface under your hands helps.
- Both a palm-down hand and a "handshake" hand (palm facing left, thumb on top) work. The
  handshake posture is easier on the forearm. Use whichever `monitor` tracks steadily,
  and calibrate in that posture.

## Tuning

Put overrides in `settings.json` next to this README. Print all settings and their current
values with `python -m hand_cursor settings`. For example:

```json
{ "gain_max": 25, "engage_hold_s": 0.3, "scroll_invert": true }
```

| If... | Change |
|---|---|
| The cursor shimmers while your hand rests | Lower `filter_min_cutoff` (e.g. 0.6). Don't raise `rest_speed`; that loses slow, precise moves. |
| Crossing the screen needs too much movement | Raise `gain_max` (fast moves) |
| Fine positioning is too twitchy | Lower `gain_min` (slow moves) |
| Clicks fire by accident, or pinches are missed | Lower or raise `pinch_on_frac` (fraction between your calibrated pinched and open distances) |
| Drags start when you meant to click | Raise `drag_slop_px` |
| Scroll direction feels backwards | `"scroll_invert": true` |
| Scrolling is too fast or slow | `scroll_gain`, `scroll_dead_mm` |
| Mouse mode switches off while you point low | Lower `raise_off_frac` |
| Turning mouse mode on fails | Open `view` and watch the *Turning mouse mode on* checklist: it shows which condition fails (hand steady, raised, not typing, open-then-pinch). Then see the rows above. |
| Engaging takes too long, or happens by accident | `engage_hold_s`, `engage_open_s` |
| Typing should pause mouse mode instead of ending it | `"typing_turns_off": false` |
| You're left-handed | `"hand": "left"`, then re-calibrate |

## Recording and replay

For tuning or experiments, record the raw tracking data and key-press times, then replay
them through the gesture engine with different settings:

```sh
python -m hand_cursor run --record recordings/session1.jsonl
python -m hand_cursor replay recordings/session1.jsonl          # prints clicks and scrolls
python -m hand_cursor replay recordings/session1.jsonl --moves  # ...and every cursor move
```

`monitor` takes `--record` too. Replays never touch the real mouse.

## Troubleshooting

- **"Ultraleap Python bindings could not be loaded"**: run `./scripts/setup.sh`, and make
  sure `.venv` is activated. If Ultraleap is installed in a non-default location, set
  `LEAPSDK_INSTALL_LOCATION` to its `LeapSDK` folder, both for setup and when running.
- **"Could not connect to the Ultraleap tracking service"**: check that Ultraleap Hand
  Tracking is running (menu bar icon) and the device is plugged in.
- **The cursor doesn't move, but `monitor` shows MOUSE ON**: Accessibility permission is
  missing for the app you're running from. Re-open that app after granting it.
- **Hands are reported as the wrong side, or tracking is poor**: the tracking mode probably
  doesn't match how the tracker is mounted. Desktop mode expects the tracker to look up at
  your palms. For a tracker above you, pick Screentop in Ultraleap Control Panel and run
  `calibrate` again.
- **"Your calibration was made in … mode"**: the tracker's mode changed after you
  calibrated. Run `calibrate` again in the current mode, or pass `--mode` to switch back.

## Code layout

| File | Role |
|---|---|
| `hand_cursor/engine.py` | Gesture state machine: mouse mode on/off, click, drag, scroll, right click |
| `hand_cursor/pointer.py` | Pointer acceleration and multi-display clamping |
| `hand_cursor/gestures.py` | Pinch detection with hysteresis |
| `hand_cursor/filters.py` | One Euro filter for the palm position |
| `hand_cursor/calibrate.py` | Interactive calibration |
| `hand_cursor/leap_source.py` | Ultraleap input; the only tracker-specific file |
| `hand_cursor/mouse.py`, `keyboard.py` | macOS mouse output and typing detection (Quartz) |
| `hand_cursor/viewer.py`, `web/viewer.html` | The `view` page: local server and live page |
| `hand_cursor/app.py`, `__main__.py` | Commands |

Run the tests with `python -m pytest`. They simulate hands and need no tracker.
