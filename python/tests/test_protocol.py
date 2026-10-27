from enum import Enum, IntEnum

import pytest

from petoi.protocol import encode


class _J(IntEnum):
    HEAD = 0


class _S(str, Enum):
    HI = "hi"


def test_ascii_skill():
    # moduleManager.h:400 — lowercase tokens end with '\n'
    assert encode("k", "sit") == b"ksit\n"


def test_ascii_numbers_are_space_separated():
    assert encode("i", 8, 30, 9, -20) == b"i8 30 9 -20\n"


def test_enums_encode_as_their_values():
    # str(IntEnum) is "_J.HEAD" on Python 3.9/3.10, so encode must use .value
    assert encode("i", _J.HEAD, 30) == b"i0 30\n"
    assert encode("k", _S.HI) == b"khi\n"


def test_bare_token():
    assert encode("d") == b"d\n"


def test_binary_token_uses_int8_and_tilde():
    # moduleManager.h:400 — uppercase tokens are binary, end with '~'
    assert encode("I", 8, -20) == b"I\x08\xec~"


def test_binary_rejects_126():
    # moduleManager.h:401 — 126 is '~' and would end the command early
    with pytest.raises(ValueError, match="126"):
        encode("I", 8, 126)


def test_binary_rejects_out_of_int8_range():
    with pytest.raises(ValueError, match="int8"):
        encode("I", 8, 200)


def test_token_must_be_one_character():
    with pytest.raises(ValueError):
        encode("ks", "it")


from petoi.protocol import LineBuffer, Reply, collect_reply, parse_ints  # noqa: E402


def test_parse_ints_from_joint_line():
    # tools.h:89 list2String -> "0,\t-3,\t45,\t"
    assert parse_ints("0,\t-3,\t45,\t") == [0, -3, 45]


def test_collect_reply_stops_at_echo_and_drops_markers():
    # reaction.h:681 prints '=', :685-686 prints two lines, :1557 echoes token
    lines = iter(["=", "0\t1\t2\t", "0,\t-3,\t45,\t", "j", "late"])
    reply = collect_reply("j", lambda: next(lines))
    assert reply == Reply("j", ["0\t1\t2", "0,\t-3,\t45,"], completed=True)


def test_collect_reply_incomplete_when_source_runs_dry():
    lines = iter(["hello", None])
    reply = collect_reply("k", lambda: next(lines))
    assert reply.completed is False
    assert reply.lines == ["hello"]


def test_reply_text_joins_lines():
    assert Reply("?", ["Bittle X", "B10_260820"], True).text == "Bittle X\nB10_260820"


def test_line_buffer_reassembles_chunks():
    buf = LineBuffer()
    assert buf.feed(b"Bit") == []
    assert buf.feed(b"tle X\r\nB10") == ["Bittle X"]
    assert buf.feed(b"\r\n?\r\n") == ["B10", "?"]


def test_token_must_be_ascii():
    with pytest.raises(ValueError, match="ASCII"):
        encode("é")


def test_binary_args_must_be_integers():
    with pytest.raises(ValueError, match="integers, got 1.7"):
        encode("I", 8, 1.7)
    with pytest.raises(ValueError, match="integers"):
        encode("I", "8")


def test_ascii_args_cannot_contain_line_breaks():
    with pytest.raises(ValueError, match="line break"):
        encode("k", "sit\nkup")
    with pytest.raises(ValueError, match="line break"):
        encode("k", "sit\r")


@pytest.mark.parametrize("token", ["X", "R", "W"])
def test_xrw_binary_tokens_reject_bytes_the_firmware_strips(token):
    for bad in (10, 13):
        with pytest.raises(ValueError, match="moduleManager.h:427"):
            encode(token, 1, bad)
    for bad in (9, 32):
        with pytest.raises(ValueError, match="moduleManager.h:427"):
            encode(token, bad, 1)
    assert encode(token, 1, 32) == token.encode() + bytes([1, 32]) + b"~"  # only leading ones are trimmed


def test_other_binary_tokens_allow_newline_bytes():
    assert encode("I", 10, 13) == b"I\x0a\x0d~"
