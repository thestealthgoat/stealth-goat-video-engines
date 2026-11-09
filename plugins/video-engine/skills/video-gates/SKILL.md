---
name: video-gates
description: QA gate for any finished or near-finished video (edit, motion graphics, logo loop, explainer) made with the video engine. Runs engine/qa.py (spec, motion, stutters, cuts against the plan, flashes, loudness and true peak, clicks, hook, holds, end tail, explainer freshness), reads the review sheet, steps through 4 fps contact sheets and every cut frame by frame to catch what the machine cannot see (overlapping text, a graphic exploding for a few frames), then has a fresh-eyes reviewer score it against the last version. Use before showing or delivering any render, and when the user says "QA this video", "check the render", "is this ready to deliver", "run the gates", "review this cut", "check loudness", "why does it stutter", "look for glitches", or "run qa.py".
---

# Video gates

Run this before any render is shown to the user or delivered, and again after every fix round. The engine does the
measuring; you do the looking. The process is fixed; only the film-specific criteria change.

The machine pass cannot see what a frame shows. Text overlapping text, a label over a face, a graphic that explodes,
smears or flips for three frames, a black or wrong frame at a cut: all of these pass every gate. A PASS from
`qa.py` is never a delivery verdict on its own. Read the review sheet, step through the contact sheets, and look at
every cut frame by frame, every time.

## 0. Find the engine and the profile

1. Check `$VIDEO_ENGINE` (`echo "$VIDEO_ENGINE"`). If it is unset or has no `engine/qa.py`, ask the user where their
   clone is, or run the `getting-started` skill. With no clone yet, set one up (`setup.sh` targets macOS with
   Homebrew):
   `git clone https://github.com/thestealthgoat/stealth-goat-video-engines && cd stealth-goat-video-engines && ./setup.sh && export VIDEO_ENGINE="$PWD"`.
   Run every engine command from there: `cd "$VIDEO_ENGINE" && python3 engine/qa.py ...`.
2. Pick the profile: the delivery spec (size, fps, loudness, true peak, safe area) comes from it. Pass
   `--profile <name>`, else `$VIDEO_PROFILE`, else the default in `local.json`. Use the profile the video was made
   with. `python3 engine/vprofile.py list` shows what is installed; every clone ships `demo` (-14 LUFS, 1920x1080 at
   29.97), so to try things use `--profile demo`. If the user has no profile, qa runs on generic defaults (-14 LUFS,
   -1 dBTP, size not checked); offer to make one: `python3 engine/vprofile.py new <name>` (copies
   `profiles/_template`; see `docs/LAYOUT.md`), then `python3 engine/vprofile.py show <name> --check`.
3. Needs ffmpeg/ffprobe (with scdet and ebur128), numpy and Pillow. The frame-stepping helper,
   `scripts/frames.py` in this skill's folder (the base directory shown when the skill loads), needs the same.

Never start a QA run while another heavy render or QA run is going: one heavy job at a time.

## 1. Machine pass

Pick the kind and declare the plan, so every flag left is a real question:

```
# footage cut to music or speech (reels, highlights, promos, talking-head edits)
python3 engine/qa.py <video> --profile <name> --kind edit --cuts 1.5,4.2,7.9   # or --shotlist <concat list | cuts.json>

# motion graphics (cards, lower thirds, logo animations): strict motion gate, hold gate, pops
python3 engine/qa.py <video> --profile <name> --kind motion --cuts none [--holds end:1.2] [--intended end_tail]

# loops and overlays (a logo swing loop, a corner bug, a lower third): as motion, no hook or end-tail gate
python3 engine/qa.py <video> --profile <name> --kind loop --cuts none

# explainers: motion gates plus freshness (a new visual at least every --max-scene seconds)
python3 engine/qa.py <video> --profile <name> --kind explainer --cuts none [--max-scene 2.5]
```

Rules for declaring:

- `--cuts` lists the planned cut times in seconds; `--cuts none` says no cuts are planned. Every other hard cut is
  an unplanned jump (FAIL). Without `--cuts` or `--shotlist` cuts are only listed, so always give one.
- `--shotlist` takes the ffmpeg concat list your renderer used (cuts are the running sum of the part durations) or a
  cuts JSON (a list, `cuts`, `starts`, or `shots[].start`). Not an edit list with in/out points: qa refuses it.
- `--holds a-b,start:N,end:N` declares planned stills. The fixed limits still apply: no hold over 0.8 s without
  life in motion work, no static tail over 1.5 s.
