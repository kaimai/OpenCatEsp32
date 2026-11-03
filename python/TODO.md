# petoi Python API: open issues

Things still unresolved on `feature/python-api`. Each item says what is known, what is not, and where the evidence is.

Plans for most items: `docs/superpowers/plans/2026-10-27-python-api-followups.md`, parts A–E (approved and implemented 2026-10-27; hardware checks still open below).

## Needs a real robot (merge gate)

- [ ] **Run the hardware suite** on USB, Bluetooth, BLE and Wi-Fi:
  `PETOI_PORT=/dev/cu.usbserial-XXXX .venv/bin/python -m pytest tests/hardware -v -s`
  (add `PETOI_BT`, `PETOI_BLE`, `PETOI_WS` for the other links; `PETOI_RISKY=1` with the robot on the floor).
  It covers the 8 plan assumptions (BLE chunking, boot timing, Wi-Fi heartbeat, leg order, skill names,
  head-move timing, 15 s echo window, retries) plus `gyro`, `melody`, `back("left"/"right")` and every `Skill` the model has.
- [ ] Time every `Skill` on hardware (`pytest tests/hardware -k every_skill -s`); each line prints the measured time next to the firmware-based estimate (`petoi._timing`, longest: Nybble `hunt` about 10.4 s). Petoi's Desktop App tester allows 30 s for `clap`, `pee` and `hunt`, so compare against that too.
- [ ] **Uploaded skills (`run_skill_data`)** (plan part B):
  `pytest tests/hardware -v -s -k "uploaded or largest"` on USB, BLE and Wi-Fi. `test_largest_upload_arrives_intact`
  sends 2487 bytes in one unpaced write; if it fails on USB, add paced writes (the Desktop App tester sends 20-byte
  slices 1 ms apart). Also find out whether CUB gaits are 8 or 12 wide (both are accepted unless the model is Bittle or Nybble).
- [ ] **Wi-Fi setup (`setup_wifi`)** (plan part A):
  `PETOI_PORT=/dev/cu.usbserial-XXXX PETOI_WIFI_SSID=... PETOI_WIFI_PASSWORD=... .venv/bin/python -m pytest tests/hardware/test_wifi_setup.py -v -s`.
  Checks that the USB link survives `ESP.restart()`, the reboot time (60 s default assumed), and the BOOT-button reset
  (the code implies about 2 s; the README says about 3 s). Record the measured reboot time here.
- [ ] **`back("right")` sends `kbkR`.** By reading `src/skill.h:55-58` it resolves by prefix and is mirrored (`:483`),
  the same path `walk("right")` uses. Not yet seen on a robot.
- [ ] **Bittle with the robot arm.** The hardware test skips `BACK_FLIP`, `FRONT_FLIP` and `ROLL` (which the arm build
  lacks) only if `?` reports a model containing "arm"; otherwise it treats the robot as plain Bittle. Find out what
  `?` reports on an arm build.
- [ ] **Quaddle (S3 firmware)**: run `tests/hardware/test_s3.py` and `test_smoke.py` over USB, BLE and Wi-Fi
  (`-s`, since `test_s3.py` asks you what you saw). Check: the `?` retry on a sleeping robot, the BLE handshake, `z0`
  keeping it still, leg order, that Scout's extra joint is the head pan at index 0 (`PETOI_SCOUT=1`; assumed from
  PetoiWebCoding and the firmware's HEADPAN define), skill timings (the estimator is unverified for 6 joints), and
  `setup_wifi()` without a reboot.
- [ ] **BLE connect on Bittle X after Part F**: connect now always asks `?` and waits for the forced rest. opencat-gemma
  made the same change, but it wasn't checked on a Bittle X there either.

## Needs the owner

