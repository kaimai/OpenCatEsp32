# petoi JavaScript API: design

Status: draft for owner review, 2026-11-07. Sections 1-2 were walked through with the owner; sections 3-5 are written here for the first time and need review. Background, owner decisions and the API research: `2026-11-06-javascript-api-notes.md`.

## Goal

A browser library that controls Petoi robots over USB, Bluetooth and Wi-Fi, with the same methods and behavior as the `petoi` Python package (`python/`), so PetoiWebCoding can replace its per-page robot code with one tested client.

## Decisions (owner, 2026-11-06 and 2026-11-07)

- Lives in `javascript/`, next to `python/`, on `feature/python-api`.
- Browser only. Node is used only for development (build and tests).
- TypeScript source, built into `dist/petoi.js` (a plain script that adds a global `Petoi`), `dist/petoi.mjs` (ES module) and `dist/petoi.d.ts` (types). The built files are committed, so PetoiWebCoding loads them with no build step.
- Publishing to npm: not decided; not needed for PetoiWebCoding.
- Names follow JavaScript style (`runSkillData`), with Python's methods and behavior.
- Tests run in Node against fake browser links; protocol cases live in one data file read by both the Python and the JavaScript tests.
- Scope: the API only. Moving PetoiWebCoding onto it is a separate project for its maintainers.
- Approach: port Python's structure part by part (not reshaping PetoiWebCoding's code, not running Python in the browser).

## Not in this project

npm publishing; Node as a runtime; converting PetoiWebCoding pages; reconnecting Bluetooth without a picker; Python design gaps 4-7 from the notes (getter/setter names, firmware beep units, mixed failure styles stay as in Python).

## 1. Files and the public API

| File | Job | Python counterpart |
|---|---|---|
| `src/protocol.ts` | command encoding, which reply means done, splitting incoming text into lines | `protocol.py` |
| `src/links/stream.ts` | shared logic for text links: the 50 ms gap between commands, late echoes from earlier commands | `transports/base.py` |
| `src/links/serial.ts` | USB and Bluetooth Classic through Web Serial | `transports/serial.py` |
| `src/links/ble.ts` | Bluetooth LE through Web Bluetooth | `transports/ble.py` |
| `src/links/websocket.ts` | Wi-Fi | `transports/websocket.py` |
| `src/links/mock.ts` | fake robot | `transports/mock.py` |
| `src/robot.ts` | `Robot` and its commands | `robot.py` |
| `src/connect.ts` | the connect functions, then the `?` check, firmware warning and S3 `z0` | `connect.py` |
| `src/constants.ts`, `src/errors.ts`, `src/timing.ts` | skills, joints, model tables; error types; skill duration | same names |
| `src/index.ts` | everything public | `__init__.py` |
| `dist/` | built files, committed | n/a |

Example page:

```html
<script src="petoi.js"></script>
<script>
  connectButton.onclick = async () => {
    const robot = await Petoi.requestUsb();   // Chrome shows its port picker
    await robot.skill("hi");
    await robot.walk("forward", { wait: false });
    await robot.stand();
    await robot.close();
  };
</script>
```

`Robot` methods: `send`, `sendBinary`, `skill`, `runSkillData`, `sit`, `stand`, `stop`, `rest`, `walk`, `trot`, `crawl`, `back`, `joint`, `moveJoints`, `joints`, `beep`, `melody`, `gyro`, `gyroState`, `calibrateGyro`, `info`, `setupWifi`, `close`.

- Every command returns a Promise.
- Optional settings go in one object last: `{ wait, timeoutMs, signal }` (plus `sequential` for `moveJoints`). Time is in milliseconds, and the names say so.
- `model`, `firmware` and `s3` are read-only.
- One command at a time per robot: a second call waits its turn, as Python's lock does.
- Skills are strings (`"hi"`) with a TypeScript union for autocompletion. `Petoi.Skill.HI` and joint constants (`Petoi.Joint`, `Petoi.QuaddleJoint`) mirror Python's enums.
- `skill()` refuses a known skill the robot's model lacks, as Python does since d8969c9.
- `Reply` has the same fields as Python's (`token`, `lines`, `completed`, `text`).

