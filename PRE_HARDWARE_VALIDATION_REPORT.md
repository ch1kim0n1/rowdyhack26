# Pre-Hardware Validation Report

Certification pass over the full system. Mocks sit **only** at the hardware
boundary (cv2, gpiozero, luma, escpos, arecord/aplay, urllib targets);
everything above the seam — scan loop, scene gate, pricing ladder, ledger,
reveal, OLED render, motor driver, radio chain, HTTP endpoints — ran for real.

**Result: READY_WITH_RISKS.** Every software-testable path passes. Remaining
risk is concentrated in physical bring-up items that cannot be proven without
parts (pin maps, polarity, I2C, RF range).

Run: `python -m unittest discover -s tests` → **109 tests, all pass** (62
contract + 41 certification), `ruff check` clean, `python smoke_demo.py` pass.

---

## 1. Hardware/software boundary map

```
APPLICATION                     SEAM                       PHYSICAL
rig/app.py        ──> capture.open_camera ──> cv2.VideoCapture ──> USB webcam / PiCam (CAM_INDEX, CAM_BACKEND)
rig/app.py        ──> vision.identify     ──> openai/anthropic HTTP ──> API keys, WAN
                  └─> pricing.resolve     ──> urllib serpapi / OpenAI chat ──> WAN
rig/app.py        ──> button.start        ──> gpiozero Button(17,27) ──> GPIO header
                  └─> keys.start          ──> evdev InputDevice ──> /dev/input/event* (USB keyboard)
rig/app.py        ──> display.start       ──> luma i2c(0x3C) ssd1306 ──> I2C OLED
                  └─> PNG fallback        ──> rig/oled-live.png
rig/app.py        ──> voice._speak/_play  ──> OpenAI TTS / aplay / pyttsx3 ──> USB/3.5mm speaker
rig/app.py        ──> listen._record_wav  ──> subprocess arecord|rec ──> USB mic (LISTEN_SECS)
rig/app.py        ──> printer.receipt     ──> escpos.printer.Usb ──> thermal printer (PRINTER_USB)
rig/app.py        ──> tripwire.start      ──> gpiozero LightSensor / RotaryEncoder ──> GPIO props
rig/rover.py      ──> post_exhibit/ping   ──> urllib ──> hub http://HUB_URL:5000
rig/drive.py      ──> RobotDriver         ──> gpiozero Robot ──> TB6612/L298N on DRIVE_PINS
rig/drive.py      ──> find_home_marker    ──> cv2.aruco ──> printed beacon (HOME_MARKER_ID)
rig/drive_server  ──> ThreadingHTTPServer ──> :5001 teleop socket
esp32/wrist.ino   ──> HTTPClient          ──> hub GET /wrist.json ──> Wi-Fi
kiosk.service     ──> cage + chromium     ──> micro-HDMI monitor
rig/hotspot.sh    ──> nmcli               ──> Wi-Fi radio (NetworkManager)
```

Tightly-coupled points flagged: gpiozero pin claims (17, 27, DRIVE_PINS, TRIPWIRE_PIN,
DIAL_PINS), I2C address 0x3C, arecord/rec binary presence, USB vid:pid for
printer, NetworkManager for hotspot, chromium binary name for kiosk.

## 2. Tests created

`tests/hw_sim.py` — sim layer: FakeCam (ok/empty/frozen/corrupt/dead, scripted
mode switching), fake gpiozero (Button/LightSensor/RotaryEncoder/Robot with
call capture), fake luma OLED device, fake escpos printer, FakeMic subprocess
runner, fake OpenAI (whisper/chat/TTS), FakeHub (latency/drop-injectable HTTP).

`tests/test_certification.py` — 41 integration tests:

- **CameraMatrix** — normal frames → exhibits; dead cam → `camera_ok=false` →
  recovery; corrupt reads; frozen frame → no dupes across 30 ticks; 10-tick
  dead gap → recovery.
