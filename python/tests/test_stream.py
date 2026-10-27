from conftest import FakeStream


def test_command_waits_for_echo():
    s = FakeStream({b"ksit\n": ["k"]})
    reply = s.command("k", b"ksit\n", timeout=1.0)
    assert reply.completed
    assert s.written == [b"ksit\n"]


def test_command_discards_stale_input_first():
    s = FakeStream(auto_echo=False)
    s.pending = ["k"]  # leftover echo from an earlier command
    reply = s.command("k", b"ksit\n", timeout=0.05)
    assert s.discards == 1
    assert reply.completed is False


def test_zero_timeout_does_not_read():
    s = FakeStream({b"kwkF\n": ["k"]})
    reply = s.command("k", b"kwkF\n", timeout=0)
    assert reply.completed is False
    assert s.pending == ["k"]
