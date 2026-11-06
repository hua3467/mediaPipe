"""Checks the Leap adapter against a fake `leap` module shaped like Ultraleap's bindings."""
import enum
import sys
import types
from contextlib import contextmanager
from types import SimpleNamespace as NS

import pytest

from hand_cursor.leap_source import LeapSource, LeapUnavailable


def V(x, y, z):
    return NS(x=x, y=y, z=z)


def bone(a, b):
    return NS(prev_joint=V(*a), next_joint=V(*b))


def tip(x, y, z):
    """A finger whose bones run from the wrist area (0, 150, 60) to the tip (x, y, z)."""
    base, knuckle = (0, 150, 60), (x, 190, 45)
    return NS(metacarpal=bone(base, knuckle), proximal=bone(knuckle, (x, 200, 40)),
              intermediate=bone((x, 200, 40), (x, 205, 35)), distal=bone((x, 205, 35), (x, y, z)))


class HandType(enum.Enum):
    Left = 0
    Right = 1


class TrackingMode(enum.Enum):
    Desktop = 0
    HMD = 1
    ScreenTop = 2


class PolicyFlag(enum.Enum):
    Images = 2

SDK = "/Applications/Ultraleap Hand Tracking.app/Contents/LeapSDK"


@pytest.fixture
def fake_leap(monkeypatch):
    module = types.ModuleType("leap")
    module.HandType = HandType
    module.TrackingMode = TrackingMode

    class Listener:
        pass

    class Connection:
        instances = []
        current = TrackingMode.ScreenTop  # the service's mode: shared and persistent, as in Ultraleap
        confirms = True

        def __init__(self):
            self.listeners, self.modes, self.policies, self.is_open = [], [], [], False
            Connection.instances.append(self)

        def get_tracking_mode(self):
            return Connection.current

        def set_tracking_mode(self, mode):
            self.modes.append(mode)
            if Connection.confirms:
                Connection.current = mode
                for listener in self.listeners:
                    listener.on_tracking_mode_event(NS(current_tracking_mode=mode))

        def set_policy_flags(self, flags_to_set=None, flags_to_clear=None):
            self.policies += [f.name for f in flags_to_set or []]

        def add_listener(self, listener):
            self.listeners.append(listener)

        @contextmanager
        def open(self):
            self.is_open = True
            yield self
            self.is_open = False

    module.Listener, module.Connection = Listener, Connection
    enums = types.ModuleType("leap.enums")
    enums.PolicyFlag = PolicyFlag
    module.enums = enums
    monkeypatch.setitem(sys.modules, "leap", module)
    monkeypatch.setitem(sys.modules, "leap.enums", enums)
    return module


def leap_hand(side, palm=(10.0, 200.0, -5.0)):
    return NS(type=side, confidence=1.0, pinch_strength=0.2, grab_strength=0.0,
              palm=NS(position=V(*palm), width=84.0, normal=V(0, -1, 0), direction=V(0, 0, -1)),
              thumb=tip(0, 210, 30), index=tip(25, 210, 30), middle=tip(0, 250, 30),
              ring=tip(-20, 240, 30), pinky=tip(-40, 230, 30), arm=bone((0, 50, 250), (0, 150, 60)))


def test_connects_sets_mode_and_converts_hands(fake_leap):
    frames = []
    with LeapSource(frames.append, "hmd") as source:
        conn = fake_leap.Connection.instances[-1]
        assert conn.is_open and conn.modes == [TrackingMode.HMD]
        listener = conn.listeners[0]
        listener.on_tracking_event(NS(timestamp=5_000_000, hands=[leap_hand(HandType.Right),
                                                                   leap_hand(HandType.Left)]))
        listener.on_tracking_event(NS(timestamp=5_010_000, hands=[]))
        source.set_mode("screentop")
        assert conn.modes[-1] == TrackingMode.ScreenTop
    assert not conn.is_open

    right, left = frames[0].hands
    assert (right.side, left.side) == ("right", "left")
    assert right.palm == (10.0, 200.0, -5.0) and right.palm_width == 84.0
    assert right.thumb_index == pytest.approx(25.0) and right.thumb_middle == pytest.approx(40.0)
    assert len(right.joints) == 5 and all(len(f) == 5 for f in right.joints)
    assert right.joints[1][-1] == (25.0, 210.0, 30.0)  # index fingertip
    assert right.arm == ((0.0, 50.0, 250.0), (0.0, 150.0, 60.0)) and right.normal == (0.0, -1.0, 0.0)
    assert right.direction == (0.0, 0.0, -1.0)
    assert frames[1].t - frames[0].t == pytest.approx(0.010)  # spacing from capture timestamps


def test_camera_images_are_copied_from_the_c_struct(fake_leap, monkeypatch):
    monkeypatch.syspath_prepend(SDK)  # where the real bindings find the compiled module
    leapc = pytest.importorskip("leapc_cffi")  # needs the installed Ultraleap SDK
    ffi = leapc.ffi
    pixels = ffi.new("uint8_t[]", bytes(range(8)) + bytes(range(10, 18)))  # both cameras, one buffer
    owners, structs = [], []
    for offset in (0, 8):
        image = ffi.new("LEAP_IMAGE *")
        image.properties.width, image.properties.height, image.properties.bpp = 4, 2, 1
        image.data, image.offset = pixels, offset
        owners.append(image)
        structs.append(NS(_data=image[0]))
    received = []
    with LeapSource(lambda f: None, "desktop", on_images=lambda *a: received.append(a)) as source:
        source._images(NS(image=structs))
        source._images(NS(image=structs))  # within 1/15 s: skipped by the frame-rate cap
    assert received == [(4, 2, [bytes(range(8)), bytes(range(10, 18))])]
    assert fake_leap.Connection.instances[-1].policies == ["Images"]


def test_keeps_the_trackers_current_mode_by_default(fake_leap):
    with LeapSource(lambda f: None) as source:
        assert source.mode == "screentop"  # as set in Ultraleap Control Panel
        assert fake_leap.Connection.instances[-1].modes == []  # nothing was switched


def test_follows_mode_changes_made_by_other_apps(fake_leap):
    seen = []
    with LeapSource(lambda f: None, on_mode=seen.append) as source:
        listener = fake_leap.Connection.instances[-1].listeners[0]
        listener.on_tracking_mode_event(NS(current_tracking_mode=TrackingMode.Desktop))
        assert source.mode == "desktop"
    assert seen == ["screentop", "desktop"]


def test_unconfirmed_mode_switch_is_an_error(fake_leap, monkeypatch):
    import hand_cursor.leap_source as leap_source
    monkeypatch.setattr(leap_source, "MODE_CONFIRM_S", 0.05)
    fake_leap.Connection.confirms = False
    with pytest.raises(LeapUnavailable, match="did not switch to Desktop"):
        with LeapSource(lambda f: None, "desktop"):
            pass


def test_device_lost_reports_an_empty_frame(fake_leap):
    frames, log = [], []
    with LeapSource(frames.append, "desktop", log=log.append):
        fake_leap.Connection.instances[-1].listeners[0].on_device_lost_event(NS())
    assert frames[-1].hands == () and any("lost" in line for line in log)


def test_missing_bindings_give_setup_hint(monkeypatch):
    monkeypatch.setitem(sys.modules, "leap", None)  # makes `import leap` fail
    with pytest.raises(LeapUnavailable, match="setup.sh"):
        with LeapSource(lambda f: None):
            pass
