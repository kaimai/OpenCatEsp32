# petoi JavaScript API: brainstorming notes

Working notes for the JavaScript port of the `petoi` Python package. Not a design yet: the design doc comes after the open questions below are answered and the design is approved.

## Decided (owner, 2026-11-06)

- The JavaScript API lives in a folder next to `python/` on `feature/python-api`.
- PetoiWebCoding should switch to it.
- The remaining Python TODOs (`python/TODO.md`) go to the team.

## Recommended, not yet confirmed

- **Browser-only first version** (Web Serial, Web Bluetooth, WebSocket). PetoiWebCoding's robot code is all browser code; Node there is only dev tooling. Node support can be added later behind its own transports if someone needs it.
- **TypeScript source**, shipped as JavaScript with type definitions.
- **Scope:** the API itself is one design, plan and build. Moving PetoiWebCoding onto it is a separate project afterwards: different repository and maintainers (Rongzhong Li, Jason.W), and it needs its own browser testing.

## What exists

### The Python package (`python/`, the reference)

About 1,700 lines of source, about 290 unit tests (most with a fake link), hardware tests under `tests/hardware/`.

| Module | Job |
|---|---|
| `protocol.py` | command encoding, reply parsing, line buffering |
| `transports/` | `serial.py`, `ble.py`, `websocket.py`, `mock.py`, shared `base.py` |
| `robot.py` | `Robot`: `send`, `send_binary`, `skill`, `run_skill_data`, `sit`, `stand`, `stop`, `rest`, `walk`, `trot`, `crawl`, `back`, `joint`, `move_joints`, `joints`, `beep`, `melody`, `gyro`, `gyro_state`, `calibrate_gyro`, `info`, `setup_wifi`, `close` |
| `connect.py` | picks a transport from a target (`ble`, `ble:<addr>`, a serial port, an IP) |
| `constants.py` | skills, joints, per-model tables |

Hardware-proven behavior the port must keep (details in `python/TODO.md` and the Part A-J plans in `docs/superpowers/plans/`):

- **Serial:** a long `K`/`b`/`B` command is sent as its first 64 bytes, a 50 ms wait, then the rest (Part H); a 50 ms gap between commands (`WRITE_GAP`, Part G).
- **S3 melody:** echoes as the tune starts, so wait out the tune.
- **BLE:** discover only the Nordic UART service (Part J; S3 firmware stalls 30 s on its Device Information service on macOS). BiBoard pushes `Petoi <MODEL>` then rests (`d`); S3 is silent and answers the first `?` with `Petoi <MODEL>u<MODEL><ver>?` and no line breaks. A sleeping Quaddle ignores the first command, so retry `?` once.
- **Wi-Fi:** `"Previous web task is still running"` triggers one retry; uploaded behaviors over Wi-Fi return as they start (`src/reaction.h:1565`).
- **Safety:** never keep or show robot lines containing the Wi-Fi password; never speed 0 in frames.

### PetoiWebCoding (public repo, checked at ed6a4d1, 2026-11-02)

- **Static site, no build step.** Everything loads through plain `<script src=...>` tags; `node_modules/` is committed so the browser loads Blockly and `esptool-js` from it. `package.json` only runs `http-server`. No test suite (`AGENTS.md`).
- **Robot code is copied per page:**
  - `main.html` (~8,500 lines): Web Serial and Web Bluetooth;
  - `mobile_remote.html`: Web Bluetooth and Web Serial;
  - `skill_composer.html`: Web Serial;
  - `js/petoi_async_client.js` (725 lines): WebSocket client.
- Useful tables: `memo/instinct_skills.csv` (skills per product), `js/product_config.js` (joints per product), `js/timeout_config.js` (timeouts: default 30 s, music 120 s).

This repo also has `PetoiWebCodingBlocks/`, an older copy of the same app (`main.html` and `js/petoi_async_client.js`, no `mobile_remote.html` or `skill_composer.html`). The public repo is the current one.

## Open questions (one at a time)

1. **How should PetoiWebCoding load the API?** It has no build step today.
   - **A. One ready-built file** loaded with `<script src="petoi.js">`, which adds a global `Petoi` (recommended). Fits PetoiWebCoding as it is. We write TypeScript and commit the built file. It also works as an ES module (`import { connect } from "./petoi.mjs"`) for newer pages.
   - **B. ES module only** (`<script type="module">`). Cleaner for modern code, but each PetoiWebCoding page would need changing to use it.
   - **C. An npm package** installed into their committed `node_modules/`. Most standard, but needs publishing to npm, and they would still load a built file.
2. Folder name next to `python/`.
3. How closely names follow Python (`run_skill_data` vs `runSkillData`, async everywhere).
4. How to test without a browser (fake Web Serial / Web Bluetooth / WebSocket objects, shared test vectors from the Python tests).
5. Whether converting one PetoiWebCoding page is part of this project as a proof, or all of it is left to its maintainers.

## API design practices, checked against the Python API (2026-11-06)

