# petoi Part F: OpenCatEsp32S3 (Quaddle) Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the `petoi` package work with OpenCatEsp32S3 firmware on Quaddle, without changing its behavior on OpenCatEsp32 (Bittle X, Nybble Q).

**Architecture:** The wire protocol is the same in both firmwares. What differs is: what each one sends when a link opens, Wi-Fi setup replies, the joint count, the skill tables, and one missing USB echo. The firmware is detected from the `?` version string (`Q_…`/`C_…` = S3). The connection fixes are ported from `opencat-gemma` (`opencat_gemma/links.py`, `ble.py`), which were verified on a Bittle X (`B10_260527`) and a Quaddle (`Q_261022`) on 2026-10-23.

**Tech Stack:** Python 3.9+, pyserial, bleak (optional), websockets (optional), pytest.

**Owner decisions (2026-11-02):** `connect()` sends `z0` to S3 robots so they don't move by themselves. Chero comes later. GBrain was unavailable when this plan was written (MCP server disconnected), so it was not queried.

---

## Sources (read these, don't guess)

| What | Where |
|---|---|
| OpenCatEsp32 firmware | `src/` in this repo |
| OpenCatEsp32S3 firmware (private) | `borntoleave/OpenCatEsp32S3` at `5ed0ad9`. Clone it read-only outside the repo and **never commit any of its files here**. |
| Hardware-verified connection code | `/Users/kaikai/projects/petoi codes/opencat-gemma-integration/opencat_gemma/{links,ble}.py`, `QUADDLE_S3_NOTES.md` |
| Petoi's joint map per product | `PetoiCamp/PetoiWebCoding` `js/product_config.js` |

S3 facts this plan relies on. Each was checked in the S3 source on 2026-11-02:

- **Version:** `BOARD_DATE`, where BOARD is `Q` (Q_Motion/Quaddle) or `C` (Chero) (`OpenCat.h:25-37`, `:1313`).
- **`z0`:** sets random mind to 0, clears the boot-time automatic level, and echoes **`z0`**, not `z` (`reaction.h:1310-1331`, `randomMind.h:66`, `:161-164`). On OpenCatEsp32 a `z` *toggles* random mode (`src/reaction.h:494-498`), so `z0` must never be sent there.
- **Quaddle model block:** `MODEL "Quaddle"`, `DOF 6`, `WALKING_DOF 4`, `BUFF_LEN 4096`, `CMD_LEN 20` (`OpenCat.h:155-165`, `:890`, `:902-907`). Behaviors with first value `-128` use an 8-value extended header (`configConstants.h:90-123`).
- **`I`/`M` echo:** not sent to USB (`reaction.h:2655-2657`).
- **Wi-Fi setup (`w%ssid%pw`):**
  - no reboot;
  - success prints `IP Address: <ip> successfully connected`, then `w`;
  - failure prints `Timeout: Fail to connect web server!`, then `w`;
  - already connected prints `IP Address: <ip>. Wifi already connected`;
  - lines cited at `reaction.h:1225-1300`.
- **Unknown token:** one line, `Undefined token! token: <whole command> <bytes…>`, which **includes the password**. It then echoes the *previous* token (`reaction.h:2621-2632`).
- **BLE:**
  - the first `?` on a link gets `Petoi <MODEL>`, `u`, `<MODEL>`, `<version>`, `?`, sent as separate notifications with **no line breaks** (`petoiBleUartNimble.h:390-414`);
  - BiBoard instead pushes `Petoi <MODEL>` on connect and then rests (`src/bleUart.h:161-176`).
- **No Bluetooth Classic on ESP32-S3** (`OpenCat.h:60-67`).

## File map

| File | Change |
|---|---|
| `python/src/petoi/constants.py` | `QuaddleJoint`, `QUADDLE_SKILLS`, `model_key()`, `skills_for()`, `is_s3_firmware()` |
| `python/src/petoi/connect.py` | retry `?` once; send `z0` to S3; Bluetooth Classic hint |
| `python/src/petoi/transports/ble.py` | absorb the connect greeting and the S3 handshake (`_settle`) |
| `python/src/petoi/transports/websocket.py` | retry once when the robot reports it's busy |
| `python/src/petoi/robot.py` | `s3` property; S3 Wi-Fi replies; per-model skill layout; `I`/`M` over USB on S3 |
| `python/src/petoi/_timing.py` | `dof` parameter |
| `python/tests/…` | tests for each of the above |
| `python/tests/hardware/test_smoke.py`, new `python/tests/hardware/test_s3.py` | model-aware checks for a Quaddle |
| `python/README.md`, `python/TODO.md` | robots and firmware section; new open items |

Run every test command from `python/`, using the venv already there: `.venv/bin/python -m pytest …`.

---

### Task 0: Commit this plan

- [ ] **Step 1: Commit**

```bash
git add docs/superpowers/plans/2026-11-02-python-api-s3-support.md
git commit -m "Plan Part F: OpenCatEsp32S3 (Quaddle) support"
```

---

### Task 1: Model and firmware helpers in constants

**Files:**
- Modify: `python/src/petoi/constants.py` (append after `RISKY`)
- Test: `python/tests/test_constants.py`

- [ ] **Step 1: Write the failing tests** (append to `tests/test_constants.py`; extend its import line to `from petoi.constants import ONLY_ON, QUADDLE_SKILLS, RISKY, Joint, QuaddleJoint, Skill, is_s3_firmware, model_key, skills_for`)

