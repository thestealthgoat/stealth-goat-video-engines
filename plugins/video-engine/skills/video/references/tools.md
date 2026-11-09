# Engine tools the video front door runs

Every command runs from the engine folder (`cd "$VIDEO_ENGINE"`). Tools that read brand or folder values take
`--profile <name>` (or a path to a `profile.json`), else `$VIDEO_PROFILE`, else `local.json`. Run `--help` on any of
them before using a flag that is not listed here; the docstring at the top of each file is the full spec.

Transcription (talkedit, captions, hopwords `--audio`) is local faster-whisper (`small.en` by default) and runs with
`HF_HUB_OFFLINE=1`, so audio never leaves the machine. On a machine that has never fetched the model the first run
fails to find it: run the command once with `HF_HUB_OFFLINE=0` in front (that downloads the model weights only).

## talkedit.py

Talking-head "edit in my style": one command from raw talk to a tight, captioned cut.

```
python3 engine/talkedit.py <video> --out <dir> [--profile P] [--name N] [--start S --end S]
        [--music track.mp3 [--music-in S]] [--aspects 16:9,9:16] [--words-file W] [--model small.en]
        [--fresh] [--plan-only] [--no-captions] [--caption-layer] [--crf N] [--qa] [--preview]
```

What it does (numbers from the profile's `talkedit` block, merged over the `RECIPE` defaults near the top of
`engine/talkedit.py`, where every key is listed. `profiles/_template/profile.json` shows only `cut`, `zoom`,
`captions`, `cards` and `music`; add `pops` or any other block yourself):

1. Words, with fillers ("um", "uh") written down on purpose so they can be cut. Saved as `<name>.words.json`.
2. Cuts every pause over `cut.max_pause` (0.40 s) and every filler or stuttered repeat ("I, I"), leaving
   `cut.keep_pause` (0.20 s). Every cut sits in measured quiet, never mid-word, with a voice fade of at least 40 ms.
3. Punch-ins alternate 1.0 / `zoom.punch_scale` (1.08) at jump cuts (held at least `zoom.min_hold_s`); a hook push
   opens the shot when nothing happens in the first 2 s; spring push-ins on emphasis words about every
   `zoom.push_every_s` (8 s), centered on the face (OpenCV face finder).
4. Cutaway cards: a full-frame title on the profile color block, the phrase being said, about one a minute
   (`cards.per_min`), fitted inside the safe area; on the beat with `--music`.
5. Pop-up cards on cue: a number with its noun counts up, trigger words from `talkedit.pops.triggers`
   (`{"word": "CARD TEXT"}`, default none), emphasis words fill the rest (`pops.per_min`, default 3 a minute).
6. Captions (captions.py) on the cut, never over a card.
7. 16:9 and a face-cropped 9:16, at the profile's delivery loudness (`delivery.loudness_lufs`, `true_peak_db`).

Outputs in `--out`: `<name>_16x9.mp4`, `<name>_9x16.mp4`, `<name>_16x9.xml` (Premiere: source clips with the
punch-in scale, cards on V2, music), `<name>.talkedit.json` (every cut, zoom and card in source seconds),
`<name>.words.json`, `<name>.srt`, `<name>.cuts.json` (planned cuts and holds for qa), `cards/`, `qa_16x9/` and
`qa_9x16/` (with `--qa`), `preview/` (with `--preview`: 720p / 540-wide, under 30 MB).

Hand edits survive re-runs: with the same `--out`, `<name>.talkedit.json` is used as it is. `"on": false` on a cut
puts the pause back; change a cut's `"punch"`, a zoom's `"add"`, a card's `"title"` or `"dur"`; add a cut as
`{"s": a, "e": b}`. `--fresh` moves the plan to `_old/` and plans again. `--plan-only` writes the plan and stops
(the fast way to tune). Old outputs move to `<out>/_old/<stamp>/`; nothing is written over.

Gotchas:
- A scripted read has almost no fillers: most of the tightening comes from pauses.
- A gated podcast mix reads as digital silence between phrases; talkedit treats 35 dB under the speech level as
  quiet and lays a quiet room tone under it, so no pause becomes a dropout.
- Sound whisper skipped (a breath, an unsure word) is kept whole and uncaptioned; the silence around it is cut.
- The XML zoom is a plain Scale about the frame center (push-ins become a split at the pushed scale); only the 16:9
  cut has an XML.
- Some program recorders' files put audio up to ~1 s off with ffmpeg's fast seek; talkedit decodes the sound once,
  sample-exact. Use the same care in any hand-made ffmpeg step (output-side `-ss`).

