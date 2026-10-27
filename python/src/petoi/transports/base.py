from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Optional

from petoi.protocol import Reply, collect_reply


class Transport(ABC):
    """A link to one robot."""

    @abstractmethod
    def command(self, token: str, payload: bytes, timeout: Optional[float]) -> Reply:
        """Send one encoded command; wait up to timeout seconds (0 = don't wait)."""

    @abstractmethod
    def close(self) -> None: ...


class StreamTransport(Transport):
    """USB serial, Bluetooth Classic, BLE, and the mock: all are streams of text lines."""

    @abstractmethod
    def write(self, data: bytes) -> None: ...

    @abstractmethod
    def readline(self, timeout: float) -> Optional[str]:
        """One line without its line ending, or None if nothing arrived in time."""

    @abstractmethod
    def discard_input(self) -> None: ...

    def command(self, token: str, payload: bytes, timeout: Optional[float]) -> Reply:
        self.discard_input()  # so an old echo can't be mistaken for this one
        self.write(payload)
        if not timeout:
            return Reply(token)
        deadline = time.monotonic() + timeout

        def next_line():
            remaining = deadline - time.monotonic()
            return self.readline(remaining) if remaining > 0 else None

        return collect_reply(token, next_line)
