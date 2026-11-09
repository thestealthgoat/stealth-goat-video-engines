# The cull folder `candidates` reads

`cutouts.py candidates <cull dir> <label>` expects a folder made by an earlier culling step. The engine does not
make this folder; it is the contract a culling tool has to meet. If the user has no such folder, use the
photo-folder route in SKILL.md instead.

```
<cull dir>/
  rows.json            {"rows": [ {...}, ... ]}
  prev960/<n>.jpg      a preview of each photo, about 960 px, as stored (not rotated)
  masks/<n>.png        a grayscale person mask of the preview AFTER rotating it upright (white = person, > 128)
```

One row per photo. `n`, `keep`, `o`, `burst`, `folder` and `cat` are all required: `candidates` reads each one
directly (`n` and `keep` on every row, the others on kept rows with a mask) and stops with a `KeyError` when one
is missing. Only `qa` is optional.

| Key | Type | Used for |
|---|---|---|
| `n` | text | the photo name (file name without extension); also the key everywhere later |
| `keep` | bool | only kept rows with a mask are checked |
| `o` | int | EXIF orientation: 6 and 8 rotate the preview (and, in `fullcrop.py`, the full JPEG), 3 turns it 180 in `candidates` |
| `burst` | any | rows with the same value are one burst; only its best frame goes forward |
| `folder`, `cat` | text | required; copied to `cut_requests.json`; `library` files a frame under `Portraits/` when `folder` is `02 Pregame` and `cat` is `portrait`, `warmup` or `sideline` |
| `qa.subj` | number | optional; subject focus score. It only ranks frames within a burst (frame score = `qa.subj` x the player's height share; missing = 0); there is no focus threshold |

`candidates` writes `<cull dir>/cut_requests.json`, keyed by `n`:

```json
{"IMG_0001": {"n": "IMG_0001", "o": 1, "burst": 4, "score": 0.41, "box": [0.31, 0.12, 0.58, 0.97],
              "folder": "03 Game", "cat": "action", "wk": "Wk03"}}
```

`box` is the player's bounding box as fractions of the upright frame. `fullcrop.py` crops the full-size JPEG to it
with 8% extra width and 6% extra height on each side.

`fullcrop.py <games dir> <cut_requests.json> <crops dir> [--seconds N]` looks for the raws at
`<games dir>/<any game folder>/Photos/**/<n>.CR3` and reads the first embedded JPEG wider than 4,000 px (Canon CR3
raws carry one). A requested name with no raw there stops the run with a `KeyError`; remove that entry from
`cut_requests.json` or put the raw in place. For other cameras, export full-size JPEGs named `<n>.jpg`, crop them
yourself, or skip `fullcrop.py` and use the photo-folder route.
