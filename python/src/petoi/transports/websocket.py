from __future__ import annotations

import base64
import inspect
import itertools
import json
import threading
from typing import Optional

from petoi.errors import ConnectionFailed, RobotError
from petoi.protocol import Reply, collect_reply
from petoi.transports.base import Transport

PORT = 81  # src/webServer.h:59
HEARTBEAT_SECONDS = 15  # firmware drops clients after 40 s of silence (src/webServer.h:51)


def to_web_command(payload: bytes) -> str:
    if payload[:1].isupper():
        return "b64:" + base64.b64encode(payload[:-1]).decode()  # drop '~'; firmware re-adds it
    return payload.decode().rstrip("\n")


class WebSocketTransport(Transport):
    """Wi-Fi link to the robot's WebSocket server."""

    def __init__(self, host: str, port: int = PORT, timeout: float = 5.0, heartbeat: bool = True):
        try:
            from websockets.sync.client import connect
        except ImportError:
            raise ConnectionFailed('Wi-Fi needs an extra package: pip install "petoi[wifi]"') from None
        url = host if host.startswith("ws://") else f"ws://{host}:{port}"
        try:
            kwargs = {}
            if "legacy" in inspect.signature(connect).parameters:
                kwargs["legacy"] = True  # websockets >= 17.1 warns on a direct connect() otherwise
            self._ws = connect(url, open_timeout=timeout, **kwargs)
            hello = json.loads(self._ws.recv(timeout))
        except Exception as e:
            raise ConnectionFailed(f"could not connect to {url}: {e}") from e
        if hello.get("type") == "error":
            raise ConnectionFailed(hello.get("error", "robot refused the connection"))
        self._ids = itertools.count(1)
        self._default_timeout = timeout
        self._stop = threading.Event()
        if heartbeat:
            threading.Thread(target=self._beat, daemon=True).start()

    def _beat(self) -> None:
        while not self._stop.wait(HEARTBEAT_SECONDS):
            try:
                self._ws.send(json.dumps({"type": "heartbeat"}))
            except Exception:
                return

    def command(self, token: str, payload: bytes, timeout: Optional[float]) -> Reply:
        # The firmware runs one web task at a time and rejects overlaps,
        # so Wi-Fi commands always wait for completion.
        timeout = timeout or self._default_timeout
        task_id = f"py-{next(self._ids)}"
        self._ws.send(json.dumps({"type": "command", "taskId": task_id, "commands": [to_web_command(payload)]}))
        while True:
            try:
                msg = json.loads(self._ws.recv(timeout))
            except TimeoutError:
                return Reply(token)
            if msg.get("taskId") != task_id:
                continue
            if msg.get("status") == "error":
                raise RobotError(msg.get("error", "command failed"))
            if msg.get("status") == "completed":
                # status "completed" is Wi-Fi's real completion signal, so add the echo in case results omit it
                lines = iter("".join(msg.get("results", [])).splitlines() + [token])
                return collect_reply(token, lambda: next(lines, None))

    def close(self) -> None:
        self._stop.set()
        self._ws.close()
