# Petoi Python API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A pip-installable `petoi` package that lets a beginner control an OpenCat ESP32 robot (Bittle X, Nybble Q, etc.) in three lines over USB serial, Bluetooth Classic, BLE, or Wi-Fi — or a built-in mock robot when they have no hardware. It replaces the old serial scripts, which were tools rather than an API.

**Architecture:** A pure `protocol` module encodes commands and parses replies exactly as the firmware does. Transports move bytes: `StreamTransport` (USB serial, Bluetooth Classic SPP, BLE, and the mock are all line streams) and `WebSocketTransport` (Wi-Fi JSON tasks). A thread-safe `Robot` class gives a raw `send("ksit")` that returns a `Reply`, plus high-level methods (`sit()`, `walk("left")`, `joint(Joint.HEAD_PAN, 30)`) that raise `RobotTimeout` if the robot never confirms. `petoi.connect()` picks the transport from one argument and checks the firmware version.

**Tech Stack:** Python ≥ 3.9, pyserial (core), bleak (extra `ble`), websockets ≥ 12 (extra `wifi`), pytest + pytest-cov, hatchling, GitHub Actions (tests only — no publishing).

---

## Firmware facts this plan relies on (verified in source on 2026-10-27)

| Fact | Source |
|---|---|
| USB serial is 115200 baud | `OpenCatEsp32.ino:38` |
| Lowercase token = ASCII, terminated by `\n`; uppercase token = binary int8 args, terminated by `~` | `src/moduleManager.h:400` |
| Spaces between token and args are trimmed (`"k sit"` == `"ksit"`) | `src/moduleManager.h:427` |
| Byte 126 (`~`) inside binary args breaks parsing; firmware says to use ≤ 125 | `src/moduleManager.h:401` |
| Completion is confirmed by printing the token on its own line | `src/reaction.h:1557`, `:1609` |
| Data replies print `=` first (e.g. `j`, `R`) | `src/reaction.h:681`, `:1106` |
| `j` prints a line of indices, then a line `a0,\ta1,\t...` | `src/reaction.h:685-686`, `src/tools.h:89` |
| `?` prints MODEL then SoftwareVersion = `BOARD_YYMMDD` (e.g. `B10_260820`) | `src/reaction.h:405-406`, `src/OpenCat.h:71-80, 666` |
| Boot ends with `Ready!` on USB serial | `src/OpenCat.h:771` |
| Joint groups: 0 head pan, 1 head tilt, 2 tail, 8–11 shoulder pitch, 12–15 knee | `src/OpenCat.h:235-237` |
| BLE is Nordic UART: service `6E400001-…`, robot RX `6E400002-…`, robot TX `6E400003-…`; device name contains `_BLE` | `src/bleCommon.h:6-8`, `src/bleUart.h:99` |
| Bluetooth Classic SPP device name contains `_SSP` | `src/bluetoothManager.h:73` |
| Wi-Fi: WebSocket on port 81, JSON `{"type":"command","taskId":…,"commands":[…]}`; replies `status: running/completed/error` with `results`; `b64:` prefix for binary; heartbeat timeout 40 s; one task at a time; max 2 clients | `src/webServer.h:51-59, 248-357, 380-400, 445-486` |
| `X`, `R`, `W` tokens are binary but still have `\r`/`\n` stripped and leading spaces trimmed | `src/moduleManager.h:427-436` |
| Skill names (`sit up balance str hi pu ck pee snf scrh zz fiv hsk`, gaits `wk tr cr bk` + `F`/`L`; `R` mirrored from `L`) | `src/InstinctBittleESP.h:2486`, `src/skill.h:501` |

## Assumptions to verify on hardware (cannot confirm from source alone)

1. BLE writes chunked to 20 bytes with `response=False` are reassembled by the firmware (10 ms inter-chunk timeout, `src/bleUart.h:63`).
2. Opening USB serial resets the board on most hosts (DTR), so the transport waits for `Ready!` or 1.5 s of silence.
3. `websockets.sync` allows `send()` from a heartbeat thread while the main thread is in `recv()`.
4. Every token used by the high-level API echoes itself.
5. Leg order inside each joint group is left-front, right-front, right-back, left-back (from OpenCat docs, not from this source).
6. Skill meanings (e.g. `fiv` = high five, `hsk` = handshake) match their names.
7. Head-only joint moves after a posture finish after the echo; scenario uses a ±3° tolerance and polling.
8. No one-shot skill takes longer than STALE_SECONDS (15 s) to echo; a later echo could still be mistaken for a newer command.

The hardware checklist in the Test Plan verifies each of these and records the result.

## Scope

In: package, four transports + mock, raw and high-level API, named joints and skills, typed public surface, firmware check, thread safety, safe stop on exceptions, `petoi` CLI (`ports`, `send`), examples, README, wheel build, CI test matrix.
Out (follow-ups, need approval): publishing to PyPI (`petoi` was unclaimed on 2026-10-27), trusted-publishing workflow, generated API reference site, deprecating the old serial scripts in other repos, skill upload (`K` token), sensors, async API.

## File structure

```
.github/workflows/python-api.yml   # tests + build on 3 OSes; never publishes
python/
  pyproject.toml
  README.md
  src/petoi/
    __init__.py          # exports connect, Robot, Reply, Joint, Skill, errors
    py.typed             # tells editors/mypy the package is typed
    protocol.py          # encode(), Reply, collect_reply(), LineBuffer, parse_ints() — pure
    errors.py            # PetoiError, ConnectionFailed, RobotError, RobotTimeout
    constants.py         # Joint, Skill
    robot.py             # Robot: raw send + high-level methods, lock, safe exit
    connect.py           # connect(), classify(), pick_serial_port(), firmware check
    cli.py               # `petoi ports`, `petoi send`
    transports/
      __init__.py
      base.py            # Transport, StreamTransport
      serial.py          # USB + Bluetooth Classic SPP (pyserial)
      ble.py             # BLE Nordic UART (bleak)
      websocket.py       # Wi-Fi (websockets)
      mock.py            # pretend robot, no hardware
  tests/
    conftest.py          # FakeStream helper
    scenario.py          # one behavior script run on mock AND real robots
    test_import.py
    test_protocol.py
    test_stream.py
    test_serial.py       # real pyserial loop:// port
    test_robot.py
    test_mock.py
    test_websocket.py    # real websockets server speaking the firmware JSON
    test_connect.py
    test_cli.py
    test_parity.py       # scenario on the mock
    hardware/test_smoke.py   # scenario + checklist on real robots; skipped unless env set
  examples/
    00_no_robot.py
    01_hello.py
    02_dance.py
```

All commands run from `python/` inside the worktree unless noted.

---

## Test Plan

### Levels

| Level | What it proves | Files | Runs where | Needs |
|---|---|---|---|---|
| L1 Protocol | Bytes we send and lines we parse match the firmware rules; each test cites the firmware line it mirrors | `test_protocol.py` | every commit, CI | nothing |
| L2 Transport | Our transports work with the **real** libraries: pyserial `loop://`, a real websockets server, `LineBuffer` for BLE chunks | `test_stream.py`, `test_serial.py`, `test_websocket.py` | every commit, CI | nothing |
| L3 API behavior | Method → command mapping, `RobotTimeout` raising, thread lock, stop-on-exception, firmware warning, port picking, CLI | `test_robot.py`, `test_connect.py`, `test_cli.py`, `test_mock.py` | every commit, CI | nothing |
| L4 Parity | The same `scenario.py` passes on the mock and on real robots, so the mock can't drift from the firmware | `test_parity.py` + `hardware/test_smoke.py` | mock: CI; real: manual | robot for the real half |
| L5 Hardware | The real round trip through the C++ firmware, per link, plus the assumption checklist | `hardware/test_smoke.py` + checklist below | manual, before merge and before each release | robot, each link |
| L6 Packaging | Wheel builds, installs into a clean venv, `import petoi` and `petoi send ? --to mock` work | CI job | CI on Linux/macOS/Windows × Python 3.9 and 3.13 | nothing |

