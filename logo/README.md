# Logo tools

Turn any logo into production graphics: a clean vector from a low-resolution raster, a 3D extrusion with transparent
4K stills, a looping alpha video and a GLB model, and a library of animated logo templates (intros, end cards, corner
bugs, stingers, sponsor lower thirds and more) rendered as ProRes 4444 with alpha. Brand colors and fonts come from a
profile, so the same commands render for any organization. Part of the
[Stealth Goat video engines](../README.md); see [docs/TOOLS.md](../docs/TOOLS.md) for every tool in the repo.

## Quick start

Run from the repo root after `./setup.sh` (or `logo/setup.sh` for the logo tools alone). This uses the bundled
`demo` profile and its drawn logo; everything is written to `out/logo/`, which git ignores.

```bash
# 1. Raster to vector: Demo.svg, Demo_Transparent_4000px.png and Demo_vector_check.png (a few seconds)
python3 logo/vectorize.py profiles/demo/assets/demo_logo.png out/logo Demo --palette "#0B3D2E,#F2B705"

# 2. 3D stills and a GLB model (Demo_3D_Hero_4K.png, Demo_3D_Front_4K.png, Demo_3D.glb; about 10 seconds)
python3 logo/render3d.py out/logo/Demo.svg out/logo Demo --still-only --profile demo

# 3. Three stills of the animated intro (Demo_intro_t0.50.png ...), then the full alpha render (a few minutes)
python3 logo/motion.py out/logo/Demo.svg out/logo Demo intro --profile demo --frames 0.5,1.5,3
python3 logo/motion.py out/logo/Demo.svg out/logo Demo intro --profile demo

# 4. QA the render. The intro holds the finished logo to the end on purpose, so declare that hold; it renders at
#    60 fps while the demo profile delivers 29.97, so pass --fps 60
python3 engine/qa.py out/logo/Demo_intro.mp4 --profile demo --kind motion --cuts none --fps 60 \
    --intended end_tail --holds end:2.2 --out out/logo/qa_intro
```

The vectorize step should print `FIDELITY silhouette IoU 1.000`, and the QA step should end `RESULT: PASS (0 warnings)`.
A mark that settles sooner holds still for longer at the end and shows `RESULT: PASS (0 warnings, 1 declared intended)`:
the declared end tail is listed as INFO, not hidden.

## The tools

