# petoi Python API: open issues

Things still unresolved on `feature/python-api`. Each item says what is known, what is not, and where the evidence is.

## Needs a real robot (merge gate)

- [ ] **Run the hardware suite** on USB, Bluetooth, BLE and Wi-Fi:
  `PETOI_PORT=/dev/cu.usbserial-XXXX .venv/bin/python -m pytest tests/hardware -v -s`
  (add `PETOI_BT`, `PETOI_BLE`, `PETOI_WS` for the other links; `PETOI_RISKY=1` with the robot on the floor).
  It covers the 8 plan assumptions (BLE chunking, boot timing, Wi-Fi heartbeat, leg order, skill names,
  head-move timing, 15 s echo window, retries) plus `gyro`, `melody`, `back("left"/"right")` and every `Skill` the model has.
- [ ] **Long skills vs the 5 s default timeout.** `skill()` waits for the skill to finish, but `robot.timeout`
  defaults to 5 s. Petoi's own `PythonSocketTester.py` (DesktopAppRelease `pyUI/`) gives `clap`, `pee`, `hunt`
  and long `b64:` payloads 30 s, and `b64:Q…` payloads or `B` melodies of over 10 values 120 s, which suggests some skills run longer than 5 s. Time every
  `Skill` on hardware. If any exceed 5 s, either raise the wait for skills only or estimate each skill's length
  from its frame count. Note the Wi-Fi server gives up on a task after 45 s (`src/webServer.h:53`).
- [ ] **`Skill.SLEEP` name.** It maps to `zz`. The workshop's `level-3.py` calls `kzz` "all joint at 0 degrees",
  and the firmware has a separate `zero` posture. I could not tell from the code what `zz` does. Watch it on a
  robot and rename the member if needed.
- [ ] **`back("right")` sends `kbkR`.** By reading `src/skill.h:55-58` it resolves by prefix and is mirrored (`:483`),
  the same path `walk("right")` uses. Not yet seen on a robot.
- [ ] **Bittle with the robot arm.** The hardware test treats any non-Nybble model as plain Bittle, so it cannot
  skip `BACK_FLIP`, `FRONT_FLIP` and `ROLL`, which the arm build lacks (they are in `RISKY`, so they only run with
  `PETOI_RISKY=1`). Find out what `?` reports on an arm build.

## Needs the owner

- [ ] **PyPI name.** `petoi` and `petoi-robot` were both unregistered on 2026-10-27. Uploading needs the owner's
  PyPI account. Decide between publishing 0.1.0 before hardware testing, or a 0.0.1 placeholder to hold the name.
- [ ] **Branch:** merge locally, open a PR, keep, or discard. Hardware testing first is the safer order.
- [ ] **Backup ref.** `refs/original/refs/heads/feature/python-api` is left from the commit-trailer rewrite.
  Delete it once the history is confirmed: `git update-ref -d refs/original/refs/heads/feature/python-api`.

## Feature candidates (each needs a plan amendment first)

- [ ] **Wi-Fi setup from Python.** Today a user needs another tool to put the robot on Wi-Fi before
  `connect("192.168.x.x")` works. The firmware takes `w%SSID%password` over serial, prints
  `Successfully connected Wifi to IP Address: <ip>`, then reboots after 3 s (`src/reaction.h:436-475`).
  If it is already on Wi-Fi it prints `Wifi already connected to IP Address: <ip>` (`:485`). A helper such as
  `petoi.setup_wifi(ssid, password) -> ip` (over USB) would close the gap. Limits to handle: an SSID cannot
  contain `%` (the first `%` after the SSID ends it), the reboot drops the serial link, and the Wi-Fi join's own
  timeout has not been looked up.
- [ ] **Upload a custom skill** (`K` + int8 frames + `~`, or `b64:` over Wi-Fi), as the Desktop App tester's
  `send_K_skill_data` does. Pairs with Skill Composer exports.
- [ ] **More `Skill` members.** Names whose meaning I could not source are left out: `zero`, `ts`, `calib`, `lnd`,
  `launch`, `pick*`, `put*`, `toss*`, `flip*`, `knock`, `lucky`, `dropRec`, `lu`, `lkPaws`, `headToss`. They
  still work through `skill("name")`.
- [ ] **Gyro extras:** read the state (`g?`) and calibrate (`gc`, which turns the servos off and runs on the robot
  for a while). Left out of `gyro(on)` on purpose.

## Engineering follow-ups

- [ ] Set a minimum hatchling version and fill in the project metadata (URLs, classifiers, keywords).
- [ ] Add a mypy step to CI.
- [ ] Add a CI matrix entry pinned to the oldest supported websockets (13) to catch API drift.
- [ ] `tests/test_constants.py` reads `../src/Instinct*.h`, so it only runs from a repo checkout, not from an
  sdist. Fine for CI; skip it cleanly if the headers are missing.
- [ ] Review error messages once more against real failures seen during hardware testing.
