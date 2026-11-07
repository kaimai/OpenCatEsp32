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
  `PETOI_ON_STAND=1 pytest tests/hardware -v -s -k "uploaded or largest"` on USB, BLE and Wi-Fi, robot on a stand.
  On Quaddle USB (2026-11-05, Part H) a 124-frame upload in one write lost bytes 1 in 3 times, and so did 20-byte slices
  1 ms apart (the Desktop App tester's pacing); `SerialTransport` now sends the first 64 bytes of a long `K`/`b`/`B` command (the only ones the firmware waits 200 ms for), waits 50 ms, then the
  rest, which passed 20 of 20. 2026-11-06, Quaddle on a stand, newest S3 main: the 3 upload tests passed on USB and on
  BLE, and the largest (124 frames, 1247 bytes) passed 10 more times on each. Still to check: Bittle X (2487 bytes),
  Bluetooth Classic and Wi-Fi.
  Also find out whether CUB gaits are 8 or 12 wide (both are accepted unless the model is Bittle or Nybble).
- [ ] **Wi-Fi setup (`setup_wifi`)** (plan part A):
  `PETOI_PORT=/dev/cu.usbserial-XXXX PETOI_WIFI_SSID=... PETOI_WIFI_PASSWORD=... .venv/bin/python -m pytest tests/hardware/test_wifi_setup.py -v -s`.
  Checks that the USB link survives `ESP.restart()`, the reboot time (60 s default assumed), and the BOOT-button reset
  (the code implies about 2 s; the README says about 3 s). Record the measured reboot time here.
- [ ] **`back("right")` sends `kbkR`.** By reading `src/skill.h:55-58` it resolves by prefix and is mirrored (`:483`),
  the same path `walk("right")` uses. Not yet seen on a robot.
- [ ] **Bittle with the robot arm.** The hardware test skips `BACK_FLIP`, `FRONT_FLIP` and `ROLL` (which the arm build
  lacks) only if `?` reports a model containing "arm"; otherwise it treats the robot as plain Bittle. Find out what
  `?` reports on an arm build.
- [ ] **Quaddle (S3 firmware)**: first USB run 2026-11-05 on Q_261027 (CH343 USB chip): `test_s3` leg test passed;
  smoke tests 18 passed, 3 failed, all fixed in Part H (melody confirmed early, long upload lost bytes, and a stop test
  that failed only after the bad upload). Skill times: `sit` 0.4 s, `up` 0.1, `balance` 0.4, `str` 0.4, `hi` 3.3,
  `pee` 2.4, `scrh` 1.8, `hsk` 1.7, `hds` 3.2, `kc` 1.0, `nd` 1.3, `wh` 1.3, `dropRec` 0.4. A single `b` with three
  notes plays all three (heard), but echoes after 0.07 s. Done 2026-11-06 (below): USB and BLE
  suites, uploads on a stand, the BLE handshake, and on USB the interactive leg order, `z0` keeping it still for 10 s,
  and three notes heard (all answered yes by the owner). Still open: Wi-Fi, the `?` retry on a sleeping robot,
  Scout's head pan at index 0 (`PETOI_SCOUT=1`), and `setup_wifi()` without a reboot. The USB link dropped
  out several times that day before it stayed up; a cable or hub problem is likely but unconfirmed.
  2026-11-06, newest S3 main (06502f4, reports `Q_261103`), floor runs with the watcher, uploads skipped: USB 27 passed;
  BLE 26 passed (the USB-only gyro line test skips). Skill times on both within 0.1 s of each other and within 0.6 s of
  the 11-05 run. Two earlier USB runs on this firmware stopped on `EXCEPTION: Pushed` (`back("right")`) and
  `EXCEPTION: Knocked` (`buttUp`); the robot stayed upright. Not seen again; cause unknown. A first run after flashing got
  no `?` answer, so the model was unknown and the skill test sent Bittle/Nybble skills, which the robot confirmed in
  0.3 s: `petoi` doesn't report an unknown skill name as an error.
- [ ] **Run hardware tests with the robot on a stand** (`PETOI_ON_STAND=1` for uploads). On 2026-11-05 the robot fell
  several times and couldn't get up while probe scripts drove it free-standing (speed-0 and misaligned uploads).
  `tests/hardware/safety.py` now ends the run on a fall, push, knock or `Trigger released` line (USB, Bluetooth, BLE).
  Floor run with it on Quaddle USB, 2026-11-05: 21 passed, robot stayed up. Its read-ahead (up to 50 ms per write)
  adds about 0.1 s to the printed skill times, so compare timings from runs with and without it carefully.
- [ ] **`WRITE_GAP` (50 ms, Part G)**: passed on Quaddle USB (2026-11-05, run on its own). Still to run on Bluetooth:
  `pytest tests/hardware -k stop_right_after -s`. If the robot keeps walking, the gap is too short. Also try `wait=False` bursts during a melody, which pacing can't fix (the firmware isn't reading then:
  `OpenCatEsp32.ino:86-89`).
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
- [ ] **Firmware (S3): macOS takes over the BLE link as a mouse.** The S3 firmware always attaches its BLE HID mouse
  service to the UART server, even with mouse mode off (OpenCatEsp32S3 `petoiBleUartNimble.h:447`, `mouse.h:71-82`;
  mouse mode is `XO`/`Xo`, `OpenCat.h:760-761`, and is cleared at boot, `configConstants.h:792-796`).
  Seen 2026-11-06 on Quaddle Q_261027, macOS, mouse mode off, robot's USB log recorded during one plain bleak connect
  (UART service only) and disconnect: the robot logged `[BLE] client connected`, our disconnect returned at 7.7 s, the
  robot never logged a disconnect, and at 10.6 s it logged `BLE mouse subscribed`. macOS then listed it as connected
  (Vendor `0xE502`, Product `0xA111`, the HID PnP ID) for as long as we watched (90 s in an earlier run), and it stopped
  advertising, so scans found nothing. Not every connect ends this way: 4 plain connects earlier that day left it free;
  why is not known. After Part J, `ble_compare.py` got 1 of 10 by scan and 0 of 10 by address for this reason.
  Separately, discovering the Device Information service (180A, which the HID code adds) stalls 30 s on macOS; Part J
  avoids it by discovering only the UART service (connect in 0.9 s). Whether the two are related is not known.
  Fix in firmware: attach the HID service only in mouse mode. Until then: disconnect the robot in the macOS Bluetooth
  panel (or restart it) before each connect. Part I (abandoned-connect cleanup in `BleTransport`) is fixed.
  **Fixed in OpenCatEsp32S3 main (06502f4, 2026-11-07; the robot still reports `Q_261103`).** With it flashed, the
  robot logs `[BLE] client disconnected` when we let go and `advertising restarted` 1.9 s later, macOS no longer
  subscribes as a mouse, and `ble_compare.py` through `petoi` got 10 of 10 by scan (8.8 s avg, 5 s of it the scan)
  and 10 of 10 by address (3.7 s avg). `petoi.connect("ble")` on older S3 builds still hits the takeover. The HID
  service is still attached at `petoiBleUartNimble.h:473`, so why this fixes it is not known.