### Rules

- **Test first:** every task writes its failing test before the code.
- **Coverage gate:** `pytest --cov=petoi --cov-fail-under=85`. `transports/ble.py` is excluded from coverage because only L5 can exercise bleak I/O; that exclusion is listed in `pyproject.toml` so it's visible.
- **Hardware bugs become unit tests:** any failure found on a real robot gets a FakeStream/mock test that reproduces it *before* the fix.
- **Never loosen a hardware assertion to make it pass:** a failure means an assumption above was wrong; fix the transport and update the assumption table.
- **Every firmware-derived test names its source line** (`# moduleManager.h:400`), so a firmware change points straight at the tests to recheck.

### Hardware checklist (L5) — fill in the PR description

Run `pytest tests/hardware -v -s` with the env var for each link, then tick the manual observations.

| Check | USB `PETOI_PORT` | BT Classic `PETOI_BT=bluetooth` | BLE `PETOI_BLE=ble` | Wi-Fi `PETOI_WS=<ip>` |
|---|---|---|---|---|
| `scenario.run()` passes | ☐ | ☐ | ☐ | ☐ |
| every `Skill` completes (verifies names, Assumption 4) | ☐ | ☐ | ☐ | ☐ |
| a 30-character command arrives intact (Assumption 1, BLE) | — | — | ☐ | — |
| connect works both right after power-on and on an already-running robot (Assumption 2) | ☐ | — | — | — |
| idle 60 s, then a command still works (heartbeat, Assumption 3) | — | — | — | ☐ |
| Ctrl-C during `walk()` stops the robot | ☐ | ☐ | ☐ | ☐ |
| **watch:** `Joint.LEFT_FRONT_SHOULDER` moves the left-front leg (Assumption 5) | ☐ | | | |
| **watch:** `Skill.HIGH_FIVE`, `HANDSHAKE`, `PUSH_UP` look right (Assumption 6) | ☐ | | | |

Record the robot model, firmware version (`robot.firmware`), host OS, and Python version next to the table.

### Not covered automatically (known gaps)

BLE I/O and real Wi-Fi only run in L5. There are no tests for multiple robots at once or for more than one Wi-Fi client (the firmware allows 2). Windows Bluetooth COM-port naming is only covered if the L5 run happens on Windows.

---

### Task 0: Commit this plan

- [ ] **Step 1: Commit** (from the worktree root)

```bash
git add docs/superpowers/plans/2026-10-27-python-api.md
git commit -m "Add implementation plan for petoi Python API"
```

### Task 1: Package scaffold

**Files:** Create `python/pyproject.toml`, `python/src/petoi/__init__.py`, `python/src/petoi/errors.py`, `python/src/petoi/py.typed` (empty), `python/tests/test_import.py`, `python/.gitignore`

- [ ] **Step 1: Write the failing test** — `python/tests/test_import.py`

```python
from pathlib import Path

import petoi


def test_version():
    assert petoi.__version__ == "0.1.0"


def test_package_is_marked_typed():
    assert (Path(petoi.__file__).parent / "py.typed").exists()
```

- [ ] **Step 2: Create `python/pyproject.toml`**

```toml
[build-system]
requires = ["hatchling>=1.18"]
build-backend = "hatchling.build"

[project]
name = "petoi"
version = "0.1.0"
description = "Control Petoi OpenCat robots (Bittle X, Nybble Q) from Python over USB, Bluetooth, BLE, or Wi-Fi"
readme = "README.md"
requires-python = ">=3.9"
license = "MIT"
dependencies = ["pyserial>=3.5"]

[project.optional-dependencies]
ble = ["bleak>=0.22"]
wifi = ["websockets>=12"]
all = ["bleak>=0.22", "websockets>=12"]
dev = ["pytest>=7", "pytest-cov>=4", "bleak>=0.22", "websockets>=12", "build"]

[project.scripts]
petoi = "petoi.cli:main"

[tool.hatch.build.targets.wheel]
packages = ["src/petoi"]

[tool.pytest.ini_options]
testpaths = ["tests"]
markers = ["hardware: needs a real robot (set PETOI_PORT, PETOI_BT, PETOI_BLE, or PETOI_WS)"]

[tool.coverage.run]
# bleak I/O is only exercised by the hardware tests (see Test Plan L5)
omit = ["*/petoi/transports/ble.py"]
```

- [ ] **Step 3: Create `python/src/petoi/errors.py`**

```python
class PetoiError(Exception):
    """Base class for every error raised by petoi."""


class ConnectionFailed(PetoiError):
    """The robot could not be found or the link could not be opened."""


class RobotError(PetoiError):
    """The robot rejected or failed a command."""


class RobotTimeout(RobotError):
    """The robot did not confirm a command in time."""
```

- [ ] **Step 4: Create `python/src/petoi/__init__.py`** and an empty `python/src/petoi/py.typed`

```python
"""Control Petoi OpenCat robots from Python."""

from petoi.errors import ConnectionFailed, PetoiError, RobotError, RobotTimeout

__version__ = "0.1.0"

__all__ = ["ConnectionFailed", "PetoiError", "RobotError", "RobotTimeout", "__version__"]
```

- [ ] **Step 5: Set up and run**

```bash
cd python
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest tests/test_import.py -v
```
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
printf ".venv/\n__pycache__/\n*.egg-info/\ndist/\n.coverage\n" > .gitignore
git add .gitignore pyproject.toml src tests
git commit -m "Scaffold petoi Python package"
```

### Task 2: Protocol encoding

**Files:** Create `python/src/petoi/protocol.py`, `python/tests/test_protocol.py`

- [ ] **Step 1: Write failing tests** — `python/tests/test_protocol.py`

```python
from enum import Enum, IntEnum

import pytest

from petoi.protocol import encode


class _J(IntEnum):
    HEAD = 0


class _S(str, Enum):
    HI = "hi"


def test_ascii_skill():
    # moduleManager.h:400 — lowercase tokens end with '\n'
    assert encode("k", "sit") == b"ksit\n"


def test_ascii_numbers_are_space_separated():
    assert encode("i", 8, 30, 9, -20) == b"i8 30 9 -20\n"


def test_enums_encode_as_their_values():
    # str(IntEnum) is "_J.HEAD" on Python 3.9/3.10, so encode must use .value
    assert encode("i", _J.HEAD, 30) == b"i0 30\n"
    assert encode("k", _S.HI) == b"khi\n"


def test_bare_token():
    assert encode("d") == b"d\n"


def test_binary_token_uses_int8_and_tilde():
    # moduleManager.h:400 — uppercase tokens are binary, end with '~'
    assert encode("I", 8, -20) == b"I\x08\xec~"


def test_binary_rejects_126():
    # moduleManager.h:401 — 126 is '~' and would end the command early
    with pytest.raises(ValueError, match="126"):
        encode("I", 8, 126)


def test_binary_rejects_out_of_int8_range():
    with pytest.raises(ValueError, match="int8"):
        encode("I", 8, 200)


def test_token_must_be_one_character():
    with pytest.raises(ValueError):
        encode("ks", "it")
```

- [ ] **Step 2: Run, expect FAIL** — `pytest tests/test_protocol.py -v` → `ModuleNotFoundError: No module named 'petoi.protocol'`

- [ ] **Step 3: Implement** — `python/src/petoi/protocol.py`

```python
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
```

- [ ] **Step 4: Run, expect PASS** — `pytest tests/test_protocol.py -v` → 8 passed
- [ ] **Step 5: Commit** — `git add -A && git commit -m "Add command encoding"`

### Task 3: Reply parsing and line buffer

**Files:** Modify `python/src/petoi/protocol.py`, `python/tests/test_protocol.py`

- [ ] **Step 1: Append failing tests** to `python/tests/test_protocol.py`

```python
from petoi.protocol import LineBuffer, Reply, collect_reply, parse_ints


