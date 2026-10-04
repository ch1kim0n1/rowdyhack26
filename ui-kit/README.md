# NOIRKIT: the case file UI system

Black and white, one red stamp, three screens. Title cards, case files,
evidence markers, and a lineup for an authorized physical red-team dashboard.
The film-noir styling is the presentation; the purpose is asset observation,
documentation, and debriefing. Internal track strategy lives in
`../INTERNAL-NOTES.md`, not in the public landing-page pitch.

| Route | Screen | Treatment |
|---|---|---|
| `/` | Live walk | Surveillance film reel and evidence ledger |
| `/reveal` | Top-5 reveal | Police lineup, "THE USUAL SUSPECTS" |
| `/manifest` | QR share page | Typed case file on paper |

## 0. Start here

### Conditional motion (2026-10-02)

Open `/motion.html` for the safe UI/UX rehearsal. It uses simulated data and
does not call the rig. The same status controller is connected to real state
on `/` and `/desk`, and to fake observations on `/demo.html`.

| Condition | Feedback |
| --- | --- |
| First connection | Threading film cells; waiting for a confirmed snapshot |
| `pending: true` | Analyzing-frame strip and elapsed time; after 10s, a slow-response explanation |
| Ready, no items | An actionable empty state, not a perpetual spinner |
| New item | One paper-arrival notice; new desk rows enter once, not on every poll |
| Camera lost | Static recovery state; previous findings remain visible |
| Hub unreachable | Stale-data explanation; reconnect notice only after a confirmed snapshot |
| Reveal / reset | Existing film transition, debrief choreography, and next-case feedback |
| Button request | Busy/disabled while sending; confirmation only for successful HTTP responses; failure/timeout restores control |

`motion.js` owns the state edges and `motion.css` owns the treatment. Scripts
load before `noir.js`. No fake percentages, inferred model confidence, or
claims that dollar value measures security risk. Remote item names remain
text, never HTML. Source badges distinguish estimates and offline demo data.

The live UI keeps its existing **Pause motion / Resume motion** navigation
control. The rehearsal and offline demo use **Motion: full / reduced**. Both
share the `appraisal-motion` preference and respect system reduced motion.
Reduced motion removes decorative loops and makes typing/reveal immediate;
background tabs pause CSS animation. The latest `main` UI is the baseline:
its vault artwork, spyglass intro, job picker, reveal skip, credential exhibits,
and Defender Report links remain intact. Conditional feedback is layered onto
that runtime, whose live polling remains independent of visual choreography.

Run `node --test tests/test_motion.cjs` for motion contracts. Python route
tests check that the required files load on all three screens.

`kit.html` renders every token, component, state, and animation with the real stylesheet. This README is the reasoning. If they disagree, the Case Index is right and this file needs fixing.

The rig serves the kit with the dashboard. Open `/kit`. Section 00 is the floor: grain, flicker, vignette, the one red stamp, hover, and a tape roll that goes picture, black, next picture. Press Roll the tape again and it rewinds. `/demo.html` and `/board.html` are on the same server. Stills are in `handoff/`.

Integration takes four steps:

1. Link `noir.css` and copy the `fonts/` folder next to it. Fonts are vendored and nothing loads from the internet.
2. Copy the markup from `demo.html` (everything above the demo driver) into the Flask template. Swap the demo `<canvas id="frame">` for `<img id="frame" class="feed-img" alt="">`, and the fake QR `<svg>` for the server's QR image.
3. Add `<script src="noir.js"></script><script>Noir.connect('/state.json')</script>`. That is the whole client.
4. Build the three backend routes in `BUILD-GUIDE.md` section 4.2: a clean `/frame.jpg`, `/state.json` and `/crop/<n>.jpg`.

| File | What it is |
|---|---|
| `kit.html` | The Case Index: tokens (read live), every component and state with copyable markup, motion players, screen previews, the state matrix, a projector test card and a `tokens.json` export |
| `noir.css` | The stylesheet, tokens first, then every component. Fluid from a 1024px projector to a 2560px screen |
| `noir.js` | The runtime: `Noir.connect()` plus every behavior (typing, odometer, markers, reveal, projection, states, sound) |
| `fonts/` | Web fonts (latin woff2) and a League Gothic TTF for the OLED. Licenses in `fonts/README.md` |
| `demo.html` | The template markup plus a fake-data driver. Keys: L walk, R reveal, M manifest, T title card, F footage lost, W line dead, U unidentified, B huge take, 3 short lineup, 0 empty lineup, L after R for the end card, S sound, ? key list |
| `tokens.json` | Every token in W3C design-token format for Figma (Tokens Studio). Re-export from `kit.html` after changing `noir.css` |
| `board.html` | The design brief for the judges' table, built as a dossier on a desk (section 18) |
| `packs/` | Font, asset and animation packs for designers (section 16) |
| `oled-preview.png` | The rig's 128x64 OLED in the same style (code in `BUILD-GUIDE.md`) |
| `shots/` | Stills and `reveal.gif` for the Devpost gallery |

### The `Noir` API

| Call | What it does |
|---|---|
| `Noir.connect(url, {every, frameUrl, cropUrl})` | Plays the reel start, then polls the rig and drives everything below. Defaults: `/state.json` every 80ms, `/frame.jpg`, `/crop/<n>.jpg` |
| `Noir.pending(n)` | Types `> EXAMINING EXHIBIT 0n...` and returns the line |
| `Noir.showExhibit(item, line?)` | The scan beat: typed line, marker, odometer. Takes over the pending line if there is one |
| `Noir.voidExhibit(line?)` | `EXHIBIT ??: UNIDENTIFIED`, struck through |
| `Noir.runReveal(items)` | The full reveal for any number of items, including the vacant and empty cases |
| `Noir.buildManifest(items)` | Fills the case file |
| `Noir.setFeed('ok' \| 'lost' \| 'dead')` | Feed slate state |
| `Noir.setOffline(bool)` | LINE DEAD in the header, the feed and the ledger |
| `Noir.newCase()` | Ends a run: THE END card if a reveal was showing, next case number, clean ledger |
| `Noir.reelStart()`, `Noir.cue()`, `Noir.theEnd()` | The projection moments (section 5) |
| `Noir.armIdle()`, `Noir.exitIdle()` | Title card after `--idle-after` of quiet, or off now |
| `Noir.cutType(el)` | Cut-paper lettering, applied automatically to every `.cut` element |
| `Noir.makeOdo(el).set(n)` | A standalone odometer |
| `Noir.sfx.toggle(bool)` | Sound on or off (section 11) |

