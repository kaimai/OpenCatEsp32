from __future__ import annotations

import operator
import re
import threading
import time
import warnings
from typing import Dict, Iterator, List, Literal, Optional, Sequence, Tuple, Union

from petoi._timing import DOF, skill_seconds
from petoi.constants import Joint, Skill, is_s3_firmware, model_key, skills_for
from petoi.errors import RobotError, RobotTimeout, WifiSetupFailed
from petoi.protocol import Reply, encode, parse_ints
from petoi.transports.base import StreamTransport, Transport
from petoi.transports.serial import READY, SerialTransport

Direction = Literal["forward", "left", "right"]
_DIRECTIONS = {"forward": "F", "left": "L", "right": "R"}  # 'R' mirrors 'L' (src/skill.h:501)
_GYRO_FLAGS = {"Update": "update", "Balance": "balance", "Print": "print", "Frequency": "fine"}  # src/reaction.h:609-612
_CALIBRATE_SECONDS = 20  # 6 s of beeps, up to 10 s calibrating, 3 s settling (src/reaction.h:519-562)
_SKILL_ROOM = 2507 - 1 - 20  # BUFF_LEN - 1 - CMD_LEN: leaves room for the next k command (src/OpenCat.h:438, :443; src/skill.h:131-137)
_WIFI_JOINED = re.compile(r"Successfully connected Wifi to IP Address: (\S+)")  # src/reaction.h:465, src/webServer.h:622
_WIFI_ALREADY = re.compile(r"Wifi already connected to IP Address: (\S+)")  # src/reaction.h:485
_IPV4 = r"(\d{1,3}(?:\.\d{1,3}){3})"
_WIFI_JOINED_S3 = re.compile(rf"IP Address: {_IPV4} successfully connected")  # S3 joins without rebooting (OpenCatEsp32S3 reaction.h:1259)
_WIFI_ALREADY_S3 = re.compile(rf"IP Address: {_IPV4}\. Wifi already connected")  # OpenCatEsp32S3 reaction.h:1279
_WIFI_FAILED_S3 = "Timeout: Fail to connect web server!"  # OpenCatEsp32S3 reaction.h:1270
_WIFI_FAILED = "Fail to connect Wifi!"  # USB only (src/reaction.h:477)
_VERSION = re.compile(r"[A-Z]\w*_\d{6}$")  # e.g. B10_260820, Q_261022
_UNDEFINED = "Undefined token!"  # firmware built without WEB_SERVER (src/reaction.h:1535)


