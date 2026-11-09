# Technique to tool map

What a reference does on screen, the engine tool that does it, and the engine ID the tool's own `--help` uses.
Log a covered idea against its ID (for example "matches O4"). Check a tool's options before promising a flag:
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

| Seen in the reference | Template | ID |
|---|---|---|
| Logo slams in from oversize and lands hard | `slam` (`--place cx,cy,bw,bh`, `--dur`) | |
| Logo intro / end card with two lines | `intro`, `outro` (`--text1`, `--text2`) | |
| Corner bug in, loop, out | `bug` (writes bug_in, bug_loop, bug_out) | |
| Full-frame wipe between shots | `stinger` (cut point printed) | |
| "Presented by" lower third with a sponsor | `presented` (`--text1`, `--sponsor img.png`) | |
| Lit sign with a flicker-on, camera settles on it | `lockup` (`--text1/2/3`, `--plate`) | |
| Glowing pen traces the logo, fills land | `writeon` (`--write SECONDS`) | L1 |
| Outline pieces converge, then a construction grid | `linebuild` | L2 |
| Circles float in and morph into the mark | `morph` | L3 |
| Outline echo stinger | `echo` | L4 |
| Kinetic word swaps ("___ is next") | `swap` (`--text1 "___ is next" --text2 "a\|b\|c"`) | L5 |
| Mark shatters and re-forms as a new mark | `shatter` (`--svg2` or `--text2`) | L7 |
| Brand sheet: logo, colours, type, a stat counting up | `brandgrid` | L8 |
| Dot grid springs out into the logo | `pixelbuild` | L9 |
| Light streak across the mark | `lightstreak` | L10 |
| One light draws scene after scene | `lightpaint` (top-level `<g>` groups are scenes) | S1 |
| Dark, cinematic finish (bloom, reflective floor, grain) | any template `--finish dark` (`--mockup laptop`) | F1 |

Related: `logo/render3d.py` (3D extruded logo stills, swing or spin loop, `.glb`), `logo/vectorize.py` (raster logo
to clean SVG first), `engine/stage3d.py extrude` (camera flies past 3D letters, L6).

## 3D scenes (`engine/stage3d.py`)

`python3 engine/stage3d.py <scene> <out_dir> <Name> [options] --profile demo`; `--alpha` adds a transparent
`_Alpha.mov`. Every scene uses a warm key, cool rim and contact shadows (H7) and springs only.

| Seen in the reference | Scene | ID |
|---|---|---|
| Bars, count-up score cards, a point cloud, camera always drifting | `data --data file.json` | E4 |
| Glass cards orbit a person, passing in front and behind | `orbit --cards "A\|B\|C" --matte DIR/<name>_matte.json` | O4 |
| 3D stack of real screenshots | `stack --shots a.png,b.png` or `--url <page>` | P1 |
| Title cards swapped behind light bursts on a mesh gradient | `burst --lines "A\|B\|C"` | P2 |
| Two badges fly in and clash, sparks, shake | `badge --text1 .. --text2 ..` | P3 |
| Settings panel, toggles flip on | `toggle --labels "A\|B\|C"` | P3 |
| Glossy 3D icon props | `props --icons check,star,heart,bolt,play,plus,pin,chat` | P4 |
| Brand glow, phone, panels, toast, tagline | `reveal --shots .. --toast .. --tagline ..` | P5 |
| Mascot hops platform to platform on the words | `hop --text ".." [--character art.png]` | C2 |
| Flythrough over a tilted app screenshot with focus boxes | `fly --shots app.png --focus focus.json` | C3 |
| Camera flies past extruded 3D type and lands on it | `extrude --text "WORD"` or `--svg mark.svg` | L6 |

Worked still (fresh clone):
`python3 engine/stage3d.py extrude out/refs/proof Proof --text "ACME" --frames 2.0 --profile demo`

## Explainers (`engine/explain.py` + `engine/storyboard.py`)

A storyboard JSON holds one beat per spoken line with a new visual every 1-2 s; `explain.py` draws it on one
continuous canvas with springs. `storyboard.py pace | retime | check | board` times and checks it.

| Seen in the reference | Element or tool | ID |
|---|---|---|
| A new visual every 1-2 s, captions snapped to the voice | storyboard beats + `retime --vo vo.wav` | E2 |
| Words land as they are said, one keyword boxed | kinetic captions, `engine/captions.py` | E1 |
| Diagram that builds node by node with pulses travelling | `flow` element (nodes, edges, pulses) | E2 |
| Live numbers, bars, plots, waves, knobs | `readout`, `bars`, `plot`, `wave`, `knob` elements | E2 |
| A real web page slides in, the quoted phrase gets a highlight box | `engine/sourcecard.py <url> "<phrase>" out.png` + `image` element | E3 |
| Oscilloscope / Lissajous figures, spectrum from real audio | `scope` element (storyboard `"data"`) | E7/E8 |
| Powers-of-ten zoom through real sizes | `scale` element | E9 |
| Music bed that drops on the payoff | `engine/musicbed.py out.wav --dur 60 --drop 41.4` | |