Items use the `/state.json` shape `{n, item, value_usd, estimated, bbox}`. `connect()` turns the normalized `bbox` array into the marker's percentages. When calling the functions directly, pass `{l, t, w, h}` in percent.

## 1. The idea

The style is 1950s black-and-white film noir, at the point where Saul Bass title design meets police-station paperwork: flat cut-paper shapes, hard contrast, condensed capitals, typewritten forms, rubber stamps, evidence tags, grain and projector flicker. Picture the title sequence of a heist film crossed with the case file that film would produce.

The design goal is a dashboard that looks like a designed object. The target is a frame of the movie itself. If a screenshot of any state went into a gallery of 1950s film stills, nobody should pick it out as a web page. The walk is reel 1, assessment footage. The button press is the changeover to reel 2, the debrief lineup. The stamp is the title card.

What success looks like:

- A judge glancing from six feet away reads "noir crime film", and nobody says "dark mode".
- The screen stays alive during the walk the way a projected frame is: log lines type, the take ticks up, markers land, and the grain and gate keep moving.
- Motion follows film editing: cuts, dissolves, freeze-frames and loops shot on twos. App transitions have no place here.
- The reveal lands as one continuous beat: dissolve, lineup, total, stamp, with no gap between them.

The deciding question for any design call: would this exist in a 1950s police station, or on 1950s film stock? A blue button, a rounded card, a toast notification or a glowing badge would not, so none of them appear. When in doubt, strip it back to black, white, type and one red stamp.

Out of scope: a generic dark theme, CRT or terminal looks (wrong decade, this is film), and a system meant to scale to other products. It serves three screens and one demo.

> A red-team field kit for authorized asset reconnaissance.

The screen is the paperwork. Each observed asset is an exhibit. The price is
an appraisal. The top five is a debrief lineup ranked by estimated market
value, not a vulnerability or risk score. The page you scan is a stamped case
file. “Take” is a theatrical label for the summed estimated asset value; no
property is taken. Every styling call after that follows from it.

Each screen has one job. Research on in-world ("diegetic") interfaces keeps landing on the same limit: three or four pieces of information on screen at once.

| Screen | Its job | What's on it |
|---|---|---|
| Title card | Explain the idea in five seconds with nobody talking | Title, one credit line, one instruction |
| Live walk | Make the room watch the take climb | Footage, the take, the ledger, the header |
| Reveal | Five suspects, one total, one stamp | The lineup, the total, one stamp, and the QR |
| Case file | A page you can scan, read on a phone, or print | The rows, the total, two stamps, the QR |

References for the look: Saul Bass title sequences (Anatomy of a Murder, The Man with the Golden Arm) for cut-paper shapes and condensed capitals; noir release prints for flicker, dust, scratches, crushed blacks and blown highlights; physical evidence for tent markers, kraft folders, stamps, typed forms and dot-leader ledgers; police lineup walls for height rules.

## 2. Palette

This is a black-and-white film with one ink. Stamp-pad red appears only as a rubber stamp. It never touches text, chrome or anything interactive, and there is no second accent.

| Token | Value | Use |
|---|---|---|
| `--black` | `#000000` | Deepest shadow only: letterbox bars, vignette core |
| `--ink` | `#0f0e0c` | App background. A warm near-black, since film blacks are never pure |
| `--carbon` | `#1a1916` | Panels, film bands, slates |
| `--smoke` | `#57564f` | Hairlines, dim text, inactive elements |
| `--ash` | `#8f8d83` | Secondary text: labels, timestamps, counters |
| `--bone` | `#d8d4c7` | Borders, markers, secondary display text |
| `--paper` | `#efe9db` | Brightest text and document stock |
| `--stamp` | `#a5382f` | Stamps on paper: EVIDENCE, FILED |
| `--stamp-lit` | `#d9604f` | Stamps on dark screens: CASE CLOSED. The same ink under projector light |
| `--paper-ink-2` | `#3a382f` | Secondary type on paper |
| `--paper-ink-3` | `#4a473e` | Fine print on paper |
| `--paper-rule` | `#7a7568` | Dot leaders on paper (decorative) |

Contrast: paper on ink is about 15:1 and bone on carbon about 9:1. Ash on ink is 5.8:1, fine for secondary text at 11px or larger. `--stamp` on ink is only 2.95:1 and turns to mud on a projector, which is why dark screens use `--stamp-lit` (5.3:1). On paper, `--stamp` is 5.4:1.

Two hard rules. A stamp never sits over the QR, because it breaks scanning. And the `№` glyph is out: Courier Prime doesn't include it, so it fell back to a mismatched font. Write `NO.` instead.

## 3. Type

Four faces, each with one job, all vendored in `fonts/` and loaded by `noir.css`. `font-display: block` hides text for a moment rather than flashing Arial.

| Role | Face | Fallback |
|---|---|---|
| Headline: the take, titles, names | League Gothic 400, capitals | "Bebas Neue", "Arial Narrow", Impact |
| Typed entry: the exhibit log and the case file | Special Elite 400 | "Courier Prime", monospace |
| Printed form: labels, meta, chrome, placards | Courier Prime 400 and 700 | "Courier New", monospace |
| Marginalia: one pencil note per screen | Caveat 500 | cursive |

