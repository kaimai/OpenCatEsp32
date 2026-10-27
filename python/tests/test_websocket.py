import base64
import json
import threading

import pytest
from websockets.sync.server import serve

from petoi.errors import ConnectionFailed, RobotError
from petoi.transports.websocket import WebSocketTransport, to_web_command

received = []


def firmware(ws):
    ws.send(json.dumps({"type": "connected", "clientId": "0"}))
    running = None  # the task the fake is "executing" forever
    for raw in ws:
        msg = json.loads(raw)
        if msg["type"] != "command":
            continue
        received.append(msg)
        task = msg["taskId"]
        if msg["commands"] == ["slow"]:
            running = task
            ws.send(json.dumps({"type": "response", "taskId": task, "status": "running"}))
            continue
        if running and msg["commands"] == ["bad"]:
            # Real firmware: errorWebTask() reports the RUNNING task's id and aborts it;
            # the new task is never stored (src/webServer.h:346-347, :487-512)
            ws.send(json.dumps({"type": "response", "taskId": running, "status": "error",
                                "error": "Previous web task is still running"}))
            running = None
            continue
        ws.send(json.dumps({"type": "response", "taskId": "someone-else", "status": "completed", "results": []}))
        ws.send(json.dumps({"type": "response", "taskId": task, "status": "running"}))
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


def test_rejection_error_carries_running_tasks_id(port):
    t = WebSocketTransport("127.0.0.1", port=port, heartbeat=False)
    assert t.command("s", b"slow\n", timeout=0.2).completed is False
    with pytest.raises(RobotError, match="still busy with the previous command"):
        t.command("b", b"bad\n", timeout=2.0)
    t.close()


def test_host_with_port_is_not_given_a_second_port(port):
    t = WebSocketTransport(f"127.0.0.1:{port}", heartbeat=False)
    assert t.command("?", b"?\n", timeout=2.0).completed
    t.close()


def serve_with(handler):
    return serve(handler, "127.0.0.1", 0)


def run_server(handler):
    srv = serve_with(handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.socket.getsockname()[1]


def test_unrelated_traffic_cannot_keep_command_waiting_forever():
    import time

    def noisy(ws):
        ws.send(json.dumps({"type": "connected"}))
        end = time.monotonic() + 3
        try:
            while time.monotonic() < end:
                ws.send(json.dumps({"type": "event_us", "distance": 40}))
                time.sleep(0.05)
        except Exception:
            pass

    srv, p = run_server(noisy)
    t = WebSocketTransport("127.0.0.1", port=p, heartbeat=False)
    start = time.monotonic()
    assert t.command("k", b"ksit\n", timeout=0.5).completed is False
    assert time.monotonic() - start < 1.0
    t.close()
    srv.shutdown()


def test_connection_closing_mid_command_raises_connection_failed():
    def closer(ws):
        ws.send(json.dumps({"type": "connected"}))
        for _ in ws:
            ws.close()
            return

    srv, p = run_server(closer)
    t = WebSocketTransport("127.0.0.1", port=p, heartbeat=False)
    with pytest.raises(ConnectionFailed, match="lost Wi-Fi connection"):
        t.command("k", b"ksit\n", timeout=2.0)
    t.close()
    srv.shutdown()


def test_hello_failure_mentions_client_limit():
    srv, p = run_server(lambda ws: None)  # closes without a hello
    with pytest.raises(ConnectionFailed, match="at most 2 Wi-Fi clients"):
        WebSocketTransport("127.0.0.1", port=p, heartbeat=False)
    srv.shutdown()
