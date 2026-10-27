import base64
import json
import threading

import pytest
from websockets.sync.server import serve

from petoi.errors import RobotError
from petoi.transports.websocket import WebSocketTransport, to_web_command

received = []


def firmware(ws):
    ws.send(json.dumps({"type": "connected", "clientId": "0"}))
    for raw in ws:
        msg = json.loads(raw)
        if msg["type"] != "command":
            continue
        received.append(msg)
        task = msg["taskId"]
        ws.send(json.dumps({"type": "response", "taskId": "someone-else", "status": "completed", "results": []}))
        ws.send(json.dumps({"type": "response", "taskId": task, "status": "running"}))
        if msg["commands"] == ["bad"]:
            ws.send(json.dumps({"type": "response", "taskId": task, "status": "error", "error": "Previous web task is still running"}))
        else:
            ws.send(json.dumps({"type": "response", "taskId": task, "status": "completed",
                                "results": ["=\r\nBittle X\r\nB10_260820\r\n?\r\n"]}))


@pytest.fixture
def port():
    received.clear()
    with serve(firmware, "127.0.0.1", 0) as srv:
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        yield srv.socket.getsockname()[1]
        srv.shutdown()


def test_ascii_command_strips_newline():
    assert to_web_command(b"ksit\n") == "ksit"


def test_binary_command_is_base64_without_tilde():
    # webServer.h:380-400 — firmware decodes b64 and appends '~' itself
    assert to_web_command(b"I\x08\xec~") == "b64:" + base64.b64encode(b"I\x08\xec").decode()


def test_command_round_trip_ignores_other_tasks(port):
    t = WebSocketTransport("127.0.0.1", port=port, heartbeat=False)
    reply = t.command("?", b"?\n", timeout=2.0)
    t.close()
    assert received[0]["commands"] == ["?"]
    assert reply.completed
    assert reply.lines == ["Bittle X", "B10_260820"]


def test_firmware_error_raises(port):
    t = WebSocketTransport("127.0.0.1", port=port, heartbeat=False)
    with pytest.raises(RobotError, match="still running"):
        t.command("b", b"bad\n", timeout=2.0)
    t.close()