def test_parse_ints_from_joint_line():
    # tools.h:89 list2String -> "0,\t-3,\t45,\t"
    assert parse_ints("0,\t-3,\t45,\t") == [0, -3, 45]


def test_collect_reply_stops_at_echo_and_drops_markers():
    # reaction.h:681 prints '=', :685-686 prints two lines, :1557 echoes token
    lines = iter(["=", "0\t1\t2\t", "0,\t-3,\t45,\t", "j", "late"])
    reply = collect_reply("j", lambda: next(lines))
    assert reply == Reply("j", ["0\t1\t2", "0,\t-3,\t45,"], completed=True)


def test_collect_reply_incomplete_when_source_runs_dry():
    lines = iter(["hello", None])
    reply = collect_reply("k", lambda: next(lines))
    assert reply.completed is False
    assert reply.lines == ["hello"]


def test_reply_text_joins_lines():
    assert Reply("?", ["Bittle X", "B10_260820"], True).text == "Bittle X\nB10_260820"


def test_line_buffer_reassembles_chunks():
    buf = LineBuffer()
    assert buf.feed(b"Bit") == []
    assert buf.feed(b"tle X\r\nB10") == ["Bittle X"]
    assert buf.feed(b"\r\n?\r\n") == ["B10", "?"]
```

- [ ] **Step 2: Run, expect FAIL** — `ImportError: cannot import name 'LineBuffer'`

- [ ] **Step 3: Append to `python/src/petoi/protocol.py`**

```python
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
```

- [ ] **Step 4: Run, expect PASS** — `pytest tests/test_protocol.py -v` → 13 passed
- [ ] **Step 5: Commit** — `git commit -am "Add reply parsing and line buffer"`

### Task 4: Transport base classes

**Files:** Create `python/src/petoi/transports/__init__.py` (empty), `python/src/petoi/transports/base.py`, `python/tests/conftest.py`, `python/tests/test_stream.py`

- [ ] **Step 1: Create the fake stream** — `python/tests/conftest.py`

```python
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
```

- [ ] **Step 2: Write failing tests** — `python/tests/test_stream.py`

```python
from conftest import FakeStream


def test_command_waits_for_echo():
    s = FakeStream({b"ksit\n": ["k"]})
    reply = s.command("k", b"ksit\n", timeout=1.0)
    assert reply.completed
    assert s.written == [b"ksit\n"]


def test_command_discards_stale_input_first():
    s = FakeStream(auto_echo=False)
    s.pending = ["k"]  # leftover echo from an earlier command
    reply = s.command("k", b"ksit\n", timeout=0.05)
    assert s.discards == 1
    assert reply.completed is False


def test_zero_timeout_does_not_read():
    s = FakeStream({b"kwkF\n": ["k"]})
    reply = s.command("k", b"kwkF\n", timeout=0)
    assert reply.completed is False
    assert s.pending == ["k"]
```

- [ ] **Step 3: Run, expect FAIL** — `ModuleNotFoundError: No module named 'petoi.transports'`

- [ ] **Step 4: Implement** — `python/src/petoi/transports/base.py`

```python
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
```

- [ ] **Step 5: Run, expect PASS** — `pytest tests/test_stream.py -v` → 3 passed
- [ ] **Step 6: Commit** — `git add -A && git commit -m "Add transport base classes"`

### Task 5: Serial transport (USB and Bluetooth Classic)

**Files:** Create `python/src/petoi/transports/serial.py`, `python/tests/test_serial.py`

- [ ] **Step 1: Write failing tests** — `python/tests/test_serial.py` (pyserial's real `loop://` port echoes writes back)

```python
import pytest
import serial

from petoi.errors import ConnectionFailed
from petoi.transports.serial import SerialTransport


def make_loop():
    port = serial.serial_for_url("loop://", timeout=0.1)
    return SerialTransport(port=port, boot_timeout=0)


def test_writes_reach_the_port_and_lines_come_back():
    t = make_loop()
    t.write(b"hello\r\n")
    assert t.readline(0.5) == "hello"


def test_readline_returns_none_on_silence():
    assert make_loop().readline(0.1) is None


def test_command_round_trip_over_loopback():
    t = make_loop()
    # loop:// echoes our bytes, so "k\n" comes back as the completion echo
    assert t.command("k", b"k\n", timeout=0.5).completed


def test_boot_wait_stops_at_ready():
    port = serial.serial_for_url("loop://", timeout=0.1)
    port.write(b"Init\r\nReady!\r\n")
    t = SerialTransport(port=port, boot_timeout=2.0)
    assert t.boot_log == ["Init", "Ready!"]


def test_bad_port_name_raises_connection_failed():
    with pytest.raises(ConnectionFailed, match="could not open"):
        SerialTransport("/dev/does-not-exist-petoi", boot_timeout=0)
```

- [ ] **Step 2: Run, expect FAIL** — `ModuleNotFoundError: No module named 'petoi.transports.serial'`

- [ ] **Step 3: Implement** — `python/src/petoi/transports/serial.py`

```python
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
```

- [ ] **Step 4: Run, expect PASS** — `pytest tests/test_serial.py -v` → 5 passed
- [ ] **Step 5: Commit** — `git add -A && git commit -m "Add serial transport for USB and Bluetooth Classic"`

### Task 6: Named joints and skills

**Files:** Create `python/src/petoi/constants.py`, `python/tests/test_constants.py`

- [ ] **Step 1: Write failing tests** — `python/tests/test_constants.py`

```python
from petoi.constants import Joint, Skill


def test_joint_indices_follow_firmware_groups():
    # src/OpenCat.h:235-237 — 0 head pan, 1 tilt, 2 tail, 8-11 shoulder, 12-15 knee
    assert Joint.HEAD_PAN == 0 and Joint.HEAD_TILT == 1 and Joint.TAIL == 2
    assert [j for j in Joint if "SHOULDER" in j.name] == list(range(8, 12))
    assert [j for j in Joint if "KNEE" in j.name] == list(range(12, 16))


def test_skill_values_are_firmware_names():
    # src/InstinctBittleESP.h:2486
    assert Skill.HIGH_FIVE.value == "fiv"
    assert Skill.STAND.value == "up"
```

- [ ] **Step 2: Run, expect FAIL** — `ModuleNotFoundError: No module named 'petoi.constants'`

- [ ] **Step 3: Implement** — `python/src/petoi/constants.py`

```python
from enum import Enum, IntEnum


class Joint(IntEnum):
    """Joint indices. Groups come from src/OpenCat.h:235-237; the leg order inside
    each group is checked on hardware (plan Assumption 5)."""

    HEAD_PAN = 0
    HEAD_TILT = 1
    TAIL = 2
    LEFT_FRONT_SHOULDER = 8
    RIGHT_FRONT_SHOULDER = 9
    RIGHT_BACK_SHOULDER = 10
    LEFT_BACK_SHOULDER = 11
    LEFT_FRONT_KNEE = 12
    RIGHT_FRONT_KNEE = 13
    RIGHT_BACK_KNEE = 14
    LEFT_BACK_KNEE = 15


class Skill(str, Enum):
    """Built-in one-shot skills (names from src/InstinctBittleESP.h:2486)."""

    SIT = "sit"
    STAND = "up"
    BALANCE = "balance"
    STRETCH = "str"
    HI = "hi"
    PUSH_UP = "pu"
    CHECK = "ck"
    PEE = "pee"
    SNIFF = "snf"
    SCRATCH = "scrh"
    SLEEP = "zz"
    HIGH_FIVE = "fiv"
    HANDSHAKE = "hsk"
```

