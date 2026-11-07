# Part J: discover only the UART service over BLE Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Connect to a Quaddle over BLE in about 1 s instead of timing out, by asking bleak to discover only the Nordic UART service that `petoi` uses.

**Architecture:** `BleTransport` passes `services=[UART_SERVICE]` to `bleak.BleakClient`. Nothing else changes: both characteristics `petoi` uses (`ROBOT_RX`, `ROBOT_TX`) are in that service, on BiBoard and S3 firmware alike.

**Tech Stack:** Python, bleak (>= 0.22, already the floor), pytest. Worktree `/Users/kaikai/projects/petoi codes/OpenCatEsp32-Quadruped-Robot - python-api`, branch `feature/python-api`, run from `python/`.

**GBrain:** MCP disconnected this session; query skipped.

---

## Evidence (2026-11-06, Quaddle Q_261027, macOS, bleak 3.0.2, mouse mode off with `Xo`)

- `ble_compare.py` through `petoi`: 0 of 10 by scan, 0 of 10 by address; every connect hit the 15 s `RUN_TIMEOUT`.
- Plain bleak with a 40 s timeout: 4 of 4 connected, each in 31.1-31.3 s.
- bleak debug log: link up at 0.5 s, UART service and its descriptors done by 1.1 s, then `Retrieving characteristics for service 180A` (Device Information) took 30.0 s, the Bluetooth ATT transaction timeout. The rest finished in 0.2 s. 180A holds the PnP ID (2A50) and manufacturer (2A29) that the S3 firmware's HID mouse adds (OpenCatEsp32S3 `mouse.h:71-82`, attached at `petoiBleUartNimble.h:447`), so the robot apparently never answers one discovery request in it. Why it doesn't answer is not known.
- Plain bleak with `services=["6E400001-..."]`: 2 of 2 connected in 0.9 s. A third attempt found no robot for 20 s after the previous disconnect 3 s earlier, then the next scan found it after 5 s. Not explained; firmware sets `advertiseOnDisconnect(false)` and restarts advertising itself.
- Assumption (unverified): other bleak backends (BlueZ, WinRT) honour or safely ignore `services=`; bleak's docstring says filtering is applied "depending on if the OS supports such filtering". Not tested on Linux or Windows.

Not in scope: the re-advertise gap after a disconnect, the 15 s connect limit, firmware.

### Task 0: Commit this plan

- [ ] `git add docs/superpowers/plans/2026-11-06-python-api-ble-uart-only-discovery.md && git commit -m "Plan Part J: discover only the UART service over BLE"`

### Task 1: Failing test (append to `python/tests/test_ble.py`)

```python
class RecordingClient:
    """A bleak client that records how it was made and fails to connect, ending __init__ early."""

    made = []

    def __init__(self, address, **kwargs):
        self.kwargs = kwargs
        RecordingClient.made.append(self)

    async def connect(self):
        raise OSError("no robot here")

    async def disconnect(self):
        pass


def test_discovers_only_the_uart_service(monkeypatch):
    import sys
    import types

    monkeypatch.setitem(sys.modules, "bleak", types.SimpleNamespace(BleakClient=RecordingClient))
    RecordingClient.made.clear()
    with pytest.raises(ConnectionFailed):
        BleTransport("AA:BB")
    # S3 firmware stalls discovery of its HID Device Information service for 30 s (Part J)
    assert RecordingClient.made[0].kwargs["services"] == [ble.UART_SERVICE]
```

- [ ] Run `.venv/bin/python -m pytest tests/test_ble.py -k uart_service -v`. Expected: FAIL (`AttributeError: ... UART_SERVICE` or `KeyError: 'services'`).

### Task 2: Fix (`python/src/petoi/transports/ble.py`)

Constants, replacing the first lines of the UART block:

```python
# Nordic UART, src/bleCommon.h:6-8
UART_SERVICE = "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
ROBOT_RX = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"  # we write here
ROBOT_TX = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"  # robot notifies here
```

In `__init__`:

```python
            # only the UART: S3 firmware leaves macOS waiting 30 s on its HID Device Information service
            self._client = bleak.BleakClient(address, services=[UART_SERVICE])
```

- [ ] Check `UART_SERVICE` against `src/bleCommon.h` and OpenCatEsp32S3 `PETOI_UART_SERVICE_UUID`.
- [ ] Run `tests/test_ble.py`, the whole suite, mypy. Expected: all pass (`HangingClient.__init__(self, address)` must accept the new keyword: change it to `__init__(self, address, **kwargs)`).
- [ ] Commit: "BLE: discover only the UART service, so a Quaddle connects in about a second".

### Task 3: Check on the robot (owner present)

- [ ] Rerun `scratchpad/ble_compare.py` (10 by scan, 10 by address). Expected: most connects succeed in a few seconds. Record counts and times.
- [ ] Update `python/TODO.md`: replace the "macOS keeps the BLE link" firmware item with the 180A finding, keep the earlier observation (robot held for 60+ s, with mouse mode in an unknown state because `Xm` is not the mouse command; `XO`/`Xo` are, `OpenCat.h:760-761`), and add the re-advertise gap as an open item.
- [ ] If counts are still poor, stop and report.
- [ ] Commit the TODO. Don't push without asking.
