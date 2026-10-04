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

## Session 4 (2026-10-04): crew photographs and stone headlines in the story scene

Request: replace the story scene's backgrounds with two photographs of the crew wearing the hat, sit the type flush with them, and give the headlines the hero title's diamond finish. Not committed.

| File | Change |
| --- | --- |
| `ui-kit/media/crew-hat-wrist.webp`, `crew-hat.webp` | The two supplied photographs (526x964 and 722x966), as supplied |
| `ui-kit/premiere.html` | Photographs sit in a `.statement-plate`; descriptive alt text; loads `premiere-diamond-type.js` |
| `ui-kit/premiere-scroll.css` | Desktop: a portrait plate flush to the marquee, the right edge and the bottom of the stage; headline sized so its longest line (3.97em) runs from the gutter to the plate; footer and rule end at the plate. Phone: the photograph fills the stage under the marquee and the type stands on its lower third. Photographs are graded to black and white |
| `ui-kit/premiere-diamond-type.js` | New. Sets both headlines in the same cut stones as the title (own copy of the shader, so the hero file is untouched): diamonds, with the accent word in rubies. Letters are read from the page's real type, which stays in the DOM and is only hidden while the stones are lit. Scroll-driven: the first headline's stones blow away as it leaves, the second's gather as it arrives. Off for reduced or paused motion and without WebGL |
| `rig/app.py` | One more static route, for the new script. A hub started earlier needs a restart |
| `tests/browser_premiere.cjs` | New group: photographs load, plate is flush, type ends at the plate, both headlines are in stones, axe passes with the stones lit. Reduced motion shows type, not stones. Asset fetches read their bodies. The last audit waits for the marquee's fade (it was flaky: audited mid-fade, the marquee button read as low contrast) |

Results: `npm run test:premiere` 13 of 13, four consecutive runs after the flake fix; `npm run test:ui` 13 of 13; UI contracts 4 and premiere/desk route contracts 8 pass. Screenshots inspected at 1440x900, 1600x736 at 1.25x, 390x844 at 1x and at 3x.

Limits: the photographs are small, so they are shown close to their native size on a plate, not stretched across the stage. Frame cadence measured 30Hz with and without the new script, on battery at 16%, so the stones' own cost could not be separated out here. At 1x pixel density on a phone-width window the stones are coarse.

## Session 5 (2026-10-04): no section is ruled off or ends on an edge

Request, with a screenshot of the story scene's hard bottom edge and the rule under its footer: a proper transition there, and never a section of the page marked out by lines.

`premiere.css` already said "no hairlines between sections: each seam is a gradient into the next section's ground, and each gets its own scroll-driven move". The story scene, added later, broke it: a solid block that ended on an edge, with a rule under its footer.

| File | Change |
| --- | --- |
| `ui-kit/premiere-scroll.css` | The scene's ground is a gradient that thins to nothing over its last 50svh. Plate, type and footer take `--story-enter` and `--story-exit`. The plate's top edge is feathered while the scene is arriving. The rule is gone. Scene is 300svh (240svh on a phone), up from 240 and 190, to give the exit room |
| `ui-kit/premiere.js` | Writes `--story-enter` (0 to 1 as the scene scrolls into place) and `--story-exit` (0 to 1 over progress .80 to .98). Beats retimed: first out .16-.36, photographs cross .26-.50, second in .38-.56, held to .80 |
| `ui-kit/premiere-diamond-type.js` | Each headline's stones gather as it arrives and blow away as it leaves, both ends of the scene |
| `ui-kit/premiere.html` | `.statement-rule` removed |
| `ui-kit/premiere.css` | Hairlines above and below the mission strip and the priors row removed |
| `tests/browser_premiere.cjs` | No rule exists; plate, type and footer are at zero before the scene lets go; a pixel check in the page margin at three positions past the scene's end finds no row-to-row brightness jump of 3/255 or more |

Results: `npm run test:premiere` 13 of 13, `npm run test:ui` 13 of 13, UI contracts and premiere/desk route contracts pass. Contact sheets of the entrance and exit inspected at 1600x736 and 390x844. A sweep of every section boundary through the screen found no remaining full-width edge in the page margins; the jumps it reported were content (the photograph, the hero artwork, a paper card) or the fixed wallpaper's own detail.

Still there on purpose: the marquee's bottom border, the film's chapter strip, and the separators between the method's steps. They are a top bar, a timeline control and list dividers, not section boundaries.

### Additional research closure

The reference's finale returns to the opening Roman street, then presents a large two-color closing headline, app download, replay control, and compact footer. The circular narrative reinforces a single continuous journey. Our ending retains the project's credits and live-dispatch links. Public code observations and browser frames support the mechanics described above; exact device frame-rate profiling of the reference was not performed.

### Execution ledger continuation

