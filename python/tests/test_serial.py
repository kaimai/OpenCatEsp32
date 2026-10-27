import pytest
import serial

from petoi.errors import ConnectionFailed
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
