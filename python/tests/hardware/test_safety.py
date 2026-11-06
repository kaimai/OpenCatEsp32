"""Unit tests for safety.py; they need no robot."""
import pytest

import safety
from conftest import FakeStream
from petoi.robot import Robot


@pytest.fixture(autouse=True)
def clean():
    yield
    safety.trouble.clear()
    safety.robots.clear()


def test_trouble_line_stops_the_command_that_read_it():
    r = Robot(FakeStream({b"j\n": ["EXCEPTION: Pushed", "j"]}), timeout=0.2)
    safety.watch(r)
    with pytest.raises(safety.RobotInTrouble):
        r.send("j")
    assert safety.trouble == ["EXCEPTION: Pushed"]


def test_trouble_line_is_seen_even_when_input_is_discarded():
    r = Robot(FakeStream(), timeout=0.2)
    safety.watch(r)
    r.transport.pending.append("EXCEPTION: Fall over")  # printed between commands
    with pytest.raises(safety.RobotInTrouble):
        r.stand()  # nothing is owed, so command() discards input before writing
    assert safety.trouble == ["EXCEPTION: Fall over"]


def test_after_trouble_only_rest_is_sent():
    r = Robot(FakeStream(), timeout=0.2)
    safety.watch(r)
    safety.trouble.append("Trigger released")
    with pytest.raises(safety.RobotInTrouble):
        r.stand()
    assert r.transport.written == []
    r.rest()
    assert r.transport.written == [b"d\n"]


def test_rest_still_goes_out_when_more_trouble_is_buffered():
    r = Robot(FakeStream(), timeout=0.2)
    safety.watch(r)
    r.transport.pending += ["EXCEPTION: Fall over", "EXCEPTION: Roll left", "EXCEPTION: Knocked"]
    with pytest.raises(safety.RobotInTrouble):
        r.stand()
    r.rest()
    assert r.transport.written == [b"d\n"]
    assert safety.trouble[0] == "EXCEPTION: Fall over"


def test_buffered_fall_blocks_the_next_move_even_while_an_echo_is_owed():
    r = Robot(FakeStream(auto_echo=False), timeout=0.2)
    safety.watch(r)
    r.walk(wait=False)  # its echo is owed, so command() won't discard input before the next write
    r.transport.pending.append("EXCEPTION: Fall over")
    with pytest.raises(safety.RobotInTrouble):
        r.stop()
    assert r.transport.written == [b"kwkF\n"]


def test_lines_read_ahead_of_a_write_are_kept_for_the_reply():
    r = Robot(FakeStream(), timeout=0.2)
    safety.watch(r)
    r.transport.pending.append("k")
    r.transport.write_command(b"kup\n")
    assert r.transport.readline(0) == "k"
