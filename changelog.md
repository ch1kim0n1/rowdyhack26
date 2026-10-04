# UI-dev: cinematic scroll design and implementation log

Last updated: 2026-10-04. This is the design guide, execution ledger, and handoff for the Fly Crooked inspired premiere. Update this file at each completed milestone. Never label an untested requirement as complete.

## Branch and boundaries

- Requested branch: `UI-dev`, created directly from local `main` at `1c06d53` (`v2`). Original checkout was `hat-cam-dev`. Fast-forwarded on 2026-10-04 to `origin/main` at `c73b39b` (the merged `.gitignore` / `.env.example` PR); no other history change.
- Primary experience: `/premiere`, implemented in `ui-kit/premiere.html`. `/` is a live operational dashboard; keep its data, routes, controls, and backend behavior intact.
- Existing uncommitted hardware changes were carried across the switch: `rig/oled-live.png`, two case stills, and `rig/state/case.json`. They belong to the user. Do not revert or stage them.
- The branch now carries main's `.gitignore`, so `.env`, `.venv`, caches, `rig/state/` and `test-artifacts/` are ignored. Files that were already tracked there (`rig/state/case.json`, two stills, `rig/oled-live.png`, and the dashboard suite's outputs under `test-artifacts/`, which every `npm run test:ui` rewrites) still show as modified; they are not part of this work. Still stage only this work's explicit paths if a commit is requested, and never read or publish credentials.
- No reference artwork, branding, code, or videos are copied into the product. Reuse the project's own film, artwork, fonts, and stills.

## Research: https://flycrooked.com/

Inspected on 2026-10-04 in a live browser, with desktop and compact viewport observations, plus its publicly served HTML and page JavaScript. The web search reader could not open the homepage; the browser and public HTTP download worked. Research downloads are local, untracked files under `test-artifacts/scroll-research/`, not product dependencies.

### Observed visual language

1. The opening is a full-viewport illustrated Roman street, near-monochrome with pink lighting. A quiet fixed brand/CTA floats over the scene; typography is large, condensed, and sparse.
2. Scrolling holds the scene on screen while changing the camera and replacing short text beats. The opening moves from street level toward the skyline. Story beats carry through aircraft interiors, Rome, a museum, and an interior doorway.
3. Images fill the stage. Text is layered independently, with breathing room between beats. Crossfades bridge scenes so there is no succession of ordinary rectangular sections in the main story.
4. Scroll controls time, including reverse movement. A cinematic moment gets multiple viewport heights rather than disappearing after one wheel gesture.
5. At a desktop override of 1440 x 900 the document reported roughly 52,335 CSS pixels tall. We should borrow the choreography, not reproduce that much scrolling for a hackathon pitch.
6. Screenshots establish composition, not frame-rate performance. Do not claim a measured 60/120 fps for the reference from these observations.

### Verified mechanics in the public page bundle

Source at inspection: `https://flycrooked.com/_next/static/chunks/app/page-05260b741ad00451.js` (hashed URLs can change).

- Custom requestAnimationFrame clock approaches native `window.scrollY` with a per-frame factor of 0.085; a secondary velocity value approaches its target at 0.12. No Lenis/GSAP attribution is justified by this inspected bundle.
- Scroll distance maps through scene-specific screen counts and timeline intervals, rather than one uniform video progression for the whole page.
- Main scene component loads numbered WebP frames, limits concurrent image requests to six, and prioritizes first/last frames plus recursively bisected ranges. On a cache miss it finds the closest loaded frame in either direction.
- Canvases redraw only when the chosen frame changes; invisible scenes skip drawing. Opacity ramps overlap outgoing and incoming scenes.
- Orientation-specific scenes and portrait framing are present. Deferred sequences begin loading before their visible interval.
- The hero includes looping videos and a separate canvas dissolve treatment; it is not all a single video scrub. Main scenes include 195-frame and 241-frame sequences.
- Some visual canvas work caps device pixel ratio at 1.5. Hero video sources include reduced-motion media conditions. This is evidence of specific accommodations, not proof the entire site passes an accessibility audit.

### Smoothness lessons