```python
@pytest.mark.parametrize("reported, key", [
    ("Bittle X", "bittle"), ("Bittle X+Arm", "bittle_arm"), ("Nybble Q", "nybble"), ("Quaddle", "quaddle"),
    ("Mock Bittle", "bittle"), ("DoF16", None), (None, None),
])
def test_model_key_maps_the_question_mark_reply(reported, key):
    assert model_key(reported) == key


@pytest.mark.parametrize("version, s3", [("Q_261022", True), ("C_261102", True), ("B10_260527", False), (None, False)])
def test_s3_firmware_is_recognised_by_its_board_letter(version, s3):
    assert is_s3_firmware(version) is s3  # OpenCatEsp32S3 OpenCat.h:25-37, :1313


def test_skills_for_esp32_models_follow_only_on():
    assert skills_for("bittle") == {s for s in Skill if "bittle" in ONLY_ON.get(s, TABLES)}
    assert Skill.WASH_FACE in skills_for("nybble") and Skill.WASH_FACE not in skills_for("bittle")


def test_skills_for_quaddle_is_its_own_table():
    assert skills_for("quaddle") == QUADDLE_SKILLS
    assert Skill.BACK_FLIP in QUADDLE_SKILLS and Skill.HUNT not in QUADDLE_SKILLS
    with pytest.raises(ValueError, match="unknown model"):
        skills_for("chero")


def test_quaddle_joints_are_petoi_web_coding_indices():
    # PetoiWebCoding js/product_config.js: legs 2-5 (LF, RF, RB, LB) on every Quaddle; head pan 0 on Scout only
    assert [int(j) for j in QuaddleJoint] == [0, 2, 3, 4, 5]
    assert QuaddleJoint.HEAD_PAN == 0


S3_SRC = os.environ.get("PETOI_S3_SRC")  # src/ of a private OpenCatEsp32S3 checkout; never vendored here
needs_s3 = pytest.mark.skipif(not S3_SRC, reason="set PETOI_S3_SRC to an OpenCatEsp32S3 src/ folder")


@needs_s3
def test_quaddle_skills_match_its_instinct_table():
    line = next(l for l in (Path(S3_SRC) / "Instinct_Quaddle.h").read_text(errors="replace").splitlines()
                if "skillNameWithType[]" in l)
    names = {n[:-1] for n in re.findall(r'"([^"]+)"', line)}
    assert {s for s in Skill if s.value in names} == QUADDLE_SKILLS
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `.venv/bin/python -m pytest tests/test_constants.py -v`
Expected: ImportError for `QUADDLE_SKILLS`.

- [ ] **Step 3: Implement** (append to `constants.py`; add `from typing import FrozenSet, Optional` at the top)

```python
class QuaddleJoint(IntEnum):
    """Quaddle's joint indices. Every Quaddle has the four legs (2-5); Quaddle Scout
    also has a head pan (0). Both report "Quaddle" to '?', so the API can't tell them
    apart. The firmware reserves 6 slots (DOF 6); index 1 is unused. Indices as
    Petoi's web coding app lists them (PetoiWebCoding js/product_config.js)."""

    HEAD_PAN = 0  # Quaddle Scout only
    LEFT_FRONT_LEG = 2
    RIGHT_FRONT_LEG = 3
    RIGHT_BACK_LEG = 4
    LEFT_BACK_LEG = 5


# The Skill members in Quaddle's table (Instinct_Quaddle.h in the private
# OpenCatEsp32S3 repo, 5ed0ad9). Quaddle has many more of its own; run them with skill("name").
QUADDLE_SKILLS: FrozenSet[Skill] = frozenset({
    Skill.SIT, Skill.STAND, Skill.BALANCE, Skill.STRETCH, Skill.BUTT_UP, Skill.HI, Skill.PEE,
    Skill.SCRATCH, Skill.HANDSHAKE, Skill.HANDSTAND, Skill.KICK, Skill.NOD, Skill.PLAY_DEAD,
    Skill.RECOVER, Skill.WAVE_HEAD, Skill.BACK_FLIP, Skill.FRONT_FLIP, Skill.ZERO,
    Skill.CALIBRATION_POSE, Skill.SERVO_TEST, Skill.DROP_RECOVER,
})

_ESP32_MODELS = ("bittle", "bittle_arm", "nybble")


def model_key(model: Optional[str]) -> Optional[str]:
    """Map the model a robot reports to '?' (e.g. "Bittle X+Arm") to a short key, or None if unknown."""
    low = (model or "").lower()
    if "quaddle" in low:
        return "quaddle"
    if "nybble" in low:
        return "nybble"
    if "bittle" in low:
        return "bittle_arm" if "arm" in low else "bittle"
    return None


def skills_for(model: str) -> FrozenSet[Skill]:
    """The Skill members a model's firmware has, by model_key()."""
    if model == "quaddle":
        return QUADDLE_SKILLS
    if model in _ESP32_MODELS:
        return frozenset(s for s in Skill if model in ONLY_ON.get(s, _ESP32_MODELS))
    raise ValueError(f"unknown model {model!r}")


def is_s3_firmware(version: Optional[str]) -> bool:
    """True for OpenCatEsp32S3 firmware: its version is BOARD_DATE with board Q (Quaddle) or C (Chero)."""
    return (version or "")[:2] in ("Q_", "C_")
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `.venv/bin/python -m pytest tests/test_constants.py -v`
Expected: all pass. `test_quaddle_skills_match_its_instinct_table` is skipped unless `PETOI_S3_SRC` is set. Run it once locally with `PETOI_S3_SRC=<clone>/src` and expect PASS.

- [ ] **Step 5: Export and commit.** Add `QuaddleJoint` to `petoi/__init__.py` next to `Joint`. Then:

