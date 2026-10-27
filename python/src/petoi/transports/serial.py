from __future__ import annotations

import time
from typing import List, Optional, Union

import serial

from petoi.errors import ConnectionFailed
from petoi.transports.base import StreamTransport

BAUD = 115200  # OpenCatEsp32.ino:38
READY = "Ready!"  # src/OpenCat.h:771
QUIET_SECONDS = 1.5  # no output this long means the robot was already booted


class SerialTransport(StreamTransport):
    """USB cable, or a paired Bluetooth Classic (_SSP) port."""

    def __init__(self, port: Union[str, serial.SerialBase], boot_timeout: float = 8.0):
        if isinstance(port, str):
            try:
                port = serial.Serial(port, BAUD, timeout=0.1)
            except serial.SerialException as e:
                raise ConnectionFailed(f"could not open {port}: {e}") from e
        self._port = port
        self.boot_log: List[str] = self._wait_for_boot(boot_timeout)

    def _wait_for_boot(self, timeout: float) -> List[str]:
        log: List[str] = []
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            line = self.readline(min(QUIET_SECONDS, deadline - time.monotonic()))
            if line is None:
                break
            log.append(line)
            if line == READY:
                break
        return log

    def write(self, data: bytes) -> None:
        self._port.write(data)
        self._port.flush()

    def readline(self, timeout: float) -> Optional[str]:
        self._port.timeout = max(timeout, 0)
        raw = self._port.readline()
        if not raw:
            return None
        return raw.rstrip(b"\r\n").decode("utf-8", "replace")

    def discard_input(self) -> None:
        self._port.reset_input_buffer()

    def close(self) -> None:
        self._port.close()
