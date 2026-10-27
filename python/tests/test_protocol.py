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