```bash
git add python/src/petoi/constants.py python/src/petoi/__init__.py python/tests/test_constants.py
git commit -m "Add Quaddle joints, Quaddle skills, and model/firmware helpers"
```

---

### Task 2: connect(): retry `?` once, calm S3 robots with `z0`, explain Bluetooth on S3

**Files:**
- Modify: `python/src/petoi/connect.py` (`_check_firmware`, `pick_serial_port`)
- Modify: `python/src/petoi/robot.py` (add the `s3` property)
- Test: `python/tests/test_connect.py`

- [ ] **Step 1: Write the failing tests** (append to `tests/test_connect.py`; add imports `import warnings`, `from conftest import FakeStream`, `from petoi.connect import _check_firmware`, `from petoi.robot import Robot`)

```python
QUADDLE = {b"?\n": ["Quaddle", "Q_261022", "?"], b"z0\n": ["z0"]}  # OpenCatEsp32S3 reaction.h:1181-1185, :1324


def test_s3_robot_is_told_to_stop_moving_on_its_own():
    robot = Robot(FakeStream(QUADDLE), timeout=0.2)
    _check_firmware(robot)
    assert robot.s3 and robot.model == "Quaddle"
    assert robot.transport.written == [b"?\n", b"z0\n"]


def test_esp32_robot_never_gets_z0():
    robot = Robot(FakeStream({b"?\n": ["Bittle X", "B10_260527", "?"]}), timeout=0.2)
    _check_firmware(robot)  # 'z' toggles random mode on OpenCatEsp32 (src/reaction.h:494-498)
    assert not robot.s3 and robot.transport.written == [b"?\n"]


def test_unconfirmed_z0_warns():
    robot = Robot(FakeStream({b"?\n": ["Quaddle", "Q_261022", "?"]}, auto_echo=False), timeout=0.1)
    with pytest.warns(RuntimeWarning, match="move on its own"):
        _check_firmware(robot)


class WakesOnFirstCommand(FakeStream):
    """A sleeping Quaddle wakes on the first command and doesn't answer it (opencat-gemma QUADDLE_S3_NOTES.md)."""

    def write(self, data):
        if not self.written:
            self.written.append(data)
            self.pending += ["Charge sleep: serial wake", "auto z1"]
            return
        super().write(data)


def test_question_mark_is_retried_once_for_a_sleeping_robot():
    robot = Robot(WakesOnFirstCommand(QUADDLE), timeout=0.1)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        _check_firmware(robot)
    assert robot.firmware == "Q_261022"


def test_bluetooth_classic_hint_mentions_s3_robots():
    with pytest.raises(ConnectionFailed, match="Quaddle"):
        pick_serial_port([], bluetooth=True)
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `.venv/bin/python -m pytest tests/test_connect.py -v`
Expected: the new tests fail (`s3` attribute missing, no retry, no hint).

- [ ] **Step 3: Implement**

In `robot.py`:
- Import `is_s3_firmware` from `petoi.constants`.
- Add this property after `__init__`:

```python
    @property
    def s3(self) -> bool:
        """True for OpenCatEsp32S3 firmware (e.g. Quaddle). Known after connect()."""
        return is_s3_firmware(self.firmware)
```

In `connect.py`:
- Import `from petoi.constants import is_s3_firmware`, `from petoi.errors import RobotTimeout`, `from petoi.protocol import encode`, and `from petoi.transports.base import StreamTransport`.
- Replace `_check_firmware` with:

```python
def _check_firmware(robot: Robot) -> None:
    info = None
    for _ in range(2):  # a sleeping Quaddle wakes on the first command without answering it (opencat-gemma)
        try:
            info = robot.info()
            break
        except RobotTimeout:
            if isinstance(robot.transport, StreamTransport):
                robot.transport._unconfirmed.clear()  # the swallowed '?' will never echo
        except PetoiError:
            break
    if info is None:
        warnings.warn("robot did not answer '?'; its firmware may be too old for this API", RuntimeWarning, stacklevel=3)
        return
    robot.model, robot.firmware = info["model"], info["version"]
    date = info["version"].rsplit("_", 1)[-1]  # BOARD_YYMMDD, src/OpenCat.h:666
    if len(date) == 6 and date.isdigit() and date < MIN_FIRMWARE_DATE:
        warnings.warn(f"firmware {info['version']} is older than {MIN_FIRMWARE_DATE}; some commands may not work. "
                      "Update it with the Petoi Desktop App.", RuntimeWarning, stacklevel=3)
    if is_s3_firmware(robot.firmware):
        _calm(robot)


def _calm(robot: Robot) -> None:
    # S3 firmware boots in random mind level 2 and moves its joints by itself when idle; z0 turns that
    # off until the next reboot and echoes "z0" (OpenCatEsp32S3 reaction.h:1310-1331, randomMind.h:66, :161).
    if not robot._run("z0", encode("z", 0), True, robot.timeout).completed:
        warnings.warn("the robot did not confirm 'z0'; it may move on its own when idle", RuntimeWarning, stacklevel=4)
```

In `pick_serial_port`, change the Bluetooth `hint` to:

```python
        hint = (" On Windows or Linux the Bluetooth port has no _SSP in its name; pass the Bluetooth COM port "
                "or /dev/rfcomm* port explicitly. ESP32-S3 robots such as Quaddle have no Bluetooth Classic: "
                "use petoi.connect(\"ble\").") if bluetooth else ""