Per-frame interpolation changes feel with refresh rate. Our damping uses `1 - exp(-dt / tau)` so the response is consistent at 60 and 120 Hz. Scroll input stays native: no wheel/touch interception, no forced snapping. A shared, demand-driven clock coordinates the portal, film, and editorial motion; it sleeps when settled or hidden. Cache layout on resize/content changes. Keep transforms/opacity on separate layers and avoid per-frame blur, large shadow changes, and layout writes.

Canvas sequences remove asynchronous video-seek contention, but decoded images cost memory. Use a bounded decoded-frame cache and limited request concurrency; retain the video as a failure/reduced-motion fallback. A smooth camera cannot invent intermediate detail beyond the source film's 24 fps.

## Art direction: enter the case

Preserve warm ivory type, charcoal shadows, crimson accents, the diamond, and the existing noir photography. The signature is a single journey from the vault into the evidence. Avoid adding unrelated neon, generic glass cards, or reference-site branding.

| Beat | Composition and motion | Reading goal |
| --- | --- | --- |
| Arrival | Existing vault artwork, restrained chrome, a visible scroll invitation | Know this is The Appraisal Job |
| Threshold | Pinned hero camera moves into the diamond; circular aperture opens the film | Feel physically drawn into the operation |
| Operation | Large cinematic film stage, frame-accurate reversible scrubbing, chapter rail, deliberate text | Observe, appraise, file, debrief |
| Crew | A short editorial statement bridges film and files; dossiers enter with controlled stagger | Understand three devices share one ledger |
| Method | Existing sticky evidence board remains; active step and image transition cleanly | Understand the real pipeline |
| Paperwork / close | Prints settle into place, restrained depth, credits and clear dispatch CTA | Continue into the working product |

On portrait phones: smaller depth, no horizontal travel, stable viewport heights, legible text, shorter pinned sequence. On reduced or paused motion: normal document flow, readable static scenes, standard film controls, no decorative motion.

## Implementation plan and acceptance gates

### 1. Baseline and research — complete

- [x] Inspect repository, identify premiere and existing portal/film behavior.
- [x] Create `UI-dev` from `main`, preserve unrelated changes.
- [x] Observe reference and inspect public implementation.
- [x] Write this guide before editing product files.

### 2. Motion foundation — complete

- [x] Add a small shared scroll coordinator (`premiere-scroll.js`), loaded before portal/film scripts.
- [x] Use time-based damping, cached geometry, passive input, idle/hidden suspension, and resize/font/image invalidation.
- [x] Move portal and film onto the coordinator, removing perpetual layout polling and double smoothing.
- [x] Honor live system/preference changes, restore native fallback, and retain keyboard/deep links.

### 3. Film rendering

- [x] Generate an optimized WebP sequence from our existing owned 960px film using a reproducible script; record dimensions/count/size.
- [x] Add canvas renderer with bounded image cache, six-request concurrency, nearest-ready-frame fallback, and loading failure fallback to video.
- [x] Keep native video controls for paused/reduced motion; no unnecessary sequence downloads in that mode.
- [x] Test fast forward/backward scroll, loading failure, and chapter navigation.

### 4. Choreography and finish

- [x] Add a scroll invitation, concise editorial bridge, section progress, and staged dossier/print movement.
- [x] Keep all effects reversible where tied to scrolling. Avoid overlapping CSS and JS ownership of the same transform.
- [x] Scope changes to premiere assets; retain original content and working product links.
- [x] Inspect desktop, portrait phone, and short laptop layouts visually.

### 5. Validation and handoff

- [x] Syntax checks plus focused browser acceptance for film progression, reverse, resize, navigation, no overflow, motion toggles, reduced motion, and errors.
- [x] Accessibility audit for the changed page, with meaningful fixes to new issues.
- [x] Collect timing evidence and screenshots on the local environment; distinguish scripted checks from actual device smoothness.
- [x] Run existing appropriate UI regression checks (full dashboard suite has an outstanding scout-status assertion; see results below).
- [x] Update this log with exact changed files, commands, outcomes, known limitations, and the next action.

