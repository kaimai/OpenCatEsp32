# Part I: cancel an abandoned BLE connect Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** When `BleTransport` gives up on a connection, make sure the operating system stops trying too, so the robot isn't left held by the computer and invisible to the next scan.

**Architecture:** `_cleanup()` calls `disconnect()` whenever a client exists, not only after a successful connect, and `_shutdown_loop()` cancels and waits for the loop's remaining tasks before stopping it.

**Tech Stack:** Python, bleak, pytest. Worktree `/Users/kaikai/projects/petoi codes/OpenCatEsp32-Quadruped-Robot - python-api`, branch `feature/python-api`, run from `python/`.

**GBrain:** MCP disconnected this session; query skipped.

---

## Evidence (2026-11-05, Quaddle Q_261027, macOS)

- 10 connects with a scan: 1 ok. 10 by address: 0 ok. The first scan attempt timed out in `client.connect()` after 15 s; every later scan found no robot, and every connect by address timed out.
- Each timeout printed `Task was destroyed but it is pending! ... BleakClient.connect()`: `_run()` cancels the future, `_cleanup()` skips `disconnect()` because `_connected` is still False, and `_shutdown_loop()` stops the loop before the cancelled connect task runs.
- Afterwards macOS's Bluetooth panel showed the robot as connected with no program running; the owner disconnected it by hand twice. A connected BLE peripheral stops advertising, which explains "no Petoi BLE robot found".
- **Assumption (unverified):** bleak's `disconnect()` on macOS cancels a pending connection (CoreBluetooth `cancelPeripheralConnection`). Task 3 checks it on the robot.

Not in scope: the 15 s connect limit (measure again after the fix), firmware.

### Task 0: Commit this plan

- [ ] `git add docs/superpowers/plans/2026-11-05-python-api-ble-abandoned-connect.md && git commit -m "Plan Part I: cancel an abandoned BLE connect"`

### Task 1: Failing tests (append to `python/tests/test_ble.py`)

```python
class HangingClient:
    """A bleak client whose connect() never finishes, like a robot macOS is slow to reach."""

    made = []

    def __init__(self, address):
        self.disconnects = 0
        self.cancelled = False
        HangingClient.made.append(self)

    async def connect(self):
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            self.cancelled = True
            raise

    async def disconnect(self):
        self.disconnects += 1


def test_abandoned_connect_is_cancelled_and_disconnected(monkeypatch):
    import sys
    import types

    monkeypatch.setattr(ble, "RUN_TIMEOUT", 0.1)
    monkeypatch.setitem(sys.modules, "bleak", types.SimpleNamespace(BleakClient=HangingClient))
    HangingClient.made.clear()
    with pytest.raises(ConnectionFailed, match="did not respond"):
        BleTransport("AA:BB")
    client = HangingClient.made[0]
    assert client.disconnects == 1  # tells the OS to stop connecting
    assert client.cancelled  # the connect task ran its cancellation before the loop stopped
```

- [ ] Run `.venv/bin/python -m pytest tests/test_ble.py -k abandoned -v`. Expected: FAIL (`disconnects == 0`).

### Task 2: Fix (`python/src/petoi/transports/ble.py`)

```python
    def _cleanup(self) -> None:
        if self._client is not None:  # also after a failed or abandoned connect, so the OS stops trying
            try:
                self._run(self._client.disconnect())
            except Exception:
                pass
            self._connected = False
        self._shutdown_loop()
```

```python
    def _shutdown_loop(self) -> None:
        if self._loop.is_closed():
            return

        async def finish_tasks():  # let a cancelled connect clean up instead of being destroyed pending
            tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
            for t in tasks:
                t.cancel()
            if tasks:
                await asyncio.wait(tasks, timeout=2)

        try:
            asyncio.run_coroutine_threadsafe(finish_tasks(), self._loop).result(timeout=3)
        except Exception:
            pass
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=2)
        if not self._thread.is_alive():
            self._loop.close()
```

- [ ] Run `tests/test_ble.py`, the whole suite, mypy. Expected: all pass. `test_close_twice_is_harmless` still sees one disconnect.
- [ ] Commit: "BLE: cancel and disconnect an abandoned connect, so the computer doesn't keep the robot".

### Task 3: Check on the robot (owner present)

- [ ] Owner makes sure the Mac's Bluetooth panel shows the robot not connected.
- [ ] Rerun the 10-by-scan / 10-by-address comparison (`scratchpad/ble_compare.py`). Expected: no `Task was destroyed` lines, and the panel doesn't show the robot connected afterwards. Record counts and times in `python/TODO.md` (BLE item), and whether the 15 s connect limit is still hit.
- [ ] If counts are still poor, stop and report; don't tune timeouts blind.
- [ ] Commit the TODO. Don't push without asking.