```

- [ ] **Step 4: Run the whole suite and confirm it passes**

Run: `.venv/bin/python -m pytest -q`
Expected: all pass. This includes the existing `test_silent_firmware_warns`, which now makes two `?` attempts of 0.1 s each.

- [ ] **Step 5: Commit**

```bash
git add python/src/petoi/connect.py python/src/petoi/robot.py python/tests/test_connect.py
git commit -m "connect(): retry '?' once, send z0 to S3 robots, point S3 users to BLE"
```

---

### Task 3: BLE: absorb the connect greeting and the S3 handshake

**Files:**
- Modify: `python/src/petoi/transports/ble.py`
- Test: `python/tests/test_ble.py`

- [ ] **Step 1: Write the failing tests** (append to `tests/test_ble.py`; add `import queue` and `from petoi.protocol import LineBuffer`)

```python
def settling(monkeypatch, on_write, pushed=b""):
    monkeypatch.setattr(ble, "PUSH_WAIT", 0.05)
    monkeypatch.setattr(ble, "GREETING_TIMEOUT", 0.2)
    monkeypatch.setattr(ble, "QUERY_TIMEOUT", 0.2)
    t = object.__new__(BleTransport)
    t._raw, t._raw_lock = bytearray(pushed), threading.Lock()
    t._buffer, t._lines = LineBuffer(), queue.Queue()
    t.write = lambda data: on_write(t, data)
    return t


def test_s3_handshake_without_line_breaks_is_absorbed(monkeypatch):
    def reply(t, data):  # OpenCatEsp32S3 petoiBleUartNimble.h:390-414
        for part in (b"Petoi Quaddle", b"u", b"Quaddle", b"Q_261022", b"?"):
            t._on_notify(None, bytearray(part))

    t = settling(monkeypatch, reply)
    t._settle()
    t._on_notify(None, bytearray(b"k\r\n"))
    assert t.readline(0.1) == "k"  # the handshake did not stick to the next line


def test_biboard_greeting_and_forced_rest_are_absorbed(monkeypatch):
    def reply(t, data):
        t._on_notify(None, bytearray(b"Bittle X\r\nB10_260527\r\n?\r\n"))

    t = settling(monkeypatch, reply, pushed=b"Petoi Bittle Xu\r\nrest\r\nd\r\n")  # src/bleUart.h:161-176
    t._settle()
    assert t.readline(0.05) is None


def test_no_answer_to_question_mark_fails_to_connect(monkeypatch):
    t = settling(monkeypatch, lambda t, data: None)
    with pytest.raises(ConnectionFailed, match="did not answer"):
        t._settle()
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `.venv/bin/python -m pytest tests/test_ble.py -v`
Expected: AttributeError `_settle` (or `PUSH_WAIT`).

- [ ] **Step 3: Implement** in `ble.py`:

Add `import time` and these constants after `RUN_TIMEOUT`:

```python
# What a robot sends when the link opens, measured by opencat-gemma (Bittle X and Quaddle, 2026-10-23)
PUSH_WAIT = 2.0  # BiBoard pushes its greeting within this
GREETING_TIMEOUT = 8.0  # then its forced rest ends with "d"
QUERY_TIMEOUT = 5.0  # the reply to our '?'
```

In `__init__`:
- before `try:` add `self._raw: Optional[bytearray] = bytearray()` and `self._raw_lock = threading.Lock()`;
- after `self._chunk = self._negotiated_chunk()` add `self._settle()`.

Replace `_on_notify` and add the helpers:

```python
    def _on_notify(self, _char, data: bytearray) -> None:
        with self._raw_lock:
            if self._raw is not None:  # still connecting: _settle() reads the raw bytes
                self._raw += data
                return
        for line in self._buffer.feed(bytes(data)):
            self._lines.put(line)

    def _raw_text(self) -> str:
        with self._raw_lock:
            return bytes(self._raw or b"").decode("utf-8", "replace")

    def _wait_raw(self, done, timeout: float) -> bool:
        end = time.monotonic() + timeout
        while not done(self._raw_text()):
            if time.monotonic() >= end:
                return False
            time.sleep(0.01)
        return True

    def _settle(self) -> None:
        """Take in what each firmware sends when the link opens, so it isn't read as a command's reply.

        BiBoard pushes "Petoi <MODEL>" and then rests, ending with "d" (src/bleUart.h:161-176). S3 firmware
        pushes nothing, but answers the first '?' with "Petoi <MODEL>u<MODEL><version>?" and no line breaks
        (OpenCatEsp32S3 petoiBleUartNimble.h:390-414). Asking '?' once here covers both (opencat-gemma ble.py)."""
        if self._wait_raw(bool, PUSH_WAIT):
            self._wait_raw(lambda text: "d" in _complete_lines(text), GREETING_TIMEOUT)  # no "d" seen: '?' still works
        with self._raw_lock:
            self._raw = bytearray()
        self.write(b"?\n")
        answered = self._wait_raw(
            lambda text: "?" in _complete_lines(text) or ("Petoi" in text and text.strip().endswith("?")), QUERY_TIMEOUT)
        if not answered:
            raise ConnectionFailed(f"the BLE robot did not answer '?' within {QUERY_TIMEOUT:g}s")
        with self._raw_lock:
            self._raw = None
        self.discard_input()
```

And add a module-level helper at the end of `ble.py`:

