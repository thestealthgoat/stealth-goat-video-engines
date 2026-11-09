# Motion additions (2026-11-06, updated 2026-11-07)

Additions to the engine: **spring physics** for anything animated (plus camera, hand-held and impact-shake helpers),
**motion_check.py**, a gate that works like `audio_check.py` but for motion, and **beatmap.py**, a bar map of the music
that `beatsnap.py` can cut to.

## Where the files live
- `engine/`: `motion_check.py`, `spring.py`, `spring.js`, `beatmap.py`, `beatsnap.py`
- `logo/spring.js` is a byte copy of `engine/spring.js` (load it in `motion.html` with `<script src="spring.js"></script>`).
  Edit `engine/spring.js`, then copy it over; `tests/test_spring.py` fails when the two differ.

## spring.js / spring.py — motion that settles like a real object
Each frame is drawn from a timestamp, so motion must be a pure function of t. These files solve the
damped-spring equation exactly, so any frame can be drawn on its own (seekable, same t → same picture).
No CSS transitions, no `@keyframes`, no ease-in-out, no frame-by-frame simulation.

| preset | ζ / ω | settles | overshoot | use for |
|---|---|---|---|---|
| `snappy` | 0.75 / 20 | 0.36 s | 2.8% | lower thirds, player cards, panels, UI |
| `bouncy` | 0.42 / 17 | 0.70 s | 23% | playful entrances, logo lands |
| `slam` | 0.30 / 26 | 0.67 s | 37% | hard hits: logo slam, score pop |
| `smooth` | 1.00 / 12 | 0.62 s | 0% | fades, camera pushes, text that must not wobble |
| `gentle` | 0.90 / 8 | 0.69 s | 0.2% | slow drifts, background moves |
| `ui` | 1.00 / 37 | 0.20 s | 0% | website and app UI (menus, popovers, toggles); everyday UI never bounces |
| `uiExit` | 1.00 / 46 | 0.16 s | 0% | UI exits (about 20% faster than entrances) |

**Default to `snappy` or a no-overshoot preset.** Measured pro work overshoots on under 9% of moves, late and small
(motionmaxxing, Apache-2.0). Use `bouncy` / `slam` for one hero moment per piece at most. Things arrive from
oversize (logos ~3.5x) or from the edge; nothing scales up from 0. Landings decelerate, exits accelerate.

```js
// JS (motion.html / any renderFrame(t))
const x = Spring.at(t, { from: -400, to: 0, start: 0.35, preset: 'snappy' });   // card slides in at 0.35 s
const s = Spring.at(t, { from: 0.6, to: 1, start: 0.42, preset: 'slam' });      // logo lands with a bounce
const o = Spring.clamp01(Spring.progress(t, { start: 0.35, preset: 'smooth' })); // opacity never overshoots
const starts = Spring.stagger(4, 0.5, 0.06);                                      // 4 lines, 60 ms apart
const holdFrom = 0.35 + Spring.settle({ preset: 'snappy' });                      // when the card is at rest
const s2 = 1 + Spring.ring(t, { start: 0.42, amp: 0.06, freq: 6, decay: 9 });    // follow-through wobble after an impact
```
```python
# Python (render_reel.py / vreel.py cards, PIL overlays)
from spring import spring_at, progress, clamp01, settle, stagger
x = spring_at(t, frm=-400, to=0, start=0.35, preset="snappy")
```
`python3 spring.py` prints every preset's settle time and overshoot.

### Camera, hand-held and impact shake (2026-11-07)
Same names and maths in both files (checked against each other by `tests/test_spring.py`). All are pure functions of
t: no state, no random numbers at draw time, so any frame renders on its own and re-renders identically.

| helper | what it gives | use for |
|---|---|---|
| `ring(t, start, amp=0.06, freq=6, decay=9)` (JS: `ring(t, {start, amp, freq, decay})`) | damped sine from 0 at `start`, to ADD to a resting value | follow-through after a landing: `scale = 1 + ring(t, 0.42)` |
| `handheld(t, amp=4, freq=0.5, seed=0)` | `(dx, dy)` / `[dx, dy]`: three sines per axis (×1, ×2.17, ×4.31 of `freq`, weights 1 / 0.45 / 0.2), phases from an integer hash of `seed`; never more than `amp` | a camera that is never dead still; different `seed` per shot |
| `shake(t, hit, amp=12, decay=8, freq=14)` | damped cosine: full `amp` on the hit frame, 0 before it | impact shake on the hit frame (slam, tackle, score pop); for 2D call it twice with different `freq` |
| `camera_at(t, keys)` (JS also `cameraAt`) | `{x, y, zoom, ...}` | camera moves as a list of keys; each key starts a spring (default `smooth`) from the previous target; overlapping moves add up without a jump |

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
A key may use `preset`, or `zeta` / `omega` (and `v0`); fields it leaves out hold their last value, and any other
numeric field (e.g. `rot`) is chained the same way. Event times (hits, key times) belong in named constants at the top
of the piece, taken from the bar map below where the music decides them. The QA gate forbids decorative shake:
use `shake` only on a real impact, and keep `handheld` small (a few px at 1080p).

