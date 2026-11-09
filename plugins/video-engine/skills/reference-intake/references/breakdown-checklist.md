# Breakdown checklist

What to look for in each area, and the measurement that answers it. Only measure what would change the build.

## Structure

- **Hook**: what happens in the first 1-2 s? A cut, a hit, a big move (20% of the frame or more in 0.2 s), a
  question, a face? `qa.py` reports the hook directly;
  `python3 engine/sheet.py ref.mp4 $R/hook.jpg 0 2 --n 12` shows it.
- **Beats**: list them in order, one line each (setup, turn, payoff). For speech, split at sentence ends in
  `<name>.words.json`.
- **Payoff**: where it lands (time in seconds) and whether the music drops there (`beatmap.json` `drop`).
- **Ending**: hard out, end card, loop back to the start (a seamless loop is a choice worth noting).

## Timing

- Cuts per second and the longest shot: `probe.json` `cuts`, or the shot table in `qa.py`'s `review.md`.
- New visuals per second and the longest stretch with nothing new: `qa.py` `freshness` (explainers aim for a new
  visual every 1-2 s; the engine's storyboard check flags stretches over 2.5 s).
- What the cuts follow: beats, downbeats, the drop (compare cut times with `beatmap.json` `beats` / `downbeats`),
  or the words (compare with `words.json`).
- Holds: where the piece deliberately stops moving, and for how long.

## Motion

- Entrances: from the edge, from oversize, from blur, by mask, by draw-on. Nothing good scales up from zero.
- Exits: faster than entrances? Accelerating away?
- Overshoot: none (UI-like), small and late (pro motion work), or one big hero bounce.
- Camera: locked, slow push, hand-held drift, impact shake on a hit.
- To put a number on one move: `measure.py track` the element from a frame where it is fully visible, then
  `measure.py fit`; it prints zeta, omega and the nearest preset.
- Dead time: `python3 engine/motion_check.py ref.mp4 --strict --sheet $R/dead.jpg` shows stretches where nothing moves.

## Type

- Class: condensed sans, geometric sans, serif, mono, hand-drawn.
- Scale: headline height as a share of the frame; how many words on screen at once.
- Case and weight; outlined or filled; boxed keyword.
- How text arrives: per word on speech, per line, typed, swapped in place, masked.
- Where it sits: safe area kept? Over faces (a fault) or beside them?

## Colour and light

- Palette: `probe.json` `shots[].palette` (hex and share) and `accent` per shot.
- Ground: flat colour, gradient, mesh gradient, footage, blurred footage.
- Accent discipline: one accent used only for the thing that matters, or many.
- Light: glow, bloom, rim light, grain, vignette, depth of field, light leaks (decorative leaks are on the engine's
  slop list).

## Sound

- Music: BPM, where the drop is, stops and silences (`beatmap.md`).
- Voice: speaking rate in words per second (`words.json`: word count over speaking time; the engine's storyboard
  check wants 2.0-3.5).
- Sound design: hits on cuts, risers into the payoff, whooshes on moves.
- Loudness: integrated LUFS from `qa.py` (useful to compare, not a verdict on someone else's file).

## Clichés to call out

The engine's QA sheet lists these as cheap or templated: corner labels, counters, timecodes, corner brackets,
"headline left, card right" deck layouts, typed-out headlines with a caret, fades everywhere, decorative wipes,
inverts, added shake, light leaks. If a reference leans on them, say so and do not log them as ideas.
