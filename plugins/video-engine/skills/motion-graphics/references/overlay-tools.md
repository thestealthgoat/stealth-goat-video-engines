# 2D overlay tools: flags, inputs, outputs

All tools run from the engine folder (`cd "$VIDEO_ENGINE"`), take `--profile <name>` and `--frames t1,t2` (stills
only, seconds). quote, progressbar, beforeafter, sketch and routemap end a full render with a `(qa: ...)` hint;
statcard (last line `DONE <base>`) and behind (`wrote <base>.mp4 (N frames)`) print none. Outputs land in `--out` (statcard:
the second positional argument) as `<name>_<suffix>`.

## statcard.py: stats lower third

```
statcard.py <stats.json> <out_dir> [--name N] [--size WxH] [--fps N] [--dur 5.5] [--start 0] [--bg image|video|'#hex']
            [--bg-in S] [--frames t1,t2] [--no-logo] [--ae] [--x0 PX] [--x1 PX] [--y1 PX] [--profile P]
```
- `stats.json` (template: `docs/stats_card_example.json`):
  `{"num": 12, "name": "Player Name", "big": "3 TDS", "stats": [["CAR", "21"], ["YDS", "148"]], "photo": "cutout.png",
  "count": true, "logo": true}`. Only `name` and `stats` (2-4 pairs; `{"label", "value"}` objects work too) are
  required. `photo` defaults to `<profile paths.headshot_cutouts>/<num>.png` when that file exists.
- Size and fps default to the profile's `delivery`. The card leaves at `--dur - 0.35` s.
- Colors: profile `primary`, `accent`, `text` (+ `text_dim`, `primary_deep` when present, else derived); fonts
  `head`, `body`, `body_semibold`; logo `brand.logo_png` (top right of the panel); position from `layout.safe_px`
  unless `--x0/--x1/--y1` move it.
- Outputs: `<name>_stats_Alpha.mov` (ProRes 4444, full frame), `<name>_stats.mp4` (preview on `--bg`, default the
  deep primary), `<name>_stats.png` (settled card, transparent). `--ae`: `<name>_stats.jsx` + `<name>_stats_ae/`.
- Motion: panel slides in (snappy), photo rises, text staggered, numbers count up on one spring (never past the
  value), a light sweep during the hold, smooth exit.

## behind.py: text behind the person (one word, timed words, or transcript keywords)

```
behind.py <video> --out DIR [--name N] [--t0 S] [--t1 S] (--text "WORD" | --events events.json | --auto words.json)
          [--every 3.5] [--matte <name>_matte.mp4] [--fill solid|gradient|<image>] [--color text|accent|'#hex']
          [--size 0.30] [--rotate cw|ccw|180] [--layer] [--max-height 1080] [--frames t1,t2] [--profile P]
```
- `--events`: `[{"text": "WORD", "t0": 1.2, "t1": 3.4}, ...]`, seconds inside the window.
- `--auto`: a faster-whisper words file (times in source seconds). One keyword per phrase (numbers, names, repeated
  or emphasized nouns), at least `--every` seconds apart, shown from just before it is said to the end of its phrase.
- Layers back to front: shot, text, person. The matte runs first (`engine/matte.py`, BiRefNet) unless `--matte`
  points at a `<name>_matte.mp4` made from the same window.
- Look: profile head font, cap height `--size` of the frame, never wider than the safe area, centered on the head.
  `--fill gradient` uses `brand.gradient`, else accent to text.
- Outputs: `<name>_behind.mp4` (sound cut sample-exactly, leveled to the profile loudness, faint room tone under
  it), `<name>_behind.events.json` (what was shown; edit and pass back with `--events`), with `--layer`
  `<name>_behind_text_Alpha.mov` (the text with the person cut out, for the editor).
- Default name: the video's file name.

## quote.py: pull-quote callout