Rules of thumb
- Positions and scale use springs and may overshoot. **Opacity never overshoots**: use `smooth` or `clamp01`.
- Plan holds and the next beat from `settle()`, not from a guessed duration.
- `velocity()` gives units/s for motion blur or squash-and-stretch on fast moves.
- Lower `zeta` = more bounce, higher `omega` = faster. Tune one at a time.

## motion_check.py — dead frames and stutters
```
python3 motion_check.py <video> [--holds 3.5-4.0,start:0.3,end:1.5] [--sheet check.jpg]
```
Two failure types:
- **dead**: at least `--min-dead` (0.5 s) where nothing on screen moves, outside a planned hold.
  A still that settles into a planned hold is fine; only the time outside holds counts.
- **stutter**: a 1-2 frame repeat in the middle of motion (a dropped or duplicated render frame).

`--holds` lists intentional stills: `a-b` seconds, `start:N`, `end:N`. For example, the logo-motion `intro`
holds on its last frame, so use `--holds end:<hold length>`.
`--sheet` writes one image: a motion timeline (red = FAIL, blue = allowed hold) plus frames from every
flagged span. **Read that image instead of watching every frame.**
`--allow-stutter` turns off the stutter check for edits containing 24p source conformed to 29.97/30, where
pulldown repeats frames on purpose.
Alpha video (ProRes 4444) is composited on grey first, so an alpha-only fade still counts as motion.
`--strict` is for short motion-graphics pieces: more than 3 flat frames in a row (almost no pixel changed since the
previous frame) outside a planned hold is dead, matching pro work where something moves on ~99% of frames. It also
fails a still opening (something should move in the first 0.5 s). Edits and footage keep the 0.5 s default.
Exit 0 = PASS, 1 = FAIL, 2 = can't read the file. `--json` writes the result for the logs.

Tuning: `--still-frac` (default 0.003 = 0.3% of pixels must differ from the start of a still before it
counts as motion). A spring's sub-pixel settle stays under it, and a small element drifting across the frame
goes over it. Raise it if a noisy source (grain, LED walls) never reads as still.

Tested 2026-11-06 on rendered clips with a planted 1 s freeze, a planted duplicate frame mid-spring, an
alpha-only fade, a clean clip with ambient drift (PASS, no false stutter at spring peaks), and 24p→29.97
pulldown (7 stutters flagged, PASS with `--allow-stutter`).

