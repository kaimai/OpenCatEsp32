# Part G: Codex Review Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the four findings from the Codex review of `feature/python-api` (2026-11-03): back-to-back serial commands merging, Wi-Fi resending a command after an unrelated task error, `g`/`p`/`z` replies that change the token, and hardware smoke tests that assume 16 joints.

**Architecture:** All fixes are inside `python/`. Stream transports hold back a write by up to `WRITE_GAP` while the previous command is unconfirmed. Wi-Fi retries only on the firmware's overlap message. `protocol.echoes()` lists the tokens each command may echo. The hardware smoke tests pick joints by model.

**Tech Stack:** Python 3.9+, pytest, mypy. Worktree: `/Users/kaikai/projects/petoi codes/OpenCatEsp32-Quadruped-Robot - python-api`, branch `feature/python-api`. Run commands from `python/`. Use `.venv/bin/python -m pytest`.

**GBrain:** the MCP server failed to connect this session, so the required GBrain query was skipped.

---

## Firmware facts (static reading of this repo's `src/`, not checked on a robot)

1. **Merging.**
   - `read_serial()` (`src/moduleManager.h:396-428`) reads one byte, then calls `delay(1)`.
   - It then reads every waiting byte before checking for the terminator.
   - The cleanup at `:431-440` deletes every `\n` in lowercase commands.
   - So `kwkF\n` and `kbalance\n` waiting together become one skill name, `wkFkbalance`, and the stop is lost.
   - Binary commands merge the same way.
2. **When the firmware reads.**
   - The idle loop reads every pass, but only when the task queue is empty (`OpenCatEsp32.ino:86-89`).
   - Behaviors check serial between frames (`src/skill.h:285-320`).
   - The firmware reads nothing during a frame transition, a melody, or a queued task.
   - **Consequence:** a short gap stops two writes sent in quick succession from merging while the firmware is reading. It can't help while the firmware is busy; only `wait=True` does.
3. **Wi-Fi errors.**
   - An overlap rejection carries the running task's id and the text `"Previous web task is still running"` (`src/webServer.h:347`, `:498-527`).
   - `"Task timeout"` (`:720-726`) also carries an earlier task's id, after 45 s.
   - The current code treats both the same.
4. **Echoes that differ from the sent token.** The echo is `printToAllPorts(token)` after `token` was rewritten (`src/reaction.h:1557`):

   | Sent | Echo | Source (`src/reaction.h`) |
   |---|---|---|
   | `z` | `Z` or `z` | `:498` |
   | bare `g` | `G` or `g` | `:506` |
   | `gF` / `gf` | `G` / `g` | `:573` |
   | `p` | `P` when pausing; `k` when resuming (token becomes `T_SKILL`) | `:627-629` |

   `gB`/`gb` keep `g`.

## Decisions in this plan (owner can veto)

- **Pacing, not echo-waiting, for finding 1.**
  - Codex suggested holding each write until the robot has consumed the previous command.
  - The echo is the only sign of that, and one-shot skills echo only when they finish. Echo-waiting would make `wait=False` on a behavior the same as `wait=True`, and `stop()` could not interrupt it.
  - So this plan waits only for the gap, and only after an unconfirmed write.
- **`WRITE_GAP = 0.05` s is a guess.** Firmware fact 2 says one idle pass plus `delay(1)` is enough. The real loop time during a gait is unmeasured, so a hardware test checks it (Task 4).
- **Accepting `k` as the echo of `p`.** A late `k` from an earlier skill could confirm a `p`. The existing stale-echo tracking catches the common case.

## File Structure

| File | Change |
|---|---|
| `python/src/petoi/transports/base.py` | `WRITE_GAP`, `write_command()`; `command()` paces and clears the owed mark; `expect()` uses `echoes()` |
| `python/src/petoi/robot.py` | S3 `I`/`M` and `setup_wifi()` write through `write_command()` |
| `python/src/petoi/protocol.py` | `echoes()`; `collect_reply()` uses it |
| `python/src/petoi/transports/websocket.py` | `_OVERLAP`; only that error raises `_Busy` |
| `python/tests/test_stream.py`, `test_protocol.py`, `test_robot.py`, `test_websocket.py` | new unit tests |
| `python/tests/hardware/test_smoke.py` | model-aware joints, Quaddle skips, a stop-after-walk test |
| `python/README.md`, `python/TODO.md` | one README sentence; TODO updates |

---

### Task 0: Commit this plan

- [ ] **Step 1: Commit**

