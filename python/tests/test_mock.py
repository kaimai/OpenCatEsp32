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