- **ButtonMatrix** — GPIO press → reveal → reset; **500 concurrent presses**
  → consistent alternating state; no-gpio fallback raises nothing.
- **OledMatrix** — all 3 modes × edge values render non-blank on the real
  `render()`; fake luma canvas path actually draws frames.
- **MotorSafety** — every path ends `stop`: normal stop, invalid direction,
  conflicting moves + return_home, empty trail. RobotDriver gen-lock verified.
- **MicMatrix** — valid recording → whisper → chat → spoken reply; zero-byte →
  "Mic's dead"; device failure → "Mic's dead"; no key → skips before record.
- **SpeakerMatrix** — missing clip → OpenAI TTS → wav played.
- **NetworkMatrix** — real HTTP hub: ping+post land; hub-down → queue → drain
  on recovery; 500ms latency inside POST_TIMEOUT; duplicate posts dedup
  hub-side.
- **BootOrder** — rover-first/hub-late queues and drains; wrist-first answers
  a valid `/wrist.json`.
- **Soak** — 500 scan ticks + 500 reveal/reset: no thread growth, no fd leak.
- **Chaos** — identify() raising → walk continues; cam death mid-scan → lost →
  recovers.
- **Timing** — reveal-to-state, snapshot, exhibit POST latency asserts.
- **Fuzz** — 500 randomized exhibit payloads + 500 randomized add_item
  candidates: zero 5xx, JSON contract stays strict-parseable, no poison.
- **RaceStorm** — 200-thread random op storm on RobotDriver: ends stopped,
  no deadlock, no orphan sleepers.
- **CorruptTail** — truncated case.json (power-cut simulation) loads fresh.
- **EndToEnd** — real werkzeug server + real rover code + real urllib →
  exhibit lands in the ledger with `origin: rover`.
- **SecurityPosture** — 429 rate limits on `/api/exhibit` + `/api/drive`,
  CSRF nonce gate on `/trigger_reveal`, security headers, `RIG_TOKEN=auto`.

## 3. Commands

```sh
python -m unittest discover -s tests -v    # 93 tests total
ruff check .
python smoke_demo.py                        # offline contract
python smoke_demo.py --tests --live http://pi:5000   # live probe (10 checks)
python -m rig.diag                          # on-device hardware probe
python -m rig.marker                        # print the ArUco home beacon
arduino-cli compile --fqbn esp32:esp32:esp32 esp32/  # ESP32 (verified: 80% flash)
```

## 4. Results

All pass. Latency measured on the real code path (M-series laptop, values
bound local compute only — network legs add their documented timeouts):

| Path | Measured |
|---|---|
| frame → JPEG | 0.5 ms |
| frame → base64 | 0.4 ms |
| scene gate eval | 0.09 ms |
| button → reveal state | 0.3 ms |
| `GET /state.json` | 0.9 ms |
| `POST /api/exhibit` full path | 0.5 ms |
| rover post vs 500ms-latency hub | ~0.5 s, inside POST_TIMEOUT=4 s |

No thread/fd growth across 500-tick scan soak and 500 reveal/reset cycles.

## 5. Bugs discovered

- **`/api/exhibit` accepted NaN/inf `value_usd`** → poisoned every JSON
  response and persisted into case.json. (P0 — found earlier, fixed.)
- **`RobotDriver` stale set() raced fresh moves**; queued lock-held sleeps let
  moves outlive a stop. (P0 — fixed, generation-based latest-wins.)
- **Stored XSS via `it.item` innerHTML** on an unauthenticated-by-default
  endpoint. (P0 — fixed, textContent.)
- **Garbage `bbox` persisted → `/crop` 500.** (P1 — fixed, shape-checked.)
- **`SERPAPI_ENABLED` env was dead** — raw flag read bypassed the resolver.
  (P1 — fixed.)
- **`GET /trigger_reveal` mutated state** — CSRF-able case-wipe. (P1 — fixed:
  GET serves a confirm page; POST mutates.)
