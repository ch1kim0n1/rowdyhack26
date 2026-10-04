# NOIRKIT packs

Everything a designer needs outside the browser. The browser kit (`noir.css`, `noir.js`, `kit.html`) stays the source of truth; these packs are rendered from it.

## fonts/

Desktop TTF files. Install all five before opening any design file, or Figma will substitute fonts and every layout will be wrong.

| File | Family | Use |
|---|---|---|
| `LeagueGothic-Regular.ttf` | League Gothic | Headlines, the take, names. Always capitals |
| `SpecialElite-Regular.ttf` | Special Elite | Typed entries: the ledger, the case file. Never bold |
| `CourierPrime-Regular.ttf`, `CourierPrime-Bold.ttf` | Courier Prime | Printed labels and meta. Labels are bold, tracked .20em |
| `Caveat-Medium.ttf` | Caveat | One pencil note per screen |

On macOS, double-click each file and choose Install. On Windows, right-click and choose Install for all users. Restart Figma afterwards. License texts are in `fonts/licenses/`: League Gothic, Courier Prime and Caveat are SIL Open Font License 1.1, Special Elite is Apache 2.0. All five can be used, bundled and shipped freely.

For design tokens (colors, sizes, spacing, easing, durations), import `../tokens.json` with the Tokens Studio plugin in Figma.

## assets/

`svg/` holds vector parts: the favicon, registration mark, Academy leader frame, cue mark, sprocket strip, marker frame, the title card's five torn bars at 1440x900, and four stamps. The stamps keep their live text in League Gothic and a roughening filter; Figma ignores the filter, so use the PNG when you need the worn edge.

`png/` holds everything rendered by the real stylesheet at 2x, on transparent backgrounds where it makes sense:

| Files | What they are |
|---|---|
| `stamp-*.png` | CASE CLOSED, CASE UNSOLVED, APPROVED, REJECTED in the screen ink; EVIDENCE and FILED in the paper ink |
| `marker.png`, `marker-top5.png` | An evidence marker, and its top-five pulse frame |
| `placard.png` | A booking-photo slot with its placard |
| `leader-8.png` to `leader-3.png`, `leader-six.png` | Every frame of the Academy leader |
| `picture-start.png`, `cue-mark.png`, `the-end-title.png`, `title-lettering.png` | Projection pieces and cut-paper titles |
| `film-band-top.png`, `film-band-bottom.png` | The feed's film strip, with edge print |
| `grain-tile.png` | The 160px grain tile at full strength; use it at 5% opacity with an overlay blend |
| `sheet-palette.png`, `sheet-type.png`, `sheet-components.png`, `sheet-states.png` | Reference sheets taken from the Case Index |
| `cover-title-1920x1080.png`, `cover-title-1500x1000.png`, `cover-live-1920x1080.png`, `cover-reveal-1920x1080.png` | Stills for Devpost, slides and social |
| `oled-preview.png` | The rig's 128x64 screen in every state |

## animation/

Every animation as an MP4 (H.264, plays anywhere) and a GIF (12fps, for Devpost and chat). `motion-spec.md` lists each one with exact keyframes, durations and bezier handles, so it can be rebuilt in After Effects or Figma.

| Clip | Length | What it shows |
|---|---|---|
| `reel-start` | 5.2s | PICTURE START and the Academy leader counting in the picture |
| `title-card` | 12.5s | One full cycle of the Saul Bass title card |
| `scan-beat` | 3.6s | One exhibit: examining, typed, marked, counted |
| `reveal` | 7.4s | Cue mark, freeze, dissolve, the lineup filling, the total, CASE CLOSED |
| `the-end` | 3.5s | The card that closes a run |
| `footage-lost`, `line-dead` | 4.2s each | The two slates with the leader looping |
| `stamp-slam` | 1.4s | The stamp and the desk thud, close up |
| `odometer-roll` | 2.0s | The take rolling from $0 to $7,420 |
| `typewriter-line` | 1.6s | One ledger line typing |
| `marker-in` | 1.4s | An evidence marker landing, with the top-five pulse |
| `hard-cut` | 0.8s | The bone flash when a new still arrives |
| `film-texture` | 4.0s | Grain, flicker, vignette and a gate hair on their own |

## Rebuilding the packs

After changing the kit, run `python packs/tools/build_packs.py` from `ui-kit/`. It needs Python with Playwright and Pillow, Chrome, and ffmpeg, and takes about three minutes. It regenerates `assets/` and `animation/`; the font files are downloads and don't change.
