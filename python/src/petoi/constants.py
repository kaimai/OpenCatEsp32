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
    """Built-in one-shot skills and postures. Any other name in the robot's skill
    table still works through robot.skill("name").

    Names come from skillNameWithType in src/InstinctBittleESP.h,
    src/InstinctBittleESP_arm.h and src/InstinctNybbleESP.h; ONLY_ON lists the
    members that are missing from some of them."""

    SIT = "sit"
    STAND = "up"
    BALANCE = "balance"
    STRETCH = "str"
    BUTT_UP = "buttUp"
    HI = "hi"
    PUSH_UP = "pu"
    CHECK = "ck"
    PEE = "pee"
    SNIFF = "snf"
    SCRATCH = "scrh"
    SLEEP = "zz"
    HIGH_FIVE = "fiv"
    HANDSHAKE = "hsk"
    ANGRY = "ang"
    BOXING = "bx"
    CHEER = "chr"
    COME_HERE = "cmh"
    DIG = "dg"
    GOOD_BOY = "gdb"
    HANDSTAND = "hds"
    HUG = "hg"
    HANDS_UP = "hu"
    HUNT = "hunt"
    KICK = "kc"
    NOD = "nd"
    PLAY_DEAD = "pd"
    RECOVER = "rc"
    TABLE = "tbl"
    WAVE_HEAD = "wh"
    CLAP = "clap"
    JUMP = "jmp"
    LEAP_OVER = "lpov"
    MOONWALK = "mw"
    PUSH_UP_ONE_HAND = "pu1"
    SHOW_OFF = "showOff"
    BACK_FLIP = "bf"
    FRONT_FLIP = "ff"
    ROLL = "rl"
    WASH_FACE = "wsf"


_BITTLE = {"bittle", "bittle_arm"}

# Skills that only some instinct tables have; every other member is on all three.
ONLY_ON = {
    Skill.SLEEP: _BITTLE,
    Skill.CLAP: _BITTLE,
    Skill.JUMP: _BITTLE,
    Skill.LEAP_OVER: _BITTLE,
    Skill.MOONWALK: _BITTLE,
    Skill.PUSH_UP_ONE_HAND: _BITTLE,
    Skill.SHOW_OFF: _BITTLE,
    Skill.BACK_FLIP: {"bittle"},
    Skill.FRONT_FLIP: {"bittle"},
    Skill.ROLL: {"bittle"},
    Skill.WASH_FACE: {"nybble"},
}

# Flips, falls and other violent moves the firmware keeps out of random mode
# (src/randomMind.h:51). Clear some space before running these.
RISKY = {
    Skill.SLEEP, Skill.ANGRY, Skill.PLAY_DEAD, Skill.RECOVER, Skill.JUMP,
    Skill.LEAP_OVER, Skill.BACK_FLIP, Skill.FRONT_FLIP, Skill.ROLL,
}
