from __future__ import annotations

import threading
from typing import Dict, List, Literal, Optional, Union

from petoi.constants import Joint, Skill
from petoi.errors import PetoiError, RobotError, RobotTimeout
from petoi.protocol import Reply, encode, parse_ints
from petoi.transports.base import Transport

Direction = Literal["forward", "left", "right"]
_DIRECTIONS = {"forward": "F", "left": "L", "right": "R"}  # 'R' mirrors 'L' (src/skill.h:501)


class Robot:
    """A connected Petoi robot. Get one with petoi.connect().

    High-level methods raise RobotTimeout if the robot doesn't confirm.
    send()/send_binary() return the Reply and never raise on timeout.
    """

    def __init__(self, transport: Transport, timeout: float = 5.0):
        self.transport = transport
        self.timeout = timeout
        self.model: Optional[str] = None  # set by connect()
        self.firmware: Optional[str] = None  # set by connect()
        self._lock = threading.Lock()

    # --- raw access -------------------------------------------------------

    def send(self, command: str, wait: bool = True, timeout: Optional[float] = None) -> Reply:
        """Send a serial-monitor style command, e.g. "ksit", "i 8 30", "d"."""
        if not command:
            raise ValueError("command is empty")
        payload = (command if command.endswith("\n") else command + "\n").encode()
        return self._run(command[0], payload, wait, timeout)

    def send_binary(self, token: str, *values: int, wait: bool = True, timeout: Optional[float] = None) -> Reply:
        """Send an uppercase (binary) command, e.g. send_binary("I", 8, -20)."""
        return self._run(token, encode(token, *values), wait, timeout)

    def _run(self, token: str, payload: bytes, wait: bool, timeout: Optional[float]) -> Reply:
        with self._lock:  # one command on the wire at a time
            return self.transport.command(token, payload, (timeout or self.timeout) if wait else 0)

    def _cmd(self, token: str, *args, wait: bool = True) -> Reply:
        payload = encode(token, *args)
        reply = self._run(token, payload, wait, None)
        if wait and not reply.completed:
            shown = payload.decode(errors="replace").strip()
            raise RobotTimeout(f"robot did not confirm {shown!r} within {self.timeout}s; check power and the connection")
        return reply

    # --- postures and skills ----------------------------------------------

    def skill(self, name: Union[Skill, str], wait: bool = True) -> Reply:
        return self._cmd("k", name, wait=wait)

    def sit(self) -> Reply:
        return self.skill(Skill.SIT)

    def stand(self) -> Reply:
        return self.skill(Skill.STAND)

    def stop(self) -> Reply:
        """Stop walking and stand still."""
        return self.skill(Skill.STAND)

    def rest(self) -> Reply:
        """Lie down and turn the servos off."""
        return self._cmd("d")

    # --- gaits (keep going until stop()) ---------------------------------

    def walk(self, direction: Direction = "forward") -> Reply:
        return self.skill("wk" + _direction(direction))

    def trot(self, direction: Direction = "forward") -> Reply:
        return self.skill("tr" + _direction(direction))

    def crawl(self, direction: Direction = "forward") -> Reply:
        return self.skill("cr" + _direction(direction))

    def back(self) -> Reply:
        return self.skill("bk")

    # --- joints -----------------------------------------------------------

    def joint(self, index: Union[Joint, int], angle: int) -> Reply:
        return self._cmd("i", index, angle)

    def move_joints(self, angles: Dict[Union[Joint, int], int], sequential: bool = False) -> Reply:
        """Move several joints together, or one after another if sequential."""
        flat = [v for pair in angles.items() for v in pair]
        return self._cmd("m" if sequential else "i", *flat)

    def joints(self) -> List[int]:
        reply = self._cmd("j")
        if not reply.lines:
            raise RobotError("no joint angles received")
        return parse_ints(reply.lines[-1])  # src/reaction.h:686

    # --- misc -------------------------------------------------------------

    def beep(self, note: int, duration: int) -> Reply:
        return self._cmd("b", note, duration)

    def info(self) -> Dict[str, str]:
        reply = self._cmd("?")  # src/reaction.h:405-406
        if len(reply.lines) < 2:
            raise RobotError(f"unexpected reply to '?': {reply.lines}")
        return {"model": reply.lines[0], "version": reply.lines[1]}

    def close(self) -> None:
        self.transport.close()

    def __enter__(self) -> "Robot":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            if exc_type is not None:  # e.g. Ctrl-C mid-walk: don't leave it walking
                try:
                    self.stop()
                except PetoiError:
                    pass
        finally:
            self.close()


def _direction(name: str) -> str:
    try:
        return _DIRECTIONS[name]
    except KeyError:
        raise ValueError(f"direction must be one of: {', '.join(_DIRECTIONS)}") from None
