# Python API follow-ups: proposed plans

> **Status: APPROVED 2026-10-27 (parts A–E).** Owner decisions:
> - D: remove `Skill.SLEEP`; include `calibrate_gyro()`.
> - C: `skill_timeout` = 30 s for now; flagged in `python/TODO.md` for review after hardware timing.
> - B: owner undecided on rejecting 126 vs clamping, and on Wi-Fi returning when a behavior starts. Implement as planned (reject; document the Wi-Fi limit) and keep both open in `python/TODO.md`.
> - E: `[project.urls]` point at upstream `PetoiCamp/OpenCatEsp32-Quadruped-Robot`; `authors` = Rongzhong Li and Kai Mai (no emails). Remaining E questions take the plan's defaults: docs URL `https://docs.petoi.com`, "3 - Alpha", exact pins for mypy/types-pyserial, no oldest-bleak job, sdist contents unchanged, keep the `CI` override in test_constants.
> - Order: E (without mypy) → D → C → B → A → E's mypy step.
> Parent plan: `2026-10-27-python-api.md`. Source list: `python/TODO.md`.

Five independent plans, drafted in parallel by read-only planning agents on 2026-10-27. The coordinator checked each plan's key firmware references against `src/`. Anything a plan marks UNVERIFIED still needs a real robot.

| Part | Topic | Main files | Hardware needed to confirm |
|---|---|---|---|
| A | `Robot.setup_wifi(ssid, password)` over USB | robot.py, errors.py | USB link survives `ESP.restart()`; reboot time |
| B | `Robot.run_skill_data(data)`: upload a `K` skill | robot.py, transports/base.py, mock.py | serial pacing of a 2487-byte upload |
| C | `skill_timeout` (30 s) for one-shot skills | robot.py, tests | measured skill durations vs estimates |
| D | `gyro_state()`, `calibrate_gyro()`, 16 sourced skills, drop `Skill.SLEEP` | robot.py, constants.py, mock.py | calibration time on MPU6050 and ICM42670 |
| E | hatchling floor, metadata, mypy job, websockets-13 job, test_constants skip | pyproject.toml, workflow, small typing fixes | none |

## Integration notes (coordinator)

The parts don't depend on each other's design, but they touch the same files, so the order matters:

1. **D before C.** C's estimator test checks every `Skill` member; D adds members (`SERVO_TEST`, the arm skills) and removes `SLEEP`. Re-run C's estimates after D lands.
2. **One duration estimator, not two.** B adds `_behavior_seconds()` in `robot.py`; C adds `estimate_seconds()` in `tests/test_constants.py`. Both model the same firmware timing (`src/skill.h:280-363`, `src/motion.h:176-203`). Keep B's in the package and have C's test call it, with C's start-posture handling folded in.
3. **B changes `StreamTransport.command()`** by splitting out `expect()`. A clears `_unconfirmed` directly. Land B's split first, or have A use it.
4. **C and B both set timeouts on `K`/`k`.** `skill()` gets `skill_timeout` (C); `run_skill_data()` computes its own (B). Gaits and postures keep `robot.timeout`.
5. **E's mypy job last.** It must type-check A, B and D too. E's `_CLOSED` sentinel change (an empty dict compared by identity) reads oddly; prefer annotating the queue as `Queue[Any]` and keeping `object()`.
6. **Existing bug found by C (not in any part):** over Wi-Fi, `wait=False` waits the transport's 5 s default, because `timeout or self._default_timeout` treats 0 as unset (`python/src/petoi/transports/websocket.py:106`). Needs its own fix and test.

Suggested order: E (except the mypy step) → D → C → B → A → E's mypy step.

## Owner questions (collected; answered above)

- A: is a 60 s default for `setup_wifi` acceptable? Keep the "already on Wi-Fi: warn and return the IP" behavior?
- B: accept that over Wi-Fi a behavior returns as it starts (firmware limit)? Accept rejecting 126 rather than clamping?
- C: 30 s `skill_timeout` default?
- D: remove `Skill.SLEEP` (its `zz` data is "all joints to 0", the same pose as `zero`)? Include `calibrate_gyro()`, which writes new offsets to flash?
- E: repo URL (upstream `PetoiCamp/OpenCatEsp32-Quadruped-Robot` or the fork), docs URL, `authors`, classifier level, exact tool pins, oldest bleak job, sdist contents, and keeping the `CI` override in `test_constants`.

---


## Part A

### Amendment: Wi-Fi setup from Python (proposed)

**Firmware facts**

- `w` is handled only when built with `WEB_SERVER` (`src/reaction.h:435`). This repo defines it (`src/OpenCat.h:92`). `WIFI_MANAGER` is commented out, "always off for now" (`src/OpenCat.h:91`). Without `WEB_SERVER` the firmware prints `Undefined token!` and then `newCmd`, which is `%ssid%password` in clear text (`src/reaction.h:1535-1536`).
- **Parsing.** `read_serial` stores everything after the token up to `\n` in `newCmd`, so `newCmd` is `%SSID%password` (`src/moduleManager.h:396-444`). It strips `\r` and `\n` anywhere (`:435-439`). `leftTrimSpaces` has no effect here because `newCmd` starts with `%` (`src/tools.h:177-184`).
  - The SSID is `substring(1, indexOf('%', 2))`, and the password is everything after that `%` (`src/reaction.h:442-446`).
  - So the SSID cannot contain `%` except as its first character, which is an odd case we reject anyway. The password may contain `%` and spaces.
  - The leading `%` is required: `wHome%pw` loses its first character.
  - `BUFF_LEN` is 2507 (`src/OpenCat.h:443`), so the buffer is never the limit.
- **Secrets the robot prints back.** Before joining it prints `WifiSSID: \t<ssid>` and `Password: \t<mask>` (`src/reaction.h:447-458`). The mask shows the **last 4 characters**, or the **whole** password if it is 4 characters or fewer. Robot output must therefore never go into Python error messages.
- **`connectWifi()` timeout.** Each attempt polls `WiFi.status()` 100 times with `delay(100)`, about 10 s. It makes 3 attempts with a 2 s pause before each retry. Total worst case is about 34 s (`src/webServer.h:554-585`).
  - On failure, `WEB_DEBUG_LEVEL` 1 (`src/webServer.h:15`) prints `WiFi connection failed on attempt: \tN` once per attempt and `All WiFi connection attempts failed` (`:579`, `:584`).
  - Then `Timeout: Fail to connect Wifi!` is printed with `Serial.println`, which reaches **USB only** (`src/reaction.h:477`).
- **Token echo.** The echo `printToAllPorts(token)` runs after the switch (`src/reaction.h:1557`).
  - On success, `ESP.restart()` runs inside the case after `delay(3000)` (`:471-473`), so there is **no echo**.
  - On failure, the "already connected" path, and a bare or malformed `w`, `w` **is** echoed after the case's own lines.
- **Already connected.** If `webServerConnected` is true, the robot prints `Wifi already connected to IP Address: <ip>` plus 3 help lines, then echoes `w` (`src/reaction.h:483-489`). It **ignores** the new credentials.
- **Bare `w` when not connected.** It prints the help text, which is 2 lines because the `PTLF` string contains `\n`. `indexOf` returns -1, so nothing else happens, and it echoes `w` (`src/reaction.h:440-443`). A bare `w` when connected reports the IP.
- **What `webServerConnected` gates.**
  - It gates the `w` handler (`src/reaction.h:438`) and `WebServerLoop` (`src/webServer.h:690`), plus the web/BLE broadcast paths (`src/webServer.h:201`, `:227`; `src/bluetoothManager.h:153`; `src/bleClient.h:167`).
  - It becomes true only through `connectWifi` (`src/reaction.h:459`, `src/webServer.h:619`).
  - On the `w` path the WebSocket server is **not** started: `webSocket.begin()` is called only in `connectWifiFromStoredConfig` at boot (`src/webServer.h:624`). That is why the robot reboots. `connect(ip)` cannot work until it has rebooted.
- **Persistence.** On success the firmware saves `WifiManager=true` (`src/reaction.h:466-470`). At boot this is read into `rebootForWifiManagerQ` (`src/configConstants.h:705`).
  - Without `WIFI_MANAGER`, boot calls `connectWifiFromStoredConfig()` (`src/OpenCat.h:705-708`). That function reads the SSID and password ESP-IDF stored (`esp_wifi_get_config`, `src/webServer.h:604-612`).
  - On success it prints `Successfully connected Wifi to IP Address: <ip>` again (`src/webServer.h:622`). This happens **before** `Ready!` (`src/OpenCat.h:771`).
  - If no SSID is stored it returns without printing anything; the warning is at `WEB_WARN` level 2, which is off (`:614-616`). If the join fails it prints `Timeout: Fail to connect web server!` (`:632`).
  - So the robot boots straight onto Wi-Fi every time after setup.
- **Changing networks.** There is no serial command to clear the saved network.
  - Holding BOOT (GPIO0) sets the flag and restarts (`src/reaction.h:199-223`).
  - Holding it through the 10-step countdown (10 × 200 ms, about 2 s, `:212-219`) calls `resetWifiManager()`, which runs `esp_wifi_restore` and clears the stored credentials (`src/webServer.h:674-684`).
- **Arduino core limits, from the locally installed core.** These come from arduino-esp32 2.0.12 at `~/Library/Arduino15/.../2.0.12/libraries/WiFi/src`.
  - `WiFi.begin` rejects an empty SSID or one over 32 bytes, and a passphrase over 64 bytes (`WiFiSTA.cpp:231`, `:236`).
  - An empty password means an open network (`WiFiSTA.cpp:96-104`).
  - Credentials are saved to flash by default (`WiFiGeneric.cpp:758` `_persistent = true`; RAM storage only if not persistent, `:689`).
- **USB link across the reboot.** `ESP.restart()` is a software reset. The serial port belongs to the USB-UART bridge chip (`connect.py` `_USB_HINTS`), so the host port should stay open. `SerialTransport` should not need to reopen; it just reads through the boot log. `LineBuffer` decodes junk bytes with `replace` (`python/src/petoi/protocol.py`, `LineBuffer.feed`).
- **WebSocket port.** It is 81 (`src/webServer.h:59`), which `WebSocketTransport` already uses.

**Open questions / UNVERIFIED**

1. UNVERIFIED: the USB serial port stays open through `ESP.restart()`, so no reopen is needed. This is expected for an external CH340/CP210x bridge but has not been seen on hardware. The hardware test checks it by calling `info()` on the same connection after setup.
2. UNVERIFIED: which arduino-esp32 version official firmware builds use. The 32/64-byte limits and the persistence default were read from the locally installed 2.0.12; the repo does not pin a version.
3. UNVERIFIED: whether a 1–7 character WPA password fails at once or only after about 34 s. No minimum is enforced.
4. UNVERIFIED: Bluetooth (BT) and BLE behavior.
   - The failure text is sent to USB only (`src/reaction.h:477`), so over BT/BLE a wrong password would surface as "did not accept".
   - On success the reboot drops the BT/BLE link, so the call ends in `ConnectionFailed` even though the robot joined.
   - Only USB is documented.
5. UNVERIFIED: the real reboot time including the Wi-Fi rejoin. A 60 s default is assumed (34 s worst-case join + 3 s + boot of about 8 s, per the test_smoke comment "USB connect can take ~8 s").
6. UNVERIFIED: the BOOT-button hold time needed to clear the network. The code implies about 2 s; the README says "about 3 seconds".
7. UNVERIFIED: the Desktop App tester's behavior (`w%ssid%pw`, 5 s sleep, then `w`). I took this from the brief and did not read it.
8. "2.4 GHz only" is Espressif's ESP32 radio specification. It is not in this repo, though it is widely known.
9. A brand-new board can stop at the IMU `(Y/n)` prompt (`src/imu.h:1013`) and never print `Ready!`. The plan handles this with a warning and still returns the IP.

**Decisions**

- **`Robot.setup_wifi(ssid, password, timeout=60.0) -> str`, a method.**
  - Rejected: a module-level `petoi.setup_wifi(...)`. It would repeat `connect()`/`close()` and add a second way to do the same thing. A method uses the port the user already has open, holds `_lock` for the whole exchange including the reboot, and is testable with `FakeStream`.
  - Rejected for now: a `petoi wifi` CLI with `getpass`, and a `wifi_ip()` query. Both are listed as follow-ups.
- **Read lines directly instead of going through `Transport.command()`.** On success the firmware never echoes, so `command()` would always run to its timeout. Rejected: adding an "until" predicate to `collect_reply`/`Transport.command`, which touches every transport for one caller.
  - The method checks for a `StreamTransport` and uses `write`/`readline`/`discard_input`.
  - It also clears `_unconfirmed`: after a reboot, nothing sent earlier will ever echo.
- **Wait through the reboot.** The method returns the IP printed at boot, after `Ready!`, because the WebSocket server starts only at boot (`src/webServer.h:624`). Seeing that line also proves the credentials were saved.
  - Rejected: returning the first IP straight away, because `connect(ip)` would fail during boot.
  - Rejected: a fixed sleep followed by `w`, as the Desktop App does. Fixed sleeps race a boot of variable length.
  - If the deadline passes after the robot joined but before `Ready!`, the method warns and returns the IP. If `Ready!` arrives with no boot IP, it raises `WifiSetupFailed`.
- **Already on Wi-Fi: return the current IP with a `RuntimeWarning`; do not raise.** This means re-running a beginner's script works. The warning says the new details were ignored and explains the BOOT-button reset.
- **One timeout, default 60 s.** It covers the worst-case failure (about 34 s) and the success path including the reboot.
- **Errors:**
  - `ValueError`: bad input, raised before anything is sent.
  - `WifiSetupFailed`: new, a subclass of `RobotError`, exported. It is raised when the robot cannot join, or cannot rejoin after the reboot. Rejected: plain `RobotError`, because a beginner could not tell a wrong password from a protocol mismatch.
  - `RobotError`: the link is not a stream (Wi-Fi), the firmware has no Wi-Fi support, or the details were not accepted.
  - `RobotTimeout`: no result within the timeout.
  - `ConnectionFailed`: raised by the transport if the link drops.
- **Password secrecy.**
  - The password never appears in an exception message or a warning.
  - No `Reply` and no robot line are kept or shown: the robot itself prints the last 4 characters (`src/reaction.h:449-458`), and the whole command on `Undefined token!` (`:1536`).
  - The method does not use `_cmd()`, because its `RobotTimeout` message quotes the payload.
  - The package has no logging, and none is added.
  - The SSID is not secret and appears in messages.
- **Validation.**
  - SSID: 1–32 UTF-8 bytes, with no `%`.
  - Password: at most 64 bytes, with no minimum; `""` means an open network. `%` is allowed.
  - Both: reject `\r`, `\n` and `\0`. `\r`/`\n` would split or truncate the command; `\0` would end the C string.
- **Mock is unchanged.** `connect("mock").setup_wifi(...)` gets a bare `w` echo and raises "did not accept". Rejected: a fake IP from the mock, which would mislead.

**Files**

