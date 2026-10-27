import builtins
import sys

import pytest
from serial.tools.list_ports_common import ListPortInfo

import petoi
from petoi.connect import classify, pick_serial_port
from petoi.errors import ConnectionFailed
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
