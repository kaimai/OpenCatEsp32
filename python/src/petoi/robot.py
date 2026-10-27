from __future__ import annotations

import re
import threading
from typing import Dict, List, Literal, Optional, Sequence, Tuple, Union

from petoi.constants import Joint, Skill
from petoi.errors import RobotError, RobotTimeout
from petoi.protocol import Reply, encode, parse_ints
from petoi.transports.base import Transport

Direction = Literal["forward", "left", "right"]
_DIRECTIONS = {"forward": "F", "left": "L", "right": "R"}  # 'R' mirrors 'L' (src/skill.h:501)
_GYRO_FLAGS = {"Update": "update", "Balance": "balance", "Print": "print", "Frequency": "fine"}  # src/reaction.h:609-612
_CALIBRATE_SECONDS = 20  # 6 s of beeps, up to 10 s calibrating, 3 s settling (src/reaction.h:519-562)


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
        self.model: Optional[str] = None  # set by connect()
        self.firmware: Optional[str] = None  # set by connect()
        self._lock = threading.Lock()

    # --- raw access -------------------------------------------------------

    def send(self, command: str, wait: bool = True, timeout: Optional[float] = None) -> Reply:
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
        """Send an uppercase (binary) command, e.g. send_binary("I", 8, -20)."""
        return self._run(token, encode(token, *values), wait, timeout)

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

    def rest(self, wait: bool = True) -> Reply:
        """Lie down and turn the servos off."""
        return self._cmd("d", wait=wait)

    # --- gaits (keep going until stop()) ---------------------------------
    # They echo when they start (src/reaction.h:1555-1565), so they keep the short timeout.

    def walk(self, direction: Direction = "forward", wait: bool = True) -> Reply:
        """Start walking forward, left or right until stop()."""
        return self._cmd("k", "wk" + _direction(direction), wait=wait)

    def trot(self, direction: Direction = "forward", wait: bool = True) -> Reply:
        """Start trotting forward, left or right until stop()."""
        return self._cmd("k", "tr" + _direction(direction), wait=wait)

    def crawl(self, direction: Direction = "forward", wait: bool = True) -> Reply:
        """Start crawling forward, left or right until stop()."""
        return self._cmd("k", "cr" + _direction(direction), wait=wait)

    def back(self, direction: Optional[Literal["left", "right"]] = None, wait: bool = True) -> Reply:
        """Start walking backward, straight or turning left or right, until stop()."""
        if direction not in (None, "left", "right"):
            raise ValueError(f"direction must be left, right or None, got {direction!r}")
        return self._cmd("k", "bk" + (_direction(direction) if direction else ""), wait=wait)

    # --- joints -----------------------------------------------------------

    def joint(self, index: Union[Joint, int], angle: float, wait: bool = True) -> Reply:
        """Move one joint to an angle in degrees (rounded to a whole degree)."""
        return self._cmd("i", index, _degrees(angle), wait=wait)

    def move_joints(self, angles: Dict[Union[Joint, int], float], sequential: bool = False, wait: bool = True) -> Reply:
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
        """Play one note: semitones above C6 (0 is a rest), lasting 1/duration s (8 = 125 ms)."""
        return self._cmd("b", note, duration)

    def melody(self, notes: Sequence[Tuple[int, int]], wait: bool = True) -> Reply:
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
        return self._cmd("b", *flat, wait=wait, timeout=self.timeout + length)

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
        if len(reply.lines) < 2:
            raise RobotError(f"unexpected reply to '?': {reply.lines}")
        return {"model": reply.lines[0], "version": reply.lines[1]}

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
