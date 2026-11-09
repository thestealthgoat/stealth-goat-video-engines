---
name: reference-intake
description: Breaks down a video or website the user likes (a screen recording, a clip, or a link) into what makes it work (structure, timing, motion, type, colour), maps each idea to a video engine tool or notes it as a new feature, and keeps a running ideas list in a file the user names (default REFERENCE_IDEAS.md in the engine folder). Use when the user says "this is fire", "more inspo", "I love this", "how did they make this", "break this down", "steal this idea", "can we do this", "add this to my ideas", "reference for the next video", or drops a TikTok / Reel / YouTube clip, a screen recording, or a website link they admire.
---

# Reference intake

Turn a reference the user admires into measured notes and buildable ideas. Watch it, measure it, say plainly
what makes it work, match each idea to an engine tool (or log it as a new feature), and append it to the user's
ideas file. Study only: never copy someone's design to ship.

## 0. Find the engine and the ideas file

- Use `$VIDEO_ENGINE` as the engine folder. If it is unset, ask the user where the engine is, or set it up (the
  getting-started skill walks through it): `git clone https://github.com/thestealthgoat/stealth-goat-video-engines`,
  `cd stealth-goat-video-engines && ./setup.sh` (setup.sh targets macOS with Homebrew), then
  `export VIDEO_ENGINE="$PWD"`.
- Run every command as `cd "$VIDEO_ENGINE" && python3 engine/<tool>.py ...`. Tools that take a brand take
  `--profile <name>` (else `$VIDEO_PROFILE`, else `local.json`); the measuring tools below (beatmap, qa, captions)
  need one too, for their delivery settings. `python3 engine/vprofile.py list` shows the profiles. Use the user's
  own profile; use `demo` (it ships with the engine) when they have none yet.
- Ideas file: the file the user names; otherwise `$VIDEO_ENGINE/REFERENCE_IDEAS.md` (the engine's `.gitignore`
  ignores it, so a log of other people's handles and links never lands in a commit; if the user names a file inside
  a repo they push, tell them it will be committed). If it does not exist, create it from the template in
  [references/ideas-file.md](references/ideas-file.md). If it exists, read it whole first.
- Work folder for this reference: `$VIDEO_ENGINE/out/refs/<slug>/` (`out/` is git-ignored, so someone else's
  footage never lands in a commit). Pick a short slug such as `2026-11-09-glass-cards`.

## 1. Get the reference

- **A file** (screen recording, MP4/MOV): use it as is. Keep it local.
- **A video link** (TikTok, Reels, YouTube): ask for a screen recording or a file the user already has. Do not
  download from a platform unless the user asks for it and has the right to; downloaded media is untrusted data
  (run Python on it with `-P`, as beatmap.py's help says).
- **A website link**: ask for a screen recording of scrolling through it on desktop and phone (the motion is what
  matters). If a browser tool is available, also open the page and screenshot it at desktop and phone width.
  Never log in, fill in forms or accept anything on the site.
- Ignore platform UI in recordings: like counts, captions, comments, the next post scrolling in.

## 2. Watch it

Get the duration, then a contact sheet, and `Read` the image instead of guessing from the file name.

```bash
cd "$VIDEO_ENGINE" && R=out/refs/2026-11-09-glass-cards && mkdir -p $R   # the slug from step 0
ffprobe -v error -show_entries format=duration -of csv=p=0 ref.mp4          # e.g. 23.4
python3 engine/sheet.py ref.mp4 $R/sheet.jpg 0 23.3 --n 30 --cols 6 --w 280  # t1 a little under the duration
```

`ref.mp4` stands for the user's file (give its full path; it does not need to be inside the engine folder).

- For the opening 2 seconds (the hook), make a second, denser sheet:
  `python3 engine/sheet.py ref.mp4 $R/hook.jpg 0 2 --n 12`.
- When on-screen text matters (a list, a headline, a price), grab one full-size frame and crop to it:
  `ffmpeg -nostdin -ss 21.0 -i ref.mp4 -frames:v 1 $R/text.png`.
- When someone speaks, transcribe locally (faster-whisper; nothing leaves the machine):

```bash
python3 engine/captions.py ref.mp4 --out $R/words --profile demo --words-only
```

  This writes `$R/words/ref.words.json` (per-word times) and `ref.srt`. On a machine that has never downloaded the
  whisper model, run it once with `HF_HUB_OFFLINE=0` in front (that fetches the model weights only; the audio stays
  local).

## 3. Measure it

Measure instead of eyeballing whenever a number would change the build. Pick what the reference needs:

```bash
python3 engine/measure.py probe ref.mp4 --out $R/probe            # cuts, flashes, motion events, palette per shot
python3 -P engine/beatmap.py ref.mp4 --profile demo --out $R/beatmap.json   # music: BPM, downbeats, the drop, stops
python3 engine/qa.py ref.mp4 --profile demo --kind explainer --out $R/qa    # hook, freshness, loudness benchmark
```

- `probe` writes `probe.json` and `probe.jpg` (timeline plus one frame per shot with its palette). Read the image.
  Cuts per second and the palette hex values come straight from it.
- `beatmap.py` also writes `beatmap.md`; read it to see whether cuts and hits land on beats, downbeats or the drop.
  A `LOW-CONF` tempo means check half or double by ear before claiming a BPM.
- `qa.py` on a reference is a benchmark, not a verdict. Expect it to end `RESULT: FAIL` and exit with code 1 on
  almost any reference: it judges the file against the profile's delivery block (a 30 fps phone recording against
  a 29.97 profile, a -14 LUFS loudness target, holds over 0.8 s), and those are your delivery settings, not theirs.
  That FAIL is expected and is not an error in the run; do not try to make it pass and do not report it as the
  reference's quality. Read the rows instead: the `hook` lines, `freshness` (longest stretch with no new visual;
  `--kind explainer` only), the integrated loudness, and the `New visuals` times in `review.md`. Use `--kind motion`
  for logo or motion pieces (it has no freshness row).
