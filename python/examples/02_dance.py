import petoi
from petoi import Joint, Skill

with petoi.connect() as robot:
    robot.stand()
    for angle in (40, -40, 0):
        robot.joint(Joint.HEAD_PAN, angle)
    robot.skill(Skill.HI)
    robot.send("kpu")  # any serial-monitor command works too
    robot.rest()
