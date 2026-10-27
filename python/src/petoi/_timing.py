"""ESTIMATE of how long a firmware skill runs; ignores servo-write time and counts IMU triggers at their 2 s cap."""
from typing import Sequence

DOF = 16  # src/OpenCat.h:249
_FRAME = DOF + 4  # angles, speed, delay, trigger, trigger angle (src/skill.h:118-126)


def skill_seconds(data: Sequence[int], start: Sequence[int]) -> float:
    """Seconds the firmware spends in one skill array (posture or behavior) from `start`, the 16 current angles."""
    angles = list(start)

    def move(target, ratio, speed):  # transform(): steps+1 iterations of 8 ms (src/motion.h:176-203)
        diff = max(abs(a - t * ratio) for a, t in zip(angles, target))
        angles[:] = [t * ratio for t in target]
        return ((int(diff / speed + 0.5) if speed > 0 else 0) + 1) * DOF // 2

    period, ratio = data[0], data[3]
    if period == 1:  # posture
        return move(data[4:4 + DOF], ratio, 1) / 1000
    first, last, cycles = data[4:7]  # src/skill.h:155-158
    rows = [data[7 + k * _FRAME:7 + (k + 1) * _FRAME] for k in range(-period)]
    ms = move(rows[0][:DOF], ratio, 1)  # loadBySkillName moves to frame 0 first (src/skill.h:512)
    repeat = 0 if 0 <= cycles < 2 else cycles - 1  # src/skill.h:282
    if repeat < 0:
        raise ValueError("skill loops until reset")
    c = 0
    while c < -period:  # src/skill.h:285-363
        row = rows[c]
        ms += move(row[:DOF], ratio, row[DOF] / 8) + abs(row[DOF + 1]) * 50 + (2000 if row[DOF + 2] else 0)
        if repeat and c and c == last:
            c, repeat = first - 1, repeat - 1
        c += 1
    return ms / 1000