- [ ] **Step 4: Run, expect PASS** — `pytest tests/test_constants.py -v` → 2 passed
- [ ] **Step 5: Commit** — `git add -A && git commit -m "Add named joints and skills"`

### Task 7: Robot API (raw + high-level, lock, safe exit)

**Files:** Create `python/src/petoi/robot.py`, `python/tests/test_robot.py`; modify `python/src/petoi/__init__.py`

- [ ] **Step 1: Write failing tests** — `python/tests/test_robot.py`

```python
import threading
import time

import pytest

from conftest import FakeStream
from petoi.constants import Joint, Skill
from petoi.errors import RobotTimeout
from petoi.robot import Robot


def robot(replies=None, **kw):
    return Robot(FakeStream(replies or {}, **kw), timeout=0.2)


def test_raw_send_appends_newline():
    assert robot().send("ksit").completed


def test_raw_send_accepts_space_after_token():
    r = robot({b"k sit\n": ["k"]})
    assert r.send("k sit").completed


@pytest.mark.parametrize(
    "call, sent",
    [
        (lambda r: r.sit(), b"ksit\n"),
        (lambda r: r.stand(), b"kup\n"),
        (lambda r: r.rest(), b"d\n"),
        (lambda r: r.stop(), b"kup\n"),
        (lambda r: r.walk(), b"kwkF\n"),
        (lambda r: r.walk("left"), b"kwkL\n"),
        (lambda r: r.trot("right"), b"ktrR\n"),
        (lambda r: r.crawl(), b"kcrF\n"),
        (lambda r: r.back(), b"kbk\n"),
        (lambda r: r.skill("hi"), b"khi\n"),
        (lambda r: r.skill(Skill.HIGH_FIVE), b"kfiv\n"),
        (lambda r: r.joint(8, 30), b"i8 30\n"),
        (lambda r: r.joint(Joint.HEAD_PAN, -20), b"i0 -20\n"),
        (lambda r: r.move_joints({8: 30, 9: -20}), b"i8 30 9 -20\n"),
        (lambda r: r.move_joints({0: 45}, sequential=True), b"m0 45\n"),
        (lambda r: r.beep(12, 8), b"b12 8\n"),
    ],
)
def test_high_level_commands(call, sent):
    r = robot()
    call(r)
    assert r.transport.written[-1] == sent


def test_unknown_direction_is_a_clear_error():
    with pytest.raises(ValueError, match="forward, left, right"):
        robot().walk("up")


def test_high_level_raises_when_robot_never_confirms():
    r = robot(auto_echo=False)
    with pytest.raises(RobotTimeout, match="did not confirm"):
        r.sit()


def test_raw_send_returns_incomplete_instead_of_raising():
    assert robot(auto_echo=False).send("ksit").completed is False


def test_wait_false_neither_waits_nor_raises():
    robot(auto_echo=False).skill("hi", wait=False)


def test_joints_parses_angle_line():
    r = robot({b"j\n": ["=", "0\t1\t2\t", "0,\t-3,\t45,\t", "j"]})
    assert r.joints() == [0, -3, 45]


def test_info_returns_model_and_version():
    r = robot({b"?\n": ["Bittle X", "B10_260820", "?"]})
    assert r.info() == {"model": "Bittle X", "version": "B10_260820"}


def test_context_manager_closes():
    r = robot()
    with r:
        pass
    assert r.transport.closed


def test_exception_inside_with_stops_robot_then_closes():
    r = robot()
    with pytest.raises(KeyboardInterrupt):
        with r:
            r.walk()
            raise KeyboardInterrupt
    assert r.transport.written[-1] == b"kup\n"
    assert r.transport.closed


class SlowStream(FakeStream):
    def __init__(self):
        super().__init__()
        self.active = 0
        self.max_active = 0

    def command(self, *args, **kwargs):
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        time.sleep(0.01)
        try:
            return super().command(*args, **kwargs)
        finally:
            self.active -= 1


def test_commands_from_threads_never_overlap():
    s = SlowStream()
    r = Robot(s)
    threads = [threading.Thread(target=r.sit) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert s.max_active == 1
```

- [ ] **Step 2: Run, expect FAIL** — `ModuleNotFoundError: No module named 'petoi.robot'`

- [ ] **Step 3: Implement** — `python/src/petoi/robot.py`

```python
from __future__ import annotations

import threading
from typing import Dict, List, Literal, Optional, Union

from petoi.constants import Joint, Skill
from petoi.errors import PetoiError, RobotError, RobotTimeout
from petoi.protocol import Reply, encode, parse_ints
from petoi.transports.base import Transport

Direction = Literal["forward", "left", "right"]
_DIRECTIONS = {"forward": "F", "left": "L", "right": "R"}  # 'R' mirrors 'L' (src/skill.h:501)


class Robot:
    """A connected Petoi robot. Get one with petoi.connect().

    High-level methods raise RobotTimeout if the robot doesn't confirm.
    send()/send_binary() return the Reply and never raise on timeout.
    """

    def __init__(self, transport: Transport, timeout: float = 5.0):
        self.transport = transport
        self.timeout = timeout
        self.model: Optional[str] = None  # set by connect()
        self.firmware: Optional[str] = None  # set by connect()
        self._lock = threading.Lock()

    # --- raw access -------------------------------------------------------

    def send(self, command: str, wait: bool = True, timeout: Optional[float] = None) -> Reply:
        """Send a serial-monitor style command, e.g. "ksit", "i 8 30", "d"."""
        if not command:
            raise ValueError("command is empty")
        payload = (command if command.endswith("\n") else command + "\n").encode()
        return self._run(command[0], payload, wait, timeout)

    def send_binary(self, token: str, *values: int, wait: bool = True, timeout: Optional[float] = None) -> Reply:
        """Send an uppercase (binary) command, e.g. send_binary("I", 8, -20)."""
        return self._run(token, encode(token, *values), wait, timeout)

    def _run(self, token: str, payload: bytes, wait: bool, timeout: Optional[float]) -> Reply:
        with self._lock:  # one command on the wire at a time
            return self.transport.command(token, payload, (timeout or self.timeout) if wait else 0)

    def _cmd(self, token: str, *args, wait: bool = True) -> Reply:
        payload = encode(token, *args)
        reply = self._run(token, payload, wait, None)
        if wait and not reply.completed:
            shown = payload.decode(errors="replace").strip()
            raise RobotTimeout(f"robot did not confirm {shown!r} within {self.timeout}s; check power and the connection")
        return reply

    # --- postures and skills ----------------------------------------------

    def skill(self, name: Union[Skill, str], wait: bool = True) -> Reply:
        return self._cmd("k", name, wait=wait)

    def sit(self) -> Reply:
        return self.skill(Skill.SIT)

    def stand(self) -> Reply:
        return self.skill(Skill.STAND)

    def stop(self) -> Reply:
        """Stop walking and stand still."""
        return self.skill(Skill.STAND)

    def rest(self) -> Reply:
        """Lie down and turn the servos off."""
        return self._cmd("d")

    # --- gaits (keep going until stop()) ---------------------------------

    def walk(self, direction: Direction = "forward") -> Reply:
        return self.skill("wk" + _direction(direction))

    def trot(self, direction: Direction = "forward") -> Reply:
        return self.skill("tr" + _direction(direction))

    def crawl(self, direction: Direction = "forward") -> Reply:
        return self.skill("cr" + _direction(direction))

    def back(self) -> Reply:
        return self.skill("bk")

    # --- joints -----------------------------------------------------------

    def joint(self, index: Union[Joint, int], angle: int) -> Reply:
        return self._cmd("i", index, angle)

    def move_joints(self, angles: Dict[Union[Joint, int], int], sequential: bool = False) -> Reply:
        """Move several joints together, or one after another if sequential."""
        flat = [v for pair in angles.items() for v in pair]
        return self._cmd("m" if sequential else "i", *flat)

    def joints(self) -> List[int]:
        reply = self._cmd("j")
        if not reply.lines:
            raise RobotError("no joint angles received")
        return parse_ints(reply.lines[-1])  # src/reaction.h:686

    # --- misc -------------------------------------------------------------

    def beep(self, note: int, duration: int) -> Reply:
        return self._cmd("b", note, duration)

    def info(self) -> Dict[str, str]:
        reply = self._cmd("?")  # src/reaction.h:405-406
        if len(reply.lines) < 2:
            raise RobotError(f"unexpected reply to '?': {reply.lines}")
        return {"model": reply.lines[0], "version": reply.lines[1]}

    def close(self) -> None:
        self.transport.close()

    def __enter__(self) -> "Robot":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            if exc_type is not None:  # e.g. Ctrl-C mid-walk: don't leave it walking
                try:
                    self.stop()
                except PetoiError:
                    pass
        finally:
            self.close()


def _direction(name: str) -> str:
    try:
        return _DIRECTIONS[name]
    except KeyError:
        raise ValueError(f"direction must be one of: {', '.join(_DIRECTIONS)}") from None
```

