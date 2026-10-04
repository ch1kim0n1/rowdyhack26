# brand/

## Vault artwork and crew emblem

The premiere uses `appraisal-job-hero-wide.webp` (1916 × 821, about 242 KB)
as an edge-to-edge desktop hero. Its vault walls and floor were extended
with the built-in ImageGen tool, preserving the title and four-person crew
inside the safe crop area. The PNG master and exact generation prompt are
saved alongside it as `appraisal-job-hero-wide.png` and
`appraisal-job-hero-wide.prompt.txt`.

Portrait and 4:3 layouts use `appraisal-job-wallpaper.webp` (1536 × 1024,
about 175 KB) at full width and its native ratio. The same image is used for
the projector title card and subdued shared wallpaper.
`appraisal-job-wallpaper.png` is the source master. The supplied
vault artwork was edited with ImageGen to replace MIDNIGHT with APPRAISAL;
the scene and other lettering were retained.

`noir-clock-emblem.webp` is the masked-clock-and-city emblem from the same
design exploration. Its transparent PNG master is retained alongside it.
These are generated raster assets. The WebP files are optimized exports.

The decorative animation lives in `../vault.css` and `../vault.js`: subtle
camera drift, vault light, dust, pause/resume, and reduced-motion support.
Motion preferences persist locally; pausing decoration does not freeze
ledger entries or other functional UI updates.

## Original placeholder

The slot for the crew's emblem. Pages pick it up on their own:

- `emblem.png`: the mark beside "The Appraisal Job" in the premiere's marquee
  and on the dispatch desk. Transparent PNG, roughly square, about 256px.
  If the file is missing the pages show the wordmark alone.

`emblem.png` is a placeholder right now: an AJ monogram on paper, marked PLACEHOLDER.
Replace it with the real emblem when there is one.

It should be a generated image, not a mark drawn from circles and lines.
A prompt that fits the kit:

> A 1950s film-noir emblem for an authorized physical red-team crew called "The Appraisal Job":
> a jeweler's loupe resting on the brim of a fedora, cut-paper style in the
> manner of Saul Bass title design, black and warm off-white (#efe9db) only,
> one small accent of stamp-pad red (#a5382f), flat shapes, torn paper edges,
> no text, transparent background.