- Built the shared scroll coordinator and replaced independent portal/film smoothing.
- Generated the owned 501-frame sequence and added bounded rendering, loading fallback, and native static player.
- Added the two-scene room/evidence bridge and editorial arrivals; retained the vault, diamond, crew, method, and working product links.
- Corrected the existing portal opacity math and credits semantics; kept paper text fully opaque following the accessibility audit.
- Completed the focused browser checks, UI/route contracts, and motion unit tests; recorded the separate dashboard regression failure and environment timing limits.

## Session 6 (2026-10-04): a motion system for the scenes after the film

Branch `cinematic-scroll-dev`, cut from `origin/main` at `d2fbd22` (the merged `UI-dev`). Not committed. Three requests in one session:

1. Follow `cinematic_scroll_transition_upgrade_spec_flask_noirkit.md`.
2. A reload plays the title sequence but did not go back to the top of the page.
3. With the reference page's markup pasted in: take its transition types and use the same kind here.

The spec describes a scroll-as-timeline site in general terms. Most of its first half already existed here (one damped clock, a frame-scrubbed canvas film with a bounded cache, pinned scenes, reduced-motion fallbacks), so this session added what was missing and left the hero camera, the film and the title stones as they were.

### What was added

| Spec | Here |
| --- | --- |
| Central controller, scene registry, progress ranges (1, 26, 27) | `scroll-cinema.js`: every `[data-cinematic-scene]` gets `progress`, `enter`, `exit`; handlers register by name; `clamp`, `lerp`, `range`, `smooth` are shared |
| Anime.js as the animation library, driven by scroll (5 to 7) | `motion-presets.js`: each `[data-motion]` element is an Anime.js animation with `autoplay: false`, sought to the scroll position. Anime.js was vendored but not loaded on this page before |
| Presets and masked type (8 to 11, 44) | Section titles rise glyph by glyph behind a mask, labels are scanned in, ledes come into focus, the credits' columns close on the centre line |
| Scene overlap and crossfades (12, 13) | A scene leaving by the top sinks and dims while the next one arrives. The method's evidence board lays each print over the last by scroll position, not by a 650ms timer |
| Camera movement and parallax (14, 15) | The fixed wallpaper is pushed in 5% over the length of the page; the light and the dust in the hero move at their own depth during the camera move; the dossier stamps lag their files |
| WebGL morph with a fallback (20, 21) | `webgl-scenes.js`: the story's two photographs dissolve through a displaced blend with a little exposure at its middle; the CSS crossfade remains underneath |
| Offscreen work pauses (38, 39) | IntersectionObserver marks scenes `data-active`; inactive scenes are not drawn, and the morph draws only when its progress changes |
| Capability hints (40), mobile (32) | Below 720px: 60% of the travel, no blur, no drift, files are not turned. Four or fewer cores: no blur |
| Film into the live UI (42) | Links between `/premiere`, `/` and `/desk` dissolve (cross-document view transitions) in the kit's `--dur-fade` and `--ez-film` |
| Jinja integration (24, 25) | `desk.html` declares `data-cinematic-scene="desk"` and `data-motion="settle"` on its four panels: a staggered settle on load, in CSS, with no script of its own |

### The reference's transition types

Read from the pasted markup's `data-text-motion` and `data-block-motion` attributes and the inline styles beside them. Only the motion was taken: no colour, type, layout or code.

| Seen there | Here |
| --- | --- |
| Lines `rise` from 135% behind a mask | Already here as `rise` |
| `slide-left`, `slide-right`, `focus` | Already here |
| `scan`: a short slide for data-like lines | New `scan`, with a wipe; used on the four typed labels |
| `signal`, `relief`, `dialogue` block motions | New presets. `relief` is on the credits' links; `dialogue` on the mission copy and the film's captions |
| "Mist" intertitles, one blurred letter at a time | New `mist`; used on the credits' two small lines. The words stay in the page (`.sr-only`) and the letters are `aria-hidden` |
| Every block also leaves (`lift`: up 34px and gone) | New `data-motion-out`. Section heads and the mission band lift away as they reach the marquee, and are put back once above the window |
| Copy that changes over a pinned, scrubbed film | The film's captions arrive and leave by film time (0.45s in, 0.35s out) instead of cutting |
| Exposure layers between scenes | A 16% lift in exposure at the middle of the photograph dissolve |

### Reload

`premiere.html`'s head script: when the title sequence is going to play and the navigation is a reload, scroll restoration is switched to manual for that load, a `#section` is dropped from the address, and the page is put at the top. A link to a section and going back to the page are unchanged.

### Files

