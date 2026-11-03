import functools
import os
import re
from pathlib import Path

import pytest

from petoi._timing import skill_seconds
from petoi.constants import ONLY_ON, QUADDLE_SKILLS, RISKY, Joint, QuaddleJoint, Skill, is_s3_firmware, model_key, skills_for
from petoi.transports.base import STALE_SECONDS

SRC = Path(__file__).resolve().parents[2] / "src"
TABLES = {"bittle": "InstinctBittleESP.h", "bittle_arm": "InstinctBittleESP_arm.h", "nybble": "InstinctNybbleESP.h"}
# The firmware headers exist only in a repo checkout, not in an sdist. CI always has them, so never skip there.
needs_headers = pytest.mark.skipif(
    not all((SRC / h).is_file() for h in [*TABLES.values(), "randomMind.h"]) and not os.environ.get("CI"),
    reason="needs the firmware headers in ../src (repo checkout only)",
)


def skill_names(header):
    line = next(l for l in (SRC / header).read_text().splitlines() if "skillNameWithType[]" in l)
    return {name[:-1] for name in re.findall(r'"([^"]+)"', line)}  # drop the trailing type letter


def test_joint_indices_follow_firmware_groups():
    # src/OpenCat.h:235-237 — 0 head pan, 1 tilt, 2 tail, 8-11 shoulder, 12-15 knee
    assert Joint.HEAD_PAN == 0 and Joint.HEAD_TILT == 1 and Joint.TAIL == 2
    assert [j for j in Joint if "SHOULDER" in j.name] == list(range(8, 12))
    assert [j for j in Joint if "KNEE" in j.name] == list(range(12, 16))


def test_skill_values_are_firmware_names():
    # src/InstinctBittleESP.h:2486, src/InstinctNybbleESP.h:1451
    assert Skill.HIGH_FIVE.value == "fiv"
    assert Skill.STAND.value == "up"
    assert Skill.ZERO.value == "zero" and Skill.LICK_PAWS.value == "lkPaws"
    assert not hasattr(Skill, "SLEEP")  # zz is all joints to 0, not sleep (src/InstinctBittleESP.h:2481-2485)


@needs_headers
@pytest.mark.parametrize("model", TABLES)
def test_skills_exist_where_documented(model):
    names = skill_names(TABLES[model])
    expected = {s for s in Skill if model in ONLY_ON.get(s, TABLES)}
    assert {s for s in Skill if s.value in names} == expected


@needs_headers
def test_risky_skills_are_the_ones_random_mode_forbids():
    line = next(l for l in (SRC / "randomMind.h").read_text().splitlines() if "forbiddenSkills[]" in l)
    forbidden = set(re.findall(r'"([^"]+)"', line))  # src/randomMind.h:51
    assert RISKY == {s for s in Skill if s.value in forbidden}


DOF = 16  # src/OpenCat.h:249


@functools.lru_cache(maxsize=None)
def skill_arrays(header):
    text = re.sub(r"//[^\n]*", "", (SRC / header).read_text())
    return {name: [int(v) for v in re.findall(r"-?\d+", body)]
            for name, body in re.findall(r"const int8_t (\w+)\[\] PROGMEM = \{(.*?)\};", text, re.S)}


def estimate_seconds(model, name, start="up"):
    """ESTIMATE of how long k<name> runs before it echoes, starting from the posture `start`."""
    arrays = skill_arrays(TABLES[model])
    posture = arrays[start]
    return skill_seconds(arrays[name], [v * posture[3] for v in posture[4:4 + DOF]])


@needs_headers
def test_some_skills_outlast_the_default_command_timeout():
    assert estimate_seconds("bittle", "pu1") > 5 and estimate_seconds("nybble", "hunt") > 5


@needs_headers
@pytest.mark.parametrize("model", TABLES)
def test_every_skill_is_estimated_to_echo_within_the_stale_window(model):
    worst = {s.value: max(estimate_seconds(model, s.value, p) for p in ("up", "rest"))
             for s in Skill if model in ONLY_ON.get(s, TABLES)}
    assert max(worst.values()) < STALE_SECONDS, worst


def test_skill_seconds_models_a_posture_and_a_looping_behavior():
    start = [0] * DOF
    posture = [1, 0, 0, 1, *([10] * DOF)]  # diff 10 at speed 1: 11 iterations of 8 ms
    assert skill_seconds(posture, start) == 0.088
    row = lambda: [*([0] * DOF), 8, 2, 0, 0]  # speed 1, delay 2 * 50 ms
    behavior = [-2, 0, 0, 1, 0, 1, 3, *row(), *row()]  # frames 0-1 run 3 times in all
    assert skill_seconds(behavior, start) == pytest.approx(0.008 + 6 * (0.008 + 0.1))
    with pytest.raises(ValueError):
        skill_seconds([-1, 0, 0, 1, 0, 0, -1, *row()], start)


@pytest.mark.parametrize("reported, key", [
    ("Bittle X", "bittle"), ("Bittle X+Arm", "bittle_arm"), ("Nybble Q", "nybble"), ("Quaddle", "quaddle"),
    ("Mock Bittle", "bittle"), ("DoF16", None), (None, None),
])
def test_model_key_maps_the_question_mark_reply(reported, key):
    assert model_key(reported) == key


@pytest.mark.parametrize("version, s3", [("Q_261022", True), ("C_261102", True), ("B10_260527", False), (None, False)])
def test_s3_firmware_is_recognised_by_its_board_letter(version, s3):
    assert is_s3_firmware(version) is s3  # OpenCatEsp32S3 OpenCat.h:25-37, :1313


def test_skills_for_esp32_models_follow_only_on():
    assert skills_for("bittle") == {s for s in Skill if "bittle" in ONLY_ON.get(s, TABLES)}
    assert Skill.WASH_FACE in skills_for("nybble") and Skill.WASH_FACE not in skills_for("bittle")


def test_skills_for_quaddle_is_its_own_table():
    assert skills_for("quaddle") == QUADDLE_SKILLS
    assert Skill.BACK_FLIP in QUADDLE_SKILLS and Skill.HUNT not in QUADDLE_SKILLS
    with pytest.raises(ValueError, match="unknown model"):
        skills_for("chero")


def test_quaddle_joints_are_petoi_web_coding_indices():
    # PetoiWebCoding js/product_config.js: legs 2-5 (LF, RF, RB, LB) on every Quaddle; head pan 0 on Scout only
    assert [int(j) for j in QuaddleJoint] == [0, 2, 3, 4, 5]
    assert QuaddleJoint.HEAD_PAN == 0


S3_SRC = os.environ.get("PETOI_S3_SRC")  # src/ of a private OpenCatEsp32S3 checkout; never vendored here
needs_s3 = pytest.mark.skipif(not S3_SRC, reason="set PETOI_S3_SRC to an OpenCatEsp32S3 src/ folder")


@needs_s3
def test_quaddle_skills_match_its_instinct_table():
    line = next(l for l in (Path(S3_SRC) / "Instinct_Quaddle.h").read_text(errors="replace").splitlines()
                if "skillNameWithType[]" in l)
    names = {n[:-1] for n in re.findall(r'"([^"]+)"', line)}
    assert {s for s in Skill if s.value in names} == QUADDLE_SKILLS
