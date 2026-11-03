from __future__ import annotations

import asyncio
import concurrent.futures
import queue
import threading
import time
from typing import Any, Optional

from petoi.errors import ConnectionFailed
from petoi.protocol import LineBuffer
from petoi.transports.base import StreamTransport

# Nordic UART, src/bleCommon.h:6-8
ROBOT_RX = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"  # we write here
ROBOT_TX = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"  # robot notifies here
NAME_MARK = "_BLE"  # src/bleUart.h:99
CHUNK = 20  # default BLE payload size
RUN_TIMEOUT = 15.0  # seconds any single BLE operation may take
# What a robot sends when the link opens, measured by opencat-gemma (Bittle X and Quaddle, 2026-10-23)
PUSH_WAIT = 2.0  # BiBoard pushes its greeting within this
GREETING_TIMEOUT = 8.0  # then its forced rest ends with "d"
QUERY_TIMEOUT = 5.0  # the reply to our '?'


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
        self._client: Any = None  # bleak.BleakClient; bleak is an optional import
        self._chunk = CHUNK
        self._connected = False
        self._closed = False
        self._raw: Optional[bytearray] = bytearray()
        self._raw_lock = threading.Lock()
        try:
            address = address or self._run(self._find(scan_timeout), limit=scan_timeout + RUN_TIMEOUT)
            self._client = bleak.BleakClient(address)
            self._run(self._client.connect())
            self._connected = True
            self._run(self._client.start_notify(ROBOT_TX, self._on_notify))
            self._chunk = self._negotiated_chunk()
            self._settle()
        except BaseException as e:  # incl. KeyboardInterrupt: clean up, then re-raise
            self._cleanup()
            if isinstance(e, Exception) and not isinstance(e, ConnectionFailed):
                where = f" {address}" if address else ""
                raise ConnectionFailed(f"could not connect to BLE device{where}: {e}") from e
            raise

    def _negotiated_chunk(self) -> int:
        try:
            char = self._client.services.get_characteristic(ROBOT_RX)
            return max(int(char.max_write_without_response_size), 1)  # bleak >= 0.22
        except Exception:
            return CHUNK

    def _cleanup(self) -> None:
        if self._connected:
            try:
                self._run(self._client.disconnect())
            except Exception:
                pass
            self._connected = False
        self._shutdown_loop()

    def _run(self, coro, limit: Optional[float] = None):
        limit = RUN_TIMEOUT if limit is None else limit
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        try:
            return future.result(timeout=limit)
        except concurrent.futures.TimeoutError:
            future.cancel()
            raise ConnectionFailed(f"the BLE robot did not respond within {limit:g}s") from None

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
        with self._raw_lock:
            if self._raw is not None:  # still connecting: _settle() reads the raw bytes
                self._raw += data
                return
        for line in self._buffer.feed(bytes(data)):
            self._lines.put(line)

    def _raw_text(self) -> str:
        with self._raw_lock:
            return bytes(self._raw or b"").decode("utf-8", "replace")

    def _wait_raw(self, done, timeout: float) -> bool:
        end = time.monotonic() + timeout
        while not done(self._raw_text()):
            if time.monotonic() >= end:
                return False
            time.sleep(0.01)
        return True

    def _settle(self) -> None:
        """Take in what each firmware sends when the link opens, so it isn't read as a command's reply.

        BiBoard pushes "Petoi <MODEL>" and then rests, ending with "d" (src/bleUart.h:161-176). S3 firmware
        pushes nothing, but answers the first '?' with "Petoi <MODEL>u<MODEL><version>?" and no line breaks
        (OpenCatEsp32S3 petoiBleUartNimble.h:390-414). Asking '?' once here covers both (opencat-gemma ble.py)."""
        if self._wait_raw(bool, PUSH_WAIT):
            self._wait_raw(lambda text: "d" in _complete_lines(text), GREETING_TIMEOUT)  # no "d" seen: '?' still works
        with self._raw_lock:
            self._raw = bytearray()
        self.write(b"?\n")
        answered = self._wait_raw(
            lambda text: "?" in _complete_lines(text) or ("Petoi" in text and text.strip().endswith("?")), QUERY_TIMEOUT)
        if not answered:
            raise ConnectionFailed(f"the BLE robot did not answer '?' within {QUERY_TIMEOUT:g}s")
        with self._raw_lock:
            self._raw = None
        self.discard_input()

    def write(self, data: bytes) -> None:
        try:
            for i in range(0, len(data), self._chunk):
                self._run(self._client.write_gatt_char(ROBOT_RX, data[i : i + self._chunk], response=False))
        except Exception as e:
            raise ConnectionFailed(f"lost BLE connection: {e}") from e

    def readline(self, timeout: float) -> Optional[str]:
        try:
            return self._lines.get(timeout=max(timeout, 0))
        except queue.Empty:
            return None

    def discard_input(self) -> None:
        self._buffer = LineBuffer()
        while not self._lines.empty():
            self._lines.get_nowait()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._cleanup()

    def _shutdown_loop(self) -> None:
        if self._loop.is_closed():
            return
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=2)
        if not self._thread.is_alive():
            self._loop.close()


def _complete_lines(text: str) -> list:
    return [line.strip() for line in text.split("\n")[:-1]]