## Starting architecture and known issues

- `premiere-portal.js` already has native scroll, a 65ms damped camera, responsive band relocation, and an iris into the film. Preserve those details while sharing the clock.
- `premiere.js` runs an unconditional rAF, reads several element bounds on every frame, uses refresh-dependent 0.22 video interpolation, and snapshots reduced motion once. These need correction.
- The current film is 501 frames at 24 fps (~20.875 seconds), with 960px/1600px MP4 and WebM alternatives. Video seeking can skip target frames while a previous seek is in flight.
- `premiere.css` already has CSS view-timeline effects. Do not pile a second transform system over those same elements without explicitly disabling the old ownership.
- `vault.js` owns `appraisal-motion` storage and emits `vaultmotionchange`; use it as the source of preference truth.
- Existing title particles are WebGL decoration and already observe portal events. Leave their content intact, then verify whether they dominate GPU cost.
- Flask serves the premiere and kit assets. `tests/ui_server.py` offers isolated offline fixtures without touching real hardware state.

## Resume instructions

1. Read this file, then `git status --short` and `git diff -- ui-kit tests changelog.md`.
2. Confirm current branch is `UI-dev`. Do not reset any unrelated rig files.
3. Continue from the first unchecked milestone. Read the actual files before assuming a checkbox captures every in-progress edit.
4. Use the isolated UI server or a local static preview of `ui-kit`; do not start hardware scanning for UI work.
5. Record all tests honestly, including failures and environmental limitations. Leave a concrete next step if interrupted.

## Execution ledger

- 2026-10-04: Created requested branch; researched reference browser experience and public sequence renderer; documented design, boundaries, implementation order, and test gates. Product implementation has not started at this checkpoint.


## Implemented file map

| File | Responsibility |
| --- | --- |
| `ui-kit/premiere-scroll.js` | Shared native-scroll clock, 85ms exponential damping, cached measurements, idle/visibility suspension |
| `ui-kit/premiere-sequence.js` | Canvas sequence, six concurrent requests, coarse anchors, nearby preload, nearest-ready fallback, eight-second request timeout |
| `ui-kit/premiere-scroll.css` | Premiere-only cinematic composition, story crossfade, editorial arrivals, readable mobile and static modes |
| `ui-kit/premiere-portal.js` | Existing diamond camera now follows shared clock; opacity normalization fixed; reading restoration deferred until motion layout changes finish |
| `ui-kit/premiere.js` | Cached section geometry, sequence integration, complete captions, live reduced-motion handling, video fallback, story timing |
| `ui-kit/premiere.html` | Scroll invitation, canvas, two-beat story, valid chapter list, accessible credits heading, no-JS fallback |
| `ui-kit/film/build-scroll-frames.py` | Reproducible ffmpeg extraction from the owned 960px film |
| `ui-kit/media/scroll-frames/` | 501 generated WebP frames and manifest; 960 x 540, 24 fps, 11,399,952 bytes total |
| `rig/app.py` | Three explicit static routes for the new JS/CSS files; no application logic changed |
| `tests/browser_premiere.cjs` | Ten focused browser acceptance groups plus frame-cadence diagnostics |
| `tests/ui_server.py` | Disables dotenv ingestion before fixture import so the real configuration cannot override fixture state/camera settings |
| `package.json` | `npm run test:premiere` command |

## Final choreography and tuning values