| Tool | Input | Output |
|---|---|---|
| **`vectorize.py`**, raster to vector | any logo PNG or JPG, even 100 px wide or a screenshot | a clean layered **SVG**, a transparent **PNG at 4000 px**, and a check image (original, vector, difference) with a fidelity score |
| **`redraw.py`** + **`fontmatch.py`**, rebuild | a logo that cannot be traced (3D mockup, photo, embossed render) | a clean vector rebuilt from measured shapes and real-font lettering, with an overlay check |
| **`render3d.py`**, logo to 3D | any SVG (your own, a partner's, or one from `vectorize.py`) | transparent **Hero** and **Front** 4K PNGs; a **swing** (or spin) loop as an alpha `.mov` plus an `.mp4`; a **GLB** model |
| **`motion.py`**, animated graphics | any SVG | more than a dozen templates (below), each as an alpha `.mov` plus an `.mp4` preview; every move runs on [spring physics](../engine/README_motion.md) |

The 3D engine follows the approach of [3dsvg](https://github.com/renatoworks/3dsvg) (MIT): three.js `SVGLoader` with
`ExtrudeGeometry`. Three things differ. Each fill keeps its own color (3dsvg makes the whole logo one color),
stacked artwork sits in raised layers, and neutral chrome or steel greys render as metal.

### Where things live

- `logo/`: the scripts, the pages they drive in headless Chromium (`render.html`, `motion.html`, `engine.js`), and
  `node_modules/` (installed by `setup.sh`).
- `resources/fonts/`: shared open-license fonts. A profile's `brand.fonts` (`head`, `body`, `body_semibold`) point at
  font files, and `motion.py` loads them into the page itself.
- `resources/models/`: the super-resolution models (`EDSR_x4.pb`, `FSRCNN_x4.pb`, OpenCV dnn_superres, Apache-2.0)
  used by `sr.py` and `vectorize.py`. They are not committed: `logo/setup.sh` downloads them from the
  [Saafke/EDSR_Tensorflow](https://github.com/Saafke/EDSR_Tensorflow) and
  [Saafke/FSRCNN_Tensorflow](https://github.com/Saafke/FSRCNN_Tensorflow) repos and checks their SHA-256: on a mismatch it prints a note and keeps the
  downloaded model.
- `logo/srenv/`: a small virtual environment with `opencv-contrib` for `sr.py`, kept apart so it cannot clash with
  the main OpenCV (made by `setup.sh`, ignored by git).
- `logo/stories/placeholder_story.svg`: a sample for the `lightpaint` template.

### Setup

```bash
logo/setup.sh     # npm packages (three, @gltf-transform/cli), Python packages, Chromium, the SR venv and models
```

The npm packages come from `logo/package.json`. Playwright is a Python package, installed with pip together with the
others (`vtracer`, `cairosvg`, `scikit-learn`, `opencv-python-headless`, `pillow`, `fonttools`), and its Chromium
comes from `python3 -m playwright install chromium`. pip runs with `--break-system-packages` first and falls back to
`--user`. The script works from any folder and is safe to run again. If a model download fails, `vectorize.py` falls back to a
Lanczos upscale.

## Vectorize a low-resolution logo

```bash
python3 logo/vectorize.py logo.png out/ ACME --palette "#112233,#E04050,#FFFFFF"
```

Writes `ACME.svg`, `ACME_Transparent_4000px.png` and `ACME_vector_check.png` into `out/`.

- `--palette`: the brand hex colors. Thin outlines in those colors survive the trace, and found colors near a
  brand color snap to its exact value. A found color far from every brand color (an edge blend, or a grey the
  palette left out) stays as its own layer, so check the layer list it prints. Without `--palette` the colors are
  found automatically.
- `--colors N`: force the number of flat colors.
- `--bg auto|none|#hex`: remove a solid background. Only background connected to the edge is removed, so a white
  shape inside the logo stays.
- `--detail 1.5` keeps smaller details; `0.7` smooths more.
- `--png-width`: width of the transparent PNG (default 4000).
- `--flatten-shading`: for logos that are already shaded or photographed; drops light neutral shadows and groups
  colors by hue.
- Logos under 700 px on the long side are upscaled ×4 with EDSR (in `logo/srenv`) before tracing; without the venv
  or the model they fall back to a Lanczos upscale.
- **Check the score.** A silhouette IoU of at least 0.98 and a mean color error of at most 20/255 means it is ready
  to use. Below that, open `*_vector_check.png`: red marks shape the vector missed, blue marks shape it added.
- A trace is a redraw, not the master file. If an official vector exists (a brand kit, the owner's own files), use
  that instead.

## Redraw a logo that cannot be traced

For 3D mockups, photos of signs and embossed renders, `redraw.py` rebuilds the logo from measured points: clean
polygons, strokes that extrude in 3D, and real-font text fitted to a measured box. Use it from a short per-logo script
(the `redraw.py` docstring shows one). `fontmatch.py` finds the closest font for a line of lettering:

```bash
python3 logo/fontmatch.py photo.jpg "ACME" 62,305,714,434 resources/fonts     # x0,y0,x1,y1 box around the text
```

It ranks every font in the folder by overlap and writes `fontmatch_<text>.png` with the best matches overlaid; an IoU
of 0.80 or more is usually the same family. The
[logo-vectorize skill](../plugins/video-engine/skills/logo-vectorize/SKILL.md) walks through the whole redraw method.

## Make a 3D logo

```bash
python3 logo/render3d.py logo.svg out/ ACME --bg 112233        # or --bg '#112233' (quote it: # starts a shell comment)
python3 logo/render3d.py logo.svg out/ ACME --still-only       # stills and GLB only (seconds)
python3 logo/render3d.py logo.svg out/ ACME --anim spin        # a full 360° turn instead of the swing
```

| File | What it is |
|---|---|
| `ACME_3D_Hero_4K.png` | 3840×2160, transparent, angled |
| `ACME_3D_Front_4K.png` | 3840×2160, transparent, straight on |
| `ACME_3D_Swing_Alpha.mov` | 1920×1080, 60 fps, ProRes 4444 with alpha, seamless loop (`_Spin_` with `--anim spin`) |
| `ACME_3D_Swing.mp4` | the same loop in H.264 on the `--bg` color, for social and web |
| `ACME_3D.glb` | the 3D model, for Blender, After Effects or the web |

- `--depth 0.03`: extrusion as a fraction of the logo width (0.02 subtle, 0.05 chunky).
- `--bg`: background color for the `.mp4` only, with or without the `#` (default: the profile's primary color).
  Every PNG and the `.mov` stay transparent.
- `--hero "0.10,-0.30"`: tilt and turn of the hero still, in radians.
- `--fps 60 --spin-seconds 4`: loop settings.
- `--drop-bg`: leave out a filled rectangle covering the whole SVG canvas (an export background); `render3d.py`
  prints a line when it drops one. It is off by default because a full-bleed plate can be part of the logo (a square
  badge, or a traced logo whose bottom layer is its whole silhouette).
- A full render with the loop takes about a minute for a simple mark and several minutes for a detailed traced logo.
  Stills take seconds.

## Animated logo graphics

```bash
python3 logo/motion.py logo.svg out/ ACME intro
python3 logo/motion.py logo.svg out/ ACME outro --text1 "THANKS FOR WATCHING" --text2 "ACME TV · YOUTUBE"
python3 logo/motion.py logo.svg out/ ACME bug                       # writes bug_in, bug_loop and bug_out
python3 logo/motion.py logo.svg out/ ACME stinger                   # prints the cut point
python3 logo/motion.py logo.svg out/ ACME presented --text1 "PRESENTED BY" --sponsor sponsor_logo.png
python3 logo/motion.py logo.svg out/ ACME intro --frames 0.5,1.5,3  # quick stills only
python3 logo/motion.py logo.svg out/ ACME stinger --bg '#112233'    # preview .mp4 background
```

| Template | Length | What it does |
|---|---|---|
| `intro` | 4 s | the logo lands and holds |
| `outro` | 6 s | end card with `--text1` and `--text2` (`--accent` colors the second line) |
| `bug` | in / loop / out | corner bug as three files |
| `stinger` | 1.2 s | full-frame wipe; prints the cut point |
| `presented` | 5 s | "presented by" lower third: `--text1` plus a `--sponsor` image |
| `slam` | 2 s or `--dur` | slam-in that lands in `--place cx,cy,w,h` (frame fractions), for compositing |
| `lockup` | 4.17 s | a camera settles onto a lit sign: `--text1` small top line, `--text2` headline, `--text3` subline; `--plate` puts a background still under it |
| `writeon` | 4.5 s or `--dur` | a glowing pen traces the outlines, then the fills land; prints the hit time; `--write` sets the pen time |
| `morph` | 3.6 s | circles float in and morph into each part of the mark |
| `pixelbuild` | 3.4 s | a dot grid springs out from the center into the logo |
| `linebuild` | 7.5 s | outline pieces converge, fills land, then a construction grid |
| `echo` | 1.2 s | outline stinger; prints the cut point |
| `lightstreak` | 3.5 s | a light with a long trail writes the logo |
| `lightpaint` | 2.4 s a scene + 0.8 s | each top-level `<g>` of the SVG is a scene drawn in turn by one light (try `logo/stories/placeholder_story.svg`) |
| `swap` | 0.9 s a word + 1.5 s | kinetic word swap: `--text1 "___ is next" --text2 "faster\|bolder\|yours"` |
| `shatter` | 3.2 s | the mark shatters and re-forms as `--svg2` (or `--text2` in the head font) |
| `brandgrid` | 5 s | logo, colors, type and a stat counting up (`--text1` label, `--text2` value) |

More examples:

```bash
python3 logo/motion.py logo.svg out/ ACME slam --place 0.5,0.44,0.62,0.42 --dur 3.4 --fps 29.97002997 --png-seq
python3 logo/motion.py logo.svg out/ ACME lockup --text1 "ACME TV" --text2 "SHOW TITLE" --text3 "DAY | TIME | LIVE" --plate set.png
python3 logo/motion.py logo.svg out/ ACME writeon --text1 "HELLO WORLD"
python3 logo/motion.py logo/stories/placeholder_story.svg out/ STORY lightpaint --finish dark
python3 logo/motion.py logo.svg out/ ACME writeon --finish dark --mockup laptop
```

Each run writes `<Name>_<template>_Alpha.mov` (ProRes 4444 with alpha, 1080p60 by default) and an `.mp4` preview on
`--bg` (default: the profile's primary color). Other options:

- `--frames t1,t2,...`: render only those stills (`<Name>_<template>_t<seconds>.png`) for a quick look.
- `--png-seq`: write a transparent PNG sequence instead of encoding.
- `--fps`, `--size 1920x1080`: frame rate and size.
- `--finish dark`: a cinematic finish on any template (dark ground, bloom, reflective floor, depth of field, grain,
  vignette; opaque output). Add `--mockup laptop` to put the finished frame on a laptop screen. A profile's
  `finish.dark` block overrides the built-in settings.
- `--profile <name>`: render for another organization.

Panel and text colors, the accent and the fonts all come from the profile (`brand.colors`, `brand.fonts`). Every
profile font must load in the page: if one does not, `motion.py` stops with an error rather than drawing the text in a
fallback font. Templates that print a hit or cut time are meant to be checked with `engine/qa.py --cuts`.

## Profiles

Every tool that takes `--profile` uses `--profile <name>`, else `$VIDEO_PROFILE`, else the machine's `local.json`.
Start from `profiles/demo/profile.json` or `profiles/_template/profile.json`, or make one with
`python3 engine/vprofile.py new <name>`; [docs/LAYOUT.md](../docs/LAYOUT.md) describes every key. `vectorize.py`,
`redraw.py` and `fontmatch.py` need no profile.

## See also

- [Root README](../README.md): install, profiles and the tour of the engine.
- [docs/TOOLS.md](../docs/TOOLS.md): every tool in the repo.
- [engine/README_motion.md](../engine/README_motion.md): the spring presets every animation uses, and the motion gate.
- [logo-motion](../plugins/video-engine/skills/logo-motion/SKILL.md),
  [logo-3d](../plugins/video-engine/skills/logo-3d/SKILL.md) and
  [logo-vectorize](../plugins/video-engine/skills/logo-vectorize/SKILL.md): the Claude skills that drive these tools.
