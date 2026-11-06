# Part H: Quaddle hardware findings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the two `petoi` problems the first Quaddle USB run found (melody, long uploads) and make the hardware tests stop before they drive a fallen robot.

**Architecture:** `melody()` plays one note per command on S3 firmware and waits out each note on the computer. `SerialTransport.write()` sends the first bytes of a long command on their own, pauses, then sends the rest. A hardware-test `conftest.py` watches the robot's output for fall and misalignment messages and ends the run when one appears; upload tests run only when the robot is on a stand.

**Tech Stack:** Python 3.9+, pyserial, pytest. Worktree `/Users/kaikai/projects/petoi codes/OpenCatEsp32-Quadruped-Robot - python-api`, branch `feature/python-api`. Run everything from its `python/` folder with `.venv/bin/python`.

**GBrain:** the MCP server failed to connect this session, so the pre-plan GBrain query was skipped.

---

## What the hardware run found (2026-11-05, Quaddle Q_261027, USB via CH343)

Verified on the robot:

- `test_s3.py::test_leg_moves_and_reads_back` passed. `test_smoke.py`: 18 passed, 3 failed.
- **Melody:** `b12 4 14 4 16 2` was echoed 0.07 s after it was sent, so `melody()` returned long before the 1 s tune.
- **Long upload:** a 124-frame `K` upload (1249 bytes, all trigger columns 0) was misaligned 2 of 5 times when written in one go. The robot printed `Trigger released` with trigger angles 54, 71 and 0, which are joint-angle values. Each misplaced trigger waits up to 2 s (OpenCatEsp32S3 `src/skill.h:470-497`), and the robot ignored `kup` until the behavior ran out. Written as 64 bytes, a 50 ms pause, then the rest, it worked 5 of 5 times. Five tries each does not prove the cause.
- `test_stop_right_after_unwaited_walk_is_not_lost` passed on its own. It failed in the full run only because it came right after the misaligned upload.
- **The robot fell over several times during my probe scripts** (speed-0 and misaligned uploads, run back to back on a free-standing robot) and could not get up. Its gyro output showed gravity on the y axis and it printed `EXCEPTION: Pushed`; I didn't act on either. The robot is undamaged.

Read in the firmware but **not verified on the robot**:

- Firmware source: the OpenCatEsp32S3 clone in the scratchpad is dated 2026-11-02 and is newer than Q_261027. It is read-only and must never be copied into this repo.
- The S3 ASCII `b` handler plays only `target[0]`/`target[1]`, one note (`src/reaction.h:1876`).
- S3 `beep()` calls `tone(BUZZER, freq, duration, volume)` and does not `delay()` for a note (`src/sound.h:102-115`). A rest (`note` 0) is a `delay()`, so its echo comes after the rest.
- **Cause of the lost bytes (assumption):** bytes are lost when a long command reaches the board while the firmware is not yet in `read_serial()`. Once `read_serial()` starts it reads until 200 ms of silence (`src/moduleManager.h:961-1010`, `SERIAL_TIMEOUT_LONG` in `src/OpenCat.h:12`). The receive buffer size on this build is unknown (the ESP32 core default is commonly 256 bytes; not checked).
- Fall messages printed over USB: `EXCEPTION: Fall over`, `EXCEPTION free fall`, `EXCEPTION: Knocked`, `EXCEPTION: Pushed` in both firmwares (OpenCatEsp32 `src/reaction.h:47-89`, OpenCatEsp32S3 `src/reaction.h:180-267`); S3 also prints `EXCEPTION: Roll left/right` (`:236-237`); `Trigger released` in both (`src/skill.h:348` and S3 `:496`).

## Decisions in this plan (approve or change)

