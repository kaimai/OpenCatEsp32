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
trouble = []  # lines seen; stop_on_trouble ends the run when this isn't empty


def watch(robot):
    """Record any STOP_LINES the robot prints. USB, Bluetooth and BLE; Wi-Fi replies don't pass through readline."""
    readline = getattr(robot.transport, "readline", None)
    if readline is None:
        return

    def watched(timeout):
        line = readline(timeout)
        if line is not None and line.strip().startswith(STOP_LINES):
            trouble.append(line.strip())
        return line

    robot.transport.readline = watched


# Import this into each hardware test module. It isn't in a tests/hardware/conftest.py because a second
# conftest module would shadow tests/conftest.py for the unit tests' `from conftest import FakeStream`.
@pytest.fixture(autouse=True)
def stop_on_trouble():
    yield
    if trouble:
        pytest.exit(f"robot printed {trouble[0]!r}; check it is upright and on a stand before running again", returncode=1)


on_stand = pytest.mark.skipif(
    not os.environ.get("PETOI_ON_STAND"),
    reason="an upload that arrives misaligned can drive the joints anywhere; put the robot on a stand and set PETOI_ON_STAND=1",
)
