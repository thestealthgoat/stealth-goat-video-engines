# qa.py gates, options and outputs (reference)

Everything here is from `engine/qa.py --help` and the code. Re-check with `python3 engine/qa.py --help` when in doubt.

## Command

```
python3 engine/qa.py <video> [--profile NAME] [--kind edit|motion|explainer|loop]
                     [--cuts 1.5,4.2,... | --cuts none | --shotlist <concat list or cuts JSON>]
                     [--holds a-b,start:N,end:N] [--intended end_tail,hook] [--max-scene 2.5]
                     [--silences a-b,...] [--allow-stutter] [--size WxH] [--fps N] [--width 320]
                     [--out <review dir>] [--no-sheet]
```

Exit code: 0 PASS, 1 FAIL, 2 unreadable file (or a bad argument, or a `--profile` that does not load).

## Kinds

| kind | for | differences |
|---|---|---|
| `edit` (default) | footage cut to music: reels, highlights, promos, talking-head edits | normal motion gate (dead stretch = 0.5 s still) |
| `motion` | motion graphics: cards, lower thirds, logo animations | strict motion gate (more than 3 flat frames in a row outside a hold is dead), hold gate, pops |
| `explainer` | explainers | normal motion gate (not strict) plus the hold gate, pops and the freshness gate (`--max-scene`, default 2.5 s) |
| `loop` | loops and overlays: a logo swing loop, a corner bug, a lower third | as `motion` (strict), but hook and end-tail gates are SKIP (with their measurement) |

## Options

| option | meaning |
|---|---|
| `--profile NAME` | profile name or path to a `profile.json`. Default `$VIDEO_PROFILE`, then `local.json`. With none at all, qa runs on generic defaults (-14 LUFS, -1 dBTP, yuv420p, 90 px safe area, size not checked) and says "none (generic defaults)". A `--profile` that fails to load exits 2. |
| `--cuts 1.5,4.2` | planned cut times in seconds. Every other detected hard cut is an unplanned jump (FAIL); a planned cut not detected is a WARN. A detected cut within 3 frames of a planned one counts as that cut. |
| `--cuts none` | no cuts are planned: every detected cut is unplanned. |
| `--shotlist FILE` | planned cuts from an ffmpeg concat list (`file '...'` lines, optional `duration` lines: cuts are the running sum of part durations) or a JSON: a plain list, `{"cuts": [...]}`, `{"starts": [...]}` or `{"shots": [{"start": ...}]}`. An edit list with `items` (in/out points) is refused: reel times depend on the renderer. A listed part that does not exist (a path from another machine) is looked for next to the list; qa says so once and stops, naming both paths, when neither exists. |
| (neither) | cuts are only listed; the "cuts vs plan" gate is SKIP. |
| `--holds` | planned stills: `a-b` seconds, `start:N`, `end:N`. Fixed limits still apply: no hold over 0.8 s without life (motion, explainer, loop), static tail at most 1.5 s. |
| `--intended` | names from `hook`, `hook_motion`, `hook_strong`, `end_tail`. Those gates still run; a failure becomes an INFO line "declared intended", not counted in the verdict. A designed end hold also needs `--holds end:N`. |
| `--max-scene S` | explainer: longest stretch without a new visual (default 2.5 s). |
| `--silences a-b` | planned silences, not flagged. |
| `--allow-stutter` | skip the repeat check, only when irregular repeated frames are there on purpose. |
| `--size WxH`, `--fps N` | replace the profile's delivery sizes / rates. `--fps` replaces both `delivery.fps` and `delivery.fps_allowed`. |
| `--width` | analysis width in px (default 320). |
| `--out DIR` | review folder (default `./qa_<video name>/` in the current folder). |
| `--no-sheet` | skip `sheet.jpg`. Do not use it for a review you are going to judge. |

## Gates (one row each in review.md)

