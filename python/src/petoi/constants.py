from enum import Enum, IntEnum
from typing import FrozenSet, Optional


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
    ZERO = "zero"
    CALIBRATION_POSE = "calib"
    SERVO_TEST = "ts"
    LAND = "lnd"
    DROP_RECOVER = "dropRec"
    KNOCK = "knock"
    LUCKY_CAT = "lucky"
    LOOK_UP = "lu"
    LICK_PAWS = "lkPaws"
    HEAD_TOSS = "headToss"
    PICK_DOWN = "pickD"   # PICK_DOWN..LAUNCH are for the robot arm
    PICK_FRONT = "pickF"
    PUT_DOWN = "putD"
    PUT_FRONT = "putF"
    TOSS_FRONT = "tossF"
    LAUNCH = "launch"


_BITTLE = {"bittle", "bittle_arm"}

# Skills that only some instinct tables have; every other member is on all three.
ONLY_ON = {
    Skill.CLAP: _BITTLE,
    Skill.JUMP: _BITTLE,
    Skill.LEAP_OVER: _BITTLE,
    Skill.MOONWALK: _BITTLE,
    Skill.PUSH_UP_ONE_HAND: _BITTLE,
    Skill.SHOW_OFF: _BITTLE,
    Skill.LAND: _BITTLE,
    Skill.PICK_DOWN: _BITTLE,
    Skill.PICK_FRONT: _BITTLE,
    Skill.PUT_DOWN: _BITTLE,
    Skill.PUT_FRONT: _BITTLE,
    Skill.TOSS_FRONT: _BITTLE,
    Skill.LAUNCH: _BITTLE,
    Skill.BACK_FLIP: {"bittle"},
    Skill.FRONT_FLIP: {"bittle"},
    Skill.ROLL: {"bittle"},
    Skill.KNOCK: {"bittle", "nybble"},
    Skill.LUCKY_CAT: {"bittle", "nybble"},
    Skill.WASH_FACE: {"nybble"},
    Skill.LOOK_UP: {"nybble"},
    Skill.LICK_PAWS: {"nybble"},
    Skill.HEAD_TOSS: {"nybble"},
}

# Flips, falls, and test postures the firmware keeps out of random mode
# (src/randomMind.h:51). Clear some space before running these.
RISKY = {
    Skill.ANGRY, Skill.PLAY_DEAD, Skill.RECOVER, Skill.JUMP, Skill.LEAP_OVER,
    Skill.BACK_FLIP, Skill.FRONT_FLIP, Skill.ROLL,
    Skill.ZERO, Skill.CALIBRATION_POSE, Skill.SERVO_TEST, Skill.LAND,
}


class QuaddleJoint(IntEnum):
    """Quaddle's joint indices. Every Quaddle has the four legs (2-5); Quaddle Scout
    also has a head pan (0). Both report "Quaddle" to '?', so the API can't tell them
    apart. The firmware reserves 6 slots (DOF 6); index 1 is unused. Indices as
    Petoi's web coding app lists them (PetoiWebCoding js/product_config.js)."""

    HEAD_PAN = 0  # Quaddle Scout only
    LEFT_FRONT_LEG = 2
    RIGHT_FRONT_LEG = 3
    RIGHT_BACK_LEG = 4
    LEFT_BACK_LEG = 5


# The Skill members in Quaddle's table (Instinct_Quaddle.h in the private
# OpenCatEsp32S3 repo, 5ed0ad9). Quaddle has many more of its own; run them with skill("name").
QUADDLE_SKILLS: FrozenSet[Skill] = frozenset({
    Skill.SIT, Skill.STAND, Skill.BALANCE, Skill.STRETCH, Skill.BUTT_UP, Skill.HI, Skill.PEE,
    Skill.SCRATCH, Skill.HANDSHAKE, Skill.HANDSTAND, Skill.KICK, Skill.NOD, Skill.PLAY_DEAD,
    Skill.RECOVER, Skill.WAVE_HEAD, Skill.BACK_FLIP, Skill.FRONT_FLIP, Skill.ZERO,
    Skill.CALIBRATION_POSE, Skill.SERVO_TEST, Skill.DROP_RECOVER,
})

_ESP32_MODELS = ("bittle", "bittle_arm", "nybble")


def model_key(model: Optional[str]) -> Optional[str]:
    """Map the model a robot reports to '?' (e.g. "Bittle X+Arm") to a short key, or None if unknown."""
    low = (model or "").lower()
    if "quaddle" in low:
        return "quaddle"
    if "nybble" in low:
        return "nybble"
    if "bittle" in low:
        return "bittle_arm" if "arm" in low else "bittle"
    return None


def skills_for(model: str) -> FrozenSet[Skill]:
    """The Skill members a model's firmware has, by model_key()."""
    if model == "quaddle":
        return QUADDLE_SKILLS
    if model in _ESP32_MODELS:
        return frozenset(s for s in Skill if model in ONLY_ON.get(s, _ESP32_MODELS))
    raise ValueError(f"unknown model {model!r}")


def is_s3_firmware(version: Optional[str]) -> bool:
    """True for OpenCatEsp32S3 firmware: its version is BOARD_DATE with board Q (Quaddle) or C (Chero)."""
    return (version or "")[:2] in ("Q_", "C_")
