# Motion spec

Exact values for rebuilding any NOIRKIT animation in After Effects, Figma or anything else. The source of truth is the tokens in `noir.css`; these values match them. Every clip in this folder was recorded from the live kit.

The film runs at 24 frames per second. Grain still jumps. Everything that carries the scene eases through a full arc: slow out of the gate, slow into the rest.

## Easing curves

Bezier handles as (x1, y1, x2, y2), the same numbers CSS `cubic-bezier()` takes. In After Effects, enter them in a bezier easing tool such as Flow, or set the graph handles by hand.

| Name | Handles | Character | Used by |
|---|---|---|---|
| stamp | 0.33, 0.02, 0.20, 1.00 | Soft throughout; the keyframes do a small settle | Stamp |
| settle | 0.42, 0.02, 0.18, 1.00 | Slow start, long landing | Markers, photos, placards, title bars |
| odo | 0.33, 0.02, 0.16, 1.00 | A little inertia, then a soft stop | Odometer digits |
| film | 0.45, 0.03, 0.20, 1.00 | Soft at both ends | Fades, dissolves, the cue, the shutter wash |

## Every animation

Times in milliseconds. Tokens in `noir.css` are the source of truth if a number here ever drifts.

| Clip | Property | Keyframes | Duration | Easing | Trigger |
|---|---|---|---|---|---|
| `reel-start` | Whole frame | PICTURE START fades, then 8, 7, SIX, 5, 4, 3, each number settling, then a dissolve out | 667 per number, then a 680 fade | settle / film | Page boot |
| `title-card` | Five paper bars, translate | Off screen at 0%, in place from 10% to 86%, off again from 96% | 12s loop, replayed from the top each time the card returns | film | 15s with no scan |
| `title-card` | Title block, opacity | 0 until 2%, 1 from 11% to 88%, then 0 | 12s loop | film | Same |
| `scan-beat` | Ledger line | Types one character per tick, then the amount fades in | 16 per character | Linear, then settle | New exhibit |
| `scan-beat` | Marker | Draws in after the line, label follows | 280 pause, then 560 | settle | Exhibit confirmed |
| `scan-beat` | Odometer | Rolls once the marker has settled | 320 pause, then 1040 | odo | Take changes |
| `marker-in` | Marker, scale, translateY, opacity | 0.9, 10px, 0, then rest | 560 | settle | Exhibit confirmed |
| `marker-in` | Tag, background and text color | Eases to paper around the middle, back by the end | 1200, after the label | settle | Item enters the top five |
| `odometer-roll` | Each digit wheel, translateY | To the digit's position | 1040 per digit, starting 72 apart from the right | odo | Take changes |
| `hard-cut` | Bone wash over the feed, opacity | 0, 0.14 at 28%, 0 | 340 | film | New still from the rig |
| `reveal` | Changeover cue, opacity and scale | Fades to 0.9 and scale 1, holds, fades out | 860 | film | Button press, 0 |
| `reveal` | Feed, translate | A small settle back to the gate | 380 | film | Button press, 0 |
| `reveal` | Black curtain, opacity | 0 to 1, overlapping the settle, then 1 to 0 | 780 in, 700 out | film | During the settle |
| `reveal` | Each suspect | Slot fades, photo drops 28px, placard and name follow | 700, next one every 420, rank 5 first | settle | As the curtain lifts |
| `reveal` | Each price | Counts up from 0, slow at both ends | 1100 | Smoothstep | With its photo |
| `reveal` | Total | Odometer roll | 1040 per digit | odo | As the last photo lands |
| `stamp-slam` | Stamp, scale and opacity | 1.16 and 0, 0.988 and 1 at 42%, 1.018 at 64%, 1 at 100% | 820 | stamp | While the total is finishing |
| `stamp-slam` | Lineup wall, translateY | 2.4, -1.5, 0.8, -0.3, 0 | 520 | Linear, decaying | Stamp contact, 42% in |
| `the-end` | Card, opacity | Fade in, hold, fade out onto the next picture | 680 in, 3200 hold, 680 out | film | A run finishes |
| `footage-lost`, `line-dead` | Leader number | 8, 7, SIX, 5, 4, 3, each settling | 667 per number | settle | Camera lost, rig unreachable |
| `typewriter-line` | Caret | Dims and returns | 1100 loop | Ease | While typing |
| `film-texture` | Grain tile, translate | 8 fixed positions | 660 loop | Hold | Always |
| `film-texture` | Flicker overlay, opacity | Wanders between 0 and 0.03 | 7300 loop | Linear | Always |
| `film-texture` | Gate hair and dust | A line and two specks that fade | Every 6 to 12s | settle | Always |
| live view | Footage only, translate | 1px drift | about 5.5s loop | film | Live |

## Rules for new motion

A dissolve, a settle, or a fade is the default. A strobe, a pop, or a bounce on a number is wrong. Nothing travels in from off screen except the title card bars. If a new animation needs an easing, use one of the four above. When `prefers-reduced-motion` is set, every animation completes instantly and the texture, weave, reel start and cue mark are removed.
