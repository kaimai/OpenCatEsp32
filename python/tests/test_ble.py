import asyncio
import concurrent.futures
import queue
import threading

import pytest

import petoi.transports.ble as ble
from petoi.errors import ConnectionFailed
from petoi.protocol import LineBuffer
from petoi.transports.ble import BleTransport


class StubClient:
    def __init__(self):
        self.disconnects = 0

    async def disconnect(self):
        self.disconnects += 1


def make_transport():
    t = object.__new__(BleTransport)  # skip __init__: it needs bleak and a robot
    t._loop = asyncio.new_event_loop()
    t._thread = threading.Thread(target=t._loop.run_forever, daemon=True)
    t._thread.start()
    t._client = StubClient()
    t._connected = True
    t._closed = False
    return t


def test_close_twice_is_harmless():
    t = make_transport()
    t.close()
    t.close()  # used to raise "Event loop is closed"
    assert t._client.disconnects == 1


def test_run_times_out_as_connection_failed(monkeypatch):
    monkeypatch.setattr(ble, "RUN_TIMEOUT", 0.1)
    t = make_transport()

    async def never():
        await asyncio.sleep(10)

    with pytest.raises(ConnectionFailed, match="did not respond"):
        t._run(never())
    t.close()


def test_run_limit_can_exceed_run_timeout(monkeypatch):
    monkeypatch.setattr(ble, "RUN_TIMEOUT", 0.05)
    t = make_transport()

    async def scan():
        await asyncio.sleep(0.15)
        return "found"

    assert t._run(scan(), limit=1) == "found"  # a long scan must not hit the per-operation limit
    t.close()


def settling(monkeypatch, on_write, pushed=b""):
    monkeypatch.setattr(ble, "PUSH_WAIT", 0.05)
    monkeypatch.setattr(ble, "GREETING_TIMEOUT", 0.2)
    monkeypatch.setattr(ble, "QUERY_TIMEOUT", 0.2)
    t = object.__new__(BleTransport)
    t._raw, t._raw_lock = bytearray(pushed), threading.Lock()
    t._buffer, t._lines = LineBuffer(), queue.Queue()
    t.write = lambda data: on_write(t, data)
    return t


def test_s3_handshake_without_line_breaks_is_absorbed(monkeypatch):
    def reply(t, data):  # OpenCatEsp32S3 petoiBleUartNimble.h:390-414
        for part in (b"Petoi Quaddle", b"u", b"Quaddle", b"Q_261022", b"?"):
            t._on_notify(None, bytearray(part))

    t = settling(monkeypatch, reply)
    t._settle()
    t._on_notify(None, bytearray(b"k\r\n"))
    assert t.readline(0.1) == "k"  # the handshake did not stick to the next line


def test_biboard_greeting_and_forced_rest_are_absorbed(monkeypatch):
    def reply(t, data):
        t._on_notify(None, bytearray(b"Bittle X\r\nB10_260527\r\n?\r\n"))

    t = settling(monkeypatch, reply, pushed=b"Petoi Bittle Xu\r\nrest\r\nd\r\n")  # src/bleUart.h:161-176
    t._settle()
    assert t.readline(0.05) is None


def test_no_answer_to_question_mark_fails_to_connect(monkeypatch):
    t = settling(monkeypatch, lambda t, data: None)
    with pytest.raises(ConnectionFailed, match="did not answer"):
        t._settle()


class HangingClient:
    """A bleak client whose connect() never finishes, like a robot macOS is slow to reach."""

    made = []

    def __init__(self, address, **kwargs):
        self.disconnects = 0
        self.cancelled = False
        HangingClient.made.append(self)

    async def connect(self):
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            self.cancelled = True
            raise

    async def disconnect(self):
        self.disconnects += 1


def test_abandoned_connect_is_cancelled_and_disconnected(monkeypatch):
    import sys
    import types

    monkeypatch.setattr(ble, "RUN_TIMEOUT", 0.1)
    monkeypatch.setitem(sys.modules, "bleak", types.SimpleNamespace(BleakClient=HangingClient))
    HangingClient.made.clear()
    with pytest.raises(ConnectionFailed, match="did not respond"):
        BleTransport("AA:BB")
    client = HangingClient.made[0]
    assert client.disconnects == 1  # tells the OS to stop connecting
    assert client.cancelled  # the connect task ran its cancellation before the loop stopped


class RecordingClient:
    """A bleak client that records how it was made and fails to connect, ending __init__ early."""

    made = []

    def __init__(self, address, **kwargs):
        self.kwargs = kwargs
        RecordingClient.made.append(self)

    async def connect(self):
        raise OSError("no robot here")

    async def disconnect(self):
        pass


def test_discovers_only_the_uart_service(monkeypatch):
    import sys
    import types

    monkeypatch.setitem(sys.modules, "bleak", types.SimpleNamespace(BleakClient=RecordingClient))
    RecordingClient.made.clear()
    with pytest.raises(ConnectionFailed):
        BleTransport("AA:BB")
    # S3 firmware stalls discovery of its HID Device Information service for 30 s (Part J)
    assert RecordingClient.made[0].kwargs["services"] == [ble.UART_SERVICE]
