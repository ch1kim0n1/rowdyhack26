# Heist Crew Parts List

As-built hardware for all three devices, updated 2026-10-04 to match the
deployed kit. Original planning BOM is in git history; single-rig wiring
details live in `BUILD-GUIDE.md` §3.

## Device 1: hat camera

| Part | As built | Note |
|---|---|---|
| Raspberry Pi Zero 2 W | Camera client | Streams stills to the backend for identification + appraisal |
| Pi camera (IMX477) | Raspberry Pi HQ Camera class sensor | Captures through `CAM_BACKEND=picamera2` (`rig/capture.py`); CSI gets no frames through V4L2 on current Pi OS |
| MicroSD | 32GB, Pi OS Lite | |
| Battery bank | 5V USB | The Zero 2 W sips power vs a Pi 4, but still test under camera load |
| Cap + mount | Stiff structured cap | Camera on the brim, angled down ~10-15° |

## Device 2: wrist unit

| Part | As built | Note |
|---|---|---|
| Raspberry Pi Zero W | Display client | Runs `rig/wrist/` under `wrist-display.service` |
| PiSugar Whisplay HAT | Display + battery | Mounts on the 40-pin header (soldered); driver from https://github.com/PiSugar/Whisplay |
| MicroSD | 32GB, Pi OS Lite | A physically cracked card forced one rebuild — carry a spare |

No wiring beyond the HAT itself: the Whisplay stacks on the header. Shows
case number, item count, total estimated value, and the top five from the
backend's `/wrist.json` (HTTP mode) or MQTT topics (fallback mode).

## Device 3: rover

| Part | As built | Note |
|---|---|---|
| SunFounder PiCar-X | Chassis + Robot HAT + motors + speaker | `DRIVE_KIT=picarx` in `rig/drive.py`; movement + audio still unvalidated |
| Raspberry Pi 4 | Rover brain | Also hosts the Mosquitto broker for the wrist's MQTT fallback |
| Camera (OV5647) | PiCar-X stock camera | Verified through the Picamera2 adapter; `rig/feed.py` can also read SunFounder's vilib MJPEG stream |
| Battery | PiCar-X pack + Pi supply | |

## Backend

- Hosted deploy (Railway, `railway.json`) serves the dashboard, manifest,
  Defender Report, and `/wrist.json` to every device. Can also run on a Pi
  or laptop via `install_pi.sh` / `python -m rig.app`.

## Bring from home

- Laptop: dev work, flashing SD cards, dashboard display
- Ethernet cable: backup SSH path if venue wifi is hostile
- Phone with hotspot: backup internet for the LLM/SerpAPI calls
- Spare microSD cards (see wrist note above)

## Optional adds (post-MVP, only if a phase finishes early)

| Part | Use | ~Price | Note |
|---|---|---|---|
| USB 58mm POS thermal printer | Prints the LOOT MANIFEST at reveal | ~$35 | Must be `python-escpos` compatible; avoid BLE toy printers (Peripage/Paperang) |
| LDR + laser module | Tripwire to arm scanning (`gpiozero.LightSensor`) | ~$5 | Arming only, never on the required path |
| KY-040 rotary encoder | Rotary "safe dial" reveal trigger | ~$3 | GPIO button stays primary |
| SSD1306 OLED + button + speaker | Pouch readout / reveal button / voice on a backend Pi | ~$25 | Only needed when the backend runs on a Pi with the single-rig wiring in BUILD-GUIDE §3.3 |

## Pre-event check

- Bench-test every battery under real load (camera streaming + active
  network call). If it browns out at home, it browns out on stage.
- Check `timedatectl` on every Pi before demo: a wrong clock broke HTTPS on
  the wrist once already.
- Confirm all devices join the same hotspot before powering the rover down.
