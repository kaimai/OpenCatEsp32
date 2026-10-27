import asyncio
import concurrent.futures
import threading

import pytest

import petoi.transports.ble as ble
from petoi.errors import ConnectionFailed
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
