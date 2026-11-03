import builtins
import sys
import warnings

import pytest
from serial.tools.list_ports_common import ListPortInfo

from conftest import FakeStream

import petoi
from petoi.connect import _check_firmware, classify, pick_serial_port
from petoi.errors import ConnectionFailed
from petoi.robot import Robot
from petoi.transports.mock import MockTransport


def port(device, description=""):
    p = ListPortInfo(device)
    p.description = description
    return p


@pytest.mark.parametrize(
    "target, kind",
    [
        (None, ("serial", None)),
        ("/dev/cu.usbserial-1420", ("serial", "/dev/cu.usbserial-1420")),
        ("COM3", ("serial", "COM3")),
        ("bluetooth", ("bluetooth", None)),
        ("ble", ("ble", None)),
        ("ble:AA:BB:CC:DD:EE:FF", ("ble", "AA:BB:CC:DD:EE:FF")),
        ("192.168.4.1", ("wifi", "192.168.4.1")),
        ("ws://10.0.0.5:81", ("wifi", "ws://10.0.0.5:81")),
        ("bittle.local", ("wifi", "bittle.local")),
        ("bittle.local:81", ("wifi", "bittle.local:81")),
        ("mock", ("mock", None)),
    ],
)
def test_classify(target, kind):
    assert classify(target) == kind


def test_pick_single_usb_port():
    ports = [port("/dev/cu.Bluetooth-Incoming-Port"), port("/dev/cu.usbserial-1420", "USB Serial")]
    assert pick_serial_port(ports, bluetooth=False) == "/dev/cu.usbserial-1420"


def test_pick_bluetooth_ssp_port():
    ports = [port("/dev/cu.usbserial-1420"), port("/dev/cu.BittleX1A2B_SSP")]
    assert pick_serial_port(ports, bluetooth=True) == "/dev/cu.BittleX1A2B_SSP"


def test_ambiguous_ports_list_choices():
    ports = [port("/dev/cu.usbserial-1"), port("/dev/cu.usbserial-2")]
    with pytest.raises(ConnectionFailed, match="usbserial-1.*usbserial-2"):
        pick_serial_port(ports, bluetooth=False)


def test_no_ports():
    with pytest.raises(ConnectionFailed, match="No robot"):
        pick_serial_port([], bluetooth=False)


def test_connect_mock_reads_model_and_firmware():
    robot = petoi.connect("mock")
    assert robot.model == MockTransport.MODEL
    assert robot.firmware == MockTransport.VERSION


def test_old_firmware_warns_but_connects(monkeypatch):
    monkeypatch.setattr(MockTransport, "VERSION", "B10_250101")
    with pytest.warns(RuntimeWarning, match="older than"):
        robot = petoi.connect("mock")
    assert robot.firmware == "B10_250101"


def test_silent_firmware_warns(monkeypatch):
    monkeypatch.setattr(MockTransport, "write", lambda self, data: None)  # robot never answers
    with pytest.warns(RuntimeWarning, match="did not answer"):
        petoi.connect("mock", timeout=0.1)


def test_connect_ble_without_bleak_gives_install_hint(monkeypatch):
    real_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name == "bleak":
            raise ImportError
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(ConnectionFailed, match=r"petoi\[ble\]"):
        petoi.connect("ble")


def test_transport_is_closed_if_firmware_check_raises(monkeypatch):
    closed = []
    monkeypatch.setattr(MockTransport, "close", lambda self: closed.append(True))
    monkeypatch.setattr(sys.modules["petoi.connect"], "_check_firmware", lambda robot: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(RuntimeError):
        petoi.connect("mock")
    assert closed == [True]


def test_bluetooth_without_match_explains_explicit_port_on_windows_and_linux():
    with pytest.raises(ConnectionFailed, match="rfcomm"):
        pick_serial_port([], bluetooth=True)


def test_connect_timeout_is_also_the_ble_scan_time(monkeypatch):
    import petoi.transports.ble as ble

    seen = {}

    def fake(address=None, scan_timeout=None):
        seen.update(address=address, scan_timeout=scan_timeout)
        raise ConnectionFailed("stop here")

    monkeypatch.setattr(ble, "BleTransport", fake)
    with pytest.raises(ConnectionFailed):
        petoi.connect("ble", timeout=9)
    assert seen == {"address": None, "scan_timeout": 9}


QUADDLE = {b"?\n": ["Quaddle", "Q_261022", "?"], b"z0\n": ["z0"]}  # OpenCatEsp32S3 reaction.h:1181-1185, :1324


def test_s3_robot_is_told_to_stop_moving_on_its_own():
    robot = Robot(FakeStream(QUADDLE), timeout=0.2)
    _check_firmware(robot)
    assert robot.s3 and robot.model == "Quaddle"
    assert robot.transport.written == [b"?\n", b"z0\n"]


def test_esp32_robot_never_gets_z0():
    robot = Robot(FakeStream({b"?\n": ["Bittle X", "B10_260527", "?"]}), timeout=0.2)
    _check_firmware(robot)  # 'z' toggles random mode on OpenCatEsp32 (src/reaction.h:494-498)
    assert not robot.s3 and robot.transport.written == [b"?\n"]


def test_unconfirmed_z0_warns():
    robot = Robot(FakeStream({b"?\n": ["Quaddle", "Q_261022", "?"]}, auto_echo=False), timeout=0.1)
    with pytest.warns(RuntimeWarning, match="move on its own"):
        _check_firmware(robot)


class WakesOnFirstCommand(FakeStream):
    """A sleeping Quaddle wakes on the first command and doesn't answer it (opencat-gemma QUADDLE_S3_NOTES.md)."""

    def write(self, data):
        if not self.written:
            self.written.append(data)
            self.pending += ["Charge sleep: serial wake", "auto z1"]
            return
        super().write(data)


def test_question_mark_is_retried_once_for_a_sleeping_robot():
    robot = Robot(WakesOnFirstCommand(QUADDLE), timeout=0.1)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        _check_firmware(robot)
    assert robot.firmware == "Q_261022"


def test_bluetooth_classic_hint_mentions_s3_robots():
    with pytest.raises(ConnectionFailed, match="Quaddle"):
        pick_serial_port([], bluetooth=True)
