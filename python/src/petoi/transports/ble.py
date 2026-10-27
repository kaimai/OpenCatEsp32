from __future__ import annotations

import asyncio
import queue
import threading
from typing import Optional

from petoi.errors import ConnectionFailed
from petoi.protocol import LineBuffer
from petoi.transports.base import StreamTransport

# Nordic UART, src/bleCommon.h:6-8
ROBOT_RX = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"  # we write here
ROBOT_TX = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"  # robot notifies here
NAME_MARK = "_BLE"  # src/bleUart.h:99
CHUNK = 20  # default BLE payload size


class BleTransport(StreamTransport):
    """Bluetooth Low Energy link. Runs bleak on a background event loop."""

    def __init__(self, address: Optional[str] = None, scan_timeout: float = 5.0):
        try:
            import bleak
        except ImportError:
            raise ConnectionFailed('BLE needs an extra package: pip install "petoi[ble]"') from None
        self._bleak = bleak
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()
        self._lines: "queue.Queue[str]" = queue.Queue()
        self._buffer = LineBuffer()
        try:
            address = address or self._run(self._find(scan_timeout))
            self._client = bleak.BleakClient(address)
            self._run(self._client.connect())
            self._run(self._client.start_notify(ROBOT_TX, self._on_notify))
        except ConnectionFailed:
            self._shutdown_loop()
            raise
        except Exception as e:
            self._shutdown_loop()
            raise ConnectionFailed(f"could not connect to BLE device {address}: {e}") from e

    def _run(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result()

    async def _find(self, timeout: float) -> str:
        devices = await self._bleak.BleakScanner.discover(timeout=timeout)
        robots = [d for d in devices if d.name and NAME_MARK in d.name]
        if len(robots) == 1:
            return robots[0].address
        if not robots:
            raise ConnectionFailed("no Petoi BLE robot found; is it powered on and not connected to the app?")
        names = ", ".join(f"{d.name} ({d.address})" for d in robots)
        raise ConnectionFailed(f"several robots found, pass one address: {names}")

    def _on_notify(self, _char, data: bytearray) -> None:
        for line in self._buffer.feed(bytes(data)):
            self._lines.put(line)

    def write(self, data: bytes) -> None:
        for i in range(0, len(data), CHUNK):
            self._run(self._client.write_gatt_char(ROBOT_RX, data[i : i + CHUNK], response=False))

    def readline(self, timeout: float) -> Optional[str]:
        try:
            return self._lines.get(timeout=max(timeout, 0))
        except queue.Empty:
            return None

    def discard_input(self) -> None:
        while not self._lines.empty():
            self._lines.get_nowait()

    def close(self) -> None:
        try:
            self._run(self._client.disconnect())
        finally:
            self._shutdown_loop()

    def _shutdown_loop(self) -> None:
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=2)
