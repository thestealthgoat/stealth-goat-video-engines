# Technique to tool map

What a reference does on screen and the engine tool that does it. Log a covered idea against its tool (for example
"matches `stage3d.py orbit`"). Check a tool's options before promising a flag:
each prints them with `-h` / `--help` (`engine/cutout.py`, `engine/flipbook.py`, `engine/vertical.py` and
`engine/fcp7xml.py` print their docstring). For `logo/motion.py`, also read the file's header
(`sed -n 1,30p logo/motion.py`): its `-h` lists the flags but not the templates.

`--profile <name>` and `--frames t1,t2` (stills only, for a quick look): `logo/motion.py`, `stage3d.py`,
`explain.py`, `matte.py`, `behind.py`, `quote.py`, `progressbar.py`, `statcard.py`, `fxpack.py`, `sketch.py`,
`beforeafter.py`, `routemap.py`, `hopwords.py` take both. `captions.py`, `talkedit.py`, `vertical.py`,
`web/build.py` and `flipbook.py` take `--profile` but no `--frames`; `sourcecard.py` and `cutout.py` take neither
(cutout accepts `--profile` and ignores it).

Commands run from the engine folder: `cd "$VIDEO_ENGINE"`. `clip.mp4`, `logo.svg`, `talk.mp4` stand for the user's
own files.

## Logo and title motion (`logo/motion.py`)

`python3 logo/motion.py <logo.svg> <out_dir> <Name> <template> [--text1 ..] [--frames 0.5,1.2] --profile demo`
writes `<Name>_<template>_Alpha.mov` (ProRes 4444) and a preview `.mp4`.

| Seen in the reference | Template |
|---|---|
| Logo slams in from oversize and lands hard | `slam` (`--place cx,cy,bw,bh`, `--dur`) |
| Logo intro / end card with two lines | `intro`, `outro` (`--text1`, `--text2`) |
| Corner bug in, loop, out | `bug` (writes bug_in, bug_loop, bug_out) |
| Full-frame wipe between shots | `stinger` (cut point printed) |
| "Presented by" lower third with a sponsor | `presented` (`--text1`, `--sponsor img.png`) |
| Lit sign with a flicker-on, camera settles on it | `lockup` (`--text1/2/3`, `--plate`) |
| Glowing pen traces the logo, fills land | `writeon` (`--write SECONDS`) |
| Outline pieces converge, then a construction grid | `linebuild` |
| Circles float in and morph into the mark | `morph` |
| Outline echo stinger | `echo` |
| Kinetic word swaps ("___ is next") | `swap` (`--text1 "___ is next" --text2 "a\|b\|c"`) |
| Mark shatters and re-forms as a new mark | `shatter` (`--svg2` or `--text2`) |
| Brand sheet: logo, colors, type, a stat counting up | `brandgrid` |
| Dot grid springs out into the logo | `pixelbuild` |
| Light streak across the mark | `lightstreak` |
| One light draws scene after scene | `lightpaint` (top-level `<g>` groups are scenes) |
| Dark, cinematic finish (bloom, reflective floor, grain) | any template `--finish dark` (`--mockup laptop`) |

Related: `logo/render3d.py` (3D extruded logo stills, swing or spin loop, `.glb`), `logo/vectorize.py` (raster logo
to clean SVG first), `engine/stage3d.py extrude` (camera flies past 3D letters).

## 3D scenes (`engine/stage3d.py`)

`python3 engine/stage3d.py <scene> <out_dir> <Name> [options] --profile demo`; `--alpha` adds a transparent
`_Alpha.mov`. Every scene uses a warm key, a cool rim and contact shadows, and moves on springs only.

