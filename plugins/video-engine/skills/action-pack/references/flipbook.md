# flipbook.py reference

Source of truth: `engine/flipbook.py` in the engine folder (its docstring lists every flag):
`python3 engine/flipbook.py --help` prints it.

## Command

```
python3 engine/flipbook.py <plan.json> <frames dir> <out.mp4> [--profile NAME] [--wide] [--fps-photo 12]
    [--label "TEXT"] [--slam DIR] [--fontdir DIR] [--root DIR] [--keep-temp]
```

| Flag | Effect |
|---|---|
| `--profile NAME` | brand profile (else `$VIDEO_PROFILE`, else `local.json`) |
| `--wide` | 1920x1080; default is 1080x1920 |
| `--fps-photo N` | shots a second inside a burst (default 12) |
| `--label "TEXT"` | title-card line; default `"<team.home_abbr> <team.home_name> · <tags>"` (empty-looking with the demo profile, so always pass it) |
| `--slam DIR` | end-card frames: `DIR/f*.png`, 1920x1080 RGBA, one per output frame, in name order |
| `--fontdir DIR` | use the profile's font file names from another folder |
| `--root DIR` | re-root profile asset paths that sit under `paths.root` onto another copy of that folder |
| `--keep-temp` | keep `<out>_frames/` (JPEG frames) and `<out>.wav` after a good render |

Without `--slam`, the end card comes from the profile's `brand.logo_3d_swing_alpha_mov` (extracted once and cached
in `<engine>/_cache/flipbook/<profile>/slam/`). A profile without that key needs `--slam`.

Output: H.264 (CRF 17, +faststart), 29.97 fps, AAC stereo 256 kb/s. Prints `done <out> <seconds> s <frames> frames`.
It asks for `-pix_fmt yuv420p`, but the frames are JPEGs, so the file comes out full-range and probes as `yuvj420p`
(qa.py WARNs on it). The bed step in SKILL.md re-encodes it to standard `yuv420p` with
`scale=in_range=pc:out_range=tv`. The encode uses `-shortest`, so the file can hold one frame fewer than the
`done` line prints (the last end-card frame, already faded to black).

## plan.json

A list in play order. Each entry:

| Key | Required | Meaning |
|---|---|---|
| `frames` | yes | file names in the frames dir **without** `.jpg` (files must be `<name>.jpg`) |
| `wk` | yes | short tag shown (upper-cased) on the bold line under the burst counter, e.g. `GAME 1`, `HEAT 3`, `Q2` |
| `opp` | no | text after the tag on the same line, printed as written; if absent, the profile's `schedule.opponents[wk]` is used, else nothing |
| `name` | no | your own label; not drawn |

`ap_helpers.py plan` writes `wk` from a pick's `tag` and copies `opp`.

## Profile keys flipbook reads

| Key | Needed | Use |
|---|---|---|
| `brand.colors.primary` / `accent` / `text` | yes | title and end-card ground, counter square and ticks, text |
| `brand.fonts.head` / `body` | yes | headline font, counter and label font |
| `brand.logo_png` | yes | logo top-left on every burst frame and on the title card |
| `team.foot`, `brand.watch_line` | yes (may be `""`) | end-card lines (white, then accent) |
| `paths.root` | yes | used by `--root` |
| `team.home_abbr`, `team.home_name` | only for the default `--label` | |
| `schedule.opponents` | no | `{"<tag>": "VS ..."}` fallback for `opp` |
| `brand.logo_3d_swing_alpha_mov` | only without `--slam` | end-card source |

Check a profile with `python3 engine/vprofile.py show <name> --check`.

## Layout

| Part | Vertical 1080x1920 | Wide 1920x1080 |
|---|---|---|
| Photo | fills the frame (crop to cover, centered across, 45% down) with a slow 1%-a-shot push | a 2:3 portrait card (about 670x1000) with a light border, over a blurred copy tinted 65% primary |
| Logo | 300 px wide, top-left | 280 px wide, top-left |
| Counter | `BURST NN/NN` + tag line + one tick per shot, 330 px above the bottom | same, 110 px above the bottom |
| Frame | white corner brackets | same |
| Title card | `ACTION` (text color) / `PACK` (accent) on primary, label below, logo 560 px wide above (top at y 480) | same, logo 560 px wide at y 60 |

The title-card logo has no height limit: at 560 px wide, a logo narrower than about 1.75:1 (width:height) reaches
the top of `ACTION` in both layouts. `ap_helpers.py packprofile` makes a flipbook-only profile copy with the logo
padded to 2:1.
| End card | slam frames scaled to 1180x664 and centered, lines below | slam frames at full size, lines below |

## Timing (29.97 fps)

| Part | Length |
|---|---|
| Title card | 30 frames (1.0 s), white flash on its first 2 frames, boom at 0; `ACTION` / `PACK` zoom from 140% to 100% over the first 0.25 s, then the card holds still |
| Each burst | `round(shots x 29.97 / fps-photo)` frames (10 shots at 12 = 25 frames), white flash on its first 2 frames, a click on every shot, a boom at its start |
| Hold | 9 frames (0.3 s) on the last shot with an eased 5% punch-in |
| End card | one frame per slam PNG, boom at its start, lines fade in from frame 15, fade to black over the last 12 frames |

`ap_helpers.py cuts` mirrors this timeline to list every planned cut (the title flash at 0.033 s, title end, every
shot change, end-card start) and the title card's still stretch (`"holds": "0.25-1.001"`).
`ap_helpers.py get <cuts.json> cuts|holds` prints either one as a command-line string.

## Audio

Synthesized in numpy: 45 ms noise-burst shutter clicks and 0.6 s sine booms (sweeping from 88 down to 48 Hz), soft-clipped, no
music. Measured against `engine/audio_check.py` alone it FAILS (clicks decay into digital silence faster than the
fade rule allows, and the first boom after the title starts from silence). Under a music bed at about the same level
as the clicks it passes; see SKILL.md step 6.

## QA notes for `engine/qa.py`

| Gate | What to expect | What to do |
|---|---|---|
| spec | 1080x1920 or 1920x1080 at 29.97: both are in a profile's `delivery` sizes | a size FAIL means the wrong profile or a re-encode changed it |
| spec: pixel format | `yuvj420p` straight out of flipbook | a WARN; the bed step's re-encode makes it `yuv420p` |
| flashes | a white flash on the title card and at every burst start | planned when `--shotlist pack.cuts.json` is given |
| cuts | every shot change is a planned cut; the title flash is a cut at 0.033 s | an unplanned cut (FAIL) means the cut list was made with a different `--fps-photo` or plan. Expect a WARN `planned not found` and one "planned cut not detected" line per shot change too small for scdet to see (shots in a burst look alike); burst starts are found |
| motion | photos held 2-3 frames; the title card still from 0.25 s to 1.0 s | `--allow-stutter` and `--holds "$(python3 "$H" get pack.cuts.json holds)"`; without `--holds` the title card FAILs as "nothing moves for 0.73 s" at f8-f29. Dead air anywhere else is real |
| loudness / true peak | flipbook's own track is not leveled | the bed step's `loudnorm` fixes it |
| end tail | the end card fades to black | a static-tail FAIL means slam frames that stop moving too early: use a longer or livelier slam |
