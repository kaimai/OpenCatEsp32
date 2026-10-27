from __future__ import annotations

import base64
import inspect
import itertools
import json
import queue
import re
import threading
import time
from typing import List, Optional

from petoi.errors import ConnectionFailed, RobotError
from petoi.protocol import Reply, collect_reply
from petoi.transports.base import Transport

PORT = 81  # src/webServer.h:59
HEARTBEAT_SECONDS = 15  # firmware drops clients after 40 s of silence (src/webServer.h:51)


def to_web_command(payload: bytes) -> str:
    if payload[:1].isupper():
        return "b64:" + base64.b64encode(payload[:-1]).decode()  # drop '~'; firmware re-adds it
    return payload.decode().rstrip("\n")


_CLOSED = object()  # reader-thread sentinel: the connection is gone
_HAS_PORT = re.compile(r":\d+$")
_CLIENT_LIMIT_HINT = "(the robot allows at most 2 Wi-Fi clients; is the app connected?)"


class WebSocketTransport(Transport):
    """Wi-Fi link to the robot's WebSocket server.

    One background thread reads every incoming message into a queue, so unrelated
    traffic (heartbeat replies, sensor events) can't pile up in the socket or keep
    command() waiting past its deadline.
    """

    def __init__(self, host: str, port: int = PORT, timeout: float = 5.0, heartbeat: bool = True):
        try:
            from websockets.exceptions import ConnectionClosed
            from websockets.sync.client import connect
        except ImportError:
            raise ConnectionFailed('Wi-Fi needs an extra package: pip install "petoi[wifi]"') from None
        if host.startswith("ws://") or _HAS_PORT.search(host):
            url = host if host.startswith("ws://") else f"ws://{host}"
        else:
            url = f"ws://{host}:{port}"
        params = inspect.signature(connect).parameters
        kwargs = {}
        if "legacy" in params:
            kwargs["legacy"] = True  # websockets >= 17.1 warns on a direct connect() otherwise
        if "max_queue" in params:
            kwargs["max_queue"] = None  # the sync client has an unbounded queue before websockets 15 (12.0 has no such argument)
        try:
            self._ws = connect(url, open_timeout=timeout, **kwargs)
            hello = json.loads(self._ws.recv(timeout))
        except ConnectionClosed as e:
            raise ConnectionFailed(f"could not connect to {url}: {e} {_CLIENT_LIMIT_HINT}") from e
        except Exception as e:
            raise ConnectionFailed(f"could not connect to {url}: {e}") from e
        if hello.get("type") == "error":
            raise ConnectionFailed(hello.get("error", "robot refused the connection"))
        self._closed_errors = (ConnectionClosed, OSError)
        self._ids = itertools.count(1)
        self._default_timeout = timeout
        self._outstanding: List[str] = []  # task ids we sent that never completed
        self._messages: "queue.Queue[object]" = queue.Queue()
        self._stop = threading.Event()
        threading.Thread(target=self._read, daemon=True).start()
        if heartbeat:
            threading.Thread(target=self._beat, daemon=True).start()

    def _read(self) -> None:
        while True:
            try:
                raw = self._ws.recv()
            except Exception:  # ConnectionClosed, or the socket died under us
                self._messages.put(_CLOSED)
                return
            try:
                msg = json.loads(raw)
            except ValueError:
                continue
            if isinstance(msg, dict):
                self._messages.put(msg)

    def _beat(self) -> None:
        while not self._stop.wait(HEARTBEAT_SECONDS):
            try:
                self._ws.send(json.dumps({"type": "heartbeat"}))
            except Exception:
                return

    def command(self, token: str, payload: bytes, timeout: Optional[float]) -> Reply:
        # The firmware runs one web task at a time and rejects overlaps,
        # so Wi-Fi commands always wait for completion.
        deadline = time.monotonic() + (timeout or self._default_timeout)
        task_id = f"py-{next(self._ids)}"
        try:
            self._ws.send(json.dumps({"type": "command", "taskId": task_id, "commands": [to_web_command(payload)]}))
        except self._closed_errors as e:
            raise ConnectionFailed(f"lost Wi-Fi connection: {e}") from e
        previous = list(self._outstanding)
        self._outstanding.append(task_id)
        while True:
            try:
                msg = self._messages.get(timeout=max(deadline - time.monotonic(), 0))
            except queue.Empty:
                return Reply(token)
            if msg is _CLOSED:
                self._messages.put(_CLOSED)  # later calls fail too
                raise ConnectionFailed("lost Wi-Fi connection; reconnect with petoi.connect()")
            tid, status = msg.get("taskId"), msg.get("status")
            if status == "error" and tid in previous:
                # The firmware reports a rejected overlap with the RUNNING task's id
                # and aborts that task; ours was never stored (src/webServer.h:346-347, :487-512).
                self._outstanding.remove(tid)
                self._outstanding.remove(task_id)
                raise RobotError("robot is still busy with the previous command; wait for it to finish")
            if status == "completed" and tid in self._outstanding:
                self._outstanding.remove(tid)
            if tid != task_id:
                continue
            if status == "error":
                self._outstanding.remove(task_id)
                raise RobotError(msg.get("error", "command failed"))
            if status == "completed":
                # status "completed" is Wi-Fi's real completion signal, so add the echo in case results omit it
                lines = iter("".join(msg.get("results", [])).splitlines() + [token])
                return collect_reply(token, lambda: next(lines, None))

    def close(self) -> None:
        self._stop.set()
        self._ws.close()