- [ ] **Step 4: Export** — in `python/src/petoi/__init__.py` add:

```python
from petoi.constants import Joint, Skill
from petoi.protocol import Reply
from petoi.robot import Robot
```
and add `"Joint", "Reply", "Robot", "Skill"` to `__all__`.

- [ ] **Step 5: Run, expect PASS** — `pytest -v` → all pass
- [ ] **Step 6: Commit** — `git add -A && git commit -m "Add Robot API with raw and high-level commands"`

### Task 8: Mock robot

**Files:** Create `python/src/petoi/transports/mock.py`, `python/tests/test_mock.py`, `python/tests/scenario.py`, `python/tests/test_parity.py`

- [ ] **Step 1: Write failing tests** — `python/tests/test_mock.py`

```python
from petoi.robot import Robot
from petoi.transports.mock import MockTransport


def test_mock_answers_query():
    r = Robot(MockTransport())
    assert r.info() == {"model": MockTransport.MODEL, "version": MockTransport.VERSION}


def test_mock_tracks_joint_angles_ascii_and_binary():
    r = Robot(MockTransport())
    r.joint(8, 30)
    r.send_binary("I", 9, -20)
    angles = r.joints()
    assert angles[8] == 30 and angles[9] == -20 and len(angles) == 16


def test_mock_records_history():
    t = MockTransport()
    Robot(t).sit()
    assert t.history == [b"ksit\n"]
```

`python/tests/scenario.py` — the shared behavior script (L4 parity):

```python
from petoi import Joint, Robot, Skill


def run(robot: Robot) -> None:
    info = robot.info()
    assert info["model"] and info["version"]
    robot.sit()
    robot.stand()
    robot.joint(Joint.HEAD_PAN, 30)
    assert robot.joints()[Joint.HEAD_PAN] == 30
    robot.move_joints({Joint.HEAD_PAN: 0, Joint.HEAD_TILT: 10})
    robot.send_binary("I", int(Joint.HEAD_PAN), -15)
    assert robot.joints()[Joint.HEAD_PAN] == -15
    robot.skill(Skill.HI)
    robot.walk()
    robot.stop()
    assert robot.send("d").completed
```

`python/tests/test_parity.py`

```python
import scenario
from petoi.robot import Robot
from petoi.transports.mock import MockTransport


def test_scenario_on_mock():
    scenario.run(Robot(MockTransport()))
```

- [ ] **Step 2: Run, expect FAIL** — `ModuleNotFoundError: No module named 'petoi.transports.mock'`

- [ ] **Step 3: Implement** — `python/src/petoi/transports/mock.py`

```python
from __future__ import annotations

from typing import List, Optional

from petoi.protocol import parse_ints
from petoi.transports.base import StreamTransport


class MockTransport(StreamTransport):
    """A pretend robot for learning, docs, and tests. Replies like the firmware:
    data lines after '=', then the token echo (src/reaction.h:681-686, 1557)."""

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
                self.angles[index] = angle
        elif token == "?":
            self._out += [self.MODEL, self.VERSION]
        elif token == "j":
            self._out += ["=", "\t".join(map(str, range(len(self.angles)))), ",\t".join(map(str, self.angles)) + ","]
        self._out.append(token)

    def readline(self, timeout: float) -> Optional[str]:
        return self._out.pop(0) if self._out else None

    def discard_input(self) -> None:
        self._out.clear()

    def close(self) -> None:
        pass
```

- [ ] **Step 4: Run, expect PASS** — `pytest tests/test_mock.py tests/test_parity.py -v` → 4 passed
- [ ] **Step 5: Commit** — `git add -A && git commit -m "Add mock robot and shared behavior scenario"`

### Task 9: Wi-Fi WebSocket transport

**Files:** Create `python/src/petoi/transports/websocket.py`, `python/tests/test_websocket.py`

- [ ] **Step 1: Write failing tests** — `python/tests/test_websocket.py`. The fake server copies `src/webServer.h:248-357, 445-486`.

```python
import base64
import json
import threading

import pytest
from websockets.sync.server import serve

from petoi.errors import RobotError
from petoi.transports.websocket import WebSocketTransport, to_web_command

received = []


def firmware(ws):
    ws.send(json.dumps({"type": "connected", "clientId": "0"}))
    for raw in ws:
        msg = json.loads(raw)
        if msg["type"] != "command":
            continue
        received.append(msg)
        task = msg["taskId"]
        ws.send(json.dumps({"type": "response", "taskId": "someone-else", "status": "completed", "results": []}))
        ws.send(json.dumps({"type": "response", "taskId": task, "status": "running"}))
        if msg["commands"] == ["bad"]:
            ws.send(json.dumps({"type": "response", "taskId": task, "status": "error", "error": "Previous web task is still running"}))
        else:
            ws.send(json.dumps({"type": "response", "taskId": task, "status": "completed",
                                "results": ["=\r\nBittle X\r\nB10_260820\r\n?\r\n"]}))


@pytest.fixture
def port():
    received.clear()
    with serve(firmware, "127.0.0.1", 0) as srv:
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        yield srv.socket.getsockname()[1]
        srv.shutdown()


def test_ascii_command_strips_newline():
    assert to_web_command(b"ksit\n") == "ksit"


def test_binary_command_is_base64_without_tilde():
    # webServer.h:380-400 — firmware decodes b64 and appends '~' itself
    assert to_web_command(b"I\x08\xec~") == "b64:" + base64.b64encode(b"I\x08\xec").decode()


def test_command_round_trip_ignores_other_tasks(port):
    t = WebSocketTransport("127.0.0.1", port=port, heartbeat=False)
    reply = t.command("?", b"?\n", timeout=2.0)
    t.close()
    assert received[0]["commands"] == ["?"]
    assert reply.completed
    assert reply.lines == ["Bittle X", "B10_260820"]


def test_firmware_error_raises(port):
    t = WebSocketTransport("127.0.0.1", port=port, heartbeat=False)
    with pytest.raises(RobotError, match="still running"):
        t.command("b", b"bad\n", timeout=2.0)
    t.close()
```

- [ ] **Step 2: Run, expect FAIL** — `ModuleNotFoundError: No module named 'petoi.transports.websocket'`

- [ ] **Step 3: Implement** — `python/src/petoi/transports/websocket.py`

