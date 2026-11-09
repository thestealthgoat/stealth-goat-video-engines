# Motion toolkit: springs, the motion gate and bar maps

The engine's motion layer has four parts. **Spring physics** (`spring.py` / `spring.js`) drives everything that
animates, with camera, hand-held and impact-shake helpers. **`motion_check.py`** is a gate that fails a render with
dead stretches or stuttering frames, the way `audio_check.py` does for sound. **`beatmap.py`** builds a bar map of a
music track (beats, downbeats, sections, the drop, stops), and **`beatsnap.py`** snaps an edit's cuts onto it.
**`measure.py`** measures a finished motion piece so it can be rebuilt on springs. Part of the
[Stealth Goat video engines](../README.md); see [docs/TOOLS.md](../docs/TOOLS.md) for every tool in the repo.

## Quick start

Run from the repo root after `./setup.sh`. Everything is written to `out/motion/`, which git ignores.

```bash
# 1. Every spring preset with its settle time and overshoot
python3 engine/spring.py

# 2. Render a logo intro on the demo profile, then gate it (the intro holds the finished logo to the end: declare it)
python3 logo/vectorize.py profiles/demo/assets/demo_logo.png out/motion Demo
python3 logo/motion.py out/motion/Demo.svg out/motion Demo intro --profile demo
python3 engine/motion_check.py out/motion/Demo_intro.mp4 --strict --holds end:2.2 --sheet out/motion/check.jpg

# 3. A bar map of a synthetic 120 BPM beat (or any track of your own)
mkdir -p out/motion
ffmpeg -nostdin -v error -y -f lavfi \
  -i "aevalsrc='0.8*sin(2*PI*60*t)*exp(-25*mod(t,0.5))+0.5*sin(2*PI*2000*t)*exp(-80*mod(t,0.25))':d=40" \
  out/motion/beat120.wav
python3 engine/beatmap.py out/motion/beat120.wav --profile demo --out out/motion/beatmap.json
```

The motion check should end `RESULT: PASS`; read `out/motion/check.jpg` for the timeline. The bar map prints
`BPM 120.0` and writes `beatmap.json` plus a readable `beatmap.md`. The full intro render takes a few minutes.

## Where the files live

- `engine/`: `spring.py`, `spring.js`, `motion_check.py`, `beatmap.py`, `beatsnap.py`, `measure.py`.
- `logo/spring.js` is a byte copy of `engine/spring.js`, loaded by `logo/motion.html` with
  `<script src="spring.js"></script>`. Edit `engine/spring.js`, then copy it over; `tests/test_spring.py` fails when
  the two differ.
- `beatmap.py` is adapted from Higgsfield's MIT-licensed `beatmap.py`; the original and its license are in
  `vendor/higgsfield/`, credits in [NOTICE.md](../NOTICE.md).

## Springs: motion that settles like a real object

Each frame is drawn from a timestamp, so motion must be a pure function of time. `spring.py` and `spring.js` solve the
damped-spring equation exactly, so any frame can be drawn on its own (seekable: the same t always gives the same
picture). No CSS transitions, no `@keyframes`, no ease-in-out curves, no frame-by-frame simulation.

| Preset | ζ / ω | Settles | Overshoot | Use for |
|---|---|---|---|---|
| `snappy` | 0.75 / 20 | 0.36 s | 2.8% | lower thirds, player cards, panels |
| `bouncy` | 0.42 / 17 | 0.70 s | 23% | playful entrances, logo landings |
| `slam` | 0.30 / 26 | 0.67 s | 37% | hard hits: logo slam, score pop |
| `smooth` | 1.00 / 12 | 0.62 s | 0% | fades, camera pushes, text that must not wobble |
| `gentle` | 0.90 / 8 | 0.69 s | 0.2% | slow drifts, background moves |
| `ui` | 1.00 / 37 | 0.20 s | 0% | website and app UI (menus, popovers, toggles); everyday UI never bounces |
| `uiExit` | 1.00 / 46 | 0.16 s | 0% | UI exits, about 20% faster than entrances |

**Default to `snappy` or a preset with no overshoot.** Measured professional work overshoots on fewer than 9% of
moves, late and small (from the Apache-2.0 motionmaxxing study). Use `bouncy` or `slam` for one hero moment per
piece at most. Things arrive from oversize (logos at about 3.5×) or from the edge; nothing scales up from 0. Landings
decelerate, exits accelerate.