class Robot:
    """A connected Petoi robot. Get one with petoi.connect().

    High-level methods raise RobotTimeout if the robot doesn't confirm.
    send()/send_binary() return the Reply and never raise on timeout.
    skill() waits up to skill_timeout, since one-shot skills confirm only when finished.
    """

    def __init__(self, transport: Transport, *, timeout: float = 5.0, skill_timeout: float = 30.0):
        self.transport = transport
        self.timeout = timeout
        self.skill_timeout = skill_timeout  # below Wi-Fi's 45 s task abort (src/webServer.h:53)
        self.model: Optional[str] = None  # set by connect()
        self.firmware: Optional[str] = None  # set by connect()
        self._lock = threading.Lock()

    @property
    def s3(self) -> bool:
        """True for OpenCatEsp32S3 firmware (e.g. Quaddle). Known after connect()."""
        return is_s3_firmware(self.firmware)

    # --- raw access -------------------------------------------------------

    def send(self, command: str, *, wait: bool = True, timeout: Optional[float] = None) -> Reply:
        """Send a serial-monitor style command, e.g. "ksit", "i 8 30", "d"."""
        if not command:
            raise ValueError("command is empty")
        body = command[:-2] if command.endswith("\r\n") else command[:-1] if command.endswith("\n") else command
        if "\n" in body:
            raise ValueError("command contains a newline; send one command per call")
        if "A" <= command[0] <= "Z":
            raise ValueError(f"{command[0]!r} is a binary command; use send_binary()")
        if "\r" in body:
            raise ValueError("command contains a carriage return; the firmware truncates at it (src/moduleManager.h:431)")
        payload = (command if command.endswith("\n") else command + "\n").encode()
        return self._run(command[0], payload, wait, timeout)

    def send_binary(self, token: str, *values: int, wait: bool = True, timeout: Optional[float] = None) -> Reply:
        """Send an uppercase (binary) command, e.g. send_binary("I", 8, -20).

        On S3 firmware over USB, I and M are never confirmed: the robot sends that echo to BLE and Wi-Fi only."""
        payload = encode(token, *values)
        if token in ("I", "M") and self.s3 and isinstance(self.transport, SerialTransport):
            with self._lock:  # OpenCatEsp32S3 reaction.h:2655-2657
                self.transport.write_command(payload)
            return Reply(token)
        return self._run(token, payload, wait, timeout)

    def _run(self, token: str, payload: bytes, wait: bool, timeout: Optional[float]) -> Reply:
        with self._lock:  # one command on the wire at a time
            return self.transport.command(token, payload, (self.timeout if timeout is None else timeout) if wait else 0)

    def _cmd(self, token: str, *args, wait: bool = True, timeout: Optional[float] = None) -> Reply:
        payload = encode(token, *args)
        reply = self._run(token, payload, wait, timeout)
        if wait and not reply.completed:
            shown = payload.decode(errors="replace").strip()
            limit = self.timeout if timeout is None else timeout
            raise RobotTimeout(f"robot did not confirm {shown!r} within {limit:g}s; check power and the connection")
        return reply

    # --- postures and skills ----------------------------------------------

    def skill(self, name: Union[Skill, str], *, wait: bool = True, timeout: Optional[float] = None) -> Reply:
        """Run a skill by name, e.g. Skill.HI or "hi"; waits until it finishes (up to skill_timeout).

        Raises ValueError for a Skill this model's firmware doesn't have (known after connect())."""
        key = model_key(self.model)
        if key is not None:
            member = name if isinstance(name, Skill) else next((s for s in Skill if s.value == name), None)
            if member is not None and member not in skills_for(key):
                # it would confirm at once without moving (Quaddle, 2026-11-06)
                raise ValueError(f"{member.value!r} is not a {self.model} skill; send('k{member.value}') sends it anyway")
        return self._cmd("k", name, wait=wait, timeout=self.skill_timeout if timeout is None else timeout)

    def _skill_layout(self) -> Tuple[int, Tuple[int, ...], int]:
        """(joint count, gait row widths, room for angle values) for this robot's firmware."""
        key = model_key(self.model)
        if key == "quaddle":  # DOF, WALKING_DOF, BUFF_LEN - 1 - CMD_LEN (OpenCatEsp32S3 OpenCat.h:155-165, :890, :902-907)
            return 6, (4,), 4096 - 1 - 20
        if key is not None:
            return DOF, (8,), _SKILL_ROOM  # WALKING_DOF (src/OpenCat.h:249-256)
        return DOF, (8, 12), _SKILL_ROOM

    def run_skill_data(self, data: Sequence[int], *, wait: bool = True, timeout: Optional[float] = None) -> Reply:
        """Upload a skill array in the Instinct*.h layout and run it; waits until a behavior ends."""
        try:
            values = [operator.index(v) for v in data]
        except TypeError:
            raise ValueError("skill data must be integers") from None
        dof, gait_widths, room = self._skill_layout()
        if dof == 6 and values[:1] == [-128]:  # Quaddle's 8-value extended header (OpenCatEsp32S3 configConstants.h:90-123)
            raise ValueError("Quaddle behaviors over 127 frames (extended header) aren't supported yet")
        _check_skill_data(values, dof, gait_widths, room)
        payload = encode("K", *values)
        # a behavior echoes K as it starts and again when it ends (src/reaction.h:1557, :1609); Wi-Fi sees only the first (:1565)
        stream = self.transport if values[0] < 0 and isinstance(self.transport, StreamTransport) else None
        if timeout is None:
            timeout = self.timeout
            if stream is not None:  # the robot is already at frame 0 when the behavior starts (src/reaction.h:1414)
                timeout += 1.5 * skill_seconds(values, [a * values[3] for a in values[7:7 + dof]], dof)
        with self._lock:
            reply = self.transport.command("K", payload, (self.timeout if stream is not None else timeout) if wait else 0)
            if stream is not None and (reply.completed or not wait):
                end = stream.expect("K", timeout if wait else 0)
                reply = Reply("K", reply.lines + end.lines, end.completed)
            elif stream is not None:
                stream.expect("K", 0)  # the start echo is late, so the end echo is still owed too
        if wait and not reply.completed:
            raise RobotTimeout("robot did not confirm the uploaded skill in time; check power and the connection")
        return reply

    def sit(self, *, wait: bool = True) -> Reply:
        """Sit down."""
        return self._cmd("k", Skill.SIT, wait=wait)

    def stand(self, *, wait: bool = True) -> Reply:
        """Stand up."""
        return self._cmd("k", Skill.STAND, wait=wait)

    def stop(self, *, wait: bool = True) -> Reply:
        """Stop walking and stand still."""
        return self._cmd("k", Skill.STAND, wait=wait)

    def rest(self, *, wait: bool = True) -> Reply:
        """Lie down and turn the servos off."""
        return self._cmd("d", wait=wait)

    # --- gaits (keep going until stop()) ---------------------------------
    # They echo when they start (src/reaction.h:1555-1565), so they keep the short timeout.

    def walk(self, direction: Direction = "forward", *, wait: bool = True) -> Reply:
        """Start walking forward, left or right until stop()."""
        return self._cmd("k", "wk" + _direction(direction), wait=wait)

    def trot(self, direction: Direction = "forward", *, wait: bool = True) -> Reply:
        """Start trotting forward, left or right until stop()."""
        return self._cmd("k", "tr" + _direction(direction), wait=wait)

    def crawl(self, direction: Direction = "forward", *, wait: bool = True) -> Reply:
        """Start crawling forward, left or right until stop()."""
        return self._cmd("k", "cr" + _direction(direction), wait=wait)

    def back(self, direction: Optional[Literal["left", "right"]] = None, *, wait: bool = True) -> Reply:
        """Start walking backward, straight or turning left or right, until stop()."""
        if direction not in (None, "left", "right"):
            raise ValueError(f"direction must be left, right or None, got {direction!r}")
        return self._cmd("k", "bk" + (_direction(direction) if direction else ""), wait=wait)

    # --- joints -----------------------------------------------------------

    def joint(self, index: Union[Joint, int], angle: float, *, wait: bool = True) -> Reply:
        """Move one joint to an angle in degrees (rounded to a whole degree)."""
        return self._cmd("i", index, _degrees(angle), wait=wait)

    def move_joints(self, angles: Dict[Union[Joint, int], float], *, sequential: bool = False, wait: bool = True) -> Reply:
        """Move several joints together, or one after another if sequential."""
        flat = [v for index, angle in angles.items() for v in (index, _degrees(angle))]
        return self._cmd("m" if sequential else "i", *flat, wait=wait)

    def joints(self) -> List[int]:
        """Read every joint's current angle, indexed like Joint."""
        reply = self._cmd("j")
        if not reply.lines:
            raise RobotError("no joint angles received")
        return parse_ints(reply.lines[-1])  # src/reaction.h:686

    # --- misc -------------------------------------------------------------

    def beep(self, note: int, duration: int) -> Reply:
        """Play one note: semitones above C6 (0 is a rest), lasting 1/duration s (8 = 125 ms).

        On S3 firmware (Quaddle) it returns as the note starts."""
        return self._cmd("b", note, duration)

    def melody(self, notes: Sequence[Tuple[int, int]], *, wait: bool = True) -> Reply:
        """Play (note, duration) pairs as in beep(); waits until the tune ends."""
        if not notes:
            raise ValueError("melody needs at least one note; a bare 'b' toggles all sound")  # src/reaction.h:967
        flat = []
        for pair in notes:
            if len(pair) != 2:
                raise ValueError(f"each note must be (note, duration), got {pair!r}")
            note, duration = pair
            if duration < 1:
                raise ValueError(f"duration must be at least 1, got {duration!r}")  # the firmware skips it (:1003)
            flat += [note, duration]
        length = sum(1 / d for _, d in notes)  # 1000/d ms per note (src/reaction.h:1004)
        reply = self._cmd("b", *flat, wait=wait, timeout=self.timeout + length)
        if self.s3 and wait:
            # S3 echoes as the tune starts and plays it on (Quaddle Q_261027, 2026-11-05: echo after 0.07 s).
            # Wait it all out from the echo: time before the echo (lock, pacing) isn't playback.
            time.sleep(length)
        return reply

    def gyro(self, on: bool) -> Reply:
        """Turn gyro balancing on or off. Turn it off before tricks it would fight."""
        return self._cmd("g", "B" if on else "b")  # explicit; bare 'g' toggles (src/reaction.h:503-506)

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

    def info(self) -> Dict[str, str]:
        """Return the robot's model and firmware version, e.g. {"model": "Bittle X", ...}."""
        reply = self._cmd("?")  # src/reaction.h:405-406
        lines = reply.lines
        # the version is BOARD_DATE (src/OpenCat.h:666); S3 can print unasked lines before the model
        at = next((i for i, line in enumerate(lines) if i and _VERSION.match(line)), 1)
        if len(lines) <= at:
            raise RobotError(f"unexpected reply to '?': {lines}")
        return {"model": lines[at - 1], "version": lines[at]}

    # --- Wi-Fi ------------------------------------------------------------

    def setup_wifi(self, ssid: str, password: str, *, timeout: float = 60.0) -> str:
        """Over USB, put the robot on a 2.4 GHz Wi-Fi network and return its IP address for petoi.connect().

        OpenCatEsp32 reboots to start its Wi-Fi server; OpenCatEsp32S3 starts it without rebooting."""
        _check_wifi(ssid, password)
        transport = self.transport
        from petoi.transports.ble import BleTransport  # the reboot drops BLE, and failures print to USB only (src/reaction.h:477)

        if not isinstance(transport, StreamTransport) or isinstance(transport, BleTransport):
            raise RobotError("setup_wifi() works over the USB cable; connect with petoi.connect() first")
        payload = f"w%{ssid}%{password}\n".encode()  # src/reaction.h:442-446
        ips: List[str] = []
        already: Optional[str] = None
        joined_now: Optional[str] = None
        failed = False
        with self._lock:
            transport.discard_input()
            transport._unconfirmed.clear()  # OpenCatEsp32 reboots; nothing sent earlier will echo now
            transport.write_command(payload, secret=True)
            deadline = time.monotonic() + timeout  # counted from sending, not from waiting for the lock
            # Never keep or show robot lines: they include the password's last 4 characters (src/reaction.h:449-458).
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
                    else:  # S3: the rest of the command (password included) follows on the next line (reaction.h:2621-2632)
                        while transport.readline(0.3) is not None:
                            pass
                        transport.discard_input()
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
        if ips:
            warnings.warn(f"the robot joined Wi-Fi but did not finish rebooting within {timeout:g}s",
                          RuntimeWarning, stacklevel=2)
            return ips[-1]
        raise RobotTimeout(f"robot did not report a Wi-Fi result within {timeout:g}s; check power and the USB cable")

    def close(self) -> None:
        """Close the connection. The with-statement does this for you."""
        self.transport.close()

    def __enter__(self) -> "Robot":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            if exc_type is not None:  # e.g. Ctrl-C mid-walk: don't leave it walking
                try:  # best effort, short wait; never mask the user's exception
                    self._run("k", encode("k", Skill.STAND), True, min(self.timeout, 1.0))
                except Exception:
                    pass
        finally:
            self.close()


