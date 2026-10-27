import time

import petoi

with petoi.connect() as robot:  # or "bluetooth", "ble", "192.168.4.1"
    print(robot.model, robot.firmware)
    robot.sit()
    robot.walk()
    time.sleep(3)  # Ctrl-C here stops the robot safely
    robot.stop()
    robot.rest()
