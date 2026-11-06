import http.client
import json
import struct
import zlib

import pytest

from hand_cursor.frames import Frame
from hand_cursor.viewer import ViewerServer, ViewerState, png_gray

from conftest import PINCHED, make_hand


@pytest.fixture
def state(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"sounds": False}))
    return ViewerState(screen=(1440, 900), mode="desktop", settings_path=settings,
                       calibration_path=tmp_path / "calibration.json")


def feed(state, seconds, t0=0.0, **hand):
    t = t0
    for _ in range(round(seconds / 0.01)):
        t += 0.01
        state.on_frame(Frame(t, (make_hand(**hand),) if hand.get("side", "right") else ()))
    return t


def test_png_encoder_places_cameras_side_by_side():
    left, right = bytes(range(6)), bytes(range(100, 106))  # two 3x2 images
    png = png_gray(3, 2, [left, right])
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = struct.unpack(">II", png[16:24])
    assert (width, height) == (6, 2)
    idat_len = struct.unpack(">I", png[33:37])[0]
    rows = zlib.decompress(png[41:41 + idat_len])
    assert rows == b"\x00" + bytes([0, 1, 2, 100, 101, 102]) + b"\x00" + bytes([3, 4, 5, 103, 104, 105])


def test_snapshot_reports_hands_stats_and_gesture_events(state):
    t = feed(state, 0.3)  # open hand...
    t = feed(state, 0.6, t0=t, d_index=PINCHED)  # ...then hold a pinch: mouse mode turns on
    feed(state, 0.3, t0=t)
    snap = state.snapshot(since_seq=0)
    json.dumps(snap)  # must be valid JSON for the page
    assert snap["hands"][0]["side"] == "right"
    assert snap["stats"]["seen"] == 1.0 and snap["stats"]["fps"] == pytest.approx(100, rel=0.05)
    assert snap["engine"]["state"] == "engaged"
    assert {"kind": "mode", "on": True} in [{k: e[k] for k in ("kind", "on")} for e in snap["events"]
                                            if e["kind"] == "mode"]
    assert state.snapshot(since_seq=snap["last_seq"])["events"] == []  # only new events are resent


def test_jitter_and_distance(state):
    feed(state, 1.0, x=30.0, height=400.0)
    stats = state.stats()
    assert stats["jitter_mm"] == 0.0
    assert stats["distance_mm"] == round((30 ** 2 + 400 ** 2) ** 0.5)


def test_config_reloads_when_calibration_appears(state, tmp_path):
    assert state.config()["calibrated"] is False
    version = state.config_version
    (tmp_path / "calibration.json").write_text(json.dumps({
        "tracking_mode": "hmd", "right_axis": [1, 0, 0], "up_axis": [0, 0, -1], "lift_axis": [0, 1, 0],
        "keyboard_level": 100, "raised_level": 200, "mouse_position": [0, 200, 0],
        "pinch_closed_mm": 15, "pinch_open_mm": 75}))
    state._checked_at = 0.0
    state.reload_if_changed()
    config = state.config()
    assert state.config_version == version + 1
    assert config["calibrated"] and config["raise"] == {"on": 0.5, "off": 0.3}
    assert config["height_problem"] is None
    assert config["pinch"]["on"] == pytest.approx(45.0)


def test_mode_scan_picks_the_mode_that_sees_the_hand(state):
    current = {"mode": None, "t": 0.0}

    def set_mode(mode):
        current["mode"] = mode

    def sleep(seconds):  # time passes as frames; only "hmd" sees the right hand
        side = "right" if current["mode"] == "hmd" else "left"
        current["t"] = feed(state, seconds, t0=current["t"], side=side)

    state.run_scan(set_mode, sleep=sleep)
    assert state.scan["best"] == "hmd" and current["mode"] == "hmd"
    assert state.scan["results"]["hmd"]["seen"] == 1.0
    assert state.scan["results"]["desktop"]["seen"] == 0.0


def test_http_endpoints(state):
    modes = []
    server = ViewerServer(state, modes.append, port=0).start()
    port = server.server_address[1]

    def request(method, path, body=None):
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request(method, path, body=body)
        response = conn.getresponse()
        return response.status, response.read()

    try:
        status, page = request("GET", "/")
        assert status == 200 and b"Tracker view" in page
        assert request("GET", "/camera.png")[0] == 204  # no images yet
        state.on_images(2, 1, [b"\x10\x20", b"\x30\x40"])
        status, png = request("GET", "/camera.png")
        assert status == 200 and png.startswith(b"\x89PNG")
        assert request("POST", "/mode", "sideways")[0] == 400
        assert request("POST", "/mode", "hmd")[0] == 200
        assert modes == ["hmd"] and state.mode == "hmd"
        assert request("GET", "/nope")[0] == 404

        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("GET", "/events")
        stream = conn.getresponse()
        assert stream.getheader("Content-Type") == "text/event-stream"
        messages = []
        while len(messages) < 2:
            line = stream.fp.readline()
            if line.startswith(b"data: "):
                messages.append(json.loads(line[6:]))
        conn.close()
        assert [m["type"] for m in messages] == ["config", "state"]
        assert messages[0]["screen"] == [1440, 900]
    finally:
        server.stop()
