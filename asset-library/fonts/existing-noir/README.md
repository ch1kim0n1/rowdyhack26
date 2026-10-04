# Fonts

Vendored so the kit renders with no internet. Latin subsets, served by `noir.css` via `@font-face`.

| File | Family | Role | License |
|---|---|---|---|
| `league-gothic-400.woff2` | League Gothic | Headlines, the take, names | SIL OFL 1.1 |
| `special-elite-400.woff2` | Special Elite | Typed entries: exhibit log, case file | Apache 2.0 |
| `courier-prime-400.woff2`, `courier-prime-700.woff2` | Courier Prime | Printed-form labels, meta, chrome | SIL OFL 1.1 |
| `caveat-500.woff2` | Caveat | Pencil marginalia | SIL OFL 1.1 |
| `LeagueGothic-Regular.ttf` | League Gothic | The rig's OLED (`display.py`). Copy to `fonts/` next to `display.py` on the Pi | SIL OFL 1.1 |

All from Google Fonts (fonts.google.com). Free to use, bundle and ship in this project; the license texts are in `licenses/` and must travel with the files. Desktop TTF versions for designers are in `packs/fonts/`. The latin subset covers U+0000 to U+00FF plus common punctuation, which includes accented names like RIVIÈRE and the `·` separator. If an LLM ever returns a name outside that range, the browser falls back to Courier New for that one glyph.