```python
from __future__ import annotations

import base64
import itertools
import json
import threading
from typing import Optional

from petoi.errors import ConnectionFailed, RobotError
from petoi.protocol import Reply, collect_reply
from petoi.transports.base import Transport

PORT = 81  # src/webServer.h:59
HEARTBEAT_SECONDS = 15  # firmware drops clients after 40 s of silence (src/webServer.h:51)


def to_web_command(payload: bytes) -> str:
    if payload[:1].isupper():
        return "b64:" + base64.b64encode(payload[:-1]).decode()  # drop '~'; firmware re-adds it
    return payload.decode().rstrip("\n")


class WebSocketTransport(Transport):
    """Wi-Fi link to the robot's WebSocket server."""

    def __init__(self, host: str, port: int = PORT, timeout: float = 5.0, heartbeat: bool = True):
        try:
            from websockets.sync.client import connect
        except ImportError:
            raise ConnectionFailed('Wi-Fi needs an extra package: pip install "petoi[wifi]"') from None
        url = host if host.startswith("ws://") else f"ws://{host}:{port}"
        try:
            self._ws = connect(url, open_timeout=timeout)
            hello = json.loads(self._ws.recv(timeout))
        except Exception as e:
            raise ConnectionFailed(f"could not connect to {url}: {e}") from e
        if hello.get("type") == "error":
            raise ConnectionFailed(hello.get("error", "robot refused the connection"))
        self._ids = itertools.count(1)
        self._default_timeout = timeout
        self._stop = threading.Event()
        if heartbeat:
            threading.Thread(target=self._beat, daemon=True).start()

    def _beat(self) -> None:
        while not self._stop.wait(HEARTBEAT_SECONDS):
            try:
                self._ws.send(json.dumps({"type": "heartbeat"}))
            except Exception:
                return

    def command(self, token: str, payload: bytes, timeout: Optional[float]) -> Reply:
        # The firmware runs one web task at a time and rejects overlaps,
        # so Wi-Fi commands always wait for completion.
        timeout = timeout or self._default_timeout
        task_id = f"py-{next(self._ids)}"
        self._ws.send(json.dumps({"type": "command", "taskId": task_id, "commands": [to_web_command(payload)]}))
        while True:
            try:
                msg = json.loads(self._ws.recv(timeout))
            except TimeoutError:
                return Reply(token)
            if msg.get("taskId") != task_id:
                continue
            if msg.get("status") == "error":
                raise RobotError(msg.get("error", "command failed"))
            if msg.get("status") == "completed":
                # status "completed" is Wi-Fi's real completion signal, so add the echo in case results omit it
                lines = iter("".join(msg.get("results", [])).splitlines() + [token])
                return collect_reply(token, lambda: next(lines, None))

    def close(self) -> None:
        self._stop.set()
        self._ws.close()
```

- [ ] **Step 4: Run, expect PASS** — `pytest tests/test_websocket.py -v` → 4 passed
- [ ] **Step 5: Commit** — `git add -A && git commit -m "Add Wi-Fi WebSocket transport"`

### Task 10: BLE transport

**Files:** Create `python/src/petoi/transports/ble.py`. Chunk reassembly is tested through `LineBuffer` (Task 3); the missing-bleak hint is tested in Task 11; bleak I/O is tested only on hardware (L5).

- [ ] **Step 1: Implement** — `python/src/petoi/transports/ble.py`

```python
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
```

- [ ] **Step 2: Check it imports** — `python -c "import petoi.transports.ble"` → no output
- [ ] **Step 3: Commit** — `git add -A && git commit -m "Add BLE transport"`

### Task 11: `connect()`, port discovery, firmware check

**Files:** Create `python/src/petoi/connect.py`, `python/tests/test_connect.py`; modify `python/src/petoi/__init__.py`

`connect()` rules:
- `connect()` → the only likely USB serial port, or an error listing the ports
- `connect("/dev/cu.usbserial-1420")` / `connect("COM3")` → serial
- `connect("bluetooth")` → the paired port whose name contains `_SSP`
- `connect("ble")` or `connect("ble:AA:BB:…")` → BLE
- `connect("192.168.4.1")` / `connect("ws://…")` / `connect("bittle.local")` → Wi-Fi
- `connect("mock")` → the mock robot
- After connecting it sends `?` and sets `robot.model` / `robot.firmware`. If the firmware is older than `MIN_FIRMWARE_DATE` or doesn't answer, it warns (`RuntimeWarning`) but still connects.

- [ ] **Step 1: Write failing tests** — `python/tests/test_connect.py`

```python
import builtins

import pytest
from serial.tools.list_ports_common import ListPortInfo

import petoi
from petoi.connect import classify, pick_serial_port
from petoi.errors import ConnectionFailed
from petoi.transports.mock import MockTransport


def port(device, description=""):
    p = ListPortInfo(device)
    p.description = description
    return p


@pytest.mark.parametrize(
    "target, kind",
    [
        (None, ("serial", None)),
        ("/dev/cu.usbserial-1420", ("serial", "/dev/cu.usbserial-1420")),
        ("COM3", ("serial", "COM3")),
        ("bluetooth", ("bluetooth", None)),
        ("ble", ("ble", None)),
        ("ble:AA:BB:CC:DD:EE:FF", ("ble", "AA:BB:CC:DD:EE:FF")),
        ("192.168.4.1", ("wifi", "192.168.4.1")),
        ("ws://10.0.0.5:81", ("wifi", "ws://10.0.0.5:81")),
        ("bittle.local", ("wifi", "bittle.local")),
        ("mock", ("mock", None)),
    ],
)
def test_classify(target, kind):
    assert classify(target) == kind


def test_pick_single_usb_port():
    ports = [port("/dev/cu.Bluetooth-Incoming-Port"), port("/dev/cu.usbserial-1420", "USB Serial")]
    assert pick_serial_port(ports, bluetooth=False) == "/dev/cu.usbserial-1420"


def test_pick_bluetooth_ssp_port():
    ports = [port("/dev/cu.usbserial-1420"), port("/dev/cu.BittleX1A2B_SSP")]
    assert pick_serial_port(ports, bluetooth=True) == "/dev/cu.BittleX1A2B_SSP"


def test_ambiguous_ports_list_choices():
    ports = [port("/dev/cu.usbserial-1"), port("/dev/cu.usbserial-2")]
    with pytest.raises(ConnectionFailed, match="usbserial-1.*usbserial-2"):
        pick_serial_port(ports, bluetooth=False)


def test_no_ports():
    with pytest.raises(ConnectionFailed, match="No robot"):
        pick_serial_port([], bluetooth=False)


def test_connect_mock_reads_model_and_firmware():
    robot = petoi.connect("mock")
    assert robot.model == MockTransport.MODEL
    assert robot.firmware == MockTransport.VERSION


def test_old_firmware_warns_but_connects(monkeypatch):
    monkeypatch.setattr(MockTransport, "VERSION", "B10_250101")
    with pytest.warns(RuntimeWarning, match="older than"):
        robot = petoi.connect("mock")
    assert robot.firmware == "B10_250101"


def test_silent_firmware_warns(monkeypatch):
    monkeypatch.setattr(MockTransport, "write", lambda self, data: None)  # robot never answers
    with pytest.warns(RuntimeWarning, match="did not answer"):
        petoi.connect("mock", timeout=0.1)


def test_connect_ble_without_bleak_gives_install_hint(monkeypatch):
    real_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name == "bleak":
            raise ImportError
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(ConnectionFailed, match=r"petoi\[ble\]"):
        petoi.connect("ble")
```

- [ ] **Step 2: Run, expect FAIL** — `ModuleNotFoundError: No module named 'petoi.connect'`

- [ ] **Step 3: Implement** — `python/src/petoi/connect.py`

