# Heist asset library

Downloaded shortlist for the project's noir/heist interface. Nothing here is wired into the app yet. Existing project assets are copies; their original locations are unchanged.

## What's inside

| Folder | Contents | Suggested use |
| --- | --- | --- |
| `music/` | Covert Affair, Bass Walker, Night on the Docks - Piano, Spy Glass | Planning ambience, briefing, dossier screens, short reveal moments |
| `sfx/freesound/` | Five HQ MP3 previews: shutter, paper shuffle, stamp, end-radio transmission, binder | Evidence capture, case-file handling, narrator radio cues |
| `sfx/kenney/interface-sounds/` | Complete Interface Sounds pack, 100 OGG files, extracted | Selection, confirmation, errors, UI transitions |
| `sfx/kenney/casino-audio/` | Complete Casino Audio pack, 55 OGG files, extracted | Loot, cash/chip handling, reward feedback; use sparingly |
| `sfx/existing-noir/` | Existing projector, typewriter, typewriter ding, radio static, stamp | Keep the current noir sound palette coherent |
| `components/game-icons/` | Spy, briefcase, pocket watch; black and white transparent SVG + PNG | Crew, carrying capacity, time pressure |
| `components/existing-noir/` | Existing SVG and PNG stamps, film decorations, reference sheets, title assets | Evidence cards, dossiers, cinematic framing |
| `textures/existing-noir/` | Existing paper and dark-paper textures | Case-file surfaces |
| `fonts/existing-noir/` | Existing project fonts and bundled license files | Preserve the current typography |
| `archives/` | Both original Kenney ZIP downloads | Untouched source packs |
| `licenses/` | License snapshots, additional font licenses, inherited attribution | Keep with redistributed assets |

## Download limitations

The five Freesound files are the site's public **HQ MP3 previews**, not the original WAVs. Original downloads require a Freesound login; their source pages are linked in [CREDITS.md](CREDITS.md) and `manifest.json`. Filenames explicitly include `_hq-preview` to avoid confusion. They are playable local assets, but use the originals if you need lossless editing.

No voice lines were generated or recorded. Custom crew emblems, new conditional-status stamps, and new UI component templates still need to be authored; they weren't downloadable assets in the shortlist.

## Usage notes

- Start with **Covert Affair** for planning and **Night on the Docks - Piano** for quieter dossier screens. These are full tracks, not ready-made seamless loops.
- Keep music low under the narrator. Fade or duck it during speech, and avoid layering several radio/static sounds simultaneously.
- Cut short cues from the paper/binder recordings before triggering them in the UI; don't play the entire recording on every interaction.
- Use black icons on paper and white icons on dark panels. Prefer SVG in the web UI.
- Add separate music/SFX/voice controls and respect mute. These are integration suggestions, not implemented behavior.

## Credits and verification

Read [CREDITS.md](CREDITS.md) before shipping. New music and icons require attribution. Existing assets retain their previous license metadata, including some share-alike terms and incomplete texture provenance; they are not all CC0.

`manifest.json` records direct download URLs, source pages, quality limitations, sizes, and SHA-256 hashes. `verification.json` records media and archive checks. The copied project's broad font attribution mislabels Special Elite as OFL; its specific README and included Apache 2.0 license take precedence.
