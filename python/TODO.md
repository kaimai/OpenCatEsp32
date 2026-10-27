# petoi Python API: open issues

Things still unresolved on `feature/python-api`. Each item says what is known, what is not, and where the evidence is.

Proposed plans for most items (awaiting approval): `docs/superpowers/plans/2026-10-27-python-api-followups.md`, parts A–E.

## Needs a real robot (merge gate)

- [ ] **Run the hardware suite** on USB, Bluetooth, BLE and Wi-Fi:
  `PETOI_PORT=/dev/cu.usbserial-XXXX .venv/bin/python -m pytest tests/hardware -v -s`
  (add `PETOI_BT`, `PETOI_BLE`, `PETOI_WS` for the other links; `PETOI_RISKY=1` with the robot on the floor).
  It covers the 8 plan assumptions (BLE chunking, boot timing, Wi-Fi heartbeat, leg order, skill names,
  head-move timing, 15 s echo window, retries) plus `gyro`, `melody`, `back("left"/"right")` and every `Skill` the model has.
- [ ] Time every `Skill` on hardware (`pytest tests/hardware -k every_skill -s`); each line prints the measured time next to the firmware-based estimate (`petoi._timing`, longest: Nybble `hunt` about 10.4 s). Petoi's Desktop App tester allows 30 s for `clap`, `pee` and `hunt`, so compare against that too.
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

## Decisions to revisit

- [ ] **`skill_timeout` default (30 s).** Chosen for now (plan part C). Revisit after timing every skill on hardware.
- [ ] **Value 126 in uploaded skills.** `run_skill_data()` rejects it (plan part B); clamping to 125/127 was the alternative. Owner undecided.
- [ ] **Uploaded behaviors over Wi-Fi return when they start**, because the firmware finishes the web task at the first `K` echo (`src/reaction.h:1565`). Owner undecided whether to accept this or ask for a firmware change.

## Feature candidates (each needs a plan amendment first)

- [ ] **Wi-Fi setup from Python** (plan part A). Today a user needs another tool to put the robot on Wi-Fi before
  `connect("192.168.x.x")` works. The firmware takes `w%SSID%password` over serial, prints
  `Successfully connected Wifi to IP Address: <ip>`, then reboots after 3 s (`src/reaction.h:436-475`).
  If it is already on Wi-Fi it prints `Wifi already connected to IP Address: <ip>` (`:485`). A helper such as
  `petoi.setup_wifi(ssid, password) -> ip` (over USB) would close the gap. Limits to handle: an SSID cannot
  contain `%` (the first `%` after the SSID ends it), the reboot drops the serial link, and the Wi-Fi join's own
  timeout has not been looked up.
- [ ] **Upload a custom skill** (plan part B) (`K` + int8 frames + `~`, or `b64:` over Wi-Fi), as the Desktop App tester's
  `send_K_skill_data` does. Pairs with Skill Composer exports.
- [ ] **`flip`/`flipD`/`flipF` left out** (plan part D): they overlap `bf`/`ff` and are not in `randomMind.h:51`, so `RISKY` could not mark them.
  They still work through `skill("name")`.
- [ ] **Time `calibrate_gyro()`** on MPU6050 and ICM42670 boards; the firmware gives up after 10 s (`src/reaction.h:549`),
  and then `calibrate_gyro()` would report failure even though calibration may finish later.

## Engineering follow-ups

Items 1–4 below: plan part E.

- [ ] **Bug: Wi-Fi `wait=False` waits 5 s.** `WebSocketTransport.command` uses `timeout or self._default_timeout`, so 0 means the default (`src/petoi/transports/websocket.py:106`). A long skill sent with `wait=False` returns incomplete after 5 s and the next command gets "busy". Needs a fix and a test.
- [x] Set a minimum hatchling version and fill in the project metadata (URLs, classifiers, keywords).
- [ ] Add a mypy step to CI.
- [x] Add a CI matrix entry pinned to the oldest supported websockets (13) to catch API drift.
- [x] `tests/test_constants.py` reads `../src/Instinct*.h`, so it only runs from a repo checkout, not from an
  sdist. Fine for CI; skip it cleanly if the headers are missing.
- [ ] Review error messages once more against real failures seen during hardware testing.
