---
name: logo-motion
description: Makes animated logo graphics from any SVG logo with the local video engine (logo/motion.py, three.js in headless Chromium, spring motion) - intro, outro end card, corner bug (in / loop / out), stinger, "presented by" sponsor lower third, slam-in for compositing, lit sign lockup, signature write-on, circle morph, pixel build, line build, echo stinger, light-streak write, light-painting story, kinetic word swaps, shatter into a new logo and a brand grid - as ProRes 4444 alpha .mov plus MP4 previews in the brand profile's colors and fonts, with an optional dark cinematic finish. Use when the user says "logo intro", "animate our logo", "logo reveal", "end card", "corner bug", "stinger transition", "presented by lower third", "sponsor lower third", "logo slam", "logo write-on", "word-swap lower third", "shatter the old logo into the new one", "rebrand reveal", "brand grid", "light painting animation" or "logo animation with a transparent background".
---

# Logo motion

Animate a logo with `logo/motion.py` in the engine folder. It draws the logo in 3D (three.js extrusion, the same
builder as the **logo-3d** skill) or in 2D from the SVG's own outlines, adds text in the profile's fonts, light
sweeps and panels in the profile's colors, and renders every frame with a transparent background. All motion uses
the engine's spring presets (`logo/spring.js`), so nothing moves on a fixed-duration ease. Everything runs locally;
nothing is uploaded.

The full template list (length, what it does, text fields, printed hit or cut, QA flags) is in
[references/templates.md](references/templates.md). Read it before picking a template or running QA.

## 0. Find the engine and the profile