- Modify `python/src/petoi/errors.py` to add `WifiSetupFailed`.
- Modify `python/src/petoi/__init__.py` to export `WifiSetupFailed`.
- Modify `python/src/petoi/robot.py` to add `setup_wifi`, `_check_wifi`, `_lines` and the reply patterns.
- Modify `python/tests/test_robot.py` to add the `FakeStream` tests.
- Modify `python/tests/test_serial.py` to add the loopback round-trip test through the real `SerialTransport` and `LineBuffer`.
- Create `python/tests/hardware/test_wifi_setup.py`.
- Modify `python/README.md` and `python/TODO.md`.
- Modify `docs/superpowers/plans/2026-10-27-python-api.md` to append this amendment once it is approved.

**Tests** (write first; all should fail with `AttributeError`/`ImportError` before the implementation exists)

Add to `python/tests/test_robot.py` (extend the imports):

```python
from petoi.errors import RobotError, RobotTimeout, WifiSetupFailed
from petoi.transports.base import Transport

PW = "s3cret-pw-9876"
SENT = b"w%Home%" + PW.encode() + b"\n"
INTRO = [  # src/reaction.h:440, :447, :458 (the robot shows the last 4 characters)
    "The wifi info should start with 'w' and followed by ssid and password, separated by %.",
    " e.g. w%WifiName%password",
    "WifiSSID: \tHome",
    "Password: \t**********9876",
]
JOINED = "Successfully connected Wifi to IP Address: 192.168.1.23"  # src/reaction.h:465, src/webServer.h:622


def wifi_robot(lines):
    return robot({SENT: INTRO + lines})


def assert_secret_kept(error):
    assert PW not in str(error) and "9876" not in str(error)


def test_setup_wifi_returns_the_ip_after_the_reboot():
    r = wifi_robot([JOINED, "Rebooting to use web server.", "ets Jun  8 2016 00:22:57", JOINED, "Ready!"])
    assert r.setup_wifi("Home", PW) == "192.168.1.23"
    assert r.transport.written == [SENT]


def test_setup_wifi_prefers_the_address_from_after_the_reboot():
    r = wifi_robot([JOINED, "Rebooting to use web server.",
                    "Successfully connected Wifi to IP Address: 192.168.1.40", "Ready!"])
    assert r.setup_wifi("Home", PW) == "192.168.1.40"


def test_setup_wifi_wrong_password_raises_without_the_password():
    r = wifi_robot([f"WiFi connection failed on attempt: \t{n}" for n in (1, 2, 3)]
                   + ["All WiFi connection attempts failed", "Timeout: Fail to connect Wifi!", "w"])
    with pytest.raises(WifiSetupFailed, match="'Home'") as e:
        r.setup_wifi("Home", PW)
    assert_secret_kept(e.value)


def test_setup_wifi_raises_if_the_robot_cannot_rejoin_after_reboot():
    r = wifi_robot([JOINED, "Rebooting to use web server.", "Timeout: Fail to connect web server!", "Ready!"])
    with pytest.raises(WifiSetupFailed, match="rejoin") as e:
        r.setup_wifi("Home", PW)
    assert_secret_kept(e.value)


def test_setup_wifi_returns_the_ip_with_a_warning_if_the_reboot_is_slow():
    r = wifi_robot([JOINED, "Rebooting to use web server."])
    with pytest.warns(RuntimeWarning, match="did not finish rebooting"):
        assert r.setup_wifi("Home", PW, timeout=0.2) == "192.168.1.23"


def test_setup_wifi_when_already_on_wifi_warns_and_returns_the_ip():
    r = robot({SENT: ["Wifi already connected to IP Address: 10.0.0.7",  # src/reaction.h:485-488
                      "Web server should already be running",
                      "Press the BOOT key to reboot and use Wifi manager.",
                      "Hold the BOOT key and count down 10 if you want to clear the previous Wifi credentials.",
                      "w"]})
    with pytest.warns(RuntimeWarning, match="already on Wi-Fi") as seen:
        assert r.setup_wifi("Home", PW) == "10.0.0.7"
    assert_secret_kept(seen[0].message)


def test_setup_wifi_silence_raises_timeout_without_the_password():
    r = robot(auto_echo=False)
    with pytest.raises(RobotTimeout, match="Wi-Fi") as e:
        r.setup_wifi("Home", PW, timeout=0.2)
    assert_secret_kept(e.value)


def test_setup_wifi_on_firmware_without_wifi_hides_the_echoed_command():
    r = robot({SENT: ["Undefined token!", "%Home%" + PW, "w"]})  # src/reaction.h:1535-1536
    with pytest.raises(RobotError, match="no Wi-Fi support") as e:
        r.setup_wifi("Home", PW)
    assert_secret_kept(e.value)


def test_setup_wifi_bare_echo_means_not_accepted():
    with pytest.raises(RobotError, match="did not accept"):
        robot({SENT: INTRO[:2] + ["w"]}).setup_wifi("Home", PW)


@pytest.mark.parametrize("password", ["", "a%b c"])  # open network; '%' kept (src/reaction.h:446)
def test_setup_wifi_sends_open_and_percent_passwords_unchanged(password):
    name = "n" * 32
    ip = "Successfully connected Wifi to IP Address: 10.0.0.9"
    r = robot({f"w%{name}%{password}\n".encode(): [ip, ip, "Ready!"]})
    assert r.setup_wifi(name, password) == "10.0.0.9"


@pytest.mark.parametrize(
    "ssid, password, match",
    [
        ("", PW, "1 to 32 bytes"),
        ("x" * 33, PW, "1 to 32 bytes"),
        ("é" * 17, PW, "1 to 32 bytes"),  # 34 UTF-8 bytes
        ("my%net", PW, "%"),
        ("Home\n", PW, "line break"),
        ("Home", "p" * 65, "64 bytes"),
        ("Home", PW + "\r", "line break"),
        ("Home", PW + "\0", "line break"),
    ],
)
def test_setup_wifi_rejects_what_the_firmware_would_misread(ssid, password, match):
    r = robot()
    with pytest.raises(ValueError, match=match) as e:
        r.setup_wifi(ssid, password)
    assert r.transport.written == []
    assert password not in str(e.value) and PW not in str(e.value)


class NotAStream(Transport):
    def command(self, token, payload, timeout):
        raise AssertionError("must not send")

    def close(self):
        pass


def test_setup_wifi_needs_a_serial_link():
    with pytest.raises(RobotError, match="USB"):
        Robot(NotAStream()).setup_wifi("Home", PW)
```

Add to `python/tests/test_serial.py` (round trip through the real `SerialTransport`; add `import threading` and `from petoi.robot import Robot`):

```python
def test_setup_wifi_reads_through_the_reboot_over_loopback():
    port = serial.serial_for_url("loop://", timeout=0.1)
    robot = Robot(SerialTransport(port=port, boot_timeout=0))
    ip = b"Successfully connected Wifi to IP Address: 192.168.1.23\r\n"
    reboot = ip + b"Rebooting to use web server.\r\n\xff\x00ets Jun  8 2016\r\n" + ip + b"Ready!\r\n"
    timer = threading.Timer(0.2, port.write, [reboot])  # after setup_wifi has discarded and written
    timer.start()
    try:
        assert robot.setup_wifi("Home", "pw-12345", timeout=3) == "192.168.1.23"
    finally:
        timer.cancel()
```

Create `python/tests/hardware/test_wifi_setup.py`:

```python
import os
import warnings

import pytest

import petoi

PORT = os.environ.get("PETOI_PORT")
SSID = os.environ.get("PETOI_WIFI_SSID")
PASSWORD = os.environ.get("PETOI_WIFI_PASSWORD", "")

pytestmark = [
    pytest.mark.hardware,
    pytest.mark.skipif(not (PORT and SSID), reason="set PETOI_PORT, PETOI_WIFI_SSID and PETOI_WIFI_PASSWORD"),
]


def test_wrong_password_fails_without_leaking_it():  # runs first: once joined, the robot ignores new details
    bad = "petoi-wrong-password"
    with petoi.connect(PORT) as robot:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            try:
                robot.setup_wifi(SSID, bad)
            except petoi.WifiSetupFailed as e:
                assert bad not in str(e) and bad[-4:] not in str(e)
                return
    pytest.skip("robot is already on Wi-Fi; hold its BOOT button to clear it to run this test")


def test_setup_wifi_then_connect_over_wifi():
    with petoi.connect(PORT) as robot:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)  # already on Wi-Fi from an earlier run is fine
            ip = robot.setup_wifi(SSID, PASSWORD)
        print(f"\nrobot joined {SSID!r} at {ip}")
        assert robot.info()["model"]  # same USB connection still works after the reboot (open question 1)
    with petoi.connect(ip) as wifi:
        assert wifi.info()["model"]
```

**Implementation**

`python/src/petoi/errors.py` (append):

```python
class WifiSetupFailed(RobotError):
    """The robot could not join the Wi-Fi network."""
```

`python/src/petoi/__init__.py`: import `WifiSetupFailed` from `petoi.errors` and add `"WifiSetupFailed"` to `__all__`, keeping it alphabetical.

`python/src/petoi/robot.py`:

```python
# imports (merge with existing)
import re
import threading
import time
import warnings
from typing import Dict, Iterator, List, Literal, Optional, Sequence, Tuple, Union

from petoi.errors import RobotError, RobotTimeout, WifiSetupFailed
from petoi.transports.base import StreamTransport, Transport
from petoi.transports.serial import READY

# module constants, after _DIRECTIONS
_WIFI_JOINED = re.compile(r"Successfully connected Wifi to IP Address: (\S+)")  # src/reaction.h:465, src/webServer.h:622
_WIFI_ALREADY = re.compile(r"Wifi already connected to IP Address: (\S+)")  # src/reaction.h:485
_WIFI_FAILED = "Fail to connect Wifi!"  # USB only (src/reaction.h:477)
_UNDEFINED = "Undefined token!"  # firmware built without WEB_SERVER (src/reaction.h:1535)
```

New section in `Robot`, placed before `close()`:

```python
    # --- Wi-Fi ------------------------------------------------------------

    def setup_wifi(self, ssid: str, password: str, timeout: float = 60.0) -> str:
        """Over USB, put the robot on a 2.4 GHz Wi-Fi network and return its IP address for petoi.connect()."""
        _check_wifi(ssid, password)
        transport = self.transport
        if not isinstance(transport, StreamTransport):
            raise RobotError("setup_wifi() works over the USB cable; connect with petoi.connect() first")
        payload = f"w%{ssid}%{password}\n".encode()  # src/reaction.h:442-446
        deadline = time.monotonic() + timeout
        ips: List[str] = []
        already: Optional[str] = None
        failed = False
        with self._lock:
            transport.discard_input()
            transport._unconfirmed.clear()  # the robot reboots; nothing sent earlier will echo now
            transport.write(payload)
            # Never keep or show robot lines: they include the password's last 4 characters (src/reaction.h:449-458).
            for line in _lines(transport, deadline):
                joined, found = _WIFI_JOINED.search(line), _WIFI_ALREADY.search(line)
                if joined:
                    ips.append(joined.group(1))  # once before the reboot, again when it rejoins at boot
                elif ips:
                    if line == READY:
                        if len(ips) > 1:
                            return ips[-1]
                        raise WifiSetupFailed(f"the robot joined {ssid!r} but could not rejoin after rebooting; try again")
                elif found:
                    already = found.group(1)
                elif _WIFI_FAILED in line:
                    failed = True
                elif line == _UNDEFINED:
                    raise RobotError("this robot's firmware has no Wi-Fi support; update it with the Petoi Desktop App")
                elif line == "w":  # echoed only when it did not reboot (src/reaction.h:1557)
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
        if ips:
            warnings.warn(f"the robot joined Wi-Fi but did not finish rebooting within {timeout:g}s",
                          RuntimeWarning, stacklevel=2)
            return ips[-1]
        raise RobotTimeout(f"robot did not report a Wi-Fi result within {timeout:g}s; check power and the USB cable")
```

Module-level helpers, after `_degrees`:

```python
def _check_wifi(ssid: str, password: str) -> None:
    if not 1 <= len(ssid.encode()) <= 32:
        raise ValueError("ssid must be 1 to 32 bytes long")  # WiFi.begin rejects others (arduino-esp32 WiFiSTA.cpp:231)
    if "%" in ssid:
        raise ValueError("ssid cannot contain '%': the firmware ends the name at it (src/reaction.h:442)")
    if len(password.encode()) > 64:
        raise ValueError("password is longer than 64 bytes")  # WiFiSTA.cpp:236; never echo the password
    for name, value in (("ssid", ssid), ("password", password)):
        if any(c in value for c in "\r\n\0"):
            raise ValueError(f"{name} cannot contain a line break or NUL character")


def _lines(transport: StreamTransport, deadline: float) -> Iterator[str]:
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        line = transport.readline(remaining)
        if line is not None:
            yield line.strip()
```

The existing `test_every_public_method_has_a_docstring` covers the new method.

**Docs**

`python/README.md`: add a subsection under "Connecting", after "Old firmware":

````markdown
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