## captions.py

Kinetic captions: 1-4 words, at most 42 characters, at least 0.4 s on screen, at most 30 characters a second; each
word springs in as it is spoken; one keyword per caption in an outlined box.

```
python3 engine/captions.py <video> --out <dir> [--profile P] [--aspect 16:9|9:16] [--words-file W]
        [--prompt "names, places"] [--model small.en] [--min-prob 0.35] [--start S --end S] [--name N]
        [--words-only] [--no-mov] [--no-mp4] [--crf N] [--vertical-fill auto|band|crop]
```

Outputs: `<name>.words.json` (one word a line: `w`, `s`, `e`, `p`; add `"key": true|false` to force or forbid the
highlight, `"break": true` to start a caption; delete a line to drop a word; dropped words listed under
`"dropped"`), `<name>.captions.json` (rule breaks under `"violations"`), `<name>.srt`,
`<name>_captions_<16x9|9x16>.mov` (full-frame ProRes 4444 alpha layer), `<name>_captioned_<16x9|9x16>.mp4`
(burned in, audio copied untouched).

- `--prompt` steers spelling of names and places (default: from the profile).
- `--aspect 9:16` from a 16:9 source: the full frame as a band over a blurred copy, captions under it. Portrait phone
  clips pillarboxed inside the 16:9 fill the frame instead (`--vertical-fill auto`; the shot list
  `<name>.fill.json` is editable and reused). `band` / `crop` force one layout.
- In the 9:16, qa.py flags more "unplanned cuts" than in the 16:9 (the crop enlarges whip pans in phone clips):
  compare with a qa run on the uncaptioned source before fixing anything.
- Style: the profile's `captions` block (font role, size, stroke, box color, position, spring).

## fxpack.py

Cinematic edit pack: flash cuts, zoom punches with radial blur, RGB split, speed ramps, whip pans, black and white
with one hue kept, kinetic text.

```
python3 engine/fxpack.py <plan.json> --out DIR [--name N] [--profile P] [--fps 29.97] [--size 1920x1080]
        [--frames t1,t2] [--plan-only]
```

- Shots last whole beats on the bar map; the `hero` shot lands on the drop.
- `"fx": "auto"` places: a flash cut on the drop; a speed ramp (1 to 0.35x on a smooth spring) into the drop when
  the shot before it moves; whip pans on cuts whose outgoing shot pans hard (two at most, never neighbors); a zoom
  punch on the strongest hit inside a shot, centered on the action; RGB split on the top hits over fast action; black
  and white keeping the hue the movers carry, on the hero; kinetic text one word a beat from the drop, on the side
  away from the action. Or give a list: `[{"type": "flash", "at": 4.0}, ...]` with types `flash`, `zoom`, `rgb`,
  `ramp`, `whip`, `pop`, `text`.
- **Effect gate:** an effect needs a music event (beat, downbeat, hit, riser, drop) within one frame AND a measured
  picture reason. Otherwise nothing renders (exit 3) and the effect is listed in `<N>_fx.json`.
- Portrait clips are cover-cropped, never stretched. `--size 1080x1920` for a vertical.
- Outputs: `<N>_fx.mp4`, `<N>_fx.xml` (shots, music, a marker per effect), `<N>_fx.json`, `<N>_fx_music.wav` (the
  leveled music the XML points at); prints the qa arguments (`qa: --kind edit --cuts ...`).
- qa's hook gate needs a cut or a big move by 2.0 s (the frame nearest 2 s counts): keep the first shot to 2 s or
  less, or open on a big move.
- Look at `--frames` stills first: pick in-points on live action, not on replays, title graphics or name straps.

## beatmap.py

Bar map of a music track: tempo, downbeats, sections, stops, pickups, risers, the drop, top hits.

```
python3 engine/beatmap.py <track|video> [--start s] [--dur d] [--fps 29.97] --out out/x/beatmap.json [--bpm N]
python3 engine/beatmap.py <track> --choose-window 15            # suggest the best 15 s windows
```

Writes `beatmap.json` and `beatmap.md` next to it. Times are film seconds from `--start`. `--fps` defaults to the
profile's `delivery.fps`. `--bpm` forces the tempo after checking by ear (the phase is still fitted). When the input
is downloaded media, run it with `python3 -P` (or `-I`).

## beatsnap.py

Snaps an edit list's cuts to the music.

