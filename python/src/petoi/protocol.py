"""Encode commands for the OpenCat firmware and decode its replies.

Wire rules come from the firmware's src/moduleManager.h (read_serial) and
src/reaction.h (completion echo). This module does no I/O.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Union

BINARY_TERMINATOR = b"~"
_TILDE = 126


def _arg(a: Union[int, str]) -> str:
    if isinstance(a, Enum):
        a = a.value
    return str(int(a)) if isinstance(a, int) else str(a)


def encode(token: str, *args: Union[int, str]) -> bytes:
    """Build the bytes for one command.

    Lowercase tokens are ASCII ("i8 30\\n"); uppercase tokens are binary,
    one signed byte per argument, ended by '~'.
    """
    if len(token) != 1:
        raise ValueError(f"token must be one character, got {token!r}")
    if token.isupper():
        values = [int(_arg(a)) for a in args]
        for v in values:
            if not -128 <= v <= 127:
                raise ValueError(f"binary argument {v} is outside the int8 range -128..127")
            if v == _TILDE:
                raise ValueError("binary argument 126 collides with the '~' terminator; use 125 or 127")
        return token.encode() + bytes(v & 0xFF for v in values) + BINARY_TERMINATOR
    return (token + " ".join(_arg(a) for a in args) + "\n").encode()


_DATA_MARKER = "="


@dataclass
class Reply:
    """What the robot printed in answer to one command."""

    token: str
    lines: List[str] = field(default_factory=list)
    completed: bool = False  # True once the robot echoed the token back

    @property
    def text(self) -> str:
        return "\n".join(self.lines)


def collect_reply(token: str, next_line) -> Reply:
    """Read lines from next_line() until the token echo or None (timeout)."""
    lines: List[str] = []
    while True:
        line = next_line()
        if line is None:
            return Reply(token, lines, completed=False)
        line = line.strip()
        if line == token:
            return Reply(token, lines, completed=True)
        if line and line != _DATA_MARKER:
            lines.append(line)


def parse_ints(line: str) -> List[int]:
    return [int(x) for x in re.findall(r"-?\d+", line)]


class LineBuffer:
    """Turn arbitrary byte chunks (BLE notifications) into complete lines."""

    def __init__(self) -> None:
        self._buf = b""

    def feed(self, data: bytes) -> List[str]:
        self._buf += data
        *complete, self._buf = self._buf.split(b"\n")
        return [c.rstrip(b"\r").decode("utf-8", "replace") for c in complete]
