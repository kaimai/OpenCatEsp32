import petoi

with petoi.connect("mock") as robot:  # no hardware needed
    print(robot.model, robot.firmware)
    robot.sit()
    robot.joint(petoi.Joint.HEAD_PAN, 30)
    print("head angle:", robot.joints()[petoi.Joint.HEAD_PAN])