```python
def _complete_lines(text: str) -> list:
    return [line.strip() for line in text.split("\n")[:-1]]
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `.venv/bin/python -m pytest tests/test_ble.py -v`, then `.venv/bin/python -m mypy src`.
Expected: all pass; mypy reports no issues.

- [ ] **Step 5: Commit**

```bash
git add python/src/petoi/transports/ble.py python/tests/test_ble.py
git commit -m "BLE: absorb the BiBoard greeting and the S3 '?' handshake on connect"
```

---

### Task 4: setup_wifi() on S3 firmware

**Files:**
- Modify: `python/src/petoi/robot.py` (`setup_wifi`, module constants)
- Test: `python/tests/test_robot.py` (next to the existing `setup_wifi` tests; reuse `PW`, `SENT`, `wifi_robot`, `assert_secret_kept`)

- [ ] **Step 1: Write the failing tests**

```python
S3_JOINED = "IP Address: 192.168.1.130 successfully connected"  # OpenCatEsp32S3 reaction.h:1259-1260


def test_setup_wifi_on_s3_returns_the_ip_without_a_reboot():
    r = wifi_robot(["RSSI: -48 dBm", S3_JOINED, "WebSocket server is ready on port 81", "w"])
    assert r.setup_wifi("Home", PW) == "192.168.1.130"


def test_setup_wifi_on_s3_wrong_password_raises_without_the_password():
    r = wifi_robot(["Timeout: Fail to connect web server!", "Saved WiFi slots:", "w"])
    with pytest.raises(WifiSetupFailed, match="'Home'") as e:
        r.setup_wifi("Home", PW)
    assert_secret_kept(e.value)


def test_setup_wifi_on_s3_when_already_on_wifi_warns_and_returns_the_ip():
    r = robot({SENT: ["IP Address: 10.0.0.7. Wifi already connected", "RSSI: -50 dBm", "w"]})
    with pytest.warns(RuntimeWarning, match="already on Wi-Fi"):
        assert r.setup_wifi("Home", PW) == "10.0.0.7"


def test_setup_wifi_on_s3_firmware_without_wifi_fails_fast_and_hides_the_command():
    # S3 prints the whole command (password included) on one line, then echoes the PREVIOUS token (reaction.h:2621-2632)
    r = robot({SENT: [f"Undefined token! token: w%Home%{PW} 37 72", "k"]})
    start = time.monotonic()
    with pytest.raises(RobotError, match="no Wi-Fi support") as e:
        r.setup_wifi("Home", PW, timeout=5)
    assert time.monotonic() - start < 1
    assert_secret_kept(e.value)
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `.venv/bin/python -m pytest tests/test_robot.py -k setup_wifi -v`
Expected: the four new tests fail; the existing ones pass.

- [ ] **Step 3: Implement**

Add these constants next to `_WIFI_JOINED`:

```python
_IPV4 = r"(\d{1,3}(?:\.\d{1,3}){3})"
_WIFI_JOINED_S3 = re.compile(rf"IP Address: {_IPV4} successfully connected")  # S3 joins without rebooting (OpenCatEsp32S3 reaction.h:1259)
_WIFI_ALREADY_S3 = re.compile(rf"IP Address: {_IPV4}\. Wifi already connected")  # OpenCatEsp32S3 reaction.h:1279
_WIFI_FAILED_S3 = "Timeout: Fail to connect web server!"  # OpenCatEsp32S3 reaction.h:1270
```

In `setup_wifi`:
- next to `already`, add `joined_now: Optional[str] = None`;
- replace the body of the `for line in _lines(...)` loop with the code below;
- change the comment on `transport._unconfirmed.clear()` to `# OpenCatEsp32 reboots; nothing sent earlier will echo now`.

```python
            for line in _lines(transport, deadline):
                joined, found = _WIFI_JOINED.search(line), _WIFI_ALREADY.search(line) or _WIFI_ALREADY_S3.search(line)
                s3_joined = _WIFI_JOINED_S3.search(line)
                if joined:
                    ips.append(joined.group(1))  # once before the reboot, again when it rejoins at boot
                elif ips:
                    if line == READY:
                        if len(ips) > 1:
                            return ips[-1]
                        raise WifiSetupFailed(f"the robot joined {ssid!r} but could not rejoin after rebooting; try again")
                elif s3_joined:
                    joined_now = s3_joined.group(1)
                elif found:
                    already = found.group(1)
                elif _WIFI_FAILED in line or line == _WIFI_FAILED_S3:
                    failed = True
                elif line.startswith(_UNDEFINED):
                    if line == _UNDEFINED:  # OpenCatEsp32: next line is the whole command, password included (:1536)
                        for rest in _lines(transport, deadline):
                            if rest == "w":
                                break
                    raise RobotError("this robot's firmware has no Wi-Fi support; update it with the Petoi Desktop App")
                elif line == "w":  # echoed only when it did not reboot (src/reaction.h:1557)
                    if joined_now:
                        return joined_now
                    if already:
                        warnings.warn(
                            f"the robot is already on Wi-Fi at {already}, so it ignored these details. To change "
                            "networks, hold its BOOT button for about 3 seconds to clear the saved one, then try again.",
                            RuntimeWarning,
                            stacklevel=2,
                        )
                        return already
                    if failed:
                        raise WifiSetupFailed(
                            f"could not join {ssid!r}: check the network name and password, and that it is 2.4 GHz Wi-Fi"
                        )
                    raise RobotError("the robot did not accept the Wi-Fi details")
```

Update the docstring to: `"""Over USB, put the robot on a 2.4 GHz Wi-Fi network and return its IP address for petoi.connect().\n\n        OpenCatEsp32 reboots to start its Wi-Fi server; OpenCatEsp32S3 starts it without rebooting."""`

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `.venv/bin/python -m pytest tests/test_robot.py -k setup_wifi -v`
Expected: all pass, old and new.

- [ ] **Step 5: Commit**

```bash
git add python/src/petoi/robot.py python/tests/test_robot.py
git commit -m "setup_wifi(): handle OpenCatEsp32S3 replies (no reboot, new wording)"
```

