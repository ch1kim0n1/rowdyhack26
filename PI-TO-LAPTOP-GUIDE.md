# Pi to Laptop Feed and Transition Guide

How to stream live camera stills from the Raspberry Pi rig to the laptop dashboard and trigger the reveal transition.

---

## 1. Network Connection (iPhone Hotspot)

Do not use venue Wi-Fi. Hackathon networks frequently block client-to-client traffic, preventing the laptop from reaching the Pi.

1. On your iPhone, open **Settings > Personal Hotspot**.
2. Turn on **Allow Others to Join**.
3. Turn on **Maximize Compatibility**. This forces 2.4 GHz so the Pi radio locks on without channel mismatches.
4. Keep the hotspot screen open on your phone until both devices connect.
5. Connect your laptop to the iPhone hotspot.
6. Boot the Pi. It connects automatically if configured in Raspberry Pi Imager.

### Finding the Pi IP

* On your laptop terminal, run:
  ```bash
  ping raspberrypi.local
  ```
* If mDNS is blocked, check the connected devices list under the iPhone hotspot settings or run `arp -a` on the laptop.

---

## 2. Running the Rig

SSH into the Pi:

```bash
ssh pi@raspberrypi.local
cd rowdyhack26-precode
python3 -m rig.app
```

The Flask server listens on `0.0.0.0:5000`.

---

## 3. How the Image Moves to the Laptop

We do not use WebRTC or RTSP. They add unnecessary decoding overhead and buffer lag on flaky links.

1. **Capture:** The cap webcam feeds the Pi via USB. The OpenCV thread in `rig/capture.py` reads frames at 12 fps and holds the latest frame in memory.
2. **Access:** Open Chrome on the laptop to:
   ```text
   http://raspberrypi.local:5000
   ```
3. **Poll Loop:** `noir.js` runs a poll loop every 80ms hitting `/state.json`.
4. **Frame Swap:** When `frame_id` increments, the dashboard preloads `/frame.jpg?id` in the background and swaps it into the view. If a frame drops, the client simply loads the next one without lag or frame queues.

---

## 4. Triggering the Scene Transition

1. The physical button on the cap connects to GPIO 17 on the Pi.
2. Pressing the button tells the backend to sort all cataloged items, select the top five, and set `revealed: true` in state.
3. Within 80ms, the laptop dashboard reads `revealed: true`.
4. The frontend runs the rolling film transition:
   * The live camera feed freezes on its last frame.
   * The tape rolls down through a soft black gap with animated film perfs.
   * Reel 2 ("The Usual Suspects") enters the gate and drops the suspect mugshots in sequence.
5. A second press on the cap button (or the on-screen Stop button) rolls through the end card and resets the case.

---

## 5. Wired Backup (Ethernet Fallback)

If cellular or Wi-Fi drops completely:

1. Plug an Ethernet cable directly from the Pi to the laptop.
2. Both machines will negotiate link-local IP addresses (169.254.x.x).
3. Access the dashboard at `http://raspberrypi.local:5000/reveal` (`/` lands on the premiere).
4. The local scan loop, OLED, speech, and reveal work offline without internet. Only external pricing lookups fall back to cached model estimates.

---

## 6. Zero-Internet Fallback and Diagnostics

* **Hardware Diagnostic:** Run `python3 -m rig.diag` to test the camera brightness, I2C OLED, GPIO button, and API keys before walking on stage.
* **Offline Fallback:** If internet is unavailable, the vision engine automatically rotates through realistic heist exhibits (Sony WH-1000XM6, Razer BlackShark V2, Rolex, Leica, Hemingway, Desk Lamp) with bounding boxes and prices. Set `RIG_OFFLINE=1` in `.env` to force this mode.
* **Comps Toggle:** Disabled by default to prioritize fast, reliable local model pricing. Toggle at runtime by POSTing to `/api/serpapi` or set `SERPAPI_ENABLED=1` in `.env`. `COMPS_PROVIDER` picks the source: `ebayapi` (official eBay Browse API, free dev creds), `ebay` (public sold-page scrape, keyless), `serpapi`, `off`.

---

## 7. Wrist + Rover on the Same Net

All devices ride the same hotspot; the backend (hosted deploy or a Pi) is
the only server.

* **Wrist (Pi Zero W + PiSugar Whisplay HAT):** runs
  `rig/wrist/wrist_hub.py` under `wrist-display.service`; set `HUB_URL` and
  `RIG_TOKEN` in `~/rowdy/hub.env` (setup: `rig/wrist/README.md`). It
  long-polls `/wrist.json` and renders case, take, count, top-5 on the
  Whisplay LCD. Fallback: `wrist_mqtt.py` against the Mosquitto broker on
  the rover Pi 4. If HTTPS fails check `timedatectl` first — a wrong clock
  broke TLS once. If mDNS fails on the hotspot, use the backend's numeric
  IP from the hotspot device list.
* **Hat (Pi Zero 2 W + IMX477):** same hotspot; captures through
  `CAM_BACKEND=picamera2` and streams stills to the backend.
* **Rover (PiCar-X + Pi 4 + OV5647):** same hotspot, then
  `HUB_URL=http://raspberrypi.local:5000 python3 -m rig.rover`.
  Hosted backend instead? `HUB_URL=https://<railway-app>` plus
  `DRIVE_POLL=1` and `CAM_PUSH=1` — the hub can't reach `:5001` inbound
  through NAT, so the rover pulls teleop and pushes its frames.
  Set `RIG_TOKEN` to the same value on both Pis before demo if you want the
  `/api/exhibit` endpoint locked; leave it unset for open LAN operation.
* **Mic button:** second momentary button on `LISTEN_PIN` (GPIO27). Press,
  ask "how long till we bail", get dispatch's ETA through the speaker. Needs
  `OPENAI_API_KEY`, transcription and the answer both run on OpenAI.


---

## 8. Venue Wi-Fi Is Dead / SSH Won't Connect: the No-Network Rungs

Climb down in order. Each rung needs less infrastructure than the last.

1. **Pi becomes the hotspot.** On the hub:
   `bash rig/hotspot.sh` → AP `HEIST-RIG` (password `crewcrew`, override via
   `HOTSPOT_SSID`/`HOTSPOT_PSK`). Laptop, wrist, and rover all join it; hub is
   `http://10.42.0.1:5000`. Set `HUB_URL=http://10.42.0.1:5000` in the rover's
   `.env` and in the wrist's `~/rowdy/hub.env`. Internet is gone,
   so vision degrades to the offline catalog, the demo still runs.
   Tear down: `sudo nmcli connection down Hotspot`.

2. **Monitor + keyboard on the Pi itself.** micro-HDMI monitor + USB keyboard:
   `bash install_pi.sh --kiosk` once, and the boot shows the dashboard
   fullscreen on the local display (cage + chromium, `kiosk.service`).
   Keyboard works even under systemd with no console, `rig/keys.py` reads
   raw evdev: **Enter** = reveal button, **q** = radio dispatch. Full demo
   with zero Wi-Fi clients.

3. **Nothing attached at all.** `RIG_SCRIPT=1` in `.env` runs the scripted
   reel, same dashboard, same reveal, pre-baked exhibits, no camera, no
   keys, no net. The projector shows a film; the crew narrates.

Pairing note: hotspot mode and kiosk mode compose. Hotspot gives the wrist
and rover their net; the monitor+keyboard replace the laptop.
