# logo/motion.py templates

Usage (from the engine folder):

```
python3 logo/motion.py <logo.svg> <out_dir> <Name> <template> [--text1 ..] [--text2 ..] [--text3 ..] [--svg2 new.svg]
       [--sponsor img.png] [--plate img.png] [--fps 60] [--size 1920x1080] [--bg 112233] [--accent "#E04050"]
       [--depth 0.03] [--frames t1,t2] [--dur S] [--place cx,cy,bw,bh] [--write S] [--finish dark] [--mockup laptop]
       [--png-seq] [--profile NAME]
```

Run `python3 logo/motion.py --help` for the current flag list. Lengths below are the defaults at 1080p60.
"3D" templates extrude the SVG's filled paths; "2D" templates trace the SVG's outlines in the browser (any shape
type, any transform) and land the SVG's own fills as a hit.

## Templates

| Template | Kind | Length | What it does | Text and options |
|---|---|---|---|---|
| `intro` | 3D | 4 s | Logo flies in from the camera with a turn, lands on a hit at 0.5 s, pushes in slowly under a light sweep (1.5 s), settles at about 2.25 s and holds the last frame | `--text1` optional line under the logo |
| `outro` | 3D | 6 s | End card: logo drops in and bounces at about 0.45 s, two lines slide up, sweep, gentle sway, all fade out by 6 s | `--text1` big line (head font), `--text2` small line in the accent (`--accent` overrides its colour) |
| `bug` | 3D | 1 s in + 6 s loop + 0.8 s out | Corner logo bottom-right inside the safe area; writes three clips `bug_in`, `bug_loop` (seamless), `bug_out` for a switcher | none |
| `stinger` | 3D | 1.2 s | Primary-colour panel with accent edges wipes the full frame, logo hits centre; frame fully covered at the **cut, 0.55 s (printed)** | none |
| `presented` | 3D | 5 s | Lower-third bar in the primary colour: the logo + "PRESENTED BY" + the sponsor's logo, wipes off by 4.9 s | `--text1` (default PRESENTED BY), `--sponsor path.png` (use the sponsor's light version on a dark bar) |
| `slam` | 3D | 2 s (`--dur`) | Logo flies in from behind the camera with a turn, lands with a bounce at 0.42 s, light sweep, slow drift. Made for compositing | `--place cx,cy,bw,bh` landing box; `--png-seq` |
| `lockup` | 2D sign | 4.17 s | Camera tilts down and settles onto a lit sign; three lines flicker on, with motion blur and grain | `--text1` small top line (default the profile's display name), `--text2` outlined headline in the accent, `--text3` spaced subline, `--plate still.png` background the camera moves over (else a drawn sign). Always pass all three lines: the defaults are placeholders |
| `writeon` | 2D | 4.5 s (`--dur`) | Signature write-on: one glowing pen traces every outline (sparks in the accent), then the fills land as a hit (spring pop, accent bloom, spark burst) at 0.86 x the pen time, two light sweeps, slow push | `--text1` optional line; `--write S` pen time (default 48% of the length, at most 2.2 s); `--place` |
| `morph` | 2D | 3.6 s (`--dur`) | One circle per part of the logo (letters, counters) floats in, drifts onto its part and morphs point by point into the real outline; fills land as a hit (pop, bloom, two sweeps), slow push | `--text1` optional line |
| `pixelbuild` | 2D | 3.4 s (`--dur`) | The logo sampled onto a dot grid; dots spring out from the centre (staggered by distance), glow as they land, then the clean mark resolves over them | `--text1` optional line |
| `linebuild` | 2D | 7.5 s | Outline pieces race in from off-frame and lock onto the logo, fills land, then three mockups: a construction grid draws on, the mark as a profile-page avatar, the mark pressed into fabric | `--text1` the profile-page name (default the profile's display name) |
| `echo` | 2D | 1.2 s | Outline stinger: echoes of the outline ripple out, a primary-colour panel swells from the mark and covers the frame at the **cut, 0.55 s (printed)**, then shrinks back and clears | none |
| `lightstreak` | 2D | 3.5 s (`--dur`) | A point of light with a long fading trail writes the outline (additive bloom), light streaks race across like timeline tracks, fills land as a hit | `--text1` optional line |
| `lightpaint` | 2D story | 2.4 s a scene + 0.8 s | Each top-level `<g>` of the SVG is a scene, laid side by side; one light draws them in turn, the camera follows, trails stay; ignite hit at 0.08 s (printed). Use with `--finish dark` | none. Sample art: `logo/stories/placeholder_story.svg` (in the engine) or this skill's `assets/story_example.svg` |
| `swap` | text | 0.9 s a word + 1.5 s | Kinetic word swaps: letters rise into the slot one by one, the old word leaves upward, the slot springs to the new width, the last word lands in the accent with an underline (hit printed). The logo file is still required but not drawn | `--text1 "___ is next"` (the line; `___` marks the slot, else the slot follows the line), `--text2 "a\|b\|c"` the words in turn |
| `shatter` | 2D | 3.2 s | The mark breaks into shards on a kick, they turn over at their farthest as pieces of the new mark and spring back together; glow on the re-form (hit printed). For rebrands | `--svg2 new.svg` the new mark, else `--text2` set in the head font (default the profile's display name) |
| `brandgrid` | 2D | 5 s | Brand-system grid: logo panel, primary and accent swatches with their hex, a type specimen, a stat counting up; panels spring in one after another (hit printed) | `--text1` stat label (default THIS YEAR), `--text2` stat value, e.g. "1,284" (only the first number counts up; "Est. 1998", "4.9/5" keep their text) |

3D type flythrough (extruded letters, camera skims past and lands on the lockup) is a different tool:
`python3 engine/stage3d.py extrude <out> <Name> --text "WORD"` (or `--svg mark.svg`) `--profile <name>`.

## Options that apply to every template

| Option | Effect |
|---|---|
| `--frames 0.5,1.5,3` | Stills only (transparent PNGs `<Name>_<template>_t0.50.png` ...). Use before every render |
| `--fps`, `--size` | Frame rate (default 60) and size (default 1920x1080) |
| `--bg` | Background of the .mp4 preview only (default the profile's primary colour); the .mov keeps alpha |
| `--depth` | 3D extrusion depth as a fraction of the logo width (default 0.03) |
| `--dur` | Overrides the length (most useful on `slam`, `writeon`, `morph`, `pixelbuild`, `lightstreak`) |
| `--png-seq` | Writes `<Name>_<template>_seq/f00000.png ...` instead of encoding a movie |
| `--finish dark` | Cinematic finish: dark radial stage, a reflective floor mirrored at the content's lowest point (blurred, fading), bloom under the content (the logo stays sharp), film grain, vignette. Output is opaque |
| `--mockup laptop` | With `--finish`: the finished frame on a laptop screen with a glass reflection |
| `--profile` | Colours (`brand.colors.primary`, `accent`, `text`) and fonts (`brand.fonts.head`, `body`, `body_semibold`) |

Profile block for the finish (any key; colours may be hex or profile colour names):

```json
"finish": {"dark": {"bg": "#05070A", "bg2": "#161B22", "bloom": 0.5, "floor": 0.3, "dof": 6, "grain": 0.3, "vignette": 0.55}}
```

## QA flags per template

Run `python3 engine/qa.py <Name>_<template>_Alpha.mov --profile <name> --fps 60 ...` (drop `--fps 60` for a render
made at the delivery rate). `<hit>` is the hit time motion.py printed.

| Template | `--kind` | `--cuts` | `--holds` and notes |
|---|---|---|---|
| `intro` | motion | none | `--holds end:2.0 --intended end_tail` (it settles at about 2 s and holds its last frame by design; widen the hold to the settle point if a short dead stretch sits just before it) |
| `outro` | motion | none | add `--holds` only for a still you planned |
| `slam` | motion | none | `--holds end:<seconds after the landing>` when `--dur` is long |
| `lockup` | motion | none | read the sheet for the flicker frames |
| `bug_in`, `bug_loop`, `bug_out` | loop | none | overlays: hook and end-tail gates are skipped. The bug is small and sways slowly, under motion_check's still threshold: `bug_in --holds start:0.1`, `bug_loop --holds 0-6` (its whole length), `bug_out --holds end:0.1`, after checking on the sheet that the bug is visible and its pose changes |
| `presented` | loop | none | overlay: hook and end-tail gates are skipped |
| `stinger`, `echo` | loop | none | the editor cuts at the printed cut point |
| `writeon` | motion | `<hit>` | `--holds end:2.0`; expect 2 warnings from the hit (a planned cut not detected as a hard cut, a one-frame pop): it is a flash, not a cut |
| `morph`, `pixelbuild`, `lightstreak` | motion | `<hit>` | `--holds end:1.6` |
| `linebuild` | motion | `<hit>` | `--holds end:1.5` |
| `lightpaint` | motion | `<hit>` | `--holds end:1.1` |
| `swap` | motion | `<hit>` | `--holds end:1.45 --intended hook` (a text-only line: its hook is the edit it sits in) |
| `shatter` | motion | `<hit>` | `--holds end:1.4` |
| `brandgrid` | motion | `<hit>` | `--holds end:2.2` |

The `intro`, `writeon` and bug flags were checked on a fresh clone with the skill's `acme_mark.svg` and the demo
profile; the other rows are starting points. An end hold may need widening to the logo's settle point (a short
`nothing moves` stretch that ends exactly where the declared hold starts, with the logo at rest on the sheet). If
a template still fails a gate otherwise, the cause is its timing: report it to the user instead of adding
`--intended` or editing the template on your own.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| 3D logo missing, only text shows | The SVG has no filled paths (stroke-only), or it is not valid XML (`--` in a comment, an unclosed tag). Fix the file or use a 2D template |
| "The source image cannot be decoded" | Same: invalid XML in the SVG |
| "writeon: found no outlines to draw" | The SVG has no path / circle / rect / line / polygon shapes (an embedded bitmap). Vectorize it first |
| "font load failed" | A profile font path is wrong; run `python3 engine/vprofile.py show <name> --check` |
| "unknown template" | Typo; the error lists the available templates |
| Logo colours vanish on the preview | The fill matches `--bg` or the profile primary; use the logo's light or dark version |