## 2. Connecting

Browsers open a device picker only inside a user's click, so connecting is split:

| Function | Needs a click? | What it does |
|---|---|---|
| `Petoi.requestUsb(options?)` | yes | Chrome's port picker, filtered to Petoi's USB chips (list from PetoiWebCoding `skill_composer.html:863`) and Bluetooth serial (`bluetoothServiceClassId: 0x1101`, dropped if the browser rejects it, as `skill_composer.html:893` does); then `connectUsb` |
| `Petoi.usbPorts()` | no | ports this site was already allowed (`navigator.serial.getPorts()`) |
| `Petoi.connectUsb(port, options?)` | no | opens at 115200 and waits for boot as Python does (1.5 s of silence, or `Ready!`, up to 20 s; no wait for Bluetooth serial) |
| `Petoi.requestBle(options?)` | yes | Chrome's Bluetooth picker; connects to the Nordic UART service only |
| `Petoi.connectWifi(address, options?)` | no | `ws://<address>:81` |
| `Petoi.connectMock(options?)` | no | fake robot |
| `Petoi.supports()` | no | `{ usb, ble, wifi }` |

Options: `{ timeoutMs = 5000, checkFirmware = true, onWarning, debug }` (the last two are in section 3).

After any link opens, the same steps as Python's `connect()`: ask `?` (retry once, for a sleeping Quaddle), warn about firmware older than `260820`, send `z0` on S3 firmware. If any step throws, the link is closed before the error reaches the page.

Failures:

- No Web Serial or Web Bluetooth (Safari, Firefox, phones): `ConnectionFailed` saying the browser lacks it, distinct from "no robot found".
- The user closes the picker: `ConnectionFailed` ("no robot was chosen") with the browser's error as `cause`. No second, unfiltered picker.
- Wi-Fi from an `https://` page: Chrome blocks `ws://` there, so `ConnectionFailed` explains that the page must be served over `http://` or from `localhost`.
- Wi-Fi refused because two clients are connected: the same hint as Python.

Unverified, check on hardware first:

- The Bluetooth picker filter. Python matches `_BLE` anywhere in the name; Web Bluetooth matches only a name prefix or an advertised service. The filter offers the UART service and PetoiWebCoding's prefixes (`Petoi`, `Bittle`, `Nybble`, `BiBoard`, `OpenCat`, `PetoiCamp`, `mobile_remote.html:826`). Whether a Quaddle matches either is not known.
- Bluetooth Classic through Web Serial: never tried with this code.
- Whether opening a Web Serial port resets the board the way some pyserial settings did.

## 3. Errors, cancelling, warnings, debugging

**Errors.** `PetoiError` (extends `Error`) > `ConnectionFailed`, `RobotError` > `RobotTimeout`, `WifiSetupFailed`. Each sets `name`, so `err.name === "RobotTimeout"` works across the global build and the module build. Where Python raises `ValueError`, JavaScript throws `RangeError` for out-of-range or disallowed values and `TypeError` for wrong kinds of value; the messages are Python's.

High-level methods reject with `RobotTimeout` when the robot doesn't confirm; `send()` and `sendBinary()` resolve with `completed: false` and never reject on a timeout, as in Python.

**Cancelling with `signal`.** Any command accepts an `AbortSignal`:

- Already aborted: rejects at once, nothing is sent.
- Aborted while waiting its turn: removed from the queue, nothing is sent.
- Aborted after it was sent: stops waiting, sends `kup` (stand) with a wait of at most 1 s, then rejects with `signal.reason`. This is Python's `with` block leaving on an error.
- `setupWifi` is the exception: aborting stops waiting but sends nothing, since the robot isn't moving.

**Disconnects.** `Robot` is an `EventTarget` and fires `disconnect` once when the cable is pulled, the Bluetooth link drops (`gattserverdisconnected`) or the socket closes. Waiting and later commands reject with `ConnectionFailed`.

