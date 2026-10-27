import threading
import time

import pytest

from conftest import FakeStream
from petoi.constants import Joint, Skill
from petoi.errors import RobotTimeout
from petoi.robot import Robot


def robot(replies=None, **kw):
    return Robot(FakeStream(replies or {}, **kw), timeout=0.2)


def test_raw_send_appends_newline():
    assert robot().send("ksit").completed


def test_raw_send_accepts_space_after_token():
    r = robot({b"k sit\n": ["k"]})
    assert r.send("k sit").completed


@pytest.mark.parametrize(
    "call, sent",
    [
        (lambda r: r.sit(), b"ksit\n"),
        (lambda r: r.stand(), b"kup\n"),
        (lambda r: r.rest(), b"d\n"),
        (lambda r: r.stop(), b"kup\n"),
        (lambda r: r.walk(), b"kwkF\n"),
        (lambda r: r.walk("left"), b"kwkL\n"),
        (lambda r: r.trot("right"), b"ktrR\n"),
        (lambda r: r.crawl(), b"kcrF\n"),
        (lambda r: r.back(), b"kbk\n"),
        (lambda r: r.skill("hi"), b"khi\n"),
        (lambda r: r.skill(Skill.HIGH_FIVE), b"kfiv\n"),
        (lambda r: r.joint(8, 30), b"i8 30\n"),
        (lambda r: r.joint(Joint.HEAD_PAN, -20), b"i0 -20\n"),
        (lambda r: r.move_joints({8: 30, 9: -20}), b"i8 30 9 -20\n"),
        (lambda r: r.move_joints({0: 45}, sequential=True), b"m0 45\n"),
        (lambda r: r.beep(12, 8), b"b12 8\n"),
    ],
)
def test_high_level_commands(call, sent):
    r = robot()
    call(r)
    assert r.transport.written[-1] == sent


def test_unknown_direction_is_a_clear_error():
    with pytest.raises(ValueError, match="forward, left, right"):
        robot().walk("up")


def test_high_level_raises_when_robot_never_confirms():
    r = robot(auto_echo=False)
    with pytest.raises(RobotTimeout, match="did not confirm"):
        r.sit()


def test_raw_send_returns_incomplete_instead_of_raising():
    assert robot(auto_echo=False).send("ksit").completed is False


def test_wait_false_neither_waits_nor_raises():
    robot(auto_echo=False).skill("hi", wait=False)


def test_joints_parses_angle_line():
    r = robot({b"j\n": ["=", "0\t1\t2\t", "0,\t-3,\t45,\t", "j"]})
    assert r.joints() == [0, -3, 45]


def test_info_returns_model_and_version():
    r = robot({b"?\n": ["Bittle X", "B10_260820", "?"]})
    assert r.info() == {"model": "Bittle X", "version": "B10_260820"}


def test_context_manager_closes():
    r = robot()
    with r:
        pass
    assert r.transport.closed


def test_exception_inside_with_stops_robot_then_closes():
    r = robot()
    with pytest.raises(KeyboardInterrupt):
        with r:
            r.walk()
            raise KeyboardInterrupt
    assert r.transport.written[-1] == b"kup\n"
    assert r.transport.closed


class SlowStream(FakeStream):
    def __init__(self):
        super().__init__()
        self.active = 0
        self.max_active = 0

    def command(self, *args, **kwargs):
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        time.sleep(0.01)
        try:
            return super().command(*args, **kwargs)
        finally:
            self.active -= 1


def test_commands_from_threads_never_overlap():
    s = SlowStream()
    r = Robot(s)
    threads = [threading.Thread(target=r.sit) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert s.max_active == 1


def test_send_timeout_zero_does_not_wait():
    r = robot(auto_echo=False)
    seen = []
    real = r.transport.command
    r.transport.command = lambda token, payload, timeout: (seen.append(timeout), real(token, payload, timeout))[1]
    r.send("ksit", timeout=0)
    assert seen == [0]


def test_send_rejects_embedded_newline():
    with pytest.raises(ValueError, match="newline"):
        robot().send("ksit\nkup")


def test_send_keeps_working_with_trailing_line_ending():
    r = robot()
    assert r.send("ksit\r\n").completed
    assert r.transport.written == [b"ksit\r\n"]


def test_send_rejects_uppercase_token():
    with pytest.raises(ValueError, match="send_binary"):
        robot().send("I8 30")


class FailingStop(FakeStream):
    def write(self, data):
        if data == b"kup\n":
            raise OSError("port gone")
        super().write(data)


def test_failed_safe_stop_does_not_mask_the_users_exception():
    r = Robot(FailingStop())
    with pytest.raises(KeyboardInterrupt):
        with r:
            raise KeyboardInterrupt
    assert r.transport.closed


def test_send_rejects_bare_carriage_return():
    with pytest.raises(ValueError, match="carriage return"):
        robot().send("ksit\rkup")