## beatmap.py — the bar map of a track
From Higgsfield's MIT `beatmap.py` (credit and licence in `NOTICE.md`); numpy + scipy only.
```
python3 engine/beatmap.py "<music.mp3>" [--start 56.5] [--dur 90] [--fps 29.97] --out out/x/beatmap.json   # + beatmap.md
python3 engine/beatmap.py "<music.mp3>" --choose-window 15        # best 15 s windows (energy on frame 1, drop inside, clean end)
python3 engine/beatmap.py "<music.mp3>" --bpm 120                 # force the tempo after checking by ear; phase still fitted
```
It finds the bar, not just the BPM: beats, downbeats, bars with sections (hook / full / mid / breath / build / drop /
stop / release), **the drop**, music **stops and silences**, pickups, risers and the top-10 transients, all as film
seconds from `--start` plus frame numbers at `--fps` (default: the profile's `delivery.fps`, else 24). Read
`beatmap.md` first. When `tempo_ambiguous` is true (it prints LOW-CONF), check half/double by ear and rerun with
`--bpm`; a low `downbeat_confidence` (under ~0.3) means beat 1 may be off: check the downbeats by ear before
cutting big moments to them. Short windows are less reliable than whole tracks: a few 20-30 s windows still read
an alias (Track B from 20 s for 20 s reads 165; Track D windows after 60 s read 100, flagged LOW-CONF), so
analyse from the music in point to the end of the track (what `beatsnap.py --barmap auto` does) or pass `--bpm`.

Changes from the original (all in `estimate_tempo`, each one only moves an existing candidate to the top):
- a 3:2 / 4:3 alias guard (straight 150 BPM tracks read as 100 and straight 90 as 120 before); the kick check counts
  the kick contrast of the candidate or of its half/double, whichever is higher (a half-time kick sits on the half);
- a second alias guard for ratios that are not a power of 2 (Track B from 10 s for 20 s read 164.96, an 11:8 alias
  of 120): a winner without a binary subdivision loses to a straight candidate with more onset on its grid, a score
  within 1.5 and as much kick;
- half/double: a winner whose odd beats are nearly empty (straight eighths counted as beats: 90 read 180) gives way
  to its half tempo when that is straight and has at least as much kick; a winner whose kick is as strong off the
  beat as on it (four on the floor counted in half notes) gives way to its double. A winner with an empty
  subdivision and a straight half tempo is flagged `tempo_ambiguous`.
On 120 windows of four reference tracks (whole track, 20 s and 30 s windows every 10 s) wrong readings went from 33 to
17, and no window that read right before reads wrong now.
Checked 2026-11-07 on a reference music set (not shipped):

| track | beatmap | reference | note |
|---|---|---|---|
| Track A (90 BPM) | 90.0 | 90 | original read 120 (4:3); tempo flagged ambiguous; downbeat confidence 0.21 |
| Track B (120 BPM) | 120.0 | 120 | 120.0 by an independent fine comb as well; the old 123 was librosa's coarse tempo bin (123.05) |
| Track C (124 BPM) | 124.0 | 124 | downbeat confidence 0.05: downbeats unreliable |
| Track D (150 BPM) | 150.0 | 150 | original read 100 (3:2); flagged ambiguous. From a reel's music in (56.5 s) for 30 s: 150 (was 100) |

## beatsnap.py with a bar map
Since 2026-11-07 `beatsnap.py` cuts to the bar map by default (same as `--barmap auto`), falling back
with a note to the legacy snap when the bar map can't be built. `--legacy-beats` snaps exactly as before (librosa
beats, out points moved ≤ `--max-shift`). Those
beats follow librosa's coarse tempo bin (`E['beats']['bpm']`: 152 for Track D, 123.05 for Track B) and sit at
onset-envelope peaks: against the bar map they land 40-50 ms late on average, wandering by about ±20 ms (one highlight
reel's cuts 29-67 ms late, another's 16-55 ms). `E['beats']['bpm_measured']` now records the tempo beatmap.py measures
over the same music (150.0 / 120.01); nothing reads it for timing. The music is analysed for 300 s from the music in
point, or longer when the edit needs more (end of the reel + `--max-shift` per cut + 10 s); an edit that fits in 300 s
is analysed exactly as before. In bar map mode it cuts to the bar map (`--barmap auto` with nothing marked
big or payoff = every cut on the accurate grid, and none inside a music stop):
```
python3 engine/beatmap.py music.mp3 --start <music in> --out barmap.json        # or let beatsnap compute it:
python3 engine/beatsnap.py edit.json music.mp3 --open 1.8 --barmap auto --big-key card.td --payoff 9
```
- every cut snaps to the nearest bar-map beat within `--max-shift` (0.25 s);
- the cut **into a big item** lands on a downbeat within `--down-shift` (1.0 s), else the nearest beat. An item is big
  when its `--big-key` is truthy (dotted key, default `big`; `card.td` = touchdowns in the football edit lists);
- the cut **into the payoff** (`"payoff": true` on the item, or `--payoff N`, 1-based) lands on **the drop** when the
  drop is within `--drop-shift` (1.5 s); otherwise it prints the music in point that would put the drop there;
- **no cut lands inside a music stop or silence**: it moves to the stop's start or to the downbeat after it, whichever
  is nearer, even past the shift limits (reported).
Only out points move, never in points; replays move in source time (`speed`). The bar map's `start` is matched to
`E['music'][0]['in']`, so build it with `--start <music in>` (auto does). `E['beats']` records the bar map, the drop
(reel seconds) and every cut with what it landed on. Leave the music argument out to use the edit's own music path
(mapped for this machine through `--profile`).

## measure.py — measure a finished piece, fit springs, prove the rebuild (2026-11-08)
For rebuilding an After Effects open (or any finished motion piece) on springs. Free tools only (ffmpeg, OpenCV,
numpy, scipy). `python3 engine/measure.py -h` has the full method.
```
python3 engine/measure.py probe   open.mp4 --out m/probe [--start S --end S] [--dump]      # cuts, flicker runs, flashes, events, palette per shot
python3 engine/measure.py track   open.mp4 --out m/track --start S --end S --ref T --el name:x,y,w,h [--el ...]   # position, scale, rotation, opacity per element
python3 engine/measure.py fit     m/track/track.json [--only a,b] [--max-springs 1] [--start-at S] [--op-step 0.5]  # springs + flicker steps
python3 engine/measure.py compare open.mp4 rebuild.mp4 --start S --out side.mp4 [--audio]   # side-by-side + per-frame SSIM (.ssim.csv)
```
- `track` uses ECC (affine) frame to frame outward from `--ref` (a frame where every element is fully visible). Under
  heavy motion blur it loses the lock: geometry then holds and is marked `ok: false`; measure those frames another way
  (a bright edge's row, as the lockup did with its light bar) and refit with `--start-at` the section's first frame.
- Opacity is the contrast gain against `--ref`. Motion blur and defocus also lower it: check the frame mean brightness
  before reading a low gain as a fade (the lockup's early "0.4" was focus, not light).
- `fit` reports the nearest preset; measured AE camera moves are often overdamped (zeta 1.2-2.5), so the rebuild keeps
  the measured zeta / omega and says which preset is closest.
- First use: a reference show-open's closing title sign (124 frames) -> motion.html `lockup`; per-frame SSIM mean
  0.78 (settled hold 0.92), with the original set as `--plate` (text painted out).