**`close()`.** Cancels the pending read, releases the Web Serial reader and writer locks, then closes the port, GATT connection or socket. Waiting commands reject with `ConnectionFailed`. Safe to call twice.

**Warnings.** Python's `warnings.warn` cases (old firmware, no `?` answer, `z0` not confirmed, boot not finished, Wi-Fi joined but no reboot) go to the `onWarning(message)` option, default `console.warn`. A callback rather than an event, because most warnings happen inside `connect`, before the page holds the robot.

**Debugging.** `debug: true` writes `-> <command>` and `<- <line>` to `console.debug`, like Python's `petoi` logger at DEBUG. The Wi-Fi setup command shows as `(Wi-Fi setup command hidden)` and lines received during Wi-Fi setup are not written.

## 4. Behavior carried over from Python

These came from hardware tests (Parts A-K in `docs/superpowers/plans/`, `python/TODO.md`) and must survive the port:

- **USB:** `K`, `b` and `B` commands longer than 64 bytes go as their first 64 bytes, a 50 ms pause, then the rest; 50 ms between an unconfirmed command and the next write; late echoes of earlier commands are consumed, not taken as the current reply.
- **Bluetooth LE:** writes in 20-byte pieces without response (Web Bluetooth doesn't report the negotiated size, as far as I know; unverified); GATT operations one at a time; on connect, take in BiBoard's pushed `Petoi <MODEL>` and its rest `d`, then ask `?` and accept S3's `Petoi <MODEL>u<MODEL><version>?` with no line breaks.
- **Wi-Fi:** JSON messages with task ids; heartbeat every 15 s; `K`/`B` uploads sent as `b64:`; one retry on `"Previous web task is still running"`; `completed` status is the done signal; uploaded behaviors over Wi-Fi return as they start.
- **Robot:** S3 melody waits out the tune (it echoes as the tune starts); `runSkillData` checks the data before sending and, for a behavior, extends its wait by 1.5 times the estimated run time (`_timing.py`); angles are rounded; Wi-Fi setup checks the name and password and never shows lines containing the password.
- **Safety:** the hardware test page never sends frames with speed 0.

## 5. Testing, build and documentation

**Tools (development only):** TypeScript, esbuild to bundle (IIFE with global `Petoi`, and ESM), Vitest for tests. No runtime dependencies. One command, `npm run check`, runs the type check, the tests and the build, and fails if `dist/` differs from what's committed.

**Shared cases.** `python/tests/cases/protocol.json` holds the protocol cases: command encoding, which line ends a reply, reply collection from line sequences, the Wi-Fi command form, the 64-byte split. The Python tests that cover these move to reading this file first (pytest parametrize), so the cases are proven against Python before JavaScript uses them; the JavaScript tests read the same file. Behavior tied to a link or to timing stays as tests in each language.

**Fakes.** `test/fakes/` has a fake Web Serial port (readable and writable streams), a fake Bluetooth device (GATT characteristic with notifications) and a fake WebSocket, each scriptable with robot replies. The Python unit tests are the checklist: each one gets a JavaScript counterpart or a note why not.

**Hardware test page.** `javascript/examples/hardware-test.html`, opened in Chrome from `localhost` (Web Serial needs a secure context; Wi-Fi needs a non-HTTPS page). Buttons connect over USB, Bluetooth or Wi-Fi, then run the Python hardware checklist (`python/tests/hardware/`): info, stand, sit, a skill, joints, a melody (with a "sound next" notice), an upload. Moving steps stay disabled until "the robot is on a stand" is ticked, and the run stops on fall or exception lines (`EXCEPTION:`) the way `tests/hardware/safety.py` does. It doubles as an example for PetoiWebCoding.

**Docs.** `javascript/README.md`: loading the file, connecting from a click, the commands, the Wi-Fi HTTPS limit, browser support, troubleshooting with `debug`.

**Version.** `0.1.0`, semantic versioning.
