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


def test_late_echo_of_unwaited_command_does_not_confirm_next_one():
    s = FakeStream(auto_echo=False)
    s.command("k", b"kwkF\n", timeout=0)  # nothing waits; its echo is still to come
    s.replies[b"ksit\n"] = ["k"]  # that late echo arrives during the next command
    reply = s.command("k", b"ksit\n", timeout=0.05)
    assert reply.completed is False  # the only "k" was the stale one


def test_second_echo_confirms_after_stale_one_is_consumed():
    s = FakeStream(auto_echo=False)
    s.command("k", b"kwkF\n", timeout=0)
    s.replies[b"ksit\n"] = ["k", "k"]
    assert s.command("k", b"ksit\n", timeout=0.05).completed
    assert s.discards == 1  # only the first command discarded; stale echoes must be kept


def test_expired_unconfirmed_entry_is_ignored(monkeypatch):
    import petoi.transports.base as base

    monkeypatch.setattr(base, "STALE_SECONDS", 0)
    s = FakeStream(auto_echo=False)
    s.command("k", b"kwkF\n", timeout=0)
    s.command("k", b"ksit\n", timeout=0)  # first entry expired at once, so input is discarded again
    assert s.discards == 2


def test_one_lost_echo_does_not_break_every_later_command():
    s = FakeStream({b"ksit\n": []})  # robot never echoes this one
    assert s.command("k", b"ksit\n", timeout=0.05).completed is False
    s.replies.clear()
    results = [s.command("k", p, timeout=0.05).completed for p in [b"ksit\n", b"kup\n"] * 3]
    assert results.count(False) <= 1
    assert results[1:] == [True] * 5


def test_stale_echo_matching_a_later_pending_entry_does_not_confirm():
    s = FakeStream(auto_echo=False)
    s.command("i", b"i8 30\n", timeout=0)  # echo lost
    s.command("k", b"kfiv\n", timeout=0)
    s.replies[b"ksit\n"] = ["k"]  # fiv's late echo only
    assert s.command("k", b"ksit\n", timeout=0.05).completed is False

    s = FakeStream(auto_echo=False)
    s.command("i", b"i8 30\n", timeout=0)
    s.command("k", b"kfiv\n", timeout=0)
    s.replies[b"ksit\n"] = ["k", "k"]
    assert s.command("k", b"ksit\n", timeout=0.05).completed


def test_genuine_late_echo_then_own_echo_completes():
    s = FakeStream(auto_echo=False)
    s.command("k", b"kfiv\n", timeout=0)
    s.replies[b"ksit\n"] = ["k", "k"]
    assert s.command("k", b"ksit\n", timeout=0.05).completed


def test_expect_waits_for_another_echo_without_writing():
    s = FakeStream(auto_echo=False)
    s.pending = ["moving", "K"]
    reply = s.expect("K", timeout=0.05)
    assert reply.completed and reply.lines == ["moving"] and s.written == []


def test_expect_zero_timeout_marks_the_echo_owed():
    s = FakeStream(auto_echo=False)
    s.expect("K", timeout=0)
    s.replies[b"ksit\n"] = ["K", "k"]
    reply = s.command("k", b"ksit\n", timeout=0.05)
    assert reply.completed and reply.lines == []


def test_owed_entry_expires_from_when_the_wait_ends(monkeypatch):
    import time

    import petoi.transports.base as base

    monkeypatch.setattr(base, "STALE_SECONDS", 0.1)
    s = FakeStream(auto_echo=False)
    s.readline = lambda timeout: time.sleep(timeout)  # the robot stays silent for the whole wait
    s.expect("k", timeout=0.15)  # longer than the stale window
    assert s._unconfirmed and s._unconfirmed[-1][1] > time.monotonic()


def _record_sleeps(monkeypatch):
    import petoi.transports.base as base

    slept = []
    monkeypatch.setattr(base.time, "sleep", slept.append)
    return slept


def test_command_right_after_an_unconfirmed_one_waits_out_the_gap(monkeypatch):
    # read_serial() takes every waiting byte, so two commands in its buffer become one (src/moduleManager.h:404-440)
    from petoi.transports.base import StreamTransport

    slept = _record_sleeps(monkeypatch)
    s = FakeStream(auto_echo=False)
    s.command("k", b"kwkF\n", timeout=0)
    s.command("k", b"kbalance\n", timeout=0)
    assert len(slept) == 1 and 0 < slept[0] <= StreamTransport.WRITE_GAP
    assert s.written == [b"kwkF\n", b"kbalance\n"]


def test_confirmed_command_does_not_slow_the_next_one(monkeypatch):
    slept = _record_sleeps(monkeypatch)
    s = FakeStream()
    assert s.command("k", b"ksit\n", timeout=1.0).completed
    assert s.command("k", b"kup\n", timeout=1.0).completed
    assert slept == []


def test_write_command_paces_the_next_command(monkeypatch):
    slept = _record_sleeps(monkeypatch)
    s = FakeStream()
    s.write_command(b"I\x08\xec~")  # never confirmed, e.g. S3 I over USB
    s.command("k", b"ksit\n", timeout=1.0)
    assert len(slept) == 1


def test_late_rewritten_echo_is_recognized_as_stale():
    s = FakeStream(auto_echo=False)
    s.command("g", b"g\n", timeout=0)  # toggles balance; echoes G or g later
    s.replies[b"ksit\n"] = ["G", "k"]
    reply = s.command("k", b"ksit\n", timeout=0.05)
    assert reply.completed and reply.lines == []