- `--intended end_tail,hook` (names: `hook`, `hook_motion`, `hook_strong`, `end_tail`) only for an exception the
  brief or the template's design asks for, such as a logo intro holding its last frame. The gate still runs and a
  failure shows as INFO "declared intended", never as a silent PASS. A designed end hold also needs
  `--holds end:N`. Tell the user what you declared and why. A gate that fails without a design reason is fixed, not
  declared.
- `--silences a-b` declares planned silences; `--allow-stutter` only when irregular repeated frames are deliberate;
  `--fps N` / `--size WxH` replace the profile's delivery rate / sizes (e.g. `--fps 60` for a 60p overlay).
- `--out <dir>` sets the review folder (default `./qa_<video name>/` in the current folder). Keep reviews next to
  the render. Inside the engine folder the only place for renders and reviews is `out/` (git ignores it, and the
  worked examples below use it); the user's own projects belong in their own folder outside the engine.
- On a preview it warns about the preview size; that is expected. Spec gates are judged on the final.

Exit code: 0 PASS, 1 FAIL, 2 unreadable file. It writes `review.md`, `sheet.jpg` and `qa.json`. The full gate list,
option details, frame-rate rules and output fields are in [references/gates.md](references/gates.md).

## 2. Read the review and the sheet

1. Read `review.md` completely: verdict, fix lines, gate table, spec, loudness, shot table, manual checks.
2. `Read` `sheet.jpg`: the timeline, one frame per shot with the safe area as a cyan box, and an evidence strip
   (before | flagged | after) for each of the worst flags.
3. Judge every FAIL and WARN by its frames: **real**, **intended** or **false alarm**, and write the judgement next to
   the flag in `review.md`. Intended things go into the declaration (a planned cut into `--cuts`, a still into
   `--holds`, a designed exception into `--intended`, an overlay into `--kind loop`) and the run is repeated, so the
   record stays clean.

## 3. Step through the frames (the part the machine cannot do)

Make the sheets with the helper:

```
python3 <this skill's folder>/scripts/frames.py <video> --qa <qa review dir> --out <qa review dir>/frames
```

It writes `contact_<t>s.jpg` (4 frames a second, 10 s a sheet, each tile labelled with time and frame),
`cut_f<N>.jpg` for every detected and every planned cut (4 frames before, 4 after, exact frame numbers, the first
frame of the new shot outlined) and `flag_f<A>-f<B>.jpg` for every flag span up to 2 s, frame by frame.

1. `Read` every contact sheet, in order. Do not skim to the end.
2. `Read` every cut strip. Check: the last frame before and the first after are both clean (no black, no stray
   frame from another shot, no half-rendered graphic), the cut has a visible cause, continuity holds.
