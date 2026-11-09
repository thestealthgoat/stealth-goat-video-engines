---
name: matte
description: Cuts the people out of a video shot (talking head, presenter, interview, podcast camera, vlog selfie, single-player camera) as a clean, steady alpha matte for compositing, with the free local engine/matte.py (BiRefNet via rembg; nothing is uploaded). Writes a ProRes 4444 alpha .mov, a greyscale matte .mp4, a preview on a brand background and an edge-flicker report. Use when the user says "cut the person out of this video", "remove the background from my clip", "matte the speaker", "rotoscope this", "green-screen without a green screen", "put text behind me", "cards orbiting the presenter", "replace the background behind the speaker", or "make an alpha of the person".
---

# Person matte from video

Cut the people out of a shot, frame by frame, with the engine's `engine/matte.py`. Everything runs on the user's
own machine with free, open-source models; no frame is uploaded. The brand profile only sets the preview
background. The matte is an intermediate for a composite (text behind the person, cards around a presenter, a new
background), not a finished video.

## 0. Find the engine

1. Use `$VIDEO_ENGINE` (a clone of https://github.com/thestealthgoat/stealth-goat-video-engines). Run every command
   as `cd "$VIDEO_ENGINE" && python3 engine/<tool>.py ...`.
2. If `$VIDEO_ENGINE` is unset or the folder has no `engine/matte.py`, ask the user where the engine folder is, or
   set it up: `git clone https://github.com/thestealthgoat/stealth-goat-video-engines`, then `./setup.sh` inside it,
   then `export VIDEO_ENGINE=<that folder>` (the getting-started skill walks through this). `setup.sh` targets macOS
   with Homebrew; on other systems see the platform note in the getting-started skill. Do not guess a path.
3. Pick the profile: `--profile <name>` on every command, else `$VIDEO_PROFILE`, else `default_profile` in the
   engine folder's `local.json`. The engine ships a `demo` profile for trying things (`python3 engine/vprofile.py list`
   shows it). If the user wants their own brand, have them make one from `profiles/_template` with
   `python3 engine/vprofile.py new <name>` (see `docs/LAYOUT.md`).
4. Check the dependencies once: `python3 -c "import rembg, onnxruntime, cv2"` and `ffmpeg -version`. If anything is
   missing, run `./setup.sh` in the engine folder: it installs what is missing and then checks. (`./setup.sh --check`
   only reports; it installs nothing.)

## 1. Decide whether a matte will work

- **Good:** one to a few people at close or mid range: talking heads, interviews, podcast cameras, presenters,
  vlog selfies, a single-subject camera on one player.
- **Not for:** wide shots with many small people (a crowd, a full field). The models find a few of them at best.
  Ask for a tighter angle of the same moment instead.
- Objects right in front of the person (a mic, a laptop edge, an instrument) may come with them. For text behind
  the speaker that is usually what the user wants; say so when you see it.
- If the user wants a still headshot cutout rather than video, this is the wrong tool: `engine/cutout.py` does
  stills with the same model.

## 2. The models (first run downloads them)

The default `birefnet-general` is BiRefNet (MIT) run through rembg. It gives the most complete people (hands, feet,
hair, dark clothing against a dark ground) and keeps the main subject(s), dropping bystanders.

`engine/models.py` picks the folder the model files live in, once, and exports it as `$U2NET_HOME`:
1. `$U2NET_HOME` if already set;
2. `"rembg_models"` in the engine folder's `local.json` (for example a shared drive);
3. `resources/models/rembg` inside the engine folder, if it exists;
4. otherwise rembg's default folder.

rembg downloads a missing model there on first use. Each BiRefNet file is about 1 GB (U^2-Net about 175 MB), so
before the first run tell the user it will download and check there is disk space. If the disk is tight, put the
models on a bigger drive, either for this shell with `export U2NET_HOME=/path/on/big/drive/rembg` or for good with a
`local.json` in the engine folder's root. A fresh clone has no `local.json` (it is per machine and never committed);
create it if missing, or add the key to the existing one:

```json
{ "rembg_models": "/path/on/big/drive/rembg" }
```

`engine/models.py` creates that folder if it does not exist yet. If the drive is not mounted (the folder cannot be
created), it silently falls back to `resources/models/rembg` or rembg's default folder, so check the drive is there before a
first run.

