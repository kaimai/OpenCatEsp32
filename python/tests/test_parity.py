import scenario
from petoi.robot import Robot
from petoi.transports.mock import MockTransport


def test_scenario_on_mock():
    scenario.run(Robot(MockTransport()))
