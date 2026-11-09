---
name: action-pack
description: Turns burst photos from a game, race or event into a fast stop-motion "action pack" video (vertical 1080x1920 and/or 16:9 1920x1080) with the brand's colours, fonts and logo, synthesized shutter clicks and a music bed, using the engine's flipbook.py. Use when the user says "action pack", "stop-motion from these bursts", "burst flipbook", "turn my burst photos into a video", "photo flipbook reel" or "stop-motion recap from the game photos".
---

# Action pack (burst flipbook)

Photographer bursts (5+ shots fired within a second or two) become a fast stop-motion reel: a 1 s "ACTION PACK" title
card, each chosen burst played at 12 photos a second inside a viewfinder frame, a punch-in hold on each burst's last
shot, and a logo end card. The engine tool is `engine/flipbook.py`; this skill's `scripts/ap_helpers.py` does the
parts flipbook does not (grouping photos into bursts, contact sheets, the plan file, the cut list, a plain logo slam).
Exact formats, layout and timing: [references/flipbook.md](references/flipbook.md).

## Before anything

- Find the engine: `echo "$VIDEO_ENGINE"`. If it is empty or the folder has no `engine/flipbook.py`, ask the user
  where their clone is, or set it up (the `getting-started` skill walks through it):
  `git clone https://github.com/thestealthgoat/stealth-goat-video-engines`, then `cd stealth-goat-video-engines &&
  ./setup.sh` (it targets macOS with Homebrew), then `export VIDEO_ENGINE="$PWD"`. Run every engine command as
  `cd "$VIDEO_ENGINE" && python3 engine/<tool>.py ...`.
