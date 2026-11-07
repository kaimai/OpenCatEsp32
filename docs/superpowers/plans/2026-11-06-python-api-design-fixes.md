# Part K: Python API design fixes before the JavaScript port Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Fix the three gaps found when checking the Python API against published API design guidelines (`docs/superpowers/specs/2026-11-06-javascript-api-notes.md`, "Python API: gaps" 1-3), before the JavaScript port copies them.

**Architecture:** (1) Optional settings (`wait`, `timeout`, `sequential`, `check_firmware`, `skill_timeout`) become keyword-only. (2) A `petoi` logger records traffic at DEBUG in `StreamTransport` and `WebSocketTransport`, and `setup_wifi()` sends with `secret=True` so nothing from it is logged. (3) `skill()` raises `ValueError` for a `Skill` member that the connected model's firmware doesn't have.

**Tech Stack:** Python 3.9+, pytest, mypy. Worktree `/Users/kaikai/projects/petoi codes/OpenCatEsp32-Quadruped-Robot - python-api`, branch `feature/python-api`, run from `python/`.

**GBrain:** MCP disconnected this session; query skipped.

---

## Facts this plan relies on

- No call in `src/`, `tests/`, `examples/` or `README.md` passes `wait`, `timeout`, `sequential` or a connect timeout by position (grep, 2026-11-06). `send_binary()` already takes `wait` and `timeout` keyword-only (after `*values`).
- The package is unpublished (0.1.0, not on PyPI), so the signature change breaks no users.
- The only robot lines that carry the Wi-Fi password come during `setup_wifi()`: `Password: ****<last 4>` and the "Undefined token" echo of the whole command (`src/reaction.h:447-456`, `robot.py:291-296`). `setup_wifi()` reads them with `transport.readline()` directly, not through `expect()`, so logging in `expect()` never sees them.
- `skills_for(model_key(...))` knows only `Skill` members. Quaddle has many skills outside the enum (`constants.py:136-145`), so plain strings that aren't `Skill` values must still pass unchecked.
- Limit of fix 3: when `connect()` can't read the model (`robot.model is None`), nothing is checked. The 2026-11-06 Quaddle run where Bittle skills "finished" in 0.3 s was that case; this fix would not have caught it.

### Task 0: Commit this plan

- [ ] `git add docs/superpowers/plans/2026-11-06-python-api-design-fixes.md && git commit -m "Plan Part K: keyword-only options, traffic logging, model skill check"`

### Task 1: Keyword-only options

**Files:** `python/src/petoi/robot.py`, `python/src/petoi/connect.py`, test `python/tests/test_robot.py`, `python/tests/test_connect.py`.

- [ ] **Failing test** (append to `tests/test_robot.py`):

```python
@pytest.mark.parametrize(
    "call",
    [
        lambda r: r.send("ksit", False),
        lambda r: r.skill("hi", False),
        lambda r: r.run_skill_data(POSTURE, False),
        lambda r: r.sit(False),
        lambda r: r.stand(False),
        lambda r: r.stop(False),
        lambda r: r.rest(False),
        lambda r: r.walk("left", False),
        lambda r: r.trot("left", False),
        lambda r: r.crawl("left", False),
        lambda r: r.back("left", False),
        lambda r: r.joint(8, 30, False),
        lambda r: r.move_joints({8: 30}, True),
        lambda r: r.melody([(1, 8)], False),
        lambda r: r.setup_wifi("Home", PW, 5.0),
    ],
)
def test_optional_settings_are_keyword_only(call):
    with pytest.raises(TypeError):  # robot.sit(False) doesn't say what False means
        call(robot())


def test_robot_timeouts_are_keyword_only():
    with pytest.raises(TypeError):
        Robot(FakeStream(), 5.0)
```

Append to `tests/test_connect.py`:

```python
def test_connect_settings_are_keyword_only():
    with pytest.raises(TypeError):
        petoi.connect("mock", 5.0)
```

(Check that `tests/test_connect.py` imports `petoi` and `pytest`; add the imports if not.)

- [ ] Run `.venv/bin/python -m pytest tests/test_robot.py tests/test_connect.py -k keyword -v`. Expected: FAIL (no `TypeError`).
- [ ] **Change the signatures** (bodies unchanged):