Full worked explainer: `examples/explain/lissajous/` (`make.py`, `storyboard.json`, `VO_SCRIPT.md`), a
Lissajous-harmony explainer. Read it before planning an explainer idea.

## People: mattes, cutouts, cards

Person mattes and cutouts use BiRefNet through rembg, locally (models folder: `engine/models.py`).

| Seen in the reference | Tool | ID |
|---|---|---|
| Per-frame cutout of the person from video | `engine/matte.py clip.mp4 --out DIR [--name N]` (writes `N_matte.json`, `N_matte_Alpha.mov`; the JSON is what `--matte` takes) | O2 |
| Big word behind the person's head | `engine/behind.py clip.mp4 --out DIR --text "WORD"` | O3 |
| Words behind the speaker picked from what they say | `engine/behind.py clip.mp4 --out DIR --auto words.json` | T2 |
| Speaker cut out beside a big serif pull-quote | `engine/quote.py --text ".." --by "Jane Doe" --matte DIR/<name>_matte.json --out DIR` | E5 |
| Progress bar with the speaker's face riding it, chapters | `engine/progressbar.py talk.mp4 --out DIR --face face.png --chapters ch.json` | O5 |
| Stats lower third with a cutout and one big number | `engine/statcard.py stats.json DIR` (`--ae` also writes an After Effects comp) | O1, X1 |
| Still headshot cutout | `engine/cutout.py in.jpg out.png` | |

Matting is slow (seconds per 1080p frame on a CPU): run one in the background, one heavy job at a time.

## Talking head and captions

| Seen in the reference | Tool | ID |
|---|---|---|
| Tight jump-cut talk, fillers and pauses gone, punch-ins on emphasis | `engine/talkedit.py talk.mp4 --out DIR` | T1 |
| Full-frame title card while the talk carries on | talkedit cutaway cards | T4 |
| Small card pops up on a keyword, numbers count up | talkedit pop-up cards | T3 |
| Word-by-word captions in a box | `engine/captions.py clip.mp4 --out DIR` | E1 |
| 16:9 piece reframed for 9:16 with a blurred fill | `engine/vertical.py in.mp4 out.mp4` | |

Plan only, no render: `python3 engine/talkedit.py talk.mp4 --out DIR --profile demo --plan-only`.

## Edits cut to music

| Seen in the reference | Tool | ID |
|---|---|---|
| Cuts on beats and downbeats, the hero shot on the drop | `engine/beatmap.py` bar map + `engine/beatsnap.py edit.json music.mp3` | H1 |
| Flash cuts, zoom punch with radial blur, RGB split, speed ramp, whip pan, colour pop, kinetic text | `engine/fxpack.py plan.json --out DIR` (each effect must have a music event and a reason in the picture: H3) | X2 |
| Build, impact, sub drop | `engine/sfx_build.py out.wav --bpm 120 --beats 8 --tail 2.2` | |
| Burst photos as fast stop-motion | `engine/flipbook.py plan.json frames_dir out.mp4` | |
| Pencil sketch draws itself, then the real shot paints in | `engine/sketch.py clip.mp4 --out DIR` | T5 |
| Before / after divider sweep | `engine/beforeafter.py --before a.mp4 --after b.mp4 --out DIR` | T6 |
| Route draws on a map, camera follows | `engine/routemap.py route.gpx --out DIR` (offline Natural Earth map by default; `--map osm` for OpenStreetMap roads, with the credit on screen) | O6 |
| A character bounces word to word through lyrics | `engine/hopwords.py --text ".." --out DIR` | C1 |

Plan only, no render: `python3 engine/fxpack.py plan.json --out DIR --plan-only --profile demo`.

## Websites (`web/build.py`)

One `site.json` plus a profile makes a static site: a hero template plus the section kit (stats, features,
process, area, gallery, form, faq, cta, text), with the compliance checklist built in. UI motion uses the `ui` /
`uiExit` springs only and switches off for reduced motion.

| Seen in the reference | Template | ID |
|---|---|---|
| Pinned frame scrubbed by scroll through an image sequence, one caption per stage | `w1` scroll-built story | W1 |
| Small 3D isometric world, camera moves scene to scene on scroll | `w2` | W2 |
| Scroll flies a camera over an aerial map, stopping on places | `w3` drone flyover | W3 |
| Cinematic build sequence scrubbed by scroll, editorial headlines, ends on the money shot | `w4` service business | W4 |
| Dark stage, glass orbs and shards refracting light bars, big editorial type | `w5` glass showcase | W5 |

Worked examples (demo profile):

```bash
python3 web/build.py examples/sites/demo-world/site.json --out out/sites/demo-world --profile demo     # W2
python3 web/build.py examples/sites/demo-studio/site.json --out out/sites/demo-studio --profile demo   # W5
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
