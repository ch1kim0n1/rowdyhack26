# PROGRESS: The Appraisal Job

Feature ledger for the three-device crew build. Updated 2026-09-30.

Status: ✅ shipped+tested · 🟡 shipped, untested on hardware · 🔧 partial · ❌ missing

## Device 1: Hat hub (Pi 4, 4GB)

| Feature | Where | Status | Notes |
|---|---|---|---|
| Camera capture + backend pick | `rig/capture.py` | ✅ | dshow/msmf/v4l2 order; `CAM_INDEX`/`CAM_BACKEND` envs |
| Scene-diff gate + flicker confirm | `capture.scene_changed` | ✅ | `SCENE_CONFIRM`, `SCENE_THRESH`; `SCAN_ALWAYS` killswitch |
| Vision identify | `rig/vision.py` | ✅ | OpenAI → Anthropic → offline catalog; 20s timeouts; bbox clamp |
| Pricing ladder | `rig/pricing.py` | ✅ | SerpAPI comps → model quote → vision estimate; `why` field |
| Dedup ledger | `rig/store.py` | ✅ | fuzzy name + category; persists `case.json` + `case-stills/` |
| Dashboard routes | `rig/app.py` | ✅ | `/`, `/reveal`, `/state.json`, `/frame.jpg`, `/crop/<n>.jpg`, `/manifest`, `/qr.png`, `/health` |
| Reveal + reset button | `rig/button.py`, GPIO17 | 🟡 | code tested; needs real button on pin 11/9 |
| Prop triggers | `rig/tripwire.py` | 🟡 | `TRIPWIRE_PIN` LDR beam-break, `DIAL_PINS` KY-040 dial; off unless pinned |
| Pouch OLED readout | `rig/display.py`, I2C 0x3C | 🟡 | renders live/lost/reveal; PNG fallback off-Pi; needs real SSD1306 |
| Top-5 + reveal speech | `rig/voice.py` | 🟡 | wav-first, pyttsx3 fallback; `RIG_VOICE`; needs speaker test |
| Radio check-in (mic → Whisper → evac ETA) | `rig/listen.py`, GPIO27 | 🟡 | full chain coded; needs USB mic + `arecord` on the Pi |
| Offline/scripted demo modes | `RIG_OFFLINE`, `RIG_SCRIPT` | ✅ | full contract runs with no camera/keys |
| Persistence across crash | `case.json` + `case-stills/` | ✅ | atomic writes; restart reopens case + mugshots |
| Autostart | `heist.service`, `install_pi.sh` | 🟡 | unit written; needs real Pi boot test |
| No-SSH control path | `rig/keys.py` evdev + `kiosk.service` | 🟡 | USB keyboard Enter/q + local monitor under systemd; needs HDMI bench test |
| Pi-as-hotspot | `rig/hotspot.sh` (nmcli) | 🟡 | venue-Wi-Fi escape hatch; needs a real Pi run |
| Hardware diagnostic | `python -m rig.diag` | 🟡 | camera/OLED/GPIO/keys/audio/motors; needs real Pi |

## Device 2: Wrist unit (ESP32 + SSD1306)

| Feature | Where | Status | Notes |
|---|---|---|---|
| Wrist data contract | `GET /wrist.json` on hub | ✅ | compact: case_no, take, count, pending, revealed, top5 |
| Firmware sketch | `esp32/wrist.ino` | 🟡 | written; compile-verified on arduino-cli (esp32:esp32 3.3.12, 80% flash); needs a real board flash |
| OLED render (top-5) | `wrist.ino draw()` | 🟡 | 128x64, 0x3C, SDA=21/SCL=22 |
| Dead-link screens | `drawDead()` | 🟡 | "LINE DEAD" states coded |

## Device 3: Rover (Pi 4, 2GB)