```
python3 engine/beatsnap.py <edit.json> <music> [--open 1.6] [--max-shift 0.25] [--barmap auto|beatmap.json]
        [--big-key big] [--payoff N] [--down-shift 1.0] [--drop-shift 1.5] [--legacy-beats] [--profile P]
```

- Reads the music offset from `music[0].in`; moves each item's OUT point (never the in point). Writes the edit back
  in place (copy it first) and adds a `beats` record.
- Shift limits: an ordinary cut moves at most `--max-shift`; a cut into a big item up to `--down-shift`, into the
  payoff up to `--drop-shift`. A cut that would land inside a music stop moves to the stop's start or the downbeat
  after it even past those limits, and the printout says `moved out of a stop`.
- Cuts into items whose `--big-key` value is truthy land on a downbeat; the cut into the payoff item (`"payoff":
  true` or `--payoff N`) lands on the drop when it is within `--drop-shift`, else the music in point that would put
  it there is printed. No cut lands inside a music stop.
- `--open` is the opener length before the first item (default 1.6 s); pass `0` when the edit has none.
- Items with `"replay": true` and `"speed"` are timed at that speed.
- `--legacy-beats`: the older librosa snap (about 40-50 ms late against the bar map); only for comparison.

## fcp7xml.py

Edit list to Final Cut Pro 7 XML (xmeml v5), which Premiere imports with File > Import.

```
python3 engine/fcp7xml.py <edit.json> <out.xml>
python3 engine/fcp7xml.py --single <render.mp4> [out.xml] [--path "<path Premiere sees>"]
```