| Seen in the reference | Scene |
|---|---|
| Bars, count-up score cards, a point cloud, camera always drifting | `data --data file.json` |
| Glass cards orbit a person, passing in front and behind | `orbit --cards "A\|B\|C" --matte DIR/<name>_matte.json` |
| 3D stack of real screenshots | `stack --shots a.png,b.png` or `--url <page>` |
| Title cards swapped behind light bursts on a mesh gradient | `burst --lines "A\|B\|C"` |
| Two badges fly in and clash, sparks, shake | `badge --text1 .. --text2 ..` |
| Settings panel, toggles flip on | `toggle --labels "A\|B\|C"` |
| Glossy 3D icon props | `props --icons check,star,heart,bolt,play,plus,pin,chat` |
| Brand glow, phone, panels, toast, tagline | `reveal --shots .. --toast .. --tagline ..` |
| Mascot hops platform to platform on the words | `hop --text ".." [--character art.png]` |
| Flythrough over a tilted app screenshot with focus boxes | `fly --shots app.png --focus focus.json` |
| Camera flies past extruded 3D type and lands on it | `extrude --text "WORD"` or `--svg mark.svg` |

Worked still (fresh clone):
`python3 engine/stage3d.py extrude out/refs/proof Proof --text "ACME" --frames 2.0 --profile demo`

## Explainers (`engine/explain.py` + `engine/storyboard.py`)

A storyboard JSON holds one beat per spoken line with a new visual every 1-2 s; `explain.py` draws it on one
continuous canvas with springs. `storyboard.py pace | retime | check | board` times and checks it.

| Seen in the reference | Element or tool |
|---|---|
| A new visual every 1-2 s, captions snapped to the voice | storyboard beats + `retime --vo vo.wav` |
| Words land as they are said, one keyword boxed | kinetic captions, `engine/captions.py` |
| Diagram that builds node by node with pulses traveling | `flow` element (nodes, edges, pulses) |
| Live numbers, bars, plots, waves, knobs | `readout`, `bars`, `plot`, `wave`, `knob` elements |
| A real web page slides in, the quoted phrase gets a highlight box | `engine/sourcecard.py <url> "<phrase>" out.png` + `image` element |
| Oscilloscope / Lissajous figures, spectrum from real audio | `scope` element (storyboard `"data"`) |
| Powers-of-ten zoom through real sizes | `scale` element |
| Music bed that drops on the payoff | `engine/musicbed.py out.wav --dur 60 --drop 41.4` |

Full worked explainer: `examples/explain/lissajous/` (`make.py`, `storyboard.json`, `VO_SCRIPT.md`), a
Lissajous-harmony explainer. Read it before planning an explainer idea.

## People: mattes, cutouts, cards

Person mattes and cutouts use BiRefNet through rembg, locally (models folder: `engine/models.py`).

| Seen in the reference | Tool |
|---|---|
| Per-frame cutout of the person from video | `engine/matte.py clip.mp4 --out DIR [--name N]` (writes `N_matte.json`, `N_matte_Alpha.mov`; the JSON is what `--matte` takes) |
| Big word behind the person's head | `engine/behind.py clip.mp4 --out DIR --text "WORD"` |
| Words behind the speaker picked from what they say | `engine/behind.py clip.mp4 --out DIR --auto words.json` |
| Speaker cut out beside a big serif pull-quote | `engine/quote.py --text ".." --by "Jane Doe" --matte DIR/<name>_matte.json --out DIR` |
| Progress bar with the speaker's face riding it, chapters | `engine/progressbar.py talk.mp4 --out DIR --face face.png --chapters ch.json` |
| Stats lower third with a cutout and one big number | `engine/statcard.py stats.json DIR` (`--ae` also writes an After Effects comp) |
| Still headshot cutout | `engine/cutout.py in.jpg out.png` |

Matting is slow (seconds per 1080p frame on a CPU): run one in the background, one heavy job at a time.

## Talking head and captions

| Seen in the reference | Tool |
|---|---|
| Tight jump-cut talk, fillers and pauses gone, punch-ins on emphasis | `engine/talkedit.py talk.mp4 --out DIR` |
| Full-frame title card while the talk carries on | talkedit cutaway cards |
| Small card pops up on a keyword, numbers count up | talkedit pop-up cards |
| Word-by-word captions in a box | `engine/captions.py clip.mp4 --out DIR` |
| 16:9 piece reframed for 9:16 with a blurred fill | `engine/vertical.py in.mp4 out.mp4` |