1. Use `$VIDEO_ENGINE` as the engine folder (a clone of
   https://github.com/thestealthgoat/stealth-goat-video-engines) and run every command from it:
   `cd "$VIDEO_ENGINE" && python3 logo/motion.py ...`. If `$VIDEO_ENGINE` is unset or the folder has no
   `logo/motion.py`, ask the user where the engine is, or set it up (the **getting-started** skill walks through
   it): `git clone https://github.com/thestealthgoat/stealth-goat-video-engines.git ~/video-engine`, then `./setup.sh` in it (it
   targets macOS with Homebrew), then `export VIDEO_ENGINE="$HOME/video-engine"`. Do not guess a
   path.
2. Check the logo tools once per machine: `./setup.sh --check` in the engine folder (installs nothing). It must find
   `logo/node_modules/three` and Playwright Chromium. The engine's setup targets macOS with Homebrew: on another
   system the Homebrew and `~/Library` lines report MISS or WARN even where the tool is installed another way, so
   judge only the two logo lines. If they are missing, tell the user what `logo/setup.sh` does and get a yes before
   running it: npm packages into `logo/node_modules`; pip packages (vtracer, cairosvg, scikit-learn,
   opencv-python-headless, pillow, playwright, fonttools) into the system Python, or the user site if that is
   refused; Playwright's Chromium into the user's browser cache (`~/Library/Caches/ms-playwright` on a Mac); a
   separate venv `logo/srenv` with opencv-contrib; and two super-resolution models (EDSR_x4.pb, FSRCNN_x4.pb)
   downloaded from GitHub into `resources/models`.
3. Pick the profile: `--profile <name>` on every command, else `$VIDEO_PROFILE`, else `local.json`. Use the user's own
   brand profile if they have one; to make one, copy `profiles/_template` with
   `python3 engine/vprofile.py new <name> --display "ACME Studio" --primary "#112233" --accent "#E04050"` (see
   `docs/LAYOUT.md`), or run the **getting-started** skill. To try things, use `--profile demo`: the repo ships it
   with its fonts (Anton and Barlow Condensed, OFL licenses beside them) and a sample logo
   `profiles/demo/assets/demo_logo.png`.
4. Check the profile's fonts: `python3 engine/vprofile.py show <name> --check`. Every `font` line must resolve:
   motion.py stops with an error rather than draw text in a fallback font. Missing paths and logo files in the
   check are fine for motion work (a profile made from `_template` may report its `paths` folders as missing until
   they are made; the demo profile's are optional, so its check ends `CHECK: OK`); missing fonts are not.

Set `SKILL` to this skill's folder (the base directory shown when the skill loads), for example
`SKILL="/path/to/logo-motion"`, quoted because the path may hold spaces. It holds two sample files for trying
templates on a fresh clone: `assets/acme_mark.svg` (a hexagon badge with a letter A) and
`assets/story_example.svg` (a three-scene line-art story for `lightpaint`).

## 1. Get a clean SVG

- motion.py takes an SVG only. If the user has a PNG, JPG or screenshot, run the **logo-vectorize** skill first.
- Every 3D template (`intro`, `outro`, `bug`, `stinger`, `presented`, `slam`) extrudes the filled paths: a path with
  `fill="none"` is skipped, so a stroke-only logo shows nothing there. Use a 2D template (`writeon`, `morph`,
  `lightstreak`, `echo`) for line art, or vectorize the strokes into fills.
- The SVG must be valid XML. A broken file (for example `--` inside an XML comment) renders an **empty** 3D logo
  with no error, and the 2D templates stop with "The source image cannot be decoded". The stills in step 3 catch it.
- Use the logo's light version when it will sit on a dark background (and the reverse); motion.py keeps the SVG's
  own fill colors.

## 2. Pick the template

Ask what the piece is for, then choose (details in [references/templates.md](references/templates.md)):

| The user wants | Template |
|---|---|
| a logo opener for videos | `intro` (3D), or a 2D build: `writeon`, `morph`, `pixelbuild`, `lightstreak`, `linebuild` |
| an end card | `outro` (`--text1` big line, `--text2` small line in the accent) |
| a corner logo for a stream | `bug` (writes `bug_in`, `bug_loop`, `bug_out` for a switcher) |
| a transition between shots | `stinger` (panel wipe) or `echo` (outline ripples); both print the cut point |
| a sponsor credit | `presented` (`--sponsor sponsor.png`, `--text1` replaces "PRESENTED BY") |
| a logo to composite into an edit | `slam` with `--place` and `--png-seq` (see step 5) |
| a show title sign | `lockup` (`--text1`, `--text2`, `--text3`, optional `--plate` still) |
| a word-swap line ("___ is next") | `swap` |
| a rebrand reveal | `shatter` (`--svg2 new.svg`, else `--text2` in the head font) |
| a brand-system card with a stat | `brandgrid` (`--text1` label, `--text2` value) |
| a short story drawn in light | `lightpaint` with `--finish dark` |
| a 3D type flythrough | not motion.py: `python3 engine/stage3d.py extrude out/ ACME --text "ACME" --profile demo` |

`--finish dark` works on any template: a dark stage, a reflective floor, bloom, grain and a vignette (opaque
output); add `--mockup laptop` to put the finished frame on a laptop screen. A profile can tune it with a
`finish.dark` block (keys `bg`, `bg2`, `bloom`, `floor`, `dof`, `grain`, `vignette`).

Write text exactly as the user gives it. Never put a real person's name, face or likeness into a piece unless it is
the user's own or they have the rights; never make a fake of a real person.

## 3. Look first: stills only

Render a few stills before any movie. `--frames` writes transparent PNGs only (seconds, not minutes):

```bash
cd "$VIDEO_ENGINE"
python3 logo/motion.py "$SKILL/assets/acme_mark.svg" out/ ACME intro --profile demo --text1 "ACME STUDIO" --frames 0.5,1.5,3.5
python3 logo/preview.py out/look.png out/ACME_intro_t0.50.png out/ACME_intro_t1.50.png out/ACME_intro_t3.50.png --profile demo
```

`preview.py` composites the stills on the profile's primary color and stacks them. `Read` `out/look.png` and check:
the logo is there (not empty), text is spelled right and fits, nothing collides with the logo or crosses the safe
area (`layout.safe_px` in the profile), and the sponsor art matches what the user supplied. Show the stills to the
user when the look is a choice they should make.

## 4. Render

Drop `--frames` to render the movie:

```bash
python3 logo/motion.py "$SKILL/assets/acme_mark.svg" out/ ACME intro --profile demo --text1 "ACME STUDIO"
```

- Outputs `out/<Name>_<template>_Alpha.mov` (ProRes 4444 with alpha, 1080p60 by default) and
  `out/<Name>_<template>.mp4` (a preview on `--bg`, default the profile's primary color; `--bg 112233` or
  `--bg '#112233'`, quoted because `#` starts a shell comment).
- motion.py prints one line per clip, for example `writeon: 4.5 s, hit at 1.858 s (frame 111; qa: --cuts 1.858)`,
  or `cut at 0.55 s` for stingers. Keep that number: QA needs it, and an editor needs the cut point.
- Expect roughly 20 seconds to 1.5 minutes of render time per second of animation at 1080p60 (the 4 s `intro` took
  1.5 min; glow-heavy 2D templates such as `writeon` are the slow end). The alpha .mov is large: about 60 MB for
  `intro`, about 400 MB for `writeon`. Run one heavy render at a time; run a long one in the background and wait
  for it rather than starting a second.
- Change the rate or size with `--fps 29.97002997` and `--size 1080x1920`. Most templates take `--dur` to change the
  length; `writeon` also takes `--write <seconds>` (pen time).
- Keep outputs outside the engine folder in real work: point `out` at the user's project folder or the profile's
  `paths.root`.

More worked commands (each checked as stills with `--frames` on a fresh clone with the demo profile):

```bash
python3 logo/motion.py "$SKILL/assets/acme_mark.svg" out/ ACME outro --profile demo --text1 "THANKS FOR WATCHING" --text2 "ACME STUDIO · YOUTUBE"
python3 logo/motion.py "$SKILL/assets/acme_mark.svg" out/ ACME presented --profile demo --sponsor profiles/demo/assets/demo_logo.png
python3 logo/motion.py "$SKILL/assets/acme_mark.svg" out/ ACME writeon --profile demo --text1 "WELCOME"
python3 logo/motion.py "$SKILL/assets/acme_mark.svg" out/ ACME swap --profile demo --text1 "___ is next" --text2 "faster|bolder|yours"
python3 logo/motion.py "$SKILL/assets/acme_mark.svg" out/ ACME brandgrid --profile demo --text1 "VIDEOS MADE" --text2 "1,284"
python3 logo/motion.py "$SKILL/assets/acme_mark.svg" out/ ACME shatter --profile demo --text2 "ACME"
python3 logo/motion.py logo/stories/placeholder_story.svg out/ STORY lightpaint --profile demo --finish dark
python3 logo/motion.py "$SKILL/assets/acme_mark.svg" out/ ACME pixelbuild --profile demo --finish dark --mockup laptop
```

`profiles/demo/assets/demo_logo.png` stands in for a sponsor's logo here; in real work the user supplies the
sponsor's PNG. `logo/stories/placeholder_story.svg` (three scenes) ships with the engine; this skill's
`"$SKILL/assets/story_example.svg"` is a second sample. For `lightpaint`, each top-level `<g>` of the SVG is one
scene (2.4 s each, plus 0.8 s); the art can be drawn, traced or made with an AI image tool and then vectorized, but never a fake of a
real person.

## 5. Compositing into an edit

For a logo that lands inside a shot (intros, promos), render a transparent PNG sequence at the edit's frame
rate instead of a movie:

```bash
python3 logo/motion.py "$SKILL/assets/acme_mark.svg" out/ ACME slam --profile demo --place 0.5,0.44,0.62,0.42 --dur 3.4 --fps 29.97002997 --png-seq
```

This writes `out/ACME_slam_seq/f00000.png ...`. `--place cx,cy,bw,bh` is the landing box in frame fractions
(center x, center y, max width, max height; `slam` and `writeon`). In the compositor, frame index =
round((t - hit time) × fps) to line the hit up with a beat; alpha-composite over the shot. Land the logo on a calm
area or a solid band so its colors don't sit on the same color.

## 6. QA before delivery

Never hand over a render without the QA gate (the **video-gates** skill). First tile the preview and look:

```bash
ffmpeg -nostdin -v error -y -i out/ACME_intro.mp4 -vf "select='not(mod(n,20))',tile=5x3" -frames:v 1 out/tiles.png
```

Then run the gate on the alpha .mov with the template's flags from
[references/templates.md](references/templates.md). `--fps 60` because the renders are 1080p60 while a profile
usually delivers 29.97 (drop it for a render made with `--fps 29.97002997`):

```bash
python3 engine/qa.py out/ACME_intro_Alpha.mov --profile demo --kind motion --fps 60 --cuts none --holds end:2.0 --intended end_tail --out out/qa_ACME_intro
python3 engine/qa.py out/ACME_writeon_Alpha.mov --profile demo --kind motion --fps 60 --cuts <hit> --holds end:2.0 --out out/qa_ACME_writeon
python3 engine/qa.py out/ACME_bug_in_Alpha.mov --profile demo --kind loop --fps 60 --cuts none --holds start:0.1 --out out/qa_ACME_bug_in
python3 engine/qa.py out/ACME_bug_loop_Alpha.mov --profile demo --kind loop --fps 60 --cuts none --holds 0-6 --out out/qa_ACME_bug_loop
python3 engine/qa.py out/ACME_bug_out_Alpha.mov --profile demo --kind loop --fps 60 --cuts none --holds end:0.1 --out out/qa_ACME_bug_out
```

What to expect with `acme_mark.svg` and the demo profile (checked on a fresh clone): `intro` and the three bug
clips PASS with 0 warnings. `writeon` (hit printed as 1.858) PASSES with 2 warnings, both from the intended hit:
`planned cut not detected as a hard cut` (the hit is a flash, not a cut) and a one-frame pop of about 80% of the
picture on the frame after the hit (the fills landing). Anything beyond that is a finding.

- Use `--kind loop` for pieces that sit on top of other video (`bug_in`, `bug_loop`, `bug_out`, `presented`) and for
  stingers (`stinger`, `echo`): their hook and end-tail gates are listed as SKIP.
- Use `--cuts <hit>` with the hit time motion.py printed: the hit's flash can read as a cut otherwise. A one-frame
  "pop" warning on the hit frame is the intended flash.
- `--holds end:N` declares the template's designed end hold. `--intended end_tail` (or `hook`) only for holds the
  template is built around (listed in the reference); never add it to make a real failure go away.
- `Read` `review.md` and `sheet.jpg` in the review folder and fix every FAIL. If a FAIL comes from a template's own
  timing, tell the user rather than editing the template.
- The designed end hold starts where the logo settles, and that point moves a little with the logo's shape. If
  the only FAIL is a short `nothing moves` stretch (under about 0.3 s) that ends where the declared hold begins,
  and the sheet shows the logo already at rest there, the hold was declared too short: widen it to start at the
  stretch. With `acme_mark.svg`, `intro` at `end:1.8` fails with `nothing moves for 0.15 s` at 2.05-2.20 s and
  `writeon` at `end:1.9` fails with `nothing moves for 0.07 s` at 2.53-2.58 s; `end:2.0` is the real settle point
  for both. A dead stretch anywhere else is a real fault: report it.
- The corner bug is small (about 17% of the frame width) and its loop sways slowly on purpose, so most of its
  frames change less than motion_check's 0.3% still threshold. Without `--holds`, `bug_loop` FAILS with 7 dead
  stretches (two of 1.00 s), `bug_in` with 0.07 s at the start (the first frames are a faint, tiny fade-in) and
  `bug_out` with 0.07 s at the end (it has shrunk to nothing). Declare those as above (`0-6` = the loop's whole
  length; change it if `--dur` changed), but only after checking the motion sheet: the logo must be visible and
  its pose must change between the sheet's frames. A bug that does not move at all is a real fault.
- For a closer look at dead stretches or stutters: `python3 engine/motion_check.py out/ACME_intro_Alpha.mov --holds
  end:2.0 --sheet out/check.jpg`, then `Read` the sheet.

## 7. Deliver

Give the user the paths of the alpha .mov (for the switcher or the edit) and the .mp4 preview, the printed hit or
cut time, and the QA verdict. For a switcher bug, deliver all three clips (`bug_in`, `bug_loop`, `bug_out`): the
loop is seamless and the in and out clips start and end in the loop's pose.

## Rules

- Brand colors and fonts come from the profile only; never hard-code a brand's values in a command or a template.
  `--accent` overrides only the outro's second line color.
- Keep each template generic: any SVG, any profile.
- A new template goes into `TEMPLATES` in `logo/motion.html`: a function of time that returns the logo placement,
  glint, texts and panels. Use the spring presets (logo lands `bouncy` or `slam`, panels and text `snappy`, pushes
  and fades `smooth` with `Spring.clamp01`, drifts `gentle`), never a fixed-duration ease; keep 3D turns under about
  70 degrees so the logo's mirrored back never shows. Check it with `engine/motion_check.py` and the QA gate.
