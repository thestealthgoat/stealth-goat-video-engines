---
name: logo-vectorize
description: Turns a raster logo (low-res PNG, JPG, screenshot, 3D mockup or photo of a sign) into a clean layered vector SVG plus a transparent 4000 px PNG, with a fidelity score and a side-by-side check image. Auto-traces with the engine's logo/vectorize.py, or rebuilds the logo from measured shapes and real-font lettering (logo/redraw.py + logo/fontmatch.py) when tracing fails. Use when the user says "turn this JPG logo into a clean SVG", "vectorize this logo", "trace our logo", "I only have a blurry/low-res logo", "make a transparent PNG of this logo", "redraw this logo", "what font is this logo", or needs an SVG before a logo animation or 3D logo.
---

# Logo vectorize

Turn a raster logo into a vector that matches the original. `logo/vectorize.py` removes a solid background,
upscales small images ×4 (EDSR super-resolution, else Lanczos), finds the flat colours (optionally snapped to brand
hexes), cleans each colour layer, traces smooth curves with vtracer, and stacks the layers outside-to-inside with no
seams. When tracing cannot work, rebuild the logo by hand with `logo/redraw.py`, using `logo/fontmatch.py` to find
the lettering font.

Everything runs locally with free, open-source tools (vtracer, cairosvg, OpenCV, scikit-learn, fontTools). Nothing
is uploaded.

## 0. Find the engine

