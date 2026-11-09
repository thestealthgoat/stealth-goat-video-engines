# Logo tools (`logo/`)

Logo tools for any organisation. Brand colours and fonts come from the profile (`profiles/<name>/profile.json`,
chosen with `--profile`, else `$VIDEO_PROFILE`, else `local.json`). Run them from the repo root on a Mac or in a
cloud workspace; outputs go wherever you point them (the profile's paths).

| Tool | Input | Output |
|---|---|---|
| **vectorize.py**, raster to vector | any logo PNG/JPG, even 100 px or a screenshot | clean layered **SVG**, transparent **PNG at 4000 px**, and a check image (original, vector, difference) with a fidelity score |
| **redraw.py** + **fontmatch.py**, rebuild | a logo that can't be traced (3D mockup, photo, embossed) | clean vector rebuilt from measured shapes and real-font lettering, with an overlay check |
| **render3d.py**, logo to 3D | any SVG (ours, a school's, a sponsor's, or one from vectorize.py) | **Hero 4K PNG** (angled) and **Front 4K PNG**, both transparent; **Swing loop** as an alpha .mov for vMix plus a .mp4 for social; **GLB** 3D model |
| **motion.py**, animated graphics | any SVG | intro, outro end card, corner bug (in/loop/out), stinger, "presented by" lower third, slam, lockup (measured rebuild of an AE sign lockup) and writeon (signature write-on with a glowing pen), as alpha .mov + .mp4; all motion on spring.js |

The 3D engine uses the same approach as [3dsvg](https://github.com/renatoworks/3dsvg) (MIT): three.js `SVGLoader` with
`ExtrudeGeometry`. We changed three things. Each fill keeps its own colour (3dsvg makes the whole logo one colour). Stacked
artwork sits in raised layers. Neutral greys such as armour or swords render as metal.

## Layout

- `logo/` the scripts, `render.html` / `motion.html` / `engine.js` (the pages they drive in headless Chromium) and
  `node_modules/` (from `setup.sh`).
- `resources/fonts/` the brand fonts. The profile's `brand.fonts` (`head`, `body`, `body_semibold`) point here, and
  motion.py hands them to the page itself; there is no `fonts/` folder next to the scripts any more.
- `resources/models/` the super-resolution models (`EDSR_x4.pb`, `FSRCNN_x4.pb`) used by `sr.py` / vectorize.py.
  They are not committed: download them from the OpenCV dnn_superres model repos (Apache-2.0),
  `https://raw.githubusercontent.com/Saafke/EDSR_Tensorflow/master/models/EDSR_x4.pb` and
  `https://raw.githubusercontent.com/Saafke/FSRCNN_Tensorflow/master/models/FSRCNN_x4.pb`.
- `logo/srenv/` the opencv-contrib venv for `sr.py` (made by `setup.sh`, gitignored).

## Setup (once per machine or session)

```bash
logo/setup.sh     # npm i (three, gltf-transform, playwright) + pip (vtracer, cairosvg, scikit-learn, opencv) + SR venv
```

It works from any folder and warns when a model is missing from `resources/models/`.

## Vectorize a low-res logo

```bash
python3 logo/vectorize.py logo.png out/ Acme_A --palette "#000000,#F8BB01,#FFFFFF"
```

- `--palette`: the brand hexes from the school's `colors.txt`. Thin outlines in those colours survive the trace,
  and the colours snap to the exact brand values. Without it, colours are found automatically.
- `--colors N`: forces the number of flat colours.
- `--bg auto|none|#hex`: removes a solid background. Only background connected to the edge is removed, so a white
  shape inside the logo stays.
- `--detail 1.5`: keeps smaller details; `0.7` smooths more.
- Logos under 700 px are AI-upscaled ×4 first (EDSR from `resources/models/`, run in `logo/srenv`) before tracing;
  without the venv or the model it falls back to a Lanczos upscale.
- **Check the score:** silhouette IoU ≥ 0.98 and colour error ≤ 20/255 means it's good to use. Below that, open
  `*_vector_check.png`: red marks shape the vector missed, blue marks shape it added.
- A trace is a redraw, not the school's master file. If an official vector exists (a brand kit, BSN Sports, the
  school's site), use that instead.

## Make a 3D logo

```bash
python3 logo/render3d.py logo.svg out/ Acme_Hawk --bg 112233      # or --bg '#112233' (quote it: # starts a shell comment)
python3 logo/render3d.py logo.svg out/ ACME --still-only             # stills + GLB only (a few seconds)
python3 logo/render3d.py logo.svg out/ ACME --anim spin              # full 360° turn instead of the swing
```

- `--depth 0.03`: extrusion as a fraction of the logo width (0.02 subtle, 0.05 chunky).
- `--bg`: background colour for the .mp4 only, with or without the `#`. Default: the profile's primary colour. Every PNG
  and the .mov keep a transparent background.
- `--hero "0.10,-0.30"`: tilt and turn of the hero still, in radians.
- `--fps 60 --spin-seconds 4`: settings for the loop.
- `--drop-bg`: leave out a filled rectangle that covers the whole SVG canvas (an export background); render3d.py prints
  a line when it drops one. Off by default, because a full-bleed plate can be part of the logo (a square badge, or any
  logo whose silhouette fills its canvas after vectorize.py: the bottom layer is the whole silhouette).
- A full render with the loop takes about a minute for a simple mark, several minutes for a detailed traced logo. Stills take seconds.

## File naming
`<Owner>_<Logo>_3D_Hero_4K.png`, `_3D_Front_4K.png`, `_3D_Swing_Alpha.mov`, `_3D_Swing.mp4`, `_3D.glb`.
Renders go in a `3D/` folder next to the source SVG (or wherever `--out` points). Traced vectors sit next to the source logo as
`logo-vector.svg` and `logo-vector-4000px.png`.

## Redraw a logo that can't be traced (3D mockups, photos, embossed renders)
`redraw.py` gives clean shapes, strokes that extrude, and real-font text fitted to a measured box. `fontmatch.py`
finds the closest font (`fontmatch.py <image> "<TEXT>" x0,y0,x1,y1 resources/fonts`). See the logo-vectorize skill,
"Redraw mode", and the `redraw.py` docstring for a per-logo script.

## Animated logo graphics, `motion.py`
```bash
python3 logo/motion.py logo.svg out/ ACME intro
python3 logo/motion.py logo.svg out/ ACME outro --text1 "THANKS FOR WATCHING" --text2 "ACME TV · YOUTUBE · FACEBOOK"
python3 logo/motion.py logo.svg out/ ACME bug                  # writes bug_in, bug_loop and bug_out
python3 logo/motion.py logo.svg out/ ACME stinger              # prints the cut point
python3 logo/motion.py logo.svg out/ ACME presented --sponsor "sponsor_logo.png"
python3 logo/motion.py logo.svg out/ ACME intro --frames 0.5,1.5,3   # quick stills only
python3 logo/motion.py logo.svg out/ ACME stinger --bg '#112233'     # preview .mp4 background, '#' optional
python3 logo/motion.py logo.svg out/ ACME slam --place 0.5,0.44,0.62,0.42 --dur 3.4 --fps 29.97002997 --png-seq  # slam-in as a PNG sequence for compositing
python3 logo/motion.py logo.svg out/ ACME lockup --text1 "ACME TV" --text2 "GAME OF THE WEEK" --text3 "FRIDAYS | 7PM | LIVE" --plate set.png --fps 29.97002997  # camera settles onto a lit sign
python3 logo/motion.py logo.svg out/ ACME writeon --text1 "WELCOME HOME"   # L1 write-on; prints the hit time for qa --cuts
python3 logo/motion.py logo.svg out/ ACME morph            # L3 (3.6 s)   · pixelbuild L9 (3.4 s) · linebuild L2 (7.5 s)
python3 logo/motion.py logo.svg out/ ACME echo             # L4 outline stinger, prints the cut point
python3 logo/motion.py logo.svg out/ ACME lightstreak      # L10 light with a long trail writes the logo
python3 logo/motion.py logo/stories/placeholder_story.svg out/ STORY lightpaint --finish dark   # S1, one <g> a scene
python3 logo/motion.py logo.svg out/ ACME writeon --finish dark [--mockup laptop]   # F1 finish on any template
```
Each run writes `<Name>_<template>_Alpha.mov` (ProRes 4444 with alpha, 1080p60) and an `.mp4` preview on `--bg`
(default: the profile's primary colour). Panel and text colours, the accent and the fonts come from the profile
(`brand.colors`, `brand.fonts` in `resources/fonts/`); `--accent` overrides the outro's second line only.
Every profile font must load in the page: if one does not, motion.py stops with an error instead of drawing the text in
a fallback font. Use `--profile <name>` to render for another organisation.
