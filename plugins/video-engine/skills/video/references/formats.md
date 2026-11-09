# File formats the front-door tools read

All times are seconds. Paths in the JSON are data: write paths that exist on the machine that reads them (fxpack
resolves relative paths against the plan file's folder; fcp7xml writes paths exactly as given, so use the paths the
Premiere machine sees).

## Edit list

Read by `engine/fcp7xml.py` (to Premiere XML) and `engine/beatsnap.py` (snaps the cuts, writes back in place).

```json
{"name": "Spring Showcase Promo", "fps": 29.97, "w": 1920, "h": 1080,
 "files": {"a": {"path": "/path/to/clip_a.mp4", "dur": 60.0, "audio_ch": 2},
           "b": {"path": "/path/to/clip_b.mp4", "dur": 42.5, "audio_ch": 2}},
 "items": [{"file": "a", "in": 2.0,  "out": 5.3,  "label": "open"},
           {"file": "b", "in": 10.0, "out": 12.9, "label": "crowd", "scale": 108},
           {"file": "a", "in": 20.0, "out": 24.1, "label": "finale", "big": true, "payoff": true}],
 "music": [{"path": "/path/to/song.mp3", "dur": 180.0, "at": 0.0, "in": 0.0, "out": 11.0, "gain_db": -12}],
 "markers": [{"at": 3.3, "name": "beat"}],
 "overlays": [{"path": "/path/to/title.mov", "dur": 1.6, "at": 0.0, "in": 0, "out": 1.6, "label": "title"}]}
```

- `items` play back to back on V1 / A1-2. Optional per item: `scale` (percent, about the frame center), `big` (cut
  into it lands on a downbeat in beatsnap), `payoff` (cut into it lands on the drop), `replay` + `speed`.
- `music[0].in` is the music offset beatsnap reads. After snapping, update `music[0].out` to the new end of the edit.
- `overlays` are video-only clips on V2 (title cards, a caption layer) placed at `at`.
- `fps` defaults to 59.94 and `w`/`h` to 1920x1080 in fcp7xml when left out: set them.

## fxpack plan

Read by `engine/fxpack.py`.

```json
{"music": "song.mp3", "music_in": 0.0, "bpm": 120,
 "shots": [{"src": "clip1.mp4", "in": 3.0, "beats": 4},
           {"src": "clip2.mp4", "in": 1.5, "beats": 4, "label": "jump"},
           {"src": "clip3.mp4", "in": 0.5, "beats": 8, "hero": true}],
 "text": ["GAME", "DAY"],
 "fx": "auto"}
```

- `bpm` is optional (give it when known); the bar map is built from `music_in`.
- Each shot lasts whole `beats`; `hero: true` lands on the drop. `in` is the shot's start in its source.
- `text`: kinetic words, one a beat from the drop (optional).
- `fx`: `"auto"` or a list such as `[{"type": "flash", "at": 4.0}, {"type": "zoom", "at": 6.0}]`
  (types `flash`, `zoom`, `rgb`, `ramp`, `whip`, `pop`, `text`). Every effect still has to pass the effect gate (a music
  event within one frame and a measured picture reason).

## Moments list

Read by `engine/clip_plays.py`.

```json
{"plays": [{"n": 1, "start": 361.5, "end": 382.0},
           {"n": 2, "start": 1204.0, "end": 1219.5, "tags": ["applause"]}]}
```

Only `n`, `start`, `end` are needed. The file name is built from optional fields (`q`, `clock`, `offense`,
`before`, `after`, `tags`); missing ones become `Q` / `na` / `NA`, e.g. `001_Q_na_NA_na_to_na.mp4`.

## Encode preset

`engine/encode.py master --preset <name>` reads `delivery.<name>` from the profile; without `--preset` it uses
`delivery.default_preset`, else `web`. The demo and `_template` profiles already ship `delivery.web` (libx264,
12M / 14M / 24M). To add another, or to give an older profile one, edit `profiles/<name>/profile.json`:

```json
"delivery": { "...": "keep the existing keys",
              "web": { "vcodec": "libx264", "b_v": "12M", "maxrate": "14M", "bufsize": "24M" } }
```

Required: `vcodec`, `b_v`, `maxrate`, `bufsize`. Optional: `vcodec_fallback` (default `libx264`),
`fallback_args` (default `["-preset", "fast"]`), `profile` (an encoder profile such as `high`), `acodec`
(default `copy`), `faststart_max_gb` (default 10: larger outputs skip the faststart rewrite).

## Stats card

Read by `engine/statcard.py` (copy `docs/stats_card_example.json` per card and fill it in by hand).

```json
{"num": 12, "name": "Jane Doe", "big": "3 GOALS",
 "stats": [["SHOTS", "7"], ["ASSISTS", "2"], ["MINUTES", "88"]],
 "photo": "cutouts/12.png", "count": true, "logo": true}
```

Only `name` and `stats` (2-4 label/value pairs) are required. `photo` defaults to
`<profile paths.headshot_cutouts>/<num>.png` when that file exists; `count: false` shows numbers as written;
`logo: false` hides the profile logo.

## Words file

Written by captions.py, talkedit.py and hopwords.py (`--audio`); read back with `--words-file` / `--words`.
Abridged (the real file carries a few more header keys; leave them as they are):

```json
{"words": [{"w": "Practice", "s": 0.52, "e": 0.98, "p": 0.97},
           {"w": "makes", "s": 1.01, "e": 1.22, "p": 0.99, "key": true},
           {"w": "progress.", "s": 1.25, "e": 1.80, "p": 0.95, "break": true}],
 "dropped": []}
```

Fix spelling in `w`; `key` forces (true) or forbids (false) the highlighted word; `break` starts a new caption at
that word; delete a line to drop a word. Read `dropped` (words whisper likely invented) before the final render.