- Pick the profile: `--profile <name>` on every command (else `$VIDEO_PROFILE`, else `local.json`). Use `demo` to try
  things: it ships with the engine (`profiles/demo`, with its fonts and `assets/demo_logo.png`). A user's own profile
  is made from `profiles/_template` (see `docs/LAYOUT.md`) with
  `python3 engine/vprofile.py new <name> --logo /path/to/logo.png`: a PNG logo is written as `brand.logo_png`, which
  flipbook needs. An `.svg` logo is written as `brand.logo_svg` instead, which flipbook does not read, so give it a
  PNG (export one from the SVG, or use the `logo-vectorize` skill's hi-res PNG).
- Set the helper path once: `H="<this skill's base directory>/scripts/ap_helpers.py"` (the base directory is shown
  when the skill loads). Run it with `python3 "$H" <command> ...`; `python3 "$H" -h` lists the commands.
- Pick a work folder outside the engine clone, under the profile's root folder
  (`python3 engine/vprofile.py show <profile>` prints `path root`; for `demo` it is `~/Movies/video-work`):
  `WORK="$HOME/Movies/video-work/action-pack/<slug>"`.
- Ask what it is for: vertical (Reels/Shorts/TikTok), wide, or both; the title line (e.g. `ACME · SPRING CUP`); the
  end-card lines come from the profile (`team.foot`, `brand.watch_line`); empty strings leave them blank.

## What the public engine does and does not do

- Does: renders the reel from JPEG frames and a plan, in profile colours/fonts/logo; synthesizes shutter clicks and
  low booms (no licence needed); vertical by default, `--wide` for 16:9; end card from a folder of 1920x1080
  transparent PNG frames (`--slam DIR`) or, without `--slam`, from the profile's `brand.logo_3d_swing_alpha_mov`.
- Does not: read RAW files, add music, write a cut list, or offer a layout preview mode. The words "ACTION PACK" and
  "BURST NN/NN" are fixed in the tool; change only what its flags and the plan allow. Do not edit engine code to get
  a look; tell the user what is fixed instead.
- Every photo is shown in a portrait shape (vertical: cropped to fill 9:16; wide: a 2:3 card on a blurred, tinted copy
  of the photo). Portrait photos crop least; landscape photos lose their sides, so prefer bursts whose action is
  near the middle of the frame.

## Steps

### 1. Photos to bursts

Flipbook reads `.jpg` files only. If the user has RAW files only, ask them to export JPEGs from their photo app (long
edge about 2000 px, metadata included so capture times survive). Then:

```bash
cd "$VIDEO_ENGINE"
python3 "$H" bursts "/path/to/exported/jpegs" "$WORK"            # --gap 2.0 s, --min 5 shots, --long 1800 px
```

This reads each photo's EXIF capture time (with sub-seconds when present), groups shots taken 2 s or less apart, keeps
groups of 5+, writes upright copies to `$WORK/img/` and the list to `$WORK/bursts.json`. If it warns that photos have
no capture time, ask for a re-export with metadata rather than guessing order.

### 2. Look at every burst

```bash
python3 "$H" sheet "$WORK"            # $WORK/sheets/bursts_00.jpg ... (first / middle / last shot, 32 bursts a sheet)
```

Read every sheet. Pick about 10-15 bursts in event order with variety: arrival or warm-up, a portrait or two, the
big plays (throws, runs, kicks, finishes, saves), celebrations, the crowd or bench, the final moment.
Gaps in the capture times (the label shows each burst's start) usually mark breaks such as halftime.

People rules, always:
- No injuries, no one down or hurt, nothing embarrassing, no one caught in a bad moment, no changing rooms or locker
  rooms. Drop a burst rather than risk it.
- No names on screen unless the user confirms them; jersey numbers are fine.
- For minors, check the user has permission to publish their photos before the reel is shared.

### 3. Plan

Write `$WORK/picks.json` in play order, then build the plan:

```json
[{"b": 2, "tag": "GAME 1", "opp": "VS ACME"},
 {"b": 7, "tag": "GAME 1", "opp": "FIRST GOAL", "trim": 3},
 {"b": 15, "tag": "FINAL", "opp": "ACME 2-1"}]
```

```bash
python3 "$H" plan "$WORK" "$WORK/picks.json"     # -> $WORK/plan.json and $WORK/sheets/chosen.jpg (max 10 shots a burst)
```

- `b` is the burst number from the sheet; `tag` is the bold line under the burst counter (shown upper-case); `opp`
  follows it on the same line and is printed as written, so write it in capitals. Keep `tag` + `opp` under about 24
  characters. Put the final score on the last burst.
- `trim` drops shots from the end of a burst (use it when a burst ends on a pile-up or a bad moment).
- Read `$WORK/sheets/chosen.jpg` before rendering: every shot that will appear is on it. Fix picks and rerun `plan`.

### 4. End card frames

- With the user's logo as SVG (their profile, or the `logo-vectorize` skill): make a slam with the engine's logo
  tools as a transparent PNG sequence at the reel's rate:
  `python3 logo/motion.py <logo.svg> "$WORK" Brand slam --fps 29.97 --png-seq --profile <name>` writes
  `$WORK/Brand_slam_seq/f00000.png ...` (2 s). Needs the logo tools' setup (`logo/setup.sh`, Playwright Chromium);
  see the `logo-motion` skill.
- Quick or no SVG: `python3 "$H" slam <logo.png> "$WORK/slam"` (54 frames, the PNG drops in and settles). For the demo:
  `python3 "$H" slam profiles/demo/assets/demo_logo.png "$WORK/slam"`.
- Frames must be 1920x1080 RGBA named `f*.png`. Flipbook lays the end-card lines over them and fades to black over the
  last 12 frames.

### 5. Test render, then the real one

There is no preview mode, so check the layout with a short test: the first two bursts only.

```bash
python3 -c "import json,sys;p=json.load(open(sys.argv[1]));json.dump(p[:2],open(sys.argv[2],'w'),indent=1)" "$WORK/plan.json" "$WORK/plan_test.json"
python3 engine/flipbook.py "$WORK/plan_test.json" "$WORK/img" "$WORK/test_vert.mp4" --profile demo --label "ACME · SPRING CUP" --slam "$WORK/slam"
python3 engine/sheet.py "$WORK/test_vert.mp4" "$WORK/sheets/test_vert.jpg" 0 4 --n 12 --cols 6
```

Read the sheet: text inside the frame, logo clear of faces, crops keep the action, and the title card (0.4 s and
0.7 s tiles) with the logo clear of "ACTION". Flipbook draws the logo 560 px wide above the title with no height
limit, so a logo narrower than about 1.75:1 (a square or round badge) runs into "ACTION". That is fixed in the tool;
the fix is a pack-only copy of the profile whose logo is padded with transparent sides to 2:1:

```bash
python3 "$H" packprofile <profile> "$WORK/profile_pack"     # then use --profile "$WORK/profile_pack" on flipbook.py only
```

The corner logo on the burst frames then comes out smaller and a little in from the corner (it is centred in the
padded box); tell the user. Keep the real profile for musicbed, qa and everything else. Then render the full plan,
one render at a time (vertical first, then wide; never both at once):

```bash
python3 engine/flipbook.py "$WORK/plan.json" "$WORK/img" "$WORK/pack_vert.mp4" --profile demo --label "ACME · SPRING CUP" --slam "$WORK/slam"
python3 engine/flipbook.py "$WORK/plan.json" "$WORK/img" "$WORK/pack_wide.mp4" --profile demo --label "ACME · SPRING CUP" --slam "$WORK/slam" --wide
```

Other flags: `--fps-photo 12` (shots a second; lower is choppier and longer), `--keep-temp` (keep the rendered JPEG
frames in `<out>_frames/`). Swap `demo` for the user's profile.

### 6. Music bed and loudness

Flipbook's own track is clicks and booms over silence. That fails the engine's audio rule (no hard audio cuts: each
click stops abruptly into silence) and is not levelled. Always lay a bed under it and level the mix:

```bash
D=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$WORK/pack_vert.mp4")
python3 engine/musicbed.py "$WORK/bed.wav" --dur "$D" --bpm 120 --drop 1.001
ffmpeg -nostdin -v error -y -i "$WORK/pack_vert.mp4" -i "$WORK/bed.wav" -filter_complex "[0:a]volume=0.5[fx];[1:a]volume=1.0[bed];[fx][bed]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-14:TP=-3:LRA=11,aresample=48000[a]" -map 0:v -map "[a]" -vf "scale=in_range=pc:out_range=tv,format=yuv420p" -color_range tv -c:v libx264 -crf 17 -preset slow -c:a aac -b:a 256k -movflags +faststart "$WORK/pack_vert_final.mp4"
```

- `musicbed.py` synthesizes a free bed (pads, arpeggio, kick from the drop); `--drop 1.001` starts its beat on the
  first burst. Use `-14` from the profile's `delivery.loudness_lufs` and a true peak 1 dB under its
  `delivery.true_peak_db`.
- The video is re-encoded, not copied: flipbook's file is full-range `yuvj420p` (it is built from JPEG frames), and
  the `scale=in_range=pc:out_range=tv` step turns it into the standard `yuv420p` the delivery spec and the platforms
  expect, with the same colours.
- A track the user owns or has cleared can replace `bed.wav` (trim it to `$D` with a fade-out). Never use music the
  user has no rights to.
- Do the same for `pack_wide.mp4` -> `pack_wide_final.mp4` (same `bed.wav`: both renders have the same length).
- In zsh, write shell variables inside filter strings as `${v}`: `$v[c]` is read as an array index.

### 7. QA (the `video-gates` skill)

```bash
python3 "$H" cuts "$WORK/plan.json" "$WORK/pack.cuts.json"       # same --fps-photo as the render
HOLDS=$(python3 "$H" get "$WORK/pack.cuts.json" holds)            # the title card's still stretch
python3 engine/qa.py "$WORK/pack_vert_final.mp4" --profile demo --kind edit --shotlist "$WORK/pack.cuts.json" --holds "$HOLDS" --allow-stutter --out "$WORK/qa_vert"
python3 engine/qa.py "$WORK/pack_wide_final.mp4" --profile demo --kind edit --shotlist "$WORK/pack.cuts.json" --holds "$HOLDS" --allow-stutter --out "$WORK/qa_wide"
```

Read `review.md` and `sheet.jpg` in each review folder and fix every real FAIL before showing anything. On a
correct pack the verdict is `RESULT: PASS` with warnings. What to expect, and why:
- The cut list holds the title card's 2-frame white flash (a cut at 0.033 s), the title end, every photo change and
  the end card, so the white flash at each burst's first shot and every shot change count as planned.
- `--holds "$(python3 "$H" get "$WORK/pack.cuts.json" holds)"` (it prints `0.25-1.001`) declares the title card's
  still stretch: flipbook zooms the "ACTION PACK" text for its first 0.25 s, then holds it still until the first
  burst. That is fixed in the tool. Without `--holds`, qa FAILs it as "nothing moves for 0.73 s" at f8-f29.
- `--allow-stutter` because each photo is held 2-3 frames on purpose (the stop-motion look). A dead stretch or a
  stutter outside the title card and the bursts is still real.
- Expected WARNs: `cuts vs plan: ... planned not found` and one "planned cut not detected as a hard cut" line per
  photo change that scdet does not see. Shots inside a burst are taken a tenth of a second apart and look alike, so
  most photo changes are too small to count as a hard cut; the burst starts (the white flash) are found. Check a few of
  those frames on `sheet.jpg`. An unplanned cut (a FAIL) is real: the cut list was made from a different plan or
  `--fps-photo` than the render.
- `pixel format yuvj420p` (a WARN) means the bed step copied flipbook's video stream (`-c:v copy`) instead of the
  re-encode above. Flipbook's file is full-range (JPEG frames); the re-encode makes it standard `yuv420p`.
- An audio FAIL means the bed step was skipped or the bed is too quiet: raise the bed `volume`, or lower the clicks.
- When you change the mix, also run
  `python3 engine/audio_check.py "$WORK/pack_vert_final.mp4" --cuts "$(python3 "$H" get "$WORK/pack.cuts.json" cuts)"`.

### 8. Deliver

- Name the files `<slug>_action_pack_1080x1920.mp4` and `<slug>_action_pack_1920x1080.mp4`, plus a `.txt` caption
  draft marked DRAFT. Put them where the user asked (or the profile's `folders.write_into`).
- Send the user a preview and the QA verdict. Nothing is uploaded or posted unless the user chooses a service and asks.
- Delete the test renders and `bed.wav` only after the user has the final files; keep `plan.json`, `picks.json` and
  `pack.cuts.json` so a re-cut is quick.

## Worked example (demo profile, fresh clone)

```bash
cd "$VIDEO_ENGINE"
H="<this skill's base directory>/scripts/ap_helpers.py"
WORK="$HOME/Movies/video-work/action-pack/spring-cup"
python3 "$H" bursts "$HOME/Pictures/spring-cup-jpegs" "$WORK"
python3 "$H" sheet "$WORK"                         # read the sheets, write $WORK/picks.json
python3 "$H" plan "$WORK" "$WORK/picks.json"       # read sheets/chosen.jpg
python3 "$H" slam profiles/demo/assets/demo_logo.png "$WORK/slam"
python3 engine/flipbook.py "$WORK/plan.json" "$WORK/img" "$WORK/pack_vert.mp4" --profile demo --label "ACME · SPRING CUP" --slam "$WORK/slam"
D=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$WORK/pack_vert.mp4")
python3 engine/musicbed.py "$WORK/bed.wav" --dur "$D" --bpm 120 --drop 1.001
ffmpeg -nostdin -v error -y -i "$WORK/pack_vert.mp4" -i "$WORK/bed.wav" -filter_complex "[0:a]volume=0.5[fx];[1:a]volume=1.0[bed];[fx][bed]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-14:TP=-3:LRA=11,aresample=48000[a]" -map 0:v -map "[a]" -vf "scale=in_range=pc:out_range=tv,format=yuv420p" -color_range tv -c:v libx264 -crf 17 -preset slow -c:a aac -b:a 256k -movflags +faststart "$WORK/pack_vert_final.mp4"
python3 "$H" cuts "$WORK/plan.json" "$WORK/pack.cuts.json"
python3 engine/qa.py "$WORK/pack_vert_final.mp4" --profile demo --kind edit --shotlist "$WORK/pack.cuts.json" --holds "$(python3 "$H" get "$WORK/pack.cuts.json" holds)" --allow-stutter --out "$WORK/qa_vert"
# expect RESULT: PASS with warnings (photo changes inside a burst that scdet does not see as hard cuts)
```

## Notes

- A typical pack: 13 bursts of up to 10 shots is about 1 s title + 13 x 1.1 s + the end card, roughly 17-18 s.
- Flipbook removes its working frames and its own `.wav` after a good render; a failed render keeps them for
  debugging. Frames left from an earlier failed run are cleared before a new one starts.
- No photographer bursts? A pack can be made from video stills too: export 8-10 sharp consecutive frames per moment
  as JPEGs into `$WORK/img/` and write `plan.json` by hand (format in the reference).