---

### Task 5: Uploaded skills follow the robot's joint count

**Files:**
- Modify: `python/src/petoi/_timing.py`, `python/src/petoi/robot.py` (`run_skill_data`, `_check_skill_data`)
- Test: `python/tests/test_robot.py`, `python/tests/test_constants.py`

- [ ] **Step 1: Write the failing tests** (in `tests/test_robot.py`)

```python
def quaddle():
    r = robot()
    r.model = "Quaddle"
    return r


def test_quaddle_posture_has_six_angles():
    quaddle().run_skill_data([1, 0, 0, 1, *([0] * 6)])
    with pytest.raises(ValueError, match="needs 10 values"):
        quaddle().run_skill_data([1, 0, 0, 1, *([0] * 16)])


def test_quaddle_gait_rows_are_four_wide():
    quaddle().run_skill_data([2, 0, 0, 1, *([10] * 8)])  # WALKING_DOF 4 (OpenCatEsp32S3 OpenCat.h:158)
    with pytest.raises(ValueError, match="needs 12 values"):
        quaddle().run_skill_data([2, 0, 0, 1, *([10] * 16)])


def test_quaddle_behavior_rows_are_ten_wide():
    data = [-1, 0, 0, 1, 0, 0, 0, *([0] * 6), 8, 0, 0, 0]  # 7-value header + one row of DOF + 4
    r = Robot(FakeStream({encode("K", *data): ["K", "K"]}), timeout=0.2)  # echoes at start and end
    r.model = "Quaddle"
    assert r.run_skill_data(data).completed


def test_quaddle_extended_behaviors_are_refused():
    with pytest.raises(ValueError, match="over 127 frames"):
        quaddle().run_skill_data([-128, 0, 0, 1])


def test_skill_room_depends_on_the_model():
    r = quaddle()
    assert r._skill_layout() == (6, (4,), 4096 - 1 - 20)
    r.model = "Bittle X"
    assert r._skill_layout()[2] == 2507 - 1 - 20
```

And in `tests/test_constants.py`:

```python
def test_skill_seconds_uses_the_given_joint_count():
    posture = [1, 0, 0, 1, *([10] * 6)]
    assert skill_seconds(posture, [0] * 6, dof=6) == 0.088  # same 11 iterations of 8 ms as 16 joints
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `.venv/bin/python -m pytest tests/test_robot.py tests/test_constants.py -k "quaddle or room or joint_count" -v`
Expected: FAIL.

- [ ] **Step 3: Implement**

In `_timing.py`:
- Delete `_FRAME`.
- Change the signature to `def skill_seconds(data: Sequence[int], start: Sequence[int], dof: int = DOF) -> float:`.
- Change the docstring to `"""Seconds the firmware spends in one skill array (posture or behavior) from `start`, the robot's current angles."""`.
- Inside it, replace each `DOF` with `dof`, and use `frame = dof + 4` where `_FRAME` was.
- Change the iteration time to an explicit 8 ms: `return ((int(diff / speed + 0.5) if speed > 0 else 0) + 1) * 8  # 8 ms per iteration; unverified on Quaddle`.

In `robot.py`:
- import `model_key` from `petoi.constants`;
- add this method on `Robot` before `run_skill_data`:

```python
    def _skill_layout(self) -> Tuple[int, Tuple[int, ...], int]:
        """(joint count, gait row widths, room for angle values) for this robot's firmware."""
        key = model_key(self.model)
        if key == "quaddle":  # DOF, WALKING_DOF, BUFF_LEN - 1 - CMD_LEN (OpenCatEsp32S3 OpenCat.h:155-165, :890, :902-907)
            return 6, (4,), 4096 - 1 - 20
        if key is not None:
            return DOF, (8,), _SKILL_ROOM  # WALKING_DOF (src/OpenCat.h:249-256)
        return DOF, (8, 12), _SKILL_ROOM
```

In `run_skill_data`, replace the two `bittle_like`/`_check_skill_data` lines and the timeout estimate with:

```python
        dof, gait_widths, room = self._skill_layout()
        if dof == 6 and values[:1] == [-128]:  # Quaddle's 8-value extended header (OpenCatEsp32S3 configConstants.h:90-123)
            raise ValueError("Quaddle behaviors over 127 frames (extended header) aren't supported yet")
        _check_skill_data(values, dof, gait_widths, room)
```

```python
                timeout += 1.5 * skill_seconds(values, [a * values[3] for a in values[7:7 + dof]], dof)
```

Change `_check_skill_data(values, gait_widths)` to `_check_skill_data(values, dof, gait_widths, room)`. In its body:
- replace `DOF` with `dof` (in `widths` and `(DOF + 4,)`);
- replace both uses of `_SKILL_ROOM` with `room`.

Run `grep -n "_check_skill_data" tests/` and update any direct calls to pass `16, (8, 12), 2486`.

- [ ] **Step 4: Run the whole suite and confirm it passes**

Run: `.venv/bin/python -m pytest -q && .venv/bin/python -m mypy src`
Expected: all pass, no mypy issues.

- [ ] **Step 5: Commit**

```bash
git add python/src/petoi/_timing.py python/src/petoi/robot.py python/tests/test_robot.py python/tests/test_constants.py
git commit -m "run_skill_data(): use Quaddle's 6 joints, 4-wide gaits and larger buffer"
```

---

### Task 6: `I`/`M` over USB on S3 don't wait for an echo that never comes

**Files:**
- Modify: `python/src/petoi/robot.py` (`send_binary`)
- Test: `python/tests/test_robot.py`