| Feature | Where | Status | Notes |
|---|---|---|---|
| Eyes pipeline | `rig/rover.py` | ✅ | same capture/gate/identify/price; POSTs to hub |
| Offline queue | `rover.run` deque ×50 | ✅ | tested: holds on failure, drains on reconnect |
| Hub intake | `POST /api/exhibit` | ✅ | dedup + `origin: rover` + optional `frame_b64` mugshot |
| Autostart | `rover.service`, `install_pi.sh --rover` | 🟡 | written; needs rover Pi boot test |
| **Driving / motor control** | `rig/drive.py` + `rig/drive_server.py` | 🟡 | gpiozero Robot on `DRIVE_PINS`; `/drive` on :5001; console driver off-Pi; needs real motors |
| Teleop chain | hub `POST /api/drive` → rover `:5001`; WASD/arrows via `Noir.drive()` | 🟡 | rover registers via `/api/rover_ping`; forward tested, wheels untested |
| Auto-return | breadcrumbs + `dir:"return"` + `DRIVE_RETURN_AFTER` watchdog | 🟡 | beacon-sighted steering via `rig/marker.py` ArUco tag; needs floor test |
| LiDAR mapping | n/a | ❌ | dropped from spec; would be +$100 RPLIDAR + 1–2 days |

## Sync / network

| Feature | Status | Notes |
|---|---|---|
| Hub-and-spoke topology | ✅ | rover POSTs, wrist GETs, laptop polls: all hub-centered |
| `RIG_TOKEN` shared secret | ✅ | 401 without it when set; open when unset; covers /api/exhibit, /api/rover_ping, /api/drive |
| Same-hotspot runbook | ✅ | BUILD-GUIDE §8.3 boot order + PI-TO-LAPTOP §7 |

## Dashboard / UI kit

| Feature | Status | Notes |
|---|---|---|
| NOIRKIT views (live/reveal/manifest) | ✅ | title card → scan → lineup → THE END |
| Client poll contract | ✅ | `Noir.connect('/state.json')` @80ms |
| Evidence markers from bbox | ✅ | drawn client-side, never burned into frame |
| QR → manifest | ✅ | |
| Sound design | 🟡 | coded; browser autoplay needs a click to arm |
| Premiere page `/premiere` | ✅ | title card, scroll-scrubbed film, crew dossiers, method, paperwork, credits |
| The film `ui-kit/film/` | ✅ | three.js set + kit overlays, 501 frames, `node render.mjs film` to re-render |
| Dispatch desk `/desk` | ✅ | live take/ledger, reveal, SerpAPI switch, wrist OLED copy, rover pad; route tests |
| Crew emblem | ❌ | needs a generated image at `ui-kit/brand/emblem.png`; pages show the wordmark until then |

## Infra / quality

| Feature | Status | Notes |
|---|---|---|
| Test suite | ✅ | 109 tests, zero hardware, zero network |
| Smoke check | ✅ | `smoke_demo.py` offline + `--live` 10-check probe |
| CI | ✅ | `.github/workflows/test.yml` on push/PR |
| Lint | ✅ | `ruff.toml`, clean |
| Docs | ✅ | README, BUILD-GUIDE (incl. §8 ops sheet), PARTS-LIST, PI-TO-LAPTOP |

## Missing / not started

- 🟡 ESP32 flash: sketch compiles clean on esp32:esp32 3.3.12 (80% flash); only the physical upload is left
- 🟡 Real-motor + real-mic bench test: code paths done and covered, GPIO untested
- ❌ Recorded voice wavs (`rig/voice/alert.wav`, `reveal.wav`): human task: record a dry read; TTS covers if skipped
- 🟡 `.asoundrc` USB-mic config: template at `rig/asoundrc.usb-mic.example`, only needed if `arecord` can't see the mic
- ❌ LiDAR: dropped from spec

## Extras shipped past the vision

- `RIG_MODE=exits`: case-the-exits prompt swaps appraisals for door/window marking
- `rig/printer.py`: `RIG_PRINTER=1` prints a paper LOOT MANIFEST on reveal (python-escpos, USB 58mm POS)
- Rover teleop: `POST /api/drive` on the hub relays to the rover's wheels; WASD/arrows wired on the dashboard

## Next up (ordered)

1. Parts in hand → flash wrist, boot rover, `smoke_demo.py --live` the whole net.
2. Real-button + mic bench test on the hub (`rig.diag` + a `q`-key radio check-in).
3. Motors wired → `python -m rig.drive` REPL on the rover, then WASD teleop through the hub.
4. Walk test → tune `SCENE_THRESH` / `LOOK_EVERY` / `LISTEN_SECS`.
