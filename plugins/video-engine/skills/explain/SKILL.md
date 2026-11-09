---
name: explain
description: Makes retention-style explainer videos from a topic with the video engine. Finds the picture that shows the real mechanism, computes every number on screen from real maths or data, writes the beats as a storyboard.json, renders an approval board (one still per beat) for the user to sign off, then renders a 16:9 MP4 plus Premiere XML with spring motion, captions, a voice-over or on-screen text, and a music bed, and QA-checks it. Use when the user says "make an explainer on...", "explain how X works in a video", "animated explainer", "why does a mic feed back, as a video", "storyboard this explanation", "turn this concept into a short video", or "render the explainer board".
---

# Explain

Turn a topic into a finished explainer: find the visual idea, write the beat sheet, get the board approved, render,
QA. The hard part is the creative step, not the rendering.

## Before anything: find the engine and the profile

1. Check `$VIDEO_ENGINE` (`echo "$VIDEO_ENGINE"`). If it is unset or the folder has no `engine/explain.py`, ask the
   user where their clone of https://github.com/thestealthgoat/stealth-goat-video-engines is, or run the
   `getting-started` skill to set it up. Without a clone, setup is
   `git clone https://github.com/thestealthgoat/stealth-goat-video-engines`, then `./setup.sh` inside it (it targets
   macOS with Homebrew), then `export VIDEO_ENGINE="<path to the clone>"`. Run every command from there:
   `cd "$VIDEO_ENGINE" && python3 engine/<tool>.py ...`.
2. Pick the profile. Every tool takes `--profile <name>` (else `$VIDEO_PROFILE`, else `local.json`). Use the user's
   own brand profile if they have one (made from `profiles/_template` with `python3 engine/vprofile.py new <name>`;
   see `docs/LAYOUT.md`), else `--profile demo` to try things (`python3 engine/vprofile.py list` shows what exists).
   If `demo` is missing (a clone older than the one that ships it), make a stand-in from the template:
   `python3 engine/vprofile.py new demo --display "Demo" --primary "#0B3D2E" --accent "#F2B705"`.

Tools used here: `engine/storyboard.py` (pace / retime / check / board), `engine/explain.py` (render, drawing with
`engine/explain.html`), `engine/musicbed.py` (a synthesised bed), `engine/sourcecard.py` (a real web page with the
exact phrase boxed), `engine/qa.py --kind explainer` (the QA gate). Worked example: `examples/explain/lissajous/`
(`make.py`, `storyboard.json`, `VO_SCRIPT.md`).

## The core rule: show the mechanism, not a metaphor

No stock images, no clip-art symbols. Make the real thing visible and compute the picture from real maths or real
data. The numbers on screen are true (ms, Hz, metres, dB), so the viewer trusts it and the visual explains itself.
Every number lives in the topic's `make.py`; never type a computed value into the storyboard by hand.

## Step 1: find the picture

Answer these before writing a word:
1. What is invisible here that could be made visible? (sound, voltage, signal, light, time, a ratio)
2. What is the smallest unit, and what happens when units combine?
3. What is the one knob? What happens as it turns from zero to extreme?
4. What would you see if time slowed down, or sped up until it blurs?
5. What would you see zoomed in, or out, by 10x, 100x, 1000x?
6. What is the surprising truth? ("a piano's fifth isn't 3:2")
7. What would all the cases look like side by side?

Give the user the 1-2 best picture ideas with a one-line pitch each, and let them choose.

## Step 2: pick one or two story patterns

| Pattern | How it goes |
|---|---|
| One knob, many worlds | sweep one value; each range reveals a different effect |
| Build-up | simplest part, then combine, combine, until the whole system |
| Scale journey | one continuous zoom, one idea per level (`scale` element) |
| Slow it down, speed it up | the parts slowly, then faster until they blur into the phenomenon |
| Everything at once | a grid of every case so the pattern pops |
| Prove it with the source | the real page with the exact phrase highlighted (`sourcecard.py` + `image` element) |

## Step 3: write the beat sheet as storyboard.json

Make a topic folder inside the engine folder at the same depth as the example, e.g. `packs/explain/<slug>/`, so the
example's `make.py` (which imports `engine/storyboard.py` from three folders up) works when copied:

```bash
cd "$VIDEO_ENGINE" && mkdir -p packs/explain && cp -R examples/explain/lissajous packs/explain/<slug>
```