```js
// JavaScript (motion.html, or any renderFrame(t))
const x = Spring.at(t, { from: -400, to: 0, start: 0.35, preset: 'snappy' });   // card slides in at 0.35 s
const s = Spring.at(t, { from: 0.6, to: 1, start: 0.42, preset: 'slam' });      // logo lands with a bounce
const o = Spring.clamp01(Spring.progress(t, { start: 0.35, preset: 'smooth' })); // opacity never overshoots
const starts = Spring.stagger(4, 0.5, 0.06);                                      // 4 lines, 60 ms apart
const holdFrom = 0.35 + Spring.settle({ preset: 'snappy' });                      // when the card is at rest
const s2 = 1 + Spring.ring(t, { start: 0.42, amp: 0.06, freq: 6, decay: 9 });    // follow-through wobble after an impact
```

```python
# Python (PIL overlays and other frame-by-frame renderers)
from spring import spring_at, progress, clamp01, settle, stagger
x = spring_at(t, frm=-400, to=0, start=0.35, preset="snappy")
```

### Camera, hand-held and impact shake

The same names and math exist in both files, checked against each other by `tests/test_spring.py`. All are pure
functions of t: no state and no random numbers at draw time, so any frame renders on its own and re-renders
identically.

| Helper | What it gives | Use for |
|---|---|---|
| `ring(t, start, amp=0.06, freq=6, decay=9)` (JS: `ring(t, {start, amp, freq, decay})`) | a damped sine from 0 at `start`, to add to a resting value | follow-through after a landing: `scale = 1 + ring(t, 0.42)` |
| `handheld(t, amp=4, freq=0.5, seed=0)` | `(dx, dy)` / `[dx, dy]`: three sines per axis (×1, ×2.17 and ×4.31 of `freq`, weights 1 / 0.45 / 0.2), phases from an integer hash of `seed`; never more than `amp` | a camera that is never dead still; a different `seed` per shot |
| `shake(t, hit, amp=12, decay=8, freq=14)` | a damped cosine: full `amp` on the hit frame, 0 before it | impact shake on the hit frame (slam, tackle, score pop); for 2D, call it twice with different `freq` |
| `camera_at(t, keys)` (JS also `cameraAt`) | `{x, y, zoom, ...}` | camera moves as a list of keys; each key starts a spring (default `smooth`) from the previous target, and overlapping moves add up without a jump |

```python
from spring import handheld, shake, camera_at
cam = camera_at(t, [{"t": 0, "x": 0, "y": 0, "zoom": 1.0},          # first key = starting pose
                    {"t": 1.2, "zoom": 1.15, "preset": "smooth"},     # push in from 1.2 s
                    {"t": 3.0, "x": -120, "preset": "gentle"}])       # drift left from 3.0 s; zoom holds
dx, dy = handheld(t, amp=6, freq=0.6, seed=3)
x = cam["x"] + dx
y = cam["y"] + dy + shake(t, hit=2.40, amp=14, decay=9, freq=13)   # hit frame at 2.40 s
```

```js
const cam = Spring.camera_at(t, [{ t: 0, x: 0, y: 0, zoom: 1 }, { t: 1.2, zoom: 1.15, preset: 'smooth' }]);
const [dx, dy] = Spring.handheld(t, 6, 0.6, 3);
const y = cam.y + dy + Spring.shake(t, 2.40, 14, 9, 13);
```

A key may use `preset`, or `zeta` / `omega` (and `v0`). Fields a key leaves out hold their last value, and any other
numeric field (for example `rot`) is chained the same way. Put event times (hits, key times) in named constants at the
top of the piece, taken from the bar map when the music decides them. The QA gate forbids decorative shake: use
`shake` only on a real impact, and keep `handheld` small (a few pixels at 1080p).

### Rules of thumb

- Position and scale use springs and may overshoot. **Opacity never overshoots**: use `smooth` or `clamp01`.
- Plan holds and the next beat from `settle()`, not from a guessed duration.
- `velocity()` gives units per second, for motion blur or squash-and-stretch on fast moves.
- A lower `zeta` gives more bounce, a higher `omega` is faster. Tune one at a time.

## motion_check.py: dead frames and stutters

```bash
python3 engine/motion_check.py <video> [--holds 3.5-4.0,start:0.3,end:1.5] [--sheet check.jpg] [--strict] [--json result.json]
```

It finds two faults:

- **dead**: at least `--min-dead` (default 0.5 s) where nothing on screen moves, outside a planned hold. A still that
  settles into a planned hold is fine; only the time outside holds counts.
- **stutter**: a 1-2 frame repeat in the middle of motion (a dropped or duplicated render frame). Repeats on a regular
  cadence (29.97 material in a 59.94 file, 3:2 pulldown, a steady slow-motion conform) are listed once as a
  "cadence" note instead.

Options:

