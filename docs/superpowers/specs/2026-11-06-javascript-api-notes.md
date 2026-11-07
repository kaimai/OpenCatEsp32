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
