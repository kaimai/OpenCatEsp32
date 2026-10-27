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


def test_mock_ignores_out_of_range_joints_like_the_firmware():
    t = MockTransport()
    r = Robot(t)
    r.joint(16, 10)  # must not raise
    r.joint(-1, 10)
    assert t.angles[15] == 0 and len(t.angles) == 16


def test_mock_reports_gyro_state_and_calibrates():
    r = Robot(MockTransport())
    assert r.gyro_state() == {"update": True, "balance": True, "print": False, "fine": True}
    assert r.calibrate_gyro().completed


def test_mock_echoes_a_behavior_twice_like_the_firmware():
    r = Robot(MockTransport())
    assert r.run_skill_data([-1, 0, 0, 1, 0, 0, 0] + [0] * 20).completed
    assert r.info()["model"] == MockTransport.MODEL