- `--holds` lists intentional stills: `a-b` seconds, `start:N`, `end:N`. The logo-motion `intro`, for example, holds
  on its last frame, so use `--holds end:2.2` (the full QA call for it is
  `qa.py --kind motion --cuts none --fps 60 --intended end_tail --holds end:2.2`).
- `--sheet` writes one image: a motion timeline (red = fail, blue = allowed hold) plus frames from every flagged
  span. **Read that image instead of watching every frame.**
- `--strict` is for short motion-graphics pieces: more than 3 flat frames in a row outside a hold count as dead,
  matching professional work where something moves on about 99% of frames. It also fails a still opening (something
  should move in the first 0.5 s). Edits and footage keep the 0.5 s default.
- `--allow-stutter` turns off the stutter check for edits that contain 24p source conformed to 29.97/30, where
  pulldown repeats frames on purpose.
- `--still-frac` (default 0.003, 0.3% of pixels) is how much of the frame must differ from the start of a still before
  it counts as motion. A spring's sub-pixel settle stays under it, and a small element drifting across the frame goes
  over it. Raise it if a noisy source (grain, LED walls) never reads as still.
- `--json` writes the result for logs.

Alpha video (ProRes 4444) is composited on grey first, so an alpha-only fade still counts as motion. Exit codes:
0 = PASS, 1 = FAIL, 2 = the file could not be read. `engine/qa.py` runs this gate as part of its full check.

It was tested on rendered clips with a planted 1 s freeze, a planted duplicate frame mid-spring, an alpha-only fade, a
clean clip with ambient drift (PASS, no false stutter at spring peaks), and a 24p to 29.97 pulldown (7 stutters
flagged, PASS with `--allow-stutter`). `tests/test_motion_gate.py` plants the same kinds of fault in synthetic clips.

## beatmap.py: the bar map of a track

```bash
python3 engine/beatmap.py music.mp3 [--start 56.5] [--dur 90] [--fps 29.97] --out out/x/beatmap.json   # also beatmap.md
python3 engine/beatmap.py music.mp3 --choose-window 15     # best 15 s windows (energy on frame 1, drop inside, clean end)
python3 engine/beatmap.py music.mp3 --bpm 120              # force the tempo after checking by ear; the phase is still fitted
```

It finds the bar, not just the BPM: beats, downbeats, bars grouped into sections (hook, full, mid, breath, build,
drop, stop, release), **the drop**, music **stops and silences**, pickups, risers and the top 10 transients. Every
time is in film seconds from `--start`, with frame numbers at `--fps` (default: the profile's `delivery.fps`, else
24). Input is anything ffmpeg decodes. Only numpy and scipy are needed.

Read `beatmap.md` first. When `tempo_ambiguous` is true (it prints `LOW-CONF`), check half and double tempo by ear
and rerun with `--bpm`. A low `downbeat_confidence` (under about 0.3) means beat 1 may be off: check the downbeats by
ear before cutting big moments to them. Short windows are less reliable than whole tracks (a few 20-30 s windows
still read an alias), so analyze from the music in point to the end of the track, which is what
`beatsnap.py --barmap auto` does, or pass `--bpm`.

### Changes from the original

All changes are in `estimate_tempo`, and each only moves an existing candidate to the top:

- **3:2 and 4:3 alias guard.** Before it, straight 150 BPM tracks read as 100 and straight 90 BPM tracks as 120. The
  kick check counts the kick contrast of the candidate or of its half or double, whichever is higher (a half-time kick
  sits on the half).
- **Aliases that are not a power of 2.** A winner without a binary subdivision loses to a straight candidate with more
  onset on its grid, a score within 1.5 and as much kick (one 20 s window of a 120 BPM track had read 164.96, an 11:8
  alias).
- **Half and double.** A winner whose odd beats are nearly empty (straight eighths counted as beats: 90 read as 180)
  gives way to its half tempo when that is straight and has at least as much kick. A winner whose kick is as strong off
  the beat as on it (four on the floor counted in half notes) gives way to its double. A winner with an empty
  subdivision and a straight half tempo is flagged `tempo_ambiguous`.

On 120 windows of four reference tracks (whole track, plus 20 s and 30 s windows every 10 s), wrong readings went from
33 to 17, and no window that read correctly before reads wrongly now. Whole-track results on that reference set (not
shipped):

| Track | beatmap.py | Reference | Note |
|---|---|---|---|
| Track A (90 BPM) | 90.0 | 90 | the original read 120 (4:3); tempo flagged ambiguous; downbeat confidence 0.21 |
| Track B (120 BPM) | 120.0 | 120 | confirmed by an independent fine comb; librosa's coarse tempo bin reads 123.05 |
| Track C (124 BPM) | 124.0 | 124 | downbeat confidence 0.05: downbeats unreliable |
| Track D (150 BPM) | 150.0 | 150 | the original read 100 (3:2); flagged ambiguous; a 30 s window from 56.5 s also reads 150 |