```python
# robot.py
def __init__(self, transport: Transport, *, timeout: float = 5.0, skill_timeout: float = 30.0):
def send(self, command: str, *, wait: bool = True, timeout: Optional[float] = None) -> Reply:
def skill(self, name: Union[Skill, str], *, wait: bool = True, timeout: Optional[float] = None) -> Reply:
def run_skill_data(self, data: Sequence[int], *, wait: bool = True, timeout: Optional[float] = None) -> Reply:
def sit(self, *, wait: bool = True) -> Reply:
def stand(self, *, wait: bool = True) -> Reply:
def stop(self, *, wait: bool = True) -> Reply:
def rest(self, *, wait: bool = True) -> Reply:
def walk(self, direction: Direction = "forward", *, wait: bool = True) -> Reply:
def trot(self, direction: Direction = "forward", *, wait: bool = True) -> Reply:
def crawl(self, direction: Direction = "forward", *, wait: bool = True) -> Reply:
def back(self, direction: Optional[Literal["left", "right"]] = None, *, wait: bool = True) -> Reply:
def joint(self, index: Union[Joint, int], angle: float, *, wait: bool = True) -> Reply:
def move_joints(self, angles: Dict[Union[Joint, int], float], *, sequential: bool = False, wait: bool = True) -> Reply:
def melody(self, notes: Sequence[Tuple[int, int]], *, wait: bool = True) -> Reply:
def setup_wifi(self, ssid: str, password: str, *, timeout: float = 60.0) -> str:

# connect.py
def connect(target: Optional[str] = None, *, timeout: float = 5.0, check_firmware: bool = True) -> Robot:
```

  `connect.py` already builds `Robot(transport, timeout=timeout)`. Grep `src/` for any internal positional call these signatures now reject (`grep -rn "Robot(\|\.skill(\|\.sit(\|_cmd(" src`) and fix it.
- [ ] Run the whole suite and mypy. Expected: all pass.
- [ ] Commit: "Make optional settings keyword-only, so robot.sit(False) can't hide what False means".

### Task 2: Traffic logging at DEBUG, with Wi-Fi setup hidden

**Files:** `python/src/petoi/transports/base.py`, `python/src/petoi/transports/websocket.py`, `python/src/petoi/robot.py`, `python/tests/hardware/safety.py`, `python/README.md`; tests `python/tests/test_robot.py`, `python/tests/test_websocket.py`.

- [ ] **Failing tests** (append to `tests/test_robot.py`, add `import logging` at the top):

```python
def test_traffic_is_logged_at_debug(caplog):
    caplog.set_level(logging.DEBUG, logger="petoi")
    robot().sit()
    assert "-> b'ksit\\n'" in caplog.text
    assert "<- k" in caplog.text


def test_nothing_from_wifi_setup_is_logged(caplog):
    caplog.set_level(logging.DEBUG, logger="petoi")
    wifi_robot([JOINED, "Rebooting to use web server.", JOINED, "Ready!"]).setup_wifi("Home", PW)
    assert PW not in caplog.text and "9876" not in caplog.text
    assert "Wi-Fi setup command hidden" in caplog.text  # still shows that something was sent
```

Append to `tests/test_websocket.py` (add `import logging` at the top):

```python
def test_wifi_traffic_is_logged_at_debug(port, caplog):
    caplog.set_level(logging.DEBUG, logger="petoi")
    t = WebSocketTransport("127.0.0.1", port=port, heartbeat=False)
    t.command("?", b"?\n", timeout=2.0)
    t.close()
    assert "-> ?" in caplog.text
    assert "Bittle X" in caplog.text
```

- [ ] Run `.venv/bin/python -m pytest tests/test_robot.py tests/test_websocket.py -k "logged" -v`. Expected: FAIL.
- [ ] **`base.py`:** add `import logging` and `log = logging.getLogger("petoi")`. Change `write_command`:

```python
    def write_command(self, payload: bytes, *, secret: bool = False) -> None:
        """Write one command, first waiting out WRITE_GAP if the previous one is unconfirmed.

        secret: log that a command went out, but not its bytes (Wi-Fi setup carries the password)."""
        if self._owed_write_at:
            wait = self._owed_write_at + self.WRITE_GAP - time.monotonic()
            if wait > 0:
                time.sleep(wait)
        log.debug("-> %s", "(Wi-Fi setup command hidden)" if secret else payload)
        self.write(payload)
        self._owed_write_at = time.monotonic()
```

  In `expect()`'s `next_line()`, right after `line = self.readline(remaining)`:

