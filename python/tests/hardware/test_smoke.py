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
    for joint, angle in angles.items():
        scenario.wait_for_angle(robot, joint, angle)


@pytest.mark.skipif(not os.environ.get("PETOI_WS"), reason="Wi-Fi only")
def test_wifi_survives_idle_minute():
    # Assumption 3: heartbeat thread keeps the connection
    with petoi.connect(os.environ["PETOI_WS"]) as r:
        time.sleep(60)
        assert r.info()["model"]
