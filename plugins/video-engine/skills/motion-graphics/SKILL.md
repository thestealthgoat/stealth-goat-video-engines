---
name: motion-graphics
description: Makes brand-styled overlays, cards and 3D card scenes with the open-source video engine - stats lower thirds, big text behind the speaker, pull-quote cards, a progress bar with the speaker's face riding it, before/after wipes, a pencil sketch that paints into the real shot, map routes that draw on, and three.js scenes (3D bar charts and count-up cards, glass cards orbiting a presenter, screenshot stacks, light-burst titles, badge clashes, toggle panels, glossy icon props, product reveals, mascot hop, UI flythroughs, extruded type). Outputs MP4 plus ProRes alpha layers and Premiere XML. Use when the user says "stats lower third", "stat card", "text behind me", "words behind the speaker's head", "quote card", "pull quote", "progress bar with chapters", "before and after", "sketch to real", "route map of our trip", "3D bar chart", "cards orbiting me", "screenshot stack", "app flythrough", "badge clash", "icon props", "3D card scene" or "overlay for Premiere".
---

# Motion graphics: overlays, cards and 3D card scenes

Graphics that sit on footage or stand alone as short motion pieces. Every color, font and logo comes from the
brand profile; every move is a spring (`engine/spring.py` / `engine/spring.js`): no fixed eases, opacity never
overshoots. Logo animation belongs to the **logo-motion** skill, full explainers to **explain**, person cut-outs to
**matte**, the final check to **video-gates**.

## 1. Find the engine and the profile