- [ ] **Step 1: Write the failing test**

```python
def test_s3_binary_joint_moves_over_usb_do_not_wait_for_an_echo():
    import serial
    from petoi.transports.serial import SerialTransport

    r = Robot(SerialTransport(serial.serial_for_url("loop://", timeout=0.05), boot_timeout=0), timeout=2)
    r.firmware = "Q_261022"
    start = time.monotonic()
    reply = r.send_binary("I", 0, 30)  # S3 sends the I/M echo to BLE and Wi-Fi only (reaction.h:2655-2657)
    assert time.monotonic() - start < 0.5 and not reply.completed
    assert r.transport._unconfirmed == []  # nothing is owed, so later commands aren't held up
    r.close()
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `.venv/bin/python -m pytest tests/test_robot.py -k binary_joint -v`
Expected: FAIL. It waits about 2 s, because loop:// echoes `I\x00\x1e~`, not the line `I`.

- [ ] **Step 3: Implement.** In `robot.py`, import `SerialTransport` alongside `READY` (`from petoi.transports.serial import READY, SerialTransport`) and change `send_binary`:

```python
    def send_binary(self, token: str, *values: int, wait: bool = True, timeout: Optional[float] = None) -> Reply:
        """Send an uppercase (binary) command, e.g. send_binary("I", 8, -20).

        On S3 firmware over USB, I and M are never confirmed: the robot sends that echo to BLE and Wi-Fi only."""
        payload = encode(token, *values)
        if token in ("I", "M") and self.s3 and isinstance(self.transport, SerialTransport):
            with self._lock:  # OpenCatEsp32S3 reaction.h:2655-2657
                self.transport.write(payload)
            return Reply(token)
        return self._run(token, payload, wait, timeout)
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `.venv/bin/python -m pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add python/src/petoi/robot.py python/tests/test_robot.py
git commit -m "send_binary(): don't wait for the I/M echo S3 never sends over USB"
```

---

### Task 7: Wi-Fi: retry once when the robot is busy

Both firmwares behave the same here (verified by opencat-gemma on Bittle X and Quaddle). A command sent while an earlier web task runs is rejected, but the rejection also aborts that task. One retry therefore gets the command through, which is what lets `stop()` interrupt a walk.

**Files:**
- Modify: `python/src/petoi/transports/websocket.py` (`command`)
- Test: `python/tests/test_websocket.py:69-71`

- [ ] **Step 1: Change the test.** Replace the `pytest.raises(...busy...)` block at lines 70-71 with:

```python
    reply = t.command("b", b"bad\n", timeout=2.0)  # rejected once, which aborts "slow"; the retry runs
    assert reply.completed
    assert [m["commands"] for m in received] == [["slow"], ["bad"], ["bad"]]
```

Rename the test to `test_busy_robot_aborts_the_old_task_and_runs_the_retry`.

- [ ] **Step 2: Run the test and confirm it fails**

Run: `.venv/bin/python -m pytest tests/test_websocket.py -v`
Expected: FAIL with RobotError "still busy".

- [ ] **Step 3: Implement.** In `websocket.py`:
- rename the current `command` method to `_command_once`;
- in its busy branch, replace `raise RobotError("robot is still busy with the previous command; wait for it to finish")` with `raise _Busy()`;
- add:

```python
class _Busy(RobotError):
    """The robot rejected our task because an earlier one was running; that rejection also aborted it."""
```

(module level, after `_CLIENT_LIMIT_HINT`), and on the class:

```python
    def command(self, token: str, payload: bytes, timeout: Optional[float]) -> Reply:
        # The firmware's rejection of an overlapping task also aborts the running one (src/webServer.h:487-512),
        # so one retry gets our command through, e.g. stop() during a walk (opencat-gemma links.py WsLink.send).
        try:
            return self._command_once(token, payload, timeout)
        except _Busy:
            try:
                return self._command_once(token, payload, timeout)
            except _Busy:
                raise RobotError("robot is still busy with the previous command; wait for it to finish") from None
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `.venv/bin/python -m pytest tests/test_websocket.py -v && .venv/bin/python -m mypy src`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add python/src/petoi/transports/websocket.py python/tests/test_websocket.py
git commit -m "Wi-Fi: retry once when the robot reports a busy task"
```

---

### Task 8: Hardware tests, README and TODO

**Files:**
- Modify: `python/tests/hardware/test_smoke.py:30-42`
- Create: `python/tests/hardware/test_s3.py`
- Modify: `python/README.md` (new section after "Connecting"), `python/TODO.md`

- [ ] **Step 1: Make the every-skill test model-aware.** In `test_smoke.py`:
- import `from petoi.constants import RISKY, model_key, skills_for` and drop `ONLY_ON`;
- replace the first three lines of `test_every_skill_completes`, and its print, with:

```python
    model = model_key(robot.model) or "bittle"
    if skill not in skills_for(model):
        pytest.skip(f"{skill.value} is not on {robot.model}")
```

```python
    estimate = f" (estimate {estimate_seconds(model, skill.value):.1f} s)" if model != "quaddle" else ""
    print(f"\n{skill.value}: {elapsed:.1f} s{estimate}")
```

- [ ] **Step 2: Create `tests/hardware/test_s3.py`**

