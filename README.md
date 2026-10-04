# The Appraisal Job: physical red-team reconnaissance

An AI-assisted field kit for authorized physical red-team walkthroughs.
Identify visible assets, attach market-value estimates with source labels,
and turn the observations into a shared evidence ledger and top-five debrief.
The point is to turn visible observations into evidence the assessment team
can review and use to discuss the potential value at stake.

Built for RowdyHacks XII. Three devices in sync: a **hat** (Pi Zero 2 W +
IMX477) that streams camera images to the backend for identification and
appraisal, a **wrist unit** (Pi Zero W + PiSugar Whisplay HAT) that keeps the
case, count, take, and top five on the assessor's wrist, and a **rover**
(SunFounder PiCar-X + Pi 4) that scouts the approved assessment area.
One ledger, one dashboard, a film-noir case-file interface.

## The pitch

> The Appraisal Job turns an authorized room walkthrough into a live evidence
> file. Our AI identifies visible assets, estimates their market value, and
> keeps the field operator and dispatch desk working from the same ledger.
> Finish the walkthrough and get a ranked top-five debrief with a shareable
> case file—so the team can discuss what deserves closer review.

Use only in spaces the assessment team has permission to inspect. The dollar
total is estimated asset value, **not** a security-risk score or a prediction
of losses. Visibility alone does not prove an asset is unsecured. The system
doesn't verify access controls, detect vulnerabilities, or perform intrusion
testing. Offline/scripted results are demo data, not observed findings.

The noir vocabulary (crew, exhibits, lineup, take) is presentation: “take”
means the summed estimated asset value, and the lineup ranks by value, not
exploitability. The useful output is documentation for an authorized review.

## Architecture

```
  hat (Pi Zero 2 W + IMX477)      backend (Flask app)            wrist (Pi Zero W
  camera stills --------------->  identify / appraise            + Whisplay HAT)
                                  case ledger (JSON+stills)  <-  GET /wrist.json
  rover (PiCar-X, Pi 4 + OV5647)  dashboard /manifest /report    (case, count,
  camera stills --POST /api/exhibit-------------------------->   take, top-5)
```

The backend runs hosted (Railway via `railway.json`) or on a Pi
(`heist.service`); the hat and rover are camera clients, the wrist and the
dashboard read the same backend API.

- `PROGRESS.md`: feature ledger: what's shipped, what's tested, what's missing.
- `BUILD-GUIDE.md`: full build walk, wiring, demo-day checklist.
- `PARTS-LIST.md`: hardware BOM for all three devices.
- `PI-TO-LAPTOP-GUIDE.md`: networking + dashboard on a laptop.
- `rig/wrist/`: wrist receiver programs + setup docs (`rig/wrist/README.md`).
- `esp32/wrist.ino`: retired ESP32 + SSD1306 wrist sketch, kept for reference.
- `ui-kit/README.md`: NOIRKIT design system the dashboard runs on.
- `/motion.html`: safe, simulated conditional-animation rehearsal for the UI/UX demo.
- `ui-kit/film/`: source for the premiere's film (three.js set, rendered frame by frame).

Team-only positioning and judging-track intent live in `INTERNAL-NOTES.md`;
that document is not served by the app.

## Backend

The Flask app (`rig/app.py`) is the shared backend: the vision + appraisal
pipeline, the case ledger, the dashboard, the manifest, the QR-linked
Defender Report, and the `/wrist.json` feed the wrist and dashboard read.
Deploy it hosted (see `railway.json`) or run it on a Pi / laptop:

```sh
bash install_pi.sh && sudo systemctl start heist   # on a Pi
# laptop dev:
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # add OPENAI_API_KEY and/or ANTHROPIC_API_KEY
python -m rig.app
```

Dashboard at `http://<host>:5000/`. GPIO17 = reveal button (Enter on laptop).
GPIO27 = mic button (`q`+Enter on laptop): records a few seconds, asks dispatch
for a grounded exercise check-in, then speaks the answer. Dispatch uses the
case ledger and configured job clock; it isn't a real-world safety or detection timer.

## Hat (Pi Zero 2 W + IMX477)

Hat-mounted Pi Zero 2 W with an IMX477 Pi camera streams stills into the
same capture → scene-gate → identify → price pipeline (`CAM_BACKEND=picamera2`
selects the Picamera2 adapter that hands frames to OpenCV; a CSI camera gets
no frames through V4L2). Verified on hardware: camera capture and live
recognition + appraisal from the hat feed on the website.

## Wrist (Pi Zero W + PiSugar Whisplay HAT)

`rig/wrist/wrist_hub.py` polls `GET /wrist.json` with `X-Rig-Token` and
renders the case number, total estimated value, exhibit count, and the top
five on the Whisplay's LCD. Runs under `wrist-display.service` (systemd).
The verified fallback is MQTT mode (`wrist_mqtt.py`, Mosquitto broker on the
rover Pi 4), including autostart after reboot. Full setup in
`rig/wrist/README.md`. Verified on hardware: backend case data retrieved
and displayed; showing the same live results as the dashboard is the
remaining integration step. Retired ESP32 + SSD1306 path: `esp32/wrist.ino`.