Paths are written as given: use the paths of the editing machine. `--single` makes a one-clip sequence of any MP4
(for tools that only write an MP4). Format: [formats.md](formats.md#edit-list).

## hopwords.py

Bouncing-character verse or lyric (2D): a character hops word to word on a gravity arc, landing on each word's start
time; each word lights up and pops; the word underfoot is in the accent color. Lines balanced over pages (3 a page
in 16:9, 5 in 9:16).

```
python3 engine/hopwords.py --text "<words>" --out <dir> [--name N] [--profile P]
        [--audio voice.wav | --words words.json | --chart chart.txt | --wpm 95] [--ref "Source line"]
        [--character art.png|art.svg] [--aspect 16:9|9:16] [--bg profile|gradient|'#hex'|image.png|none]
        [--bg-dim 0.62] [--lead 1.0] [--tail 1.6] [--fps N] [--frames 1.0,2.5] [--model small.en] [--prompt P]
```

- Word times, first found wins: `--words`, `--audio` (local transcription, saved as `<name>.words.json`),
  `--chart` (one cue a line: `<seconds or m:ss.ss> <word or phrase>`), `--wpm`.
- With `--text` plus timed words, the shown words are the `--text` words, each taking the time of the word it
  matches.
- `--ref` adds a small source line at the bottom (a book and verse, a song credit).
- Outputs: `<name>_hop.mp4` (audio muxed in with `--audio`), `<name>_hop_Alpha.mov` with `--bg none`,
  `<name>.timing.json`, `<name>.words.json` when it transcribed, stills with `--frames`.
- QA: `python3 engine/qa.py <name>_hop.mp4 --profile P --kind motion --cuts none`.

## statcard.py (with --ae) and aejsx.py

Stats lower third: cutout photo, number and name, one big stat line, 2-4 label/value pairs; counts up on a spring.

```
python3 engine/statcard.py <stats.json> <out_dir> [--name N] [--profile P] [--size WxH] [--fps N] [--dur 5.5]
        [--start 0] [--bg image|video|'#hex'] [--bg-in S] [--frames t1,t2] [--no-logo] [--ae]
```

Outputs `<N>_stats_Alpha.mov` (ProRes 4444, full frame), `<N>_stats.mp4` (preview on `--bg`), `<N>_stats.png`
(settled card, transparent); `--frames` writes only stills `<N>_stats_t<t>.png`. `--ae` also writes `<N>_stats.jsx`
and `<N>_stats_ae/`: run it in After Effects (File > Scripts > Run Script File) for a native comp with real text
layers in the profile fonts and every spring baked to keyframes (simplified so curves stay editable). Fonts must be
installed where AE runs. `engine/aejsx.py` is the library (class `Comp`: `null`, `image`, `text`, `track`,
`source_track`, `write`); it has no command line. Format of `stats.json`: [formats.md](formats.md#stats-card).

## encode.py

Delivery masters with ffmpeg and an encode preset from the profile.

```
python3 engine/encode.py master INPUT... -o OUT.mp4 [--preset NAME] [--b-v 12M --maxrate 14M --bufsize 24M]
        [--faststart|--no-faststart] [--full-verify] [--force] [--log FILE] [--profile P]
python3 engine/encode.py rewrap IN.ts [-o OUT.mp4]
python3 engine/encode.py copy-verify FILE... --to DIR|<profile paths key>
python3 engine/encode.py verify FILE [--expect SECONDS | --like INPUT...] [--full-verify] [--tol 2]
```

- `--preset` defaults to the profile's `delivery.default_preset`, else `web`. The demo and `_template` profiles
  ship `delivery.web` (libx264, 12M / 14M / 24M), so `master ... --profile demo` works without `--preset`. A profile
  without the preset stops with `FATAL: no encode preset '<name>': profile <p> has no delivery.<name>`: add one
  ([formats.md](formats.md#encode-preset)).
- `master`: one ffconcat list (in/out points honored) or several media files (joined). Video encoded with
  `delivery.<preset>`, audio copied; falls back to `vcodec_fallback` (libx264) when this ffmpeg lacks the encoder.
- Writes `<name>.partial.mp4`, renamed on success; never replaces an output without `--force`; an input is never an
  output. Verify runs after master and rewrap (decode errors in the first and last minute, duration check).
- Log protocol: every run starts `=== START <mode>` and ends `=== DONE <mode>` or `=== FAILED <mode>`, with a
  failure line (`ENCODE_FAIL`, `VERIFY_FAIL`, `REWRAP_FAIL`, `COPY_FAIL`, or `FATAL: <reason>`) before it.
  Default log: `<output folder>/.enc/encode.log`. The Mac is kept awake while it runs (`--no-caffeinate` to skip).

## vertical.py

9:16 (1080x1920) social version of a finished 16:9 piece without re-cutting it.

```
python3 engine/vertical.py <in_16x9.mp4> <out_9x16.mp4> [--profile P] [--kicker TXT] [--head TXT] [--sub TXT]
        [--foot TXT] [--sponsor TXT] [--assets DIR] [--fontdir DIR]
```

The full frame (graphics intact) as a 1080-wide band over a blurred moving copy, the profile logo
(`brand.logo_png`, required: `vprofile.py new --logo x.svg` stores `brand.logo_svg`, which vertical does not read)
and the header lines above, the footer (`team.foot`, `--foot` overrides) below, clear
of the Reels/TikTok UI. Audio copied untouched (the input needs an audio track), so no new audio cuts.

## sheet.py

```
python3 engine/sheet.py <video> <out.jpg> <t0> <t1> [--n 12] [--cols 6] [--w 320] [--label TEXT]
```

Frames evenly from t0 to t1, each labeled with its time. Keep t1 a little before the end of the file (a frame at
the exact end comes out black). No profile.

## clip_plays.py

```
python3 engine/clip_plays.py <source.mp4> <moments.json> <out_dir> [--seconds 150] [--only 3,7,12]
```

Stream-copy cuts (no re-encode) of every listed moment; never touches the source; skips clips that already exist.
Time-sliced: rerun until it prints `DONE`. `-c copy` cuts land on keyframes, so cuts are only as tight as the
source's keyframe interval. Format: [formats.md](formats.md#moments-list).

## audio_check.py and motion_check.py

Run by qa.py; on their own:

```
python3 engine/audio_check.py <video> --cuts 1.6,8.2       # PASS / FAIL on hard audio cuts (exit 1 on FAIL)
python3 engine/audio_check.py <source>                     # no --cuts: is a hard cut-off already in the source?
python3 engine/motion_check.py <video> --holds 3.5-4.0,end:1.2 --sheet out/check.jpg   # dead stretches, stutters
```

`motion_check.py --allow-stutter` only when the edit contains 24p source conformed to 29.97/30. Read the sheet
instead of every frame.

## Other engine tools worth knowing

- `engine/offload.py <card> <dest> [--ext MP4,MOV] [--dry-run] [--check-only] [--profile P]` - safe, resumable
  card copy with byte verification; `--dry-run` first.
- `engine/cutout.py in.jpg out.png [more pairs]` - one photo to a clean transparent cutout (BiRefNet via rembg).
- `engine/musicbed.py out.wav --dur 30 --bpm 120 [--drop 18]` - a synthesized music bed (no license questions).
- `engine/measure.py {probe,track,fit,compare}` - measure a finished motion piece and fit springs to it.
- `engine/spring.py` / `engine/spring.js` - the closed-form springs every animated tool uses.