- Native scroll stays authoritative. The animation clock uses tau=85ms, settles below 0.15px, and snaps large jumps over 1.5 viewport heights. There is no scroll hijacking.
- The existing diamond portal remains 200svh of additional hero travel. Its `range` helper previously clamped every denominator to at least 1, including normalized 0..1 intervals; this kept film chrome at 0.242 opacity. The denominator floor is now 0.0001, allowing full opacity.
- Film: 600svh desktop / 430svh mobile, with the original 501-frame narrative and chapter links. Video is loaded only for static mode or a failed image sequence.
- Story bridge: 240svh desktop / 190svh mobile; sticky full-screen imagery scales from 1.03 to 1.12. Crossfade spans progress .35-.65; the first headline exits over .22-.47, and the second enters over .50-.72. Reverse scrolling reverses these transitions.
- Dossiers and paperwork arrive from up to 90px below, using a cubic ease-out and a 32px stagger. Text remains opaque for contrast; only pictures fade. These elements no longer use competing legacy CSS timeline animations.
- Application-held decoded frames are capped at 56 on desktop (~111 MiB RGBA pixels), 32 when initialized at <=720px (~63 MiB); plus up to six in-flight requests and browser/GPU overhead. Browser-internal caches are outside this cap. The budget follows the viewport live: narrowing past 720px evicts down to 32 at once, with no reload.
- No-JS exposes both story beats. Paused/system-reduced motion collapses pinned travel, displays both story beats, and uses native video controls. Changes to the preference are handled without reload.
- The independent, pre-existing title-particle renderer remains; it sleeps offscreen and respects reduced motion. The shared clock claim covers the scroll choreography, not every decorative animation in the project.

## Validation results and reproducible commands

Run from the project root. Python commands use the existing Windows venv; use the equivalent Python path elsewhere.

```powershell
npm run test:premiere
$env:PYTHON_DOTENV_DISABLED='1'
.venv/Scripts/python.exe -X utf8 -m unittest discover -s tests -p test_ui_contract.py -q
$env:PYTHONPATH='tests'
.venv/Scripts/python.exe -X utf8 -m unittest test_contract.PremiereAndDesk -q
node --test tests/test_motion.cjs
# Use a free port: 5127 was already serving a different process in this workspace.
$env:UI_TEST_PORT='5164'
npm run test:ui
```

- Focused premiere browser suite: 10 groups passed, no page JavaScript errors. Covers served assets/frame count, exact forward/reverse frames, cache/concurrency caps, idle clock, chapter navigation, story reversibility, pause/resume, four viewport sizes, system reduced motion with zero sequence requests, failed sequence video fallback, no-JS reading, and axe checks.
- Serious/critical axe findings: zero in animated desktop film and reduced-motion mobile. This is automated coverage, not a claim of complete WCAG certification.
- Viewport checks: 1440x900, 1366x768, 390x844, 360x640; no horizontal overflow and the film gate stays within the viewport. Desktop and mobile screenshots inspected.
- Python UI contracts: 4 passed with dotenv disabled. The initial unisolated invocation failed the rover timeout check because the local camera configuration counts a URL camera as an online rover.
- Premiere/desk route contracts: 8 passed with UTF-8 mode and dotenv disabled. The initial Windows invocation encountered an unrelated cp1252 decoding error while reading existing internal notes; `-X utf8` resolved it.
- Motion unit tests: 13 passed.
- Full existing dashboard browser suite: first six groups pass, then `Camera loss and scout timeout have separate reasons` expects `SCOUT OFFLINE` but sees `SCOUT ONLINE`. Repeated with a separate port and dotenv disabled. Dashboard runtime and rover status logic were not changed by this work; do not claim the entire regression suite passes. This is the remaining regression investigation, separate from the premiere's ten passing groups.
- One diagnostic run recorded 120 rAF intervals: median 33.3ms, p95 33.5ms, zero intervals over 34ms. This environment delivered ~30Hz; it does **not** establish 60/120fps performance on the judging laptop. The source film is 24fps. Rehearse on the actual laptop/projector before judging.
- Syntax checks pass for all changed/new JavaScript. `git diff --check` passes.

Artifacts: `test-artifacts/premiere-scroll/results.json`, `axe-film-desktop.json`, `axe-reduced-mobile.json`, `film-desktop.png`, `film-mobile.png`, and `story-desktop.png`. Research downloads and browser artifacts are local evidence, not runtime assets.

## Remaining practical limits / next session