- [ ] **Firmware: larger serial receive buffer.** `Serial.setRxBufferSize()` before `Serial.begin()` in OpenCatEsp32 and
  OpenCatEsp32S3 would stop long commands losing bytes for every client, not only `petoi` (Part H). The buffer size on
  current builds wasn't checked.
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
- [ ] **Wi-Fi busy retry** (Part F review, narrowed in Part G): only `"Previous web task is still running"` triggers the
  retry; other errors for earlier tasks (e.g. `"Task timeout"`) are dropped. Each attempt has its own deadline (up to
  2 × timeout). Still unverified: a deferred task that finishes after the retry starts might complete the retry with the
  old command's results (`src/webServer.h:498-527`). Check on hardware: `walk()` then `stop()`.
- [x] **Codex review fixes** (Part G, 2026-11-03): serial write pacing, the Wi-Fi retry limited to overlap errors,
  `G`/`Z`/`P`/`k` echoes, and Quaddle-aware smoke tests.
- [x] **Quaddle hardware fixes** (Part H, 2026-11-05, `docs/superpowers/plans/2026-11-05-python-api-quaddle-hardware-fixes.md`):
  split long serial writes, wait out S3 melodies, and hardware-test safety (fall watcher, `PETOI_ON_STAND`, no speed 0).