- Use the engine folder at `$VIDEO_ENGINE` (a clone of
  https://github.com/thestealthgoat/stealth-goat-video-engines). Run every command as
  `cd "$VIDEO_ENGINE" && python3 logo/<tool>.py ...`.
- If `$VIDEO_ENGINE` is unset or the folder has no `logo/vectorize.py`, ask the user where the engine is, or set it
  up (the **getting-started** skill walks through it): `git clone https://github.com/thestealthgoat/stealth-goat-video-engines`,
  `cd stealth-goat-video-engines && ./setup.sh`, then `export VIDEO_ENGINE="$PWD"`. `setup.sh` targets macOS with
  Homebrew; on other systems install the packages it lists by hand.
- Check the tools once per machine: `cd "$VIDEO_ENGINE" && ./setup.sh --check` (installs nothing). If vtracer,
  cairosvg, sklearn or fontTools are missing, or you want the AI upscale, run `logo/setup.sh` (it works from any
  folder). First tell the user what it does: npm packages in `logo/`; pip packages (vtracer, cairosvg,
  scikit-learn, opencv-python-headless, pillow, playwright, fonttools), tried with `--break-system-packages` first
  and then `--user`; Playwright's Chromium browser download; a small `logo/srenv` venv with opencv-contrib; and two
  super-resolution models (EDSR and FSRCNN, from the Saafke GitHub repos) into `resources/models/`.
- A fresh clone has no `resources/models/` (`./setup.sh --check` warns `EDSR_x4.pb missing`), so logos under 700 px
  get a Lanczos upscale instead of the AI one until `logo/setup.sh` has run. That still works; say which one ran in
  the report (section 6 says how to tell).
- Keep outputs outside the engine folder (a work folder next to the source logo, or one the user names).

## 1. Find the best source first

- Ask for, or look for, an official vector before tracing anything: a brand kit, `logo.svg` / `.ai` / `.eps` /
  `.pdf` in the asset folder, the organisation's press page. A real vector beats any trace; if one exists, use it
  and stop.
- From the rasters, pick the **largest, cleanest** file: transparent PNG over JPG, the biggest pixel size, no
  compression blocks.
- Get the brand hexes. For the user's own brand, read them from the profile:
  `cd "$VIDEO_ENGINE" && python3 engine/vprofile.py show <profile>` (the `color` lines; `demo` for trying things).
  For someone else's logo, use their brand guide, or sample the flat areas of the image. Measured values beat
  "approximately". `vectorize.py` itself takes no `--profile`; pass the hexes with `--palette`.

## 2. Auto-trace

```bash
cd "$VIDEO_ENGINE" && python3 logo/vectorize.py <logo.png|jpg> <out_dir> <Name> --palette "#hex,#hex" [--colors N]
```

It writes `<out_dir>/<Name>.svg`, `<Name>_Transparent_4000px.png` and `<Name>_vector_check.png`, prints one
`layer #hex  area ..%  paths N` line per colour, then the **FIDELITY** line.

Main options (full list and troubleshooting in [references/vectorize.md](references/vectorize.md)):
- `--palette "#hex,..."`: brand colours. Thin outlines in those colours survive, and colours snap to the exact hexes.
- `--colors N`: the true number of flat colours. Set it whenever you know it: it stops anti-aliased edges becoming
  an extra fringe layer.
- `--bg auto|none|#hex`: `auto` removes a solid background connected to the edge; `none` keeps the logo's own
  background plate when it is part of the art.
- `--detail 1.5` for fine lettering; `--detail 0.7` for noisy JPGs.
- `--flatten-shading` (+ `--bg-light`) for mildly embossed or photographed logos: drops light neutral shadows and
  groups colours by hue instead of brightness. Try it once before switching to a redraw.

### Worked example (fresh clone, demo profile)

```bash
cd "$VIDEO_ENGINE" && python3 engine/vprofile.py show demo        # primary #0B3D2E, accent #F2B705
cd "$VIDEO_ENGINE" && python3 logo/vectorize.py profiles/demo/assets/demo_logo.png ~/logo-work/demo DemoLogo \
    --palette "#0B3D2E,#F2B705" --colors 2
```

Expected: two layers (`#f2b705` about 59 %, `#0b3d2e` about 41 %) and
`FIDELITY silhouette IoU 1.000  mean colour error 1.2/255  colours 2`. Without `--colors 2` the same run adds a
third, about 2 % olive layer: the anti-aliased edge between gold and green. That is the case `--colors` is for. The
demo logo is 551 × 320, so a fresh clone without `logo/setup.sh` upscales it with Lanczos; these numbers are from
that case.

## 3. Judge the result

1. Read the FIDELITY line. Good: **IoU ≥ 0.98** and **colour error ≤ 20/255**. Below 0.97 IoU, look closely before
   using it.
2. `Read` `<Name>_vector_check.png` (original | vector | difference). In the difference panel, red is shape the
   vector missed and blue is shape it added; the rest shows colour difference, so a near-black panel is a match.
   Check lettering, thin outlines and small holes by eye, not only by score.
3. Fix and re-run, at most three attempts:
   - colours merged or a thin outline vanished: add that colour to `--palette`, or raise `--colors`;
   - an extra small layer of an in-between colour: lower `--colors` to the true count;
   - lumpy or rounded-off edges: raise `--detail`, or find a larger source;
   - speckles or JPEG noise traced as shapes: lower `--detail`;
   - the logo's white plate disappeared: `--bg none`.
4. After three tries, or when the signs in section 4 apply, stop tracing: report what is wrong or switch to a redraw.
   Never ship a bad trace.

## 4. Redraw mode, when tracing fails

Use a redraw for 3D mockups, embossed or metal renders, photos of signs, and logos with baked-in shadows or
lighting. The signs: the layer colours sit only a few units apart, the check image looks blotchy, or shadows join
up with shapes. Rebuild the logo the way a designer would. Full API, helper scripts and a worked example are in
[references/redraw.md](references/redraw.md).

1. **Measure.** Make gridded enlargements of the reference (the whole logo with a 25 px grid; each detailed area at
   4× with a 10 px grid; the grid script is in the reference). `Read` them and write down the coordinates of every
   corner and the ink box of each line of lettering.
2. **Match the lettering.** From the work folder (it writes `fontmatch_<TEXT>.png` into the current folder):
   ```bash
   cd ~/logo-work/demo && python3 "$VIDEO_ENGINE/logo/fontmatch.py" "$VIDEO_ENGINE/profiles/demo/assets/demo_logo.png" \
       "DEMO" 40,90,510,295 "$VIDEO_ENGINE/resources/fonts" --thresh 62
   ```
   The box must hold all of the lettering with a little margin (the demo's measured ink box is 49,98 to 503,290); a
   box that clips the letters lowers every score. It ranks every `.ttf`/`.otf` in the folder by overlap (IoU) and
   prints the top 6 (`--top N`); on the demo logo, `Anton-Regular.ttf` wins at about 0.98, with the next font about
   0.77. The ranking below the winner depends on which fonts are in the folder. `--thresh` is the L* cut for the letter mask (a negative value selects
   light letters on a dark ground). ≥ 0.80 is usually the same family or close enough. `Read` the overlay image.
   If nothing fits, gather candidate OFL fonts into a folder and run again (see the reference for families by
   style).
3. **Rebuild** in a short per-logo Python script with `redraw.Doc(w, h)` in the reference image's pixel space:
   `poly()` / `rect()` for shapes (with `holes=` for cut-outs), `line()` / `polyline()` for strokes (filled quads, so
   they extrude in 3D later), `text()` to set real font outlines stretched to the measured box. Pick 3–5 flat colours
   from the art; a mockup's lighting is not a colour.
4. **Check.** `d.check(ref, 'check.png')` writes reference | redraw | redraw outline over reference. `Read` it and fix
   any edge that drifts more than a few px. Simplify illustrations to clean shapes; don't chase texture or shading.
5. **Label it.** Say clearly it is a **redraw**: close to the original, not the designer's file. If the owner can
   get the original file, use that instead.

## 5. Save

- Never overwrite or edit the source files.
- Save beside the source logo as `logo-vector.svg` and `logo-vector-4000px.png` (copy from `<Name>.svg` and
  `<Name>_Transparent_4000px.png`); keep the check image and any redraw script in a `_vector/` folder next to it.
  If the user names other filenames or a folder, use theirs.
- Add one line to a notes file beside the logo (or tell the user), e.g. "logo-vector.svg traced 2026-11-09 from
  logo.png (IoU 0.997)", so nobody mistakes a trace for the official master.
- For the user's own brand, offer to make the SVG the profile's logo: a new profile takes it with
  `cd "$VIDEO_ENGINE" && python3 engine/vprofile.py new <name> --logo "/absolute/path/to/logo-vector.svg"` (use the
  saved file's absolute path, since the command runs from the engine folder; it copies the SVG into the profile's
  `assets/` and stores it as `brand.logo_svg`); for an existing
  profile, copy it into `profiles/<name>/assets/` and set `brand.logo_svg` in `profile.json` after asking.

## 6. Report

In one or two lines: what was traced (or redrawn), the fidelity score, where the files are, how it was upscaled, and
any detail the trace could not hold.

`vectorize.py` does not print which upscale ran, so work it out:
- Long side 700 px or more: no ×4 upscale at all (only a resize to the working size).
- Under 700 px: AI only if `$VIDEO_ENGINE/logo/srenv/bin/python` exists, the model exists in
  `$VIDEO_ENGINE/resources/models/` (`EDSR_x4.pb` for a long side up to 600 px, `FSRCNN_x4.pb` for 601 to 699 px),
  and the run printed no Python traceback from `sr.py` before the `layer` lines. If any of those fails, it silently
  used Lanczos. If an official vector should be requested (a partner's or
sponsor's logo especially), say who to ask.

## Hand-offs

- Want it in 3D? Run the **logo-3d** skill on the new SVG. Animated (intro, end card, corner bug)? Run
  **logo-motion**. Any video made from it goes through **video-gates** before delivery.
- Logos of other organisations: keep their original untouched, use the vector only for the job at hand, and prefer
  their official file whenever they can supply it.
