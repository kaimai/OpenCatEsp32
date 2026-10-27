from petoi import Joint, Robot, Skill


def run(robot: Robot) -> None:
    info = robot.info()
    assert info["model"] and info["version"]
    robot.sit()
    robot.stand()
    robot.joint(Joint.HEAD_PAN, 30)
    assert robot.joints()[Joint.HEAD_PAN] == 30
    robot.move_joints({Joint.HEAD_PAN: 0, Joint.HEAD_TILT: 10})
    robot.send_binary("I", int(Joint.HEAD_PAN), -15)
    assert robot.joints()[Joint.HEAD_PAN] == -15
    robot.skill(Skill.HI)
    robot.walk()
    robot.stop()
    assert robot.send("d").completed