```bash
cd "/Users/kaikai/projects/petoi codes/OpenCatEsp32-Quadruped-Robot - python-api"
git add docs/superpowers/plans/2026-11-03-python-api-codex-fixes.md
git commit -m "Plan Part G: fixes for the Codex review findings

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 1: Pace writes after an unconfirmed command (finding 1, P1)

**Files:**
- Modify: `python/src/petoi/transports/base.py:10`, `:49-58`
- Modify: `python/src/petoi/robot.py:73-78` (S3 `I`/`M`), `:262-265` (`setup_wifi`)
- Test: `python/tests/test_stream.py`, `python/tests/test_robot.py`

- [ ] **Step 1: Write the failing tests** (append to `python/tests/test_stream.py`)

```python
def _record_sleeps(monkeypatch):
    import petoi.transports.base as base

    slept = []
    monkeypatch.setattr(base.time, "sleep", slept.append)
    return slept


def test_command_right_after_an_unconfirmed_one_waits_out_the_gap(monkeypatch):
    # read_serial() takes every waiting byte, so two commands in its buffer become one (src/moduleManager.h:404-440)
    from petoi.transports.base import StreamTransport

    slept = _record_sleeps(monkeypatch)
    s = FakeStream(auto_echo=False)
    s.command("k", b"kwkF\n", timeout=0)
    s.command("k", b"kbalance\n", timeout=0)
    assert len(slept) == 1 and 0 < slept[0] <= StreamTransport.WRITE_GAP
    assert s.written == [b"kwkF\n", b"kbalance\n"]


def test_confirmed_command_does_not_slow_the_next_one(monkeypatch):
    slept = _record_sleeps(monkeypatch)
    s = FakeStream()
    assert s.command("k", b"ksit\n", timeout=1.0).completed
    assert s.command("k", b"kup\n", timeout=1.0).completed
    assert slept == []


def test_write_command_paces_the_next_command(monkeypatch):
    slept = _record_sleeps(monkeypatch)
    s = FakeStream()
    s.write_command(b"I\x08\xec~")  # never confirmed, e.g. S3 I over USB
    s.command("k", b"ksit\n", timeout=1.0)
    assert len(slept) == 1
```

Append to `python/tests/test_robot.py`. The robot is built the same way as the existing S3 `loop://` test at `:655-664`:

```python
def test_s3_binary_joint_paces_the_following_command(monkeypatch):
    import serial
    import petoi.transports.base as base
    from petoi.transports.serial import SerialTransport

    slept = []
    monkeypatch.setattr(base.time, "sleep", slept.append)
    r = Robot(SerialTransport(serial.serial_for_url("loop://", timeout=0.05), boot_timeout=0), timeout=2)
    r.firmware = "Q_261022"
    r.send_binary("I", 2, 20)  # never confirmed over USB on S3 (reaction.h:2655-2657)
    r.send_binary("I", 3, 20)
    assert len(slept) == 1
    r.close()
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `.venv/bin/python -m pytest tests/test_stream.py tests/test_robot.py -k "gap or slow or paces" -v`
Expected: FAIL. The first and fourth tests fail with `slept == []`. The third fails with `AttributeError: 'FakeStream' object has no attribute 'write_command'`.

- [ ] **Step 3: Implement in `base.py`**

Add this class attribute and method to `StreamTransport`, below `_unconfirmed`:

```python
    # Time to let the firmware read an unconfirmed command on its own before the next write:
    # read_serial() takes every waiting byte, so two commands in its buffer become one
    # (src/moduleManager.h:404-440). 50 ms covers an idle loop pass; unverified on hardware.
    WRITE_GAP = 0.05
    _owed_write_at = 0.0  # when the last unconfirmed command was written; 0 once confirmed

    def write_command(self, payload: bytes) -> None:
        """Write one command, first waiting out WRITE_GAP if the previous one is unconfirmed."""
        if self._owed_write_at:
            wait = self._owed_write_at + self.WRITE_GAP - time.monotonic()
            if wait > 0:
                time.sleep(wait)
        self.write(payload)
        self._owed_write_at = time.monotonic()
```

Replace the end of `command()`:

```python
        self.write_command(payload)
        reply = self.expect(token, timeout)
        if reply.completed:
            self._owed_write_at = 0.0  # its echo proves the firmware read it
        return reply
