import os
import time

import pytest

import petoi
import scenario
from petoi import Skill
from petoi.constants import ONLY_ON, RISKY
from petoi.transports.base import STALE_SECONDS, StreamTransport
from test_constants import estimate_seconds

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
    model = "nybble" if "nybble" in (robot.model or "").lower() else "bittle"  # an arm build reports as Bittle
    if model not in ONLY_ON.get(skill, {model}):
        pytest.skip(f"{skill.value} is not on {robot.model}")
    if skill in RISKY and not os.environ.get("PETOI_RISKY"):
        pytest.skip("flips, falls and test postures; set PETOI_RISKY=1 with the robot on the floor")
    robot.stand()  # same start posture for every timing
    start = time.monotonic()
    robot.skill(skill)
    elapsed = time.monotonic() - start
    print(f"\n{skill.value}: {elapsed:.1f} s (estimate {estimate_seconds(model, skill.value):.1f} s)")
    assert elapsed < STALE_SECONDS  # a later echo could be taken for a newer command's


def test_melody_confirms_after_it_finishes(robot):
    start = time.monotonic()
    robot.melody([(12, 4), (14, 4), (16, 2)])  # 250 + 250 + 500 ms
    assert time.monotonic() - start >= 0.9


@pytest.mark.parametrize("direction", ["left", "right"])
def test_back_turning_completes(robot, direction):
    robot.back(direction)  # bkR is resolved by prefix match and mirrored (src/skill.h:55-58, :483)
    time.sleep(2)
    robot.stop()


def test_long_command_arrives_intact(robot):
    # Assumption 1: BLE chunking. 7 joint pairs = a 30+ character ASCII command.
    angles = {int(petoi.Joint.HEAD_PAN): 10, 8: 20, 9: 20, 10: 20, 11: 20, 12: 10, 13: 10}
    robot.move_joints(angles)
    for joint, angle in angles.items():
        scenario.wait_for_angle(robot, joint, angle)


@pytest.mark.skipif(not os.environ.get("PETOI_WS"), reason="Wi-Fi only")
def test_wifi_survives_idle_minute():
    # Assumption 3: heartbeat thread keeps the connection
    with petoi.connect(os.environ["PETOI_WS"]) as r:
        time.sleep(60)
        assert r.info()["model"]


def test_gyro_off_then_on_confirms_and_next_command_is_clean(robot):
    robot.gyro(False)  # 'gb' prints 'g' twice; the second must not leak
    assert robot.info()["model"] == robot.model
    robot.gyro(True)


def test_gyro_state_over_usb(robot, request):
    if request.node.callspec.params["robot"] != os.environ.get("PETOI_PORT"):
        pytest.skip("the gyro state line is printed to USB only (src/tools.h:6)")
    robot.gyro(True)
    assert robot.gyro_state()["balance"] is True


def _standing(robot):
    robot.stand()
    angles = robot.joints()
    assert len(angles) == 16 and all(-125 <= a <= 125 for a in angles), angles
    return angles


def test_uploaded_posture_turns_the_head(robot):
    angles = _standing(robot)
    angles[petoi.Joint.HEAD_PAN] = 20
    robot.run_skill_data([1, 0, 0, 1] + angles)
    scenario.wait_for_angle(robot, petoi.Joint.HEAD_PAN, 20)
    robot.stand()


def test_uploaded_behavior_returns_after_it_finishes(robot):
    angles = _standing(robot)
    look = list(angles)
    look[petoi.Joint.HEAD_PAN] = 30
    frames = [angles + [8, 10, 0, 0], look + [8, 10, 0, 0], angles + [8, 0, 0, 0]]  # two 500 ms pauses
    start = time.monotonic()
    robot.run_skill_data([-3, 0, 0, 1, 0, 0, 0] + [v for f in frames for v in f])
    if isinstance(robot.transport, StreamTransport):  # Wi-Fi returns as it starts (src/reaction.h:1565)
        assert time.monotonic() - start >= 1.0
    assert robot.info()["model"] == robot.model  # no leftover K echo
    robot.stand()


def test_largest_upload_arrives_intact(robot):
    angles = _standing(robot)
    last = list(angles)
    last[petoi.Joint.HEAD_PAN] = 20
    frames = [angles + [0, 0, 0, 0]] * 123 + [last + [0, 0, 0, 0]]  # 124 frames, 2487 bytes, speed 0 = jump
    robot.run_skill_data([-124, 0, 0, 1, 0, 0, 0] + [v for f in frames for v in f])
    scenario.wait_for_angle(robot, petoi.Joint.HEAD_PAN, 20)  # lost bytes would misalign the last frame
    robot.skill(Skill.BALANCE)  # "kbalance" must still fit (src/skill.h:131-137)