1. **S3 `melody(wait=False)` raises `ValueError`.** The computer has to time each note, so it can't return early. (Alternative: play in a background thread; more code and a lock held across calls.)
2. **The split write applies to every serial link (USB and Bluetooth Classic) and every firmware**, for commands longer than 64 bytes. It costs 50 ms per long command. Bittle X was not tested, but the old TODO already suspected unpaced long writes there.
3. **Upload tests need `PETOI_ON_STAND=1`.** A misaligned upload can drive the joints to any angle.
4. **The fall watcher stops the whole run on `EXCEPTION: Pushed` and `Knocked` too**, not only falls. If it stops runs for normal skills, relax it later.
5. **Firmware follow-up (out of scope, owner's call):** a larger receive buffer (`Serial.setRxBufferSize()` before `Serial.begin()`) in both firmwares would fix lost bytes for every client. Not done here.

## File structure

- Modify `python/src/petoi/transports/serial.py`: split long writes.
- Modify `python/src/petoi/robot.py`: S3 branch in `melody()`; `beep()` docstring.
- Create `python/tests/hardware/safety.py` (fall watcher, `on_stand` mark) and `python/tests/hardware/conftest.py` (ends the run on trouble).
- Modify `python/tests/hardware/test_smoke.py`, `python/tests/hardware/test_s3.py`: use the watcher, gate uploads, speed 8, listen for the melody.
- Modify `python/tests/test_serial.py`, `python/tests/test_robot.py`: unit tests.
- Modify `python/README.md`, `python/TODO.md`.

---

### Task 0: Commit this plan

- [ ] **Step 1: Commit**

```bash
cd "/Users/kaikai/projects/petoi codes/OpenCatEsp32-Quadruped-Robot - python-api"
git add docs/superpowers/plans/2026-11-05-python-api-quaddle-hardware-fixes.md
git commit -m "Plan Part H: fix melody and long uploads on Quaddle, make hardware tests stop on a fall

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 1: Measure on the robot first (gate; the owner must be there)

Robot **on a stand with all legs off the ground**, USB connected, the owner listening. The script moves no joint: every frame is the robot's standing pose at speed 8, and it stops at the first `EXCEPTION` or misaligned upload.

**Files:** none committed. Script in the session scratchpad.

- [ ] **Step 1: Listening test.** Write `<scratchpad>/listen.py`:

```python
import sys, time, petoi

with petoi.connect(sys.argv[1]) as r:
    input("Listen. Press Enter to send one b command with three notes")
    r.send("b12 4 14 4 16 2")
    time.sleep(1.5)
    heard_one = input("How many notes did you hear? ").strip()
    input("Press Enter to send the same three notes as three b commands, 250/250/500 ms apart")
    for note, d in ((12, 4), (14, 4), (16, 2)):
        r.send(f"b{note} {d}")
        time.sleep(1 / d)
    heard_three = input("How many notes did you hear? ").strip()
    print(f"one command: {heard_one} notes; three commands: {heard_three} notes")
```

Run: `.venv/bin/python <scratchpad>/listen.py /dev/cu.wchusbserial<id>`
Expected (from the source reading): 1 note, then 3 notes. **If the first is 3 notes, stop and re-plan Task 3** (only the early return would need fixing).

- [ ] **Step 2: Upload test.** Write `<scratchpad>/uploads.py`:

```python
import sys, time, petoi
from petoi.protocol import encode

STOP = ("EXCEPTION", "Trigger released")

def send(t, payload, how):
    if how == "whole":
        t.write(payload)
    elif how == "split":
        t.write(payload[:64]); time.sleep(0.05); t.write(payload[64:])
    else:  # Desktop App tester style: 20-byte slices 1 ms apart
        for i in range(0, len(payload), 20):
            t.write(payload[i:i + 20]); time.sleep(0.001)

def trial(r, payload, how):
    t = r.transport
    r.stand(); time.sleep(0.5); t.discard_input()
    t0 = time.monotonic(); send(t, payload, how)
    ks = 0
    while time.monotonic() - t0 < 6 and ks < 2:
        line = t.readline(0.2)
        if line is None:
            continue
        line = line.strip()
        if line.startswith(STOP):
            return line
        ks += line == "K"
    return "ok" if ks == 2 else "no end K"

with petoi.connect(sys.argv[1]) as r:
    r.stand(); base = r.joints()
    frames = [base + [8, 0, 0, 0]] * 124
    payload = encode("K", *([-124, 0, 0, 1, 0, 0, 0] + [v for f in frames for v in f]))
    tally = {}
    for i in range(20):
        for how in ("whole", "split", "slices"):
            result = trial(r, payload, how)
            tally.setdefault(how, []).append(result)
            print(f"{i:2} {how:6} {result}", flush=True)
            if result != "ok":
                print("stopping: check the robot, then rerun"); r.rest(); sys.exit(1)
    for how, results in tally.items():
        print(how, results.count("ok"), "/ 20 ok")
    r.rest()
```

Run: `.venv/bin/python <scratchpad>/uploads.py /dev/cu.wchusbserial<id>`. The script stops at the first failure, so rerun it with the failing method removed from the tuple (e.g. `("split", "slices")`) until each remaining method has 20 runs. Record every count.

- [ ] **Step 3: Decide.**
  - `split` 20/20 → Task 2 as written.
  - Only `slices` 20/20 → Task 2 with 20-byte slices and 1 ms sleeps instead (change the test in Task 2 Step 1 to expect `ceil(len/20)` writes).
  - Neither reaches 20/20 → stop and report; the fix belongs in the firmware (decision 5).
  - If a Bittle X is available, rerun Step 2 on it (`+ [8, 0, 0, 0]` frames have 16 joints there) and record the counts.

### Task 2: Split long serial writes

**Files:**
- Modify: `python/src/petoi/transports/serial.py` (`write`, new constants)
- Test: `python/tests/test_serial.py`

- [ ] **Step 1: Write the failing tests** (append to `tests/test_serial.py`):

```python
class _RecordingPort:
    in_waiting = 0

    def __init__(self):
        self.writes = []

    def write(self, data):
        self.writes.append(bytes(data))

    def flush(self):
        pass

    def read(self, n):
        return b""

    def reset_input_buffer(self):
        pass

    def close(self):
        pass


def test_long_write_sends_its_start_alone_then_pauses(monkeypatch):
    import petoi.transports.serial as serial_transport

    slept = []
    monkeypatch.setattr(serial_transport.time, "sleep", slept.append)
    port = _RecordingPort()
    t = SerialTransport(port, boot_timeout=0)
    payload = bytes(range(1, 101)) + b"~"
    t.write(payload)
    assert port.writes == [payload[:64], payload[64:]]
    assert slept == [serial_transport.CHUNK_PAUSE]


def test_short_write_goes_out_whole(monkeypatch):
    import petoi.transports.serial as serial_transport

    slept = []
    monkeypatch.setattr(serial_transport.time, "sleep", slept.append)
    port = _RecordingPort()
    t = SerialTransport(port, boot_timeout=0)
    t.write(b"kup\n")
    assert port.writes == [b"kup\n"] and slept == []
```

(`SerialTransport` is already imported at the top of `tests/test_serial.py`.)

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/python -m pytest tests/test_serial.py -k "long_write or short_write" -v`
Expected: `test_long_write...` FAILS (one write of 101 bytes; `CHUNK_PAUSE` missing). `test_short_write...` passes.

- [ ] **Step 3: Implement.** In `src/petoi/transports/serial.py`, below `READ_SLICE`:

```python
# A long command that reaches the board while the firmware isn't reading can lose bytes and
# misalign skill frames (Quaddle Q_261027 over USB, 2026-11-05: 2 of 5 uploads). Sending its
# start alone lets read_serial() begin; it then reads until 200 ms of silence
# (OpenCatEsp32S3 moduleManager.h:961-1010). The cause is unverified; the split fixed 5 of 5.
FIRST_CHUNK = 64
CHUNK_PAUSE = 0.05
```

and replace `write`:

```python
    def write(self, data: bytes) -> None:
        try:
            self._port.write(data[:FIRST_CHUNK])
            self._port.flush()
            if len(data) > FIRST_CHUNK:
                time.sleep(CHUNK_PAUSE)
                self._port.write(data[FIRST_CHUNK:])
                self._port.flush()
        except serial.SerialException as e:
            raise ConnectionFailed(f"lost connection to {self._name()}: {e}") from e
```

- [ ] **Step 4: Run the serial tests and the whole suite**

Run: `.venv/bin/python -m pytest tests/test_serial.py -v && .venv/bin/python -m pytest -q`
Expected: all pass (271 + 2 passed, 74 skipped).

- [ ] **Step 5: Commit**

```bash
git add python/src/petoi/transports/serial.py python/tests/test_serial.py
git commit -m "Send the start of a long serial command alone, so Quaddle doesn't lose upload bytes

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 3: Play S3 melodies one note at a time

**Files:**
- Modify: `python/src/petoi/robot.py` (`beep`, `melody`)
- Test: `python/tests/test_robot.py`

- [ ] **Step 1: Write the failing tests** (append to `tests/test_robot.py`):

```python
def _s3_robot():
    r = Robot(FakeStream(), timeout=0.2)
    r.firmware = "Q_261027"
    return r


def test_s3_melody_sends_one_note_per_command_and_waits_out_each(monkeypatch):
    import petoi.robot as robot_module

    slept = []
    monkeypatch.setattr(robot_module.time, "sleep", slept.append)
    r = _s3_robot()
    assert r.melody([(12, 4), (0, 8), (16, 2)]).completed
    assert r.transport.written == [b"b12 4\n", b"b0 8\n", b"b16 2\n"]
    assert slept == [0.25, 0.5]  # a rest already waited before its echo (OpenCatEsp32S3 sound.h:102-115)


def test_s3_melody_cannot_return_early():
    with pytest.raises(ValueError, match="S3"):
        _s3_robot().melody([(12, 8)], wait=False)
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/python -m pytest tests/test_robot.py -k s3_melody -v`
Expected: both FAIL (one `b12 4 0 8 16 2` write; no ValueError).

- [ ] **Step 3: Implement.** In `robot.py`, change `beep`'s docstring and the end of `melody`:

```python
    def beep(self, note: int, duration: int) -> Reply:
        """Play one note: semitones above C6 (0 is a rest), lasting 1/duration s (8 = 125 ms).

        On S3 firmware (Quaddle) it returns as the note starts."""
        return self._cmd("b", note, duration)

    def melody(self, notes: Sequence[Tuple[int, int]], wait: bool = True) -> Reply:
        """Play (note, duration) pairs as in beep(); waits until the tune ends.

        On S3 firmware the notes are sent one at a time, so wait must be True."""
        # (existing validation loop unchanged)
        ...
        if self.s3:
            # S3 plays only the first note of a b list and echoes as it starts
            # (OpenCatEsp32S3 reaction.h:1876, sound.h:102-115), so time each note here.
            if not wait:
                raise ValueError("on S3 firmware melody() times each note itself, so it can't return before the tune ends")
            for note, duration in notes:
                reply = self._cmd("b", note, duration)
                if note:  # a rest is a delay before the echo
                    time.sleep(1 / duration)
            return reply
        length = sum(1 / d for _, d in notes)  # 1000/d ms per note (src/reaction.h:1004)
        return self._cmd("b", *flat, wait=wait, timeout=self.timeout + length)
```

Keep the existing validation (`if not notes`, pair length, `duration < 1`) and the `flat` list exactly as they are; only the `if self.s3:` block and the docstrings are new.

- [ ] **Step 4: Run the robot tests, the whole suite, and mypy**

Run: `.venv/bin/python -m pytest tests/test_robot.py -v -k melody && .venv/bin/python -m pytest -q && .venv/bin/python -m mypy src`
Expected: all pass; mypy clean (if mypy reports `reply` possibly undefined, the `notes` check above guarantees one iteration; add `reply = Reply("b")` before the loop).

- [ ] **Step 5: Commit**

```bash
git add python/src/petoi/robot.py python/tests/test_robot.py
git commit -m "Play melodies one note at a time on S3 firmware, which plays only the first note of a list

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 4: Hardware tests stop on a fall and keep uploads on a stand

**Files:**
- Create: `python/tests/hardware/safety.py`, `python/tests/hardware/conftest.py`
- Modify: `python/tests/hardware/test_smoke.py`, `python/tests/hardware/test_s3.py`

The helpers live in `safety.py`, not `conftest.py`: `tests/conftest.py` already exists and the unit tests do `from conftest import FakeStream`, so a second importable `conftest` could resolve to the wrong file.

- [ ] **Step 1: Create `tests/hardware/safety.py`:**

```python
"""Stop driving the robot once it reports trouble, and keep uploads to a robot on a stand."""
import os

import pytest

# Printed over USB (src/reaction.h:47-89, src/skill.h:348; OpenCatEsp32S3 reaction.h:180-267, skill.h:496).
# Our test frames never set a trigger, so "Trigger released" means an upload arrived misaligned.
STOP_LINES = (
    "EXCEPTION: Fall over",
    "EXCEPTION free fall",
    "EXCEPTION: Roll",
    "EXCEPTION: Knocked",
    "EXCEPTION: Pushed",
    "Trigger released",
)
trouble = []  # lines seen; the autouse fixture in conftest.py ends the run when this isn't empty


def watch(robot):
    """Record any STOP_LINES the robot prints. USB, Bluetooth and BLE; Wi-Fi replies don't pass through readline."""
    readline = getattr(robot.transport, "readline", None)
    if readline is None:
        return

    def watched(timeout):
        line = readline(timeout)
        if line is not None and line.strip().startswith(STOP_LINES):
            trouble.append(line.strip())
        return line

    robot.transport.readline = watched


on_stand = pytest.mark.skipif(
    not os.environ.get("PETOI_ON_STAND"),
    reason="an upload that arrives misaligned can drive the joints anywhere; put the robot on a stand and set PETOI_ON_STAND=1",
)
```

Then create `tests/hardware/conftest.py`:

```python
import pytest

import safety


@pytest.fixture(autouse=True)
def stop_on_trouble():
    yield
    if safety.trouble:
        pytest.exit(f"robot printed {safety.trouble[0]!r}; check it is upright and on a stand before running again", returncode=1)
```

- [ ] **Step 2: Use it in `test_smoke.py`.** Add `from safety import on_stand, watch` to the imports. In the `robot` fixture, call `watch(r)` right after the `print(...)` line. Put `@on_stand` above `test_uploaded_posture_turns_the_head`, `test_uploaded_behavior_returns_after_it_finishes` and `test_largest_upload_arrives_intact`. In `test_largest_upload_arrives_intact`, change the frames to speed 8:

```python
    frames = [angles + [8, 0, 0, 0]] * 123 + [last + [8, 0, 0, 0]]  # speed 8; never 0 on hardware. 124 frames: 2487 bytes on 16 joints, 1247 on Quaddle
```

- [ ] **Step 3: Use it in `test_s3.py`.** Add `from safety import watch`. In the `robot` fixture, call `watch(r)` after the `print(...)` line. Append:

```python
def test_melody_plays_every_note(robot):
    input("Listen; press Enter to play three notes")
    robot.melody([(12, 4), (14, 4), (16, 2)])
    assert input("Did you hear three notes? [y/n] ").strip().lower() == "y"
```

- [ ] **Step 4: Check the hardware tests still collect and skip without a robot**

Run: `.venv/bin/python -m pytest tests/hardware -q`
Expected: all skipped ("no robot configured"), no import errors. Then `.venv/bin/python -m pytest -q`: all pass.

- [ ] **Step 5: Commit**

```bash
git add python/tests/hardware/safety.py python/tests/hardware/conftest.py python/tests/hardware/test_smoke.py python/tests/hardware/test_s3.py
git commit -m "Hardware tests: stop on a fall or misaligned upload, run uploads only on a stand, never use speed 0

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 5: README and TODO

**Files:** `python/README.md`, `python/TODO.md`

- [ ] **Step 1: README.** Change the `melody` row (line 136) to:

```markdown
| `melody([(12, 8), (14, 8), (16, 4)])` | Play several `(note, duration)` pairs; returns when the tune ends. On Quaddle the notes are sent one at a time, so `wait=False` isn't allowed |
```

- [ ] **Step 2: TODO.** Under "Needs a real robot", rewrite the Quaddle item to record what ran on 2026-11-05 (USB only: `test_s3` leg test passed; smoke 18 passed; skill times `sit` 0.4 s, `up` 0.1, `balance` 0.4, `str` 0.4, `hi` 3.3, `pee` 2.4, `scrh` 1.8, `hsk` 1.7, `hds` 3.2, `kc` 1.0, `nd` 1.3, `wh` 1.3, `dropRec` 0.4), what is still open (BLE, Wi-Fi, leg order, Scout head, `setup_wifi`), and the Task 1 counts. Mark the `WRITE_GAP` item as passing on Quaddle USB, still open on Bluetooth. Add an item: "Run hardware tests with the robot on a stand (`PETOI_ON_STAND=1`); the robot fell several times on 2026-11-05 when probe scripts drove it free-standing." Add under "Needs the owner": "Firmware: a larger serial receive buffer (`Serial.setRxBufferSize()` before `Serial.begin()`) in OpenCatEsp32 and OpenCatEsp32S3 would stop long commands losing bytes for every client (Part H)." Add an `[x]` item for Part H linking this plan.

- [ ] **Step 3: Commit**

```bash
git add python/README.md python/TODO.md
git commit -m "README and TODO for Part H and the first Quaddle USB run

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 6: Verify

- [ ] **Step 1:** `.venv/bin/python -m pytest -q && .venv/bin/python -m mypy src`. Expected: all pass, mypy clean.
- [ ] **Step 2 (owner there, robot on a stand):**
  `PETOI_PORT=/dev/cu.wchusbserial<id> PETOI_ON_STAND=1 .venv/bin/python -m pytest tests/hardware/test_s3.py tests/hardware/test_smoke.py -v -s`
  Expected: no failures; the run ends early by itself if the robot prints a fall line.
- [ ] **Step 3:** `/codex review` on the Part H commits; fix P1/P2 findings.
- [ ] **Step 4:** Do not push. Ask the owner.