```

- [ ] **Step 4: Implement in `robot.py`**

S3 `I`/`M` branch of `send_binary`: change `self.transport.write(payload)` to `self.transport.write_command(payload)`.

`setup_wifi`: change `transport.write(payload)` to `transport.write_command(payload)`.

`run_skill_data` already goes through `command()`, so it needs no change.

- [ ] **Step 5: Run the tests and confirm they pass**

Run: `.venv/bin/python -m pytest -q && .venv/bin/mypy src`
Expected: all pass (256 + 4 new), and mypy reports no issues.

- [ ] **Step 6: Commit**

```bash
git add python/src/petoi/transports/base.py python/src/petoi/robot.py python/tests/test_stream.py python/tests/test_robot.py
git commit -m "Wait briefly before writing after an unconfirmed command so the firmware doesn't merge them

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Wi-Fi retries only on the overlap rejection (finding 2, P2)

**Files:**
- Modify: `python/src/petoi/transports/websocket.py:32-35` (constant), `:138-143`
- Test: `python/tests/test_websocket.py` (the fake `firmware()` and one new test)

- [ ] **Step 1: Write the failing test**

In `firmware()`, add `timed_out = None` next to `running = None`. Insert this block before the `if running and msg["commands"] == ["bad"]:` branch:

```python
        if msg["commands"] == ["late"]:
            timed_out = task
            ws.send(json.dumps({"type": "response", "taskId": task, "status": "running"}))
            continue
        if timed_out:
            # WEB_TASK_EXECUTION_TIMEOUT fired for it before this command (src/webServer.h:720-726)
            ws.send(json.dumps({"taskId": timed_out, "status": "error", "error": "Task timeout"}))
            timed_out = None
```

Add this test:

```python
def test_old_task_timeout_does_not_resend_the_next_command(port):
    t = WebSocketTransport("127.0.0.1", port=port, heartbeat=False)
    assert t.command("l", b"late\n", timeout=0.2).completed is False
    assert t.command("k", b"khi\n", timeout=2.0).completed
    assert [m["commands"] for m in received] == [["late"], ["khi"]]  # not sent twice
    t.close()
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `.venv/bin/python -m pytest tests/test_websocket.py -v`
Expected: the new test FAILS, with `received` equal to `[["late"], ["khi"], ["khi"]]`. `test_busy_robot_aborts_the_old_task_and_runs_the_retry` still passes.

- [ ] **Step 3: Implement**

Below `class _Busy`:

```python
_OVERLAP = "Previous web task is still running"  # the only error that means ours was refused (src/webServer.h:347)
```

Replace the `if status == "error" and tid in previous:` block:

```python
            if status == "error" and tid in previous:
                self._outstanding.remove(tid)
                if msg.get("error") != _OVERLAP:
                    continue  # an earlier task failed on its own, e.g. "Task timeout" (src/webServer.h:720-726)
                # The firmware reports a rejected overlap with the RUNNING task's id
                # and aborts that task; ours was never stored (src/webServer.h:346-347, :487-512).
                self._outstanding.remove(task_id)
                raise _Busy()
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `.venv/bin/python -m pytest -q && .venv/bin/mypy src`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add python/src/petoi/transports/websocket.py python/tests/test_websocket.py
git commit -m "Wi-Fi: retry only when the robot refused an overlapping task

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Accept the echoes the firmware rewrites (finding 3, P2)

**Files:**
- Modify: `python/src/petoi/protocol.py:77-88`
- Modify: `python/src/petoi/transports/base.py` (`expect()`: the stale match and `consumed_own`)
- Test: `python/tests/test_protocol.py`, `python/tests/test_stream.py`, `python/tests/test_robot.py`

- [ ] **Step 1: Write the failing tests**

Append to `python/tests/test_protocol.py`. `pytest` and `collect_reply` are already imported there:

```python
@pytest.mark.parametrize("token,echo", [("g", "G"), ("g", "g"), ("z", "Z"), ("p", "P"), ("p", "k")])
def test_rewritten_echo_completes(token, echo):
    # src/reaction.h:498, :506, :573, :627-629 rewrite the token before echoing it (:1557)
    lines = iter(["=", echo])
    assert collect_reply(token, lambda: next(lines, None)).completed


def test_other_tokens_still_need_their_exact_echo():
    lines = iter(["K"])
    assert collect_reply("k", lambda: next(lines, None)).completed is False
```

Append to `python/tests/test_stream.py`:

```python
def test_late_rewritten_echo_is_recognized_as_stale():
    s = FakeStream(auto_echo=False)
    s.command("g", b"g\n", timeout=0)  # toggles balance; echoes G or g later
    s.replies[b"ksit\n"] = ["G", "k"]
    reply = s.command("k", b"ksit\n", timeout=0.05)
    assert reply.completed and reply.lines == []
```

