from __future__ import annotations

from typing import List, Optional

from petoi.protocol import parse_ints
from petoi.transports.base import StreamTransport


class MockTransport(StreamTransport):
    """A pretend robot for learning, docs, and tests. Replies like the firmware:
    data lines after '=', then the token echo (src/reaction.h:681-686, 1557).

    Does not model: start angles, 'j<index>', odd argument counts, the 'd' posture."""

    MODEL = "Mock Bittle"
    VERSION = "MOCK_260820"

    def __init__(self, dof: int = 16):
        self.angles = [0] * dof
        self.history: List[bytes] = []
        self._out: List[str] = []

    def write(self, data: bytes) -> None:
        self.history.append(data)
        token = chr(data[0])
        if token.isupper():
            args = [b - 256 if b > 127 else b for b in data[1:-1]]  # int8, drop '~'
        else:
            args = parse_ints(data[1:].decode())
        if token in ("i", "m", "I", "M"):
            for index, angle in zip(args[::2], args[1::2]):
                if 0 <= index < len(self.angles):  # the firmware ignores bad indices (src/reaction.h:882, :1077)
                    self.angles[index] = angle
        elif token == "?":
            self._out += [self.MODEL, self.VERSION]
        elif token == "j":
            self._out += ["=", "\t".join(map(str, range(len(self.angles)))), ",\t".join(map(str, self.angles)) + ","]
        elif data == b"g?\n":
            self._out.append("Gyro state: Update-1 Balance-1 Print-0 Frequency-1")  # src/reaction.h:608-612
        elif data == b"gc\n":
            self._out.append("Calibration done.")  # src/imu.h:1102
        elif token == "K" and args and args[0] < 0:
            self._out.append(token)  # a behavior echoes when it starts and when it ends (src/reaction.h:1557, :1609)
        self._out.append(token)

    def readline(self, timeout: float) -> Optional[str]:
        return self._out.pop(0) if self._out else None

    def discard_input(self) -> None:
        self._out.clear()

    def close(self) -> None:
        pass
