---
name: "video-gates"
description: "QA gate for any finished or near-finished video (edit, motion graphics, explainer): runs the machine pass (spec, motion, audio, loudness, cuts, flashes, clicks, hook and hold gates, freshness), reads the review sheet, then gets a fresh-eyes reviewer to score it against the last version. Use before showing or delivering any render."
---

# video-gates

Nothing is shown or delivered without this review. The process is fixed; only the film-specific criteria change.
The engine does the measuring; you do the looking. Run it on the animatic/preview and again on the final.

Engine: `engine/qa.py` in the video engine repo (it calls `engine/motion_check.py` and `engine/audio_check.py`).
Needs ffmpeg/ffprobe, numpy and Pillow. The delivery spec (size, fps, loudness, true peak, safe area) comes from the
profile: pass `--profile <name>`, or it uses `$VIDEO_PROFILE` / the machine default. If the user has no profile yet,
it runs with generic defaults (-14 LUFS, -1 dBTP, size not checked); offer to make one with
`python3 engine/vprofile.py new <name>`.

`python3 engine/vprofile.py show <name> --check` checks that the profile's fonts and folders exist on this machine.
Folders the profile lists under `optional_paths` (machine-only ones, e.g. a Dropbox folder under one person's home)
are printed as "optional, missing here" when absent and do not fail the check; anything else missing does.

## When to run

- Before you show any render to the user, and before anything is delivered or uploaded.
- After every fix round: re-run on the new render (the whole file; it is fast).
- On a preview it will warn about preview size; that is expected. Spec gates are judged on the final.

## 1. Machine pass (one command per kind)

```
# footage cut to music (reels, highlights, promos)
python3 engine/qa.py <video> --kind edit --shotlist <out dir>/_parts/list.txt (the render's concat list) or a cuts JSON [--holds ...] [--allow-stutter]

# motion graphics (cards, lower thirds, logo animations): strict motion gate + hold gate
python3 engine/qa.py <video> --kind motion --cuts none [--holds end:1.2] [--intended end_tail]

# loops and overlay pieces (a logo swing loop, a corner bug, a "presented by" lower third): as motion, but no hook
# and no end-tail gate (a loop has no opening or ending of its own)
python3 engine/qa.py <video> --kind loop --cuts none

# explainers: motion gates + freshness (a new visual at least every --max-scene seconds)
python3 engine/qa.py <video> --kind explainer --cuts <planned cuts or none> [--max-scene 2.5]
```

- `--cuts 1.5,4.2,...` or `--shotlist` (a render's `_parts/list.txt`, or a cuts JSON; not an edit list) gives the planned cuts; every other hard cut is an unplanned jump.
  `--cuts none` means no cuts are planned. Without either, cuts are only listed.
- A concat list holds absolute part paths of the shell that rendered it (e.g. `/sessions/<id>/mnt/...` from the
  device shell), and renderers often reuse an old list. When a listed part doesn't exist here, qa.py uses the file
  of the same name next to the list and says so once (also under "Notes" in `review.md`). It stops, naming both
  paths, only when neither exists; then pass `--cuts`.
- `--holds` declares planned stills (`a-b`, `start:N`, `end:N` seconds) for the motion gate. Fixed gates still apply:
  nothing static over 0.8 s in motion/explainer work, and the static tail is never over 1.5 s (unless declared
  with `--intended end_tail`, below).
- `--intended end_tail,hook` (names: `hook`, `hook_motion`, `hook_strong`, `end_tail`) is for a designed exception
  that no `--holds` / `--cuts` can declare: a logo intro holding its last frame for 1.6 s, or a piece that is not
  meant to grab a scroll. Those gates still run; a failure becomes an **INFO** line "declared intended" in the
  fixes and the gate table and is not counted in the verdict (the verdict says how many were declared intended).
  It is never a silent PASS. A designed end hold also needs `--holds end:N` (N = the hold in seconds), or the
  motion gate still fails it as a dead stretch. Use it only for what the brief or the template's design asks for, and say so to the
  user; a gate that fails without a reason is fixed, not declared.
- `--kind loop` lists the hook and end-tail gates as SKIP with their measurement; dead stretches, stutters, holds
  without life, pops, spec and audio are still gated.
- Frame rate: the profile's `delivery.fps` plus `delivery.fps_allowed` (other rates it delivers, e.g. 59.94 reels
  made of 29.97 material) are accepted; `--fps N` replaces both with exactly N (e.g. `--fps 60` for a 60p overlay).
  The rate is the file's average; when the average misses but the file declares an accepted constant rate
  (`r_frame_rate`) within 0.5%, spec is judged on the declared rate and the average is a **WARN**: the file has
  timestamp gaps or uneven frames (look at the stutter flags and the part joins), so treat it as a real issue to
  judge, not noise.
- Repeats on a regular cadence (29.97 material in a 59.94 file, 3:2 pulldown, a steady slow-motion conform) are
  recognised and reported once as a cadence note, not as stutters; a repeat that breaks the cadence is still a
  stutter. `--allow-stutter` (skip the repeat check) only when irregular repeats are there on purpose.
- `--silences a-b` declares planned silences. `--out <dir>` sets the review folder (default `./qa_<name>/`).
- Exit code: 0 PASS, 1 FAIL, 2 unreadable file.

It writes `review.md` (verdict, fix lines, gates, spec, loudness, shot table, manual checks), `sheet.jpg` (timeline,
one frame per shot with the safe area drawn, evidence strips before | flagged | after) and `qa.json`.

Gates measured: spec and clean decode; dead stretches and stutters; hard audio cuts at every cut; integrated LUFS
(+-1 LU) and true peak; unplanned cuts (scdet); 1-2 frame flashes and foreign frames; one-frame pops (warning);
audio clicks, dropouts and silence >= 0.5 s; something moves in the first 0.5 s; a strong moment (cut or big move)
by 2 s; no hold over 0.8 s without life; end card / static tail <= 1.5 s; explainer freshness. Gate results are
PASS, WARN, FAIL, SKIP (not run, e.g. no audio or `--kind loop`) or INFO (declared intended with `--intended`).

## 2. Read the review and the sheet

1. Read `review.md` completely.
2. `Read` `sheet.jpg`. Look at one frame per shot: composition, faces, text, contact.
3. For every FAIL and WARN, open its evidence strip and judge it by frame: **real**, **intended** or
   **false alarm**. Write the judgement next to the flag in `review.md`. Intended things (a planned flash cut, a
   declared hold) go into the cut list or `--holds` (a designed end hold or a deliberately soft opening into
   `--intended`, a loop or overlay into `--kind loop`) and the run is repeated, so the record stays clean.
4. Do the manual checks the machine cannot (listed in `review.md`), cropping frames with ffmpeg where needed:
   text at least 24 px from the edges and inside the profile's safe area (the cyan box), never over a face or other
   text, readable at phone size; every cut has a visible cause; no decorative wipes, inverts, added shake or light
   leaks; nothing cut by the frame edge; continuity across cuts.
5. Sound is measured, not heard: say so, and ask a person to listen before acceptance.

## 3. Fresh-eyes reviewer (H4)

You built it, so you never grade it. Spawn a sub-agent with **no context**: it gets only `sheet.jpg` (and any frame
crops or evidence strips you made) plus `review.md`, and, when there is one, the previous version's sheet and
review. Do not tell it what the video is meant to say. Prompt it to:

1. Say in one or two sentences what the video is about and where it got confused. If it misreads the point, that
   is a defect of the video, not of the reviewer.
2. Score it out of 10, **head to head against the last version** (which is better and why, by frame). No previous
   version: score against the brief's reference.
3. Flag anything cheap or templated. Slop list (any yes is a fix): corner labels, counters, timecodes, corner
   brackets, "headline left / card right" deck layouts, typed-out headlines with a caret, fades everywhere,
   repeated identical transitions, things that grow from zero, decorative effects not born from the picture.
4. List defects by frame and write every fix in the fix-line format:
   `f<start>-f<end> (mm:ss.s) - what is wrong - why it matters - concrete fix (with a number when possible)`

Put its answer under "Fresh-eyes review" in `review.md`. Fix, re-render the changed ranges, re-run steps 1-3 with
a new fresh reviewer. **Three rounds at most**; after the third, report what is left to the user instead of looping.

## 4. Verdict

Decide **ACCEPT**, **FIX** or **REBUILD** and tell the user: the verdict, the score against the last version, the
loudness numbers, and the remaining fix lines, most severe first. Keep `review.md`; delete sheets, crops and frame
dumps made only for looking once the review is done.
