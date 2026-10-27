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