def _direction(name: str) -> str:
    try:
        return _DIRECTIONS[name]
    except KeyError:
        raise ValueError(f"direction must be one of: {', '.join(_DIRECTIONS)}") from None


def _degrees(angle: float) -> int:
    return round(angle)  # the firmware's atoi would cut 30.7 to 30 (src/reaction.h:877)


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


def _check_skill_data(values: List[int], dof: int, gait_widths: Tuple[int, ...], room: int) -> None:
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
    widths = (dof,) if period == 1 else gait_widths if period > 1 else (dof + 4,)
    body = len(values) - header
    if body not in [frames * w for w in widths]:
        kind = "posture" if period == 1 else "gait" if period > 1 else "behavior"
        need = " or ".join(str(header + frames * w) for w in widths)
        raise ValueError(f"a {kind} with {frames} frames needs {need} values, got {len(values)}")
    if body > room:
        raise ValueError(f"skill data is too long: {body} angle values, the robot keeps at most {room}")
    if period < 0:
        start, end, cycles = values[4:7]
        if cycles < 0:
            raise ValueError("a loop count (seventh value) below 0 loops forever (src/skill.h:282); use 0 or 1 for no loop")
        if cycles >= 2 and not 0 <= start <= end < frames:
            raise ValueError(f"loop rows {start}..{end} must lie within the {frames} frames")
