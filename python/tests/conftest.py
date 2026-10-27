from __future__ import annotations

from petoi.transports.base import StreamTransport


class FakeStream(StreamTransport):
    """Records writes. Answers with scripted lines, or by echoing the token."""

    def __init__(self, replies: dict[bytes, list[str]] | None = None, auto_echo: bool = True):
        self.replies = replies or {}
        self.auto_echo = auto_echo
        self.written: list[bytes] = []
        self.pending: list[str] = []
        self.discards = 0
        self.closed = False

    def write(self, data: bytes) -> None:
        self.written.append(data)
        if data in self.replies:
            self.pending.extend(self.replies[data])
        elif self.auto_echo:
            self.pending.append(chr(data[0]))

    def readline(self, timeout: float):
        return self.pending.pop(0) if self.pending else None

    def discard_input(self) -> None:
        self.discards += 1
        self.pending.clear()

    def close(self) -> None:
        self.closed = True