League Gothic revives Alternate Gothic (1903), the condensed face on mid-century headlines and film posters. Bebas Neue, the usual pick for this look, is a 2010s font every judge has already seen. Special Elite is a worn typewriter face with uneven ink, so the case file reads as typed by hand. Courier Prime looks clean and digital by comparison, which suits printed labels.

The split between printed and typed follows how real forms worked. Labels were printed on the blank form and an officer typed the entries onto it. So labels are Courier Prime and anything the machine writes is Special Elite. Special Elite has one weight and is never set bold.

### Cut-paper lettering

Big titles (the title card, THE USUAL SUSPECTS, THE END, the board's premise) get a Saul Bass treatment. `Noir.cutType(el)` wraps each letter in a span with a small fixed tilt (up to 2.5 degrees) and baseline shift. The offsets are seeded by position, so a title always lands the same way and never shimmers, and words never break mid-letter. This makes the headline face ours. Numbers and names stay straight, because they have to read cleanly.

### Scale

Sizes are tokens in `noir.css`, fluid through the scale unit `--u` (section 6). Pixel values below are at the 1440px reference; the Case Index shows them computed at your window.

| Class | Token | At 1440 | Face | Tracking | Line |
|---|---|---|---|---|---|
| `.t-hero` (the take) | `--fs-hero` | 130px, capped at 17% of the height | League Gothic | .01em | .85 |
| `.t-view` (view titles) | `--fs-view` | 64px | League Gothic, `.cut` | .04em | .95 |
| `.t-item` (suspect names) | `--fs-item` | 34px | League Gothic | .02em | 1.0 |
| `.t-data` (log, case file) | `--fs-data` | 15px | Special Elite | 0 | 1.45 |
| `.label` | `--fs-label` | 11px | Courier Prime 700 | .20em | 1.3 |
| `.meta` | `--fs-meta` | 11px | Courier Prime | .14em | 1.4 |
| `.note` | `--fs-note` | 19px | Caveat | 0 | 1.2, rotated -2 degrees |

The remaining sizes are `--fs-total` (reveal total), `--fs-title` (title card), `--fs-slate`, `--fs-stamp`, `--fs-price`, `--fs-cap` (marker captions, placards) and `--fs-tag` (10px, the smallest text in the kit).

Display type is always capitals and only ever paper or bone; `noir.css` forces the case because League Gothic has lowercase. Labels use wide tracking in bold Courier Prime, the printed-field look. There are no italics outside marginalia, and one pencil note per screen at most.

## 4. Grading and texture

Five subtle layers turn a grey website into noir footage. Each is optional on its own.

The live feed is graded like surveillance stock: `grayscale(1) contrast(1.28) brightness(.92)` plus `#noir-grade`, an SVG S-curve defined inline in the page. It lifts the black floor to about 2%, because true black never appears on film, and rolls the highlights off at 97%. Without SVG filters the CSS part still reads correctly. The filter is safe on a still that changes every two seconds. It must never go on a playing `<video>`, where it forces a CPU pass on every frame.

Grain is a fixed full-screen overlay: a 160px `feTurbulence` noise tile at 5% opacity with `mix-blend-mode: overlay`. The layer is oversized and jumps between eight positions at about 12fps using `transform`, so it runs on the compositor with no repaint. Film grain jumps rather than drifts.

Projector flicker is an ink overlay with `multiply` whose opacity wanders between 0 and 3% over a 7.3 second loop, felt more than seen. An earlier draft added a periodic brightness dip on top. It was cut: stacked effects read as a lack of control.

Every 6 to 12 seconds a 1px hair shows in the gate for 90ms at a random position, with two or three specks of dust near the top (`scheduleScratch()` in `noir.js`). A vignette darkens the corners to 55%, slightly stronger over the footage.

Gate weave: film never sits perfectly still in a projector gate. The live and reveal views drift 1px sideways, rarely vertically, on twos over a 2.2 second loop (`--weave-cycle`). The case file doesn't weave, since it's paper.

`prefers-reduced-motion` removes grain, flicker, scratches, weave, the reel start and the cue mark, and completes every animation instantly. No content is withheld.

## 5. Projection

These are the details that make the laptop behave like a reel in a 1950s projector. All of them come from how theatrical projection actually worked.

The Academy leader (1930 to the mid-1960s) counts a reel in: a number in a circle, one per foot of film, which is 16 frames or 0.67 seconds at 24fps (`--dur-leader-foot`). NINE and SIX were spelled out so they couldn't be misread upside down. The kit counts 8, 7, SIX, 5, 4, 3. The countdown with a sweeping clock hand that most people picture is the SMPTE universal leader from 1965, a decade too late, so the kit doesn't use it.

The reel start (`Noir.reelStart()`) plays once when the page boots: PICTURE START, then the countdown, a beep on 3 when sound is on, two black frames, then the title card. `Noir.connect()` runs it before the first poll. The FOOTAGE LOST and LINE DEAD slates loop the same leader while they're up.

The changeover cue (`Noir.cue()`) is the white circle that tells a projectionist to switch projectors: top right, four frames (`--dur-cue`, 167ms), about a second before a reel ends. Here it flashes on the button press, the end of reel 1, just before the freeze-frame and the dissolve to the lineup. The headers read REEL 1 on the walk and REEL 2 on the lineup.

THE END (`Noir.theEnd()`) closes every run: the card dissolves in, holds for 3.2 seconds (`--dur-the-end`), and the title card follows. The case number advances with the next run.

The film band above the feed carries edge print, the stock markings between the perforations and the picture: SAFETY FILM and key numbers. Safety film replaced nitrate stock around 1951, so it's right for the period.

## 6. Scale, layout and chrome

The scale unit `--u` is 1px up to a 1440px-wide screen and grows with the screen above that, to 1.8px at 2592px. Every size in the kit is a multiple of it, so the 1440 design is the reference and a 4K projector shows the same composition, larger. Below 1440 it stays at 1px. The layout was checked at 1024x768, 1280x720, 1366x768, 1920x1080 and 2560x1440, with a phone at 360px for the case file.

Spacing is an 8pt grid with 4 and 12 as half-steps: `--sp-1` 4, `--sp-2` 8, `--sp-3` 12, `--sp-4` 16, `--sp-5` 24, `--sp-6` 32, `--sp-7` 48 (px at 1440). Layers are tokens too, from low to high: title card 80, reel start and THE END 84, cue 86, curtain 87, flicker 88, vignette 89, grain 90, scratches 91, demo hints 95. Film texture always sits on top, so every overlay still reads as the same film.

Hairlines are `var(--rule)`, 1px, in smoke, or bone where they must read at a distance. Corners are square, apart from 2px on the feed frame and QR mat and 3px on stamps. There are no drop shadows on chrome; the paper document is the one exception, because it's a physical object on a desk. The only gradients are the vignette, the lamp glow behind the lineup wall and paper shading.

Every view has a header strip. On the left is the case number. On the right is the reel, the frame counter, and the line status: a blinking `● REC` while the rig answers, `○ LINE DEAD` when it stops. The case number advances with every run in the header, the title card credits and the case file.

The dashboard uses fewer grey capital labels than a generic dark dashboard: a handful per screen, all of them printed-form labels that a real 1950s form would carry. Decorative filler labels (a fake room number, a fake timer) were removed; fake detail reads as machine-made.

## 7. Components

### Film-strip feed frame `.film`

The feed sits in a strip of surveillance film: carbon bands top and bottom with a row of sprocket holes, edge print on the top band, `ROLL A · CAM 01 · OPTIC SURVEILLANCE` on the bottom, and small registration marks in the frame corners.

The feed is a `.frame-box` that holds the frame at its own aspect ratio (`--ar`, 4/3 for a 640x480 webcam, close to the Academy ratio of 1.37) and letterboxes it in black like a film gate, so normalized bboxes land on the object whatever the panel's shape. The rig sends a still every two or three seconds and each one arrives as a short bone wash (`.feed.cutting`, `--dur-cut`), like a shutter rather than a strobe. The next image is preloaded before the swap, so a blank frame never shows.

### Evidence markers `.marker`

Detected items get crime-scene evidence markers: a 1px bone rectangle with a dark outer ring, so it reads over any footage (Return of the Obra Dinn outlines everything for the same reason), and a faintly hand-drawn edge from `#rough`. A tag above the corner reads `EXHIBIT 07`; a caption below reads `"WATCH, WRIST" · $4,200` and truncates at 38 characters. The box draws in over `--dur-marker`, then the tag and caption follow. The number comes from the exhibit counter, so it always matches the ledger. An item with no plausible bbox keeps its ledger line and its place in the take but gets no marker.

### Slates `.feed.lost`

When there's nothing to show, the feed shows a slate: the looping Academy leader, a League Gothic title and a line of meta.

| State | Cause | Title | Line |
|---|---|---|---|
| `lost` | The camera dropped (`camera_ok: false`) | FOOTAGE LOST | ROLL A · CAM 01 · RECONNECTING... |
| `dead` | The laptop can't reach the rig (3 failed polls, about 1.5s) | LINE DEAD | RIG UNREACHABLE · REDIALING... |

LINE DEAD also switches the header to `○ LINE DEAD` and types a system line into the ledger, then `> LINE RESTORED.` when the rig answers. Markers, the ledger and the take stay put: the case file doesn't lose evidence because the camera blinked.

### The odometer `.odo`

The running take is the centerpiece of the live view, set in League Gothic and rolling like a mechanical counter. Each digit is a wheel of 0 to 9, centered in its column. Digits roll right to left, `--stagger-digit` apart, over `--dur-odo` with `--ez-odo`: a little inertia, then a soft stop. A bounce would read as a slot machine, and this should feel like a bank vault. Commas don't roll. Long takes shrink to fit through `--odo-k`, so $1,282,600 still fits the column.

### Exhibit log `.log`

The ledger types itself like a case officer at a typewriter: `EXHIBIT 07: "WATCH, WRIST" ........ $4,200.00`, with dot leaders between the fields. A new line types at about 16ms per character with a blinking block caret, and a key sound every fourth character when sound is on. About eight lines fit; older lines fade to ash and drop off. Before the first scan it reads `> SCENE STABLE. AWAITING TARGETS...`.

While the model is working, a pending line types `> EXAMINING EXHIBIT 07...` in ash and the result replaces it, so latency reads as work. An unidentified scan is filed like anything else, struck through: `EXHIBIT ??: UNIDENTIFIED ...... NO APPRAISAL`. Long names end in an ellipsis inside the line, and the grid columns are `minmax(0, 1fr)`, so one verbose answer can't push the layout. Estimated prices carry a small `est.` everywhere a price appears.

The walk has a rhythm: the line finishes typing, the marker draws in, and the odometer rolls once the marker has settled. The beats are `--beat-mark` and `--beat-count`. Judges pick up typed, marked, counted within about ten seconds.

### Stamps `.stamp`

On screen a stamp is a 3px border in `--stamp-lit`, League Gothic at 30px tracked .12em, rotated a few degrees (never the same angle twice; set `--rot` so the slam keeps it), with worn edges from `#stamp-rough`. It lands over `--dur-stamp` on `--ez-stamp`: the curve stays soft and the keyframes do a small settle, then the desk answers with a decaying thud (`.shake`). One stamp per region, never aligned to the grid, because a hand applies stamps.

On paper the same stamp uses `--stamp` with `mix-blend-mode: multiply` at 78% opacity, like real ink, so the typing underneath stays readable. Over a dark photograph multiply would turn the ink black, so stamps on photos use the lit ink.

### Lineup wall `.lineup-wall`

The reveal background is a carbon-to-ink wash with height rules every 48px and foot-and-inch marks from 4'0" to 7'0". Each of the five slots holds a booking photo (the exhibit's bbox cropped from the frame it was found in, widened to 3:4, from `/crop/<n>.jpg`), a placard reading `SUSPECT NO. 5` like a mugshot letter board, and the name and price in fixed two-line boxes so every photo shares one baseline. Slots are capped by screen height as well as width, so on a short 1280x720 projector the total and stamp stay on screen. Until a crop loads the slot shows a faint shadow figure, kept dim so it never reads as an avatar icon.

With fewer than five suspects the empty ranks stand vacant (`NO. 5 · VACANT`, `NO SUSPECT`) and a subtitle reads `ONLY THREE SUSPECTS BROUGHT IN`. With none, the title is `NO SUSPECTS`, the stamp `CASE UNSOLVED`, the take $0.

### File copy `.file-copy`

The QR always sits on a paper mat, the only white object on a dark screen, because phone cameras need the contrast. The caption reads `FILE COPY · SCAN TO RETRIEVE`.

### Case file `.doc`

A portrait sheet of paper stock, tossed slightly off square, with masking tape at the corners and the kit's one drop shadow. Everything inside is Special Elite: the header, rows with dot leaders, a total under a double rule, and two stamps. On a phone it tightens up and scrolls normally; this is the screen judges hold. Printing gives a clean letter-size case file on white paper, with the stamps in color, to hand out.

### Title card `body.idle`

The live view's resting state, after 15 seconds without a scan. Torn-paper bars travel in from the edges, THE APPRAISAL JOB fades up in cut-paper League Gothic, one credit line crossfades every 2.4 seconds, and a line at the bottom tells people what to do. Each return to the card plays that entrance from the first frame. The first scan fades the card back to the walk.

## 8. Motion

Every duration, stagger and beat is a token in `noir.css` (`--dur-*`, `--stagger-*`, `--beat-*`, `--idle-after`, `--title-cycle`, `--weave-cycle`), and `noir.js` reads its timings from the same tokens, so one edit changes both. The Case Index lists each animation as the property that changes, its duration, easing and trigger, with a play button.

| Easing | Value | Use |
|---|---|---|
| `--ez-stamp` | `cubic-bezier(.33, .02, .2, 1)` | Stamp. Soft curve; the keyframes do a small settle |
| `--ez-settle` | `cubic-bezier(.42, .02, .18, 1)` | Entrances, markers, photo drops, title bars |
| `--ez-odo` | `cubic-bezier(.33, .02, .16, 1)` | Digit rolls |
| `--ez-film` | `cubic-bezier(.45, .03, .2, 1)` | Fades and dissolves |
| none | `steps()` | Grain only. The caret and REC blink ease |

Decorative grain still jumps, which is the film stock. Motion that carries the scene eases through a full arc, slow out of the gate and slow into the rest, so nothing pops.

### The reveal

| Time | What happens |
|---|---|
| 0 | The button fires. The changeover cue fades in at the top right. The feed starts to settle |
| during the settle | The curtain is already dissolving to black |
| as the curtain lifts | The lineup fades up. Suspects enter from rank 5 to rank 1, each one starting while the previous photo is still dropping. The placard and the name follow the photo. The price counts with a slow start and a slow finish |
| as the last photo lands | The total starts rolling |
| while the total is finishing | CASE CLOSED lands and the desk answers with a short decaying thud |

Ascending order is deliberate. The take builds to the best item, then the stamp lands. The pieces overlap, so it reads as one move.

When an item enters the top five during the walk and the speaker calls it out, that marker's tag flashes once from bone to paper, so the room connects the sound to the screen.

## 9. Copy deck

The voice is deadpan police paperwork produced by the crew's own machine. It is flat and procedural and never winks; the system doesn't know it's funny.

| Where | Copy |
|---|---|
| Live header | `CASE NO. 1138 · THE APPRAISAL JOB`, `REEL 1 · FR 00:14:32:08 · ● REC` |
| Feed band | `ROLL A · CAM 01 · OPTIC SURVEILLANCE` |
| Take | `ESTIMATED TAKE`, `ITEMS CATALOGED: 07`, `ESTIMATES MARKED est.` |
| Ledger | `EXHIBIT LOG · LIVE`; lines `EXHIBIT 07: "WATCH, WRIST" .... $4,200.00` |
| Empty ledger | `> SCENE STABLE. AWAITING TARGETS...` |
| Marginalia | `the good stuff's never on the first shelf.` |
| Footer | `Press the button on the cap for the lineup` |
| Reveal | `THE USUAL SUSPECTS`, placards `SUSPECT NO. 5` to `NO. 1`, `APPRAISED: $4,200`, `TOTAL APPRAISED TAKE`, `CASE CLOSED`, `FILE COPY · SCAN TO RETRIEVE` |
| Case file | `LOOT MANIFEST`, `JOB NO. 1138 · WHAT THE CAMERA PRICED`, `FILED WITH NOBODY AT THE DESK`, `TOTAL TAKE`, stamps `EVIDENCE` and `FILED 09/26/2026`, footer `PROPERTY OF THE CREW. DO NOT FILE.` |
| Reel start | `PICTURE START`, then `8`, `7`, `SIX`, `5`, `4`, `3` |
| Title card | `A ROWDYHACKS XII PICTURE`, `THE APPRAISAL JOB`; credits `CASE NO. 1138`, `STARRING WHATEVER'S ON THE SHELVES`, `APPRAISALS BY THE OPTIC SURVEILLANCE UNIT`, `FILMED ON LOCATION IN ROOM 3, EXHIBITS WING`; prompt `PUT ON THE CAP · WALK THE ROOM · PRESS THE BUTTON` |
| Scanning | `> EXAMINING EXHIBIT 07...` |
| Unidentified | `EXHIBIT ??: UNIDENTIFIED` ... `NO APPRAISAL` |
| Camera lost | `FOOTAGE LOST`, `ROLL A · CAM 01 · RECONNECTING...` |
| Rig unreachable | `LINE DEAD`, `RIG UNREACHABLE · REDIALING...`; header `○ LINE DEAD`; ledger `> LINE TO THE RIG IS DEAD. REDIALING...` then `> LINE RESTORED.` |
| Few or no suspects | `ONLY THREE SUSPECTS BROUGHT IN`, `NO. 5 · VACANT`, `NO SUSPECT`; `NO SUSPECTS`, `CASE UNSOLVED`, `NO EXHIBITS RECOVERED` |
| End of a run | `A ROWDYHACKS XII PICTURE`, `THE END`, `CASE NO. 1138 · CLOSED` |

A price the model estimated rather than found in comps reads `$4,200.00 est.` The honest mark survives the theme.

Copy rules: no em dashes, no arrows, no curly quotes and no emoji. Separators are `·` or a colon. Status lines are short sentences ending in a period. Nothing is invented for decoration; every label on screen is true.

## 10. Wiring to the Flask app

Three backend changes make the kit work with real data, all written up in `BUILD-GUIDE.md` section 4.2. `/frame.jpg` must be clean, with no boxes drawn by OpenCV: the dashboard draws its own markers, and burned-in gold boxes would double up and add a second color. `/state.json` returns `frame_id`, `camera_ok`, `pending`, `revealed`, `take` and `items[{n, item, value_usd, estimated, bbox}]`, with the bbox normalized as `[x, y, w, h]`. `/crop/<n>.jpg` returns the booking photo for exhibit n.

In the kit, `/`, `/reveal` and `/manifest` are one page that swaps `.view`s, so the freeze-frame and dissolve work without a reload. The client is one line, `Noir.connect('/state.json')`. It plays the reel start, shows the title card, then on each poll:

| `/state.json` says | The screen does |
|---|---|
| no answer three times | LINE DEAD; the first good answer restores it |
| `camera_ok: false` | FOOTAGE LOST slate |
| a new `frame_id` | Preloads `/frame.jpg?<id>`, cuts to it, sets `--ar` from the image |
| `pending: true` | Types the EXAMINING line |
| new entries in `items` | The scan beat for each, in order, then re-arms the title card timer |
| `revealed` becomes true | The reveal |
| `revealed` goes back to false | THE END, then the title card; the next case number |

`/manifest` also stays its own route, since phones reach it from the QR. Render the `.doc` server-side with the same rows and `est.` marks, and include `noir.css`.

This path was tested against a mock rig that runs a scripted walk through the contract: a pending line, four exhibits (one without a bbox), a camera drop, the rig going silent and coming back, a reveal with real crops, and a second run.

## 11. Sound, voice and the OLED

Dashboard sound is off by default, because venues are loud and the rig's speaker carries the voice. `?sound` in the URL turns it on at the first key press or click (browsers need a gesture), or call `Noir.sfx.toggle(true)`. Launching Chrome with `--autoplay-policy=no-user-gesture-required` skips the gesture. Everything is synthesized, with no audio files: a low projector motor chopped by a 24Hz shutter, a typewriter key every few characters, a carriage-return thud at the end of each line, a click on each hard cut, the leader's one-frame beep on 3, and a low thud when a stamp lands.

The voice lines that never change are recorded, since espeak is the one sound that would break the film. Record them as 16-bit WAV files in `voice/` next to `voice.py` on the Pi. A teammate reading flat, dry and unhurried into a phone is enough.

| File | Line |
|---|---|
| `voice/reveal.wav` | "Scan complete. Here's the take." |
| `voice/alert.wav` | "Alert." |

The changing half of the top-5 callout ("Sony WH-1000XM6. Top five. 500 dollars.") stays text-to-speech at 145 words per minute. If a clip is missing, text-to-speech reads the whole line. A music sting under the reveal, if you add one, should be a single upright bass or sax hit.

The OLED on the rig uses the same style: the case-file header, a blinking REC, the take in League Gothic, a dot-leader rule, FOOTAGE LOST, and a rotated CASE CLOSED stamp. See `oled-preview.png`; the code is `rig/display.py` in `BUILD-GUIDE.md`, and it also runs on a laptop to regenerate the preview. `display.py` loads `fonts/LeagueGothic-Regular.ttf` straight from this directory, so a repo checkout on the Pi needs no copy step.

## 12. Kiosk and venue setup

Launch the dashboard full screen with `chrome --kiosk http://<pi-address>:5000/`, or press F11. A tab bar on the projector breaks the film. On dashboard pages `noir.js` hides the mouse pointer after two seconds of stillness; moving the mouse brings it back.

Calibrate the projector with the test card in the Case Index. Projectors crush dark greys, so raise the black level until ink, carbon and the near-black steps are all distinct, then check the smallest text reads from the back of the table.

The layout holds from 1024x768 to 2560x1440 and scales up above 1440. Below 1024 wide, only the case file is designed to work. Fonts are local and nothing loads from the internet; the one network dependency is the rig, which has its own LINE DEAD state.

## 13. Accessibility

Every text color passes AA on its background, and the Case Index shows the ratios live. Ash never goes below 11px, and `--stamp` never appears on a dark screen.

The typed ledger is hidden from screen readers, since it arrives a character at a time. Instead `#log-sr` announces each exhibit once ("Exhibit 4: Silk smoking jacket, $420.00, estimated.") and `#reveal-sr` announces the verdict ("Case Closed. 5 suspects. Total take $7,600.00."). Cut-paper titles keep their text as an `aria-label`, and the odometer carries its value as one.

Reduced motion removes the texture layers, weave, reel start and cue mark, and completes every animation instantly; no content is withheld. Anything focusable gets a 2px bone outline. The dashboard has no on-screen controls, since the button is physical. The case file is plain text in reading order and prints cleanly.

## 14. Do and don't

| Do | Don't |
|---|---|
| Hairline rules, tracked capitals, dot leaders | Corners rounder than 3px |
| One stamp-red hit per region | Any other color, anywhere |
| Grain, flicker, weave and scratches at film levels | CRT scanlines (wrong decade) |
| League Gothic capitals, typed entries in Special Elite | Gradient text, glows, neon |
| Cuts, dissolves, freeze-frames | Slides, wipes, bouncing numbers |
| A real shadow under paper only | Shadows or glass on chrome |
| `est.` on guessed prices | Emoji, icons, stock illustration |

## 15. Decisions log

What we tried or considered, and why it isn't in the kit. When someone proposes one of these at 3am, point here.

| Rejected | Why |
|---|---|
| The build guide's gold-on-black surveillance readout | It reads as a dark-mode dashboard, which every hackathon has |
| CRT scanlines, terminal green, glitch effects | Wrong decade; this is film |
| Bebas Neue headlines | The 2010s default. League Gothic is the period face |
| Courier Prime for everything | Looks digital on paper. Special Elite for typed entries |
| A second accent color | One ink is what makes the stamp land |
| A brightness dip on top of the flicker | Stacked effects read as a lack of control |
| The sweep-hand countdown | The SMPTE leader is from 1965. The Academy leader is the period one |
| Smooth video feed | The rig sends stills. Hard cuts turn that into CCTV |
| Hiding LLM latency | A frozen screen looks broken; a typed EXAMINING line looks like work |
| Stamps over the QR | Breaks scanning |
| Opaque stamps over case-file rows | Hid item names on phones. Multiply, like ink |
| Decorative labels ("Room 3", a fake timer) | Fake detail reads as machine-made |
| The `№` glyph | Missing from Courier Prime. `NO.` instead |
| Borrowing the organizers' corkboard | Their site is static colored paper; ours is moving black-and-white film |
| Em dashes, arrows and bold-heavy prose in copy and docs | The best-known tells of machine-written text |

## 16. Packs

`packs/` collects everything a designer needs outside the browser. See `packs/README.md` for details.

- `packs/fonts/`: desktop TTF files for all four faces (install these for Figma), with licenses and a specimen sheet.
- `packs/assets/`: SVG parts (stamps, leader, marker, registration mark, film band, favicon), PNG sheets (palette, type, components), the grain tile, a 1920x1080 cover still and the OLED preview.
- `packs/animation/`: every animation as MP4 and GIF, plus `motion-spec.md` with exact values and bezier handles for After Effects or Figma.

## 16b. The premiere, the desk and the film

Three pieces built on the kit after the dashboard.

`premiere.html` (`/premiere`) is the one-sheet: the title card over a still of the set, then a reel the scroll wheel runs through the gate one frame at a time, three personnel files, the six-step procedure with its evidence board, the paperwork, and closing credits. `premiere.js` loads the whole film into memory before scrubbing, so every seek is local. With reduced motion the reel is a plain player.

Two small files sit on top of the title card, and both stand down when motion is paused or reduced, leaving the page above exactly as it is. `premiere-title-particles.js` sets the three words of the title in small cut stones: it samples the lettering out of the artwork, paints the wall back over it, and draws the letters again as a WebGL point cloud of faceted diamonds, each one placed wholly inside its letter so the strokes keep their edges. Each stone has a flat table and four facets that take the light in turn as it idles; one in six also throws a four-pointed flare now and then, and every few seconds a bar of light crosses the lettering and sets off the readiest of them. They gather on arrival, part around the pointer and scatter as the camera leaves. `premiere-portal.js` pins the title card and pushes the camera into the diamond from the first scroll; the film opens out of the diamond through a circular aperture and takes over at its first frame. Native scroll only, no wheel or touch handling. Where the title card is taller than the window (any laptop or desktop), the brief and the mission strip move to after the film so the artwork alone fills the screen; they are read there on the reel's black, and the crew's ground dissolves up out of it with no rule between. On a phone, where art and band fit one screen, they stay under the art.

The scenes after the film run on a small motion system, in four files. Nothing in it plays by itself: the scroll decides where everything stands, so scrolling back runs it backwards.

- `scroll-cinema.js` is the scene registry. Every `[data-cinematic-scene]` gets a `progress` (through its pinned length), an `enter` and an `exit`, from the one clock in `premiere-scroll.js`. A page draws a scene with `ScrollCinema.scene(name, draw)`; scenes far from the window are skipped (an IntersectionObserver marks them `data-active`). It holds animation state only and never touches the rig's data.
- `motion-presets.js` is the vocabulary. Markup names an entrance and, where it wants one, a way out: `<h2 data-motion="rise" data-motion-out="lift">`. Each is an Anime.js animation that is only ever sought, never played.

  | Preset | What it does |
  |---|---|
  | `rise` | Display type comes up from under its baseline behind a mask: a `.cut` title glyph by glyph, plain type line by line. Anything else rises 70px whole |
  | `slide-left`, `slide-right`, `signal` | In from the side: 60px, or 68px for `signal` |
  | `scan` | A typed label read off from its left end: a short slide with a wipe |
  | `focus` | Out of blur, settling back from 1.05 |
  | `relief` | Out of blur, coming forward from 0.94 |
  | `depth-in` | From 1.08, for large type |
  | `settle`, `dialogue` | 12px up into place: `settle` from 80% and slightly large, `dialogue` from nothing |
  | `mist` | A line of plain type, letter by letter out of blur. The words stay in the page for a screen reader |
  | `type` | The same letters struck on one at a time behind a block caret, with the kit's key sound if sound is on |
  | `lift` | Up 34px and gone. The usual exit |
  | `crossfade` | Opacity only |
  | `drift` | A layer that lags the scroll by `data-motion-depth` |

  An exit runs as the element's foot nears the top of the window, and the element is put back once it is above it. `data-motion-order` holds a neighbour back a step, `data-motion-start` and `data-motion-span` move where an entrance begins and how long it takes, and anything inside `[data-motion-rest]` stays put. Curves are `--ez-settle` and `--ez-film`. A phone moves 60% as far with no blur, nothing large is blurred, and nothing is scaled past the window's width.
- `webgl-scenes.js` changes the story's first photograph into its second with ink: it lands at the hat's lens and spreads across the print like a puddle, an uneven front with a wet red lip, and the second photograph is there where it has passed. The front follows the scroll, both ways. The canvas grades the photographs itself (a CSS filter would grey the ink). Without WebGL, or with motion off, the CSS crossfade shows instead.
- `cinematic-motion.css` holds the masks, stands down the older timers where the scroll now owns a property, and resets everything for print.

Two set pieces sit on that system, each in a file of its own and each standing down when motion is paused or reduced:

- `premiere-props.js`: the crew's red string is run from pin to pin as the files land; each file is stamped with the kit's slam once it is down; the files are swept aside as the next scene arrives; and the kit's changeover cue mark blinks twice, top right, before every change of scene. It also turns the rover, the wrist unit and the hat: after the crew, three pinned scenes each lay the photographs of one thing, one over another in a single print, as the scroll goes by (nine of the rover, seven of the wrist, five of the hat). The plates are square crops of the photographs in `film/rover/`, `film/wrist/` and `film/cap/`, cut by `film/build-turn-plates.py` so the thing stands the same in all of them. `film/wrist/` holds fourteen photographs and the script's `WRIST_TURN` says which seven are used. A scene sets its own length with `--turn` (and `--turn-small` for a narrow window) and its contact sheet's columns with `--sheet`; `turntable-pair` is a head and a print, and `turntable-flip` puts the print on the left. With motion off, or no script, the plates are a contact sheet. Any `section.turntable` with a `.plates` list, a `.turn-name` and a `.turn-count` is turned the same way. The wrist's head is where the page says what the wrist is for: it pairs with the hat's camera and the rover's, and shows the most valuable finds with a guessed name and an estimated price. A second print stands beside the turning one (`media/rover-field.webp`, the rover at a door): a photograph on its own that takes no part in the turn. Where three columns will not fit it sits under the first screen and comes up once the turn is done.
- `premiere-flock.js`: between the paperwork and the credits, as the room fades to black, 150 birds cross the screen on a canvas (70 on a phone) and half way over they draw the diamond. Where each bird is comes from the scroll, so scrolling back turns the flock round; its wingbeats are its own.

The film's captions use the same presets by the film's own time: each arrives (`dialogue`) and leaves (`lift`) over a fraction of a second of film, so they move with the wheel like the picture.

With motion paused or reduced none of it is built: no inline style, no mask, no canvas. A screen that does not scroll can still declare a preset: the desk's panels carry `data-motion="settle"` under `data-cinematic-trigger="load"`, which is one short CSS animation. Links between the premiere, the projector and the desk dissolve (`@view-transition`, opted into inline in each page's head because the browser reads it before a linked sheet arrives); `vault.js` skips the dissolve when motion is paused. A reload of the premiere plays the title sequence over the top of the page, not where it was left.

