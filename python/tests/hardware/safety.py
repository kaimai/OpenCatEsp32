"""Stop driving the robot once it reports trouble, and keep uploads to a robot on a stand."""
import os

import pytest

# Printed over USB (src/reaction.h:47-89, src/skill.h:348; OpenCatEsp32S3 reaction.h:180-267, skill.h:496).
# Our test frames never set a trigger, so "Trigger released" means an upload arrived misaligned.
STOP_LINES = (
    "EXCEPTION: Fall over",
    "EXCEPTION free fall",
    "EXCEPTION: Roll",
    "EXCEPTION: Knocked",
    "EXCEPTION: Pushed",
    "Trigger released",
)
_REST = b"d\n"
trouble = []  # lines seen; stop_on_trouble ends the run when this isn't empty
robots = []  # watched robots, put to rest before the run ends


class RobotInTrouble(Exception):
    """The robot printed a STOP_LINES message; nothing but rest is sent after it."""


def watch(robot):
    """Raise RobotInTrouble on any STOP_LINES line, then refuse every command but rest.

    USB, Bluetooth and BLE; Wi-Fi replies don't pass through readline. While watched, each
    write but rest and each discard first read what is buffered (up to 50 ms on serial)."""
    t = robot.transport
    readline = getattr(t, "readline", None)
    if readline is None:
        return
    discard, write_command = t.discard_input, t.write_command
    held = []  # lines read ahead of a write, handed back in order

    def check(line):
        if line is not None and line.strip().startswith(STOP_LINES):
            first = not trouble
            trouble.append(line.strip())
            if first:  # later lines only get recorded, so the emergency rest can still go out
                raise RobotInTrouble(f"robot printed {line.strip()!r}")
        return line

    def watched_readline(timeout):
        return held.pop(0) if held else check(readline(timeout))

    def watched_discard():
        held.clear()  # already checked
        while check(readline(0)) is not None:  # command() discards before writing; a fall line may be waiting
            pass
        discard()

    def guarded_write(payload, **kw):
        if payload != _REST:
            # with an echo owed, command() writes without discarding, so look at what's buffered first
            while True:
                line = check(readline(0))
                if line is None:
                    break
                held.append(line)
        if trouble and payload != _REST:
            raise RobotInTrouble(f"not sending {payload[:20]!r}: robot printed {trouble[0]!r}")
        write_command(payload, **kw)

    t.readline, t.discard_input, t.write_command = watched_readline, watched_discard, guarded_write
    robots.append(robot)


# Import this into each hardware test module. It isn't in a tests/hardware/conftest.py because a second
# conftest module would shadow tests/conftest.py for the unit tests' `from conftest import FakeStream`.
@pytest.fixture(autouse=True)
def stop_on_trouble():
    yield
    if trouble:
        for robot in robots:
            try:
                robot.rest()
            except Exception:
                pass
        pytest.exit(f"robot printed {trouble[0]!r}; check it is upright and on a stand before running again", returncode=1)


on_stand = pytest.mark.skipif(
    not os.environ.get("PETOI_ON_STAND"),
    reason="an upload that arrives misaligned can drive the joints anywhere; put the robot on a stand and set PETOI_ON_STAND=1",
)