```python
"""Checks for OpenCatEsp32S3 robots (Quaddle). Run with PETOI_PORT, PETOI_BLE or PETOI_WS pointing at one."""
import os
import warnings

import pytest

import petoi
from petoi import QuaddleJoint

TARGETS = [os.environ[k] for k in ("PETOI_PORT", "PETOI_BLE", "PETOI_WS") if os.environ.get(k)]
pytestmark = [pytest.mark.hardware, pytest.mark.skipif(not TARGETS, reason="no robot configured")]


@pytest.fixture(scope="module", params=TARGETS)
def robot(request):
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # '?' retry, BLE handshake and z0 must all succeed quietly
        r = petoi.connect(request.param)
    if not r.s3:
        r.close()
        pytest.skip(f"{r.model} {r.firmware} is not S3 firmware")
    print(f"\n{request.param}: {r.model} firmware {r.firmware}")
    yield r
    r.rest()
    r.close()


def test_leg_moves_and_reads_back(robot):
    robot.joint(QuaddleJoint.LEFT_FRONT_LEG, 30)
    assert robot.joints()[QuaddleJoint.LEFT_FRONT_LEG] == 30
    robot.joint(QuaddleJoint.LEFT_FRONT_LEG, 0)


def test_leg_order_matches_quaddle_joint(robot):
    for joint in QuaddleJoint:
        if joint is QuaddleJoint.HEAD_PAN:
            continue
        input(f"Watch the {joint.name.replace('_', ' ').lower()}; press Enter to move it")
        robot.joint(joint, 30)
        robot.joint(joint, 0)
        assert input("Did that leg move? [y/n] ").strip().lower() == "y"


@pytest.mark.skipif(not os.environ.get("PETOI_SCOUT"), reason="set PETOI_SCOUT=1 for a Quaddle Scout (head pan)")
def test_scout_head_pan_is_joint_0(robot):
    input("Watch the head; press Enter to move it")
    robot.joint(QuaddleJoint.HEAD_PAN, 30)
    robot.joint(QuaddleJoint.HEAD_PAN, 0)
    assert input("Did the head turn? [y/n] ").strip().lower() == "y"


def test_robot_stays_still_after_connect(robot):
    robot.stand()
    input("Leave the robot idle for 10 s and watch it. Press Enter when done")
    assert input("Did it stay still (no random head or leg moves)? [y/n] ").strip().lower() == "y"
```

Run it with `-s` so `input()` works: `PETOI_PORT=… .venv/bin/python -m pytest tests/hardware/test_s3.py -v -s`.

- [ ] **Step 3: README.** Add this section after "Connecting":

````markdown
### Robots and firmware

| Robot | Firmware | Links | Joints |
|---|---|---|---|
| Bittle X, Bittle X+Arm, Nybble Q | OpenCatEsp32 (BiBoard) | USB, Bluetooth, BLE, Wi-Fi | `Joint` (16) |
| Quaddle | OpenCatEsp32S3 | USB, BLE, Wi-Fi (no Bluetooth Classic) | `QuaddleJoint`: 4 legs; Quaddle Scout also has `HEAD_PAN` |

`robot.s3` tells you which firmware you're on. On S3 firmware, `connect()` sends `z0` so the robot stops moving
by itself when idle (until it reboots). On a Quaddle, `send_binary("I"/"M")` over USB is never confirmed. Use
`joint()` / `move_joints()` instead. Skills: `petoi.constants.skills_for("quaddle")` lists the `Skill` members a
Quaddle has. Its other skills work with `robot.skill("name")`.
````

- [ ] **Step 4: TODO.md.**

Under "Needs a real robot", add:
- `[ ] **Quaddle (S3 firmware)**: run tests/hardware/test_s3.py and test_smoke.py over USB, BLE and Wi-Fi. Check: the '?' retry on a sleeping robot, the BLE handshake, z0 keeping it still, leg order, that Scout's extra joint is the head pan at index 0 (PETOI_SCOUT=1; assumed from PetoiWebCoding and the firmware's HEADPAN define), skill timings (the estimator is unverified for 6 joints), and setup_wifi() without a reboot.`
- `[ ] **BLE connect on Bittle X after Part F**: connect now always asks '?' and waits for the forced rest. opencat-gemma made the same change, but it wasn't checked on a Bittle X there either.`

Under "Decisions to revisit", add:
- `[ ] **Chero** (S3, board C): later, per owner. Needs its own skill table (no crawl, side gaits or bk) and joint map.`
- `[ ] **Bittle/Nybble on S3 firmware**: not detected or supported; S3 Bittle lacks knock and lucky.`
- `[ ] **Quaddle extended behaviors** (over 127 frames, -128 header): refused for now.`

- [ ] **Step 5: Run everything, then commit**

Run: `.venv/bin/python -m pytest -q -W error::DeprecationWarning && .venv/bin/python -m mypy src`
Expected: all pass (hardware tests skipped).

```bash
git add python/tests/hardware python/README.md python/TODO.md
git commit -m "Hardware checks, README and TODO for Quaddle (S3) support"
```

---

### Task 9: Independent review

- [ ] Dispatch `superpowers:code-reviewer` on the Part F commit range. Point it at this plan and the "Sources" table, with emphasis on:
  - `z0` can never reach OpenCatEsp32;
  - no robot output with the Wi-Fi password is kept or shown;
  - the BLE `_settle` race between the notify thread and the caller.
- [ ] Fix the confirmed findings with tests first, then rerun the full suite and mypy.

## Not in this plan

- Chero (owner decision). Bittle or Nybble running S3 firmware.
- Quaddle-only `Skill` members (`gallop`, `paddle`, `qWheel*`, …): `skill("name")` already runs them.
- `w?` / `w!` helpers (`wifi_ip()`, clearing Wi-Fi): S3-only commands; a follow-up.
- Vendoring any S3 firmware file. The private source stays out of this public repo; only `PETOI_S3_SRC` points at it.