Append to `python/tests/test_robot.py`, building the robot the way the other `FakeStream`-backed robot tests in that file do:

```python
def test_send_g_completes_when_balance_turns_on():
    r = Robot(FakeStream({b"g\n": ["G"]}))
    assert r.send("g").completed
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `.venv/bin/python -m pytest tests/test_protocol.py tests/test_stream.py tests/test_robot.py -k "rewritten or exact_echo or balance_turns" -v`
Expected: the `G`/`Z`/`P`/`k` cases fail with `completed is False`. The stale test fails because `lines == ["G"]`. The `g`/`g` case and `test_other_tokens_still_need_their_exact_echo` already pass.

- [ ] **Step 3: Implement**

In `protocol.py`, above `collect_reply`:

```python
# Tokens the firmware rewrites before echoing (src/reaction.h:498, :506, :573, :627-629, echoed at :1557)
_ECHOES = {"g": ("g", "G"), "z": ("z", "Z"), "p": ("P", "k")}


def echoes(token: str) -> Tuple[str, ...]:
    """Every line that confirms a command sent with this token."""
    return _ECHOES.get(token, (token,))
```

Add `Tuple` to the `typing` import. In `collect_reply`, change `if line == token:` to `if line in echoes(token):`.

In `base.py` `expect()`, import `echoes` from `petoi.protocol`, then:

```python
                    hit = next((i for i, (t, _) in enumerate(pending) if line.strip() in echoes(t)), None)
                    if hit is not None:
                        # a late echo; earlier entries ahead of it were lost
                        consumed_own = consumed_own or line.strip() in echoes(token)
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `.venv/bin/python -m pytest -q && .venv/bin/mypy src`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add python/src/petoi/protocol.py python/src/petoi/transports/base.py python/tests/test_protocol.py python/tests/test_stream.py python/tests/test_robot.py
git commit -m "Accept G, Z, P and k as the echoes of g, z and p

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Hardware smoke tests that fit Quaddle, plus a stop-after-walk check (finding 4, P2; round-trip check for Task 1)

**Files:**
- Modify: `python/tests/hardware/test_smoke.py:26-27`, `:59-64`, `:88-123`

These run only on a robot. In CI they are skipped, so the check is that collection still works.

- [ ] **Step 1: Edit `test_smoke.py`**

Add `from petoi import QuaddleJoint` to the imports, then add these helpers after the `robot` fixture:

```python
def _quaddle(robot):
    return model_key(robot.model) == "quaddle"


def _layout(robot):
    """(joint count, a joint safe to turn by 20-30 degrees while standing).

    Quaddle has 6 joints and a head only on Scout (OpenCatEsp32S3 OpenCat.h:155-165);
    its front-left leg is used instead. Not yet tried on a Quaddle."""
    if _quaddle(robot):
        return 6, int(QuaddleJoint.LEFT_FRONT_LEG)
    return 16, int(petoi.Joint.HEAD_PAN)
```

`test_scenario`: add `if _quaddle(robot): pytest.skip("scenario moves head joints; tests/hardware/test_s3.py covers Quaddle")` as its first line.

`test_long_command_arrives_intact`: add `if _quaddle(robot): pytest.skip("Quaddle's 4 leg joints make a short command; the upload tests cover long writes")` as its first line.

Replace `_standing` and the three upload tests' uses of `petoi.Joint.HEAD_PAN`:

