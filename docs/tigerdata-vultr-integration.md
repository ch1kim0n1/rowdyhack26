# TigerData + Vultr integration

How The Appraisal Job uses **Tiger Cloud (TimescaleDB)** and **Vultr** — the
plan, the division of labour, and the near-zero-delay sync across the hat,
rover, and wrist. Everything here is additive and env-gated: with no
`TIGER_DB_URL` and no `VULTR_API_KEY` set, the rig behaves exactly as it does
today (offline catalog, JSON ledger, 2 s wrist poll), so the demo never hard-
depends on a network that might blink on the floor.

## TL;DR of the two tracks

| Sponsor | What it is best at | What it does here |
|---|---|---|
| **Tiger Cloud / TimescaleDB** | Append-heavy time-series + fast analytic reads over huge, growing event streams; Postgres underneath (so `LISTEN/NOTIFY`, SQL, continuous aggregates, columnar compression) | The **cloud event ledger**: every recognition from every device is one row in a `detections` **hypertable**. A **continuous aggregate** precomputes "take over time / top value per case", and a `NOTIFY` trigger is the cross-hub push backbone. |
| **Vultr Serverless Inference** | OpenAI-compatible multimodal + text inference, no GPU to manage; also Cloud GPU / Compute if you want to self-host | Runs the **vision model** that recognizes items (a third provider beside OpenAI/Anthropic) and the **analysis layer** (end-of-case insights, RAG over the ledger, TTS/STT). Optionally hosts the Flask hub itself. |

---

## Rating your idea

> "TimescaleDB hypertables to get fast reads and writes so, as soon as a viable
> item is recognized, we get near real-time accurate solutions/database logs.
> That data of what was recognized gets analyzed by Vultr, which also runs the
> computer-vision model."

**Score: 8.5 / 10 — the instincts are right and the division of labour is
exactly how a judge would want to see both sponsors used. Two honest
corrections make it bulletproof:**

1. **Hypertables are the right home, but for the right reason.** A *single*
   `INSERT` into plain Postgres is already sub-millisecond — hypertables don't
   make one write meaningfully faster. What they buy you is **scale and
   analytics**: an append-only stream that stays fast as detections pile up
   across many walks and three devices, plus **continuous aggregates** so
   "running take", "top-5", and "value over time" are *precomputed* instead of
   re-summed on every poll, plus **Hypercore columnar compression** for old
   cases. So the pitch is "a time-series ledger that scales and serves instant
   analytics", not "faster single writes". That framing is both true and more
   impressive.

2. **"Near real-time" comes from push, not from the DB being fast.** Polling a
   fast DB every 2 s is still 2 s of latency. The real near-zero-delay path is
   **`LISTEN/NOTIFY`** (a Postgres/Timescale feature) fanned out to the devices
   over **SSE / long-poll**. TimescaleDB *enables* this because it's Postgres;
   the DB speed and the sync latency are two different wins, and you get both.

Everything else in your idea lands: Vultr as the CV engine **and** the analysis
brain is a clean, non-redundant split, and logging every recognition to Tiger
for later analysis is precisely the time-series use case the track asks for.

**What I'd add to make it "extremely useful" rather than just "integrated":**
the detections hypertable is what makes the **Defender Report** and the wrist's
"most valuable items" trustworthy across *multiple* walks — you can answer "what
has this team ever seen, where, and when" in one SQL query, which the current
single-JSON-file ledger can't do. That's the feature that justifies a database
at all, versus the file we already have.

---

## Where it plugs into the existing architecture

Today (unchanged, still the offline-safe core):

```
rover ─POST /api/exhibit─┐
                         ├─► hub (hat): rig/store.Store  ──► case.json (+ stills)
hat camera ──────────────┘        │
                                  ├─ GET /state.json   (dashboard @80ms, desk @1s)
                                  └─ GET /wrist.json    (ESP32 @2s)
```

After (new pieces marked ✦, all optional):

```
rover ─POST /api/exhibit─┐
                         ├─► hub: Store ──► case.json          (source of truth, offline-safe)
hat camera ──────────────┘        │
   │  vision.identify              ├─✦ timescale.record_detection(...)  ──► Tiger Cloud
   │   ├ openai                    │        detections hypertable
   │   ├ anthropic                 │        + detections_5m continuous aggregate
   │   └✦ vultr   (CV model)       │        + NOTIFY 'detections'  ─────┐
   │                               │                                    │
   └✦ vultr.analyze(ledger)  ◄─────┤  insights / report                 │
                                   │                                    ▼
                                   └─✦ sync.ChangeBus ──► SSE /events  (dashboard, desk)
                                                      └─► long-poll /wrist.json?wait  (ESP32)
                                        ▲                                │
                                        └── pg LISTEN 'detections' ──────┘  (multi-hub fan-in)
```