Then rewrite `make.py` for the topic: compute the numbers, build the beats, call `storyboard.pace(...)` (or `retime`
when a voice-over exists), set `drop_at` and `duration`, and save `storyboard.json`. Keep generated audio and data
frames in the topic's `_build/` folder (the engine's `.gitignore` already ignores `**/_build/` and `**/out/`);
`make.py` regenerates them.

Beat rules:
- **Hook in the first second:** the counterintuitive claim, with motion on screen at frame 0 (a `burst`, a moving
  trace). `check` fails a first beat whose elements all have an `in` delay.
- **One idea per sentence, one beat per sentence.** Split long lines ("Push the fader," | "and one peak crosses the
  line first."). Aim for 2.0-3.5 spoken words a second.
- **One continuous canvas that transforms in place.** An element listed again with the same `id` stays and its numbers
  spring to the new values; a new element or a state change every 1-2 s; no hard cuts. Use `changes` for state
  changes inside a beat and `keep` for ids that stay without being re-listed.
- **One keyword per line** (`key`, boxed in the captions) and a big title word or number on screen.
- **The payoff lands on the music's drop:** `"drop": true` on that beat; `make.py` copies its `t0` into `drop_at`.
- **End on a question** ("Which interval should we draw next?").
- Times inside a beat (`at` on changes, pulses and bar items, `in`, `markAt`, `boxAt`) are seconds after the beat's
  start, so pacing and voice-over retiming never break them.

The element types (text, readout, flow, bars, plot, wave, knob, burst, image, scope, scale), their fields, the
storyboard top-level keys and the profile's `explain.*` keys are in
[references/storyboard-format.md](references/storyboard-format.md). The format's own summary is the docstring at the
top of `engine/storyboard.py` (`head -40 engine/storyboard.py`; `-h` lists only the subcommands).

## Step 4: one visual grammar per video

- Dark ground (the profile's `primary_deep`, else a darkened `primary`) with a soft radial glow; one meaning per colour.
- `signal` (gold `#F2C14E` unless the profile sets `explain.signal`) = what moves through the system.
- `hot` (the profile's `explain.hot`, else its accent) = over the line, the answer. Never use `hot` for something that
  has a real colour of its own (green light gets its own hex) and never for a good outcome.
- Small eyebrow + big title; real units on every readout; thin lines with glow; nothing decorative. Captions stay in
  one zone at the bottom.
- For a `scope` trace use `"color": "text"` so it reads on any ground.

What the engine does for you, so the storyboard doesn't fight it: text that would cross the 4% side margin shrinks to
fit; a readout whose label or unit changes fades the old number out and counts the new one up from 0 (it never tweens
through the old quantity); `decimals` switches, it doesn't spring; values of 10,000 and up are grouped (21,235); an
element re-declared with an `in` delay clears its old text at the cut; a caption keyword gets room for its box;
`burst` takes `r` to keep the rings inside the frame; the stage drifts slightly so no frame is ever frozen.

What it can't do: keep text off a trace, a grid line or another label. Lay columns out so they can't collide in the
widest profile font (the example puts the scope at x 0.40 and the words in a column at x 0.78), and give a readout its
real value on the beat it appears (never 0 plus a later change).

## Step 5: check, board, approval

Worked example on a fresh clone (`make.py` writes `examples/explain/lissajous/_build/` and `storyboard.json`; the
clone does not ship `_build/`, so run `make.py` first):

```bash
cd "$VIDEO_ENGINE"
python3 examples/explain/lissajous/make.py                                      # computes the numbers, writes storyboard.json
python3 engine/storyboard.py check examples/explain/lissajous/storyboard.json   # must end CHECK: OK
python3 engine/storyboard.py board examples/explain/lissajous/storyboard.json --out out/lissajous --profile demo
```

`check` enforces: every beat has a line and something on screen; beats are contiguous; no stretch longer than
`--max-scene` (default 2.5 s) without a planned new visual; speaking rate; motion in the first frame; known element
types; images and data files exist. Fix every FAIL in `make.py` and run it again.

`board` writes `out/lissajous/storyboard_board.jpg`: one still per beat (middle of the beat) with its number, time,
element types and line (the single stills it is built from, `storyboard_t<seconds>.png`, stay beside it). **Show the board to the user and wait for approval before the final render.** While waiting
it is fine to render a draft, and to pull single stills to check a moment:

```bash
python3 engine/explain.py examples/explain/lissajous/storyboard.json --out out/lissajous --profile demo --frames 1.0,29.0
```

Optional source card (needs the page to load in headless Chromium; `--dark` hides cookie banners and sticky headers):

```bash
python3 engine/sourcecard.py "<url>" "<exact phrase>" packs/explain/<slug>/src.png --dark
```

Add it to the storyboard's `"images"` map and show it with an `image` element (fields in the reference).

## Step 6: voice-over (optional)

Until a voice-over exists the piece runs as on-screen captions plus music, paced from the text. For a voice:
- Write `VO_SCRIPT.md` in the topic folder: the beats' lines in order, keyword in bold, plus the commands below. The
  example's `VO_SCRIPT.md` shows the shape.
- The user records it themselves, or uses an AI voice they set up (for example ElevenLabs). Never clone or imitate a
  real person's voice. Nothing is uploaded unless the user chooses that service.
- Save the take as a WAV in the topic folder (e.g. `packs/explain/<slug>/vo.wav`), then snap the beats to the words
  with local faster-whisper (nothing leaves the machine):

```bash
python3 engine/storyboard.py retime packs/explain/<slug>/storyboard.json --vo packs/explain/<slug>/vo.wav
```

`retime` writes `vo.words.json` next to the WAV and re-times every beat (inner times scale with each beat). When the
soundtrack or data frames are built from beat times (as in the example), have `make.py` read that words file and
re-time itself, then run `make.py` again so the demo audio follows the words. Check the example's `make.py` and
`VO_SCRIPT.md` for the exact file name it looks for.

## Step 7: render

One heavy render at a time. Music: either a synthesised bed (no samples, no licences) or the topic's own demo sound.

```bash
# a music bed, with a bar starting exactly on the payoff beat (read drop_at and duration from storyboard.json);
# musicbed.py creates out/<slug>/ if it doesn't exist yet
python3 engine/musicbed.py out/<slug>/bed.wav --dur <duration> --drop <drop_at>
python3 engine/explain.py packs/explain/<slug>/storyboard.json --out out/<slug> --profile <name> --music out/<slug>/bed.wav \
    [--vo packs/explain/<slug>/vo.wav --music-db -24]
```

The example's soundtrack is the two tones the scope draws (its storyboard sets `"audio": "linear"`, so the mix gets
one gain plus a peak limiter and keeps its real dynamics):

```bash
python3 engine/explain.py examples/explain/lissajous/storyboard.json --out out/lissajous --profile demo \
    --music examples/explain/lissajous/_build/tones.wav
```

Outputs in `--out`: `<name>.mp4` (H.264, 1080p at the profile's frame rate, mix levelled to the profile's
`delivery.loudness_lufs`) and `<name>.xml` (Premiere: one clip per beat, a marker on each). `<name>` defaults to the
storyboard's file name (`storyboard`); `--name` changes it. Other flags: `--aspect 9:16` (portrait; elements may
carry `"v": {...}` overrides for it), `--fps`, `--no-music`. With a voice-over, `--music-db` sets the bed under the
voice (default -18); without one the bed is the whole programme and `--music-db` has no effect.

## Step 8: QA before delivery

Run the QA gate (the `video-gates` skill) on every render before showing it:

```bash
python3 engine/qa.py out/lissajous/storyboard.mp4 --profile demo --kind explainer --max-scene 2.5 --cuts none --out out/lissajous/qa
```

On the worked example this ends `RESULT: PASS (0 warnings)` with exit code 0 (exit 1 = FAIL, 2 = unreadable file). The
full example render takes about five minutes on an Apple-silicon Mac and writes a ~40 MB MP4.

- `--kind explainer` adds the freshness gate: no stretch over `--max-scene` seconds without a new visual (a cut, a
  scene change, or a local state change such as a readout changing or an element landing; motion alone doesn't count).
- `--cuts none` means no cuts were planned. A storyboard with a planned `"cuts"` list takes
  `--shotlist packs/explain/<slug>/storyboard.json` instead, or its planned cuts show as unplanned jumps.
- Read `review.md` and `sheet.jpg` in the `--out` folder, fix every real FAIL (in `make.py`, then re-run), then do the
  fresh-eyes review from the `video-gates` skill.
- The gate can't see a trace exploding for four frames, text under another element, or a number that disagrees with
  the voice-over. Pull stills around every beat change (`--frames`) and look at them; if the user has more than one
  profile, check the widest-font one too.

## Done means

- `storyboard.py check` ends `CHECK: OK`; the user approved the board.
- The MP4 and XML are rendered with the user's profile; `qa.py` passes (or every remaining flag is explained).
- Every on-screen number traces back to `make.py`; the voice-over (if any) says the same numbers.
- Report the paths of the MP4, XML, board and QA folder to the user.