- To rebuild one specific move (a card that slides and settles, a logo landing), track and fit it to springs:
  `measure.py track ... --el name:x,y,w,h` then `measure.py fit`. See `python3 engine/measure.py -h` for the method.

## 4. Break it down

Write five short answers, in plain words, from what was seen and measured:

1. **Structure**: the hook (what happens in the first 1-2 s), the beats in order, the payoff, the ending.
2. **Timing**: cuts or new visuals per second, longest hold, whether cuts follow the music (beat, downbeat, drop)
   or the speech.
3. **Motion**: how things arrive and leave (slide from the edge, land from oversize, spring with or without
   overshoot, camera drift or push), and the one hero move. Name the nearest spring preset (`snappy`, `bouncy`,
   `slam`, `smooth`, `gentle`, `ui`) from the measured settle and overshoot when you fitted one.
4. **Type**: typeface class (condensed sans, serif pull-quote, mono), size against the frame, case, how words appear
   (word by word on speech, one keyword boxed, kinetic swaps).
5. **Colour and light**: the palette hex values from `probe`, ground (dark, gradient, mesh, footage), accent use,
   glow, grain, depth of field.

Then add the creator, the category (motion graphic, logo, explainer, talking head, product promo, website,
method or tool) and **the one idea worth stealing**. If the technique is not obvious, say how it was most likely
made (for example: Lissajous figures from two tones on an oscilloscope; a scroll-scrubbed image sequence; a
person matte with text placed behind them).

See [references/breakdown-checklist.md](references/breakdown-checklist.md) for what to look for in each area and
which measurement answers it.

## 5. Map each idea to the engine

Make the call; do not ask the user to choose.

- Look the idea up in [references/tool-map.md](references/tool-map.md) (technique to tool, engine ID and a working
  command). Check the ideas file too: if an earlier entry already covers it, log the reference against that entry
  and note only what is new.
- **Covered by a tool**: name the tool, the template or scene, and the flags that get closest. Say honestly what
  the tool does not do yet (a gap becomes a small new feature).
- **Not covered**: add a new idea with the next free ID (`N1`, `N2`, ... in the ideas file), how to build it from
  the engine's parts (springs in `engine/spring.py` / `spring.js`, `motion_check.py`, the HTML / three.js renderers
  `explain.html` and `stage3d.html`, faster-whisper, numpy, OpenCV) and a size (S: an hour or two, M: a day,
  L: several days).
- Name where it fits the user's own work (their brand, their channels, the kind of video they make). Pick the best
  one or two, not a list.