The store stays the **source of truth** and stays pure (no network). Tiger is
the **durable, queryable history + the push trigger**. The change bus is the
**in-process nerve** that turns a store mutation into an instant push.

---

## Part 1 — Tiger Cloud (TimescaleDB)

### Schema (`rig/timescale_schema.sql`)

- **`detections` hypertable** — one row per recognition, from either device:
  `ts, case_no, device, n, item, category, value_usd, estimated, source,
  price_source, weight_lb, mode, hot`. Append-only; this is the event stream.
- **`detections_5m` continuous aggregate** — `time_bucket('5 minutes')` →
  `finds, take, top_value` per case/device, with a refresh policy and real-time
  aggregation on, so "value over time" and leaderboards read instantly.
- **Hypercore compression** — `compress_segmentby = case_no, device`, policy
  compresses cases older than 7 days. Demonstrates the columnar engine.
- **`NOTIFY 'detections'`** trigger — fires on every insert; this is what lets a
  second hub (or a cloud dashboard) react in real time without polling.

Bootstrap is **idempotent** (`IF NOT EXISTS` throughout). It runs
**automatically on hub startup** (`timescale.ensure_schema_async`, in the
background, non-fatal if the DB is unreachable), so a working `TIGER_DB_URL` is
all the operator needs — no CLI step. `python -m rig.timescale bootstrap` / `…
check` remain for manual use.

### Write path (`rig/timescale.record_detection`)

Non-blocking by design — mirrors the rover's "never stall the frame loop" rule.
`record_detection` just **enqueues**; a daemon worker drains to Tiger over one
persistent connection and reconnects on failure. A full queue drops oldest. If
`TIGER_DB_URL` is unset the call is a no-op and nothing is imported, so tests
and offline demos are untouched.

**Every object, nothing filtered.** The vision pass now identifies *every*
object in the frame (`vision.identify_all`, multi-object prompt), not just the
clearest one — headphones, a chair, a table, a fan, jewelry, all of it. Each
recognition is written to the hypertable **whether or not the dedup ledger
keeps it** (the raw event stream wants the repeats; the case ledger stays clean
for the live UI). That is what fills Tiger with enough data for the analytics to
matter. `VISION_MAX_OBJECTS` caps how many one look may file.

### Read path (analytics)

`top_values(case_no)`, `take_series(case_no)`, `lifetime_top(limit)` — thin SQL
helpers over the hypertable and the continuous aggregate, used by the Defender
Report and `/api/insights`. These are the "fast analytics" the track is about.

### Why this is the honest, useful win

The JSON ledger answers "what's in *this* case right now". The hypertable
answers "what has the crew seen across *every* walk, bucketed over time, ranked
by value" — in one query, fast, and it keeps being fast as the data grows.

---

## Part 2 — Vultr

### 2a. Vision provider (`rig/vultr.py` → wired into `rig/vision.py`)

Vultr Serverless Inference is OpenAI-compatible
(`https://api.vultrinference.com/v1/chat/completions`, `Authorization: Bearer`),
and its live catalog includes multimodal models that accept base64 JPEG
(`deepseek-v4-flash-0731`, `glm-5.3-flash`, `qwen3.8-flash-next`, …). So Vultr
drops into the existing provider ladder as a **third identify() backend** using
the exact same prompt and `parse_response` JSON contract:

```
openai  →  anthropic  →  vultr  →  offline catalog     (default order)
```

Set `VULTR_API_KEY` to enable it; set `VULTR_VISION_FIRST=1` to make Vultr the
primary CV engine (your stated goal — "Vultr runs the computer-vision model").
Model is `VULTR_VISION_MODEL` (default `deepseek-v4-flash-0731`). Because we
reuse `vision.parse_response`, no response-format assumptions are made.

### 2b. Analysis layer (`rig/vultr.analyze_analytics`)