`desk.css` and `desk.js` (`/desk`) are the crew's console. The take and ledger come from `/state.json`, the posts from `/health`, the wrist from `/wrist.json?peek` (the peek keeps the desk from counting as the wrist). Every change goes through `Noir.authFetch`, so the token rule is the dashboard's.

`wrist-oled.js` copies `draw()` from `esp32/wrist.ino` pixel for pixel: the same 5x7 font, cursor positions and truncation.

`film/` is the film's source. A three.js office set (blinds, a banker's lamp, six exhibits) with this kit's markup laid over it: the leader, tracking markers, the typed ledger, the odometer, the dashboard, the lineup, the stamp, THE END. Every frame is a pure function of time. `cd film && npm install && node render.mjs film` renders 501 frames and encodes `media/film-1600.mp4` and `media/film-960.mp4` with a six-frame GOP for scrubbing; `node render.mjs stills` writes the hero, rover and mugshot stills. Serve `ui-kit/` and open `film/film.html` to look at the set.

`brand/` holds the crew's emblem slot. See `brand/README.md`.

## 17. Test before the event

- [x] Fonts vendored in `fonts/` and loaded by `noir.css` (verified with the network off)
- [x] `LeagueGothic-Regular.ttf` in `ui-kit/fonts/` — `display.py` loads it repo-relative, no copy needed
- [ ] `prefers-reduced-motion` checked: full content, no motion layers
- [ ] QR readable from a phone at two meters on the projector
- [ ] Reveal timing rehearsed against the real voice line
- [ ] Backup screen recording of all three screens (see the build guide risk table)
- [ ] `/frame.jpg` has no drawn boxes, and markers land on objects at the real webcam aspect ratio
- [ ] Crops look like booking photos (frame stored at 640px or wider)
- [ ] Every failure seen once on the real rig: unplug the webcam, cut the network mid-scan, reveal with 0 and with 3 items
- [ ] Title card appears after about 15 seconds idle and cuts away on the first scan
- [ ] `/manifest` opened on an iPhone and an Android phone: it scrolls and the QR is clear of stamps
- [ ] Printed case files from the final rehearsal, one per judge
- [ ] `voice/reveal.wav` and `voice/alert.wav` recorded and played through the cap speaker
- [ ] 60fps on the demo laptop on battery (DevTools, Rendering, Frame rendering stats)
- [ ] Projector calibrated with the test card at the venue
- [ ] Dashboard launched with `chrome --kiosk`: no cursor, no tab bar
- [ ] The reel start plays on boot, and THE END plays between runs

## 18. Presenting it at the table

Design prizes are judged on reasoning as much as results. Keep `board.html` open in a second tab: a typed memo to the judges with the premise, the rule and six findings, next to taped prints of each screen and the rejected first direction. Say the premise in one sentence, then let the walk and the reveal carry it. Put `shots/reveal.gif` first in the Devpost gallery.

The event's own branding is a detective corkboard: kraft paper, red string, polaroids. We're in the same world on purpose, but we don't borrow their corkboard. Ours is moving black-and-white film against their static colored paper, and that contrast is worth pointing out.