```python
                if line is not None:
                    log.debug("<- %s", line)
```

  (keep the existing `if line is not None:` block below it; merge the two if cleaner).
- [ ] **`websocket.py`:** add `import logging`, `log = logging.getLogger("petoi")`. In `_command_once`, after building the command, `log.debug("-> %s", to_web_command(payload))`; when a task completes, `log.debug("<- %s", "".join(msg.get("results", [])).strip())`. `setup_wifi()` refuses Wi-Fi links, so nothing secret goes this way.
- [ ] **`robot.py` `setup_wifi()`:** `transport.write_command(payload, secret=True)`.
- [ ] **`tests/hardware/safety.py`:** `guarded_write(payload, **kw)` passes `**kw` on to `write_command`.
- [ ] **README:** under a short "Seeing what is sent" section: `import logging; logging.basicConfig(level=logging.DEBUG)` shows every command and reply; Wi-Fi setup is shown only as "(Wi-Fi setup command hidden)".
- [ ] Run the whole suite and mypy. Expected: all pass.
- [ ] Commit: "Log commands and replies at DEBUG on the petoi logger; never log Wi-Fi setup".

### Task 3: Refuse a skill the connected model doesn't have

**Files:** `python/src/petoi/robot.py`, test `python/tests/test_robot.py`, `python/README.md`.

- [ ] **Failing tests** (append to `tests/test_robot.py`):

```python
def quaddle():
    r = robot()
    r.model = "Quaddle"
    return r


def test_skill_the_model_lacks_is_refused():
    with pytest.raises(ValueError, match="'clap' is not a Quaddle skill"):
        quaddle().skill(Skill.CLAP)
    with pytest.raises(ValueError, match="send"):
        quaddle().skill("clap")  # the value of a Skill member counts too


def test_names_outside_skill_still_go_through():
    r = quaddle()
    r.skill("wkF")  # Quaddle's own skills aren't all in Skill
    assert r.transport.written[-1] == b"kwkF\n"


def test_unknown_model_checks_nothing():
    r = robot()  # model None: connect() couldn't read it
    r.skill(Skill.CLAP)
    assert r.transport.written[-1] == b"kclap\n"
```

- [ ] Run `.venv/bin/python -m pytest tests/test_robot.py -k "model_lacks or outside_skill or unknown_model" -v`. Expected: the first FAILS, the other two pass.
- [ ] **`robot.py`:** import `skills_for` from `petoi.constants` (next to `model_key`). At the start of `skill()`:

```python
        key = model_key(self.model)
        if key is not None:
            member = name if isinstance(name, Skill) else next((s for s in Skill if s.value == name), None)
            if member is not None and member not in skills_for(key):
                raise ValueError(f"{member.value!r} is not a {self.model} skill; send('k{member.value}') sends it anyway")
```

  Check `walk()`, `sit()` and the rest don't go through `skill()` (they call `_cmd("k", ...)` directly); if any does, make sure its gait name isn't refused on Quaddle.
- [ ] Docstring of `skill()`: add "Raises ValueError for a Skill this model's firmware doesn't have (known after connect())."
- [ ] README skills section: one line saying the same.
- [ ] Run the whole suite and mypy. Expected: all pass, including the hardware suite's `test_every_skill_completes` unit-collection (it already skips skills not on the model).
- [ ] Commit: "Refuse a Skill the connected model's firmware doesn't have, instead of letting it confirm in 0.3 s".

### Task 4: Wrap-up

- [ ] Update the "Python API: gaps" list in `docs/superpowers/specs/2026-11-06-javascript-api-notes.md`: mark 1-3 fixed with their commits.
- [ ] Optional hardware check (owner present, robot on the floor): `PETOI_PORT=... pytest tests/hardware -k "every_skill and (sit or hi)" -s` with `logging` on, to see real traffic in the log. Not required: the changes are covered by unit tests.
- [ ] Commit. Don't push without asking.