```python
def _standing(robot):
    count, _ = _layout(robot)
    robot.stand()
    angles = robot.joints()
    assert len(angles) == count and all(-125 <= a <= 125 for a in angles), angles
    return angles


def test_uploaded_posture_turns_the_head(robot):
    _, joint = _layout(robot)
    angles = _standing(robot)
    angles[joint] = 20
    robot.run_skill_data([1, 0, 0, 1] + angles)
    scenario.wait_for_angle(robot, joint, 20)
    robot.stand()


def test_uploaded_behavior_returns_after_it_finishes(robot):
    _, joint = _layout(robot)
    angles = _standing(robot)
    look = list(angles)
    look[joint] = 30
    frames = [angles + [8, 10, 0, 0], look + [8, 10, 0, 0], angles + [8, 0, 0, 0]]  # two 500 ms pauses
    start = time.monotonic()
    robot.run_skill_data([-3, 0, 0, 1, 0, 0, 0] + [v for f in frames for v in f])
    if isinstance(robot.transport, StreamTransport):  # Wi-Fi returns as it starts (src/reaction.h:1565)
        assert time.monotonic() - start >= 1.0
    assert robot.info()["model"] == robot.model  # no leftover K echo
    robot.stand()


def test_largest_upload_arrives_intact(robot):
    _, joint = _layout(robot)
    angles = _standing(robot)
    last = list(angles)
    last[joint] = 20
    frames = [angles + [0, 0, 0, 0]] * 123 + [last + [0, 0, 0, 0]]  # 124 frames; 2487 bytes on 16 joints, 1247 on Quaddle
    robot.run_skill_data([-124, 0, 0, 1, 0, 0, 0] + [v for f in frames for v in f])
    scenario.wait_for_angle(robot, joint, 20)  # lost bytes would misalign the last frame
    robot.skill(Skill.BALANCE)  # "kbalance" must still fit (src/skill.h:131-137)
```

Add the round-trip check for Task 1. The firmware is the consumer, and it only runs on a robot:

```python
def test_stop_right_after_unwaited_walk_is_not_lost(robot):
    # Without WRITE_GAP the firmware can read "kwkF\nkbalance\n" as one command (src/moduleManager.h:404-440).
    # stop()'s echo alone can't prove it worked: whether a merged, unknown skill name still echoes "k" is unverified.
    robot.walk(wait=False)
    robot.stop()
    time.sleep(0.5)
    first = robot.joints()
    time.sleep(0.5)
    second = robot.joints()
    assert all(abs(a - b) <= 3 for a, b in zip(first, second)), (first, second)  # still walking: the stop was lost
```

- [ ] **Step 2: Check collection and the suite**

Run: `.venv/bin/python -m pytest -q && .venv/bin/python -m pytest tests/hardware --collect-only -q | tail -3`
Expected: all unit tests pass, and the hardware tests collect, then skip with "no robot configured".

- [ ] **Step 3: Commit**

```bash
git add python/tests/hardware/test_smoke.py
git commit -m "Hardware smoke tests: pick joints by model so they run on Quaddle; check stop() right after walk(wait=False)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: README and TODO

**Files:**
- Modify: `python/README.md:149`
- Modify: `python/TODO.md`

- [ ] **Step 1: README**

Append this sentence to the paragraph at line 149 (the one ending "...without waiting."):

```markdown
A command sent within 50 ms of an unconfirmed one waits out the rest of that gap, so the robot reads the two separately; while the robot is busy (a melody, a frame transition), commands sent in a burst can still run together, so use `wait=True` when the order matters.
```

- [ ] **Step 2: TODO**

Under "Needs a real robot (merge gate)", add:

```markdown
- [ ] **`WRITE_GAP` (50 ms, Part G)**: run `pytest tests/hardware -k stop_right_after -s` on USB and Bluetooth. If the robot keeps walking, the gap is too short. Also try `wait=False` bursts during a melody, which pacing can't fix (the firmware isn't reading then: `OpenCatEsp32.ino:86-89`).
```

In the "Quaddle (S3 firmware)" item, after "run `tests/hardware/test_s3.py` and `test_smoke.py`", add: "(the upload tests turn the front-left leg on Quaddle, which hasn't been tried)".

Replace the "Wi-Fi busy retry, unverified edge case" item with:

```markdown
- [ ] **Wi-Fi busy retry** (Part F review, narrowed in Part G): only `"Previous web task is still running"` triggers the retry; other errors for earlier tasks (e.g. `"Task timeout"`) are dropped. Still unverified: a deferred task that finishes after the retry starts might complete the retry with the old command's results (`src/webServer.h:498-527`). Check on hardware: `walk()` then `stop()`.
```

Under "Engineering follow-ups", add:

```markdown
- [x] **Codex review fixes** (Part G, 2026-11-03): serial write pacing, the Wi-Fi retry limited to overlap errors, `G`/`Z`/`P`/`k` echoes, and Quaddle-aware smoke tests.
```

- [ ] **Step 3: Commit**

```bash
git add python/README.md python/TODO.md
git commit -m "README and TODO for the Part G fixes

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Final check

- [ ] Run `.venv/bin/python -m pytest -q && .venv/bin/mypy src`. Expect about 266 passed and 74 skipped, with mypy clean.
- [ ] Run `git status`: clean. Run `git log --oneline -7`: the plan plus 5 commits.
- [ ] Do not push.
