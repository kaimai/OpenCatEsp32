from __future__ import annotations

import collections
import time
import warnings
from typing import Deque, List, Optional, Union

import serial

from petoi.errors import ConnectionFailed
from petoi.protocol import LineBuffer
from petoi.transports.base import StreamTransport

BAUD = 115200  # OpenCatEsp32.ino:38
READY = "Ready!"  # src/OpenCat.h:771
QUIET_SECONDS = 1.5  # no output this long means the robot was already booted


READ_SLICE = 0.05  # port read timeout; readline() loops over slices


class SerialTransport(StreamTransport):
    """USB cable, or a paired Bluetooth Classic (_SSP) port."""

    def __init__(self, port: Union[str, serial.SerialBase], boot_timeout: float = 20.0):
        if isinstance(port, str):
            try:
                port = serial.Serial(port, BAUD, timeout=READ_SLICE)
            except serial.SerialException as e:
                raise ConnectionFailed(f"could not open {port}: {e}") from e
        else:
            port.timeout = READ_SLICE
        self._port = port
        self._buffer = LineBuffer()
        self._lines: Deque[str] = collections.deque()
        try:
            self.boot_log: List[str] = self._wait_for_boot(boot_timeout)
        except BaseException:
            port.close()
            raise

    def _wait_for_boot(self, timeout: float) -> List[str]:
        # Boot has long silent stretches (IMU convergence, src/imu.h:739+) and
        # may stop at a Y/n prompt on a new board (src/imu.h:1013). So: silence
        # before any output means already booted; after output, wait for Ready!.
        log: List[str] = []
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            line = self.readline(min(QUIET_SECONDS, deadline - time.monotonic()))
            if line is None:
                if not log:
                    return log
                continue
            log.append(line)
            if line == READY:
                return log
        if log:
            warnings.warn(
                f"the robot did not finish booting within {timeout}s (no {READY!r}); it may be "
                "waiting at a calibration prompt. Open a serial monitor to check.",
                RuntimeWarning,
                stacklevel=3,
            )
        return log

    def write(self, data: bytes) -> None:
        try:
            self._port.write(data)
            self._port.flush()
        except serial.SerialException as e:
            raise ConnectionFailed(f"lost connection to {self._name()}: {e}") from e

    def readline(self, timeout: float) -> Optional[str]:
        deadline = time.monotonic() + timeout
        while not self._lines:
            try:
                data = self._port.read(self._port.in_waiting or 1)
            except serial.SerialException as e:
                raise ConnectionFailed(f"lost connection to {self._name()}: {e}") from e
            if data:
                self._lines.extend(self._buffer.feed(data))
            if not self._lines and time.monotonic() >= deadline:
                return None  # a partial line stays buffered
        return self._lines.popleft()

    def discard_input(self) -> None:
        try:
            self._port.reset_input_buffer()
        except serial.SerialException as e:
            raise ConnectionFailed(f"lost connection to {self._name()}: {e}") from e
        self._buffer = LineBuffer()
        self._lines.clear()

    def _name(self) -> str:
        return getattr(self._port, "port", None) or getattr(self._port, "name", None) or "the robot"

    def close(self) -> None:
        self._port.close()
