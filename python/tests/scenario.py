import time

from petoi import Joint, Robot, Skill


def wait_for_angle(robot: Robot, joint: int, expected: int, tolerance: int = 3, timeout: float = 2.0) -> None:
    """Poll until a joint reads near expected. Head-only moves finish after the echo
    (src/reaction.h:1043-1047) and gyro balance shifts readings slightly."""
    deadline = time.monotonic() + timeout
    while True:
        angle = robot.joints()[joint]
        if abs(angle - expected) <= tolerance:
            return
        if time.monotonic() >= deadline:
            raise AssertionError(f"joint {int(joint)}: expected {expected}±{tolerance}, last read {angle}")
        time.sleep(0.1)


def run(robot: Robot) -> None:
    info = robot.info()
    assert info["model"] and info["version"]
    robot.sit()
    robot.stand()
    robot.joint(Joint.HEAD_PAN, 30)
    wait_for_angle(robot, Joint.HEAD_PAN, 30)
    robot.move_joints({Joint.HEAD_PAN: 0, Joint.HEAD_TILT: 10})
    robot.send_binary("I", int(Joint.HEAD_PAN), -15)
    wait_for_angle(robot, Joint.HEAD_PAN, -15)
    robot.skill(Skill.HI)
    robot.walk()
    robot.stop()
    assert robot.send("d").completed
