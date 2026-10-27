import os
import time

import pytest

import petoi
import scenario
from petoi import Skill
from petoi.constants import ONLY_ON, RISKY

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
        pytest.skip("flips and falls; set PETOI_RISKY=1 with the robot on the floor")
    robot.skill(skill)


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