## Rover (SunFounder PiCar-X + Pi 4 + OV5647)

Second camera platform. Same codebase, different entry point:

```sh
HUB_URL=http://<backend>:5000 RIG_TOKEN=crew python -m rig.rover
```

Captures, gates, identifies, prices, then POSTs exhibits to the backend's
ledger. Queues finds if the Wi-Fi blinks; refiles next tick. OV5647 capture
verified through the Picamera2 adapter. `DRIVE_KIT=picarx` runs the Robot
HAT motors; movement and audio features still need validation.

Hosted backend (Railway): the hub can't reach the rover's `:5001` inbound
behind venue NAT, so set `DRIVE_POLL=1` (rover long-polls `/api/drive/pending`
for queued teleop) and `CAM_PUSH=1` (rover POSTs frames to `/api/cam/frame`,
keeping `CAM_SOURCE=rover` working) on the rover. The hat is a camera client
too in hosted mode — run `python -m rig.rover` on it, not `rig.app`, or it
spawns a second ledger.

## Routes

| Route | What |
|---|---|
| `/` `/reveal` | live scan view / reveal view (client swaps on `revealed`) |
| `/manifest` | printable asset case file (QR'd from the dashboard; retains the themed “Loot Manifest” label) |
| `/state.json` | dashboard poll contract |
| `/wrist.json` | compact top-5 for the wrist display |
| `POST /api/exhibit` | rover files a find (`X-Rig-Token` if `RIG_TOKEN` set) |
| `POST /api/rover_ping` | rover heartbeat; registers the teleop address (`{"poll": true}` = pull-mode) |
| `POST /api/drive` | teleop relay: hub forwards `{dir, secs}` to the rover, or queues it for a poll-mode rover |
| `GET /api/drive/pending` | pull-mode rover's long-poll drain (`?wait=N`) |
| `POST /api/cam/frame` | rover pushes a JPEG frame (`CAM_PUSH=1`) |
| `/frame.jpg` `/crop/<n>.jpg` | live still / exhibit mugshot |
| `/health` `/trigger_reveal` `/api/serpapi` | status / the button (GET open-LAN only) / price toggle (GET=status, POST=mutate) |
| `/kit` `/demo.html` `/board.html` | NOIRKIT index, driver, board |
| `/premiere` | the one-sheet: title card, a film the scroll wheel plays, the crew, the method |
| `/desk` | dispatch desk for the crew: take, ledger, reveal button, price switch, wrist preview, rover pad |
| `/media/*` `/shots/*` `/brand/*` | the premiere's film and stills, kit screenshots, the emblem slot |
| `/plan.json` `POST /api/plan` | Mastermind: the job and live plan / pick the job (`{"mode": "appraisal"}` or `{"mode": "mastermind", "bag_lb", "time_s", "level": "small"\|"big"}`; token or the dashboard's case nonce) |
| `POST /api/radio` `POST /api/radio/text` | key the mic / a typed call (`{"text", "job_id"}`); returns the job at once (202) |
| `/api/radio/jobs` `/api/radio/jobs/<id>` | radio calls: transcript, intent, state, plan revision, reply, errors |
| `POST /api/exhibit_status` | Mastermind: `{"n", "status": "available"\|"collected"\|"excluded"}`; the desk's buttons and the radio use it |
| `/narrator.json` | what the narrator said, is saying, and dropped |
| `/report/<id>` `/report/<id>.json` | Defender Report for a closed case (`?secure=3&move=5` runs an owner what-if) |
| `/report/<id>/evidence/<n>.jpg` `/report/<id>/qr.png` | the report's preserved evidence crops / its read-only phone QR |
| `POST /report/<id>/unlock` `/api/reports` | token mode: trade `RIG_TOKEN` (form body) for the share link / operator list |

## How a look flows

`capture.scene_changed` gates the camera on a frame diff held for
`SCENE_CONFIRM` samples → `vision.identify` sends the still to OpenAI, then
Anthropic, then the offline catalog → `pricing.resolve_detailed` tries live
comps (`COMPS_PROVIDER`: ebayapi / ebay scrape / serpapi), then a model quote, then the vision number, every price
carries a `why`. `store` dedupes on fuzzy name + category, keeps the running
take, tags each find `origin: hat|rover`, and mirrors the ledger to disk on
every change.

Badges, keycards, and school/student IDs come back as `category: "badge"`
with a `card` (`name`, `id`, `org`, `role`, `card_no`, `issued`, `expires`)
holding only the text the model could read, exactly as printed. The prompt
knows the UT Dallas Comet Card: front gives role, full name, and `UTD ID#`
(`id`); back gives the 16-digit `card_no` and the `issued` date. Show both
sides and they fill in one exhibit (a match on `id` or `card_no`, or the same
card name, merges instead of re-filing). Badges skip the resale ladder, file
as "credential cloned", show CLONED in the lineup, and the card rides
`/state.json` (`items[].card`) for any frontend to show.
Long public numbers (library barcodes, campus card numbers) are kept as is.
**Never real payment cards:** the prompt refuses them, and any Visa/Mastercard/
Amex/Discover number that passes the Luhn check is masked to `****1234` in
`vision` and again in `store`, so it never reaches `case.json` or `/state.json`.
## Two jobs: Appraisal and Mastermind

The title card offers both (and `P`, or the mode chip in the live header,
reopens the choice before the reveal):

- **Appraisal** is the sandbox: scan anything, every find counts, no limits.
- **Mastermind** asks for the bag (pounds), the clock (seconds), and the job:
  a *small job* stays quiet (a tight risk budget, nothing conspicuous), a
  *big score* takes anything that fits. `rig/planner.py` then keeps one plan
  current as finds come in: the sidebar shows what's in the bag, pounds and
  seconds used, and the next target; case-file lines are marked BAG or LEAVE
  (with why), and a swap posts `PLAN REVISED +$…`. The reveal stamps each
  suspect BAGGED or LEFT and shows the haul under the room's total.

Weights come from the vision model's spec-sheet estimate (`weight_lb`), or a
per-category default when it gives none; grab time and risk are category
defaults. The plan is exact (branch and bound, checked against brute force)
and deterministic; it is a simulation, not a measurement. The job persists
with the case and carries over to the next one.

## The radio and the narrator

**Dispatch radio** (`rig/radio.py`). Key the mic (GPIO27, `R` on the
projector, *Key the mic* on the desk) or type on the desk. Every call is a
job you can watch: queued, listening, transcribing, thinking, applying,
speaking, then done, or clarify / failed / cancelled / expired. Dispatch
answers from the live plan and the ledger only: *what's next, why leave the
lamp, how much fits, how much time is left* (planned grab time against the
clock, never a countdown), *what changed, how many badges*. It can change
the job through the same validated calls as the desk: *switch to small job /
big score / appraisal / mastermind, set the clock to 20 seconds, set the bag
to 10 pounds, mark exhibit 2 collected, exclude the lamp, put back exhibit
4*. Unclear commands ask for the missing piece; a call heard for a case that
closed, or against a plan that moved, is cancelled visibly instead of
applied late. One call at a time with a short line (`429` when it's full),
idempotent `job_id`s, and recordings are deleted as soon as they're
transcribed. Typed calls need no keys at all.

**Narrator** (`rig/narration.py`, `rig/voice/lines.json`). A bank of short
dispatch lines for real moments: the job starting, the first find, a new
top-five entry, a milestone, the camera dropping and coming back, a plan
swap, nothing fitting, the reveal, the case closing, radio trouble. Lines
come from state changes, never polls; each has a priority, cooldown, repeat
scope, and expiry, and variants rotate. Everything plays through one bounded
queue, so the reveal or a radio answer jumps a backlog of commentary, and a
closed case's lines never play. The 26 bundled clips play offline with no
cloud call; item names, prices, and radio answers use TTS. `RIG_VOICE=0`
mutes it and the desk still shows every line.

```sh
python -m rig.narration check          # catalog + every clip, before the demo
python -m rig.narration build          # regenerate clips: OpenAI TTS if keyed, else macOS say
```

## Defender Report

The reveal freezes the ledger; `rig/report.py` copies that case (exhibits,
provenance, one evidence crop each) into `<state dir>/reports/<id>/` before a
reset can clear it, so the report renders the same after the next case or a
restart. If that write fails, the case is **not** reset; the error shows on
`/health` and the manifest, and the next press retries.

The report shows the observed inventory with its evidence and where every
identification and price came from (fixture/demo finds are labeled as such,
unknown stays unknown), then modeled exposure at 30, 60, and 120 seconds from
`rig/planner.py`: an exact, deterministic selection that maximizes appraisal
value under a fixed bag (10 carry units) and risk cap (8). Per-category time,
size, and risk are disclosed modeling assumptions, not measurements. The owner
can mark exhibits secured or moved and re-run the same scenarios as a
comparison; the stored case is never edited.

Access: open-LAN mode (no `RIG_TOKEN`) opens it to anyone with the opaque
link. With a token, the page needs the operator (`X-Rig-Token`, or the unlock
form) or the report's own read-only share key, which its QR carries.
`RIG_TOKEN` never goes into a URL or QR. Retention: `RIG_REPORT_KEEP`,
`RIG_REPORT_DAYS`; expired reports keep a tombstone page and lose their evidence.

## Tests and checks

```sh
python -m unittest discover -s tests -v   # no camera or keys needed
python smoke_demo.py                      # offline contract check
python smoke_demo.py --tests --live URL   # everything, against a running hub
python -m rig.diag                        # hardware + key check on the Pi
```

## Config

All env vars documented in `.env.example`, keys, model picks, offline/script
modes, camera index/backend, scene gate (`SCENE_CONFIRM`, `SCENE_THRESH`),
`LOOK_EVERY`, `HOST`/`PORT`, voice, multi-device (`RIG_TOKEN`, `HUB_URL`,
`LISTEN_PIN`, `LISTEN_SECS`), and persistence path.