3. For every element entrance, exit and transition (titles, cards, labels, logos, scene changes), look at that range
   at the full frame rate, because a 2-3 frame break falls between 4 fps samples:
   `python3 <skill folder>/scripts/frames.py <video> --out <dir>/full --from 12.0 --to 13.5 --fps 29.97 --window 1.5`
   (use the file's own rate).
4. Do the manual checks listed in `review.md`, cropping frames with ffmpeg where needed
   (`ffmpeg -ss 12.4 -i <video> -frames:v 1 -vf "crop=960:540:0:0" crop.png`):
   - text at least 24 px from the edges and inside the profile's safe area (the cyan box);
   - text never over a face or over other text; readable at phone size;
   - no graphic that overshoots, explodes, smears, flips or jumps; nothing that appears or vanishes in one frame;
   - every cut has a visible cause; no reversals or ghost frames; continuity across cuts;
   - no decorative wipes, inverts, added shake or light leaks; nothing cut by the frame edge;
   - no slow stretches where nothing new happens.
5. Write each defect you find as a fix line in `review.md`:
   `f<start>-f<end> (mm:ss.s) - what is wrong - why it matters - concrete fix (with a number when possible)`.
6. Sound is measured, not heard. Say so, and ask a person to listen before acceptance.

## 4. Fresh-eyes reviewer

You built it, so you never grade it. Spawn a sub-agent with no context. Give it only files: `review.md`,
`sheet.jpg`, the `frames/` sheets and crops, and the previous version's review and sheets when there is one. Do not
tell it what the video is meant to say. It says what the video is about and where it got confused (a misreading is a
defect of the video), scores it out of 10 head to head against the last version (or the brief's reference), flags
anything cheap or templated, and lists defects as fix lines. The prompt and the slop list are in
[references/fresh-eyes.md](references/fresh-eyes.md). Paste its answer under "Fresh-eyes review" in `review.md`.

Fix, re-render the changed ranges, then re-run steps 1-4 on the whole new file with a new fresh reviewer. Three
rounds at most; after the third, report what is left to the user instead of looping.

## 5. Verdict

Decide **ACCEPT**, **FIX** or **REBUILD** and tell the user: the verdict, the score against the last version, the
loudness and true-peak numbers, anything declared intended and why, and the remaining fix lines, most severe first.
Never call a video ready on the machine pass alone. Keep `review.md`; delete sheets, crops and frame dumps made only
for looking once the review is done. Nothing is uploaded anywhere unless the user chooses a service.

## Worked examples (fresh clone, demo profile)

These were run on a fresh clone; the numbers are what to expect. Make a 4-second synthetic test clip and gate it as
motion graphics:

```
cd "$VIDEO_ENGINE"
mkdir -p out/qa_demo
ffmpeg -nostdin -v error -y -f lavfi -i "testsrc2=size=1920x1080:rate=30000/1001:duration=4" \
  -f lavfi -i "sine=frequency=440:duration=4" -c:v libx264 -pix_fmt yuv420p -c:a aac -shortest out/qa_demo/test.mp4
python3 engine/qa.py out/qa_demo/test.mp4 --profile demo --kind motion --cuts none --out out/qa_demo/review
```

Expected: `RESULT: FAIL (2 fail, 0 warning)`, exit 1. This first run is meant to fail; it shows what real failures
look like. Spec, motion, flashes, cuts, holds and true peak pass; the loudness gate fails (-21.8 LUFS against the
demo profile's -14, fix line "apply +7.8 dB (2-pass loudnorm I=-14:TP=-2)") and the hook gate fails (no cut or big
move by 2 s). Both are real: a test tone is quiet and the test pattern has no hook. Tell the user so; do not
declare either one intended.

Then step through it:

```
python3 <this skill's folder>/scripts/frames.py out/qa_demo/test.mp4 --qa out/qa_demo/review --out out/qa_demo/review/frames
```

It writes `contact_0000.00s.jpg` (16 tiles at 4 fps) and `flag_f00000-f00059.jpg` (the hook flag's frames); the
loudness flag spans the whole file, so it gets no strip.

A fix round: apply the loudness fix line and gate the result as a loop (a test pattern is overlay-like, so no hook
or end-tail gate):

```
ffmpeg -nostdin -v error -y -i out/qa_demo/test.mp4 -c:v copy -af "loudnorm=I=-14:TP=-2" -ar 48000 -c:a aac out/qa_demo/test_fixed.mp4
python3 engine/qa.py out/qa_demo/test_fixed.mp4 --profile demo --kind loop --cuts none --out out/qa_demo/review_fixed
```

Expected: `RESULT: PASS (0 warnings)`, exit 0, loudness -14.0 LUFS, true peak about -8 dBTP. The same fixed file as
`--kind motion` still fails one gate (the hook), exit 1, because the picture has not changed. The unfixed file as
`--kind loop` fails only on loudness.

An explainer: build and render the Lissajous example (`examples/explain/lissajous/`, see the explain skill). The
render is 40 s of 1080p and takes about 6 minutes:

```
python3 examples/explain/lissajous/make.py
python3 engine/explain.py examples/explain/lissajous/storyboard.json --out out/lissajous --profile demo \
    --music examples/explain/lissajous/_build/tones.wav
python3 engine/qa.py out/lissajous/storyboard.mp4 --profile demo --kind explainer --max-scene 2.5 --cuts none --out out/lissajous/qa
python3 <this skill's folder>/scripts/frames.py out/lissajous/storyboard.mp4 --qa out/lissajous/qa --out out/lissajous/qa/frames
```

Expected: `RESULT: PASS (0 warnings)`, exit 0 (-14.0 LUFS, true peak about -13 dBTP), and four contact sheets
(`contact_0000.00s.jpg` to `contact_0030.00s.jpg`). That PASS is still only the machine pass: steps 2-5 apply.

An edit with planned cuts at 2.0 s and 5.5 s: `python3 engine/qa.py reel.mp4 --profile demo --kind edit --cuts 2.0,5.5`.
A detected cut within 3 frames of a planned time counts as that cut; any other hard cut is an unplanned FAIL, and a
planned cut that was not detected is a WARN to check by eye in its `cut_f<N>.jpg` strip.
