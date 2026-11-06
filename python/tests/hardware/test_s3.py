"""Checks for OpenCatEsp32S3 robots (Quaddle). Run with PETOI_PORT, PETOI_BLE or PETOI_WS pointing at one."""
import os
import warnings

import pytest

import petoi
from petoi import QuaddleJoint
from safety import stop_on_trouble, watch  # noqa: F401 (stop_on_trouble is an autouse fixture)

TARGETS = [os.environ[k] for k in ("PETOI_PORT", "PETOI_BLE", "PETOI_WS") if os.environ.get(k)]
pytestmark = [pytest.mark.hardware, pytest.mark.skipif(not TARGETS, reason="no robot configured")]


@pytest.fixture(scope="module", params=TARGETS)
def robot(request):
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # '?' retry, BLE handshake and z0 must all succeed quietly
        r = petoi.connect(request.param)
    if not r.s3:
        r.close()
        pytest.skip(f"{r.model} {r.firmware} is not S3 firmware")
    print(f"\n{request.param}: {r.model} firmware {r.firmware}")
    watch(r)
    yield r
    r.rest()
    r.close()


def test_leg_moves_and_reads_back(robot):
    robot.joint(QuaddleJoint.LEFT_FRONT_LEG, 30)
    assert robot.joints()[QuaddleJoint.LEFT_FRONT_LEG] == 30
    robot.joint(QuaddleJoint.LEFT_FRONT_LEG, 0)


def test_leg_order_matches_quaddle_joint(robot):
    for joint in QuaddleJoint:
        if joint is QuaddleJoint.HEAD_PAN:
            continue
        input(f"Watch the {joint.name.replace('_', ' ').lower()}; press Enter to move it")
        robot.joint(joint, 30)
        robot.joint(joint, 0)
        assert input("Did that leg move? [y/n] ").strip().lower() == "y"


@pytest.mark.skipif(not os.environ.get("PETOI_SCOUT"), reason="set PETOI_SCOUT=1 for a Quaddle Scout (head pan)")
def test_scout_head_pan_is_joint_0(robot):
    input("Watch the head; press Enter to move it")
    robot.joint(QuaddleJoint.HEAD_PAN, 30)
    robot.joint(QuaddleJoint.HEAD_PAN, 0)
    assert input("Did the head turn? [y/n] ").strip().lower() == "y"


def test_robot_stays_still_after_connect(robot):
    robot.stand()
    input("Leave the robot idle for 10 s and watch it. Press Enter when done")
    assert input("Did it stay still (no random head or leg moves)? [y/n] ").strip().lower() == "y"


def test_melody_plays_every_note(robot):
    input("Listen; press Enter to play three notes")
    robot.melody([(12, 4), (14, 4), (16, 2)])
    assert input("Did you hear three notes? [y/n] ").strip().lower() == "y"