1. The implementation is complete locally on `UI-dev`; it has not been committed, pushed, or deployed. Preserve the user's original rig changes. If committing later, explicitly stage the file map and generated `scroll-frames` directory; never stage `.env`, `.venv`, or unrelated output.
2. Investigate the existing dashboard scout-status browser assertion if broader regression certification is needed. It is not a failing premiere check.
3. Rehearse at the actual judging display refresh rate. Check wheel, trackpad, touch, fast reverse, tab-away/resume, and projection; Safari and Firefox were not tested in this Windows session.
4. Full-download media size is ~11.4MB, though the sequence is demand-loaded. For a larger production rollout, consider a CDN and a separately rendered 48/60fps film. Current film detail remains limited to the owned 24fps source.
5. Preview the experience at `/premiere`, not `/`. The isolated local fixture was started at `http://127.0.0.1:5128/premiere#top`; if it is no longer running, launch `tests/ui_server.py` with a free `UI_TEST_PORT`. Operational links in this preview point to fixture screens.

## Session 2 (2026-10-04): finishing the interrupted checks

The first session stopped mid-way through its last verification run. Its "Validation results" and "Remaining practical limits" sections above describe the state before this session; where they disagree with this section, this section is current.

### What was actually unfinished

- The final `npm run test:premiere` run had not completed: `results.json` predated the 32-frame phone budget. Re-run, it **failed** at the viewport group (`56 !== 32`). Cause: the test called `page.goto()` with the URL the page was already on, which only moves to the `#fragment`, so no viewport was ever a fresh load and the budget fixed at the first 1440px load stayed in force.
- The mobile story layout had not been looked at.
- The dashboard suite's `SCOUT ONLINE` failure was open.

### Changes

| File | Change |
| --- | --- |
| `ui-kit/premiere-sequence.js` | Frame budget and preload radius are read from a live media query instead of once at start; a change evicts immediately |
| `ui-kit/premiere-scroll.css` | Story shade keeps the bottom band near-solid so the footer no longer sits on the ledger image's own numerals; phone footer's second label is right-aligned |
| `ui-kit/premiere.html` | Non-breaking space before the two `↓` arrows so they cannot wrap alone |
| `tests/browser_premiere.cjs` | Each viewport is a real load; budget asserted at every size; new group for narrowing without a reload; waits for the loading card to finish fading; saves `hero-mobile.png`, `story-mobile-first.png`, `story-mobile-second.png` |
| `tests/ui_server.py` | `app.run(..., load_dotenv=False)` |
| `tests/test_certification.py`, `test_contract.py`, `test_mastermind.py`, `test_narration.py`, `test_radio.py`, `test_report.py` | `PYTHON_DOTENV_DISABLED=1` set before `rig.app` is imported |

### Root cause of the scout-status failure

Not a dashboard regression. Flask's `app.run()` loads `.env` on its own, through `dotenv_values`, which `PYTHON_DOTENV_DISABLED` does not cover. With a real `.env` whose `CAM_SOURCE` is a URL, the "isolated" fixture saw a URL camera, and `rover_ok` is true for any URL feed while the camera is up, so the page said `SCOUT ONLINE`. The same load put the real Vultr key and Tiger URL into the fixture's environment. `load_dotenv=False` closes it.

The Python unit modules had the same hole by a different route: `rig.app` calls `load_dotenv(override=True)` at import, which undid each module's own `os.environ.pop(...)` setup, restored the keys, and reset `RIG_STATE_FILE` to the live case file. Each module that imports `rig.app` now disables dotenv first. No hand-set environment variable is needed any more.

### Results (real `.env` present, nothing set by hand)

- `npm run test:premiere`: 11 groups pass, no page errors.
- `UI_TEST_PORT=5164 npm run test:ui`: 13 of 13 pass. A free port is still required because 5127 is the live hub.
- `.venv/Scripts/python.exe -X utf8 -m unittest discover -s tests`: 310 tests, 1 error, 1 skipped. The error is `test_ids_and_paths_cannot_escape_the_reports_root`, which needs the Windows symlink privilege; it is unrelated to this work.
- `node --test tests/test_motion.cjs`: 13 pass.
- Syntax checks and `git diff --check` pass.
- Frame-cadence diagnostic this session: 120 samples, median 8.3ms, p95 8.5ms, none over 34ms (about 120Hz in headless Chrome on this laptop). The first session measured 33.3ms. Both are diagnostics of one environment; neither certifies the judging display.
- Screenshots inspected: hero, film and both story beats at 390x844; film and story at 1440x900. Story footer is legible over the ledger image at both sizes.
- Live check in the app's browser on the real hub at `http://localhost:5127/premiere`: canvas ready, shown frame equals target frame, loading card gone, clock idle at rest, no console errors.

