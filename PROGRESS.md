# PROGRESS: The Appraisal Job

Feature ledger for the three-device crew build. Updated 2026-10-04.

Status: ✅ shipped+tested · 🟡 shipped, untested on hardware · 🔧 partial · ❌ missing

## Hardware as built (2026-10-04 ground truth)

- **Hat:** Raspberry Pi **Zero 2 W** + **IMX477** Pi camera. Streams stills to
  the backend for identification and appraisal. Camera capture verified;
  live recognition + appraisal from the hat feed demonstrated on the website.
- **Wrist:** Raspberry Pi **Zero W** + **PiSugar Whisplay HAT** (soldered
  40-pin header). Shows current case, item count, total estimated value, and
  the top five. Runs `rig/wrist/` under `wrist-display.service`. HTTP mode
  (`wrist_hub.py`) reads the backend API directly — verified retrieving and
  displaying case data. MQTT mode (`wrist_mqtt.py`, Mosquitto on the rover
  Pi 4) verified including autostart after reboot.
- **Rover:** **SunFounder PiCar-X** + Pi 4 + **OV5647** camera. Second camera
  platform; capture verified. Movement and audio still need validation.
- **Backend:** the Flask app (`rig/app.py`), deployed hosted (Railway); both
  cameras and the wrist talk to the same API.
- Both cameras capture through the Picamera2 adapter in `rig/capture.py`
  (`CAM_BACKEND=picamera2`), which supplies frames to OpenCV.
- Integration issues hit and handled: intermittent Wi-Fi on one Pi 4, an
  incorrect system clock that blocked HTTPS (corrected manually; automatic
  time sync still open), and a physically cracked wrist microSD that required
  a rebuild.
- Remaining integration: wrist showing the same live results as the
  dashboard; rover movement, audio, and the full camera-to-wrist path.

## Device 1: Hat (Pi Zero 2 W + IMX477)

| Feature | Where | Status | Notes |
|---|---|---|---|
| Camera capture + backend pick | `rig/capture.py` | ✅ | IMX477 verified via Picamera2 adapter (`CAM_BACKEND=picamera2`); dshow/msmf/v4l2 order kept for other platforms; `CAM_INDEX` env |
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

## Device 2: Wrist unit (Pi Zero W + PiSugar Whisplay HAT)

| Feature | Where | Status | Notes |
|---|---|---|---|
| Wrist data contract | `GET /wrist.json` on backend | ✅ | compact: case_no, take, count, pending, revealed, top5 |
| HTTP receiver | `rig/wrist/wrist_hub.py` | ✅ | long-polls `/wrist.json` with `X-Rig-Token`; verified retrieving + displaying backend case data on the Whisplay |
| Whisplay render | `wrist_hub.py render()` | ✅ | case no, take, count, top-5 names + prices; "LINE DEAD" error screens |
| MQTT fallback receiver | `rig/wrist/wrist_mqtt.py` | ✅ | Mosquitto broker on the rover Pi 4; hat + rover topics verified on the display |
| Autostart | `rig/wrist/wrist-display.service` | 🟡 | MQTT-mode boot autostart verified; HTTP-mode boot test still open |
| Live parity with dashboard | `wrist_hub.py` | 🔧 | wrist shows case data; matching the dashboard's live results is the remaining integration step |
| Retired ESP32 sketch | `esp32/wrist.ino` | — | superseded by the Whisplay build; kept for reference |

## Device 3: Rover (SunFounder PiCar-X + Pi 4 + OV5647)

| Feature | Where | Status | Notes |
|---|---|---|---|
| Eyes pipeline | `rig/rover.py` | ✅ | same capture/gate/identify/price; POSTs to backend |
| Camera capture | `rig/capture.py` | ✅ | OV5647 verified via Picamera2 adapter |
| Offline queue | `rover.run` deque ×50 | ✅ | tested: holds on failure, drains on reconnect |
| Hub intake | `POST /api/exhibit` | ✅ | dedup + `origin: rover` + optional `frame_b64` mugshot |
| Autostart | `rover.service`, `install_pi.sh --rover` | 🟡 | written; needs rover Pi boot test |
| **Driving / motor control** | `rig/drive.py` + `rig/drive_server.py` | 🟡 | `DRIVE_KIT=picarx` drives the Robot HAT; `/drive` on :5001; movement still needs validation |
| Teleop chain | backend `POST /api/drive` → rover `:5001`; WASD/arrows via `Noir.drive()` | 🟡 | rover registers via `/api/rover_ping`; forward tested, wheels untested |
| Auto-return | breadcrumbs + `dir:"return"` + `DRIVE_RETURN_AFTER` watchdog | 🟡 | beacon-sighted steering via `rig/marker.py` ArUco tag; needs floor test |
| Rover audio | PiCar-X speaker | 🟡 | not yet validated |
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

- 🔧 Wrist live parity: wrist displays backend case data; matching the same live results shown on the dashboard is the remaining integration step
- 🟡 Wrist HTTP-mode autostart after reboot (MQTT-mode autostart verified)
- 🟡 Automatic time sync on the wrist Pi: a wrong clock blocked HTTPS until corrected manually
- 🟡 Rover movement + audio validation: PiCar-X motors and speaker untested
- 🟡 Full camera-to-wrist workflow end to end
- 🟡 Real-motor + real-mic bench test: code paths done and covered, GPIO untested
- ❌ Recorded voice wavs (`rig/voice/alert.wav`, `reveal.wav`): human task: record a dry read; TTS covers if skipped
- 🟡 `.asoundrc` USB-mic config: template at `rig/asoundrc.usb-mic.example`, only needed if `arecord` can't see the mic
- ❌ LiDAR: dropped from spec

## Extras shipped past the vision

- `RIG_MODE=exits`: case-the-exits prompt swaps appraisals for door/window marking
- `rig/printer.py`: `RIG_PRINTER=1` prints a paper LOOT MANIFEST on reveal (python-escpos, USB 58mm POS)
- Rover teleop: `POST /api/drive` on the hub relays to the rover's wheels; WASD/arrows wired on the dashboard

## Next up (ordered)

1. Wire the wrist to the same live results as the dashboard; verify HTTP-mode autostart after reboot.
2. Full camera-to-wrist walk: hat capture → backend → wrist + dashboard together.
3. PiCar-X movement + audio bench test (`python -m rig.drive` REPL, then WASD teleop through the backend).
4. Real-button + mic bench test on the backend Pi (`rig.diag` + a `q`-key radio check-in).
5. Walk test → tune `SCENE_THRESH` / `LOOK_EVERY` / `LISTEN_SECS`.