```python
from __future__ import annotations

import re
import warnings
from typing import List, Optional, Tuple

from serial.tools import list_ports

from petoi.errors import ConnectionFailed, PetoiError
from petoi.robot import Robot

SSP_MARK = "_SSP"  # src/bluetoothManager.h:73
MIN_FIRMWARE_DATE = "260820"  # firmware in this repo (src/OpenCat.h:80); the version hardware tests run against
_USB_HINTS = ("usb", "wch", "ch340", "ch910", "cp210", "uart", "acm")
_IGNORE = ("bluetooth-incoming-port", "debug-console")
_IP = re.compile(r"^\d{1,3}(\.\d{1,3}){3}(:\d+)?$")


def classify(target: Optional[str]) -> Tuple[str, Optional[str]]:
    if target is None:
        return ("serial", None)
    low = target.lower()
    if low in ("bluetooth", "ble", "mock"):
        return (low, None)
    if low.startswith("ble:"):
        return ("ble", target[4:])
    if low.startswith("ws://") or _IP.match(target) or low.endswith(".local"):
        return ("wifi", target)
    return ("serial", target)


def pick_serial_port(ports, bluetooth: bool) -> str:
    candidates = [p for p in ports if not any(i in p.device.lower() for i in _IGNORE)]
    if bluetooth:
        matches = [p for p in candidates if SSP_MARK in p.device or SSP_MARK in (p.description or "")]
    else:
        matches = [p for p in candidates
                   if SSP_MARK not in p.device
                   and any(h in f"{p.device} {p.description}".lower() for h in _USB_HINTS)]
    if len(matches) == 1:
        return matches[0].device
    if not matches:
        what = "paired Bluetooth (_SSP)" if bluetooth else "USB"
        raise ConnectionFailed(f"No robot {what} port found. Ports seen: {[p.device for p in ports] or 'none'}")
    raise ConnectionFailed(f"Several possible ports, pass one: {', '.join(p.device for p in matches)}")


def list_ports_info() -> List[str]:
    return [f"{p.device}\t{p.description}" for p in list_ports.comports()]


def _open(kind: str, value: Optional[str], timeout: float):
    if kind == "mock":
        from petoi.transports.mock import MockTransport
        return MockTransport()
    if kind == "wifi":
        from petoi.transports.websocket import WebSocketTransport
        return WebSocketTransport(value, timeout=timeout)
    if kind == "ble":
        from petoi.transports.ble import BleTransport
        return BleTransport(value)
    from petoi.transports.serial import SerialTransport
    if value is None:
        value = pick_serial_port(list_ports.comports(), bluetooth=(kind == "bluetooth"))
    boot = 0 if kind == "bluetooth" or SSP_MARK in value else 8.0  # SPP doesn't reset the board
    return SerialTransport(value, boot_timeout=boot)


def _check_firmware(robot: Robot) -> None:
    try:
        info = robot.info()
    except PetoiError:
        warnings.warn("robot did not answer '?'; its firmware may be too old for this API", RuntimeWarning, stacklevel=3)
        return
    robot.model, robot.firmware = info["model"], info["version"]
    date = info["version"].rsplit("_", 1)[-1]  # BOARD_YYMMDD, src/OpenCat.h:666
    if len(date) == 6 and date.isdigit() and date < MIN_FIRMWARE_DATE:
        warnings.warn(f"firmware {info['version']} is older than {MIN_FIRMWARE_DATE}; some commands may not work. "
                      "Update it with the Petoi Desktop App.", RuntimeWarning, stacklevel=3)


def connect(target: Optional[str] = None, timeout: float = 5.0, check_firmware: bool = True) -> Robot:
    """Connect to a robot. target: None (USB), a port name, "bluetooth", "ble",
    "ble:<address>", a Wi-Fi address, or "mock"."""
    kind, value = classify(target)
    robot = Robot(_open(kind, value, timeout), timeout=timeout)
    if check_firmware:
        _check_firmware(robot)
    return robot
```

Note: `test_silent_firmware_warns` replaces `write` so the mock stays silent; `info()` then raises `RobotTimeout` (a `PetoiError`), which triggers the warning.

- [ ] **Step 4: Export** — in `python/src/petoi/__init__.py` add `from petoi.connect import connect, list_ports_info` and add both names to `__all__`.

- [ ] **Step 5: Run, expect PASS** — `pytest -v` → all pass
- [ ] **Step 6: Commit** — `git add -A && git commit -m "Add connect() with transport selection and firmware check"`

### Task 12: CLI

**Files:** Create `python/src/petoi/cli.py`, `python/tests/test_cli.py`

- [ ] **Step 1: Write failing tests** — `python/tests/test_cli.py`

```python
from petoi import cli


def test_ports_lists_devices(monkeypatch, capsys):
    monkeypatch.setattr(cli, "list_ports_info", lambda: ["/dev/cu.usbserial-1\tUSB Serial"])
    assert cli.main(["ports"]) == 0
    assert "usbserial-1" in capsys.readouterr().out


def test_send_to_mock_prints_reply(capsys):
    assert cli.main(["send", "?", "--to", "mock"]) == 0
    assert "Mock Bittle" in capsys.readouterr().out


def test_connection_error_exits_1(capsys):
    assert cli.main(["send", "ksit", "--to", "/dev/does-not-exist-petoi"]) == 1
    assert "error:" in capsys.readouterr().err
```

- [ ] **Step 2: Run, expect FAIL** — `ModuleNotFoundError: No module named 'petoi.cli'`

- [ ] **Step 3: Implement** — `python/src/petoi/cli.py`

```python
from __future__ import annotations

import argparse
import sys
from typing import List, Optional

from petoi.connect import connect, list_ports_info
from petoi.errors import PetoiError


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="petoi", description="Talk to a Petoi robot.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("ports", help="list serial ports")
    send = sub.add_parser("send", help="send a command, e.g. petoi send ksit")
    send.add_argument("command")
    send.add_argument("--to", default=None, help="port, 'bluetooth', 'ble', a Wi-Fi address, or 'mock'")
    args = parser.parse_args(argv)

    if args.cmd == "ports":
        for line in list_ports_info():
            print(line)
        return 0
    try:
        with connect(args.to) as robot:
            reply = robot.send(args.command)
    except PetoiError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(reply.text or ("ok" if reply.completed else "no reply"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run, expect PASS** — `pytest tests/test_cli.py -v` → 3 passed
- [ ] **Step 5: Commit** — `git add -A && git commit -m "Add petoi command-line tool"`

### Task 13: Hardware smoke test (L4 real half + L5)

**Files:** Create `python/tests/hardware/test_smoke.py`

- [ ] **Step 1: Write the test**

```python
import os
import time

import pytest

import petoi
import scenario
from petoi import Skill

TARGETS = [os.environ[k] for k in ("PETOI_PORT", "PETOI_BT", "PETOI_BLE", "PETOI_WS") if os.environ.get(k)]

pytestmark = [pytest.mark.hardware, pytest.mark.skipif(not TARGETS, reason="no robot configured")]


@pytest.fixture(scope="module", params=TARGETS)  # one connection per link; USB connect can take ~8 s
def robot(request):
    with petoi.connect(request.param) as r:
        print(f"\n{request.param}: {r.model} firmware {r.firmware}")
        yield r
        r.rest()


def test_scenario(robot):
    scenario.run(robot)


@pytest.mark.parametrize("skill", list(Skill))
def test_every_skill_completes(robot, skill):
    robot.skill(skill)


def test_long_command_arrives_intact(robot):
    # Assumption 1: BLE chunking. 7 joint pairs = a 30+ character ASCII command.
    angles = {int(petoi.Joint.HEAD_PAN): 10, 8: 20, 9: 20, 10: 20, 11: 20, 12: 10, 13: 10}
    robot.move_joints(angles)
    got = robot.joints()
    assert all(got[i] == a for i, a in angles.items())