The other models (`birefnet-portrait`, `modnet`, `u2net_human_seg`) and when to use them are in
[references/models-and-knobs.md](references/models-and-knobs.md). `modnet` needs its ONNX file placed by hand at
`resources/models/modnet_photographic_portrait_matting.onnx` (source in the engine's `NOTICE.md`); it is not
downloaded automatically, so do not pick it on a fresh clone unless that file exists.

## 3. Look first (stills)

Always run `--frames` before a render. It processes the window from `--t0` up to the last asked time (so the
steady filter is warmed up) and writes only stills.

```bash
cd "$VIDEO_ENGINE" && python3 engine/matte.py ~/Movies/interview.mp4 --out out/matte --t0 12 --t1 20 \
  --frames 0.5,3.0,6.5 --profile demo
```

Outputs in `--out` (the name defaults to the clip's file name; set it with `--name`):
- `<name>_matte_check.jpg`: one row per asked time: original | matte | cut-out on the preview background.
- `<name>_matte_t<time>.png`: the RGBA cut-out of each asked frame (times are relative to `--t0`).

Read `<name>_matte_check.jpg` and check:
- **People sideways or upside down?** The clip's rotation tag is wrong (common on phone clips). Add
  `--rotate cw`, `--rotate ccw` or `--rotate 180` and look again; the model needs people upright.
- **Missing limbs or a hollow torso?** Try `--model birefnet-portrait`; if it is still missing, the shot is too wide.
- **A bystander or a lamp kept?** Raise `--min-region` (default 0.15 = drop islands smaller than 15% of the largest
  region); lower it or set 0 if a second person you want got dropped.
- **A halo of the old background around the edge?** Add `--choke 1`.
- **A streaky ghost of the background where a hand or arm just was?** (Vertical streaks of the background kept in
  the matte beside a fast gesture, worst over a textured wall.) That is the temporal hold (`--steady`) keeping the
  old alpha after the limb moved away. Lower `--steady` (try 0.5, or 0 for raw per frame) and look again; the edges
  will flicker a little more, so check the flicker number after the render. Pick a still time right after a fast
  gesture so the check sheet would show it.

Ignore "Broken pipe" and "Error muxing a packet" lines from ffmpeg after a stills run: the decoder is stopped early
on purpose.

## 4. Render

Use the same window and flags as the stills run, without `--frames`:

```bash
cd "$VIDEO_ENGINE" && python3 engine/matte.py ~/Movies/interview.mp4 --out out/matte --t0 12 --t1 20 --profile demo
```

BiRefNet takes about 5-6 seconds a 1080p frame on a laptop CPU, so an 8 s clip at 30 fps (240 frames) is roughly
20-25 minutes, and 60 fps doubles it. Tell the user the estimate, run it in the background, and run only one heavy
render at a time (no other matte, 3D or explainer render alongside). Keep windows short: matte only the seconds the
composite needs. For a fast rough draft, `--model u2net_human_seg` is lighter; see the reference.

The output is capped at `--max-height` (default 1080) on the short side, so a 4K clip comes out at 1080p and a
portrait phone clip stays 1080 wide. Outputs in `--out`:

| File | What it is |
|---|---|
| `<name>_matte_Alpha.mov` | ProRes 4444 with alpha: the person in original colours, edge colour taken from the person, not the old background. Drop it on top of anything. |
| `<name>_matte.mp4` | the alpha as greyscale (white = person), for any compositor's luma matte |
| `<name>_matte_preview.mp4` | the cut-out over `--bg` (default `profile`: the profile's `primary_deep`, else `primary` colour) |
| `<name>_matte.json` | settings, frame count, size, fps, and the edge-flicker numbers |

`--bg` takes `profile`, a hex colour in quotes (`'#101820'`), an image path, `blur` (the shot itself blurred) or
`none` (also falls back to the blurred shot in the preview). It only affects the preview.

## 5. Check before handing it over

1. **Flicker number.** Read `edge_flicker_mean` and `edge_flicker_p95` in `<name>_matte.json` (the alpha's second
   difference in time inside the edge band). Rough calibration on a talking head: about 0.15 raw (`--steady 0`),
   0.04 at `--steady 0.75`, 0.02 at 0.9. Under about 0.05 reads as solid on screen. If it is higher, raise
   `--steady` (default 0.85) toward 0.9-0.95 and re-render. The trade-off: a higher value can leave a streaky ghost
   of the background for a few frames where a hand or arm just moved away (see step 3), and the flicker number does
   not catch that. If you see trails, lower `--steady` instead and accept a little more edge flicker.
2. **Watch the preview** at full size, paying attention to hair, hands, fingers and shoulders, and any frame where
   the person moves fast or something crosses in front of them (ghost trails after a gesture show up here, not in
   the numbers or in qa).
3. **Run the QA gate** (the video-gates skill) on the alpha file. A matte has no opening or ending of its own, so
   use `--kind loop`, and `--cuts none` (a matte should never contain a cut):

   ```bash
   cd "$VIDEO_ENGINE" && python3 engine/qa.py out/matte/interview_matte_Alpha.mov --profile demo --kind loop \
     --cuts none --fps 29.97 --size 1920x1080
   ```

   The matte keeps the source frame rate and size, while qa checks against the profile's delivery spec by default.
   Pass `--fps` and `--size` with the values from `<name>_matte.json` (`fps`, `size`) so an intentional source rate
   (30, 59.94, 60) or a portrait size is not reported as a spec failure; the conform to the delivery spec happens in
   the final composite, which gets its own QA run. Read `review.md` and `sheet.jpg` in the review folder (default
   `./qa_<video name>/`; set it with `--out`). Exit code 0 = PASS, 1 = FAIL. Fix every FAIL before handing it over.

   What to expect on a clean matte: `RESULT: PASS`, with `spec` showing the alpha pixel format (`yuva444p12le`) and
   `no audio` (neither is flagged for an alpha file), `cuts vs plan: 0 detected`, and the two hook lines, the end
   card line and the audio line listed as SKIP (a loop has no opening or ending, and a matte has no sound). A
   `spec_size` or `spec_fps` FAIL means `--size`/`--fps` do not match the json. qa checks the file, not the matte
   quality: a PASS does not mean the edges are good, so steps 1 and 2 still decide that.

## 6. Use the matte

- **Text or a big word behind the speaker:** `engine/behind.py` composites shot -> text -> person. Pass the matte you
  already made with `--matte out/matte/<name>_matte.mp4` and the same `--t0`/`--t1` (and `--rotate` if used),
  otherwise it runs matte.py again. Example:
  `python3 engine/behind.py ~/Movies/interview.mp4 --out out/behind --t0 12 --t1 20 --text "FOCUS" --matte out/matte/interview_matte.mp4 --profile demo`
  (try `--frames 1.0,4.0` first for stills).
- **Glass cards orbiting a presenter:** `engine/stage3d.py orbit <out_dir> <Name> --cards "A|B|C" --matte out/matte/<name>_matte.json --profile demo`
  (the `.json`, not the video; it finds the plate and the cut-out from it).
- **A new background, or the user's own editor:** give them `<name>_matte_Alpha.mov` to lay over any background in
  Premiere, Resolve, Final Cut or After Effects, or `<name>_matte.mp4` as a luma/track matte.

Run qa again on whatever final composite comes out of these before delivering it.

## Rules

- Never upload footage anywhere unless the user explicitly chooses a service; this skill is fully local.
- Matte only people the user has the right to use. Never use a matte to build a fake of a real person (putting
  someone into a scene or saying something they did not).
- One heavy render at a time; tell the user the time estimate before starting a long one.
- Do not claim a matte is clean until you have read the check sheet, the flicker numbers and the qa review.

## Worked example (fresh clone, demo profile)

The user: "Cut me out of this clip so I can put a title behind me", with `~/Movies/talk.mov`, a 1080p 30 fps
phone clip, wanting seconds 40-46.

```bash
cd "$VIDEO_ENGINE"
python3 engine/matte.py ~/Movies/talk.mov --out out/talk --t0 40 --t1 46 --frames 0.5,3.0,5.5 --profile demo
```

Read `out/talk/talk_matte_check.jpg`. The person is sideways, so add `--rotate ccw` and look again: upright, hands
whole, a lamp kept as an island. Raise `--min-region` to 0.25, look once more, then render in the background
(about 180 frames, roughly a quarter of an hour on a laptop CPU):

```bash
python3 engine/matte.py ~/Movies/talk.mov --out out/talk --t0 40 --t1 46 --rotate ccw --min-region 0.25 --profile demo
```

`out/talk/talk_matte.json` shows `edge_flicker_mean` 0.03, `size` [1080, 1920] and `fps` 30.0. Watch
`talk_matte_preview.mp4`, then:

```bash
python3 engine/qa.py out/talk/talk_matte_Alpha.mov --profile demo --kind loop --cuts none --fps 30 --size 1080x1920
```

It prints `RESULT: PASS` and exits 0 (the hook, end card and audio lines show as SKIP, as expected for a matte).
Then put the title behind with
`python3 engine/behind.py ~/Movies/talk.mov --out out/talk_behind --t0 40 --t1 46 --rotate ccw --text "HELLO" --matte out/talk/talk_matte.mp4 --profile demo`,
check its stills, render, and QA that output before delivery.

More on every flag, model choice and troubleshooting: [references/models-and-knobs.md](references/models-and-knobs.md).
