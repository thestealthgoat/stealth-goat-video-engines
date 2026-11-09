# Tool reference

Every command-line tool in this repository, grouped by job. For each tool: what it is for, the synopsis, the
options you will use most, what it writes, and the `engine/qa.py` call that checks its output.

The synopses below were checked against each tool's `--help` and its source. The docstring at the top of each file
is the full specification; run `python3 <tool> --help` before using a flag that is not listed here.

## Contents

- [Conventions](#conventions)
- [Quick index](#quick-index)
- [QA and audio](#qa-and-audio)
  - [qa.py](#qapy) · [motion_check.py](#motion_checkpy) · [audio_check.py](#audio_checkpy) · [sheet.py](#sheetpy) ·
    [beatmap.py](#beatmappy) · [musicbed.py](#musicbedpy) · [sfx_build.py](#sfx_buildpy)
- [Editing and encoding](#editing-and-encoding)
  - [talkedit.py](#talkeditpy) · [captions.py](#captionspy) · [fxpack.py](#fxpackpy) · [beatsnap.py](#beatsnappy) ·
    [clip_plays.py](#clip_playspy) · [calls.py](#callspy) · [fcp7xml.py](#fcp7xmlpy) · [vertical.py](#verticalpy) ·
    [flipbook.py](#flipbookpy) · [encode.py](#encodepy)
- [Motion graphics and cards](#motion-graphics-and-cards)
  - [statcard.py](#statcardpy) · [quote.py](#quotepy) · [behind.py](#behindpy) · [progressbar.py](#progressbarpy) ·
    [beforeafter.py](#beforeafterpy) · [sketch.py](#sketchpy) · [hopwords.py](#hopwordspy) ·
    [stage3d.py](#stage3dpy) · [measure.py](#measurepy)
- [Explainers](#explainers)
  - [storyboard.py](#storyboardpy) · [explain.py](#explainpy) · [sourcecard.py](#sourcecardpy)
- [Logos](#logos)
  - [vectorize.py](#vectorizepy) · [fontmatch.py](#fontmatchpy) · [render3d.py](#render3dpy) ·
    [motion.py (logo)](#motionpy-logo) · [preview.py (logo)](#previewpy-logo) · [sr.py](#srpy)
- [People and cutouts](#people-and-cutouts)
  - [matte.py](#mattepy) · [cutout.py](#cutoutpy) · [cutouts.py](#cutoutspy) · [fullcrop.py](#fullcroppy) ·
    [copy_photos.py](#copy_photospy)
- [Maps](#maps)
  - [routemap.py](#routemappy)
- [Websites](#websites)
  - [build.py](#buildpy) · [compliance.py](#compliancepy) · [preview.py (web)](#previewpy-web)
- [Utilities](#utilities)
  - [vprofile.py](#vprofilepy) · [offload.py](#offloadpy) · [spring.py](#springpy) · [setup.sh](#setupsh)
- [Library modules (no command line)](#library-modules-no-command-line)

## Conventions

- **Run from the repository root.** Paths in the synopses are relative to it (`python3 engine/qa.py ...`).
- **Profiles.** Every tool that reads brand colors, fonts, logos, folders or delivery specs takes
  `--profile NAME` (a folder under `profiles/`, or a path to a `profile.json`). Without it the tool uses
  `$VIDEO_PROFILE`, then `default_profile` in `local.json` (machine-only, not committed). The examples use the
  bundled [demo profile](../profiles/demo/profile.json); start your own from the
  [template](../profiles/_template/profile.json) or with `engine/vprofile.py new`. The profile API is described in
  [LAYOUT.md](LAYOUT.md).
- **QA.** Every video goes through `engine/qa.py` before anyone sees it. Several renderers print the arguments to
  use, for example `(qa: --kind motion --cuts none --holds end:2.4)`: pass exactly those. The
  [video-gates skill](../skills/video-gates/SKILL.md) explains how to read the review. "QA: n/a" below means the
  tool does not produce a finished video; its own check is named instead.
- **Common render options.** Most renderers take an output folder, either as a positional `<out_dir>` or as
  `--out DIR` (see each synopsis), and many also take `--name N` (output base name), `--fps N`, `--size WxH` and
  `--frames t1,t2,...` (render only stills at those times, for a fast look before a full render).
- **Local only.** Transcription (faster-whisper), segmentation (rembg / BiRefNet) and rendering run on your machine.
  Network use is limited to what a tool says it fetches: model downloads on first use, a page you ask
  `sourcecard.py` or `stage3d.py --url` to screenshot, and map data for `routemap.py --map osm`.
- **Alpha deliverables** are ProRes 4444 `.mov` files named `*_Alpha.mov`; each comes with an `.mp4` preview.
- **Exit codes.** Gate-style tools exit `0` on PASS, `1` on FAIL and `2` when the input cannot be read.

## Quick index

| Tool | Area | Purpose | QA |
|---|---|---|---|
| [`engine/qa.py`](#qapy) | QA | One-command review: spec, motion, audio, loudness, cuts, hook, holds | (the gate) |
| [`engine/motion_check.py`](#motion_checkpy) | QA | Dead stretches and stutters | run by qa.py |
| [`engine/audio_check.py`](#audio_checkpy) | QA | Hard audio cuts | run by qa.py |
| [`engine/sheet.py`](#sheetpy) | QA | Contact sheet of a time range | n/a |
| [`engine/beatmap.py`](#beatmappy) | Audio | Bar map: tempo, downbeats, sections, drop | n/a |
| [`engine/musicbed.py`](#musicbedpy) | Audio | Synthesized music bed | n/a |
| [`engine/sfx_build.py`](#sfx_buildpy) | Audio | Synthesized build, impact and sub drop | n/a |
| [`engine/talkedit.py`](#talkeditpy) | Editing | Talking head to a tight, captioned cut | `--qa` (edit) |
| [`engine/captions.py`](#captionspy) | Editing | Kinetic word-by-word captions | edit |
| [`engine/fxpack.py`](#fxpackpy) | Editing | Beat-placed cinematic effects pack | edit |
| [`engine/beatsnap.py`](#beatsnappy) | Editing | Snap an edit list's cuts to the beat | edit |
| [`engine/clip_plays.py`](#clip_playspy) | Editing | Stream-copy clips out of a long source | n/a |
| [`engine/calls.py`](#callspy) | Editing | Transcribe commentary around listed moments | n/a |
| [`engine/fcp7xml.py`](#fcp7xmlpy) | Editing | Edit list to Premiere-ready FCP7 XML | n/a |
| [`engine/vertical.py`](#verticalpy) | Editing | 9:16 social version of a 16:9 piece | edit |
| [`engine/flipbook.py`](#flipbookpy) | Editing | Photo bursts to a stop-motion pack | edit |
| [`engine/encode.py`](#encodepy) | Encoding | Masters, rewraps, verified copies | built-in verify, then edit |
| [`engine/statcard.py`](#statcardpy) | Graphics | Stats lower third (+ After Effects comp) | loop |
| [`engine/quote.py`](#quotepy) | Graphics | Pull-quote card with the speaker cut out | motion |
| [`engine/behind.py`](#behindpy) | Graphics | Big text behind the person | edit |
| [`engine/progressbar.py`](#progressbarpy) | Graphics | Progress bar with a face marker | edit |
| [`engine/beforeafter.py`](#beforeafterpy) | Graphics | Before / after divider sweep | motion |
| [`engine/sketch.py`](#sketchpy) | Graphics | Pencil sketch that paints into the real shot | motion |
| [`engine/hopwords.py`](#hopwordspy) | Graphics | Bouncing character over a lyric or short text | motion |
| [`engine/stage3d.py`](#stage3dpy) | Graphics | 3D card scenes (three.js) | motion |
| [`engine/measure.py`](#measurepy) | Graphics | Measure a reference piece, fit springs | n/a (SSIM compare) |
| [`engine/storyboard.py`](#storyboardpy) | Explainers | Pace, retime, check and board a storyboard | `check` |
| [`engine/explain.py`](#explainpy) | Explainers | Render an explainer storyboard | explainer |
| [`engine/sourcecard.py`](#sourcecardpy) | Explainers | Screenshot a page and box an exact phrase | n/a |
| [`logo/vectorize.py`](#vectorizepy) | Logos | Raster logo to layered SVG + hi-res PNG | n/a (fidelity score) |
| [`logo/fontmatch.py`](#fontmatchpy) | Logos | Rank fonts against lettering in a logo | n/a |
| [`logo/render3d.py`](#render3dpy) | Logos | 3D logo stills, swing loop and GLB | loop |
| [`logo/motion.py`](#motionpy-logo) | Logos | Animated logo templates with alpha | motion / loop |
| [`logo/preview.py`](#previewpy-logo) | Logos | Alpha PNGs on the brand color, stacked | n/a |
| [`logo/sr.py`](#srpy) | Logos | x4 AI super-resolution | n/a |
| [`engine/matte.py`](#mattepy) | People | Per-frame person matte from video | n/a (edge flicker) |
| [`engine/cutout.py`](#cutoutpy) | People | One photo to a clean transparent cutout | n/a |
| [`cutouts/cutouts.py`](#cutoutspy) | People | Find, cut, grade and file cutouts from a photo set | n/a (review sheets) |
| [`cutouts/fullcrop.py`](#fullcroppy) | People | Full-res crops from camera raw previews | n/a |
| [`cutouts/copy_photos.py`](#copy_photospy) | People | Copy crops into the cutout library | n/a |
| [`engine/routemap.py`](#routemappy) | Maps | GPX route drawn on a map | motion |
| [`web/build.py`](#buildpy) | Websites | site.json + profile to a static site | compliance.py |
| [`web/compliance.py`](#compliancepy) | Websites | Website compliance gate in a real browser | (the gate) |
| [`web/preview.py`](#previewpy-web) | Websites | Screenshots and a scroll-through video | n/a |
| [`engine/vprofile.py`](#vprofilepy) | Utilities | List, show, check and create profiles | `show --check` |
| [`engine/offload.py`](#offloadpy) | Utilities | Safe, resumable card offload | built-in verify |
| [`engine/spring.py`](#springpy) | Utilities | Spring presets (settle time, overshoot) | n/a |
| [`setup.sh`](#setupsh) | Utilities | Install and check dependencies | `--check` |

---

## QA and audio

### qa.py

The QA run: one command, one review folder, every machine check.

```
python3 engine/qa.py <video> [--profile NAME] [--kind edit|motion|explainer|loop]
        [--cuts 1.5,4.2,... | --cuts none | --shotlist <list.txt | cuts.json>] [--holds 3.5-4.0,start:N,end:N]
        [--intended end_tail,hook] [--max-scene 2.5] [--silences a-b,...] [--allow-stutter]
        [--size WxH] [--fps N] [--width 320] [--no-sheet] [--out DIR]
```

| Option | Meaning |
|---|---|
| `--kind` | `edit` (default): footage cut to music. `motion`: motion graphics (strict motion gate, hold gate). `explainer`: motion plus the freshness gate. `loop`: a loop or overlay (logo swing, corner bug, lower third): as motion, but the hook and end-tail gates are skipped. |
| `--cuts` / `--shotlist` | Planned cuts. Unplanned detected cuts are flagged. `--cuts none` means no cuts are planned; without either, cuts are only listed. `--shotlist` takes a render's concat list or a JSON list / `cuts` / `starts` / `shots[].start`. |
| `--holds` | Intentional stills, as in `motion_check.py`. |
| `--intended` | Gates that fail by design (`hook`, `hook_motion`, `hook_strong`, `end_tail`): a failure becomes an INFO line, never a silent PASS. |
| `--max-scene` | Explainer: longest stretch without a new visual (default 2.5 s). |
| `--silences` | Planned silences that are not flagged. |
| `--size`, `--fps` | Expected frame size and rate (default: the profile's delivery block). |
| `--allow-stutter` | Passed to `motion_check.py` for 24p material conformed to 30p. |

Checks: spec, motion, audio cuts, loudness and true peak, unplanned cuts, flashes, pops, clicks and dropouts, hook,
holds, and (explainers) freshness.
Outputs in `--out` (default `./qa_<video name>/`): `review.md` (verdict, one fix line per flag, gate and shot tables,
manual checks), `sheet.jpg` (timeline, one frame per shot with the safe area, evidence strips) and `qa.json`.
Exit `0` PASS, `1` FAIL, `2` unreadable. Needs ffmpeg/ffprobe, numpy and Pillow.

### motion_check.py

The motion gate: dead stretches (nothing moves that should) and stutters (a 1-2 frame repeat mid-motion).
Regular repeat cadences are reported once as a note, not as stutters.

```
python3 engine/motion_check.py <video> [--holds 3.5-4.0,start:N,end:N] [--strict] [--min-dead 0.5]
        [--still-frac 0.003] [--level 3] [--width 480] [--allow-stutter] [--sheet out.jpg] [--json out.json]
```

- `--strict`: motion-graphics mode (more than 3 flat frames in a row outside a hold is dead).
- `--sheet`: one image with the motion timeline and frames from every flagged span; read it instead of every frame.

Exit `0` PASS, `1` FAIL, `2` unreadable. QA: run by `qa.py` (with `--strict` for `--kind motion` and `--kind loop`).

### audio_check.py

Fails a mix on any drastic level change: every cut must fade, even quickly.

```
python3 engine/audio_check.py <video> [--cuts 1.6,8.2,...] [--drop 18] [--floor -32]
```

- Away from cuts only drops are judged (a fall of `--drop` dB or more from above `--floor` dBFS within 10 ms).
- At each `--cuts` time (plus or minus 60 ms) a jump either way of `--drop` dB fails.
- Steps into or out of silence are judged as fades or cuts by their shape (a linear fade of about 16 ms or longer
  passes at the default `--drop`).

Prints PASS or FAIL with timestamps. Exit `1` on FAIL, `2` when there is no audio. `--help` prints the usage from
its docstring. QA: run by `qa.py`.

### sheet.py

Contact sheet for review: frames spread evenly from `t0` to `t1`, each labeled with its time.

```
python3 engine/sheet.py <video> <out.jpg> <t0> <t1> [--n 12] [--cols 6] [--w 320] [--label TEXT]
```

Keep `t1` slightly before the end of the file (a frame at the exact end decodes black). No profile. QA: n/a.

### beatmap.py

The bar map of a music track for code edits: tempo, downbeats, sections, stops, pickups, risers, the drop and the
top hits. Used by `beatsnap.py`, `fxpack.py` and `talkedit.py`.

```
python3 -P engine/beatmap.py <track|video> [--start S] [--dur D] [--fps 29.97] [--bpm N] --out out/x/beatmap.json
python3 -P engine/beatmap.py <track> --choose-window 15 [--fps 29.97]      # suggest the best 15 s windows
```

- Times are film seconds from `--start`; frame numbers use `--fps` (default: the profile's `delivery.fps`, else 24).
- `--bpm` forces the tempo after checking by ear; the phase is still fitted.
- Run with `python3 -P` (or `-I`) when the input is downloaded media.

Outputs: `beatmap.json` and `beatmap.md` beside it. Also importable: `from beatmap import build`. QA: n/a; its beat
and drop times are what you pass to `qa.py --cuts`.

### musicbed.py

A simple music bed synthesized in code (no samples, no licenses): pad chords, a plucked arpeggio, a swell into the
drop, then kick and bass from the drop on.

```
python3 engine/musicbed.py <out.wav> --dur 60 [--bpm 92] [--drop 41.4] [--key D] [--prog 1,5,6,4] [--seed 3]
```

A bar starts exactly on `--drop`. Outputs a 48 kHz stereo WAV (peak -3 dBFS) and `<out>.json` with the bar times.
QA: n/a (audio only; the video that uses it goes through `qa.py`).

### sfx_build.py

Synthesizes a beat-synced build, impact and sub drop (no samples, no license).

```
python3 engine/sfx_build.py <out.wav> --bpm 152 --beats 8 --tail 2.2
```

The hit lands `beats * 60 / bpm` seconds into the file; the file runs `--tail` seconds past it and fades at both
ends. QA: n/a.

---

## Editing and encoding

### talkedit.py

One command turns a talking-head video into a tight, captioned cut in 16:9 and 9:16.

```
python3 engine/talkedit.py <video> --out DIR [--profile NAME] [--name N] [--start S --end S]
        [--music track.mp3 [--music-in S]] [--aspects 16:9,9:16] [--words-file W] [--model small.en]
        [--min-prob 0.35] [--fresh] [--plan-only] [--no-captions] [--caption-layer] [--crf 18] [--qa] [--preview]
```

What it does, with every number from the profile's `talkedit` block: local transcription (fillers kept so they
can be cut), pause and filler cuts in measured quiet with voice fades, punch-ins and spring push-ins, cutaway title
cards, pop-up stat and keyword cards, and kinetic captions.

- `--plan-only` writes the plan and stops: the fast way to tune.
- Hand edits survive re-runs: `<name>.talkedit.json` is reused as it is; `--fresh` moves it to `_old/` and plans again.
- `--music` cuts the cards on the beat; `--caption-layer` keeps the ProRes caption layer; `--preview` writes phone
  copies under 30 MB.

Outputs in `--out`: `<name>_16x9.mp4`, `<name>_9x16.mp4`, `<name>_16x9.xml` (Premiere), `<name>.talkedit.json`,
`<name>.words.json`, `<name>.srt`, `<name>.cuts.json`, `cards/`, plus `qa_16x9/`, `qa_9x16/` and `preview/` with
the flags above. Old outputs are moved to `_old/<stamp>/`, never overwritten.
QA: `--qa` runs `qa.py --kind edit` on every output with the planned cuts and holds filled in.

### captions.py

Kinetic captions: 1-4 word captions that spring in word by word, one keyword per caption in an outlined box.

```
python3 engine/captions.py <video> --out DIR [--profile NAME] [--aspect 16:9|9:16] [--words-file words.json]
        [--prompt "names, places"] [--model small.en] [--min-prob 0.35] [--start S --end S] [--name N]
        [--words-only] [--no-mov] [--no-mp4] [--crf 18] [--vertical-fill auto|band|crop]
```

- Fix spelling in `<name>.words.json` and re-run with `--words-file` (no transcription). Per word you can add
  `"key": true|false` (force or forbid the highlight) and `"break": true` (start a new caption).
- `--words-only` transcribes, groups and writes the `.srt` without rendering.
- `--aspect 9:16` from a 16:9 source: the frame as a band over a blurred copy, captions under it; pillarboxed
  portrait clips fill the frame (`--vertical-fill auto`, shot list in `<name>.fill.json`).
- Style comes from the profile's `captions` block.

Outputs: `<name>.words.json`, `<name>.captions.json` (rule breaks under `"violations"`), `<name>.srt`,
`<name>_captions_<16x9|9x16>.mov` (alpha layer), `<name>_captioned_<16x9|9x16>.mp4` (burned in, audio copied).
QA: `--kind edit` with the source's planned cuts. In 9:16, compare with a run on the uncaptioned source before
fixing extra "unplanned cut" flags.

### fxpack.py

A cinematic edit pack placed on the bar map: flash cuts, zoom punches with radial blur, RGB split, speed ramps,
whip pans, black and white with one hue kept, and kinetic text.

```
python3 engine/fxpack.py <plan.json> --out DIR [--name N] [--profile NAME] [--fps 29.97] [--size 1920x1080]
        [--frames t1,t2] [--plan-only]
```

- `plan.json` holds the music, the shots (each a whole number of beats; a `hero` shot lands on the drop), optional
  kinetic text, and `"fx": "auto"` or an explicit list (`flash`, `zoom`, `rgb`, `ramp`, `whip`, `pop`, `text`).
- Every effect must have a music event within one frame and a measured reason in the picture; otherwise nothing
  renders (exit 3) and the effect is listed.
- `--plan-only` writes the timeline and effects JSON and stops.

Outputs: `<N>_fx.mp4`, `<N>_fx.xml` (Premiere, one marker per effect), `<N>_fx.json`.
QA: `--kind edit --cuts <the list it prints>`.

### beatsnap.py

Moves an edit list's cut points onto the music's beats (OUT points only, never IN points). Writes the edit back in
place, so copy it first.

```
python3 engine/beatsnap.py <edit.json> [<music file>] [--open 1.6] [--max-shift 0.25] [--barmap auto|beatmap.json]
        [--big-key big] [--payoff N] [--down-shift 1.0] [--drop-shift 1.5] [--legacy-beats] [--profile NAME]
```

- Default mode uses the `beatmap.py` grid (`--barmap auto`). Cuts into "big" items (`--big-key`, a dotted key) land
  on a downbeat; the cut into the payoff item (`"payoff": true` or `--payoff N`) lands on the drop; no cut lands
  inside a music stop.
- `--open` is the opener length before the first item; pass `0` when there is none.
- With the music file left out, the edit's own music path is used, mapped for this machine by the profile.
- `--legacy-beats` is the older librosa snap, kept for comparison.

QA: render the edit, then `--kind edit --shotlist <the render's concat list>` (or `--cuts`).

### clip_plays.py

Cuts every listed moment out of a long source video with stream copy (no re-encode). Never touches the source.

```
python3 engine/clip_plays.py <source.mp4> <plays.json> <out_dir> [--seconds 150] [--only 3,7,12]
```

- `plays.json`: `{"plays": [{"n": 12, "start": 3601.5, "end": 3622.0, ...}]}`; optional fields name the clip.
- Time-sliced: it stops after `--seconds` and prints `TIMESLICE`; rerun until it prints `DONE`. Existing clips are
  skipped.
- Stream-copy cuts land on keyframes: encode the source with short keyframe intervals for tight cuts.

`--help` prints the usage from its docstring. QA: n/a (source clips).

### calls.py

Transcribes the commentary around listed moments (local faster-whisper) so an editor can name who did what. Names
come only from what was said, never guessed.

```
python3 engine/calls.py <idx_dir> [--plays 5,17,40] [--minrank 7] [--model small.en] [--roster a.csv,b.csv]
        [--context "Sports broadcast, ACME Hawks"] [--profile NAME]
```

Reads `<idx_dir>/plays.json` and `<idx_dir>/audio16k.opus`; the window per moment is 3 s before to 20 s after.
Roster names go into the prompt for spelling; `--context` (else the profile's `transcribe.context`) opens it.
Output: `<idx_dir>/calls.json` (`{n: text}`). `--help` prints the usage from its docstring. QA: n/a.

### fcp7xml.py

Edit list (JSON) to Final Cut Pro 7 XML (xmeml v5), which Premiere Pro imports with File > Import.

```
python3 engine/fcp7xml.py <edit.json> <out.xml>
python3 engine/fcp7xml.py --single <render.mp4> [out.xml] [--path "<path Premiere sees>"]
```

- `edit.json` holds `name`, `fps`, `w`, `h`, `files`, `items` (V1 / A1-2, back to back, optional `scale`),
  `music`, `markers` and `overlays` (V2); see the docstring for the full schema.
- Paths are written as given: use the paths of the editing machine.
- `--single` wraps one finished render as a one-clip sequence at its own size, rate and audio.

QA: n/a.

### vertical.py

A 9:16 (1080x1920) social version of a finished 16:9 piece, without re-cutting it: the full frame as a band over a
blurred moving copy, the brand header above, the footer below and clear of the app UI.

```
python3 engine/vertical.py <in_16x9.mp4> <out_9x16.mp4> [--profile NAME] [--kicker TEXT] [--head TEXT]
        [--sub TEXT] [--foot TEXT] [--sponsor TEXT] [--assets DIR] [--fontdir DIR]
```

Brand (logo `brand.logo_png`, fonts, colors, `team.foot`, `brand.watch_line`) comes from the profile;
`--assets` / `--fontdir` override its assets folder and fonts. Audio is copied untouched, so the input needs an
audio track. QA: `--kind edit` with the same cuts as the 16:9.

### flipbook.py

Turns photo bursts into a fast stop-motion "action pack" with an end card.

```
python3 engine/flipbook.py <plan.json> <frames dir> <out.mp4> [--profile NAME] [--wide] [--fps-photo 12]
        [--label TEXT] [--root DIR] [--fontdir DIR] [--slam DIR] [--keep-temp]
```

- `plan.json`: `[{"name": ..., "wk": ..., "frames": ["IMG_0001", ...], "opp": "..."}]` in play order.
- Vertical 1080x1920 by default; `--wide` for 1920x1080. `--fps-photo` sets how many photos a second.
- `--slam DIR` uses PNG frames for the end-card slam (default: frames from the profile's
  `brand.logo_3d_swing_alpha_mov`); `--root` re-roots the profile's assets; `--keep-temp` keeps the working frames.

QA: `--kind edit`; judge any repeated-frame flags on the sheet against `--fps-photo`.

### encode.py

Builds, rewraps, copies and verifies delivery masters with ffmpeg, using an encode preset from the profile.

```
python3 engine/encode.py master INPUT... -o OUT.mp4 [--preset NAME] [--b-v 12M --maxrate 14M --bufsize 24M]
        [--faststart | --no-faststart] [--full-verify] [--no-verify] [--force] [--log FILE] [--profile NAME]
python3 engine/encode.py rewrap IN.ts [-o OUT.mp4]
python3 engine/encode.py copy-verify FILE... --to DIR|<profile paths key>
python3 engine/encode.py verify FILE [--expect SECONDS | --like INPUT...] [--tol 2] [--full-verify]
```

- `master`: one ffconcat list (in/out points honored) or several media files; video encoded with
  `delivery.<preset>` (default `delivery.default_preset`, else `web`), audio copied.
- Every output is written as `<name>.partial.mp4` and renamed on success; an existing output is never replaced
  without `--force`.
- Log protocol: `=== START <mode>` ... `=== DONE <mode>` or `=== FAILED <mode>`, with `ENCODE_FAIL`,
  `VERIFY_FAIL`, `REWRAP_FAIL`, `COPY_FAIL` or `FATAL: <reason>` before a failure. Default log:
  `<output folder>/.enc/encode.log`. `--no-caffeinate` lets the Mac sleep.

QA: the built-in verify (decode errors and duration, `VERIFY_OK` / `VERIFY_FAIL`), then `qa.py --kind edit` on the
master. ffmpeg notes: [ffmpeg-notes.md](ffmpeg-notes.md).

---

## Motion graphics and cards

Every move in these tools is a closed-form spring ([spring.py](#springpy)), so each frame is a pure function of
time. More on the motion rules: [engine/README_motion.md](../engine/README_motion.md).

### statcard.py

A stats lower third: cutout photo, `#NN NAME`, one big stat line and a row of 2-4 label/value pairs that count up.

```
python3 engine/statcard.py <stats.json> <out_dir> [--name N] [--profile NAME] [--size WxH] [--fps N]
        [--dur 5.5] [--start 0] [--bg image|video|'#hex'] [--bg-in S] [--frames t1,t2] [--no-logo] [--ae]
        [--x0 PX] [--x1 PX] [--y1 PX]
```

- `stats.json`: `num`, `name`, `photo`, `big`, `stats` (2-4 pairs), `count`. Example:
  [stats_card_example.json](stats_card_example.json).
- `--x0` / `--x1` / `--y1`: the panel's left edge, right limit and bottom edge in pixels (default: the profile's
  safe area).
- `--ae` also writes `<N>_stats.jsx` and `<N>_stats_ae/`: run it in After Effects (File > Scripts > Run Script
  File) for a native comp with real text layers and every spring baked to keyframes.

Outputs: `<N>_stats_Alpha.mov`, `<N>_stats.mp4` (preview on `--bg`), `<N>_stats.png` (settled card, transparent).
QA: `--kind loop --cuts none` (a lower third has no opening, so `--kind motion` fails the hook gate).

### quote.py

A quote callout: the speaker cut out on one side, their words as a big serif pull-quote on the other.

```
python3 engine/quote.py --text "..." --by "Jane Doe" [--role "..."] --out DIR [--name N]
        (--matte <name>_matte.json [--at S] | --cutout person.png) [--bg video.mp4 [--bg-t S] | --bg '#hex']
        [--dur S] [--fps 29.97] [--size 1920x1080] [--frames t1,t2] [--profile NAME]
```

The person comes from a `matte.py` window (the frame `--at` seconds in) or any cutout PNG. The quote face is the
profile's `quote` font role, else the bundled Fraunces (OFL). Outputs: `<name>_quote.mp4`, `<name>_quote_Alpha.mov`.
QA: `--kind motion --cuts none --holds end:2.4` (printed).

### behind.py

Big text behind the person: one word for a window, timed events, or words picked automatically from a transcript,
set between the background and the speaker using a `matte.py` matte.

```
python3 engine/behind.py <video> --out DIR [--name N] [--t0 S] [--t1 S] [--profile NAME]
        (--text "WORD" | --events events.json | --auto words.json) [--every 3.5] [--matte <name>_matte.mp4]
        [--fill solid|gradient|<image>] [--color text|accent|'#hex'] [--size 0.30] [--rotate cw|ccw|180]
        [--max-height 1080] [--layer] [--frames t1,t2]
```

- `--events`: `[{"text": "WORD", "t0": 1.2, "t1": 3.4}]`; `--auto`: a faster-whisper `words.json`, one word per
  phrase at least `--every` seconds apart.
- `--matte` reuses an existing matte of the same window (else `matte.py` runs first).
- `--layer` also writes the text with the person cut out of it, to lay over the original in an NLE.

Outputs: `<name>_behind.mp4`, `<name>_behind.events.json`, and with `--layer` `<name>_behind_text_Alpha.mov`.
QA: `--kind edit --cuts none` (add `--intended hook` for an insert).

### progressbar.py

A thin progress bar along the bottom of a long talk that fills with the video, the speaker's face riding the head
of the fill, chapter ticks and chapter titles.

```
python3 engine/progressbar.py <video> --out DIR [--name N] [--t0 S] [--t1 S]
        (--face face.png | --matte <name>.json) [--chapters chapters.json] [--fps N] [--frames t1,t2] [--profile NAME]
```

`--chapters`: `[{"t": 0, "title": "Welcome"}, {"t": 95.5, "title": "The story"}]`. Outputs:
`<name>_progress_Alpha.mov` (full-frame overlay) and `<name>_progress.mp4` (over the video, with sound).
QA: `--kind edit --cuts none --intended hook` (an overlay has no hook); render at the profile's rate.

### beforeafter.py

One frame, a divider that sweeps across to show the change between two takes of the same framing.

```
python3 engine/beforeafter.py --before A --after B --out DIR [--name showcase] [--a0 S] [--b0 S] [--dur 6.5]
        [--labels "BEFORE|AFTER"] [--fps 29.97] [--size 1920x1080] [--frames t1,t2] [--profile NAME]
```

`A` and `B` are videos or stills; `--a0` / `--b0` are their in-points. Sound is B's, leveled to the profile.
Output: `<name>_ba.mp4`. QA: `--kind motion --cuts none` (printed); add `--intended hook` when it is an insert.

### sketch.py

A pencil drawing of the first frame draws itself stroke by stroke, shades in, then the real footage paints in through
it and plays on. OpenCV only.

```
python3 engine/sketch.py <video|still> --out DIR [--name sketch] [--t0 S] [--dur 6.0] [--draw 2.2]
        [--fps 29.97] [--size 1920x1080] [--frames t1,t2] [--profile NAME]
```

Output: `<name>_sketch.mp4` with the source's sound from where the footage starts to play.
QA: `--kind motion --cuts none` (printed) plus `--silences 0-<the real-shot time it prints>`.

### hopwords.py

A 2D bouncing character hops word to word through a lyric or short text; each word lights up as it lands.

```
python3 engine/hopwords.py --text "the words" --out DIR [--name N] [--profile NAME]
        [--audio voice.wav | --words words.json | --chart chart.txt | --wpm 110] [--ref "Source line"]
        [--character art.png|art.svg] [--aspect 16:9|9:16] [--bg profile|gradient|'#hex'|image|none]
        [--bg-dim 0.62] [--lead 1.0] [--tail 1.4] [--fps N] [--frames t1,t2] [--model small.en] [--prompt TEXT]
```

- Word times, first found wins: `--words`, `--audio` (transcribed locally and saved as `<name>.words.json`),
  `--chart` (one cue a line: `<seconds or m:ss.ss> <word or phrase>`), `--wpm`.
- `--character` must be owned or original art; without it a placeholder bean is drawn in the accent color.
- `--bg none` also writes an alpha `.mov`.

Outputs: `<name>_hop.mp4`, `<name>_hop_Alpha.mov` (with `--bg none`), `<name>.timing.json`.
QA: `--kind motion --cuts none`.

### stage3d.py

The 3D card engine: three.js scenes rendered frame by frame in headless Chromium, lit with a warm key, cool rim and
contact shadows.

```
python3 engine/stage3d.py <scene> <out_dir> <Name> [scene options] [--spec settings.json] [--alpha]
        [--bg gradient|mesh] [--fps 30] [--size WxH] [--dur S] [--frames t1,t2] [--profile NAME]
```

| Scene | What it is | Main options |
|---|---|---|
| `data` | Bars, count-up cards and point clouds, camera always moving | `--data sections.json` or a `label,value` CSV ([sample](../examples/stage3d/sample_data.json)) |
| `orbit` | Glass cards orbit a presenter, passing in front and behind | `--cards "A\|B\|C"`, `--matte <name>_matte.json` |
| `stack` | 3D stack of real screenshots | `--shots a.png,b.png` or `--url URL` (repeat), `--shot-size 1440x900` |
| `burst` | Title cards swapped behind light bursts | `--lines "A\|B\|C"` |
| `badge` | Two badges fly in and clash | `--text1`, `--text2` |
| `toggle` | Settings panel whose switches flip on | `--labels "A\|B\|C"` |
| `props` | Glossy icon props | `--icons check,star,heart,bolt,play,plus,pin,chat` |
| `reveal` | Brand glow, phone, panels, toast, tagline | `--shots` / `--url`, `--panels`, `--toast`, `--tagline` |
| `hop` | A mascot hops platform to platform on word times | `--text`, `--words` / `--chart` / `--wpm 110`, `--character` |
| `fly` | UI flythrough over a tilted screenshot | `--shots` / `--url`, `--focus` (JSON list of `{x,y,w,h,label}`) |
| `extrude` | 3D extruded type flythrough landing on the lockup | `--text "WORD"` or `--svg mark.svg` |

Outputs: `<Name>_<scene>.mp4`; `--alpha` adds `<Name>_<scene>_Alpha.mov` (shadows kept in the alpha). `orbit`
also writes `<Name>_orbit_front_Alpha.mov` and `<Name>_orbit_back_Alpha.mov`.
QA: `--kind motion --cuts <the times it prints>`. Render with `--fps` at the profile's delivery rate (`--fps 29.97`
on the demo profile): stage3d defaults to 30 fps, and the QA spec gate fails a 30 fps file on a 29.97 profile.

### measure.py

Measures a finished motion piece (a show open, a sting, a lower third) so it can be rebuilt on springs in
`logo/motion.html`. ffmpeg, OpenCV, numpy and scipy only.

```
python3 engine/measure.py probe   <video> --out DIR [--start S] [--end S] [--dump] [--cut-min 10] [--cut-hist 0.75]
        [--flash 25] [--events 12]
python3 engine/measure.py track   <video> --out DIR --start S --end S --ref T --el name:x,y,w,h [--el ...]
        [--scale 0.5] [--min-rho 0.55]
python3 engine/measure.py fit     DIR/track.json [--out DIR/fit.json] [--max-springs 2] [--only a,b] [--start-at S]
        [--op-step 0.1]
python3 engine/measure.py compare <original> <rebuild> --out side.mp4 [--start S] [--dur S] [--labels "A|B"] [--audio]
```

| Command | Writes |
|---|---|
| `probe` | `probe.json` and `probe.jpg`: cuts, flashes, motion events and each shot's palette (`--dump` saves every frame) |
| `track` | `track.json` and `track.jpg`: position, scale, rotation and opacity of each `--el` box against time |
| `fit` | `fit.json` and `fit.jpg`: springs fitted to every moving channel, the nearest preset and a ready `motion.html` call |
| `compare` | a side-by-side MP4 with a per-frame SSIM graph and `<out>.ssim.csv` |

QA: n/a; `compare` is the check (both videos at the same frame rate).

---

## Explainers

A worked example lives in [examples/explain/lissajous](../examples/explain/lissajous/storyboard.json); the steps
are in [examples/README.md](../examples/README.md).

### storyboard.py

Tools for the explainer storyboard: one beat per spoken line, a new visual every 1-2 s, times snapped to the words.

```
python3 engine/storyboard.py pace   <sb.json> [--wps 2.6] [--min 1.6] [--pad 0.45]   # time beats from the text
python3 engine/storyboard.py retime <sb.json> (--vo vo.wav | --words vo.words.json)   # snap beats to the voice-over
python3 engine/storyboard.py check  <sb.json> [--max-scene 2.5]                      # the rules; exit 1 on a FAIL
python3 engine/storyboard.py board  <sb.json> --out DIR [--profile NAME]             # approval sheet
```

`check` enforces: every beat has a line and something on screen, beats are contiguous, no stretch longer than
`--max-scene` without a planned new visual, 2.0-3.5 words a second, motion in the first beat, known element types,
and images that exist. The format is in the docstring. QA: `check` before rendering; the render goes through
`qa.py --kind explainer`.

### explain.py

Renders an explainer from a `storyboard.json` with `engine/explain.html`: one continuous canvas, spring motion,
captions that land word by word.

```
python3 engine/explain.py <storyboard.json> --out DIR [--name N] [--profile NAME] [--aspect 16:9|9:16] [--fps N]
        [--frames t1,t2] [--board] [--vo voice.wav] [--music bed.wav] [--music-db -18] [--no-music]
```

- `--board` writes one still per beat tiled into `<name>_board.jpg` for approval before the full render.
- `--vo` and / or `--music` (for example from `musicbed.py`); the mix is leveled to the profile's
  `delivery.loudness_lufs`. `--music-db` sets the bed under the voice.
- Colors come from the profile (`explain.signal`, `explain.hot`, `explain.key` override the defaults).

Outputs: `<name>.mp4` and `<name>.xml` (Premiere: one clip a beat, a marker on each).
QA: `--kind explainer --cuts none` (or the planned cuts) `[--max-scene 2.5]`.

### sourcecard.py

Screenshots a real page and finds an exact phrase on it, so an explainer can slide the page in and land a
highlight box on the words. The page is only read; nothing is posted.

```
python3 engine/sourcecard.py <url or file.html> "<exact phrase>" <out.png> [--width 1280] [--height 760]
        [--context 0.55] [--wait 1.0] [--dark] [--also "<another phrase>" ...]
```

- `--context`: where the phrase sits vertically in the crop (0-1). `--dark` hides fixed overlays such as cookie
  banners. `--also` boxes more phrases on the same screenshot (repeatable).

Outputs: `<out.png>` and `<out.json>` (`box`, per-line `rects`, `groups`, `credit`) for an `image` element in the
storyboard. Exit `1` when the phrase is not on the page. QA: n/a.

---

## Logos

Setup: `logo/setup.sh` (npm packages, Playwright Chromium, the super-resolution models). Full guide:
[logo/README.md](../logo/README.md).

### vectorize.py

Any raster logo (low-res PNG, JPG, screenshot) to a clean layered SVG and a transparent hi-res PNG.

```
python3 logo/vectorize.py <input.png|jpg> <out_dir> <name> [--colors N] [--palette "#112233,#E04050,#FFFFFF"]
        [--bg auto|none|#hex] [--png-width 4000] [--detail 1.0] [--target 2400] [--flatten-shading] [--bg-light 74]
```

- `--palette`: found colors near a brand color snap to it, and a found color far from every brand color stays
  as its own layer; `--detail` above 1 keeps smaller details, below 1 smooths.
- `--flatten-shading` for logos that are already 3D, embossed or photographed.

Outputs: `<name>.svg`, `<name>_Transparent_<W>px.png`, `<name>_vector_check.png` (original, vector, difference).
QA: n/a; it prints a fidelity score. Under 0.97 silhouette IoU, look closely (or redraw with `logo/redraw.py`).

### fontmatch.py

Finds the font that best matches a line of lettering in a logo image.

```
python3 logo/fontmatch.py <image> "<TEXT>" x0,y0,x1,y1 <fonts_dir> [--thresh 72] [--top 6]
```

The box is in image pixels. `--thresh` is the L* cut for the letter mask (negative for light letters). Writes
`fontmatch_<text>.png` with the top matches overlaid; 0.80 IoU or better is usually the same family. QA: n/a.

### render3d.py

A 3D logo from an SVG: 4K stills, a seamless swing loop with alpha and a GLB model.

```
python3 logo/render3d.py <logo.svg> <out_dir> <name> [--depth 0.03] [--fill 0.78] [--anim swing|spin]
        [--spin-seconds 4] [--fps 60] [--bg 112233] [--hero 0.10,-0.30] [--still-only] [--drop-bg] [--profile NAME]
```

Outputs: `<name>_3D_Hero_4K.png`, `<name>_3D_Front_4K.png`, `<name>_3D_Swing_Alpha.mov`, `<name>_3D_Swing.mp4`
(on `--bg`, default the profile's primary color) and `<name>_3D.glb`.
QA: `--kind loop --cuts none --fps 60` on the swing.

### motion.py (logo)

Animated logo graphics with a transparent background, rendered from `logo/motion.html`.

```
python3 logo/motion.py <logo.svg> <out_dir> <Name> <template> [--text1 TEXT] [--text2 TEXT] [--text3 TEXT]
        [--svg2 new.svg] [--sponsor img.png] [--plate img.png] [--fps 60] [--size 1920x1080] [--bg 112233]
        [--accent "#E04050"] [--depth 0.03] [--dur S] [--place cx,cy,bw,bh] [--write S]
        [--finish dark [--mockup laptop]] [--png-seq] [--frames t1,t2] [--profile NAME]
```

Templates: `slam`, `intro`, `outro`, `bug` (writes `bug_in`, `bug_loop`, `bug_out`), `stinger`, `presented`,
`lockup`, `writeon`, `morph`, `pixelbuild`, `linebuild`, `echo`, `lightstreak`, `lightpaint`, `swap`, `shatter`,
`brandgrid`. A sample `lightpaint` story: [placeholder_story.svg](../logo/stories/placeholder_story.svg).

- `--finish dark` adds a cinematic finish (bloom, reflective floor, depth of field, grain) from the profile's
  `finish.dark` block; the output is then opaque.
- `--png-seq` writes a transparent PNG sequence instead of encoding.

Outputs: `<Name>_<template>_Alpha.mov` and `<Name>_<template>.mp4` (preview on `--bg`). Templates with a hit or cut
point print it as `qa: --cuts <t>`.
QA (add `--fps 60` for a 60 fps render):

| Template | qa call |
|---|---|
| `intro` | `--kind motion --cuts none --fps 60 --intended end_tail --holds end:2.2` |
| `outro`, `slam`, `lockup` | `--kind motion --cuts none` (`slam`: `--holds end:<s after landing>` when `--dur` is long) |
| `writeon` | `--kind motion --cuts <hit> --holds end:2.0` |
| `morph`, `pixelbuild`, `lightstreak` | `--kind motion --cuts <hit> --holds end:1.6` |
| `linebuild` | `--kind motion --cuts <hit> --holds end:1.5` |
| `lightpaint` | `--kind motion --cuts <hit> --holds end:1.1` |
| `swap` | `--kind motion --cuts <hit> --holds end:1.45 --intended hook` |
| `shatter` | `--kind motion --cuts <hit> --holds end:1.4` |
| `brandgrid` | `--kind motion --cuts <hit> --holds end:2.2` |
| `bug_in` / `bug_loop` / `bug_out` | `--kind loop --cuts none` with `--holds start:0.1` / `--holds 0-6` / `--holds end:0.1` |
| `presented`, `stinger`, `echo` | `--kind loop --cuts none` |

The hold values are starting points; widen a hold to the logo's settle point when the sheet shows it at rest.

### preview.py (logo)

Contact sheet: alpha PNGs composited on the profile's primary color, each fitted to 1280x720, stacked.

```
python3 logo/preview.py <out.png> <in1.png> [in2.png ...] [--profile NAME]
```

QA: n/a.

### sr.py

x4 AI super-resolution (EDSR, or FSRCNN for inputs over 600 px). Runs in the `logo/srenv` virtual environment that
`logo/setup.sh` creates; `vectorize.py` calls it for small inputs.

```
logo/srenv/bin/python logo/sr.py <in.png> <out.png>
```

Two positional arguments; `--help` prints the usage. QA: n/a.

---

## People and cutouts

Segmentation models (BiRefNet, U^2-Net via rembg; MODNet) are free and run locally. They live in `$U2NET_HOME`, else
`rembg_models` in `local.json`, else `resources/models/rembg`; rembg downloads a missing model on first use.

### matte.py

A per-frame person matte from video, refined at the edges and held steady from frame to frame, for compositing
(text behind the person, cards behind or in front).

```
python3 engine/matte.py <video> --out DIR [--name N] [--t0 S] [--t1 S]
        [--model birefnet-general|birefnet-portrait|modnet|u2net_human_seg] [--infer 512] [--steady 0.85]
        [--choke 0] [--feather 1.0] [--min-region 0.15] [--bg profile|'#hex'|image|blur|none] [--max-height 1080]
        [--rotate cw|ccw|180] [--frames t1,t2] [--profile NAME]
```

- `birefnet-general` (default) is the most complete but slow (seconds a frame on a CPU: run long clips in the
  background); `modnet` is fast and fine for drafts; `u2net_human_seg` suits small, far figures.
- `--steady` trades shimmer for lag (0 = raw per frame, 0.9 = very steady). `--rotate` fixes phone clips whose
  rotation tag is wrong.

Outputs: `<name>_matte_Alpha.mov`, `<name>_matte.mp4` (grayscale alpha), `<name>_matte_preview.mp4`,
`<name>_matte.json` (settings and edge flicker). QA: n/a; check the edge flicker in `_matte.json` (under about 0.05
reads as solid) and watch the preview.

### cutout.py

One photo to a clean transparent cutout: BiRefNet general, a 2 px choke with a soft edge, white spill removed.

```
python3 engine/cutout.py <in.jpg> <out.png> [<in2.jpg> <out2.png> ...]
```

No profile values (a `--profile NAME` pair is accepted and ignored). QA: n/a.

### cutouts.py

Finds, cuts, grades and files person cutouts from a culled photo set. Takes `--profile NAME` for the uniform colors
(`team.uniform`), the review-sheet color, the label font and the abbreviation in file names. Full workflow:
[cutouts/README.md](../cutouts/README.md).

```
python3 cutouts/cutouts.py candidates <cull dir> <label>                 # cut_requests.json + cutcand_N.jpg sheets
python3 cutouts/cutouts.py cut <crops dir> <numbers.json> <out dir> [<frame>=A|B|X ...]
python3 cutouts/cutouts.py library <out dir> <roster.csv> <library dir> --games-map <cull dir>/rows.json [...]
```

- `candidates` keeps one frame per burst with one dominant, uncropped, large enough person in the uniform colors.
  Read the sheets and write the readable numbers into `numbers.json` (`{"IMG_0001": "12", "IMG_0002": null}`).
- `cut` grades each cutout A (full body), B (cut at the frame bottom) or X (rejected) and writes `png/`,
  `grades.json` and `review_N.jpg`. Override a wrong grade by adding `<frame>=A|B|X` arguments.
- `library` files the cutouts as `<library>/#<n> <Name>/{Cutouts,Portraits,Action}` with `_index.csv`,
  `_Overview.jpg` and `lib_plan.json`.

`--help` prints the usage. QA: n/a; look at every review sheet.

### fullcrop.py

Cuts each requested person out of the full-size JPEG preview embedded in camera raw files (`.CR3`), with padding.

```
python3 cutouts/fullcrop.py <photos root> <cut_requests.json> <out dir> [--seconds 150]
```

Looks for raws under `<photos root>/*/Photos/**`. Time-sliced and resumable: rerun until it prints `DONE`. Output:
`<out>/<name>.jpg`. `--help` prints the usage. QA: n/a.

### copy_photos.py

Copies the full-res crops into the cutout library, following the `lib_plan.json` that `cutouts.py library` wrote.

```
python3 cutouts/copy_photos.py <crops dir> <lib_plan.json> <library dir>
```

Never overwrites an existing file; prints how many it copied. `--help` prints the usage. QA: n/a.

---

## Maps

### routemap.py

A GPX route drawn on a map, the camera following the line while the distance counts up.

```
python3 engine/routemap.py <route.gpx> --out DIR [--name route] [--dur 7] [--labels "Start|Finish"]
        [--map naturalearth|osm] [--fps 29.97] [--size 1920x1080] [--frames t1,t2] [--profile NAME]
python3 engine/routemap.py --gpx-from-videos "<folder or glob>" --gpx-out route.gpx
```

- `--map naturalearth` (default): public-domain Natural Earth layers, offline after one download, for regional
  routes. `--map osm`: OpenStreetMap data via the Overpass API for city-scale routes, cached, with the on-screen
  credit its license requires.
- `--gpx-from-videos` builds a GPX track from phone clips' location tags and creation dates.
- Distance units follow the profile.

Output: `<name>_route.mp4`. QA: `--kind motion --cuts none --holds end:1.0` (printed).

---

## Websites

A site is one `site.json` (hero template W1-W5 plus section kit) and a profile. Examples:
[demo-studio](../examples/sites/demo-studio/site.json), [demo-world](../examples/sites/demo-world/site.json).

### build.py

Builds a static site with the brand from the profile and the compliance checklist built in: drafted legal pages,
consent-safe forms, alt text and asset licenses, and `ui` springs that respect reduced motion. No tracking by
default.

```
python3 web/build.py <site.json> --out DIR [--profile NAME]
```

Hero templates (in `web/templates/`): `w1` scroll-built story, `w2` 3D isometric scroll world, `w3` drone flyover,
`w4` cinematic service business, `w5` 3D glass showcase. Section types: `stats`, `features`, `process`, `area`,
`gallery`, `form`, `faq`, `cta`, `text`. Output: the site in `--out`, with `assets.json`.
QA: run `web/compliance.py` on the output, then `web/preview.py`.

### compliance.py

The website compliance checklist as a gate, run against the built site in a real browser: legal pages and footer
links, consent banner behavior (no third-party request before a choice), forms, third-party audit, no dark
patterns, alt text, measured text contrast, keyboard focus, business details, asset licenses, no sideways scroll.

```
python3 web/compliance.py <dist dir> [--site site.json] [--out report.md]
```

The default report is `<dist>_compliance.md`, beside the folder that gets deployed, never inside it. It ends with
"Needs the owner" (decisions and missing facts only). Exit `1` when anything fails.

### preview.py (web)

Looks at a built site: desktop and phone screenshots of every section and a scroll-through video.

```
python3 web/preview.py <dist dir> --out DIR [--name site] [--seconds 14]
```

Outputs: `<name>_desktop.jpg`, `<name>_phone.jpg`, `<name>_laptop.jpg`, `<name>_scroll.mp4`.
QA: n/a. Do not run `qa.py` on `_scroll.mp4`: it fails by design (no sound, screen size and rate, load and end
holds), and none of that is a fault in the site.

---

## Utilities

### vprofile.py

Lists, shows, checks and creates profiles. A profile holds everything about one organization (brand, folders,
house style); tools never hard-code those values. The profile API for tool authors is in [LAYOUT.md](LAYOUT.md).

```
python3 engine/vprofile.py list
python3 engine/vprofile.py show [NAME] [--check]              # --check: every font and folder exists here
python3 engine/vprofile.py new NAME [--display "ACME Hawks"] [--primary "#112233"] [--accent "#E04050"]
        [--head-font F] [--body-font F] [--logo logo.svg] [--root DIR] [--sample]
python3 engine/vprofile.py default NAME                       # writes local.json (machine-only)
python3 engine/vprofile.py sample NAME card.png               # brand check card: logo, colors, contrast, fonts
```

QA: `show --check`.

### offload.py

Offloads a camera card (or any folder) to a destination, safely and resumably. The source is strictly read-only;
every copy lands as `<name>.part` and is renamed only after a verify.

```
python3 engine/offload.py SRC DST [--files-from LIST] [--date YYYY-MM-DD[,YYYY-MM-DD]] [--since "YYYY-MM-DD HH:MM"]
        [--until "YYYY-MM-DD HH:MM"] [--ext CR3,JPG,MP4,MOV] [--flat] [--verify cmp|md5|size] [--verify-existing]
        [--conflict skip|rename] [--label LABEL] [--log FILE] [--check-only [--sample N]] [--histogram]
        [--dry-run] [--progress 250] [--no-caffeinate] [--profile NAME]
```

- `SRC` may be a card name from the profile's `cards` block.
- Re-runs resume: a same-size file at the destination is skipped; a different file with the same name is never
  overwritten (`CONFLICT`, or `--conflict rename`).
- `--dry-run` lists what would be copied; `--check-only` copies nothing and verifies `DST` against `SRC`.
- The last line is `<LABEL>_COMPLETE ...` (default `ALL_COMPLETE`) or `<LABEL>_INCOMPLETE ...` with exit `1`;
  scripts can wait on it. The log defaults to `<DST>/_offload_<date>.log`.

QA: the built-in verify (byte compare by default).

### spring.py

Closed-form damped springs, the same math and presets as `engine/spring.js`. Every animated tool uses them.
Run it to print each preset's settle time and overshoot:

```
python3 engine/spring.py
```

Presets: `snappy`, `bouncy`, `slam`, `smooth`, `gentle`, `ui`, `uiExit`. From code:
`from spring import spring_at, settle, PRESETS` (plus `handheld`, `shake`, `camera_at`). QA: n/a. Tests:
`tests/test_spring.py`.

### setup.sh

Sets up the engine on a Mac (Apple silicon and Homebrew): Homebrew formulas, pip requirements, the logo tools, and a
profile check. Safe to run again.

```
./setup.sh [--check] [--no-brew] [--no-pip] [--no-logo] [--profile NAME]
```

`--check` installs nothing and reports what is there and what is missing. Exit `0` when every required piece is
present. See [setup.sh](../setup.sh) and the quick start in the [README](../README.md).

---

## Library modules (no command line)

These are imported by the tools above and have no command line of their own.

| Module | What it provides |
|---|---|
| `engine/aejsx.py` | After Effects handoff: class `Comp` (`null`, `image`, `text`, `track`, `source_track`, `write`) writes an ExtendScript `.jsx` that rebuilds a template as a native comp with springs baked to keyframes. Used by `statcard.py --ae`. |
| `engine/models.py` | `rembg_home()`: picks the folder for the segmentation models before rembg loads. |
| `engine/spring.js` | The browser twin of `spring.py`, used by the HTML renderers and the website kit. |
| `logo/redraw.py` | Class `Doc`: rebuild a logo as measured vector shapes and real font outlines when tracing fails, with an overlay check against the reference. |
| `web/templates/w1.py` ... `w5.py` | The hero templates `web/build.py` renders. |
| [`vendor/higgsfield/beatmap.py`](../vendor/higgsfield/beatmap.py) | The original bar-map analysis that `engine/beatmap.py` extends; see [NOTICE.md](../NOTICE.md). |