## beatsnap.py: cut to the bar map

`beatsnap.py` snaps the cuts of an edit list (JSON) to the music. By default it builds a bar map with `beatmap.py`
(the same as `--barmap auto`) and falls back, with a note, to the legacy snap when the bar map cannot be built.

```bash
python3 engine/beatsnap.py edit.json music.mp3 --open 1.8 --barmap auto --big-key card.big --payoff 9
python3 engine/beatmap.py music.mp3 --start <music in> --out barmap.json     # or build the bar map yourself:
python3 engine/beatsnap.py edit.json music.mp3 --barmap barmap.json
```

- Every cut snaps to the nearest bar-map beat within `--max-shift` (default 0.25 s).
- The cut **into a big item** lands on a downbeat within `--down-shift` (default 1.0 s), else on the nearest beat. An
  item is big when its `--big-key` value is truthy (a dotted key; default `big`).
- The cut **into the payoff** (`"payoff": true` on the item, or `--payoff N`, 1-based) lands on **the drop** when the
  drop is within `--drop-shift` (default 1.5 s); otherwise it prints the music in point that would put the drop there.
- **No cut lands inside a music stop or silence**: it moves to the stop's start or to the downbeat after it, whichever
  is nearer, even past the shift limits (and says so).

Only out points move, never in points; replays move in source time (`speed`). The bar map's `start` is matched to
`E['music'][0]['in']`, so build it with `--start <music in>` (`auto` does this). The edit gets an `E['beats']` record:
the bar map, the drop in reel seconds, and what every cut landed on. Leave the music argument out to use the edit's own
music path, mapped for this machine through `--profile`.

`--legacy-beats` snaps exactly as before the bar map existed (librosa beats, out points moved at most `--max-shift`).
Those beats follow librosa's coarse tempo bin and sit at onset-envelope peaks, so against the bar map they land 40-50 ms
late on average, wandering by about ±20 ms. In that mode `E['beats']['bpm']` is the coarse bin and
`E['beats']['bpm_measured']` records the tempo `beatmap.py` measures; no renderer reads either for timing.

## measure.py: measure a finished piece, fit springs, prove the rebuild

For rebuilding an After Effects open (or any finished motion piece) on springs. Free tools only: ffmpeg, OpenCV, numpy
and scipy. `python3 engine/measure.py -h` has the full method.

```bash
python3 engine/measure.py probe   open.mp4 --out m/probe [--start S --end S] [--dump]     # cuts, flicker, flashes, events, palette per shot
python3 engine/measure.py track   open.mp4 --out m/track --start S --end S --ref T --el name:x,y,w,h [--el ...]   # position, scale, rotation, opacity
python3 engine/measure.py fit     m/track/track.json [--only a,b] [--max-springs 1] [--start-at S] [--op-step 0.5]  # springs and flicker steps
python3 engine/measure.py compare open.mp4 rebuild.mp4 --start S --out side.mp4 [--audio]  # side by side plus per-frame SSIM (.ssim.csv)
```

- `track` follows each element with ECC (affine) frame to frame, outward from `--ref` (a frame where every element is
  fully visible). Under heavy motion blur it loses the lock: geometry then holds and the frame is marked `ok: false`.
  Measure those frames another way (for example the row of a bright edge) and refit with `--start-at` set to the
  section's first frame.
- Opacity is the contrast gain against `--ref`. Motion blur and defocus also lower it, so check the frame's mean
  brightness before reading a low gain as a fade.
- `fit` reports the nearest preset. Measured After Effects camera moves are often overdamped (zeta 1.2-2.5), so a
  rebuild keeps the measured zeta and omega and notes which preset is closest.
- First use: the closing title sign of a reference show open (124 frames), rebuilt as the `lockup` template in
  `logo/motion.py`. Per-frame SSIM averaged 0.78 (0.92 on the settled hold), with the original set as `--plate` and its
  text painted out.

## See also

- [Root README](../README.md): install, profiles and the tour of the engine.
- [docs/TOOLS.md](../docs/TOOLS.md): every tool in the repo.
- [logo/README.md](../logo/README.md): the animated logo templates built on these springs.
- [video-gates skill](../plugins/video-engine/skills/video-gates/SKILL.md): the full QA gate (`engine/qa.py`) that runs
  `motion_check.py` with the audio and cut checks.