```
quote.py --text "..." --by "Name" [--role "..."] --out DIR [--name quote]
         (--matte <name>_matte.json [--at 1.0] | --cutout person.png) [--bg video.mp4 [--bg-t S] | --bg '#hex']
         [--dur S] [--fps 29.97] [--size 1920x1080] [--frames t1,t2] [--profile P]
```
- The person: one frame of the matte's `_Alpha.mov` at `--at`, or any cut-out PNG (`engine/cutout.py in.jpg out.png`).
- Ground: the video blurred and darkened (default: the matte's own video), or a flat color.
- Font: the profile's `quote` font role if it has one, else the bundled serif `resources/fonts/Fraunces-SoftSemiBold.ttf`.
- Outputs: `<name>_quote.mp4`, `<name>_quote_Alpha.mov` (the card without the ground).
- Only real quotes the user supplies or that are in the footage.

## progressbar.py: progress bar with a face marker

```
progressbar.py <video> --out DIR [--name N] [--t0 S] [--t1 S] (--face face.png | --matte <name>_matte.json)
               [--chapters chapters.json] [--fps N] [--frames t1,t2] [--profile P]
```
- `--chapters`: `[{"t": 0, "title": "Welcome"}, {"t": 95.5, "title": "The story"}]`, seconds of the video.
- `--face`: any image; cropped to a circle around its alpha or center. `--matte`: the face from the first matte frame.
- The fill moves at the real clock; everything else springs. Colors: accent (fill, ring), text (titles), primary (track).
- Outputs: `<name>_progress_Alpha.mov` (ProRes 4444 full frame, to lay over the program), `<name>_progress.mp4`
  (bar over the video window, with sound). Default name: the video's file name. fps defaults to the video's.

## beforeafter.py: before / after showcase

```
beforeafter.py --before A --after B --out DIR [--name showcase] [--a0 S] [--b0 S] [--dur 6.5]
               [--labels "BEFORE|AFTER"] [--fps 29.97] [--size 1920x1080] [--frames t1,t2] [--profile P]
```
- A and B: videos or stills with the same framing. The accent-colored divider sweeps in, holds, scrubs back to
  BEFORE and across to AFTER, then clears to AFTER whole. Sound from B, leveled.
- Output: `<name>_ba.mp4`. Vertical: `--size 1080x1920`.

## sketch.py: sketch to real shot

```
sketch.py <video|still> --out DIR [--name sketch] [--t0 S] [--dur 6] [--draw 2.2] [--fps 29.97] [--size 1920x1080]
          [--frames t1,t2] [--profile P]
```
- The first frame's edges draw stroke by stroke, a pencil shade settles in, then the real footage paints in from
  the action outward and plays on. OpenCV only. Paper is the profile `text` color, ink its `primary`.
- Output: `<name>_sketch.mp4` with the source's sound from where the footage starts.

## routemap.py: route draw-on

```
routemap.py <route.gpx> --out DIR [--name route] [--dur 7] [--labels "Start|Finish"] [--map naturalearth|osm]
            [--fps 29.97] [--size 1920x1080] [--frames t1,t2] [--profile P]
routemap.py --gpx-from-videos "<folder or glob>" --gpx-out route.gpx
```
- `naturalearth` (default): public-domain 1:10m layers, downloaded once into `_cache/`, regional routes.
  `osm`: OpenStreetMap roads, water and towns from the Overpass API, for city-scale routes. The credit stays on screen.
- The route draws on a spring with a glowing head; the camera follows and settles on the whole route; distance
  counts up (km / mi).
- `--gpx-from-videos` reads each clip's QuickTime location tag and creation date into a GPX track.
- Output: `<name>_route.mp4`.

## fcp7xml.py --single: one render as a Premiere sequence

```
fcp7xml.py --single <render.mp4> [out.xml] [--path <path the editing machine sees>]
```
- A one-clip sequence at the render's own size, rate and audio (picture only when silent). Default `out.xml`: next
  to the MP4. Import in Premiere with File > Import. Paths are written as given: use `--path` when the editor
  opens the file from another machine or drive.

## QA calls (checked on the demo profile)

The hint column is what the tool prints; the call column is what to run. Add `--profile <name>` and
`--out out/mg/qa_<name>` (the default review folder lands in the engine root).

| Tool | Printed hint | qa call | Expect |
|---|---|---|---|
| statcard | none | `qa.py <name>_stats.mp4 --kind loop --cuts none` | PASS; `--kind motion` FAILs the hook gate (a lower third has no opening) |
| behind | none | `qa.py <name>_behind.mp4 --kind edit --cuts none` (+ `--intended hook` for an insert) | judge by the sheet |
| quote | `--kind motion --cuts none --holds end:2.4` | the hint | PASS |
| progressbar | `--cuts none` | `qa.py <name>_progress.mp4 --kind edit --cuts none --intended hook` | PASS, 1 declared intended (an overlay has no hook); render at the profile's rate (`--fps`) or spec FAILs |
| beforeafter | `--kind motion --cuts none` | the hint, + `--intended hook` when it is an insert | without it the "strong moment by 2 s" gate FAILs (the sweep is a calm move); that FAIL is real if it opens a post |
| sketch | `--kind motion --cuts none` | the hint + `--silences 0-<the real shot time it printed>` | PASS (without `--silences`: one WARN for the silent head) |
| routemap | `--kind motion --cuts none --holds end:1.0` | the hint | PASS |
| stage3d | `--cuts <times>` | `qa.py <Name>_<scene>.mp4 --kind motion --cuts <times>` | burst: PASS with one "planned cut not detected" WARN per line (swaps hide behind a light burst); check them by eye |

Read `review.md` and `sheet.jpg` in the qa folder. Report the RESULT line qa printed; never call a FAIL a pass.
