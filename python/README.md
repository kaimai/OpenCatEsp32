# petoi

Control Petoi OpenCat robots (Bittle X, Nybble Q and other ESP32 BiBoard robots) from Python, over USB, Bluetooth Classic, BLE, or Wi-Fi.

> Status: 0.1.0, not yet tested against every kind of real robot. See "Known limitations" below.

## Install

```bash
pip install petoi            # USB and Bluetooth Classic
pip install "petoi[ble]"     # adds BLE
pip install "petoi[wifi]"    # adds Wi-Fi
pip install "petoi[all]"     # everything
```

Until the first release, install from this repository instead. From the repository root:

```bash
pip install ./python
pip install "./python[all]"   # with BLE and Wi-Fi
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

## Three-line start

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

`connect(target, timeout=5.0, check_firmware=True)`: `timeout` is how many seconds each command may wait for the robot to confirm.

Run `petoi ports` (see CLI below) to see what serial ports your computer has.

### USB takes a while to connect

Opening a USB serial port usually resets the robot's board, so it reboots. `connect()` waits for the robot to print `Ready!`, for up to 20 seconds, so your first command is not lost during boot. If the robot prints nothing for 1.5 seconds right after opening, it is assumed to be running already and the wait ends early. Bluetooth Classic does not reset the board, so it does not wait. If `Ready!` never appears, you get a warning (the robot may be waiting at a calibration prompt) and you can open a serial monitor to check.

### Old firmware

After connecting, the library asks the robot for its model and firmware version. If the firmware is older than `260820`, or does not answer, you get a `RuntimeWarning` suggesting an update with the Petoi Desktop App. Everything may still work. Pass `check_firmware=False` to skip the check (then `robot.model` and `robot.firmware` stay `None`).

## High-level methods

| Method | What it does |
|---|---|
| `sit()`, `stand()` | Posture |
| `walk()`, `trot()`, `crawl()` | Gait, forward by default. `direction="left"` or `"right"`. Keeps going until `stop()` |
| `back()` | Walk backward |
| `stop()` | Stand still |
| `rest()` | Lie down and turn the servos off |
| `skill(Skill.HI)` | Run a built-in one-shot skill (a `Skill` or its short name such as `"hi"`) |
| `joint(Joint.HEAD_PAN, 30)` | Move one joint to an angle in degrees |
| `move_joints({Joint.HEAD_PAN: 30, Joint.HEAD_TILT: 10})` | Move several joints together. `sequential=True` moves them one after another |
| `joints()` | Current angle of every joint, as a list indexed by joint number |
| `beep(note, duration)` | Play a note |
| `info()` | `{"model": ..., "version": ...}` |

`Joint` names: `HEAD_PAN`, `HEAD_TILT`, `TAIL`, `LEFT_FRONT_SHOULDER`, `RIGHT_FRONT_SHOULDER`, `RIGHT_BACK_SHOULDER`, `LEFT_BACK_SHOULDER`, `LEFT_FRONT_KNEE`, `RIGHT_FRONT_KNEE`, `RIGHT_BACK_KNEE`, `LEFT_BACK_KNEE`. You can also pass plain joint numbers.

`Skill` names: `SIT`, `STAND`, `BALANCE`, `STRETCH`, `HI`, `PUSH_UP`, `CHECK`, `PEE`, `SNIFF`, `SCRATCH`, `SLEEP`, `HIGH_FIVE`, `HANDSHAKE`. Robots have more skills than this list; reach them with `robot.skill("name")`.

Every method waits for the robot to confirm it finished. Pass `wait=False` to `skill()`, or use `send(..., wait=False)`, to not wait.

## Errors

There are two ways a missing reply is reported, depending on which kind of call you make:

- **High-level methods** (`sit()`, `walk()`, `joint()` ...) raise `petoi.RobotTimeout` if the robot does not confirm in time. Catch it, or let it stop your script.
- **Raw `send()` / `send_binary()`** never raise on a timeout. They return a `Reply`; check `reply.completed` (`False` means no confirmation) and read `reply.text` or `reply.lines` for anything the robot printed.

```python
import petoi

try:
    robot.sit()
except petoi.RobotTimeout:
    print("robot did not answer: check power and the connection")

reply = robot.send("d")
if not reply.completed:
    print("no confirmation")
```

`timeout=0` means "do not wait": `robot.send("kwkF", timeout=0)` returns at once with `completed=False`. That is expected, not a failure. Over Wi-Fi the firmware handles one command at a time, so Wi-Fi always waits for completion and `timeout=0` / `wait=False` do not skip the wait.

All errors inherit from `petoi.PetoiError`; `RobotTimeout` is a `RobotError`; failing to open a link raises `petoi.ConnectionFailed`.

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

## Troubleshooting

- **"could not open" / port busy**: another program (Petoi Desktop App, Arduino serial monitor) has the port. Close it.
- **No USB port found, or several**: run `petoi ports` and pass the port name to `connect()`.
- **BLE robot not found**: the robot may be connected to the phone app. Disconnect it there first.
- **Wi-Fi**: the robot accepts at most 2 clients at once.
- **Firmware warning**: update the firmware with the Petoi Desktop App (see "Old firmware" above).
- **Robot keeps moving after your script ended**: send `robot.stop()` or `robot.rest()`. The `with` block does this for you if an error ends the script.

## Known limitations

- The library cannot tell which reply belongs to which command, because the robot's protocol has no command IDs. Most commands are fine. But a one-shot skill (such as `Skill.PUSH_UP`) only replies when it finishes. If that reply arrives more than 15 seconds late, it could be mistaken for the reply to a newer command with the same first letter. We assume no built-in skill takes that long; this has not been checked on hardware.
- Some details were derived from the firmware source and have not been confirmed on a real robot yet: BLE long-command reassembly, the Wi-Fi idle heartbeat, the left/right order of the leg joints, and what each skill does.
- The mock is a simplified robot, useful for trying code, not for judging timing or motion.

## Examples

In `examples/`: `00_no_robot.py` (mock), `01_hello.py` (walk for 3 seconds), `02_dance.py` (head moves, a skill, and a raw command).