| gate | what it measures | target |
|---|---|---|
| integrity and spec | size, fps, frame count, pixel format, audio present; clean decode | the profile's `delivery` block |
| motion | `engine/motion_check.py`: dead stretches and stutters (1-2 frame repeats mid-motion). Regular repeat cadences (29.97 in 59.94, 3:2 pulldown) are a note, or a WARN when lower-rate material was conformed by repeating frames | no dead stretch, no stutter |
| flashes and foreign frames | 1-2 frame luma spikes/drops; a single frame unlike both neighbors | none unplanned |
| cuts vs plan | ffmpeg scdet hard cuts against `--cuts` / `--shotlist` | no unplanned cut |
| pops | an element appearing or vanishing in one frame (motion, explainer, loop) | WARN only |
| hook: motion by 0.5 s | first visible change | <= 0.5 s |
| hook: strong moment by 2 s | a cut or a big move (>= 20 % of the frame in 0.2 s), up to and including frame round(2 × fps): at 29.97 fps a cut at 2.002 s (frame 60) counts, one at 2.035 s does not. | <= 2.0 s |
| holds | no hold over 0.8 s without life (motion, explainer, loop) | <= 0.8 s |
| end card / static tail | the still at the end | <= 1.5 s |
| hard audio cuts | `engine/audio_check.py` at every cut: an audio change without a fade | every change fades |
| loudness | integrated LUFS | `delivery.loudness_lufs` +-1 LU |
| true peak | dBTP | <= `delivery.true_peak_db` |
| clicks, dropouts, silence | sample discontinuities, digital silence inside the program, silence >= 0.5 s | none (outside `--silences`) |
| freshness | explainer only: a new visual (a cut, a scene change, or a part of the frame that changes and stays changed) at least every `--max-scene` s. A dot passing through or a steady drift does not count | <= `--max-scene` |

Results: **PASS**, **WARN**, **FAIL**, **SKIP** (not run: no audio, `--kind loop`, no cut plan), **INFO** (declared
with `--intended`). A silent file as `edit` or `explainer` gets a WARN ("no audio stream"); a silent overlay belongs in
`--kind motion` or `loop`.

## Frame rate rules

Accepted rates are `delivery.fps` plus `delivery.fps_allowed` (or only `--fps`). The rate judged is the file's average
(`avg_frame_rate`). When the average misses but the file declares an accepted rate (`r_frame_rate`) within 0.5 %, spec
is judged on the declared rate and the average is a WARN: the file has timestamp gaps or uneven frames. Treat that
WARN as a real issue: look at the stutter flags and the part joins.

## Outputs

- `review.md`: verdict, fix lines (most severe first), gate table, spec, loudness, shot table (every detected cut:
  frame, time, scdet score, planned yes/NO, offset), manual checks, an empty "Fresh-eyes review" section, coverage,
  the tool output.
- `sheet.jpg`: timeline (lanes for change, luma, big move and audio dB; flags as red FAIL / amber WARN bars; planned cuts as green lines, detected cuts white, red when unplanned), one frame per shot with the profile's
  safe area drawn as a cyan box, evidence strips (before | flagged | after) for up to 10 flags.
- `qa.json`: `spec`, `loudness`, `planned_cuts` (seconds), `cuts` (`frame`, `t`, `score`, `planned`, `offset`),
  `freshness_events`, `gates`, `flags` (`kind`, `sev`, `f0`, `f1`, `t0`, `t1`, `what`, `why`, `fix`), `fix_lines`,
  and `notes` / `intended` when present.

## Fix-line format

Every flag, and every defect you or the reviewer find by eye, is written the same way:

```
f<start>-f<end> (mm:ss.s) - what is wrong - why it matters - concrete fix (with a number when possible)
```

Example: `f412-f415 (00:13.7) - the title card scales past the frame for 3 frames, then snaps back - reads as a render
glitch - clamp the spring overshoot to 1.04 or start the scale at 0.9`.