- [ ] **Publish to PyPI as `petoi`.** Name decided 2026-11-01 (`pyproject.toml`). Uploading needs the owner's PyPI account
  (consider a Petoi organization account). Decide between publishing 0.1.0 before hardware testing, or a 0.0.1
  placeholder to hold the name. Optionally also hold `opencat-robot`. Availability checked on 2026-10-27:

  | Name | Status |
  |---|---|
  | `petoi` (decided) | free |
  | `petoi-robot` (name inside Petoi's MindPlus `PetoiRobot` library) | free |
  | `opencat-robot` | free |
  | `petoi-opencat` | free |
  | `opencatesp32` | free |
  | `opencat` / `OpenCat` | taken: unrelated desktop-cat app, v0.2.1 (github.com/Jacobzwj/opencat) |
  | `open-cat` | free on lookup, but likely refused as too close to `opencat` (unverified) |
- [ ] **Branch:** merge locally, open a PR, keep, or discard. Hardware testing first is the safer order.
- [ ] **Backup ref.** `refs/original/refs/heads/feature/python-api` is left from the commit-trailer rewrite.
  Delete it once the history is confirmed: `git update-ref -d refs/original/refs/heads/feature/python-api`.

## Decisions to revisit

- [ ] **`skill_timeout` default (30 s).** Chosen for now (plan part C). Revisit after timing every skill on hardware.
- [ ] **Value 126 in uploaded skills.** `run_skill_data()` rejects it (plan part B); clamping to 125/127 was the alternative. Owner undecided.
- [ ] **Uploaded behaviors over Wi-Fi return when they start**, because the firmware finishes the web task at the first `K` echo (`src/reaction.h:1565`). Owner undecided whether to accept this or ask for a firmware change.
- [ ] **Chero** (S3, board C): later, per owner. Needs its own skill table (no crawl, side gaits or bk) and joint map.
- [ ] **Bittle/Nybble on S3 firmware**: not detected or supported; S3 Bittle lacks knock and lucky.
- [ ] **Quaddle extended behaviors** (over 127 frames, -128 header): refused for now.

## Feature candidates (each needs a plan amendment first)

- [x] **Wi-Fi setup from Python**: done as `Robot.setup_wifi(ssid, password)` (plan part A).
- [ ] **`petoi wifi` CLI** that asks for the password with `getpass` (follow-up to part A).
- [ ] **`wifi_ip()`**: report the robot's current Wi-Fi address with a bare `w` (follow-up to part A).
- [ ] **`flip`/`flipD`/`flipF` left out** (plan part D): they overlap `bf`/`ff` and are not in `randomMind.h:51`, so `RISKY` could not mark them.
  They still work through `skill("name")`.
- [ ] **Time `calibrate_gyro()`** on MPU6050 and ICM42670 boards; the firmware gives up after 10 s (`src/reaction.h:549`),
  and then `calibrate_gyro()` would report failure even though calibration may finish later.

## Engineering follow-ups

Items 1–4 below: plan part E.

- [ ] **Late echo after 15 s with `wait=False`.** Owed echoes expire after `STALE_SECONDS` (15 s, `src/petoi/transports/base.py`). A skill or uploaded behavior that runs longer, sent with `wait=False`, can leave its late `k`/`K` in front of the next command, which then confirms early or carries an extra line. No built-in skill is estimated over 15 s, but uploaded ones can be.
- [ ] **Bug: Wi-Fi `wait=False` waits 5 s.** `WebSocketTransport.command` uses `timeout or self._default_timeout`, so 0 means the default (`src/petoi/transports/websocket.py:106`). A long skill sent with `wait=False` returns incomplete after 5 s and the next command gets "busy". Needs a fix and a test.
- [x] Set a minimum hatchling version and fill in the project metadata (URLs, classifiers, keywords).
- [x] Add a mypy step to CI.
- [x] Add a CI matrix entry pinned to the oldest supported websockets (13) to catch API drift.
- [x] `tests/test_constants.py` reads `../src/Instinct*.h`, so it only runs from a repo checkout, not from an
  sdist. Fine for CI; skip it cleanly if the headers are missing.
- [ ] Review error messages once more against real failures seen during hardware testing.
- [ ] **BLE connect ignores `check_firmware=False` and `timeout`** (Part F review). `BleTransport._settle()` always sends
  `?`, waits up to 2 s for a greeting plus up to 8 s for the rest to end, and fails after a fixed 5 s with no answer.
  Before Part F, a BiBoard that didn't answer `?` still connected with a warning. Ported as-is from opencat-gemma.
- [ ] **`?` retry doubles the wait before the old-firmware warning** (Part F review): a robot that never answers takes
  2 × `timeout` (10 s by default). The retry is there for a sleeping Quaddle, which can't be told apart beforehand.
- [ ] **Wi-Fi busy retry, unverified edge case** (Part F review): each attempt has its own deadline (up to 2 × timeout).
  If the aborted task was a deferred one that finishes after the retry starts, `finishWebCommand()` might complete
  the retry with the old command's results (`src/webServer.h:498-527`). Check on hardware: `walk()` then `stop()`.
