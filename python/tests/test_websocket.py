import base64
import json
import logging
import threading

import pytest
from websockets.sync.server import serve

from petoi.errors import ConnectionFailed, RobotError
from petoi.transports.websocket import WebSocketTransport, to_web_command

received = []


def firmware(ws):
    ws.send(json.dumps({"type": "connected", "clientId": "0"}))
    running = None  # the task the fake is "executing" forever
    timed_out = None  # a task whose firmware-side timeout fires before the next command
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
        if msg["commands"] == ["late"]:
            timed_out = task
            ws.send(json.dumps({"type": "response", "taskId": task, "status": "running"}))
            continue
        if timed_out:
            # WEB_TASK_EXECUTION_TIMEOUT fired for it before this command (src/webServer.h:720-726)
            ws.send(json.dumps({"taskId": timed_out, "status": "error", "error": "Task timeout"}))
            timed_out = None
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


def test_busy_robot_aborts_the_old_task_and_runs_the_retry(port):
    t = WebSocketTransport("127.0.0.1", port=port, heartbeat=False)
    assert t.command("s", b"slow\n", timeout=0.2).completed is False
    reply = t.command("b", b"bad\n", timeout=2.0)  # rejected once, which aborts "slow"; the retry runs
    assert reply.completed
    assert [m["commands"] for m in received] == [["slow"], ["bad"], ["bad"]]
    t.close()


def test_old_task_timeout_does_not_resend_the_next_command(port):
    t = WebSocketTransport("127.0.0.1", port=port, heartbeat=False)
    assert t.command("l", b"late\n", timeout=0.2).completed is False
    assert t.command("k", b"khi\n", timeout=2.0).completed
    assert [m["commands"] for m in received] == [["late"], ["khi"]]  # not sent twice
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
                try:
                    ws.recv(timeout=0.05)  # drain input so the client's close handshake isn't stuck
                except TimeoutError:
                    pass
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


def test_non_dict_hello_is_rejected_and_connection_closed():
    seen = {}

    def odd(ws):
        ws.send("[1, 2]")
        try:
            ws.recv(timeout=2)
        except Exception as e:  # closed by the client
            seen["closed"] = type(e).__name__

    srv, p = run_server(odd)
    with pytest.raises(ConnectionFailed, match="unexpected greeting"):
        WebSocketTransport("127.0.0.1", port=p, heartbeat=False)
    import time
    for _ in range(40):
        if "closed" in seen:
            break
        time.sleep(0.05)
    assert seen.get("closed") == "ConnectionClosedOK"
    srv.shutdown()


def test_wifi_traffic_is_logged_at_debug(port, caplog):
    caplog.set_level(logging.DEBUG, logger="petoi")
    t = WebSocketTransport("127.0.0.1", port=port, heartbeat=False)
    t.command("?", b"?\n", timeout=2.0)
    t.close()
    assert "-> ?" in caplog.text
    assert "Bittle X" in caplog.text
