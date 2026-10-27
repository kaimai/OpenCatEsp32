from enum import Enum, IntEnum


class Joint(IntEnum):
    """Joint indices. Groups come from src/OpenCat.h:235-237; the leg order inside
    each group is checked on hardware (plan Assumption 5)."""

    HEAD_PAN = 0
    HEAD_TILT = 1
    TAIL = 2
    LEFT_FRONT_SHOULDER = 8
    RIGHT_FRONT_SHOULDER = 9
    RIGHT_BACK_SHOULDER = 10
    LEFT_BACK_SHOULDER = 11
    LEFT_FRONT_KNEE = 12
    RIGHT_FRONT_KNEE = 13
    RIGHT_BACK_KNEE = 14
    LEFT_BACK_KNEE = 15


class Skill(str, Enum):
    """Built-in one-shot skills (names from src/InstinctBittleESP.h:2486)."""

    SIT = "sit"
    STAND = "up"
    BALANCE = "balance"
    STRETCH = "str"
    HI = "hi"
    PUSH_UP = "pu"
    CHECK = "ck"
    PEE = "pee"
    SNIFF = "snf"
    SCRATCH = "scrh"
    SLEEP = "zz"
    HIGH_FIVE = "fiv"
    HANDSHAKE = "hsk"