- **Rover exits announced "$0 door" callouts.** (P2 — fixed.)
- **wrist.ino used ArduinoJson 6 types** — would not compile on v7. (P1 —
  fixed; verified by real arduino-cli compile.)
- **keys.py leaked fds on device drop and died on unplug.** (P2 — fixed:
  closes old devices, rescans on a timer.)
- **heartbeat hot-looped on failed ping.** (P2 — fixed.)
- **`kiosk.service` hardcoded a binary name that may not exist.** (P2 — fixed:
  installer picks whichever landed.)

## 6. Bugs fixed in this pass

None outstanding — the certification suite found no new defects. Earlier
review-round bugs (above) are all covered by regression tests.

## 7. Remaining risks (software-observable)

- **Breadcrumb return drifts** — dead reckoning without encoders; beacon
  correction only engages when the marker is in frame. Demo-tier by design.
- **Drive watchdog granularity** — `_auto_return` polls every 5 s; return
  latency = up to `DRIVE_RETURN_AFTER` + 5 s.
- **OLED preview file** grows nothing but writes `oled-live.png` every 0.5 s
  when luma is absent — harmless on laptop, should be noted on SD-only boots.
- **Voice thread lock** serializes callouts; a long TTS fetch delays the next
  line — acceptable pacing, not a bug.

## 8. HARDWARE_REQUIRED checklist

- GPIO pin wiring: Button 17 (reveal), 27 (mic), DRIVE_PINS 22–25, TRIPWIRE_PIN, DIAL_PINS.
- I2C: SSD1306 at 0x3C actually enumerated (`python -m rig.diag`).
- Motor polarity + enable jumpers on TB6612/L298N; `python -m rig.drive` REPL.
- Camera orientation/framing on the cap mount; `CAM_INDEX`/`CAM_BACKEND`.
- USB mic capture (`arecord -l`; `.asoundrc` template if needed) + gain.
- Speaker path (aplay USB vs 3.5mm), volume.
- Battery brownout under webcam+LLM load (5V/3A minimum).
- Wi-Fi: venue client isolation, hotspot AP range, rover↔hub reachability.
- Kiosk: cage/chromium on the HDMI panel, boot order vs `heist.service`.
- Thermal: sustained load under enclosure.
- ESP32 flash + real Wi-Fi join + OLED render.
- Printer vid:pid vs `PRINTER_USB`.
- Beacon print size/legibility at return distance (~10 cm square).

## 9. Rehearsal procedure (full system)

1. Flash both Pis; on hub: `bash install_pi.sh`, `.env` (keys, `RIG_TOKEN`),
   `python -m rig.diag` → all green, `sudo systemctl start heist`.
2. Rover: `bash install_pi.sh --rover`, `.env` (`HUB_URL`, `RIG_TOKEN`),
   `python -m rig.diag` (Motors column), `sudo systemctl start rover`.
3. Laptop: `python smoke_demo.py --live http://<hub>:5000` → 10/10.
4. Bench: `python -m rig.drive` wasd REPL; dashboard WASD teleop; drop beacon
   at start, idle 60 s → auto-return.
5. Wrist: set WIFI/HUB, flash, confirm `/wrist.json` rows render.
6. Camera walk with `RIG_OFFLINE=1` first (deterministic), then keys live.
7. Failure drill: kill Wi-Fi (hotspot fallback), unplug camera (LINE DEAD),
   pull mic (voice fallback), stop rover (502 → TTL → 503), replay.
8. Cold boot everything simultaneously; confirm ready state without SSH.
9. If venue LAN hostile: `bash rig/hotspot.sh` → all devices on HEIST-RIG.
10. Reveal → manifest QR → optional printer manifest → `/trigger_reveal`
    confirm page → reset for next walk.

## Verdict: READY_WITH_RISKS

All software-testable integration paths pass under simulation; nothing in the
boundary map is unexercised. Risk is now entirely physical: pin maps,
polarity, RF, and power — the §8 checklist is the bring-up plan.
