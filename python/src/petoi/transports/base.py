from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import List, Optional, Tuple

from petoi.protocol import Reply, collect_reply


STALE_SECONDS = 15.0  # longest one-shot skill we expect to take before it echoes


class Transport(ABC):
    """A link to one robot."""

    @abstractmethod
    def command(self, token: str, payload: bytes, timeout: float) -> Reply:
        """Send one encoded command and wait up to timeout seconds for its echo.

        timeout=0 means do not wait: send and return an incomplete Reply."""

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

    @property
    def _unconfirmed(self) -> List[Tuple[str, float]]:
        # (token, expiry) of commands whose echo we haven't seen; lazy so
        # subclasses needn't call super().__init__()
        try:
            return self.__unconfirmed
        except AttributeError:
            self.__unconfirmed: List[Tuple[str, float]] = []
            return self.__unconfirmed

    def command(self, token: str, payload: bytes, timeout: float) -> Reply:
        # The protocol has no command IDs and one-shot skills echo only when
        # finished, so a late echo from an earlier command can arrive now.
        pending = self._unconfirmed
        now = time.monotonic()
        pending[:] = [(t, exp) for t, exp in pending if exp > now]
        if not pending:
            self.discard_input()  # nothing is owed, so anything buffered is junk
        self.write(payload)
        return self.expect(token, timeout)

    def expect(self, token: str, timeout: float) -> Reply:
        """Wait for one more echo of token without sending; timeout=0 only marks it as owed."""
        pending = self._unconfirmed
        entry = (token, time.monotonic() + STALE_SECONDS)
        if not timeout:
            pending.append(entry)
            return Reply(token)
        deadline = time.monotonic() + timeout
        consumed_own = False

        def next_line():
            nonlocal consumed_own
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                line = self.readline(remaining)
                if line is not None:
                    hit = next((i for i, (t, _) in enumerate(pending) if t == line.strip()), None)
                    if hit is not None:
                        # a late echo; earlier entries ahead of it were lost
                        consumed_own = consumed_own or line.strip() == token
                        del pending[: hit + 1]
                        continue
                return line

        reply = collect_reply(token, next_line)
        if not reply.completed:
            if consumed_own:
                pending.clear()  # the echo we swallowed as stale was most likely our own
            else:
                pending.append(entry)
        return reply