Sources (read 2026-11-06):
- Azure SDK guidelines: [general](https://azure.github.io/azure-sdk/general_introduction.html), [Python](https://azure.github.io/azure-sdk/python_design.html), [TypeScript](https://azure.github.io/azure-sdk/typescript_design.html). Written for cloud clients, but the principles are general: idiomatic, consistent, approachable, diagnosable, dependable.
- W3C TAG [Web Platform Design Principles](https://www.w3.org/TR/design-principles/): rules for JavaScript APIs in the browser.
- Chrome docs for [Web Serial](https://developer.chrome.com/docs/capabilities/serial) and [Web Bluetooth](https://developer.chrome.com/docs/capabilities/bluetooth).

The judgments below are mine, applying those sources; they are not quoted from them.

### Python API: what already matches

| Practice | Source | `petoi` |
|---|---|---|
| Easy start with good defaults, progressive disclosure | Azure general | `petoi.connect()` finds a USB robot; `"mock"` works with no robot; `send()` / `send_binary()` are there for advanced users |
| Timeouts in seconds | Azure Python | `timeout`, `skill_timeout` in seconds |
| Few exception types, only ones a caller can act on; built-ins for bad input | Azure Python | `PetoiError` > `ConnectionFailed`, `RobotError` > `RobotTimeout`, `WifiSetupFailed`; `ValueError` for bad arguments |
| Actionable error messages | Azure general | e.g. "check power and the connection", "check the network name and password, and that it is 2.4 GHz Wi-Fi" |
| Extensible string enums with UPPERCASE members | Azure Python | `Skill(str, Enum)`, `Skill.HI`; plain strings accepted too |
| Clean-up through the language's own construct | idiomatic | `with petoi.connect() as robot:`; leaving on an error makes the robot stand |
| Names match the domain | Azure general | skill names are the firmware's (`hi`, `kc`) |

### Python API: gaps

1. **Positional booleans.** `wait`, `timeout` and `sequential` can be passed by position (`robot.sit(False)`, `robot.move_joints(a, True)`). Azure Python: "DO provide optional operation-specific arguments as keyword only." Fix: add `*` before them. The package isn't on PyPI yet, so this break costs nothing now and something after release.
2. **Not diagnosable.** No `logging` anywhere, so there's no way to see the bytes sent and lines received. This session needed throwaway scripts to see them. Fix: a `petoi` logger at DEBUG for traffic, with the Wi-Fi command and its echoed lines redacted.
3. **Unknown skill names succeed silently.** On a Quaddle, Bittle-only skills confirmed in 0.3 s (2026-11-06). The model's skill table is known after `connect()`, so `skill()` could raise `ValueError` for a name the model doesn't have, with an option to skip the check. What the firmware itself replies to an unknown name hasn't been checked.
4. **Getter/setter names don't pair.** `joint(i, angle)` moves, `joints()` reads; `gyro(on)` sets, `gyro_state()` reads. Readable once known, easy to mix up. Candidates: `move_joint` / `read_joints`. Renaming is a judgment call: it costs README and example churn.
5. **Firmware units leak.** `beep(note, duration)` uses the firmware's 1/duration-second unit (8 = 125 ms). Documented, but surprising. Leave it in Python (it matches Petoi's other tools); in JavaScript, consider the same, for parity.
6. **Mixed failure styles.** High-level methods raise `RobotTimeout`; `send()` returns a `Reply` with `completed=False`. Deliberate and documented (raw access never raises), so keep it, and keep it the same in JavaScript.
7. **Internals exposed.** `robot.transport` is public, and `model` / `firmware` are writable attributes set by `connect()`. Low risk; read-only properties would be cleaner.

Items 1-3 were fixed in Python before the port (Part K, `docs/superpowers/plans/2026-11-06-python-api-design-fixes.md`): keyword-only settings 4e65f56, DEBUG traffic logging with Wi-Fi setup hidden a0af3fe, refusing a `Skill` the model lacks d8969c9. Items 4-7 are left as they are.

### What this means for the JavaScript API

- **Idiomatic first, the same concepts second.** Azure ranks consistency within a language above consistency across languages, and feature parity above name parity. So: `runSkillData`, not `run_skill_data`, with the same methods and behavior. This answers open question 3.
- **Promises for everything that talks to the robot** (W3C 6.11). One request at a time per robot, as the Python lock does; Web Bluetooth also needs its GATT operations queued.
- **Options objects, not positional optionals** (W3C 6.5): `robot.sit({ wait: false })`, `robot.skill("hi", { timeout: 10000 })`.
- **Milliseconds** for time (W3C 8.3), unlike Python's seconds. Name it so it can't be misread, e.g. `timeoutMs`, as Azure's TypeScript guide suggests.
- **Cancellation with `AbortSignal`** in the options (W3C 6.12; W3C names it `signal`, Azure `abortSignal`; follow W3C for a browser library). Aborting a walk should make the robot stand, the way leaving Python's `with` block does.
- **String literals for enums** (W3C 6.13): skills as `"hi"` with a TypeScript string union for autocompletion; joints by number with named constants.
- **Events through `EventTarget`** (W3C 7.4, 7.10), present-tense names, e.g. `disconnect`, and possibly `message` for unsolicited robot lines.
- **Errors as `Error` subclasses** with distinct `name`s (W3C 8.5), mirroring Python's hierarchy: `PetoiError`, `ConnectionFailed`, `RobotError`, `RobotTimeout`, `WifiSetupFailed`.
- **Device pickers need a user click.** `navigator.serial.requestPort()` and `navigator.bluetooth.requestDevice()` must be called from a user gesture, before any other `await`; PetoiWebCoding's `main.html:6247` already notes this. So connecting is two steps: something like `Petoi.requestUsb()` / `Petoi.requestBle()` inside a click handler, which can't be hidden behind a single `connect("ble")` as in Python. Previously granted USB ports can reconnect without a prompt via `navigator.serial.getPorts()`.
- **Web Bluetooth specifics:** list the UART service in `optionalServices`; handle `gattserverdisconnected`; re-fetch GATT objects after a reconnect; HTTPS only.
- **Web Serial specifics:** release the reader and writer locks before `close()`; cancel a pending read to stop it.
- **Feature detection:** report "this browser has no Web Serial / Web Bluetooth" separately from "no robot found" (W3C 2.6). Web Serial is Chromium desktop only; Web Bluetooth isn't in Safari or Firefox (not checked against current compatibility tables).
- **Dependable:** no runtime dependencies, and semantic versioning, starting at 0.x.