| File | Change |
| --- | --- |
| `ui-kit/scroll-cinema.js`, `motion-presets.js`, `webgl-scenes.js`, `cinematic-motion.css` | New |
| `ui-kit/premiere.html` | 8 scenes, 37 `data-motion` and 12 `data-motion-out` attributes; loads Anime.js and the three scripts; inline view-transition opt-in; reload-to-top |
| `ui-kit/premiere.js` | The story, the arrivals, the board and the exits are scene handlers; captions move by film time. The one-shot `on-cue` IntersectionObserver is gone. If `scroll-cinema.js` is missing (an old hub) the story and the arrivals still run from the clock |
| `ui-kit/premiere.css`, `premiere-scroll.css`, `premiere-portal.css` | Removed `on-cue`, `fade-to-black`, `credits-up` and `mission-rise`: the scroll clock owns those now, in every browser, not only where `animation-timeline` exists. Files and prints take an `--arrival-turn`. Morph canvas, caption line and hero depth rules |
| `ui-kit/premiere-portal.js` | Writes `--camera` on the hero scene |
| `ui-kit/vault.css`, `vault.js` | Dissolve timing; `pageswap` skips the dissolve when motion is paused |
| `rig/templates/desk.html`, `dashboard.html` | Desk: the stylesheet, scene and preset attributes, opt-in. Dashboard: the one-line opt-in only |
| `rig/app.py` | Four static routes. A hub started before this needs a restart |
| `tests/browser_premiere.cjs`, `browser_ui.cjs`, `test_ui_contract.py` | Five new premiere groups and one new dashboard group; the reduced-motion, viewport and title-sequence groups extended |

Nothing in NOIRKIT changed: no token, colour, font or component was added or edited, and the page's copy is untouched.

### Decisions worth knowing

- `data-motion` is also an attribute on `<html>` (`full` or `reduce`, set by `vault.js`). The presets only look inside `<body>`, and no preset is named `full` or `reduce`. Do not write a bare `[data-motion]` CSS selector.
- Display type is revealed by mask and movement, not by fading. Paper text on the dossiers stays opaque, as the earlier audit required.
- An exiting scene dims only once it is in the top half of the window and is restored when it has left it; an exiting head is restored once it is above the window. Nothing off-screen is left hidden or at low contrast.
- The dissolve's opt-in has to be inline in each page's `<head>`. Chrome resolves it as `<body>` opens; in a linked stylesheet it was missed on `/` and `/desk`, and only worked on `/premiere` by the accident of a blocking script in its head.
- Not built, on purpose. `state-manager.js`: `noir.js` and `desk.js` already own polling and were left alone. `canvas-scenes.js`: `premiere-sequence.js` is that file. Smooth-scroll libraries: native scroll stays. Blur on large elements: THE END only scales and fades, and the mission copy is not blurred because it arrives while the film's iris is closing.

### Results

- `npm run test:premiere`: 18 of 18. New: scenes register and a head arrives, leaves and is put back, forward and in reverse; a caption arrives and leaves by film time; the board lays prints by scroll and a scene overlaps the next; the photographs dissolve through WebGL and through CSS without it; pausing clears every inline style, the marquee links still work, and axe passes at a settled method scene and at the foot of the page. Reduced motion builds zero motion elements, masks and letters. A reload lands at the top with the sequence playing, with and without a `#section`; a link to a section still lands on it.
- `UI_TEST_PORT=5165 npm run test:ui`: 14 of 14. New: the desk's four panels settle and leave nothing behind, `/state.json` is still polled and a new find still appears, the premiere-to-desk link dissolves, and with motion paused it cuts. One run failed in the unrelated manifest group with an operating-system error writing `test-artifacts/axe-manifest-5.json`; the next run passed.
- `node --test tests/test_motion.cjs`: 13 pass. `.venv/Scripts/python.exe -X utf8 -m unittest discover -s tests`: 310 tests, 1 error, 1 skipped; the error is the same Windows symlink-privilege test as before.
- The suite caught two real faults during the work. A full-width strip scaled by `settle` made the page wider than the window; presets now refuse to scale anything that would. Exited scenes were left dimmed, which axe reports as low contrast; they are now restored once out of the window.
- Whole-page scroll sweep in headless Chrome (36px a frame, down and back, 855 frames), against `origin/main` served from a scratch copy. Median frame gap 16.7ms on both. Frames over 34ms varied a lot from run to run: 5 to 21 on main, 8 to 31 here, in the same places on both (the film's frame decoding, the stones where the story ends, the volley at the credits). Two hotspots that were this branch's own were found and removed: blur on THE END, and blur on the mission copy. Headless Chrome renders in software, where blur costs far more than on a GPU; this compares the two versions and does not certify the judging laptop.
- Screenshots inspected at 1440x900 and 390x844: each section head mid-entrance, at rest and on its way out, the dissolve at its start, middle and end, the board mid-dissolve, the mission band, the priors, the credits and their letters, the foot of the page, and a scene exit.

### Still open

1. Not committed or pushed. To commit: the four new files, the files in the table above, and this log.
2. Not seen on a real GPU or in Safari or Firefox. The view-transition dissolve is Chromium and Safari 18.2 or later; elsewhere links cut as before. The in-app browser pane was hidden during this session (the page's clock sleeps while hidden), so every visual check was made in headless Chrome.
3. The film's iris-out into the next scene is still a CSS `animation-timeline` effect and does not run in Firefox.
4. Rehearse on the judging laptop, as before: wheel, trackpad, fast reverse, tab away and back. If the credits or a section head stutter there, the first things to try are `mist` to `dialogue` on the two credit lines and `focus` to `dialogue` on the ledes: both remove blur.
