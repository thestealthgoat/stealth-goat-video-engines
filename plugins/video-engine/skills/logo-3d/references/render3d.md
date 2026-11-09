# render3d.py reference

`python3 logo/render3d.py <logo.svg> <out_dir> <name> [options]`, run from the engine folder. It serves
`logo/render.html` on a local port and drives it in headless Chromium (Playwright, software WebGL), then encodes with
ffmpeg and compresses the GLB with `logo/node_modules/.bin/gltf-transform`.

## Options

| Option | Default | What it does |
|---|---|---|
| `svg` `out` `name` | required | input SVG, output folder (created), file name prefix |
| `--depth` | `0.03` | extrusion as a fraction of the logo's longest side. `0.02` thin type and lettering, `0.05` chunky single mark |
| `--fill` | `0.78` | share of the frame the logo's widest side fills (the fit holds at any rotation). Lower it if the swing clips |
| `--hero` | `"0.10,-0.30"` | tilt (rotX) and turn (rotY) of the hero still, in radians. The front still is fixed at a slight tilt (`0.06,0`) |
| `--still-only` | off | hero + front PNGs and the GLB only; no loop, no profile needed |
| `--anim` | `swing` | `swing`: seamless sway, rotY = 0.44 rad x sin, plus a small nod; never shows the back. `spin`: full 360 degree turn with a small tilt |
| `--spin-seconds` | `4` | loop length in seconds (both animations) |
| `--fps` | `60` | loop frame rate (integer) |
| `--bg` | profile primary | MP4 background: `112233`, `'#112233'`, `0x112233`, or an ffmpeg colour name such as `black`. PNGs and the .mov stay transparent |
| `--drop-bg` | off | leave out a filled, hole-free rectangle that covers the whole canvas (an export background); prints what it dropped |
| `--profile` | `$VIDEO_PROFILE`, then `local.json` | profile name or path to a `profile.json`; used for the default `--bg` |

## Outputs

| File | Format |
|---|---|
| `<name>_3D_Hero_4K.png` | 3840x2160 RGBA, angled by `--hero` |
| `<name>_3D_Front_4K.png` | 3840x2160 RGBA, straight on |
| `<name>_3D.glb` | Draco-compressed glTF binary. If compression fails the raw GLB is kept and a line says so |
| `<name>_3D_Swing_Alpha.mov` (`_Spin_` with `--anim spin`) | 1920x1080, `--fps`, ProRes 4444 with alpha (ffprobe reports `yuva444p12le`) |
| `<name>_3D_Swing.mp4` (`_Spin_`) | 1920x1080, `--fps`, H.264 yuv420p, CRF 16, faststart, on `--bg` |

The loop is seamless: frame `n` is the start again, so it can be set to loop in any player or switcher.

## How the look is made (`logo/render.html`)

- Only filled paths are extruded. Paths with `fill="none"`, `transparent` or `fill-opacity="0"` are skipped.
- Paint order is kept. A new layer starts each time the fill colour changes from one path to the next, and each
  layer sits a small step in front of the one before (traced logos stack whole colour layers, so they come out
  raised).
- Neutral greys (saturation under 0.08, lightness 0.25 to 0.85) get a metal material; other colours get a glossy
  clearcoat. Side walls are a darker shade of the face colour.
- Tone mapping is neutral, so brand colours stay close to their hex values on the face.

## Timing and load

- Stills only: a few seconds for simple marks, about 30 s for detailed traced logos.
- Full render (240 frames at 1080p for the default 4 s at 60 fps, rendered in software): under a minute for simple
  marks (the three-shape worked example renders a 60-frame loop in about 13 s), several minutes for detailed traced
  logos with hundreds of paths.
- One heavy render at a time. Batch logos sequentially in one background shell loop.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `paths 0` or parts missing | the SVG uses strokes or `fill="none"`; convert strokes to filled paths, or run logo-vectorize on a PNG export |
| one big rectangle behind the logo | export background: rerun with `--drop-bg` |
| a coloured part disappears in `check.png` | its colour equals the profile primary used by `preview.py`; composite on a contrasting colour (SKILL.md step 2) |
| letters look swollen | lower `--depth` to `0.02` |
| logo looks like a flat sticker | raise `--depth` to `0.04`-`0.05`, or a stronger `--hero` such as `"0.14,-0.40"` |
| edges clip during the swing | lower `--fill` to `0.70` |
| text, gradients or images missing | the renderer extrudes vector fills only: convert text to outlines; replace gradients with flat fills (a gradient fill comes out white); embedded bitmaps are ignored, so vectorize them first |
| `glb optimize failed, kept raw` | `logo/node_modules` missing or stale: rerun `logo/setup.sh` |
| Playwright or Chromium errors | `python3 -m playwright install chromium`, or rerun `logo/setup.sh` |
| qa.py `spec` FAIL on frame rate | pass `--fps 60` (or the `--fps` you rendered at) |