- It takes up to a minute: the robot tries the network up to 3 times, then reboots to start its Wi-Fi server. `setup_wifi()` returns once it is back.
- The robot remembers the network and joins it every time it starts.
- 2.4 GHz networks only. The name is 1 to 32 bytes and cannot contain `%`. The password is up to 64 characters; use `""` for an open network.
- A wrong name or password raises `petoi.WifiSetupFailed`. Your password never appears in error messages (the robot's own serial monitor shows its last 4 characters).
- If the robot is already on Wi-Fi it ignores the new details, and `setup_wifi()` returns its current address with a warning. To switch networks, hold the robot's BOOT button for about 3 seconds to clear the saved one, then run `setup_wifi()` again.
- USB only: over Bluetooth the reboot drops the link.
````

Other README changes:

- **High-level methods table:** add the row ``| `setup_wifi(ssid, password)` | Over USB, put the robot on Wi-Fi; returns its IP address for `connect()` |``.
- **Errors section:** add "`setup_wifi()` raises `petoi.WifiSetupFailed` (a `RobotError`) when the robot cannot join the network."
- **Troubleshooting:** extend the Wi-Fi bullet with "Not on Wi-Fi yet? See 'Putting the robot on Wi-Fi'."

`python/TODO.md`:

- Mark "Wi-Fi setup from Python" done, pointing to this amendment.
- Under "Needs a real robot", add `PETOI_WIFI_SSID=... PETOI_WIFI_PASSWORD=... pytest tests/hardware/test_wifi_setup.py -v -s`. This checks that the USB link survives `ESP.restart()`, the reboot time, and the BOOT-button reset.
- Add the follow-ups: a `petoi wifi` CLI with `getpass`, and `wifi_ip()` using a bare `w`.

**Verify**

- `cd python && .venv/bin/python -m pytest -q tests/test_robot.py tests/test_serial.py -k wifi`: expect 21 passed (12 test functions, 2 + 8 parametrized cases, plus the loopback test). Before the implementation they fail with `ImportError: cannot import name 'WifiSetupFailed'`.
- `cd python && .venv/bin/python -m pytest -q -W error::DeprecationWarning`: expect the whole suite to pass, with hardware tests skipped and no failures.
- `grep -n "password" python/src/petoi/robot.py`: `password` should appear only in the signature, `payload`, and `_check_wifi`. No f-string message may interpolate it.
- Hardware (merge gate): `cd python && PETOI_PORT=/dev/cu.usbserial-XXXX PETOI_WIFI_SSID=MyHomeWiFi PETOI_WIFI_PASSWORD=... .venv/bin/python -m pytest tests/hardware/test_wifi_setup.py -v -s`.
  - Expected: `test_wrong_password_fails_without_leaking_it PASSED` after about 34 s. It is SKIPPED if the robot is already on Wi-Fi.
  - Then `robot joined 'MyHomeWiFi' at 192.168.x.x` and `test_setup_wifi_then_connect_over_wifi PASSED`.
  - That resolves open questions 1 and 5. Record the measured reboot time in `TODO.md`.

### Critical Files for Implementation
- /Users/kaikai/projects/petoi codes/OpenCatEsp32-Quadruped-Robot - python-api/python/src/petoi/robot.py
- /Users/kaikai/projects/petoi codes/OpenCatEsp32-Quadruped-Robot - python-api/python/src/petoi/errors.py
- /Users/kaikai/projects/petoi codes/OpenCatEsp32-Quadruped-Robot - python-api/python/tests/test_robot.py
- /Users/kaikai/projects/petoi codes/OpenCatEsp32-Quadruped-Robot - python-api/src/reaction.h (lines 436-490, 1535, 1557)
- /Users/kaikai/projects/petoi codes/OpenCatEsp32-Quadruped-Robot - python-api/src/webServer.h (lines 554-636, 674-684)
---

## Part B

### Amendment: upload and run a custom skill (`K` token) (proposed)

I only read code for this. Nothing was edited or run, and no tests were run.

**Firmware facts**

*Reading the bytes*
- `K` is `T_SKILL_DATA` (`src/OpenCat.h:338`). Uppercase tokens end at `~` (`src/moduleManager.h:400`), and the code's own comment warns that an angle of 126 "may introduce bug" (`:401`).
- `K` gets the long inter-byte timeout: `SERIAL_TIMEOUT_LONG` is 200 ms, against 10 ms for other tokens (`src/moduleManager.h:402`, `src/OpenCat.h:68-69`).
- How the serial loop ends a command:
  - The inner loop reads every available byte without looking at it (`src/moduleManager.h:420-423`).
  - The outer loop stops when the *last byte read so far* is `~`, or after 200 ms of silence (`:428`).
  - So a 126 inside the data ends the command early only if it happens to be the last byte in the buffer at that moment. The result depends on timing. Nothing clamps 126 and nothing forbids it.
  - BLE does the same check per write (`src/bleUart.h:78`).
  - The Wi-Fi `b64:` path copies the decoded bytes and never looks for `~`, so 126 is harmless there (`src/webServer.h:384-398`).
- Lowercase tokens and `X`/`R`/`W` get `\r`/`\n` stripped. `K` does not, so bytes 10 and 13 are safe (`src/moduleManager.h:430`).

*Buffer size*
- The buffer is `BUFF_LEN` 2507 bytes, commented as "125*20+7" (`src/OpenCat.h:443-444`). Serial reports `OVF` past `BUFF_LEN` for any token (`src/moduleManager.h:409`).
- `spaceAfterStoringData` only limits *later* `k`/`i`/`m` commands, not `K` itself (`:409`).
- After building a skill, its angles are stored at the end of the buffer and `spaceAfterStoringData = BUFF_LEN - angleLen - 1`. The firmware prints `LMT` when that is less than `CMD_LEN` (20) (`src/skill.h:128-140`, `src/OpenCat.h:438`).
  - Example: after a 125-frame behavior only 6 bytes are left, so the next `kbalance\n` triggers `OVF`, and `OVF` makes the robot run `up` (`src/moduleManager.h:409-418`).
- Exactly 2507 data bytes would make the firmware write `newCmd[2508]`, one byte past its 2508-byte buffer (`src/moduleManager.h:446`).
- BLE and Wi-Fi do no bounds check at all (`src/bleUart.h:67`, `src/webServer.h:389-392`).

*Data layout* (`buildSkill`/`dataLen`/`formatSkill`, `src/skill.h:111-157`, `src/configConstants.h:58-66`)
- Byte 0 is the frame count `period` (int8): 1 = posture, >1 = gait, <0 = behavior.
- Bytes 1-2 are the expected roll and pitch (`:148`). Byte 3 is the angle ratio, which multiplies every angle (`:153`, `:417`).
  - Every Instinct array uses 1 or 2, and `convertTargetToPosture` picks 1 or 2 (`:264-273`).
- Behaviors add 3 loop bytes: start row, end row, cycles (`:155-157`). The header is 4 bytes, or 7 for a behavior.
- Frame width:
  - Posture: `DOF` = 16.
  - Gait: `WALKING_DOF`, which is 8 on Nybble/Bittle and 12 otherwise (`src/OpenCat.h:249-256`).
  - Behavior: `DOF+4` = 20.
- The 4 extra behavior columns:
  - speed: `/8` is degrees per step, and 0 means jump (`src/skill.h:324`, `src/motion.h:178`);
  - pause: ×50 ms (`src/skill.h:355`);
  - gyro trigger axis and angle, which wait up to 2 s (`:326-342`).
- Each interpolation step takes `delay((DOF-offset)/2)`, which is 8 ms (`src/motion.h:203`).
- Loops: `repeat = cycles in {0,1} ? 0 : cycles-1`, and a **negative count loops forever** (`src/skill.h:282`). The loop jumps back when `c != 0 && c == end` (`:357-363`), so rows start..end run `cycles` times in total.
- The `hi` sample in `src/InstinctBittleESP.h:2109-2113` is `[-5,0,0,1, 1,2,3, 5×20]`, which is exactly the tester's sample.

*Running and echoes*
- The `K` case does three things (`src/reaction.h:1400-1418`):
  - saves the data to NVS (`config.putBytes("tmp", …)`, `:1409-1410`; `I2C_EEPROM_ADDRESS` is commented out, `src/OpenCat.h:86`);
  - builds the skill;
  - moves to frame 0 (`:1413`).
- `token` stays `K`, because `resetCmd` keeps it (`src/tools.h:204`). The code after the switch then:
  - echoes `K` straight away (`src/reaction.h:1555-1557`);
  - runs `skill->perform()` because `tolower('K') == 'k'` (`:1575-1580`).
- So the echoes differ by type:
  - **Posture:** `K` once the posture is reached.
  - **Gait:** `K` once frame 0 is reached; the gait then loops until the next command.
  - **Behavior:** `K` twice, once as it starts and again when it ends (`:1609`). Between them the behavior is converted to a held posture (`:1605`).
- Over Wi-Fi the task completes at the first echo (`:1565`), and `cmdFromWeb` is cleared (`src/webServer.h:489`), so the end echo never reaches Wi-Fi.
- Serial input during a behavior interrupts it, then the robot runs `up` (`src/skill.h:288-319`, `src/reaction.h:1603`).
- `T` replays the stored data: it echoes `T` (`src/reaction.h:1384-1399`), then `k`.

*Where the data comes from*
- The comments say SkillComposer skills are imported into `InstinctX.h` (`src/voice.h:17`) and that `T` replays "the last skill data sent by the Skill Composer" (`src/voice.h:52`).
- I checked every array in the Bittle, Bittle-arm and Nybble Instinct files against the proposed validation: none fail it, and none contain 126.

**Open questions / UNVERIFIED**
1. **Serial pacing.** The tester sends 20-byte slices with 1 ms gaps. The ESP32 UART receive buffer size is not in this repo (arduino-esp32 defaults to 256 B, UNVERIFIED). The plan sends one unpaced write; the hardware test sends 2487 bytes to check it.
2. **CUB gait width.** `dataLen` uses `WALKING_DOF` = 12, but `InstinctCubESP.h` gaits are 8 wide. So 8 and 12 are both accepted unless the model reports Bittle or Nybble. What CUB reports to `?` is UNVERIFIED.
3. **Wi-Fi timing.** UNVERIFIED that `sendSocketResponse` sends before the blocking `perform()`. Also UNVERIFIED: zero bytes surviving `String += char(0)` in `base64Decode` (`src/webServer.h:126`); the tester sends zeros this way, so it probably works.
4. **Duration estimate.** The cost of `calibratedPWM` per step has not been measured. The `1.5×` factor plus `robot.timeout` is a guessed margin.
5. **Suppressed first echo.** If a `k wkF 3`-style command sent with `send()` left `deferSkillTokenEcho` set (`src/reaction.h:1478`, `:1513`), the first `K` echo is suppressed (`:1556`) and postures and gaits would time out.
6. **Gyro during behaviors.** The name `tmp` is not on the gyro-off list (`src/skill.h:284`), so a flip during an uploaded behavior interrupts it. Not seen on a robot.
7. **Skill Composer export format** (`.md`) is not in this repo, so there is no parser (see Decisions).
8. **Flash wear.** Every upload writes NVS (`src/reaction.h:1410`). Uploading in a tight loop wears the flash.

**Decisions**
- **API:** `Robot.run_skill_data(data, wait=True, timeout=None) -> Reply`. The name follows the brief because the skill runs immediately.
- **Validation happens before sending** and raises `ValueError`:
  - header too short;
  - any value outside int8;
  - 126, reported with its index;
  - frame count 0;
  - angle ratio not 1 or 2;
  - length not equal to header + frames × width;
  - more than 2486 angle bytes. That is `BUFF_LEN-1-CMD_LEN`, which keeps room for the next `k` command and avoids the 2507 off-by-one. In practice it means at most 124 behavior frames.
  - a negative loop count;
  - loop rows out of range when cycles ≥ 2.
- **Waiting for behaviors (serial, Bluetooth, BLE):** wait for both echoes. This needs a new `StreamTransport.expect(token, timeout)`, split out of `command()`; `command()` keeps its behavior.
  - With `wait=False`, both echoes are marked as owed, so they are swallowed later instead of confirming a newer command.
- **Wi-Fi:** returns at the first echo, which is a firmware limit. This is documented.
- **Timeout:** the user's `timeout`, or by default:
  - postures and gaits: `robot.timeout`;
  - behaviors: `robot.timeout + 1.5 × estimate`. The estimate adds pauses, 8 ms steps from frame-to-frame angle changes ÷ speed, 2 s per gyro trigger, and loop repeats.
- **Mock:** echoes a behavior twice, as the firmware does.
- **Rejected alternatives:**
  - Silently clamping 126 to 125: it changes the user's data.
  - Allowing 126 over Wi-Fi only: the rules would differ per link.
  - 20 B / 1 ms pacing: the firmware reads until `~` with a 200 ms gap tolerance, there is no evidence pacing is needed, and the hardware test settles it.
  - A fixed 30 s timeout like the tester: it is too short for long behaviors and too long for quick ones.
  - Parsing Skill Composer files: the format cannot be checked from this repo.
  - Putting the layout checks in `encode`: `encode` handles every token generically.
  - A `T` replay method: it echoes two different tokens; that can be a follow-up.

**Files**
- Modify `/Users/kaikai/projects/petoi codes/OpenCatEsp32-Quadruped-Robot - python-api/python/src/petoi/robot.py`
- Modify `/Users/kaikai/projects/petoi codes/OpenCatEsp32-Quadruped-Robot - python-api/python/src/petoi/transports/base.py`
- Modify `/Users/kaikai/projects/petoi codes/OpenCatEsp32-Quadruped-Robot - python-api/python/src/petoi/transports/mock.py`
- Modify `/Users/kaikai/projects/petoi codes/OpenCatEsp32-Quadruped-Robot - python-api/python/tests/test_robot.py`, `tests/test_stream.py`, `tests/test_mock.py`, `tests/hardware/test_smoke.py`
- Modify `/Users/kaikai/projects/petoi codes/OpenCatEsp32-Quadruped-Robot - python-api/python/README.md` and `python/TODO.md` (move the "Upload a custom skill" candidate under hardware checks)
- Append this amendment to `/Users/kaikai/projects/petoi codes/OpenCatEsp32-Quadruped-Robot - python-api/docs/superpowers/plans/2026-10-27-python-api.md`

**Tests** (write these first and watch them fail with `AttributeError`)

Append to `tests/test_robot.py` (add `from petoi.protocol import encode` and `from petoi.robot import _behavior_seconds`):
```python
UP = [0, 0, 0, 0, 0, 0, 0, 0, 30, 30, 30, 30, 30, 30, 30, 30]  # Bittle "up" (src/InstinctBittleESP.h:1898-1900)
POSTURE = [1, 0, 0, 1] + UP
STILL = UP + [8, 0, 0, 0]  # speed 8/8 = 1 degree a step, no pause, no gyro trigger
HEAD = [30] + UP[1:] + [8, 0, 0, 0]


def behavior(*frames, loop=(0, 0, 0)):
    return [-len(frames), 0, 0, 1, *loop] + [v for f in frames for v in f]


def test_skill_data_is_sent_as_one_binary_command():
    r = robot()
    assert r.run_skill_data(POSTURE).completed
    assert r.transport.written == [b"K\x01\x00\x00\x01" + bytes(UP) + b"~"]


@pytest.mark.parametrize("width", [8, 12])
def test_gait_frames_may_be_8_or_12_wide(width):
    r = robot()
    r.run_skill_data([2, 0, 0, 1] + [10] * (2 * width))
    assert r.transport.written[-1] == encode("K", 2, 0, 0, 1, *([10] * (2 * width)))


def test_bittle_gait_must_be_8_wide():
    r = robot()
    r.model = "Bittle X"
    with pytest.raises(ValueError, match="needs 20 values"):
        r.run_skill_data([2, 0, 0, 1] + [10] * 24)


def test_behavior_waits_for_its_second_echo():
    data = behavior(STILL, HEAD, STILL)
    r = robot({encode("K", *data): ["K", "note", "K"]})
    reply = r.run_skill_data(data)
    assert reply.completed and reply.lines == ["note"]


def test_behavior_without_end_echo_raises():
    data = behavior(STILL, HEAD)
    r = robot({encode("K", *data): ["K"]})  # started, never finished
    with pytest.raises(RobotTimeout, match="uploaded skill"):
        r.run_skill_data(data)


def test_behavior_wait_false_owes_both_echoes():
    r = robot(auto_echo=False)
    r.run_skill_data(behavior(STILL, HEAD), wait=False)
    r.transport.replies[b"ksit\n"] = ["K", "K", "k"]  # both late K echoes arrive during the next command
    assert r.sit().lines == []


@pytest.mark.parametrize(
    "data, message",
    [
        ([1, 0, 0], "header"),
        ([0, 0, 0, 1], "cannot be 0"),
        ([1, 0, 0, 3] + UP, "angle ratio"),
        ([1, 0, 0, 1] + UP[:-1], "needs 20 values"),
        ([2, 0, 0, 1] + [0] * 20, "needs 20 or 28 values"),
        (behavior(STILL, loop=(0, 0, -1)), "forever"),
        (behavior(STILL, STILL, loop=(0, 2, 3)), "loop rows"),
        ([1, 0, 0, 1] + UP[:-1] + [126], "126 at index 19"),
        ([1, 0, 0, 1] + UP[:-1] + [200], "int8"),
        (behavior(*[STILL] * 125), "too long"),
        (["1", 0, 0, 1] + UP, "integers"),
    ],
)
def test_skill_data_rejects_what_the_robot_would_misread(data, message):
    r = robot()
    with pytest.raises(ValueError, match=message):
        r.run_skill_data(data)
    assert r.transport.written == []


def test_behavior_time_counts_pauses_and_loops():
    pause = UP + [0, 20, 0, 0]  # jump, then 20 x 50 ms = 1 s (src/skill.h:355)
    assert 2.0 <= _behavior_seconds(behavior(pause, pause)) < 2.1
    assert 6.0 <= _behavior_seconds(behavior(pause, pause, loop=(0, 1, 3))) < 6.1  # rows 0-1 run three times
```
Append to `tests/test_stream.py`:
```python
def test_expect_waits_for_another_echo_without_writing():
    s = FakeStream(auto_echo=False)
    s.pending = ["moving", "K"]
    reply = s.expect("K", timeout=0.05)
    assert reply.completed and reply.lines == ["moving"] and s.written == []


def test_expect_zero_timeout_marks_the_echo_owed():
    s = FakeStream(auto_echo=False)
    s.expect("K", timeout=0)
    s.replies[b"ksit\n"] = ["K", "k"]
    reply = s.command("k", b"ksit\n", timeout=0.05)
    assert reply.completed and reply.lines == []
```
Append to `tests/test_mock.py`:
```python
def test_mock_echoes_a_behavior_twice_like_the_firmware():
    r = Robot(MockTransport())
    assert r.run_skill_data([-1, 0, 0, 1, 0, 0, 0] + [0] * 20).completed
    assert r.info()["model"] == MockTransport.MODEL
```
Append to `tests/hardware/test_smoke.py` (add `from petoi.transports.base import StreamTransport`):
```python
def _standing(robot):
    robot.stand()
    angles = robot.joints()
    assert len(angles) == 16 and all(-125 <= a <= 125 for a in angles), angles
    return angles


def test_uploaded_posture_turns_the_head(robot):
    angles = _standing(robot)
    angles[petoi.Joint.HEAD_PAN] = 20
    robot.run_skill_data([1, 0, 0, 1] + angles)
    scenario.wait_for_angle(robot, petoi.Joint.HEAD_PAN, 20)
    robot.stand()


def test_uploaded_behavior_returns_after_it_finishes(robot):
    angles = _standing(robot)
    look = list(angles)
    look[petoi.Joint.HEAD_PAN] = 30
    frames = [angles + [8, 10, 0, 0], look + [8, 10, 0, 0], angles + [8, 0, 0, 0]]  # two 500 ms pauses
    start = time.monotonic()
    robot.run_skill_data([-3, 0, 0, 1, 0, 0, 0] + [v for f in frames for v in f])
    if isinstance(robot.transport, StreamTransport):  # Wi-Fi returns as it starts (src/reaction.h:1565)
        assert time.monotonic() - start >= 1.0
    assert robot.info()["model"] == robot.model  # no leftover K echo
    robot.stand()


def test_largest_upload_arrives_intact(robot):
    angles = _standing(robot)
    last = list(angles)
    last[petoi.Joint.HEAD_PAN] = 20
    frames = [angles + [0, 0, 0, 0]] * 123 + [last + [0, 0, 0, 0]]  # 124 frames, 2487 bytes, speed 0 = jump
    robot.run_skill_data([-124, 0, 0, 1, 0, 0, 0] + [v for f in frames for v in f])
    scenario.wait_for_angle(robot, petoi.Joint.HEAD_PAN, 20)  # lost bytes would misalign the last frame
    robot.skill(Skill.BALANCE)  # "kbalance" must still fit (src/skill.h:131-137)
```

**Implementation**

`transports/base.py`: replace `StreamTransport.command` with:
```python
    def command(self, token: str, payload: bytes, timeout: float) -> Reply:
        # The protocol has no command IDs and one-shot skills echo only when
        # finished, so a late echo from an earlier command can arrive now.
        pending = self._unconfirmed
        now = time.monotonic()
        pending[:] = [(t, exp) for t, exp in pending if exp > now]
        if not pending:
            self.discard_input()  # nothing is owed, so anything buffered is junk
        self.write(payload)
        return self.expect(token, timeout)

    def expect(self, token: str, timeout: float) -> Reply:
        """Wait for one more echo of token without sending; timeout=0 only marks it as owed."""
        pending = self._unconfirmed
        entry = (token, time.monotonic() + STALE_SECONDS)
        if not timeout:
            pending.append(entry)
            return Reply(token)
        deadline = time.monotonic() + timeout
        consumed_own = False
        # ... existing next_line(), collect_reply() and re-append logic, unchanged ...
```
`transports/mock.py`: in `write`, before the final `self._out.append(token)`:
```python
        elif token == "K" and args and args[0] < 0:
            self._out.append(token)  # a behavior echoes when it starts and when it ends (src/reaction.h:1557, :1609)
```
`robot.py`: add `import operator`, change the import to `from petoi.transports.base import StreamTransport, Transport`, and add:
```python
_SKILL_ROOM = 2507 - 1 - 20  # BUFF_LEN - 1 - CMD_LEN: leaves room for the next k command (src/OpenCat.h:438, :443; src/skill.h:131-137)
```
Method, after `skill()`:
```python
    def run_skill_data(self, data: Sequence[int], wait: bool = True, timeout: Optional[float] = None) -> Reply:
        """Upload a skill array in the Instinct*.h layout and run it; waits until a behavior ends."""
        try:
            values = [operator.index(v) for v in data]
        except TypeError:
            raise ValueError("skill data must be integers") from None
        bittle_like = any(n in (self.model or "").lower() for n in ("bittle", "nybble"))
        _check_skill_data(values, (8,) if bittle_like else (8, 12))  # WALKING_DOF (src/OpenCat.h:249-256)
        payload = encode("K", *values)
        # a behavior echoes K as it starts and again when it ends (src/reaction.h:1557, :1609); Wi-Fi sees only the first (:1565)
        stream = self.transport if values[0] < 0 and isinstance(self.transport, StreamTransport) else None
        if timeout is None:
            timeout = self.timeout + (1.5 * _behavior_seconds(values) if stream is not None else 0)
        with self._lock:
            reply = self.transport.command("K", payload, (self.timeout if stream is not None else timeout) if wait else 0)
            if stream is not None and (reply.completed or not wait):
                end = stream.expect("K", timeout if wait else 0)
                reply = Reply("K", reply.lines + end.lines, end.completed)
        if wait and not reply.completed:
            raise RobotTimeout("robot did not confirm the uploaded skill in time; check power and the connection, or pass a longer timeout")
        return reply
```
Helpers at the bottom of the module:
```python
def _check_skill_data(values: List[int], gait_widths: Tuple[int, ...]) -> None:
    # layout: src/skill.h:118-126, :144-157
    if len(values) < 4:
        raise ValueError("skill data needs a header: frames, roll, pitch, angle ratio")
    for i, v in enumerate(values):
        if not -128 <= v <= 127:
            raise ValueError(f"value {v} at index {i} is outside the int8 range -128..127")
        if v == 126:
            raise ValueError(f"value 126 at index {i} is the end marker '~' and could cut the skill short; use 125 or 127")
    period, ratio = values[0], values[3]
    if period == 0:
        raise ValueError("frame count (first value) cannot be 0: 1 is a posture, more a gait, negative a behavior")
    if ratio not in (1, 2):
        raise ValueError(f"angle ratio (fourth value) must be 1 or 2, got {ratio}")
    header, frames = (4 if period > 0 else 7), abs(period)
    widths = (16,) if period == 1 else gait_widths if period > 1 else (20,)
    body = len(values) - header
    if body not in [frames * w for w in widths]:
        kind = "posture" if period == 1 else "gait" if period > 1 else "behavior"
        need = " or ".join(str(header + frames * w) for w in widths)
        raise ValueError(f"a {kind} with {frames} frames needs {need} values, got {len(values)}")
    if body > _SKILL_ROOM:
        raise ValueError(f"skill data is too long: {body} angle values, the robot keeps at most {_SKILL_ROOM}")
    if period < 0:
        start, end, cycles = values[4:7]
        if cycles < 0:
            raise ValueError("a loop count (seventh value) below 0 loops forever (src/skill.h:282); use 0 or 1 for no loop")
        if cycles >= 2 and not 0 <= start <= end < frames:
            raise ValueError(f"loop rows {start}..{end} must lie within the {frames} frames")


def _behavior_seconds(values: List[int]) -> float:
    """Rough run time of a valid behavior (src/skill.h:280-363, src/motion.h:178-203)."""
    frames, ratio = -values[0], values[3]
    start, end, cycles = values[4:7]
    rows = [values[7 + 20 * k : 27 + 20 * k] for k in range(frames)]
    order = list(range(frames))
    if cycles >= 2 and end > 0:  # rows start..end run `cycles` times
        order = list(range(end + 1)) + list(range(start, end + 1)) * (cycles - 1) + list(range(end + 1, frames))
    seconds, previous = 0.0, rows[order[0]]  # the robot is already at frame 0 (src/reaction.h:1413)
    for k in order:
        row = rows[k]
        diff = ratio * max(abs(a - b) for a, b in zip(row[:16], previous[:16]))
        steps = round(diff / (row[16] / 8)) if row[16] > 0 else 0
        seconds += (steps + 1) * 0.008 + abs(row[17]) * 0.05 + (2.0 if row[18] else 0.0)
        previous = row
    return seconds
```

**Docs** (README)

Methods table row:
`| run_skill_data(data) | Upload and run your own skill array (see "Custom skills") |`

New section after "High-level methods":
```markdown
## Custom skills

`run_skill_data(data)` sends a skill array in the layout of the firmware's `src/Instinct*.h` files (Skill Composer skills use it too), runs it, and returns when it is done:

    up = [0, 0, 0, 0, 0, 0, 0, 0, 30, 30, 30, 30, 30, 30, 30, 30]   # Bittle's "up"
    look = [30] + up[1:]                                               # head turned
    robot.run_skill_data([1, 0, 0, 1] + look)                          # a posture
    robot.run_skill_data([-2, 0, 0, 1, 0, 0, 0] + look + [8, 10, 0, 0] + up + [8, 0, 0, 0])  # a behavior

- Header: frame count (1 posture, more than 1 gait, negative behavior), expected roll, expected pitch, angle ratio (1, or 2 to double every angle). A behavior adds three loop values: start row, end row, and how many times those rows run.
- Frames: 16 angles for a posture; 8 for a gait on Bittle and Nybble (12 on other models); for a behavior, 16 angles plus speed (8 = 1 degree per step, 0 = jump), pause (×50 ms), and two gyro trigger values (0, 0 for none).
- Postures return once reached and gaits once started (they keep going until `stop()`). Behaviors return when finished; over Wi-Fi, a behavior returns as it starts.
- Rejected before sending: a length that doesn't match the header, values outside -128..127, the value 126 (it is the end marker `~`; use 125 or 127), a negative loop count (it would loop forever), and more than 124 behavior frames.
- The robot also saves each upload to flash, so avoid uploading in a tight loop.
```

**Verify**
- `cd "/Users/kaikai/projects/petoi codes/OpenCatEsp32-Quadruped-Robot - python-api/python" && .venv/bin/python -m pytest -q`: every test passes (the existing ones plus about 23 new cases) with 0 failures. Before the implementation, the new tests fail with `AttributeError` (`run_skill_data` / `expect`).
- `.venv/bin/python -m pytest -q tests/test_stream.py`: all existing stream tests still pass, so the `command()` → `expect()` split changed nothing.
- On hardware: `PETOI_PORT=/dev/cu.usbserial-XXXX .venv/bin/python -m pytest tests/hardware -v -s -k "uploaded or largest"`, then again with `PETOI_BLE` and `PETOI_WS`. Expected: 3 passed per link.
  - If `test_largest_upload_arrives_intact` fails on USB, that settles Open question 1: add paced writes to `SerialTransport`.

### Critical Files for Implementation
- /Users/kaikai/projects/petoi codes/OpenCatEsp32-Quadruped-Robot - python-api/python/src/petoi/robot.py
- /Users/kaikai/projects/petoi codes/OpenCatEsp32-Quadruped-Robot - python-api/python/src/petoi/transports/base.py
- /Users/kaikai/projects/petoi codes/OpenCatEsp32-Quadruped-Robot - python-api/python/src/petoi/transports/mock.py
- /Users/kaikai/projects/petoi codes/OpenCatEsp32-Quadruped-Robot - python-api/python/tests/test_robot.py
- /Users/kaikai/projects/petoi codes/OpenCatEsp32-Quadruped-Robot - python-api/src/reaction.h (lines 1400-1418, 1555-1612 for echo semantics)
---

## Part C

### Amendment: separate wait for one-shot skills (`skill_timeout`) (proposed)

**Firmware facts**
- A behavior has `period < 0`, a 7-byte header (`period, roll, pitch, angleDataRatio, loopStart, loopEnd, loopCycles`) and `|period|` rows of `DOF + 4 = 20` bytes each (`src/skill.h:118-126`, `:154-158`). A posture has `period == 1`, a 4-byte header and 16 angles. `DOF` is 16 (`src/OpenCat.h:249`).
- Before a behavior starts, `loadBySkillName` moves the robot to frame 0 at speed 1 (`src/skill.h:512` → `:260-262`).
- `perform()` loops over the rows. Each row does three things in order:
  - `transform(row, ratio, row[16] / 8.0)` (`src/skill.h:324`);
  - if `row[18] != 0`, an IMU-trigger wait that breaks after at most 2000 ms (`:326-353`, `:342`; only built with `GYRO_PIN`);
  - `delay(|row[17]| * 50)` ms (`:355`).
- The loop: `repeat = (0 <= loopCycles < 2) ? 0 : loopCycles - 1` (`:282`). When `c == loopEnd`, the frames from `loopStart` to `loopEnd` run again (`:357-362`). A negative cycle count loops forever.
- `transform()` timing: `steps = round(maxDiff / speedRatio)` (0 if the speed is 0) (`src/motion.h:176-178`). It then runs `steps + 1` iterations of `delay((DOF - offset) / 2)`, which is 8 ms for behaviors and postures (`:183`, `:203`).
- `runDelay` and `fineAdjust` affect gaits only (`src/reaction.h:1581-1588`), never behaviors.
- Echo timing differs by skill type:
  - Behaviors echo `k` after `perform()` returns (`src/reaction.h:1609`), and Wi-Fi is notified at the same moment (`:1612`).
  - Postures and gaits echo before `perform()` (`:1555-1565`), so gaits confirm when they start.
- Any byte arriving on serial, or a flip detected by the IMU, interrupts a behavior. It then loads `up` and still echoes `k` (`src/skill.h:308-319`, `src/reaction.h:1602-1609`).
- The Wi-Fi server aborts a task after 45 s (`src/webServer.h:53`, `:720-726`).

**Duration estimates (ESTIMATE, not measured)**
How the numbers were made: from the Instinct arrays using the rules above, starting from `up` (in brackets: starting from `rest`). Servo-write and loop overhead are ignored, so real times will be somewhat longer. An IMU-trigger frame adds up to 2 s.

| Skill | Bittle | Bittle arm | Nybble |
|---|---|---|---|
| SIT / STAND / BALANCE / STRETCH / BUTT_UP (postures) | ≤0.9 (≤1.2) | ≤0.8 (≤1.1) | ≤0.9 (≤1.1) |
| HI | 4.6 (4.9) | 4.4 | 4.5 |
| PUSH_UP | 4.6 (5.3) | 4.7 (5.3) | **7.0** |
| CHECK | 4.1 | 3.3 | 4.1 |
| PEE | 3.1 | 2.8 | 3.5 |
| SNIFF | 2.4 | 2.1 | 4.2 |
| SCRATCH | 2.7 | 2.9 | 3.0 |
| SLEEP | 0.3 | 0.4 | – |
| HIGH_FIVE | 4.7 (5.4) | **5.2** | 4.5 (5.2) |
| HANDSHAKE | **5.4** | 3.7 | 3.3 |
| ANGRY | 2.9 | 3.6 | 3.9 |
| BOXING | **6.3** | **6.1** | 4.9 (5.5) |
| CHEER | 2.8 | 3.6 | 3.4 |
| COME_HERE | 4.4 | 3.7 | 2.4 |
| DIG | 2.5 | 3.0 | 2.8 |
| GOOD_BOY | 1.6 | 2.7 | 3.5 |
| HANDSTAND | 3.6 | 3.8 | 4.7 (5.3) |
| HUG | **7.2** (7.9) | **6.8** | 4.8 (5.5) |
| HANDS_UP | **6.2** | **7.3** (7.8) | 4.8 (5.4) |
| HUNT | 2.3 | 2.3 | **10.1** (10.4) |
| KICK | 1.0 | 1.0 | 1.5 |
| NOD | 0.7 | 1.2 | 3.7 |
| PLAY_DEAD | **6.3** | **6.6** | **5.3** |
| RECOVER | 4.4 | **5.3** | 3.8 |
| TABLE | 3.9 | **5.0** | **6.2** |
| WAVE_HEAD | 1.1 | 1.7 | 2.3 |
| CLAP | **7.7** (8.4) | **7.9** (8.4) | – |
| JUMP | 0.8 | 0.9 | – |
| LEAP_OVER | 3.5 | 3.5 | – |
| MOONWALK | 4.4 | 4.6 | – |
| PUSH_UP_ONE_HAND | **8.6** (9.3) | **8.8** (9.3) | – |
| SHOW_OFF | 2.5 | 2.6 | – |
| BACK_FLIP | 2.5 (+2 s trigger cap = 4.5) | – | – |
| FRONT_FLIP | 1.8 (+2 = 3.8) | – | – |
| ROLL | 3.4 | – | – |
| WASH_FACE | – | – | **8.3** |

- Starting from `up`, 7 Bittle, 9 Bittle-arm and 5 Nybble skills exceed 5 s.
- The longest is Nybble `hunt` at about 10.4 s, which is under the 15 s stale window.
- No built-in skill loops forever.

**Open questions / UNVERIFIED**
- Per-step overhead is not in the model: 16 LEDC writes, the cos interpolation and the IMU task. Real durations are UNVERIFIED and probably longer.
- `angleLimit` clamping (`src/motion.h:8`) can shrink `maxDiff`. The model ignores it.
- The Petoi tester gives `pee` 30 s, but the estimate is 3–4 s. The reason is UNVERIFIED (perhaps older firmware or a different robot).
- Possible existing bug, not fixed here: over Wi-Fi, `wait=False` falls back to the transport's 5 s default (`python/src/petoi/transports/websocket.py:106`). A long skill with `wait=False` would then return incomplete after 5 s, and the next command would get "busy". This needs its own fix.
- The duration starts from whatever posture the robot is in. The hardware test standardises on `stand()` first.

**Decisions**
- **Chosen: (a).** Add `Robot.skill_timeout = 30.0`, used only by `skill()`. Also add an optional `timeout=` on `skill()` for custom or uploaded skills.
- Why 30 s:
  - about 3× the longest estimate;
  - at least `STALE_SECONDS` (15);
  - under Wi-Fi's 45 s abort, so Python reports its own timeout first;
  - the same figure Petoi's tester uses.
- `sit`, `stand`, `stop`, `walk`, `trot`, `crawl` and `back` call `_cmd("k", ...)` directly and keep `robot.timeout` (5 s):
  - gaits echo when they start;
  - postures take 1.2 s or less.
- `skill("wkF")` gets 30 s. That only slows failure detection. The success path is unchanged.
- The stale window needs no code change:
  - an entry expires at write time + 15 s;
  - after a 30 s timeout it is already expired, which is correct because no built-in skill is estimated to echo after 15 s;
  - a test now guards that estimate against changes to the headers.
- **Rejected (b), a per-skill table:**
  - it needs the model, which is `None` with `check_firmware=False`;
  - it misses servo overhead, trigger waits and the dependence on the starting posture;
  - it cannot cover arbitrary or uploaded names;
  - it goes stale with every firmware change.
  - The estimator is kept only as a test guard and as a hardware comparison.
- **Rejected (c), a list of known-long skills:** the estimates put about 20% of skills over 5 s, and the set differs by model. Arbitrary names would still fall back to 5 s.

**Files**
- Modify `/Users/kaikai/projects/petoi codes/OpenCatEsp32-Quadruped-Robot - python-api/python/src/petoi/robot.py`
- Modify `/Users/kaikai/projects/petoi codes/OpenCatEsp32-Quadruped-Robot - python-api/python/tests/test_robot.py`
- Modify `/Users/kaikai/projects/petoi codes/OpenCatEsp32-Quadruped-Robot - python-api/python/tests/test_constants.py`
- Modify `/Users/kaikai/projects/petoi codes/OpenCatEsp32-Quadruped-Robot - python-api/python/tests/hardware/test_smoke.py`
- Modify `/Users/kaikai/projects/petoi codes/OpenCatEsp32-Quadruped-Robot - python-api/python/README.md` (lines 71 and 175)
- Modify `/Users/kaikai/projects/petoi codes/OpenCatEsp32-Quadruped-Robot - python-api/python/TODO.md`
- Modify `/Users/kaikai/projects/petoi codes/OpenCatEsp32-Quadruped-Robot - python-api/docs/superpowers/plans/2026-10-27-python-api.md` (append this amendment)

**Tests (write first)**

`tests/test_robot.py` additions (add `from petoi.transports.base import STALE_SECONDS` to the imports):
```python
def recorded_timeouts(r):
    seen = []
    command = r.transport.command
    r.transport.command = lambda token, payload, timeout: seen.append(timeout) or command(token, payload, timeout)
    return seen


def test_skill_waits_skill_timeout_because_it_confirms_when_finished():
    r = robot()
    seen = recorded_timeouts(r)
    r.skill(Skill.CLAP)
    r.skill("anything")
    assert seen == [r.skill_timeout, r.skill_timeout]


def test_skill_timeout_can_be_overridden_per_call():
    r = robot()
    seen = recorded_timeouts(r)
    r.skill("myLongSkill", timeout=60)
    assert seen == [60]


@pytest.mark.parametrize(
    "call",
    [lambda r: r.sit(), lambda r: r.stand(), lambda r: r.stop(), lambda r: r.walk(),
     lambda r: r.trot("left"), lambda r: r.crawl(), lambda r: r.back("right")],
)
def test_gaits_and_postures_keep_the_short_timeout(call):
    r = robot()  # gaits echo when they start (src/reaction.h:1555-1565)
    seen = recorded_timeouts(r)
    call(r)
    assert seen == [0.2]


def test_skill_timeout_error_names_the_skill_limit():
    r = Robot(FakeStream({}, auto_echo=False), timeout=0.2, skill_timeout=0.3)
    with pytest.raises(RobotTimeout, match=r"within 0\.3s"):
        r.skill("hi")


def test_default_skill_timeout_fits_between_stale_window_and_wifi_abort():
    # at least the 15 s stale window, below the Wi-Fi server's 45 s task abort (src/webServer.h:53)
    assert STALE_SECONDS <= Robot(FakeStream()).skill_timeout < 45
```

`tests/test_constants.py` additions (add `import functools` and `from petoi.transports.base import STALE_SECONDS`):
```python
DOF = 16  # src/OpenCat.h:249


@functools.lru_cache(maxsize=None)
def skill_arrays(header):
    text = re.sub(r"//[^\n]*", "", (SRC / header).read_text())
    return {name: [int(v) for v in re.findall(r"-?\d+", body)]
            for name, body in re.findall(r"const int8_t (\w+)\[\] PROGMEM = \{(.*?)\};", text, re.S)}


def estimate_seconds(model, name, start="up"):
    """ESTIMATE of how long k<name> runs before it echoes; ignores servo-write time, counts IMU triggers at their 2 s cap."""
    arrays = skill_arrays(TABLES[model])
    posture = arrays[start]
    angles = [v * posture[3] for v in posture[4:4 + DOF]]

    def move(target, ratio, speed):  # transform(): steps+1 iterations of 8 ms (src/motion.h:176-203)
        diff = max(abs(a - t * ratio) for a, t in zip(angles, target))
        angles[:] = [t * ratio for t in target]
        return ((int(diff / speed + 0.5) if speed > 0 else 0) + 1) * DOF // 2

    data = arrays[name]
    period, ratio = data[0], data[3]
    if period == 1:  # posture
        return move(data[4:4 + DOF], ratio, 1) / 1000
    first, last, cycles = data[4:7]  # src/skill.h:155-158
    rows = [data[7 + k * (DOF + 4):7 + (k + 1) * (DOF + 4)] for k in range(-period)]
    ms = move(rows[0][:DOF], ratio, 1)  # loadBySkillName moves to frame 0 first (src/skill.h:512)
    repeat = 0 if 0 <= cycles < 2 else cycles - 1  # src/skill.h:282
    assert repeat >= 0, f"{name} loops until reset"
    c = 0
    while c < -period:  # src/skill.h:285-363
        row = rows[c]
        ms += move(row[:DOF], ratio, row[DOF] / 8) + abs(row[DOF + 1]) * 50 + (2000 if row[DOF + 2] else 0)
        if repeat and c and c == last:
            c, repeat = first - 1, repeat - 1
        c += 1
    return ms / 1000


def test_some_skills_outlast_the_default_command_timeout():
    assert estimate_seconds("bittle", "pu1") > 5 and estimate_seconds("nybble", "hunt") > 5


@pytest.mark.parametrize("model", TABLES)
def test_every_skill_is_estimated_to_echo_within_the_stale_window(model):
    worst = {s.value: max(estimate_seconds(model, s.value, p) for p in ("up", "rest"))
             for s in Skill if model in ONLY_ON.get(s, TABLES)}
    assert max(worst.values()) < STALE_SECONDS, worst
```
I dry-ran this logic through stdin: worst case 10.404 s (Nybble `hunt` from `rest`).

`tests/hardware/test_smoke.py`: replace `test_every_skill_completes` (add `from petoi.transports.base import STALE_SECONDS` and `from test_constants import estimate_seconds`):
```python
@pytest.mark.parametrize("skill", list(Skill))
def test_every_skill_completes(robot, skill):
    model = "nybble" if "nybble" in (robot.model or "").lower() else "bittle"  # an arm build reports as Bittle
    if model not in ONLY_ON.get(skill, {model}):
        pytest.skip(f"{skill.value} is not on {robot.model}")
    if skill in RISKY and not os.environ.get("PETOI_RISKY"):
        pytest.skip("flips and falls; set PETOI_RISKY=1 with the robot on the floor")
    robot.stand()  # same start posture for every timing
    start = time.monotonic()
    robot.skill(skill)
    elapsed = time.monotonic() - start
    print(f"\n{skill.value}: {elapsed:.1f} s (estimate {estimate_seconds(model, skill.value):.1f} s)")
    assert elapsed < STALE_SECONDS  # a later echo could be taken for a newer command's
```

**Implementation (`robot.py`)**
```python
class Robot:
    """A connected Petoi robot. Get one with petoi.connect().

    High-level methods raise RobotTimeout if the robot doesn't confirm.
    send()/send_binary() return the Reply and never raise on timeout.
    skill() waits up to skill_timeout, since one-shot skills confirm only when finished.
    """

    def __init__(self, transport: Transport, timeout: float = 5.0, skill_timeout: float = 30.0):
        self.transport = transport
        self.timeout = timeout
        self.skill_timeout = skill_timeout  # below Wi-Fi's 45 s task abort (src/webServer.h:53)
        ...

    def skill(self, name: Union[Skill, str], wait: bool = True, timeout: Optional[float] = None) -> Reply:
        """Run a skill by name, e.g. Skill.HI or "hi"; waits until it finishes (up to skill_timeout)."""
        return self._cmd("k", name, wait=wait, timeout=self.skill_timeout if timeout is None else timeout)

    def sit(self, wait: bool = True) -> Reply:
        """Sit down."""
        return self._cmd("k", Skill.SIT, wait=wait)

    def stand(self, wait: bool = True) -> Reply:
        """Stand up."""
        return self._cmd("k", Skill.STAND, wait=wait)

    def stop(self, wait: bool = True) -> Reply:
        """Stop walking and stand still."""
        return self._cmd("k", Skill.STAND, wait=wait)

    # gaits echo when they start (src/reaction.h:1555-1565), so they keep the short timeout
    def walk(self, direction: Direction = "forward", wait: bool = True) -> Reply:
        """Start walking forward, left or right until stop()."""
        return self._cmd("k", "wk" + _direction(direction), wait=wait)

    def trot(...):   return self._cmd("k", "tr" + _direction(direction), wait=wait)
    def crawl(...):  return self._cmd("k", "cr" + _direction(direction), wait=wait)
    def back(...):   # keep the validation, then:
        return self._cmd("k", "bk" + (_direction(direction) if direction else ""), wait=wait)
```
- `_cmd` already uses `timeout` in its `RobotTimeout` message.
- `connect()` is unchanged. Users set `robot.skill_timeout = 60` or pass `skill(..., timeout=60)`.

**Docs**
- README line 71, append: "`skill()` waits up to `robot.skill_timeout` (30 s) instead, because a one-shot skill confirms only when it finishes. Raise it with `robot.skill_timeout = 60` or `robot.skill("name", timeout=60)`."
- README line 175, replace the last sentence with: "By an estimate from the firmware's skill tables, the longest built-in skill (Nybble `hunt`) takes about 10 s. This has not been checked on hardware."
- TODO.md: replace the "Long skills vs the 5 s default timeout" item with: "[ ] Time every `Skill` on hardware (`-k every_skill -s`) and compare it with the estimate column."
- Plan: append this section, renamed "(approved …)" once approved.

**Verify**
- `cd "/Users/kaikai/projects/petoi codes/OpenCatEsp32-Quadruped-Robot - python-api/python" && .venv/bin/python -m pytest -q`
  - Expected: all pass, with 15 new tests (5 robot tests + 7 gait/posture parametrized cases + 1 + 3 estimate tests). Hardware tests are skipped.
- Before the implementation: the 5 new robot tests and the 7 gait cases fail on `skill_timeout` (`TypeError`/`AttributeError`). The estimator tests pass already.
- `PETOI_PORT=/dev/cu.usbserial-XXXX PETOI_RISKY=1 .venv/bin/python -m pytest tests/hardware -v -s -k every_skill` on Bittle and on Nybble. Also run with `PETOI_WS` once to check the Wi-Fi path near 10 s.
  - **Confirms (a):** at least one skill measures over 5 s (expected: `clap`, `pu1`, `hg` on Bittle; `hunt`, `wsf` on Nybble), and every skill finishes in under 15 s. Measurements within about +30% of the estimates also validate the model.
  - **Overturns or adjusts:**
    - Every skill under ~4 s: the premise is wrong. Keep (a) as harmless or drop it.
    - Any skill between 15 and 30 s: raise `STALE_SECONDS` above it and fix the README claim.
    - Any skill over ~20 s: raise `skill_timeout`, which must stay under 45.
    - Any skill over 45 s: Wi-Fi cannot run it at all; firmware issue.
    - Measured times consistently far from the estimates (beyond overhead): the timing model is wrong; mark the estimator tests as unreliable.

### Critical Files for Implementation
- /Users/kaikai/projects/petoi codes/OpenCatEsp32-Quadruped-Robot - python-api/python/src/petoi/robot.py
- /Users/kaikai/projects/petoi codes/OpenCatEsp32-Quadruped-Robot - python-api/python/tests/test_robot.py
- /Users/kaikai/projects/petoi codes/OpenCatEsp32-Quadruped-Robot - python-api/python/tests/test_constants.py
- /Users/kaikai/projects/petoi codes/OpenCatEsp32-Quadruped-Robot - python-api/python/tests/hardware/test_smoke.py
- /Users/kaikai/projects/petoi codes/OpenCatEsp32-Quadruped-Robot - python-api/src/skill.h (timing source, read-only)

Note: I wrote no files. The estimates came from Python run on stdin with the venv interpreter, not from a scratchpad script.
---

## Part D

### Amendment: gyro state, gyro calibration, and sourced skill names (proposed)

**Firmware facts** (worktree `src/` unless a URL is given)

*Gyro state (`g?`)*
- `g?` takes the `g`+args branch. It loops over each argument character and prints only on `'?'` (`reaction.h:606-612`): `PTF("Gyro state:")`, `PTT(" Update-", updateGyroQ)`, `PTT(" Balance-", gyroBalanceQ)`, `PTT(" Print-", printGyroQ)`, `PTTL(" Frequency-", fineAdjustQ)`.
- How those macros print:
  - `PT` is `Serial.print` (`tools.h:6`).
  - `PTT(s,d)` is `PT(s); PT(d)` with no newline (`tools.h:13`). `PTTL` adds the newline (`tools.h:14`).
  - `PTF` prints with no newline (`tools.h:9`).
  - The four flags are `bool` (`OpenCat.h:463-467`). ESP32 core 2.0.12 `Print` has no `print(bool)`, so a bool promotes to `print(int)` and prints `1` or `0` (`~/Library/Arduino15/packages/esp32/hardware/esp32/2.0.12/cores/esp32/Print.h:84-94`).
- The exact line is therefore `Gyro state: Update-1 Balance-1 Print-0 Frequency-1`.
  - "Frequency" is `fineAdjustQ`, described as "increase the frequency of gyroscope sampling" (`OpenCat.h:319`).
- **The state line goes to USB serial only.** It uses `PT`/`Serial.print`, not `printToAllPorts`, and only `printToAllPorts` writes to BLE, SPP, Web and Serial2 (`io.h:12-45`). Over Bluetooth, BLE or Wi-Fi only the echo arrives.
- **Echo.** The token stays `g` unless an `F`/`f` in the same command sets it to `G`/`g` (`reaction.h:573`). The echo comes from `printToAllPorts(token)` (`reaction.h:1557`). `g?` therefore echoes exactly `g`.
- **`?` inside `g`.** No conflict:
  - The other branches test `toupper(c)` against `F`, `B`, `U`, `P` (`reaction.h:569-604`).
  - `T_QUERY` `'?'` is only special when it is the token itself (`OpenCat.h:370`, `reaction.h:402`).
  - The BLE `'g'` remap applies only when `cmdLen == 0` (`bleUart.h:87`).
- **Side effect.** Every `g<args>` command except `gc` resets `imuSkip` and `runDelay` from `fineAdjustQ` (`reaction.h:616-617`). This undoes any `.`/`,` speed tweak.
- **No gyro.** Without `GYRO_PIN` the case body is compiled out and the robot only echoes `g` (`reaction.h:500-501`, `:621`).
- If the robot was running a skill, the token returns to `k` after the echo, so gaits continue (`reaction.h:1558-1560`).

*Gyro calibration (`gc` / `gci`)*
- **Sequence** (`reaction.h:511-563`):
  1. `shutServos()`, so the robot goes limp.
  2. Print `Setting updateGyroQ to false...` and set `updateGyroQ=false`.
  3. Unless the command is `gci`, print `Put the robot FLAT on the table and don't touch it during calibration.` and play `beep(8,500,500,5)` + `beep(15,500,500,1)`.
     - `tone(...,duration)` blocks for `duration` (`PetoiESP32Servo/ESP32Tone.cpp:23-26`), and each repeat is tone plus `pause` (`sound.h:71-80`), so this takes about 6 s when sound is on.
  4. Wait for the IMU task to exit (`taskIMU` loops `while (*running)` on `&updateGyroQ`, `imu.h:954`, `:991-995`).
  5. Start `taskCalibrateImuUsingCore0`.
  6. Poll up to **10 s** (`:549`) for `updateGyroQ` to become true again. On timeout it prints `Timeout waiting for calibration to complete. Forcing continuation.` (`:553`) and carries on anyway.
  7. Print `Calibration completed, allowing IMU to stabilize...`, then `delay(3000)`, then `beep(18,50,50,6)` (about 0.6 s), then `createIMUTask()`, which prints `Creating IMU task...` (`imu.h:989`).
  8. Echo `g` (`reaction.h:1557`).
- **Worst case** is about 6 + 10 + 3 + 0.6 + 0.1 ≈ 20 s. `gci` skips the 6 s of beeps.
- **No Y/n prompt in the normal path.** The calibration task (`imu.h:1048-1104`):
  - prints offsets and `Calibrating...` or `*** Calibrating Now ***`;
  - runs `calibrateICM()` / `calibrateMPU()`;
  - **writes the new offsets to EEPROM/NVS**, so they persist (`imu.h:208-228`, `:491-512`);
  - sets `updateGyroQ=true`;
  - prints `\nCalibration done.\n` with `printToAllPorts`, commented "for confirming the desktop app" (`imu.h:1102`). This reaches every port.
- **Interactive failure path.** On an ICM42670 read error it prints `Reading error: ...`, then loops a melody until any byte arrives on USB `Serial` (`imu.h:1069-1082`, `:478-490`). The main loop's 10 s timeout fires meanwhile and the robot echoes `g` without `Calibration done.`.
- The Y/n prompt (`- Calibrate the Inertial Measurement Unit (IMU)? (Y/n)`) exists only in first-boot `imuSetup()` (`imu.h:1012-1014`), not in `gc`.
- **Petoi's Desktop App** sends `gc` and waits 20 s for a line containing `Calibration done` (https://github.com/PetoiCamp/OpenCat-Quadruped-Robot/blob/54da7b70e5fdbf94019b0fea23162641ef7e9508/pyUI/Debugger.py#L229-L251).

*Skill lookup (relevant to the skill names)*
- `lookUp` prints the matched skill name before running it (`skill.h:60`).
- A key ending in `L`/`R`/`X` matches a table name by prefix (`skill.h:55-58`). So `kpickL` resolves to `pick`, the first entry in table order `pick, pickD, pickF` (`InstinctBittleESP.h:2486`).
- For any key not ending in `L`, a behavior is **mirrored on alternate calls** through `coinFace` (`skill.h:500-506`). Bare `kpick`, `kput` and `ktoss` therefore alternate sides.
- On `ROBOT_ARM` builds, keys ending in `L`/`R`/`F` first try `<name>Arm<lr>` (`skill.h:461-475`). A miss prints `?pickArmF?` (`skill.h:63-65`) and falls back. This adds an extra reply line, which does no harm.
- `zz` is a one-frame behavior that sets all 16 joints to 0 at speed 4, in both Bittle tables (`InstinctBittleESP.h:2481-2485`, `InstinctBittleESP_arm.h:2396-2400`). It is not in the Nybble table. `zero` is a posture with all joints at 0 (`InstinctBittleESP.h:1901-1903`, `InstinctNybbleESP.h:1069-1071`), and `calib` is identical (`InstinctBittleESP.h:1877-1879`). `zz` was added in commit `10de0da` (2023-02-28, "dataBuffer->newCmd; KT OVF; fix direction") with no comment.
- `randomMind.h:51` forbidden list: `ff bf rc rl jmp bk pd hlw calib dropped lifted ts ang zero zz lnd lpov`.

**Skill meaning table**

Abbreviations:
- B = `InstinctBittleESP.h:2486`; A = `InstinctBittleESP_arm.h:2401`; N = `InstinctNybbleESP.h:1451`.
- PWC = PetoiCamp/PetoiWebCoding at commit `e8e145b`. Labels are in `js/motion_skills.js` and English text in `lang/translations.js`: https://github.com/PetoiCamp/PetoiWebCoding/blob/e8e145b91031a923b8eb36169b6817d850968db3/js/motion_skills.js

| name | meaning | source | B | A | N | RISKY | add as |
|---|---|---|---|---|---|---|---|
| `zero` | all joints at 0° (posture) | PWC `kzero` → "zero" (motion_skills.js:58; translations.js:1063); data `InstinctBittleESP.h:1901` | Y | Y | Y | yes | `ZERO` |
| `calib` | calibration posture for attaching legs | `OpenCat.h:300-302`; loaded by `c` (`reaction.h:865`); PWC "calibration" (:56, tr:1060) | Y | Y | Y | yes | `CALIBRATION_POSE` |
| `ts` | servo test (all servos rotate in sync) | `qualityAssurance.h:182-183`; PWC "test servo" (:89, tr:1115) | Y | Y | Y | yes | `SERVO_TEST` |
| `lnd` | landing posture used on free fall | `reaction.h:46-48` (IMU_EXCEPTION_FREEFALL) | Y | Y | - | yes | `LAND` |
| `dropRec` | recovery queued after the robot is put down from being lifted | `reaction.h:181-188` (non-arm builds) | Y | Y | Y | no | `DROP_RECOVER` |
| `knock` | reaction to being knocked | `reaction.h:69-74` (IMU_EXCEPTION_KNOCKED); PWC "knock" (:123, tr:1213) | Y | - | Y | no | `KNOCK` |
| `lucky` | lucky cat | `voice.h:60` "lucky cat 招财猫"; PWC "lucky cat" (:125, tr:1215) | Y | - | Y | no | `LUCKY_CAT` |
| `lu` | look up (posture) | PWC `klu` → "look up" (:57, tr:1062) | - | - | Y | no | `LOOK_UP` |
| `lkPaws` | lick paws | `voice.h:61`; PWC "lick paws" (:124, tr:1214) | - | - | Y | no | `LICK_PAWS` |
| `headToss` | head toss | PWC "head toss" (:122, tr:1212) | - | - | Y | no | `HEAD_TOSS` |
| `pickD` / `pickF` | arm: pick down / pick front | PWC (:105-106, tr "pick down/front"); `voice.h:35` "pick front" | Y | Y | - | no | `PICK_DOWN`, `PICK_FRONT` |
| `putD` / `putF` | arm: put down / put front | PWC (:109-110); `voice.h:36` "put down" | Y | Y | - | no | `PUT_DOWN`, `PUT_FRONT` |
| `tossF` | arm: throw front | PWC (:114, "throw front"); `voice.h:43` "toss front" | Y | Y | - | no | `TOSS_FRONT` |
| `launch` | arm: shoot/launch | PWC `klaunch` → "shoot" (:113); `voice.h:41` "launch 发射" | Y | Y | - | no | `LAUNCH` |
| `pick` / `put` / `toss` | one side, alternating per call; `kpickL`/`kpickR` fix the side | PWC `kpickL` = "pick left", resolved to `pick` by `skill.h:55-58`; mirroring `skill.h:500-506` | Y | Y | - | no | leave out |
| `tossD` | arm: throw down | PWC hides it: "Temporarily hidden until the toss-down skill implementation is improved" (:120-121) | Y | Y | - | no | leave out |
| `flip` / `flipD` / `flipF` | flip / backflip / frontflip | PWC "flip" (:100), `kflipD` "backflip", `kflipF` "frontflip" (:95-96) | Y | - | - | **no** (not in `randomMind.h:51`) | leave out |
| `zz` | all joints to 0° slowly (one frame, speed 4); **not "sleep"** | data `InstinctBittleESP.h:2481-2485`; workshop `level-3.py` "all joint at 0 degrees" | Y | Y | - | yes | remove `SLEEP`; no member |

**`zz` = SLEEP is refuted.** The firmware data is just "all joints to 0", which is the same pose as `zero` and `calib`. No PetoiCamp source labels it sleep. PWC's skill list (`memo/instinct_skills.csv`) lists `zz` but gives it no label.

**Open questions / UNVERIFIED**
- How long `calibrateMPU()` (`CalibrateAccel(20)` + `CalibrateGyro(20)`) and `calibrateICM()` (two `getOffset(200)` calls) take. If either takes more than 10 s, the firmware echoes `g` before `Calibration done.`, and `calibrate_gyro()` would report failure even though calibration finishes later. Time this on hardware.
- What `ROBOT_ARM` builds do with `gc`. Not traced beyond the shared code.
- Whether mirrored `pickF`/`pickD`/`putF`/`putD`/`tossF`/`launch` look the same as unmirrored. They alternate per call (`skill.h:500-506`).
- What the arm skills do on a Bittle with no arm attached. PWC offers them only for `bittle_arm`.
- The `kzz` "困" (sleepy) label in the local `../xiaozhi codes/mcp_server.cc:32`. Its provenance is unknown (not a git repo, and no PetoiCamp match), so it is not used.
- `knock` and `lucky` are in the plain Bittle table, but PWC offers them only for Nybble. The availability below follows the tables.
- `DROP_RECOVER` meaning is inferred from where the firmware calls it. The name expansion "drop recovery" is not stated anywhere.

**Decisions**
1. **`gyro_state()` returns `{"update", "balance", "print", "fine"}`.**
   - It parses the one line that contains `Gyro state:` with `(\w+)-([01])`, which tolerates other lines such as `print6Axis` spam.
   - It raises `RobotError` if the line is missing (non-USB link or no IMU) or any flag is missing.
   - Rejected: reading the state from echoes. `g?` always echoes `g`, which carries no information.
   - Rejected: making it work over BLE. The firmware never sends the line there.
2. **Include `calibrate_gyro()`, sending `gc` only.**
   - It is non-interactive in the normal path, and Petoi's Desktop App drives it the same way: send `gc`, wait for `Calibration done`, 20 s.
   - Timeout is `self.timeout + 20`.
   - It succeeds only if a reply line contains `Calibration done`; otherwise it raises `RobotError`.
   - Rejected: `gci`. It removes the 6 s warning beep, which is the only cue to a person holding the robot, and the offsets it writes persist.
   - Rejected: leaving calibration out. The library can detect failure cleanly, and the "robot goes limp" and "writes offsets" risks are covered by the docstring and README.
   - The ICM read-error path still blocks until a USB byte arrives. That is documented, not handled.
3. **Skills.**
   - Add the 16 sourced members in the table above.
   - **Remove `Skill.SLEEP`.** Its name is refuted, `zz` duplicates `ZERO`, and the package is unpublished, so nothing downstream breaks.
   - Rejected: renaming it to an invented name such as `ZERO_SLOW`.
   - Leave out `flip*`: their meaning overlaps `BACK_FLIP`/`FRONT_FLIP` without a stated difference, and `test_constants` would force violent flips out of `RISKY`.
   - Leave out bare `pick`/`put`/`toss` (their side alternates) and `tossD` (hidden upstream).
4. **`RISKY` grows** by `ZERO`, `CALIBRATION_POSE`, `SERVO_TEST` and `LAND`, as the test requires. The comment changes from "violent" to "skills the firmware keeps out of random mode".
5. **Mock** answers `g?` and `gc` so docs examples work offline.
6. **Gyro state stays out of `scenario.py`**, which also runs over BLE and Wi-Fi. It gets a USB-only hardware test instead.

**Files**
- Modify `python/src/petoi/robot.py`: add `gyro_state` and `calibrate_gyro`.
- Modify `python/src/petoi/constants.py`: `Skill`, `ONLY_ON`, `RISKY`.
- Modify `python/src/petoi/transports/mock.py`: answer `g?` and `gc`.
- Modify `python/tests/test_robot.py`, `python/tests/test_constants.py`, `python/tests/test_mock.py` and `python/tests/hardware/test_smoke.py`.
- Modify `python/README.md`, `python/TODO.md`, and `docs/superpowers/plans/2026-10-27-python-api.md` (append this amendment).

**Tests** (write these first and run them red)

`python/tests/test_robot.py`: change the import to `from petoi.errors import RobotError, RobotTimeout`, then append:
```python
def test_gyro_state_parses_the_state_line():
    # src/reaction.h:608-612 prints one line on USB; other output may come first
    r = robot({b"g?\n": ["ypr 1 2 3", "Gyro state: Update-1 Balance-0 Print-0 Frequency-1", "g"]})
    assert r.gyro_state() == {"update": True, "balance": False, "print": False, "fine": True}
    assert r.transport.written[-1] == b"g?\n"


def test_gyro_state_without_state_line_is_an_error():
    r = robot({b"g?\n": ["g"]})  # e.g. over BLE: the line is USB-only (src/tools.h:6)
    with pytest.raises(RobotError, match="gyro state"):
        r.gyro_state()


def test_calibrate_gyro_waits_for_calibration_done():
    r = robot({b"gc\n": [
        "Setting updateGyroQ to false...", "Calibrating...", "Calibration done.",
        "Calibration completed, allowing IMU to stabilize...", "Creating IMU task...", "g",
    ]})
    seen = []
    command = r.transport.command
    r.transport.command = lambda token, payload, timeout: seen.append(timeout) or command(token, payload, timeout)
    assert r.calibrate_gyro().completed
    assert r.transport.written[-1] == b"gc\n"
    assert seen == [pytest.approx(0.2 + 20)]


def test_calibrate_gyro_raises_when_firmware_gives_up():
    r = robot({b"gc\n": [
        "Timeout waiting for calibration to complete. Forcing continuation.",
        "Calibration completed, allowing IMU to stabilize...", "g",
    ]})
    with pytest.raises(RobotError, match="calibration did not finish"):
        r.calibrate_gyro()
```

`python/tests/test_mock.py`: append:
```python
def test_mock_reports_gyro_state_and_calibrates():
    r = Robot(MockTransport())
    assert r.gyro_state() == {"update": True, "balance": True, "print": False, "fine": True}
    assert r.calibrate_gyro().completed
```

`python/tests/test_constants.py`: replace `test_skill_values_are_firmware_names` with:
```python
def test_skill_values_are_firmware_names():
    # src/InstinctBittleESP.h:2486, src/InstinctNybbleESP.h:1451
    assert Skill.HIGH_FIVE.value == "fiv"
    assert Skill.STAND.value == "up"
    assert Skill.ZERO.value == "zero" and Skill.LICK_PAWS.value == "lkPaws"
    assert not hasattr(Skill, "SLEEP")  # zz is all joints to 0, not sleep (src/InstinctBittleESP.h:2481-2485)
```
The existing parametrized `test_skills_exist_where_documented` and `test_risky_skills_are_the_ones_random_mode_forbids` cover the new `ONLY_ON` and `RISKY` entries without changes.

`python/tests/hardware/test_smoke.py`:
- Change the skip text in `test_every_skill_completes` to `"flips, falls and test postures; set PETOI_RISKY=1 with the robot on the floor"`.
- Append:
```python
def test_gyro_state_over_usb(robot, request):
    if request.node.callspec.params["robot"] != os.environ.get("PETOI_PORT"):
        pytest.skip("the gyro state line is printed to USB only (src/tools.h:6)")
    robot.gyro(True)
    assert robot.gyro_state()["balance"] is True
```
(`calibrate_gyro` gets no automated hardware test: it overwrites the stored offsets. Run it by hand once with the robot flat and time it. That timing answers the first open question.)

**Implementation**

`python/src/petoi/robot.py`:
- Add `import re` after `import threading`.
- Change the errors import to `from petoi.errors import RobotError, RobotTimeout` (already present).
- Add after `_DIRECTIONS`:
```python
_GYRO_FLAGS = {"Update": "update", "Balance": "balance", "Print": "print", "Frequency": "fine"}  # src/reaction.h:609-612
_CALIBRATE_SECONDS = 20  # 6 s of beeps, up to 10 s calibrating, 3 s settling (src/reaction.h:519-562)
```
- Add after `gyro()`:
```python
    def gyro_state(self) -> Dict[str, bool]:
        """Read the gyro flags (USB only): update, balance, print, and fine (frequent sampling)."""
        reply = self._cmd("g", "?")  # src/reaction.h:606-612
        line = next((l for l in reply.lines if "Gyro state:" in l), None)
        if line is None:
            raise RobotError("no gyro state received; the robot prints it over USB only (src/tools.h:6)")
        flags = dict(re.findall(r"(\w+)-([01])", line))
        if not set(_GYRO_FLAGS) <= set(flags):
            raise RobotError(f"unexpected gyro state: {line!r}")
        return {key: flags[name] == "1" for name, key in _GYRO_FLAGS.items()}

    def calibrate_gyro(self) -> Reply:
        """Calibrate and save the gyro (about 20 s). Servos turn off; keep the robot flat and still."""
        reply = self._cmd("g", "c", timeout=self.timeout + _CALIBRATE_SECONDS)  # src/reaction.h:511-563
        if not any("Calibration done" in line for line in reply.lines):  # src/imu.h:1102
            raise RobotError("gyro calibration did not finish; put the robot flat, keep it still and try again")
        return reply
```

`python/src/petoi/transports/mock.py`: in `write()`, before `self._out.append(token)`, add these branches to the `if`/`elif` chain:
```python
        elif data == b"g?\n":
            self._out.append("Gyro state: Update-1 Balance-1 Print-0 Frequency-1")  # src/reaction.h:608-612
        elif data == b"gc\n":
            self._out.append("Calibration done.")  # src/imu.h:1102
```

`python/src/petoi/constants.py`:
- In `Skill`, delete `SLEEP = "zz"`.
- Add after `WASH_FACE = "wsf"`:
```python
    ZERO = "zero"
    CALIBRATION_POSE = "calib"
    SERVO_TEST = "ts"
    LAND = "lnd"
    DROP_RECOVER = "dropRec"
    KNOCK = "knock"
    LUCKY_CAT = "lucky"
    LOOK_UP = "lu"
    LICK_PAWS = "lkPaws"
    HEAD_TOSS = "headToss"
    PICK_DOWN = "pickD"   # PICK_DOWN..LAUNCH are for the robot arm
    PICK_FRONT = "pickF"
    PUT_DOWN = "putD"
    PUT_FRONT = "putF"
    TOSS_FRONT = "tossF"
    LAUNCH = "launch"
```
- Replace `ONLY_ON` and `RISKY`:
```python
ONLY_ON = {
    Skill.CLAP: _BITTLE,
    Skill.JUMP: _BITTLE,
    Skill.LEAP_OVER: _BITTLE,
    Skill.MOONWALK: _BITTLE,
    Skill.PUSH_UP_ONE_HAND: _BITTLE,
    Skill.SHOW_OFF: _BITTLE,
    Skill.LAND: _BITTLE,
    Skill.PICK_DOWN: _BITTLE,
    Skill.PICK_FRONT: _BITTLE,
    Skill.PUT_DOWN: _BITTLE,
    Skill.PUT_FRONT: _BITTLE,
    Skill.TOSS_FRONT: _BITTLE,
    Skill.LAUNCH: _BITTLE,
    Skill.BACK_FLIP: {"bittle"},
    Skill.FRONT_FLIP: {"bittle"},
    Skill.ROLL: {"bittle"},
    Skill.KNOCK: {"bittle", "nybble"},
    Skill.LUCKY_CAT: {"bittle", "nybble"},
    Skill.WASH_FACE: {"nybble"},
    Skill.LOOK_UP: {"nybble"},
    Skill.LICK_PAWS: {"nybble"},
    Skill.HEAD_TOSS: {"nybble"},
}

# Flips, falls, and test postures the firmware keeps out of random mode
# (src/randomMind.h:51). Clear some space before running these.
RISKY = {
    Skill.ANGRY, Skill.PLAY_DEAD, Skill.RECOVER, Skill.JUMP, Skill.LEAP_OVER,
    Skill.BACK_FLIP, Skill.FRONT_FLIP, Skill.ROLL,
    Skill.ZERO, Skill.CALIBRATION_POSE, Skill.SERVO_TEST, Skill.LAND,
}
```

**Docs**
- `python/README.md`, method table: after the `gyro(on)` row add:
  - `| gyro_state() | {"update", "balance", "print", "fine"} flags as booleans; USB only (raises RobotError over Bluetooth/Wi-Fi) |`
  - `| calibrate_gyro() | Calibrate and save the gyro (~20 s). The servos turn off: lay the robot flat and don't touch it. Raises RobotError if it didn't finish |`
- `python/README.md`, `Skill` names line: drop `SLEEP` and append `ZERO`, `CALIBRATION_POSE`, `SERVO_TEST`, `LAND`, `DROP_RECOVER`, `KNOCK`, `LUCKY_CAT`, `LOOK_UP`, `LICK_PAWS`, `HEAD_TOSS`, `PICK_DOWN`, `PICK_FRONT`, `PUT_DOWN`, `PUT_FRONT`, `TOSS_FRONT`, `LAUNCH`.
- `python/README.md`, following paragraph:
  - Add: "`PICK_DOWN` … `LAUNCH` are made for the robot arm. For a fixed side, use `robot.skill("pickL")` / `"pickR"` (also `put`, `toss`); a bare `"pick"` alternates sides."
  - Change the `RISKY` sentence to "lists flips, falls and test postures the firmware keeps out of random mode."
- `python/TODO.md`:
  - Delete the `Skill.SLEEP` item and the "More `Skill` members" item, and replace them with one line: "`flip`/`flipD`/`flipF` left out: overlap with `bf`/`ff` and not in `randomMind.h:51`, so `RISKY` could not mark them".
  - Replace "Gyro extras" with a hardware item: "Time `calibrate_gyro()` on MPU6050 and ICM42670 boards; firmware gives up after 10 s (`src/reaction.h:549`)".
- Plan file: append this amendment after the "API doc review notes" amendment.

**Verify**
- `cd "/Users/kaikai/projects/petoi codes/OpenCatEsp32-Quadruped-Robot - python-api/python" && .venv/bin/python -m pytest -q`
  - Before any change: `151 passed, 47 skipped` (the current baseline).
  - After the tests are written but before the implementation: the 4 new `test_robot` tests, the new `test_mock` test and the edited `test_skill_values_are_firmware_names` fail.
  - After the implementation: **`156 passed, 63 skipped`**. Passed is +4 robot and +1 mock. Skipped is +15 parametrized skills (−`SLEEP`, +16 new) and +1 gyro hardware test.
- `.venv/bin/python -m pytest -q tests/test_constants.py -v`: all 3 models in `test_skills_exist_where_documented` and `test_risky_skills_are_the_ones_random_mode_forbids` pass.
- `.venv/bin/python -c "from petoi import Robot; from petoi.transports.mock import MockTransport; print(Robot(MockTransport()).gyro_state())"` prints `{'update': True, 'balance': True, 'print': False, 'fine': True}`.
- Hardware (USB): `PETOI_PORT=/dev/cu.usbserial-XXXX .venv/bin/python -m pytest tests/hardware -v -s -k "gyro_state or every_skill"`.

### Critical Files for Implementation
- /Users/kaikai/projects/petoi codes/OpenCatEsp32-Quadruped-Robot - python-api/python/src/petoi/robot.py
- /Users/kaikai/projects/petoi codes/OpenCatEsp32-Quadruped-Robot - python-api/python/src/petoi/constants.py
- /Users/kaikai/projects/petoi codes/OpenCatEsp32-Quadruped-Robot - python-api/python/tests/test_robot.py
- /Users/kaikai/projects/petoi codes/OpenCatEsp32-Quadruped-Robot - python-api/python/src/petoi/transports/mock.py
- /Users/kaikai/projects/petoi codes/OpenCatEsp32-Quadruped-Robot - python-api/src/reaction.h (lines 493-622, 1557; read-only reference)
---

## Part E

### Amendment: packaging and CI follow-ups (proposed)

The repo was not modified (`git status --short` is empty). All tests ran in scratch copies and venvs under `/private/tmp/claude-502/-Users-kaikai-projects-petoi-codes-OpenCatEsp32-Quadruped-Robot/df4f9dff-4f8a-483a-b6b9-65d6dfa83fc9/scratchpad/planE/` (called `$S` below). The repo `python/` dir is `$P`.

#### 1. Hatchling floor and project metadata

**Findings**

I built the current pyproject with each candidate hatchling (`hatchling build -d $S/out_$v`). I checked each wheel's METADATA with `packaging.metadata.Metadata.from_email(validate=True)` (packaging 26.3) and with `twine check`.

| hatchling | Metadata-Version | license fields | validate / twine |
|---|---|---|---|
| 1.18.0, 1.21.1 | 2.1 | `License-Expression: MIT`, `License-File: LICENSE` | INVALID: `license-expression introduced in metadata version 2.4, not 2.1`; twine `ERROR InvalidDistribution` |
| 1.24.2, 1.25.0 | 2.3 | same | INVALID (`... not 2.3`); twine ERROR |
| 1.26.3 | 2.3 | legacy `License: MIT` only | valid, but not PEP 639 |
| **1.27.0**, 1.28.0 | **2.4** | `License-Expression: MIT`, `License-File: LICENSE` | valid; twine PASSED |

- The `LICENSE` file is picked up by hatchling's default glob in every version tested, so an explicit `license-files` key adds nothing. I tested `license-files = ["LICENSE"]` too: both 1.26.3 and 1.27.0 build with it.
- On PyPI, hatchling 1.27.0 (2024-12-15) has `requires_python >=3.8`, while 1.28.0 through 1.32.4 (the latest) need `>=3.10`. So on the CI Python 3.9 legs, build isolation already resolves to exactly 1.27.0. Verified: `$S/ws39/bin/python -m build` on 3.9.6 gives `Generator: hatchling 1.27.0` and `Metadata-Version: 2.4`.
- Not verified: whether PyPI itself would reject the 1.18–1.25 output. I did not try an upload; twine rejecting it is the evidence.
- URL checks (`curl -L`, status and final URL):
  - `github.com/PetoiCamp/OpenCatEsp32` returns 200 but redirects to `github.com/PetoiCamp/OpenCatEsp32-Quadruped-Robot`. That is the canonical name, and it is also the `origin` remote.
  - `.../OpenCatEsp32-Quadruped-Robot/issues`: 200.
  - `.../tree/main/python`: **404** (not merged yet).
  - `https://www.petoi.com`: 200. `https://docs.petoi.com`: 200.
  - `https://docs.petoi.com/apis/python-api`: 200, but it documents the older `ardSerial` API, not this package.
  - Fork `kaimai/OpenCatEsp32`: 200, but `gh api` reports `has_issues: false`. `.../tree/feature/python-api/python`: 404 (branch not pushed).
- Trove classifiers (trove-classifiers package): there is **no Robotics topic**. `Framework :: Robot Framework` is a test-automation tool and does not apply. All 16 proposed classifiers are in the list (`unknown classifiers: []`).
- With the proposed metadata, hatchling 1.27.0 gives Metadata-Version 2.4 and the `packaging` validation passes. `twine check --strict` passes on both the wheel and the sdist.

**Decisions**

- Floor: `hatchling>=1.27`. No `license-files` key.
- URLs point at upstream's canonical name, not the redirect. Docs go to the doc-center root until a page for this package exists. The upstream-vs-fork choice is left to the owner (see questions).
- Classifiers list 3.9–3.13. CI tests only 3.9 and 3.13; 3.10–3.12 are untested.
- `authors` is a draft for the owner to confirm: the LICENSE copyright is "Rongzhong Li", and all 25 `python/` commits are by Kai Mai. No emails.

**Diff: `python/pyproject.toml`**

```diff
 [build-system]
-requires = ["hatchling>=1.18"]
+requires = ["hatchling>=1.27"]  # 1.27 is the first to write PEP 639 License-Expression with Metadata-Version 2.4
 build-backend = "hatchling.build"
@@
 license = "MIT"
+authors = [{ name = "Rongzhong Li" }, { name = "Kai Mai" }]
+keywords = ["petoi", "opencat", "bittle", "nybble", "quadruped", "robot", "robotics", "education", "esp32", "bluetooth", "ble", "websocket"]
+classifiers = [
+    "Development Status :: 3 - Alpha",
+    "Environment :: Console",
+    "Intended Audience :: Developers",
+    "Intended Audience :: Education",
+    "Operating System :: OS Independent",
+    "Programming Language :: Python :: 3",
+    "Programming Language :: Python :: 3 :: Only",
+    "Programming Language :: Python :: 3.9",
+    "Programming Language :: Python :: 3.10",
+    "Programming Language :: Python :: 3.11",
+    "Programming Language :: Python :: 3.12",
+    "Programming Language :: Python :: 3.13",
+    "Topic :: Education",
+    "Topic :: Software Development :: Embedded Systems",
+    "Topic :: System :: Hardware",
+    "Typing :: Typed",
+]
 dependencies = ["pyserial>=3.5"]

+[project.urls]
+Homepage = "https://www.petoi.com"
+Documentation = "https://docs.petoi.com"
+Source = "https://github.com/PetoiCamp/OpenCatEsp32-Quadruped-Robot"
+Issues = "https://github.com/PetoiCamp/OpenCatEsp32-Quadruped-Robot/issues"
+
 [project.optional-dependencies]
```

**Verify**

```
cd python && python -m build --outdir /tmp/x && pip install twine && twine check --strict /tmp/x/*
unzip -p /tmp/x/*.whl '*.dist-info/METADATA' | grep -E '^(Metadata-Version|License-Expression|License-File|Project-URL|Classifier)'
# expect Metadata-Version: 2.4, License-Expression: MIT, License-File: LICENSE
```

The existing CI step `python -m build` on the 3.9 legs already builds with exactly 1.27.0.

#### 2. mypy in CI

**Findings**

mypy 2.4.0 (compiled), Python 3.13, `pip install -e ".[all]"` (bleak 3.0.2, websockets 17.3). Output, trimmed:

```
$ mypy src/petoi
protocol.py:39: Argument 1 to "index" has incompatible type "Any | int | str"; expected "SupportsIndex"  [arg-type]
transports/serial.py:8 / connect.py:7: Library stubs not installed for "serial" / "serial.tools"  [import-untyped]
transports/ble.py:55,63,95: Item "None" of "BleakClient | None" has no attribute "services"/"disconnect"/"write_gatt_char"  [union-attr]
transports/ble.py:56: Item "None" of "BleakGATTCharacteristic | Any | None" has no attribute "max_write_without_response_size"
transports/websocket.py:55: Incompatible types in assignment (expression has type "None", target has type "bool")   # kwargs = {} inferred dict[str, bool]
transports/websocket.py:57: No overload variant of "connect" matches argument types "str", "float", "dict[str, bool]"
transports/websocket.py:122,135,138: "object" has no attribute "get"   # Queue[object]
connect.py:62: Argument 1 to "WebSocketTransport" has incompatible type "str | None"; expected "str"
Found 13 errors in 5 files
```

- With `types-pyserial==3.5.0.20260712` installed, the stub errors become two real findings: `serial.py:77/88: "SerialBase" has no attribute "in_waiting"/"reset_input_buffer"`. The annotation `Union[str, serial.SerialBase]` is too wide: `SerialBase` has neither method. In the stubs, `serial_for_url()` returns `serial.Serial`.
- `--strict` gives 23 errors. The extra ones are mostly `no-untyped-def` plus one `no-any-return`. Not proposed now.
- `mypy --python-version 3.9` fails with: `Python 3.9 is not supported (must be 3.10 or higher)`. mypy 2.4.0 also needs Python >=3.10 to install. So mypy cannot check 3.9 compatibility. The 3.9 test legs still catch that at runtime.
- After the fixes below, `mypy` with the config below gives `Success: no issues found in 13 source files`. The same holds with websockets 13.0 installed instead of 17.3. The same config on the original src gives `Found 13 errors in 5 files`.
- Tests still pass after the fixes:
  - 3.13: 147 passed, 47 skipped, coverage 94.61%. The 4 failures were test_constants run outside the repo; see item 4.
  - 3.9.6 + websockets 13.1: 151 passed, 47 skipped, coverage 94.10%.
- Checking `tests/` as well would add about 15 errors (pytest stubs, `BrokenPort` fakes). Scope is `src/petoi` only.

**Decisions**

- Level: mypy's defaults plus `check_untyped_defs`, `warn_unused_ignores`, `warn_redundant_casts` and `strict_equality`. Not `--strict`.
- Pin `mypy==2.4.0` and `types-pyserial==3.5.0.20260712` in the CI step only. They are not added to the `dev` extra, because mypy 2.x will not install on 3.9.
- CI: one job, ubuntu-latest, Python 3.13.

**Code fixes** (no behaviour change; no `# type: ignore`)

```diff
--- python/src/petoi/protocol.py
-from typing import List, Union
+from typing import Any, List, Union
@@ def encode
-            raw = a.value if isinstance(a, Enum) else a
+            raw: Any = a.value if isinstance(a, Enum) else a  # a str raises TypeError below
--- python/src/petoi/transports/serial.py
-    def __init__(self, port: Union[str, serial.SerialBase], boot_timeout: float = 20.0):
+    def __init__(self, port: Union[str, serial.Serial], boot_timeout: float = 20.0):
--- python/src/petoi/transports/ble.py
-from typing import Optional
+from typing import Any, Optional
@@
-        self._client = None
+        self._client: Any = None  # bleak.BleakClient; bleak is an optional import
--- python/src/petoi/transports/websocket.py
-from typing import List, Optional
+from typing import Any, Dict, List, Optional
@@
-_CLOSED = object()  # reader-thread sentinel: the connection is gone
+_CLOSED: Dict[str, Any] = {}  # reader-thread sentinel (compared by identity): the connection is gone
@@
-        kwargs = {}
+        kwargs: Dict[str, Any] = {}
@@
-        self._messages: "queue.Queue[object]" = queue.Queue()
+        self._messages: "queue.Queue[Dict[str, Any]]" = queue.Queue()
--- python/src/petoi/connect.py
         from petoi.transports.websocket import WebSocketTransport
+        assert value is not None  # classify() always gives "wifi" a host
         return WebSocketTransport(value, timeout=timeout)
```

**Config: `python/pyproject.toml`**

```toml
[tool.mypy]
files = ["src/petoi"]
check_untyped_defs = true
warn_unused_ignores = true
warn_redundant_casts = true
strict_equality = true
```

**Workflow: add under `jobs:`**

```yaml
  typecheck:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: python
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
      - run: pip install -e ".[dev]" "mypy==2.4.0" "types-pyserial==3.5.0.20260712"
      - run: mypy
```

**Verify**

```
cd python && pip install "mypy==2.4.0" "types-pyserial==3.5.0.20260712" && mypy    # Success: no issues found in 13 source files
pytest -W error::DeprecationWarning --cov=petoi --cov-fail-under=85
```

#### 3. CI job pinned to the oldest websockets (13.x)

**Findings**

| Setup | `tests/test_websocket.py` | Full suite (`-W error::DeprecationWarning`) |
|---|---|---|
| Python 3.9.6, websockets 13.1 (`websockets==13.*`) | `9 passed in 1.04s` | `151 passed, 47 skipped in 2.47s` |
| Python 3.13, websockets 13.0 | — | `151 passed, 47 skipped`, coverage 94.44% (websocket.py 83%) |
| Python 3.13, websockets 13.1 | — | `151 passed, 47 skipped`, coverage 94.44% (websocket.py 83%) |

- The version check one-liner printed `13.1` and exited 0. With `'14.'` substituted it exits 1, so the check works.
- A matrix `include` cannot add this job. An include entry that matches an existing os/python pair only adds the new key to that leg. ubuntu/3.9 would then silently swap from latest websockets to 13, which is easy to misread.

**Decision:** a separate small job on ubuntu-latest with Python 3.9 (oldest Python plus oldest websockets, the combination most likely to drift). No coverage gate, since the main matrix already enforces it.

```yaml
  oldest-websockets:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: python
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.9"
      - run: pip install -e ".[dev]" "websockets==13.*"
      - run: python -c "import websockets, sys; print(websockets.__version__); sys.exit(not websockets.__version__.startswith('13.'))"
      - run: pytest -v -W error::DeprecationWarning
```

`permissions: contents: read` stays at the top level. Neither new job publishes.

**Verify:** `pip install -e ".[dev]" "websockets==13.*" && pytest tests/test_websocket.py -W error::DeprecationWarning` should give 9 passed.

#### 4. `tests/test_constants.py` without the firmware headers

**Findings**

- `python -m build --sdist --outdir $S/sd "$P"` gives `Successfully built petoi-0.1.0.tar.gz`. The sdist **does include `tests/`**: all test files plus `tests/hardware/test_smoke.py`. It also contains `TODO.md`, `examples/`, `.gitignore`, `LICENSE`, `README.md`, `pyproject.toml` and `PKG-INFO`. `.mypy_cache` is excluded even though it exists in `$P`.
- Run outside the repo, the current file fails 4 tests with `FileNotFoundError: ... /src/InstinctBittleESP.h` (also for `_arm.h` and `randomMind.h`). In the repo, `6 passed`.

**Decision**

- Skip only the 4 header-reading tests. The two tests that need no headers keep running.
- Never skip when `CI` is set (GitHub sets `CI=true`). A moved header then fails loudly in CI instead of being skipped silently.

```diff
--- python/tests/test_constants.py
+import os
 import re
 from pathlib import Path
@@
 TABLES = {"bittle": "InstinctBittleESP.h", "bittle_arm": "InstinctBittleESP_arm.h", "nybble": "InstinctNybbleESP.h"}
+# The firmware headers exist only in a repo checkout, not in an sdist. CI always has them, so never skip there.
+needs_headers = pytest.mark.skipif(
+    not all((SRC / h).is_file() for h in [*TABLES.values(), "randomMind.h"]) and not os.environ.get("CI"),
+    reason="needs the firmware headers in ../src (repo checkout only)",
+)
@@
+@needs_headers
 @pytest.mark.parametrize("model", TABLES)
 def test_skills_exist_where_documented(model):
@@
+@needs_headers
 def test_risky_skills_are_the_ones_random_mode_forbids():
```

**Results with the patch**

| Run | Result |
|---|---|
| Without headers | `2 passed, 4 skipped`; `-rs` shows `needs the firmware headers in ../src (repo checkout only)` |
| Without headers, `CI=true` | `4 failed, 2 passed` (FileNotFoundError), as intended |
| With the real headers (via symlink) | `6 passed` |
| Installed from the extracted sdist, patched test, full suite | `147 passed, 51 skipped` |

**Verify**

```
cd python && pytest tests/test_constants.py -rs        # in repo: 6 passed
python -m build --sdist --outdir /tmp/sd && tar xzf /tmp/sd/petoi-0.1.0.tar.gz -C /tmp/sd && cd /tmp/sd/petoi-0.1.0 && pip install ".[dev]" && pytest -rs   # 4 skipped from test_constants, rest pass
```

#### 5. Error-message review

This stays open in `python/TODO.md` until hardware testing; no change now.

**TODO.md:** tick the first four "Engineering follow-ups" items when they land; leave "Review error messages ..." unticked.

#### Owner questions

1. **Repo URL:** upstream `https://github.com/PetoiCamp/OpenCatEsp32-Quadruped-Robot` (canonical; `PetoiCamp/OpenCatEsp32` only redirects there) or the fork `https://github.com/kaimai/OpenCatEsp32`? The fork has Issues disabled, so it can't be the `Issues` URL. A deep link to `.../tree/main/python` is a 404 until merged.
2. **Documentation URL:** use `https://docs.petoi.com` for now? `https://docs.petoi.com/apis/python-api` exists but documents the older `ardSerial` API. Should Petoi add a page for this package first?
3. **`authors`:** "Rongzhong Li" (LICENSE copyright) and "Kai Mai" (all `python/` commits), "Petoi", or something else? Include emails?
4. **Classifiers:** keep "Development Status :: 3 - Alpha" until hardware sign-off? List 3.10–3.12 even though CI tests only 3.9 and 3.13?
5. **Tool pins:** pin `mypy` and `types-pyserial` exactly (proposed; needs manual bumps) or float them?
6. **Other floors:** also pin `bleak==0.22.*` (the declared floor) in the oldest-deps job? Not tested here.
7. **sdist contents:** keep `TODO.md` and `.gitignore` in the sdist, or exclude them?
8. **`CI` override in test_constants:** OK to keep, or prefer a plain skip?

### Critical Files for Implementation
- /Users/kaikai/projects/petoi codes/OpenCatEsp32-Quadruped-Robot - python-api/python/pyproject.toml
- /Users/kaikai/projects/petoi codes/OpenCatEsp32-Quadruped-Robot - python-api/.github/workflows/python-api.yml
- /Users/kaikai/projects/petoi codes/OpenCatEsp32-Quadruped-Robot - python-api/python/src/petoi/transports/websocket.py
- /Users/kaikai/projects/petoi codes/OpenCatEsp32-Quadruped-Robot - python-api/python/src/petoi/transports/serial.py
- /Users/kaikai/projects/petoi codes/OpenCatEsp32-Quadruped-Robot - python-api/python/tests/test_constants.py

---