@pytest.mark.skipif(not os.environ.get("PETOI_WS"), reason="Wi-Fi only")
def test_wifi_survives_idle_minute():
    # Assumption 3: heartbeat thread keeps the connection
    with petoi.connect(os.environ["PETOI_WS"]) as r:
        time.sleep(60)
        assert r.info()["model"]
```

- [ ] **Step 2: Check it skips without hardware** — `pytest tests/hardware -v` → all skipped
- [ ] **Step 3: Run on each available link and fill in the Test Plan's hardware checklist** in the PR description (e.g. `PETOI_PORT=/dev/cu.usbserial-XXXX pytest tests/hardware -v -s`). Do the manual "watch" rows and the Ctrl-C row by hand with `examples/01_hello.py`.
- [ ] **Step 4: Commit** — `git add -A && git commit -m "Add hardware smoke tests"`

### Task 14: Examples, docs, and CI

**Files:** Create `python/examples/00_no_robot.py`, `python/examples/01_hello.py`, `python/examples/02_dance.py`, `python/README.md`, `.github/workflows/python-api.yml`; modify root `README.md` (one short section)

- [ ] **Step 1: Examples**

`python/examples/00_no_robot.py`

```python
import petoi

with petoi.connect("mock") as robot:  # no hardware needed
    print(robot.model, robot.firmware)
    robot.sit()
    robot.joint(petoi.Joint.HEAD_PAN, 30)
    print("head angle:", robot.joints()[petoi.Joint.HEAD_PAN])
```

`python/examples/01_hello.py`

```python
import time

import petoi

with petoi.connect() as robot:  # or "bluetooth", "ble", "192.168.4.1"
    print(robot.model, robot.firmware)
    robot.sit()
    robot.walk()
    time.sleep(3)  # Ctrl-C here stops the robot safely
    robot.stop()
    robot.rest()
```

`python/examples/02_dance.py`

```python
import petoi
from petoi import Joint, Skill

with petoi.connect() as robot:
    robot.stand()
    for angle in (40, -40, 0):
        robot.joint(Joint.HEAD_PAN, angle)
    robot.skill(Skill.HI)
    robot.send("kpu")  # any serial-monitor command works too
    robot.rest()
```

- [ ] **Step 2: `python/README.md`** — sections: Install (`pip install petoi`, `petoi[ble]`, `petoi[wifi]`, `petoi[all]`); No robot yet? (`00_no_robot.py`); Three-line start (`01_hello.py`); Connecting (the six `connect()` forms from Task 11); High-level methods table (`sit stand stop rest walk trot crawl back skill joint move_joints joints beep info`) plus `Joint` and `Skill`; Errors (`RobotTimeout` from high-level methods vs `Reply.completed` from `send`); Raw commands (`send`, `send_binary`, link to the token table at `src/OpenCat.h:293-375`); CLI (`petoi ports`, `petoi send ksit --to ble`); Troubleshooting (port busy in another app, BLE robot already connected to the phone app, Wi-Fi limited to 2 clients, firmware-too-old warning).

- [ ] **Step 3: Root `README.md`** — add a short "Python API" section that points to `python/README.md` and shows the `01_hello.py` snippet.

- [ ] **Step 4: CI** — `.github/workflows/python-api.yml` (tests and build only; it never publishes)

```yaml
name: python-api
on:
  push:
    paths: ["python/**", ".github/workflows/python-api.yml"]
  pull_request:
    paths: ["python/**", ".github/workflows/python-api.yml"]
jobs:
  test:
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, macos-latest, windows-latest]
        python: ["3.9", "3.13"]
    runs-on: ${{ matrix.os }}
    defaults:
      run:
        working-directory: python
        shell: bash
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python }}
      - run: pip install -e ".[dev]"
      - run: pytest -v --cov=petoi --cov-report=term-missing --cov-fail-under=85
      - run: python -m build
      - name: Wheel works in a clean venv
        run: |
          python -m venv "$RUNNER_TEMP/clean"
          if [ "$RUNNER_OS" = "Windows" ]; then VBIN="$RUNNER_TEMP/clean/Scripts"; else VBIN="$RUNNER_TEMP/clean/bin"; fi
          "$VBIN/pip" install dist/*.whl
          cd "$RUNNER_TEMP" && "$VBIN/petoi" send "?" --to mock
```

Note: `macos-latest` runners are Apple Silicon; if `setup-python` has no 3.9 build for that runner, change that one matrix cell to `macos-13` and say so in the PR.

- [ ] **Step 5: Local release checks**

```bash
pytest -v --cov=petoi --cov-report=term-missing --cov-fail-under=85
python -m build
python -m venv /tmp/petoi-clean && /tmp/petoi-clean/bin/pip install dist/petoi-0.1.0-py3-none-any.whl
cd /tmp && /tmp/petoi-clean/bin/petoi send "?" --to mock
```
Expected: all tests pass, coverage ≥ 85%, the last command prints `Mock Bittle` and `MOCK_260820`.

- [ ] **Step 6: Commit** — `git add -A && git commit -m "Add examples, docs, and CI for the Python API"`

---

## Self-review

- Spec coverage: four links (Tasks 5, 9, 10, 11) + mock (8); raw + high-level (7); pip packaging (1, 14); replaces the serial tools with an importable API (whole plan). Best-practice additions: raise on timeout (7), typed surface + `Joint`/`Skill` + `py.typed` (1, 6, 7), mock (8), thread lock (7), firmware check (11), safe stop on exception (7). Test plan levels L1–L6 each map to tasks.
- Names are the same across tasks: `encode`, `Reply`, `collect_reply`, `LineBuffer`, `parse_ints`, `Transport.command(token, payload, timeout)`, `StreamTransport.write/readline/discard_input`, `Robot.send/send_binary/skill/joint/move_joints/joints/info`, `Robot.model/firmware`, `Joint`, `Skill`, `RobotTimeout`, `MockTransport.MODEL/VERSION/history`, `connect`, `classify`, `pick_serial_port`, `list_ports_info`, `MIN_FIRMWARE_DATE`.
- Known gaps are listed in the Test Plan.

## Amendments after code review (2026-10-27)

- F1: StreamTransport tracks unconfirmed tokens (expire after `STALE_SECONDS` = 15 s) and consumes their late echoes, because the protocol has no command IDs and one-shot skills echo only when finished.
- F2: SerialTransport reads through `LineBuffer` in short slices so a timeout never returns a partial line.
- F3: Boot wait returns on early silence only if nothing was printed; once output starts it waits for `Ready!` (default 20 s) and warns otherwise, since boot has long silent stretches and a Y/n prompt (`src/imu.h:739+`, `:1013`).
- F4: The port is closed if the boot wait fails, and `serial.SerialException` becomes `ConnectionFailed`.
- F5: `Transport.command` timeout 0 means do not wait; `Robot.send(..., timeout=0)` honors it instead of falling back to the default.
- F6: `encode` rejects non-ASCII tokens, non-integer binary args, line breaks in ASCII args, and (for `X`, `R`, `W`) bytes 10/13 and a leading 9/32 that the firmware strips (`src/moduleManager.h:427-436`).
- F7: `Robot.send` rejects embedded newlines (would split the command) and uppercase tokens (use `send_binary()`).
- F8: `__exit__` stops the robot best-effort with a 1 s wait and catches any `Exception`, so it never masks the user's exception.
- F9: MockTransport ignores out-of-range joint indices like the firmware (`src/reaction.h:882`, `:1077`) and documents what it does not model.
- F10: The shared scenario polls joint angles with a ±3° tolerance because head-only moves finish after the echo (`src/reaction.h:1043-1047`, `src/skill.h:414`).
