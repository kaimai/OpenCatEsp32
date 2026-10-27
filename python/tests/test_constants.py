import re
from pathlib import Path

import pytest

from petoi.constants import ONLY_ON, RISKY, Skill, Joint

SRC = Path(__file__).resolve().parents[2] / "src"
TABLES = {"bittle": "InstinctBittleESP.h", "bittle_arm": "InstinctBittleESP_arm.h", "nybble": "InstinctNybbleESP.h"}


def skill_names(header):
    line = next(l for l in (SRC / header).read_text().splitlines() if "skillNameWithType[]" in l)
    return {name[:-1] for name in re.findall(r'"([^"]+)"', line)}  # drop the trailing type letter


def test_joint_indices_follow_firmware_groups():
    # src/OpenCat.h:235-237 — 0 head pan, 1 tilt, 2 tail, 8-11 shoulder, 12-15 knee
    assert Joint.HEAD_PAN == 0 and Joint.HEAD_TILT == 1 and Joint.TAIL == 2
    assert [j for j in Joint if "SHOULDER" in j.name] == list(range(8, 12))
    assert [j for j in Joint if "KNEE" in j.name] == list(range(12, 16))


def test_skill_values_are_firmware_names():
    # src/InstinctBittleESP.h:2486
    assert Skill.HIGH_FIVE.value == "fiv"
    assert Skill.STAND.value == "up"


@pytest.mark.parametrize("model", TABLES)
def test_skills_exist_where_documented(model):
    names = skill_names(TABLES[model])
    expected = {s for s in Skill if model in ONLY_ON.get(s, TABLES)}
    assert {s for s in Skill if s.value in names} == expected


def test_risky_skills_are_the_ones_random_mode_forbids():
    line = next(l for l in (SRC / "randomMind.h").read_text().splitlines() if "forbiddenSkills[]" in l)
    forbidden = set(re.findall(r'"([^"]+)"', line))  # src/randomMind.h:51
    assert RISKY == {s for s in Skill if s.value in forbidden}
