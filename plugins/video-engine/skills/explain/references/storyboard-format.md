# storyboard.json reference

Read alongside the docstring at the top of `engine/storyboard.py` and the drawing code in `engine/explain.html`
(each element type is one function in its `DRAW` table). Coordinates and sizes are fractions: `x`, `w` of the frame
width, `y`, `h` of the frame height; a `size` or `r` is a share of the frame's short side (1080 px in 16:9).
Colours anywhere may be a role name (`text`, `dim`, `accent`, `signal`, `hot`, `key`, `bg`, `bg2`, `panel`) or a hex.

## Top level

| Key | Meaning |
|---|---|
| `topic` | title, printed on the approval board |
| `approved` | your own flag: set it to true once the user approves the board |
| `beats` | the list of beats (below) |
| `colors` | override roles for this video: `{"hot": "accent"}` (a profile colour name) or `{"signal": "#4FD1C5"}` |
| `images` | `{name: file.png}` for `image` elements (relative to the storyboard's folder); `check` fails a missing file |
| `data` | `{name: file.json}` for `scope` elements; `check` fails a missing file |
| `audio` | `"linear"`: level the mix with one measured gain plus a peak limiter instead of loudnorm (when the sound is the demo) |
| `drop_at` | the payoff beat's start (seconds), for `musicbed.py --drop` |
| `duration` | the programme length; else the last beat's `t1` + 0.6 s |
| `cuts` | planned hard cuts (seconds), read by `qa.py --shotlist <storyboard.json>` |
| `measured` | free-form: the computed numbers, kept for the record and the voice-over script |
| `vo` | written by `storyboard.py retime --vo`: the recording's path |

## A beat

| Key | Meaning |
|---|---|
| `say` | the spoken line (captions word by word; on-screen text until a voice-over exists) |
| `key` | the one highlighted word of the line (matched ignoring case and punctuation) |
| `t0`, `t1` | written by `storyboard.py pace` (from the text) or `retime` (from the voice-over) |
| `show` | the elements on screen in this beat (each has `id` and `type`) |
| `changes` | `[{"at": s, "id": ..., "set": {...}}]`: state changes inside the beat (`at` = seconds after `t0`) |
| `keep` | ids that stay on screen although this beat doesn't list them |
| `drop` | `true` on the payoff beat (your `make.py` copies its `t0` to `drop_at`) |
| `min` | minimum beat length in seconds for `pace` |
| `exit_at` | seconds after `t0` at which elements not listed in this beat leave (default 0) |
| `words` | written by `retime`: per-word times for the captions |

Element life: an element listed in the next beat with the same `id` and `type` stays and its numbers spring to the
new values (strings swap with a short slide); one not listed (and not in `keep`) exits with a fade and a small drift
up; a new one enters with a snappy slide plus fade, about 0.15 s after the cut. Every element takes `in` (seconds
after the beat starts) to delay its entrance, and `"v": {...}` overrides used only in a portrait (`--aspect 9:16`)
render. A keyframe may set `"spring": "smooth"` (default) or another spring.js preset.

## Element types

**text**: `text`, `role` (`eyebrow` small spaced caps in `dim` | `title` big head font | `body`), `x`, `y`, `size`
(defaults: title 0.13, eyebrow 0.028, body 0.045), `color`, `align` (`center` | `left` | `right`), `glow` (a colour).
Shrinks to fit inside the 4% side margin.

**readout**: a label above a big monospace number. `label`, `value`, `decimals`, `unit`, `prefix`, `x`, `y`, `size`
(default 0.06), `align`, `color`, `hot` (a colour: the number takes it and glows). The value springs when it changes;
a new label or unit swaps the quantity (old out, new counts up from 0). `fromKnob: {"id", "base", "hotAbove"}` ties
the value to a knob's `dB` (value = base x 10^(dB/20)), turning hot above `hotAbove`.

**flow**: a node graph with travelling pulses. `nodes: [{"id", "x", "y", "r" (default 0.055), "icon" (short text in
the circle), "label", "sub" (a mono line under the label)}]`, `edges: [[from, to, bend]]` (bend 0 = straight),
`pulses: [{"at", "path": [node ids], "seg" (s per edge, default 0.5), "amp" (dot size, default 1), "color"}]`,
`active: [node ids]` (ring in `activeColor`, default `signal`). Re-list the same flow with more nodes to build it up:
each new node enters on its beat and its edges draw on. Pulses of one flow id carry across beats.

**bars**: `x`, `y`, `w`, `h`, `items: [{"label", "value", "at"}]` (each bar rises at its `at`), `max` (top of the
scale, default 2), `line` (a dashed reference line; a bar above it, or above 1 without a line, is drawn in
`hotColor`, default `hot`), `lineLabel`, `color` (default `signal`).

**plot**: a curve that draws on left to right once. `x`, `y`, `w`, `h`, `xs`, `ys`, `xlog` (log x axis), `ymin`,
`ymax`, `xticks: [values]` (1000 and up shown as `1k`), `yticks: [[value, label]]`, `xlabel`, `ylabel`, `hline`
(threshold: the curve above it is filled and stroked in `hotColor`), `hlineLabel`, `color`, `mark: {"x", "y",
"label"}` with `markAt` and `markColor` (default `hot`).

**wave**: a tone whose amplitude steps once per lap, written on over `draw` seconds (default 1.4). `x`, `y`, `w`, `h`,
`env: [amplitude per lap]`, `max` (default 4), `cycles` per lap (default 5), `ref` (a same-level line at the first
lap's height, `refLabel`), `bracket` (text over one lap), `ticks` with `lap_ms` (a ms label under each lap), `color`.

**knob**: `x`, `y`, `r` (default 0.06), `value` (0-1, springs), `label`, `dB` (shown as +6 dB) or `valueText`, `color`.

**burst**: the hook's hit: shock rings and a white-hot flash. `x`, `y`, `at` (seconds after it enters), `r` (caps the
ring radius, share of the short side), `color` (default `hot`).

**image**: a real-source card from `sourcecard.py`. `src` (a key in `images`), `x`, `y`, `w`, `crop: [top, bottom]`
(a band of the screenshot), `box` and `rects` (copy them from the `.json` that `sourcecard.py` writes), `groups:
[{"rects", "at"}]` (several phrases landing one after another, from `--also`), `boxAt` (default 0.55 s after entry),
`push` (camera push, default 0.25) or `fill` (push until the box fills that share of the width), `dim` (darken the
page around the highlight), `credit` (from the `.json`).

**scope**: frames computed in `make.py` from real audio. `src` (a key in `data`), `mode` (`xy` | `spectrum` | `wave`),
`x`, `y`, `w`, `h`, `color` (use `text` so it reads on any ground), `trail` (phosphor frames, default 4), `gain`,
`grid` (graticule, default on), `peak` (spectrum top colour, default `hot`), `label`. The data file is
`{"fps", "t0", "mode", "frames": [...]}`: an `xy` frame is a flat list `[x0, y0, x1, y1, ...]` in -1..1; a `wave`
frame a list of samples in -1..1; a `spectrum` frame a list of dB values with optional `dbMin`, `dbMax` (default -80,
0) and `ticks: [[position 0-1, label]]` in the data file. An empty frame draws nothing.

**scale**: one continuous zoom through real sizes. `x`, `y`, `z` (log10 of the frame width in metres; springs beat to
beat, plus a slow constant push-in), `levels: [{"exp" (log10 of the level's width in metres), "shape" (`rect` |
`circle` | `grid` | `wave`), "label", "color", "dx", "dy" (offset as a share of its size), "aspect", "cells" (grid),
"cycles" (wave), "round" (rect corner)}]`. A level is drawn while it is between 1/400 and 6x the frame; a scale bar
shows the frame's width in real units.

## Profile keys the explainer reads

| Key | Effect |
|---|---|
| `brand.colors.primary_deep` | the ground (else `primary` darkened) |
| `brand.colors.text_dim` | `dim` (else `text` mixed toward the ground) |
| `brand.fonts.mono` | the readout face (else `body_semibold`, else `body`) |
| `explain.signal` | the `signal` colour (default `#F2C14E`) |
| `explain.hot` | the `hot` colour (default the accent) |
| `explain.key` | the caption keyword box (default the accent) |
| `explain.font_scale` | scales labels and captions (e.g. 1.2 for a condensed face) |
| `explain.head_caps` | `true` for a caps-only head face: units (dB, ms, Hz, kHz, x1.26) are set in the body face |
| `delivery.fps`, `delivery.loudness_lufs`, `delivery.true_peak_db` | render frame rate and mix level |

## The worked example: `examples/explain/lissajous/`

"Why some notes sound good together": two tones, one on each axis of an XY scope. The figure closes into a still
shape when the frequencies make a small whole-number ratio (unison 1:1 a circle, octave 2:1 a figure eight, fifth
3:2, fourth 4:3, major third 5:4); a tritone (45:32) never settles. The twist: a piano's equal-tempered fifth is
2^(7/12) = 1.4983, so on A220 the shape slowly turns at about 0.74 Hz. `make.py` synthesises the two sine tones
(`_build/tones.wav`, the soundtrack, so the storyboard sets `"audio": "linear"`), computes every scope frame from
those same waveforms (`_build/xy.json`), shows the tritone stroboscopically (its shape cycles faster than the frame
rate), lays the scope out left of centre with the words in their own column, puts the payoff on the drop, and writes
12 beats (about 40 s) with every number recorded under `measured`. Read it as the template for a topic's `make.py`.
