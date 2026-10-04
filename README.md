# The Appraisal Job: physical red-team reconnaissance

An AI-assisted field kit for authorized physical red-team walkthroughs.
Identify visible assets, attach market-value estimates with source labels,
and turn the observations into a shared evidence ledger and top-five debrief.
The point is to turn visible observations into evidence the assessment team
can review and use to discuss the potential value at stake.

Built for RowdyHacks XII. Three devices in sync: a **hat** that scans a room
and estimates asset values, a **wrist unit** that keeps the top five on the
assessor's wrist, and a **rover** that scouts the approved assessment area.
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
  rover (Pi4 2GB)            hat (Pi4 4GB, hub)            wrist (ESP32+OLED)
  camera -> identify/price   camera -> identify/price      polls GET /wrist.json
        \  POST /api/exhibit      button -> reveal                 (top-5 + take)
         ------------------>   mic button -> Whisper           ^
                               -> evac ETA -> speaker          |
                               case ledger (JSON+stills) ------+
                               dashboard /manifest /qr
```

- `PROGRESS.md`: feature ledger: what's shipped, what's tested, what's missing.
- `BUILD-GUIDE.md`: full build walk, wiring, demo-day checklist.
- `PARTS-LIST.md`: hardware BOM for all three devices.
- `PI-TO-LAPTOP-GUIDE.md`: networking + dashboard on a laptop.
- `esp32/wrist.ino`: wrist firmware sketch.
- `ui-kit/README.md`: NOIRKIT design system the dashboard runs on.
- `/motion.html`: safe, simulated conditional-animation rehearsal for the UI/UX demo.
- `ui-kit/film/`: source for the premiere's film (three.js set, rendered frame by frame).

Team-only positioning and judging-track intent live in `INTERNAL-NOTES.md`;
that document is not served by the app.

## Hub (hat Pi 4GB)

```sh
bash install_pi.sh && sudo systemctl start heist   # on the Pi
# laptop dev:
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # add OPENAI_API_KEY and/or ANTHROPIC_API_KEY
python -m rig.app
```

Dashboard at `http://<pi>:5000/`. GPIO17 = reveal button (Enter on laptop).
GPIO27 = mic button (`q`+Enter on laptop): records a few seconds, asks dispatch
for a grounded exercise check-in, then speaks the answer. Dispatch uses the
case ledger and configured job clock; it isn't a real-world safety or detection timer.

## Wrist (ESP32 + SSD1306)

Flash `esp32/wrist.ino`, set `WIFI_SSID`/`WIFI_PASS`/`HUB` at the top. It
polls `GET /wrist.json` every 2s and renders case no, take, count, top-5.

## Rover (Pi4 2GB)

Same codebase, different entry point:

```sh
HUB_URL=http://raspberrypi.local:5000 RIG_TOKEN=crew python -m rig.rover
```

Captures, gates, identifies, prices locally, then POSTs exhibits to the
hub's ledger. Queues finds if the Wi-Fi blinks; refiles next tick.

## Routes

| Route | What |
|---|---|
| `/` `/reveal` | live scan view / reveal view (client swaps on `revealed`) |
| `/manifest` | printable asset case file (QR'd from the dashboard; retains the themed “Loot Manifest” label) |
| `/state.json` | dashboard poll contract |
| `/wrist.json` | compact top-5 for the ESP32 |
| `POST /api/exhibit` | rover files a find (`X-Rig-Token` if `RIG_TOKEN` set) |
| `POST /api/rover_ping` | rover heartbeat; registers the teleop address |
| `POST /api/drive` | teleop relay: hub forwards `{dir, secs}` to the rover |
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
Anthropic, then the offline catalog → `pricing.resolve_detailed` tries SerpAPI
sold-listing comps, then a model quote, then the vision number, every price
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