### Environment changes this session

- The leftover fixture on `127.0.0.1:5128` was stopped. It had been started before the isolation fix and had the real configuration loaded. Port 5128 on the LAN address is a different process (the Pi drop server) and was left alone.
- The live hub on 5127 was restarted so it picks up the three new static routes in `rig/app.py`; before that, `/premiere` on the hub returned 404 for `premiere-scroll.js`, `premiere-scroll.css` and `premiere-sequence.js`. Any hub started before this branch's `rig/app.py` needs the same restart.

### Still open

1. Nothing is committed or pushed. To commit: the file maps above, `ui-kit/media/scroll-frames/` (502 files, about 11.4MB), `ui-kit/film/build-scroll-frames.py`, `changelog.md`.
2. Rehearse on the judging laptop and projector: wheel, trackpad, touch, fast reverse, tab-away and return.
3. Safari and Firefox are untested.
4. Preview at `http://localhost:5127/premiere` (live hub), or run `tests/ui_server.py` with a free `UI_TEST_PORT` for fixture data.

## Session 3 (2026-10-04): the title sequence plays on every load

Request: the gun-barrel title sequence should run before the site appears, every time the page loads.

It already existed (`ui-kit/intro.js`) but almost never ran: once per browser session only, and never for a URL with a `#fragment`, which is how every preview link in this file was written.

| File | Change |
| --- | --- |
| `ui-kit/premiere.html` | Head script: the sequence is on for every load, deep links included. Reduced or paused motion still skips it. `?intro` plays it even then; `?intro=off` never does. A blocked `localStorage` no longer cancels it |
| `ui-kit/intro.js` | No more once-per-session flag. New beat after the lock-on: the emblem fires (white flash, glass kicks), red runs down the glass from the top, and the barrel sways and sinks before the emblem goes home. Runs 4.8s plus the fade, up from 4.15s |
| `tests/browser_premiere.cjs` | Functional groups load with `?intro=off`; new group: plays on a first load, a repeat load and a deep link, ends on its own, skips on a key press, stays off for `?intro=off` and for reduced motion; saves `intro-run.png` |
| `tests/browser_ui.cjs` | The one premiere visit uses `?intro=off` |

The sequence is drawn from scratch on a canvas with the project's own emblem and colours. No film footage, logo or music is used, and it stays silent.

Results: `npm run test:premiere` 12 of 12; `UI_TEST_PORT=5164 npm run test:ui` 13 of 13; UI contracts 4 and premiere/desk route contracts 8 pass. Frames stepped to fixed times were inspected at 1440x900 and 390x844 (dots, barrel, lock-on, flash, red front part-way and full, return to the marquee). Live on the hub at `http://localhost:5127/premiere#top`: plays on load, overlay removed afterwards, no console errors.

Scope: `/premiere` only. The dashboard at `/` keeps its own cold open. Add `ui-kit/intro.js` and `tests/browser_ui.cjs` to the commit list in Session 2.

### Additional research closure

The reference's finale returns to the opening Roman street, then presents a large two-color closing headline, app download, replay control, and compact footer. The circular narrative reinforces a single continuous journey. Our ending retains the project's credits and live-dispatch links. Public code observations and browser frames support the mechanics described above; exact device frame-rate profiling of the reference was not performed.

### Execution ledger continuation

- Built the shared scroll coordinator and replaced independent portal/film smoothing.
- Generated the owned 501-frame sequence and added bounded rendering, loading fallback, and native static player.
- Added the two-scene room/evidence bridge and editorial arrivals; retained the vault, diamond, crew, method, and working product links.
- Corrected the existing portal opacity math and credits semantics; kept paper text fully opaque following the accessibility audit.
- Completed the focused browser checks, UI/route contracts, and motion unit tests; recorded the separate dashboard regression failure and environment timing limits.