Plan only, no render: `python3 engine/talkedit.py talk.mp4 --out DIR --profile demo --plan-only`.

## Edits cut to music

| Seen in the reference | Tool |
|---|---|
| Cuts on beats and downbeats, the hero shot on the drop | `engine/beatmap.py` bar map + `engine/beatsnap.py edit.json music.mp3` |
| Flash cuts, zoom punch with radial blur, RGB split, speed ramp, whip pan, color pop, kinetic text | `engine/fxpack.py plan.json --out DIR` (each effect must have a music event and a reason in the picture) |
| Build, impact, sub drop | `engine/sfx_build.py out.wav --bpm 120 --beats 8 --tail 2.2` |
| Burst photos as fast stop-motion | `engine/flipbook.py plan.json frames_dir out.mp4` |
| Pencil sketch draws itself, then the real shot paints in | `engine/sketch.py clip.mp4 --out DIR` |
| Before / after divider sweep | `engine/beforeafter.py --before a.mp4 --after b.mp4 --out DIR` |
| Route draws on a map, camera follows | `engine/routemap.py route.gpx --out DIR` (offline Natural Earth map by default; `--map osm` for OpenStreetMap roads, with the credit on screen) |
| A character bounces word to word through lyrics | `engine/hopwords.py --text ".." --out DIR` |

Plan only, no render: `python3 engine/fxpack.py plan.json --out DIR --plan-only --profile demo`.

## Websites (`web/build.py`)

One `site.json` plus a profile makes a static site: a hero template plus the section kit (stats, features,
process, area, gallery, form, faq, cta, text), with the compliance checklist built in. UI motion uses the `ui` /
`uiExit` springs only and switches off for reduced motion.

| Seen in the reference | Template |
|---|---|
| Pinned frame scrubbed by scroll through an image sequence, one caption per stage | `w1` scroll-built story |
| Small 3D isometric world, camera moves scene to scene on scroll | `w2` |
| Scroll flies a camera over an aerial map, stopping on places | `w3` drone flyover |
| Cinematic build sequence scrubbed by scroll, editorial headlines, ends on the money shot | `w4` service business |
| Dark stage, glass orbs and shards refracting light bars, big editorial type | `w5` glass showcase |

Worked examples (demo profile):

```bash
python3 web/build.py examples/sites/demo-world/site.json --out out/sites/demo-world --profile demo     # the w2 template
python3 web/build.py examples/sites/demo-studio/site.json --out out/sites/demo-studio --profile demo   # the w5 template
python3 web/compliance.py out/sites/demo-world --site examples/sites/demo-world/site.json              # the gate
python3 web/preview.py out/sites/demo-world --out out/sites/demo-world_preview                         # screenshots + scroll video
```

## Measuring and gates (used on references too)

| Need | Tool |
|---|---|
| Contact sheet of any span | `engine/sheet.py clip.mp4 out.jpg t0 t1 --n 12` |
| Cuts, flashes, motion events, palette per shot | `engine/measure.py probe` |
| Position / scale / rotation / opacity of one element over time | `engine/measure.py track` |
| Fit springs to a measured move, nearest preset | `engine/measure.py fit` |
| Side-by-side of the reference and a rebuild, per-frame SSIM | `engine/measure.py compare` |
| Dead stretches and stutters | `engine/motion_check.py clip.mp4 --sheet out.jpg` |
| Hook, freshness, loudness, shot table | `engine/qa.py clip.mp4 --kind edit|motion|explainer|loop` |

## Spring presets (for naming measured motion)

| Preset | Settles | Overshoot | Typical use |
|---|---|---|---|
| `snappy` | 0.36 s | 2.8% | lower thirds, cards, panels |
| `bouncy` | 0.70 s | 23% | playful entrances, logo lands (one hero moment) |
| `slam` | 0.67 s | 37% | hard hits |
| `smooth` | 0.62 s | 0% | fades, camera pushes, text that must not wobble |
| `gentle` | 0.69 s | 0.2% | slow drifts |
| `ui` / `uiExit` | 0.20 / 0.16 s | 0% | website and app UI |

`python3 engine/spring.py` prints these numbers from the code.
