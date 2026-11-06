import threading

import pytest
import serial

from petoi.errors import ConnectionFailed
from petoi.robot import Robot
from petoi.transports.serial import SerialTransport


def make_loop():
    port = serial.serial_for_url("loop://", timeout=0.1)
    return SerialTransport(port=port, boot_timeout=0)


def test_writes_reach_the_port_and_lines_come_back():
    t = make_loop()
    t.write(b"hello\r\n")
    assert t.readline(0.5) == "hello"


def test_readline_returns_none_on_silence():
    assert make_loop().readline(0.1) is None


def test_command_round_trip_over_loopback():
    t = make_loop()
    # loop:// echoes our bytes, so "k\n" comes back as the completion echo
    assert t.command("k", b"k\n", timeout=0.5).completed


def test_boot_wait_stops_at_ready():
    port = serial.serial_for_url("loop://", timeout=0.1)
    port.write(b"Init\r\nReady!\r\n")
    t = SerialTransport(port=port, boot_timeout=2.0)
    assert t.boot_log == ["Init", "Ready!"]


def test_bad_port_name_raises_connection_failed():
    with pytest.raises(ConnectionFailed, match="could not open"):
        SerialTransport("/dev/does-not-exist-petoi", boot_timeout=0)


def test_partial_line_is_held_until_complete():
    port = serial.serial_for_url("loop://", timeout=0.1)
    t = SerialTransport(port=port, boot_timeout=0)
    port.write(b"0,\t-3")
    assert t.readline(0.2) is None
    port.write(b",\t45,\r\n")
    assert t.readline(0.5) == "0,\t-3,\t45,"


def test_discard_input_drops_buffered_partial_and_ready_lines():
    port = serial.serial_for_url("loop://", timeout=0.1)
    t = SerialTransport(port=port, boot_timeout=0)
    port.write(b"a\r\nb\r\nc")
    assert t.readline(0.5) == "a"
    t.discard_input()
    port.write(b"d\r\n")
    assert t.readline(0.5) == "d"


def test_boot_wait_keeps_waiting_through_a_silent_stretch(monkeypatch):
    import threading
    import time

    import petoi.transports.serial as mod

    monkeypatch.setattr(mod, "QUIET_SECONDS", 0.2)
    port = serial.serial_for_url("loop://", timeout=0.1)
    port.write(b"Init\r\n")
    threading.Timer(0.5, lambda: port.write(b"Ready!\r\n")).start()
    t = SerialTransport(port=port, boot_timeout=3.0)
    assert "Ready!" in t.boot_log


def test_boot_wait_warns_when_ready_never_arrives(monkeypatch):
    port = serial.serial_for_url("loop://", timeout=0.1)
    port.write(b"Init\r\n")
    with pytest.warns(RuntimeWarning, match="calibration prompt"):
        SerialTransport(port=port, boot_timeout=0.3)


class BrokenPort:
    def __init__(self):
        self.closed = False
        self.in_waiting = 0

    def read(self, n):
        raise serial.SerialException("device disconnected")

    def write(self, data):
        raise serial.SerialException("device disconnected")

    def flush(self):
        pass

    def reset_input_buffer(self):
        pass

    def close(self):
        self.closed = True


def test_serial_errors_become_connection_failed():
    t = SerialTransport(port=BrokenPort(), boot_timeout=0)
    with pytest.raises(ConnectionFailed, match="lost connection"):
        t.readline(0.1)
    with pytest.raises(ConnectionFailed, match="lost connection"):
        t.write(b"k\n")


def test_port_is_closed_if_boot_wait_fails():
    port = BrokenPort()
    with pytest.raises(ConnectionFailed):
        SerialTransport(port=port, boot_timeout=1.0)
    assert port.closed


def test_setup_wifi_reads_through_the_reboot_over_loopback():
    port = serial.serial_for_url("loop://", timeout=0.1)
    robot = Robot(SerialTransport(port=port, boot_timeout=0))
    ip = b"Successfully connected Wifi to IP Address: 192.168.1.23\r\n"
    reboot = ip + b"Rebooting to use web server.\r\n\xff\x00ets Jun  8 2016\r\n" + ip + b"Ready!\r\n"
    timer = threading.Timer(0.2, port.write, [reboot])  # after setup_wifi has discarded and written
    timer.start()
    try:
        assert robot.setup_wifi("Home", "pw-12345", timeout=3) == "192.168.1.23"
    finally:
        timer.cancel()


class _RecordingPort:
    in_waiting = 0

    def __init__(self):
        self.writes = []

    def write(self, data):
        self.writes.append(bytes(data))

    def flush(self):
        pass

    def read(self, n):
        return b""

    def reset_input_buffer(self):
        pass

    def close(self):
        pass


def test_long_write_sends_its_start_alone_then_pauses(monkeypatch):
    import petoi.transports.serial as serial_transport

    slept = []
    monkeypatch.setattr(serial_transport.time, "sleep", slept.append)
    port = _RecordingPort()
    t = SerialTransport(port, boot_timeout=0)
    payload = bytes(range(1, 101)) + b"~"
    t.write(payload)
    assert port.writes == [payload[:64], payload[64:]]
    assert slept == [serial_transport.CHUNK_PAUSE]


def test_short_write_goes_out_whole(monkeypatch):
    import petoi.transports.serial as serial_transport

    slept = []
    monkeypatch.setattr(serial_transport.time, "sleep", slept.append)
    port = _RecordingPort()
    t = SerialTransport(port, boot_timeout=0)
    t.write(b"kup\n")
    assert port.writes == [b"kup\n"] and slept == []