1. Use `$VIDEO_ENGINE` as the engine folder (a clone of
   https://github.com/thestealthgoat/stealth-goat-video-engines). If it is unset, ask the user where the engine is,
   or run the **getting-started** skill to install it (directly: `git clone
   https://github.com/thestealthgoat/stealth-goat-video-engines.git ~/video-engine && cd ~/video-engine && ./setup.sh`,
   then `export VIDEO_ENGINE="$HOME/video-engine"`; `setup.sh` targets macOS with Homebrew). Run every command from there:
   `cd "$VIDEO_ENGINE" && python3 engine/<tool>.py ...`.
2. Pass `--profile <name>` on every command (else the tools fall back to `$VIDEO_PROFILE`, then `local.json`).
   Use the user's own profile when they have one (`python3 engine/vprofile.py list`); use `demo` to try things.
   A new brand starts from `profiles/_template` (`python3 engine/vprofile.py new <name>`, see `docs/LAYOUT.md`);
   check it with `python3 engine/vprofile.py show <name> --check`.
3. Write outputs under `out/` in the engine folder (or a folder the user names), never into their source footage.

## 2. Pick the tool

| The user wants | Tool | Main output |
|---|---|---|
| A stats lower third (number, name, one big stat, 2-4 stat pairs, cut-out photo) | `engine/statcard.py` | `_stats_Alpha.mov` (ProRes 4444) + `_stats.mp4` preview + `_stats.png`; `--ae` adds an After Effects script |
| One word (or timed words) behind the person | `engine/behind.py --text` / `--events` | `_behind.mp4`; `--layer` adds `_behind_text_Alpha.mov` |
| Big keywords behind the speaker's head, picked from the transcript | `engine/behind.py --auto words.json` | same |
| A pull-quote: the person cut out, their words big in a serif | `engine/quote.py` | `_quote.mp4` + `_quote_Alpha.mov` |
| A progress bar along a talk, face marker, chapter ticks and titles | `engine/progressbar.py` | `_progress_Alpha.mov` + `_progress.mp4` |
| Before / after: a divider sweeps and scrubs across one frame | `engine/beforeafter.py` | `_ba.mp4` |
| Sketch to real: the frame draws itself in pencil, then the footage paints in | `engine/sketch.py` | `_sketch.mp4` |
| A route drawing itself on a map, distance counting up | `engine/routemap.py` | `_route.mp4` |
| 3D scenes: data, orbiting cards, screenshots, bursts, badges, toggles, props, reveal, mascot hop, flythrough, extruded type | `engine/stage3d.py <scene>` | `<Name>_<scene>.mp4`; `--alpha` adds `_Alpha.mov` |
| Any MP4-only render handed to Premiere | `engine/fcp7xml.py --single` | a one-clip `.xml` sequence |

Flags, file formats and output names for every 2D tool: [references/overlay-tools.md](references/overlay-tools.md).
Every stage3d scene, the `--data` format and `--spec` keys: [references/stage3d-scenes.md](references/stage3d-scenes.md).

## 3. Work in this order, every piece

1. **Confirm the words.** Spell names, numbers and quotes back to the user before rendering. Never invent a stat or
   put words in a real person's mouth: quotes and stats come from the user or the footage.
2. **Stills first.** Every tool takes `--frames t1,t2,...` and writes only those stills (seconds). Look at them:
   spelling, safe area, brand colors and fonts, nothing over a face, text readable at phone size.
3. **Render.** One heavy render at a time (stage3d, matte and behind are heavy; run long ones in the background and
   do not start a second). quote, progressbar, beforeafter, sketch, routemap and stage3d end with a `(qa: ...)`
   hint; keep it. statcard (last line `DONE <base>`) and behind print none: use the qa calls in section 4.
4. **QA before delivery.** Run `engine/qa.py` (the **video-gates** skill) with the hint or the call in section 4:
   `--kind motion` for stand-alone graphics, `--kind edit` for footage with graphics on it, `--kind loop` for
   overlays without an opening or ending of their own (a lower third). Always pass `--out out/mg/qa_<name>`: the
   default review folder is `./qa_<video name>/` in the engine root, outside the git-ignored `out/`. Read
   `review.md` and `sheet.jpg`, fix every real FAIL, re-run. When a gate fails by design (an insert with no hook of
   its own), declare it with `--intended hook`: qa then reports it as an INFO line, never a silent PASS. Never call
   a run a pass unless qa printed `RESULT: PASS`.
5. **Hand off.** Give the user the paths: the MP4 to watch, the `_Alpha.mov` layers to stack in an editor, and an
   XML for MP4-only tools (`python3 engine/fcp7xml.py --single <render.mp4> [out.xml] [--path <path the editor sees>]`).

## 4. Worked examples (fresh clone, demo profile)

Make throwaway test inputs once (ffmpeg only; replace them with the user's real files). The sample is 29.97 fps
because the demo profile delivers 29.97: progressbar renders at its source's rate, and a 30 fps source fails the
qa spec gate.

```bash
cd "$VIDEO_ENGINE" && mkdir -p out/mg
ffmpeg -v error -y -f lavfi -i testsrc2=size=1920x1080:rate=30000/1001 -f lavfi -i sine=frequency=330:sample_rate=48000 \
  -t 8 -c:v libx264 -pix_fmt yuv420p -c:a aac out/mg/sample.mp4
ffmpeg -v error -y -i out/mg/sample.mp4 -vf hue=s=0 -c:a copy out/mg/sample_grey.mp4
printf 'label,value\nMon,12\nTue,18\nWed,9\nThu,24\nFri,15\n' > out/mg/visits.csv
echo '[{"t": 0, "title": "Welcome"}, {"t": 4, "title": "The idea"}]' > out/mg/chapters.json
cat > out/mg/trip.gpx <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="hand" xmlns="http://www.topografix.com/GPX/1/1"><trk><trkseg>
<trkpt lat="46.00" lon="7.50"/><trkpt lat="46.10" lon="7.70"/><trkpt lat="46.25" lon="7.80"/><trkpt lat="46.40" lon="8.05"/>
</trkseg></trk></gpx>
EOF
```

### Stats lower third (statcard)
Copy `docs/stats_card_example.json` per person and fill it in (`num`, `name`, `big`, 2-4 `stats` pairs, optional
`photo` cut-out PNG; make one with `python3 engine/cutout.py photo.jpg person.png`).
```bash
python3 engine/statcard.py docs/stats_card_example.json out/mg --profile demo --frames 1.0,3.0   # stills
python3 engine/statcard.py docs/stats_card_example.json out/mg --profile demo                    # alpha .mov + mp4 + png
python3 engine/qa.py out/mg/stats_card_example_stats.mp4 --profile demo --kind loop --cuts none --out out/mg/qa_stats
```
Expect `RESULT: PASS` (hook and end-card gates listed as SKIP). Use `--kind loop`, not `--kind motion`: a lower
third has no opening of its own, and `--kind motion` fails it on the hook gate (no strong moment by 2 s; the
biggest move is about 8% of the frame).
Use `--bg clip.mp4 --bg-in 12` to preview it over real footage, `--dur` for a longer hold, `--no-logo` to hide the
logo, `--ae` to also write `<name>_stats.jsx` (After Effects: File > Scripts > Run Script File rebuilds it as a
native comp with real text layers; install the profile fonts first).

### Text behind the person (behind)
Needs a clip with a person at close or mid range (the matte runs first; it is slow: about 5 s a frame on a laptop
CPU with BiRefNet, so keep the window short and render in the background).
```bash
python3 engine/behind.py talk.mp4 --out out/mg/b --t0 30 --t1 42 --text "FOCUS" --profile demo --frames 1.0,4.0
python3 engine/behind.py talk.mp4 --out out/mg/b --t0 30 --t1 42 --text "FOCUS" --profile demo --layer
python3 engine/behind.py talk.mp4 --out out/mg/b --t0 30 --t1 70 --auto out/talk.words.json --profile demo   # keywords
```
- In the stills, check the word rises from behind the head and shoulders and never covers the face.
- `--auto` takes a faster-whisper words file (`engine/captions.py` or `engine/talkedit.py` write `<name>.words.json`).
  It picks one keyword per phrase, at least `--every 3.5` s apart. Fix a bad pick by editing the saved
  `<name>_behind.events.json` and re-running with `--events`.
- Reuse a matte of the same window with `--matte <name>_matte.mp4`. A sideways phone clip: `--rotate cw|ccw|180`.
- Look: `--fill solid|gradient|image.jpg`, `--color text|accent|'#hex'`, `--size 0.30` (cap height share).
- QA (behind prints no hint): `python3 engine/qa.py out/mg/b/<name>_behind.mp4 --profile demo --kind edit
  --cuts none --out out/mg/qa_behind`; add `--intended hook` when the clip is an insert, not the opening of a piece.

### Pull-quote (quote)
```bash
python3 engine/quote.py --text "Make the thing you wish existed." --by "Jane Doe" --role "Founder, ACME" \
  --cutout person.png --bg out/mg/sample.mp4 --bg-t 2 --out out/mg --name demo --profile demo --frames 2.5
```
For a smoke test without a person photo, use `--cutout profiles/demo/assets/demo_logo.png --bg '#0B3D2E'`. With a
matte instead of a photo: `--matte out/m/<name>_matte.json --at 1.0` (the ground defaults to the matte's own video).
Drop `--frames` to render, then QA with the printed hint:
```bash
python3 engine/qa.py out/mg/demo_quote.mp4 --profile demo --kind motion --cuts none --holds end:2.4 --out out/mg/qa_quote
```
Both the smoke test and the version over `out/mg/sample.mp4` give `RESULT: PASS`.

### Progress bar (progressbar)
```bash
python3 engine/progressbar.py out/mg/sample.mp4 --out out/mg --name demo --face profiles/demo/assets/demo_logo.png \
  --chapters out/mg/chapters.json --profile demo --frames 2.0,5.0
```
Use a real headshot or cut-out for `--face`, or `--matte <name>_matte.json` to take the face from a matte. Chapters
are `[{"t": seconds, "title": "..."}]` in the video's own time; `--t0/--t1` limit the window. It renders at the
video's frame rate: pass `--fps` with the profile's rate when the source differs. Lay `_progress_Alpha.mov` over
the program. QA the MP4 (the printed hint is only `--cuts none`):
```bash
python3 engine/qa.py out/mg/demo_progress.mp4 --profile demo --kind edit --cuts none --intended hook --out out/mg/qa_progress
```
`--intended hook` is needed: the bar rides a program and has no hook of its own, so the "strong moment by 2 s"
gate fails (biggest move about 6%). With it, expect `RESULT: PASS (0 warnings, 1 declared intended)`.

### Before / after (beforeafter)
```bash
python3 engine/beforeafter.py --before out/mg/sample_grey.mp4 --after out/mg/sample.mp4 --out out/mg --name demo \
  --labels "RAW|GRADED" --profile demo --frames 1.5,3.5
```
Both inputs must share the framing (raw vs graded, plate vs matte, rough vs final). `--a0/--b0` are in-points,
`--size 1080x1920` makes a vertical. Sound comes from AFTER. QA:
```bash
python3 engine/qa.py out/mg/demo_ba.mp4 --profile demo --kind motion --cuts none --intended hook --out out/mg/qa_ba
```
The divider sweep is a calm move (about 5% of the frame), so without `--intended hook` the printed hint
(`--kind motion --cuts none`) FAILs the "strong moment by 2 s" gate. Declare it when the piece is an insert after
the edit's own hook (expect `PASS, 1 declared intended`); when it opens a post, the FAIL is real: put a stronger
shot before it in the edit, and tell the user.

### Sketch to real (sketch)
```bash
python3 engine/sketch.py out/mg/sample.mp4 --out out/mg --name demo --profile demo --frames 1.0,3.0
```
`--t0` picks the start in the source, `--draw` the drawing time (default 2.2 s), `--dur` the length (default 6).
Pick a shot with clear shapes and some motion; flat or very dark frames draw poorly. The sound starts with the
real shot (the render prints `the real shot from 1.62 s`), so declare the silent head to qa:
```bash
python3 engine/qa.py out/mg/demo_sketch.mp4 --profile demo --kind motion --cuts none --silences 0-1.62 --out out/mg/qa_sketch
```
Use the time this render printed. Expect `RESULT: PASS`; without `--silences` it is a PASS with one WARN (silence at
the head).

### Route map (routemap)
```bash
python3 engine/routemap.py out/mg/trip.gpx --out out/mg --name demo --labels "Start|Finish" --profile demo --frames 3.0,7.0
python3 engine/routemap.py --gpx-from-videos "footage/*.MOV" --gpx-out out/mg/trip.gpx    # GPX from phone clips' GPS tags
```
`--map naturalearth` (default, public-domain layers, regional scale) or `--map osm` (city scale). Tell the user this
downloads public map data once into `_cache/` (Natural Earth is about 23 MB; or OpenStreetMap via the Overpass
API); nothing of theirs is uploaded, and the map credit stays on screen as the license requires. Drop `--frames`
to render, then QA with the printed hint (expect `RESULT: PASS`):
```bash
python3 engine/qa.py out/mg/demo_route.mp4 --profile demo --kind motion --cuts none --holds end:1.0 --out out/mg/qa_route
```

### 3D card scenes (stage3d)
Needs the setup's Playwright Chromium and `logo/node_modules/three` (`./setup.sh --check` lists both).
```bash
python3 engine/stage3d.py data  out/mg Demo --data out/mg/visits.csv --profile demo --frames 2.0
python3 engine/stage3d.py burst out/mg Demo --lines "PLAN|BUILD|SHIP" --bg mesh --profile demo --fps 29.97
python3 engine/stage3d.py badge out/mg Demo --text1 "FAST" --text2 "FREE" --alpha --profile demo --fps 29.97
python3 engine/qa.py out/mg/Demo_burst.mp4 --profile demo --kind motion --cuts 0.310,2.110,3.910 --out out/mg/qa_burst
```
The burst render takes about a minute on a laptop and ends with
`hit at 0.310 s, cuts 0.310,2.110,3.910 (qa: --cuts 0.310,2.110,3.910)`; pass the cuts your render printed.
Expect `RESULT: PASS (3 warnings)`: one "planned cut not detected as a hard cut" WARN per line, because each
title swaps behind a light burst rather than on a hard cut. Check those frames on `sheet.jpg` by eye; that WARN is
expected here, any other flag is not. stage3d renders at 30 fps unless told otherwise: pass `--fps` to match the
profile's delivery rate, or give qa `--fps 30`. Scenes, inputs and settings: [references/stage3d-scenes.md](references/stage3d-scenes.md). Cards that
orbit a presenter (`orbit`) need a matte first (**matte** skill: `engine/matte.py`), then
`--matte out/m/<name>_matte.json --cards "A|B|C"`.

### Hand an MP4 to Premiere
```bash
python3 engine/fcp7xml.py --single out/mg/demo_ba.mp4 out/mg/demo_ba.xml
```
Add `--path "/the/path/the/editing/machine/sees/demo_ba.mp4"` when the editor opens it from another machine or drive.

## 5. Pop-up cards inside a talking-head edit

`engine/talkedit.py` (the **video** skill) places pop-up cards on cue by itself: a number said with its noun
becomes a stat card that counts up, a profile trigger word becomes a word card, emphasis words fill the rest. Tune
them in the profile under `talkedit.pops` (`per_min`, `min_gap_s`, `triggers: {"word": "CARD TEXT"}`), or edit the
`pops` list in `<name>.talkedit.json` and re-run (`--fresh` plans again). Do not rebuild them with these tools.

## 6. Rules

- Brand only from the profile. Do not hard-code colors or fonts in commands; if a look is wrong, fix the profile.
- One big spring moment per piece at most (a badge clash, a quote mark landing); everything else stays calm.
- Keep text inside the profile's safe area and off faces; check the stills, then the qa sheet.
- Free and local by default: the matte and cut-outs run BiRefNet through rembg on the user's machine (models folder:
  `engine/models.py`); captions run faster-whisper locally. Nothing is uploaded unless the user picks a service.
- AI tools are fine when the user wants them, but never fake a real person: no invented quotes, no made-up stats
  attributed to someone, no synthetic face or voice of a real person.
- Render twice with two different profiles (e.g. `demo` and the user's) before calling a reusable template done.
- QA every render with `engine/qa.py` before showing or delivering it.
