# The Appraisal Job: physical red-team field kit

Cap-mounted POV rig + vision LLM asset appraisal: build guide for authorized
physical red-team reconnaissance, presented through a film-noir case file.

_Transcribed from `heist_loot_scanner_build_guide.pdf`; amended 2026-09-26 with scope decisions + top-5 TTS announcements; amended 2026-09-25 with MVP additions; amended 2026-09-30 with the three-device crew build._

_Pitch updated 2026-10-02. Older technical terms such as “loot,” “take,” and
`heist.service` remain for compatibility and the noir presentation. In the
pitch they mean observed assets and estimated asset value, not theft. See
`INTERNAL-NOTES.md` for team-only track positioning._

## Scope amendment (2026-09-30): the crew is three devices

The rig above is the hub, worn on the hat. Two more devices join it:

- **Wrist (ESP32 + SSD1306, I2C).** Polls the hub's `GET /wrist.json` every
  ~2s over Wi-Fi and renders case no, running take, exhibit count, and the
  top-5 names + prices. Firmware is `esp32/wrist.ino` (Arduino IDE; libs:
  Adafruit SSD1306, Adafruit GFX, ArduinoJson). Set `WIFI_SSID`, `WIFI_PASS`,
  `HUB` at the top of the sketch. Wire the OLED on SDA=GPIO21, SCL=GPIO22,
  VCC=3.3V, the wrist OLED is NOT the Pi's OLED; the Pi's own SSD1306 (I2C
  can't run the cable distance) stays on the belt pouch as a rig readout.
- **Rover (Pi 4 2GB + camera).** Deployed in the room before the walk. Runs
  `python -m rig.rover`, same capture/gate/identify/price pipeline as the
  hat, but instead of keeping a ledger it POSTs every exhibit to the hub's
  `POST /api/exhibit` (JSON; optional `frame_b64` mugshot; `X-Rig-Token`
  header when `RIG_TOKEN` is set on the hub). Hub dedup treats rover finds
  like hat finds, so pre-scanned items don't double-count when the wearer
  walks past them. Rover finds are tagged `origin: "rover"` in the ledger
  and the manifest. A 50-item queue holds finds through Wi-Fi drops.
  Rover camera: Pi Camera Module or USB webcam both work, `CAM_BACKEND=v4l2`
  is already the Linux default path.
- **Radio check-in (mic button).** A second button on `LISTEN_PIN` (GPIO27;
  `q`+Enter on a laptop) records `LISTEN_SECS` of mic audio, transcribes it
  with Whisper, and asks the model for the evacuation ETA with the live case
  state in the prompt. Answer plays through the speaker via `voice.announce`.
  Needs `OPENAI_API_KEY`; without it the radio plays a "dead" line.
- **Sync model:** hub-and-spoke, the hat Pi is the hub. Rover pushes, wrist
  pulls, laptop polls, all plain HTTP on the hotspot. Set `RIG_TOKEN` on
  both Pis once the rover joins the net; unset means open LAN demo.

Everything from the single-rig guide still applies: the rover and wrist add
endpoints and a second capture process, not new concepts.

## Scope decisions (2026-09-26; amended 2026-09-25)

#### Mandatory (part of the core build)
1. Real price comps via SerpAPI: every identified item gets a live market lookup (eBay sold listings / Google Shopping) instead of an LLM-guessed value. SerpAPI is a hackathon sponsor; this turns the weakest link into sponsor-track evidence.
2. Live frames on the dashboard: the dashboard shows what the camera sees with item labels as well as a counter.
3. Running take total: a live dollar counter during the walk (`$12,400 and counting`) building toward the reveal.
4. Bounding-box annotation on live frames: the vision prompt also returns normalized bbox coords; the dashboard draws a rect + label + price over each detected item. Degrades to label-only if coords come back implausible.
5. Local frame-delta gating: an OpenCV frame-diff skips the LLM call when the view hasn't meaningfully changed. Fewer API calls, less latency pressure, and a real edge-processing story.
6. SSD1306 OLED on the rig: a 128x64 I2C display on the wearer shows the running take and item count, so the hardware visibly works without the laptop.
7. Odometer reveal animation: the reveal page lands items one at a time while the total spins up. The payoff beat is the judges' core memory; make it theatrical.
8. Category-tagged dedup: the LLM returns a broad `category` per item; dedup uses category + fuzzy name so "laptop" vs "MacBook" doesn't double-count.
9. QR-code web manifest: the reveal page shows a QR to `/manifest`, a shareable loot-manifest page judges can open on their phones.
10. Top-5 live TTS announcement: when a newly scanned item's price lands it in the current top 5, the speaker announces it mid-walk: "Alert. This item, [name], is in the top 5 most valuable items this run and costs $X." Fire-and-forget on a background thread so it never stalls the scan loop; deduped re-sightings don't re-announce.

#### Post-MVP (documented, not built at the event)
11. Heist receipt / printable loot-manifest card (top 5, total take, timestamp, room name).
12. Zero-internet fallback: a frame-hash lookup of canned LLM responses so the demo survives total network loss.
13. Second mode: "case the exits" (LLM marks doors/windows in frames).
14. Thermal receipt printer: physical LOOT MANIFEST print at reveal (USB 58mm POS, python-escpos). Deferred to keep the build inside 24h.
15. Laser tripwire arming + rotary "safe dial" reveal trigger: themed physical triggers; the GPIO button stays the primary path.

---

## 1. Project Overview

A cap-mounted camera documents visible assets during an authorized room
walkthrough. A vision LLM identifies items; the pricing pipeline attaches
market comps when available and labels model estimates otherwise. A physical
button triggers a top-five asset debrief on the dashboard and speaker. The
ledger and shareable case file help a red team discuss assets that deserve
closer review; they don't establish vulnerabilities or verify access controls.

What to explain to judges:

- Purpose: permission-based physical reconnaissance and evidence documentation.
- Software: shared multi-camera observations, source-labeled appraisals,
  deduplication, and a ranked case-file debrief.
- Presentation: a coordinated crew and cinematic reveal, without removing
  property or claiming to perform an intrusion.
- Limits: market value isn't security risk; demo/offline observations and the
  model's radio ETA aren't validated real-world findings.

Key build decision: this rig uses a DIY USB webcam setup instead of actual smart glasses. There is no wired or third-party live camera feed available on consumer smart glasses hardware, so a webcam mounted on a cap is both the reliable option and, honestly, the more "heist crew built their own gadget" option thematically.

## 2. System Architecture

Data flow, in order:

1. USB webcam mounted on the cap captures video, wired directly into the Raspberry Pi 4.
2. While in scanning mode, the Pi samples one frame every 2-3 seconds, but a local OpenCV frame-diff gates the call: static scenes are skipped and only novel frames go to the LLM.
3. Each novel frame is sent to a vision LLM with a structured prompt asking for item name, short description, broad `category`, estimated value, and a normalized bounding box, returned as JSON.
4. Each identified item is priced via SerpAPI: an eBay sold-listings / Google Shopping query per item name returns real market comps; the median sold price becomes the item's `value_usd`. If the lookup fails or returns no comps, the LLM estimate is kept and flagged `estimated: true`.
5. Parsed results are checked against a rolling in-memory list using category + fuzzy name matching, so walking past the same object twice, or naming it differently ("laptop" vs "MacBook"), doesn't double-count it.
6. When a newly added item's price lands it in the current top 5, the speaker announces it live: "Alert. This item, [name], is in the top 5 most valuable items this run and costs $X." It plays via TTS on a background thread so the announcement never blocks the next frame. Re-scanning an already-counted item doesn't re-announce.
7. A push button wired to a GPIO pin triggers "reveal mode": the current list is sorted by estimated value and the top 5 are pulled out.
8. The Pi serves a small Flask app: a live walk view (camera frame with bounding-box overlays, scanned-item ticker, and a running "take" total), a reveal page that lands items one at a time behind an odometer-style total, and a `/manifest` page linked by a QR code on the reveal.
9. An SSD1306 OLED on the rig mirrors the running take and item count, so the hardware visibly works even with the laptop closed.
10. On reveal, the Pi also plays an offline text-to-speech line through a small speaker, so the climax of the demo never depends on the venue's wifi holding up at that exact second.

Note the network split: only steps 3-4 (the LLM + SerpAPI calls) need internet. Everything else (the button, the dashboard, the OLED readout, the running total, the reveal, the speech line) runs entirely local on the Pi. That's deliberate: it isolates the parts of the system that depend on a network from the part everyone is watching at the payoff moment.

## 3. Hardware Build

### 3.1 Full Parts List (bring list)

- Raspberry Pi 4 (4GB is fine, no local inference is running on it)
- MicroSD card, 32GB+, pre-flashed with Raspberry Pi OS Lite (64-bit) before arriving, tested and bootable
- USB webcam with built-in mic (e.g. Logitech C270): 720p is plenty
- USB-C portable battery bank, 5V/3A output minimum, plus its cable
- Standard Pi power brick (5V/3A) for bench dev work, separate from the demo battery pack
- Momentary push button (arcade button or basic tactile switch) + jumper wires
- SSD1306 128x64 I2C OLED display (~$7) + 4 short jumper leads
- Small 3.5mm or USB powered speaker
- A stiff, structured baseball cap (not floppy: the brim has to hold the camera steady)
- Zip ties, velcro strips, gaffer tape, small hot glue gun
- Small pouch, fanny pack, or lanyard bag to carry the Pi + battery on the body
- Laptop, for dev work, flashing the SD card, and running the dashboard display
- Ethernet cable, as a backup way to SSH into the Pi if wifi is flaky
- Phone with hotspot capability, as backup internet for the Pi's LLM calls

### 3.2 Mounting the Rig on the Cap

1. Mount the USB webcam to the center of the brim, lens facing forward, using hot glue or a zip-tie loop through its mount clip. Angle it down roughly 10-15 degrees, since the wearer's head will already tilt down slightly when looking at an item.
2. Route the webcam's USB cable from the brim along the side of the cap down toward the back or side, where it will connect to the Pi in its pouch.
3. Mount the push button somewhere reachable without looking down: the side of the cap band, or run its wires down to a handheld position (clipped to a wrist band or belt loop) so it can be pressed on cue without fumbling.
4. Mount the speaker to the cap band or the back of the cap so the reveal line is audible to the people nearby as well as the wearer.
5. Put the Pi and battery pack in a pouch or fanny pack worn at the waist, not on the cap itself. The Pi is too heavy for the cap and a top-heavy rig will not survive a live demo.
6. Mount the SSD1306 OLED on the front of the pouch or on the belt, facing outward, not on the cap. I2C does not tolerate long cable runs; keep the leads under ~30 cm and twisted together.
7. Route all cables (webcam USB, button wires, speaker) down from the cap to the pouch with slack for head movement, and secure them along the way with zip ties or tape so nothing snags mid-walk.

### 3.3 Wiring

- USB webcam: straight into any USB-A port on the Pi 4. The C270's built-in mic covers the radio check-in; a Pi Camera Module has no mic, so pair it with a USB mic dongle.
- Push button (reveal): one leg to GPIO17 (physical pin 11), the other leg to Ground (physical pin 9). Use gpiozero's default pull-up so a press pulls the pin low; no external resistor needed.
- Push button (mic/radio): second momentary button, one leg to GPIO27 (physical pin 13), other leg to Ground (physical pin 14). `LISTEN_PIN` env var moves it.
- SSD1306 OLED: VCC to 3.3V (pin 1), GND to pin 6, SDA to GPIO2 (pin 3), SCL to GPIO3 (pin 5). Enable I2C first: `sudo raspi-config nonint do_i2c 0`.
- Speaker: USB draws power from the Pi (factor into battery budget); 3.5mm jack speakers usually need their own small battery.
- Power: Pi runs continuously off the USB-C battery bank for the whole demo. It must supply 5V/3A minimum or the Pi will brown out and reset while the webcam and LLM calls are both active.

### 3.4 Wrist Unit Wiring (ESP32)

- SSD1306 to ESP32: VCC→3.3V, GND→GND, SDA→GPIO21, SCL→GPIO22 (pins configurable at the top of `esp32/wrist.ino`).
- Flash: set `WIFI_SSID`/`WIFI_PASS`/`HUB` at the top of the sketch, then `arduino-cli upload -p <port> --fqbn esp32:esp32:esp32 esp32/` (or Arduino IDE → board support `esp32`, libs Adafruit SSD1306 + GFX + ArduinoJson 7). Compile-verified on esp32 core 3.3.12: 80% flash, clean. ArduinoJson **7** needs `JsonArrayConst`/`JsonObjectConst` — already handled.
- Power: small LiPo or a lipstick USB bank on a wrist strap.
- Note the wrist OLED is NOT the Pi OLED from §3.3. I2C can't span hat-to-wrist, so the wrist gets its own wireless ESP32; the Pi's OLED stays on the belt pouch as a rig readout.

### 3.5 Rover Wiring (Pi 4 2GB)

- Camera: Pi Camera Module on the CSI port or a USB webcam. `CAM_BACKEND=v4l2` is already the Linux default.
- Motors (if driving): 2WD kit → TB6612 or L298N breakout. Wire left fwd/back and right fwd/back into the four GPIOs named by `DRIVE_PINS` (default 22/23/24/25), enables tied high or jumpered on for L298N. Feed motors from their own supply or a buck converter, never the Pi's 5V rail. Teleop path: hold WASD/arrows on the dashboard to keep rolling (a move re-fires every ~300ms while held, `stop` on release) → `POST /api/drive` on the hub → hub forwards to the rover's `/drive` on :5001 (the rover registers its address by pinging the hub every 10s). No GPIO = console driver that logs moves. `python -m rig.drive` is a wasd REPL for bench-testing wheels. Auto-return: `DRIVE_RETURN_AFTER` seconds of teleop silence (default 60, 0=off) replays the breadcrumb trail back to the drop point — dead reckoning, expect drift on carpet; `POST /drive {"dir":"return"}` forces it on demand. Beacon correction: `python -m rig.marker` prints `home-marker.png` (ArUco id `HOME_MARKER_ID`, default 0) — tape it at the drop point and during return the rover's camera sights it and steers on instead of guessing.
- Power: its own 5V/3A bank.
- Software: clone the repo, `bash install_pi.sh --rover` (same deps; installs `rover.service` instead of `heist.service`), set `HUB_URL` (+ `RIG_TOKEN` if the hub has one) in `.env`, then `sudo systemctl start rover` or run `python3 -m rig.rover` in the foreground for bring-up.

## 4. Software Build (CS Side)

### 4.1 Base Setup

1. Flash Raspberry Pi OS Lite (64-bit) to the SD card ahead of time with Raspberry Pi Imager. In the imager's advanced settings, pre-configure SSH and wifi so the Pi boots headless and reachable.
2. Boot the Pi, SSH in, clone the repo, run `bash install_pi.sh`. It installs the apt packages (including `python3-opencv`, cv2 comes from apt on the Pi, not the 90MB pip wheel), enables I2C, installs `requirements-pi.txt`, and drops in the `heist.service` systemd unit.
3. `cp .env.example .env` and fill in the keys. `OPENAI_API_KEY` is the primary vision + pricing + Whisper path; `ANTHROPIC_API_KEY` is the vision fallback; `SERPAPI_API_KEY` + `SERPAPI_ENABLED=1` turn on sold-listing comps. Every other knob (`HOST`, `RIG_OFFLINE`, `SCENE_CONFIRM`, `LOOK_EVERY`, `RIG_TOKEN`, `LISTEN_PIN`, …) is documented inline in `.env.example`.
4. Test the webcam with `v4l2-ctl --list-devices`, then `python3 -m rig.diag`, it checks camera, OLED, GPIO button, keys, and audio in one pass.
5. `sudo systemctl start heist` for the real deal, or `python3 -m rig.app` to watch logs.

### 4.2 Code Structure

One hub app on the hat Pi, small modules, scan loop decoupled from Flask so a dashboard bug can't take down the scan. The rover runs the same package with a different entry point.

| File | Job |
|---|---|
| `rig/capture.py` | Webcam open (per-OS backend order), frame→JPEG/b64, the scene-diff gate (`SCENE_CONFIRM` samples + `SCENE_THRESH` mean-diff), 3:4 mugshot crops |
| `rig/vision.py` | One still in, one exhibit JSON out. OpenAI → Anthropic → offline catalog (frame-hash deterministic). Bbox clamped to frame, dropped if too small |
| `rig/pricing.py` | SerpAPI sold-listing comps (3s timeout, title must name the product) → model quote → vision estimate. Every price carries a `why` string and an `estimated` flag |
| `rig/store.py` | The ledger: fuzzy+category dedup, running take, atomic JSON mirror to `case.json` + `case-stills/` mugshots so a restart reopens the same case |
| `rig/app.py` | Flask routes + `scan_loop` (grab → gate → async look thread), the reveal button handler |
| `rig/display.py` | SSD1306 case-file readout on the pouch; falls back to `oled-live.png` off-Pi |
| `rig/voice.py` | Fire-and-forget speaker: recorded wav first, pyttsx3 TTS otherwise, never blocks the loop |
| `rig/listen.py` | The radio check-in: mic → Whisper → evac ETA → speaker |
| `rig/button.py` | GPIO17 = reveal, `LISTEN_PIN` (GPIO27) = mic; Enter / `q`+Enter on laptops, evdev USB keyboard under systemd |
| `rig/keys.py` | USB keyboard fallback via evdev when there's no tty: the no-SSH rung |
| `rig/tripwire.py` | Optional prop triggers: LDR beam-break (`TRIPWIRE_PIN`), KY-040 dial (`DIAL_PINS`) |
| `rig/rover.py` | Rover entry point: same pipeline, POSTs exhibits to `HUB_URL`, heartbeats for teleop, queues through Wi-Fi drops |
| `rig/drive.py` | Wheel abstraction: gpiozero Robot on `DRIVE_PINS`, console driver off-Pi; `python -m rig.drive` is a wasd REPL |
| `rig/drive_server.py` | Rover's stdlib teleop endpoint on :5001: `POST /drive {dir, secs}` |
| `rig/printer.py` | Optional USB POS printer: paper LOOT MANIFEST on reveal when `RIG_PRINTER=1` |
| `rig/hotspot.sh` | `nmcli` AP `HEIST-RIG`: the venue-Wi-Fi escape hatch |
| `rig/diag.py` | `python -m rig.diag` hardware + key check before the walk |
| `rig/script.py` | `RIG_SCRIPT=1`: scripted walk with no camera and no keys |
| `tests/test_contract.py` | 103 tests covering the whole contract: no hardware needed |

The dashboard contract (`/state.json`). The UI kit's client, `Noir.connect('/state.json')` in `ui-kit/noir.js`, polls this every ~80 ms and diffs it. No other data path is needed:

```jsonc
{
  "frame_id": 412,              // bump on every new capture; the client hard-cuts to the new still
  "camera_ok": true,            // false shows the "FOOTAGE LOST" slate on the dashboard
  "pending": false,             // true while a look runs; shows "EXAMINING EXHIBIT 07..."
  "revealed": false,            // flips true when the button fires; the client plays the reveal
  "case_no": 1138,              // bumps on every case reset
  "take": 7600,
  "items": [{"n": 1, "item": "VINTAGE ROLEX", "value_usd": 4200, "estimated": false,
             "why": "priced from live eBay sold-listing comps",
             "origin": "hat",   // or "rover" when filed by the scout
             "bbox": [0.12, 0.20, 0.26, 0.36]}]
}
```

The wrist unit's contract (`/wrist.json`) is the same case compressed for a 128x64 screen: `{case_no, take, count, pending, revealed, camera_ok, top: [{item, value_usd} ×5]}`.

The rover's contract (`POST /api/exhibit`) is the exhibit schema plus an optional `frame_b64` mugshot: `{item, desc, category, value_usd, estimated, bbox, why, frame_b64?}` with an `X-Rig-Token` header when `RIG_TOKEN` is set. Response: `{"added": bool, "hot": bool, "take": float}`, `added: false` means the ledger already had it.

Each exhibit keeps the frame it was found in (`frame_jpeg`, mirrored to `case-stills/still-<n>.jpg`) so `/crop/<n>.jpg` can cut the booking photo, `capture.crop_jpeg` widens the bbox to a 3:4 mugshot, falling back to a centered crop when the model returned no box.

### 4.3 Dashboard Styling Notes

- Styling is the 1950s-noir case-file kit in `ui-kit/` (`noir.css` + `demo.html` as the reference, spec in `ui-kit/README.md`): black-and-white film, one stamp-red, League Gothic headlines, Special Elite typed entries, Courier Prime labels. The notes below describe layout only; colors, type, and motion come from the kit.
- Live view: the camera frame large on the left; right column holds the running take total in the biggest type on the page, then a scrolling row of item thumbnails with prices. Keeps energy up while walking.
- Live view overlays: an evidence marker per detected item (`EXHIBIT 07` tag + name/price caption), drawn by the dashboard from `/state.json` and never burned into `/frame.jpg`.
- Reveal view: a big numbered list of item name, one-line description and market price (with a small "est." marker on LLM-estimated values), with #1 largest and boldest. Items animate in one at a time (~600 ms apart) while the total counts up like an odometer; a QR code to `/manifest` sits in a bottom corner so judges can pull the manifest onto their phones.
- When nobody is walking, the live view falls back to a title-card attract loop so a judge arriving mid-cycle sees a designed screen, not an empty feed.

## 5. Build Timeline

Written as relative phases. Scale them to your actual hackathon length. Do the riskiest part (the core capture-to-LLM loop) first, mount and polish last. Most of phases 1–5 already exist in `rig/`, these are now bring-up + integration steps.

1. Phase 1: Flash both SD cards (before arriving if possible), verify the webcam and button work standalone on each Pi.
2. Phase 2: Bench the hub's core loop end to end, unmounted: frame capture, frame-delta gate, vision call, pricing, store entry. `python smoke_demo.py` covers the contract offline; `python -m rig.diag` covers hardware. Highest-risk part, solid before anything else.
3. Phase 3: Wire reveal button (GPIO17), mic button (GPIO27), the pouch SSD1306, and the speaker. `rig.diag` covers the first three; confirm a top-5 callout plays.
4. Phase 4: Flash the wrist (`esp32/wrist.ino`), get it polling `/wrist.json` on the hotspot. Bench-test with `RIG_SCRIPT=1` on the hub so the wrist shows a live case without a camera.
5. Phase 5: Bench the rover: same repo, `HUB_URL` + `RIG_TOKEN` set, `python -m rig.rover`. Confirm exhibits land on the hub ledger with `origin: "rover"` and dedup blocks the double-count when the hat re-sees them.
6. Phase 6: Mount everything (cap, pouch, wrist strap, rover), run a full walk + rover pre-scan with real objects.
7. Phase 7: Tune `SCENE_THRESH`, `SCENE_CONFIRM`, `LOOK_EVERY`, and mic `LISTEN_SECS` based on the walk test.
8. Phase 8: Polish: rehearse the radio check-in question, the reveal, the reset. Rehearse the full demo twice. Record a backup video.

## 6. Demo Script (~90 seconds)

1. Set up an approved assessment area with team-owned or explicitly permitted
   props. The rover's pre-scan observations are already on the shared ledger;
   no property is moved or taken.
2. Put the cap on and open with: “The Appraisal Job is an AI-assisted physical
   red-team field kit. An authorized walkthrough becomes a shared evidence
   file and a ranked asset debrief.” Glance at the wrist: the top five is live.
3. Walk past 4–6 props, pausing on each. Point out identification, bounding
   boxes, duplicate handling, price-source labels, and the summed estimated
   asset value. Explain that value prioritizes review, not proven security risk.
4. Optional radio beat: ask “How much time is left in this exercise?” State
   that the current ETA is a simulated narrative cue, not a measured timer or
   a prediction of detection. Skip this beat if it distracts from the evidence.
5. Press reveal for the debrief. Read the top-five assets as they land; show
   hat/rover provenance and the QR case file. Close with: “This gives the team
   documented observations to review—not a claim that these assets are unsecured.”
6. Second press closes the case and starts a fresh run. Identify any scripted
   or offline demo data explicitly rather than presenting it as live findings.

## 7. Risk List & Backups

| Risk | Mitigation |
|------|-----------|
| Venue wifi is flaky | Use the phone hotspot for ALL devices (hub, rover, ESP32, laptop); venue wifi often blocks client-to-client anyway, and the whole sync depends on peer traffic. Test before demo day. |
| Rover loses Wi-Fi mid-scan | Finds queue on the rover (50 deep) and refile when the hub comes back. Worst case it's a stationary camera the judges see working after reconnect. |
| ESP32 won't flash/connect | It's read-only decoration; the pouch OLED + dashboard carry the same info. Bring a pre-recorded wrist video if flash fails at the venue. |
| Whisper/listen latency | Record is capped at `LISTEN_SECS` (4s), calls have 20s timeouts, and every failure path speaks a dead-radio line: the bit survives a bad network. |
| `RIG_TOKEN` mismatch | Symptom is a clean 401 on the rover's POST, logged on both sides. For demo, leave `RIG_TOKEN` unset: open LAN is fine on your own hotspot. |
| SerpAPI quota/latency | Timeout the lookup (~3 s); on failure keep the model quote/vision estimate flagged `estimated: true`, so the demo never stalls on pricing. Cache results per deduped item so prices don't repeat queries. |
| LLM call latency during the demo | The walk-and-pause pacing covers it; all calls carry 15–20s timeouts so a hung request can't stall the scan. |
| OLED or I2C glitch | Cosmetic only. Keep leads <30 cm, mount on the pouch; if it dies, the dashboard carries the demo. |
| LLM returns bad bbox coords | `valid_bbox` clamps to the frame and drops boxes too small to be real; the label survives either way. |
| Frame gate skips real changes | Tune `SCENE_THRESH` in Phase 7; `SCAN_ALWAYS=1` bypasses the gate entirely. |
| Judges' phones can't reach the Pi for the QR | Venue wifi may block peer-to-peer, so the QR is a flourish and never a required path. Bring printed case files: open `/manifest` after the final rehearsal, print it (the kit has print styles) and hand one to each judge. |
| Button or GPIO failure | USB keyboard (Enter/q via evdev), SSH `/trigger_reveal`, or the dashboard stop button: three independent paths. |
| Venue Wi-Fi dead / no SSH | `bash rig/hotspot.sh` makes the hub the AP; monitor+keyboard kiosk covers the laptop. Rungs in PI-TO-LAPTOP §8. |
| Full live failure on stage | `RIG_SCRIPT=1` runs the whole contract with no camera and no keys: that's the fallback reel, then the backup video. |
| Battery dies mid-demo | Fully charge the bank the night before; use the wall brick for all bench testing so the battery pack is reserved for demo time only. |

## 8. Ops Sheet: pin map, boot order, who runs what

### 8.1 Pin map

**Hat hub (Pi 4 4GB):**

| Signal | Pin | Notes |
|---|---|---|
| GPIO17: reveal button | phys 11, GND phys 9 | internal pull-up, no resistor |
| GPIO27: mic button | phys 13, GND phys 14 | `LISTEN_PIN` moves it |
| GPIO2 (SDA): OLED | phys 3 | hub pouch SSD1306, 0x3C |
| GPIO3 (SCL): OLED | phys 5 | keep leads <30 cm |
| 3.3V / GND: OLED | phys 1 / phys 6 | |
| Webcam + mic | USB-A | C270 mic covers the radio check-in |
| Speaker | USB or 3.5mm | powered speaker preferred |
| Tripwire LDR | `TRIPWIRE_PIN` (free GPIO + GND) | optional: beam break fires reveal/reset |
| Safe dial | `DIAL_PINS=a,b` (two free GPIOs) | optional: KY-040, DIAL_TICKS detents crack the vault |

**Wrist (ESP32):**

| Signal | Pin | Notes |
|---|---|---|
| SDA: SSD1306 | GPIO21 | `SDA_PIN` in `wrist.ino` |
| SCL: SSD1306 | GPIO22 | `SCL_PIN` in `wrist.ino` |
| 3.3V / GND | | OLED at 0x3C, same address as the hub's |

**Rover (Pi 4 2GB):** camera on CSI or USB. No fixed GPIO assignment in this
repo, motor wiring is whatever the drive build picks (out of scope).

### 8.2 Who runs what

| Device | Process | Started by |
|---|---|---|
| Hat hub | `python3 -m rig.app` (Flask + scan loop + OLED + voice) | `heist.service` via `install_pi.sh`, or foreground for bring-up |
| Rover | `python3 -m rig.rover` (capture → identify → POST to hub) | `rover.service` via `install_pi.sh --rover` |
| Wrist | `esp32/wrist.ino` (polls `/wrist.json` @2s) | power on; no service |
| Laptop | browser → `http://raspberrypi.local:5000` | Chrome, full screen |

### 8.3 Boot order (demo morning)

1. Phone hotspot ON, screen open, "Maximize Compatibility" (2.4 GHz), every device joins this net.
2. Hub Pi on → `heist.service` autostarts → `journalctl -u heist -f` to watch.
3. `python3 smoke_demo.py --live http://raspberrypi.local:5000` from the laptop, ten checks including `/wrist.json`, `/manifest`, `/qr.png`, and a mugshot crop.
4. `python3 -m rig.diag` on the hub if anything is amber.
5. Rover Pi on → `journalctl -u rover -f` → exhibits should land on the hub ledger within a scene change.
6. Wrist on → "LINE DEAD" clears to the case readout on first poll.
7. Laptop opens the dashboard; title card plays, first poll starts the walk.
8. Walk test with 2-3 props; confirm wrist top-5 and the rover-tagged lines on `/manifest`.

### 8.4 Shutdown

- Hub: `sudo systemctl stop heist` (case file + stills persist in `rig/state/`).
- Rover: `sudo systemctl stop rover` (queued finds are lost if it never reconnected: check `journalctl -u rover` first).
- Wrist: power off. The ledger lives on the hub; nothing else owns state.

## Post-MVP backlog (do not build at the event)

Built since this list was written: the printable loot manifest (`/manifest` + QR), the zero-internet frame-hash fallback (`RIG_OFFLINE`), the wrist unit, the rover pre-scan, the radio check-in mic, rover driving (`rig/drive.py` + teleop relay), case-the-exits mode (`RIG_MODE=exits`), the thermal printer hook (`rig/printer.py`, `RIG_PRINTER=1`), and the prop triggers (`rig/tripwire.py`: `TRIPWIRE_PIN` LDR beam-break, `DIAL_PINS` KY-040 crack-the-vault, both fire the same reveal/reset as the button). Still open:

- Hardware verification only: ESP32 flash, real motors, real mic, tripwire/dial wiring, kiosk monitor, hotspot. Every code path is complete; what remains needs physical parts.