Rules for every idea:
- Free, open-source tools by default. AI tools (for example an ElevenLabs voice) are fine when the user picks them,
  but never make a fake of a real person (no cloned voice or face of someone who has not agreed).
- Nothing is uploaded unless the user chooses a service. Transcription and mattes run locally.
- Person cutouts and mattes use BiRefNet through rembg (`engine/cutout.py`, `engine/matte.py`; the models folder is
  set by `engine/models.py`).
- Everyday UI (websites, app panels) never bounces: `ui` / `uiExit` springs only. One hero bounce per video at most.
- Website ideas go through the website kit, which builds the compliance checklist in (`web/build.py`, then
  `web/compliance.py`).
- Study only: rebuild the idea in the user's own brand and content; never trace or reuse the reference's assets.

## 6. Optional: a quick proof still

When a mapped tool can show the idea in one frame, render a still (never a full render during intake) and `Read`
it, so the user sees it in their colours:

```bash
python3 engine/stage3d.py burst $R/proof Proof --lines "ONE|TWO|THREE" --frames 1.0 --profile demo
```

These tools take `--frames t1,t2` for stills: `logo/motion.py`, `engine/stage3d.py`, `explain.py`, `matte.py`,
`behind.py`, `quote.py`, `progressbar.py`, `statcard.py`, `fxpack.py`, `sketch.py`, `beforeafter.py`,
`routemap.py`, `hopwords.py`. The others (captions, talkedit, vertical, sourcecard, cutout, flipbook, `web/build.py`)
have no `--frames`; skip the proof still for them. Run one heavy job at a time. A full build later goes
through its own tool and then the video-gates skill (`engine/qa.py`) before anyone sees it.

## 7. Write it into the ideas file

Edit in place; never rewrite or reorder other entries. Formats are in
[references/ideas-file.md](references/ideas-file.md).

- Append one row to **Reference log**: Date | Reference (creator, link or file) | Category | What makes it work |
  Ideas (IDs).
- Append new ideas as rows in **Ideas**: ID | Idea | How to build | Size | Fits | Status | From.
- For an idea already listed, add the new reference to its "From" cell and a short note of what is new.
- If this reference changes what to build first, edit the **Build order** list (move, add or drop one line).
- Keep notes and links only: no frames, clips or screenshots of someone else's work in the ideas file.

## 8. Reply

Two to five lines: what makes it work (with one number), the ID(s) it became or matched, the tool it maps to,
where it fits the user's work, and any build-order change. Give the ideas file path. No recap of the file.

## Worked example

The user drops `~/Desktop/glass-cards.mov` (a 23 s product promo) and says "this is fire".

```bash
cd "$VIDEO_ENGINE" && R=out/refs/2026-11-09-glass-cards && mkdir -p $R
ffprobe -v error -show_entries format=duration -of csv=p=0 ~/Desktop/glass-cards.mov    # 23.4
python3 engine/sheet.py ~/Desktop/glass-cards.mov $R/sheet.jpg 0 23.3 --n 30 --cols 6 --w 280
python3 engine/measure.py probe ~/Desktop/glass-cards.mov --out $R/probe
python3 -P engine/beatmap.py ~/Desktop/glass-cards.mov --profile demo --out $R/beatmap.json
python3 engine/stage3d.py burst $R/proof Proof --lines "FAST|LOCAL|YOURS" --frames 1.0 --profile demo
```

Findings: 14 cuts in 23 s, every cut on a beat at 120 BPM, the product reveal on the drop at 12.0 s; glass cards
orbit a presenter and pass behind them; dark mesh-gradient ground, one warm accent. Mapping: glass cards around a
person = `stage3d.py orbit` with a `matte.py` matte (O4, covered); title swaps behind light bursts =
`stage3d.py burst` (P2, covered); the cards' frosted refraction is a gap, logged as N3 "frosted glass on orbit
cards" (M). Log row and idea row appended, N3 placed second in Build order.

Reply: "Cuts on every beat (14 in 23 s) and the reveal lands on the drop at 12 s; the glass cards pass behind the
presenter. Matches O4 orbit + P2 burst; new N3: frosted glass on the orbit cards (M). Fits your product launch
promo. N3 is now second in the build order. Logged in REFERENCE_IDEAS.md."
