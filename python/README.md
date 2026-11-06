# petoi

Control Petoi OpenCat robots (Bittle X, Nybble Q and other ESP32 BiBoard robots) from Python, over USB, Bluetooth Classic, BLE, or Wi-Fi.

> Status: 0.1.0, not yet tested against every kind of real robot. See "Known limitations" below.

## Install

From this repository (the repository root):

```bash
pip install ./python
pip install "./python[all]"   # with BLE and Wi-Fi
```

After the first PyPI release you will be able to install it with pip directly:

```bash
pip install petoi            # USB and Bluetooth Classic
pip install "petoi[ble]"     # adds BLE
pip install "petoi[wifi]"    # adds Wi-Fi
pip install "petoi[all]"     # everything
```

Python 3.9 or newer.

## No robot yet?

`"mock"` is a built-in fake robot, so you can try the API right now:

```python
import petoi

with petoi.connect("mock") as robot:
    print(robot.model, robot.firmware)   # Mock Bittle MOCK_260820
    robot.sit()
    robot.joint(petoi.Joint.HEAD_PAN, 30)
    print("head angle:", robot.joints()[petoi.Joint.HEAD_PAN])
```

This is `examples/00_no_robot.py`. The mock does not model everything the real firmware does.

## Quick start

```python
import time

import petoi

with petoi.connect() as robot:  # finds a USB robot by itself
    robot.sit()
    robot.walk()
    time.sleep(3)  # Ctrl-C here stops the robot safely
    robot.stop()
    robot.rest()
```

(`examples/01_hello.py` also prints the model and firmware.) Leaving the `with` block because of an error or Ctrl-C makes the robot stand still before the connection closes.

## Connecting

| Call | Connects to |
|---|---|
| `petoi.connect()` | The only USB robot plugged in (error if there are none or several) |
| `petoi.connect("/dev/cu.usbserial-1410")` | A specific serial port (`COM3` on Windows) |
| `petoi.connect("bluetooth")` | A paired Bluetooth Classic robot (its port name contains `_SSP`) |
| `petoi.connect("ble")` | A BLE robot found by scanning. `"ble:<address>"` picks one |
| `petoi.connect("192.168.4.1")` | Wi-Fi, by IP address, `ws://...` URL, or `name.local` |
| `petoi.connect("mock")` | The built-in fake robot |

`connect(target, timeout=5.0, check_firmware=True)`: `timeout` is how many seconds each command may wait for the robot to confirm. `skill()` waits up to `robot.skill_timeout` (30 s) instead, because a one-shot skill confirms only when it finishes. Raise it with `robot.skill_timeout = 60` or `robot.skill("name", timeout=60)`.

Run `petoi ports` (see CLI below) to see what serial ports your computer has.

`connect("bluetooth")` finds the robot by `_SSP` in the port name, which macOS does. On Windows and Linux the Bluetooth port has no such name, so pass the Bluetooth COM port or `/dev/rfcomm*` port explicitly.

### USB takes a while to connect

Opening a USB serial port usually resets the robot's board, so it reboots. `connect()` waits for the robot to print `Ready!`, for up to 20 seconds, so your first command is not lost during boot. If the robot prints nothing for 1.5 seconds right after opening, it is assumed to be running already and the wait ends early. Bluetooth Classic does not reset the board, so it does not wait. If `Ready!` never appears, you get a warning (the robot may be waiting at a calibration prompt) and you can open a serial monitor to check.

### Old firmware

After connecting, the library asks the robot for its model and firmware version. If the firmware is older than `260820`, or does not answer, you get a `RuntimeWarning` suggesting an update with the Petoi Desktop App. Everything may still work. Pass `check_firmware=False` to skip the check (then `robot.model` and `robot.firmware` stay `None`).

### Putting the robot on Wi-Fi

Plug in the USB cable once, and the robot joins your Wi-Fi and tells you its address:

```python
import getpass

import petoi

with petoi.connect() as robot:  # over USB
    ip = robot.setup_wifi("MyHomeWiFi", getpass.getpass("Wi-Fi password: "))
print("robot is at", ip)

with petoi.connect(ip) as robot:  # now over Wi-Fi; the cable can come out
    robot.sit()
```