`/api/insights` is the instant-analytics endpoint and the heart of the
TigerData + Vultr pairing: **TimescaleDB's hypertable does the fast aggregation,
Vultr reasons over the numbers.** When Tiger is on, the endpoint runs the fast
hypertable / continuous-aggregate queries (`case_analytics`: this case's
leaderboard, take-over-time, and the all-time top) and hands those precomputed
stats to a Vultr text model (`VULTR_TEXT_MODEL`, default `deepseek-v4.1-flash`)
for a 2-3 sentence read. The `stats` come back even with no Vultr key, so the
hypertable speed is demonstrable on its own; Vultr adds the narrative. With
Tiger off it falls back to summarizing the in-memory ledger. Grounded strictly
in filed data (no invented findings), consistent with the project's claim
boundaries.

Vultr also offers, if we want them later, `/v1/embeddings` + `/v1/vector_store`
(RAG over past cases), `/v1/audio/speech` (narrator TTS) and
`/v1/audio/transcriptions` (the radio's Whisper step) — all the same key.

### 2c. Compute (optional)

A Vultr Cloud Compute VM can host the Flask hub so all three devices and a
remote dashboard reach one public endpoint instead of the venue LAN; a Cloud
GPU instance could self-host a YOLO/VLM if you outgrow serverless. Not required
for the demo — serverless inference is the low-friction, high-signal path.

---

## Part 3 — Near-zero-delay sync across the three devices

The latency problem today: the wrist polls every 2 s, the dashboard every
80 ms, the desk every 1 s. The fix is **push**, built on one small in-process
primitive plus the DB's `NOTIFY`.

### `rig/sync.ChangeBus` (pure stdlib, always on)

A `threading.Condition` + a monotonically increasing `version` + the last
compact payload. Every store mutation (new exhibit, reveal, reset, status,
plan) calls `bus.publish(payload)`; waiters wake immediately.

### Three transports, one bus

- **Dashboard & desk → SSE** `GET /events`: a `text/event-stream` that emits the
  compact state the instant the bus bumps (heartbeat every ~15 s). Browsers
  reconnect automatically. **Wired in:** `ui-kit/noir.js` (dashboard) and
  `ui-kit/desk.js` (desk) each open an `EventSource('/events')` that pokes an
  immediate refresh on every message; the existing interval polling stays as the
  fallback (and covers token mode, where `EventSource` can't send the header).
- **Wrist (ESP32) → long-poll** `GET /wrist.json?since=<v>&wait=<secs>`: blocks
  on the bus until `version > since` (or the timeout), then returns the usual
  body plus `"v"`. The firmware keeps `v` and re-requests with it, so an update
  reaches the wrist in **tens of milliseconds** instead of up to 2 s, with
  *fewer* requests. A plain `GET /wrist.json` (no args) is unchanged, so every
  existing client and test still works.
- **Multi-hub → `LISTEN 'detections'`**: a second hub (or a Vultr-hosted
  dashboard) can `LISTEN` on Tiger and republish to its own bus, so two hats on
  the same case converge in real time. This is the bridge between Part 1 and
  Part 3.

### Why long-poll for the wrist and SSE for the browsers

SSE is the clean browser story (EventSource, auto-reconnect). But SSE on a
battery ESP32 behind flaky venue Wi-Fi is fiddly; a `since`+`wait` long-poll is
dead-simple firmware, survives reconnects trivially, and gives the same
perceived latency. Right tool per device.

---

## Turnkey: what the operator supplies

The build is complete and env-gated. To switch the sponsors on, add two values to
`.env` and restart the hub — nothing else:

```
TIGER_DB_URL=postgres://tsdbadmin:<pw>@<host>.tsdb.cloud.timescale.com:<port>/tsdb?sslmode=require
VULTR_API_KEY=<your-vultr-serverless-inference-key>
VULTR_VISION_FIRST=1     # optional: make Vultr the primary CV engine
```

On startup the hub auto-creates the Tiger schema, begins streaming every
recognized object to the hypertable, and `/api/insights` starts answering with
hypertable analytics + a Vultr read. `pip install -r requirements.txt` pulls in
`psycopg[binary]` (only used when `TIGER_DB_URL` is set).

## Rollout order

1. `rig/sync.py` + SSE + wrist long-poll + firmware — **the headline "zero-delay
   sync" feature**, works with zero cloud dependencies.
2. `rig/vultr.py` + vision wiring — Vultr as the CV engine, one key to enable.
3. `rig/timescale.py` + schema + record/analytics hooks — the Tiger ledger.
4. `vultr.analyze` + `/api/insights` — the analysis brain.
5. Bootstrap Tiger (`python -m rig.timescale bootstrap`) on a live, writable
   service and demo "value over time" from the continuous aggregate.

Each step is independently demoable and independently revertible, and none of
them weakens the offline-safe core.