- It takes up to a minute: the robot tries the network up to 3 times, then reboots to start its Wi-Fi server. `setup_wifi()` returns once it is back. (A Quaddle starts its Wi-Fi server without rebooting.)
- The robot remembers the network and joins it every time it starts.
- 2.4 GHz networks only. The name is 1 to 32 bytes and cannot contain `%`. The password is up to 64 characters; use `""` for an open network.
- A wrong name or password raises `petoi.WifiSetupFailed`. Your password never appears in error messages (the robot's own serial monitor shows its last 4 characters).
- If the robot is already on Wi-Fi it ignores the new details, and `setup_wifi()` returns its current address with a warning. To switch networks, hold the robot's BOOT button for about 3 seconds to clear the saved one, then run `setup_wifi()` again.
- USB only: over Bluetooth the reboot drops the link.

### Robots and firmware

| Robot | Firmware | Links | Joints |
|---|---|---|---|
| Bittle X, Bittle X+Arm, Nybble Q | OpenCatEsp32 (BiBoard) | USB, Bluetooth, BLE, Wi-Fi | `Joint` (16) |
| Quaddle | OpenCatEsp32S3 | USB, BLE, Wi-Fi (no Bluetooth Classic) | `QuaddleJoint`: 4 legs; Quaddle Scout also has `HEAD_PAN` |

`robot.s3` tells you which firmware you're on. On S3 firmware, `connect()` sends `z0` so the robot stops moving
by itself when idle (until it reboots). On a Quaddle, `send_binary("I"/"M")` over USB is never confirmed. Use
`joint()` / `move_joints()` instead. Skills: `petoi.constants.skills_for("quaddle")` lists the `Skill` members a
Quaddle has. Its other skills work with `robot.skill("name")`.

## High-level methods

| Method | What it does |
|---|---|
| `sit()`, `stand()` | Posture |
| `walk()`, `trot()`, `crawl()` | Gait, forward by default. `direction="left"` or `"right"`. Keeps going until `stop()` |
| `back()` | Walk backward; `back("left")` or `back("right")` turns while backing up. Keeps going until `stop()` |
| `stop()` | Stand still |
| `rest()` | Lie down and turn the servos off |
| `skill(Skill.HI)` | Run a built-in one-shot skill (a `Skill` or its short name such as `"hi"`) |
| `run_skill_data(data)` | Upload and run your own skill array (see "Custom skills") |
| `joint(Joint.HEAD_PAN, 30)` | Move one joint to an angle in degrees (decimals are rounded to the nearest degree) |
| `move_joints({Joint.HEAD_PAN: 30, Joint.HEAD_TILT: 10})` | Move several joints together. `sequential=True` moves them one after another |
| `joints()` | Current angle of every joint, as a list indexed by joint number |
| `beep(note, duration)` | Play one note: `note` is semitones above C6 (0 is a rest); it lasts 1/`duration` of a second, so `beep(12, 8)` is 125 ms. On Quaddle it returns as the note starts |
| `melody([(12, 8), (14, 8), (16, 4)])` | Play several `(note, duration)` pairs; returns when the tune ends |
| `gyro(on)` | Turn gyro balancing on or off (off before tricks it would fight) |
| `gyro_state()` | `{"update", "balance", "print", "fine"}` flags as booleans; USB only (raises `RobotError` over Bluetooth/Wi-Fi) |
| `calibrate_gyro()` | Calibrate and save the gyro (~20 s). The servos turn off: lay the robot flat and don't touch it. Raises `RobotError` if it didn't finish |
| `info()` | `{"model": ..., "version": ...}` |
| `setup_wifi(ssid, password)` | Over USB, put the robot on Wi-Fi; returns its IP address for `connect()` |

`Joint` names: `HEAD_PAN`, `HEAD_TILT`, `TAIL`, `LEFT_FRONT_SHOULDER`, `RIGHT_FRONT_SHOULDER`, `RIGHT_BACK_SHOULDER`, `LEFT_BACK_SHOULDER`, `LEFT_FRONT_KNEE`, `RIGHT_FRONT_KNEE`, `RIGHT_BACK_KNEE`, `LEFT_BACK_KNEE`. You can also pass plain joint numbers.

`Skill` names: `SIT`, `STAND`, `BALANCE`, `STRETCH`, `BUTT_UP`, `HI`, `PUSH_UP`, `CHECK`, `PEE`, `SNIFF`, `SCRATCH`, `HIGH_FIVE`, `HANDSHAKE`, `ANGRY`, `BOXING`, `CHEER`, `COME_HERE`, `DIG`, `GOOD_BOY`, `HANDSTAND`, `HUG`, `HANDS_UP`, `HUNT`, `KICK`, `NOD`, `PLAY_DEAD`, `RECOVER`, `TABLE`, `WAVE_HEAD`, `CLAP`, `JUMP`, `LEAP_OVER`, `MOONWALK`, `PUSH_UP_ONE_HAND`, `SHOW_OFF`, `BACK_FLIP`, `FRONT_FLIP`, `ROLL`, `WASH_FACE`, `ZERO`, `CALIBRATION_POSE`, `SERVO_TEST`, `LAND`, `DROP_RECOVER`, `KNOCK`, `LUCKY_CAT`, `LOOK_UP`, `LICK_PAWS`, `HEAD_TOSS`, `PICK_DOWN`, `PICK_FRONT`, `PUT_DOWN`, `PUT_FRONT`, `TOSS_FRONT`, `LAUNCH`.

Not every robot has every skill. `petoi.constants.ONLY_ON` lists the exceptions: for example the flips and `ROLL` are on Bittle only (not Bittle with the robot arm), and `WASH_FACE` is on Nybble only. `petoi.constants.RISKY` lists flips, falls and test postures the firmware keeps out of random mode; clear some floor space first. `PICK_DOWN` ... `LAUNCH` are made for the robot arm. For a fixed side, use `robot.skill("pickL")` / `"pickR"` (also `put`, `toss`); a bare `"pick"` alternates sides. Robots have more skills than this list; reach them with `robot.skill("name")`.

Every method waits for the robot to confirm. Gaits (`walk()`, `trot()`, `crawl()`, `back()`) return once the gait has started and keep going until `stop()`; one-shot skills and postures return when they have finished. Pass `wait=False` to any movement method (or to `send()`) to send the command and return at once without waiting. A command sent within 50 ms of an unconfirmed one waits out the rest of that gap, so the robot reads the two separately; while the robot is busy (a melody, a frame transition), commands sent in a burst can still run together, so use `wait=True` when the order matters.

## Custom skills

`run_skill_data(data)` sends a skill array in the layout of the firmware's `src/Instinct*.h` files (Skill Composer skills use it too), runs it, and returns when it is done:

```python
up = [0, 0, 0, 0, 0, 0, 0, 0, 30, 30, 30, 30, 30, 30, 30, 30]   # Bittle's "up"
look = [30] + up[1:]                                               # head turned
robot.run_skill_data([1, 0, 0, 1] + look)                          # a posture
robot.run_skill_data([-2, 0, 0, 1, 0, 0, 0] + look + [8, 10, 0, 0] + up + [8, 0, 0, 0])  # a behavior
```

- Header: frame count (1 posture, more than 1 gait, negative behavior), expected roll, expected pitch, angle ratio (1, or 2 to double every angle). A behavior adds three loop values: start row, end row, and how many times those rows run.
- Frames: 16 angles for a posture; 8 for a gait on Bittle and Nybble (12 on other models); for a behavior, 16 angles plus speed (8 = 1 degree per step, 0 = jump), pause (×50 ms), and two gyro trigger values (0, 0 for none).
- Postures return once reached and gaits once started (they keep going until `stop()`). Behaviors return when finished; over Wi-Fi, a behavior returns as it starts.
- Rejected before sending: a length that doesn't match the header, values outside -128..127, the value 126 (it is the end marker `~`; use 125 or 127), a negative loop count (it would loop forever), and more than 124 behavior frames.
- The robot also saves each upload to flash, so avoid uploading in a tight loop.

## Errors

There are two ways a missing reply is reported, depending on which kind of call you make:

- **High-level methods** (`sit()`, `walk()`, `joint()` ...) raise `petoi.RobotTimeout` if the robot does not confirm in time. Catch it, or let it stop your script.
- **Raw `send()` / `send_binary()`** never raise on a timeout. They return a `Reply`; check `reply.completed` (`False` means no confirmation) and read `reply.text` or `reply.lines` for anything the robot printed.

```python
import petoi

robot = petoi.connect("mock")

try:
    robot.sit()
except petoi.RobotTimeout:
    print("robot did not answer: check power and the connection")

reply = robot.send("d")
if not reply.completed:
    print("no confirmation")
```

`timeout=0` means "do not wait": `robot.send("kwkF", timeout=0)` returns at once with `completed=False`. That is expected, not a failure. Over Wi-Fi the firmware handles one command at a time, so Wi-Fi always waits for completion and `timeout=0` / `wait=False` do not skip the wait.

All errors inherit from `petoi.PetoiError`; `RobotTimeout` is a `RobotError`; failing to open a link raises `petoi.ConnectionFailed`. `setup_wifi()` raises `petoi.WifiSetupFailed` (a `RobotError`) when the robot cannot join the network.

## Raw commands

`send()` takes the same text commands you would type in the Arduino serial monitor, for example `"ksit"`, `"i 8 30"`, or `"d"`:

```python
reply = robot.send("kbalance")
print(reply.completed, reply.text)
```

Rules:

- One command per call. A newline inside the command raises `ValueError` (it would be two commands). A single trailing newline is fine.
- Commands starting with an uppercase letter are binary commands and `send()` rejects them. Use `send_binary(token, *integers)`: `robot.send_binary("I", 8, -20)`.

The command tokens are listed in the firmware source, `src/OpenCat.h` lines 293-375.

## CLI

```bash
petoi ports                      # list serial ports
petoi send ksit                  # send a command to the USB robot
petoi send ksit --to ble         # ...or to a BLE robot ("bluetooth", an IP address, a port name, "mock")
petoi send "?" --to mock
```

Exit codes: 0 means the robot confirmed the command, 1 means a failure or no reply from the robot, 2 means a bad command (for example an uppercase binary command).

## Troubleshooting

- **"could not open" / port busy**: another program (Petoi Desktop App, Arduino serial monitor) has the port. Close it.
- **No USB port found, or several**: run `petoi ports` and pass the port name to `connect()`.
- **BLE robot not found**: the robot may be connected to the phone app. Disconnect it there first.
- **Wi-Fi**: the robot accepts at most 2 clients at once. Not on Wi-Fi yet? See "Putting the robot on Wi-Fi".
- **Firmware warning**: update the firmware with the Petoi Desktop App (see "Old firmware" above).
- **Robot keeps moving after your script ended**: send `robot.stop()` or `robot.rest()`. The `with` block does this for you if an error ends the script.

## Known limitations

- The library cannot tell which reply belongs to which command, because the robot's protocol has no command IDs. Most commands are fine. But a one-shot skill (such as `Skill.PUSH_UP`) only replies when it finishes. If that reply arrives more than 15 seconds late, it could be mistaken for the reply to a newer command with the same first letter. By an estimate from the firmware's skill tables, the longest built-in skill (Nybble `hunt`) takes about 10 s. This has not been checked on hardware.
- Some details were derived from the firmware source and have not been confirmed on a real robot yet: BLE long-command reassembly, the Wi-Fi idle heartbeat, the left/right order of the leg joints, and what each skill does.
- The mock is a simplified robot, useful for trying code, not for judging timing or motion.

## Examples

In `examples/`: `00_no_robot.py` (mock), `01_hello.py` (walk for 3 seconds), `02_dance.py` (head moves, a skill, and a raw command).
