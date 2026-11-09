# team.uniform: the jersey colours `candidates` checks

`candidates` keeps a frame only if the main person wears the team's colours. The check counts the share of his
mask pixels (on the 960 px preview) that fall inside each colour band, in OpenCV HSV: H 0-179 (degrees / 2),
S and V 0-255.

```json
"team": {
  "home_abbr": "ACME",
  "uniform": {
    "team":   {"h": [70, 95], "s_gt": 60, "v_gt": 15, "v_lt": 160, "min": 0.12},
    "reject": [
      {"name": "red (low)",  "h": [0, 8],     "s_gt": 90, "v_gt": 80, "max": 0.05},
      {"name": "red (high)", "h": [172, 179], "s_gt": 90, "v_gt": 80, "max": 0.05},
      {"name": "white",      "h": [0, 179],   "s_gt": -1, "v_gt": 215, "max": 0.20}
    ]
  }
}
```

This example is a dark-green team (the `demo` primary `#0B3D2E` is H 81, S 209, V 61) playing a red-and-white
opponent.

| Key | Meaning |
|---|---|
| `h` | hue range, both ends included; it cannot wrap past 179, so split red into two bands |
| `s_gt`, `v_gt` | saturation / value strictly above this (default -1: no limit) |
| `v_lt` | value strictly below this (optional; keeps dark jerseys from matching bright grass of a similar hue) |
| `team.min` | the share inside the team band must be at least this |
| `reject[].max` | the share inside each reject band must be at most this; `name` is only a label |

## Measuring your colours

Crop a patch of jersey (and of the opponent's jersey) from a game photo, then print its HSV spread:

```bash
python3 -c "import cv2,numpy as np,sys; h=cv2.cvtColor(cv2.imread(sys.argv[1]),cv2.COLOR_BGR2HSV).reshape(-1,3); print('H S V at p10/p50/p90:', np.percentile(h,[10,50,90],axis=0).astype(int).tolist())" jersey_patch.jpg
```

Set the band a little wider than p10-p90. Then run `candidates` on one game and `Read` the `cutcand_N.jpg` sheets:

- Teammates missing: lower `team.min` or widen `h`.
- Opponents or fans getting through: add a `reject` band for their colour, or raise `team.min`.
- A white or grey team kit is hard to tell from a white opponent; rely on `reject` bands for the opponent and on
  your own reading of the sheets, and leave non-team players out of `numbers.json`.

Different home and away kits need two profiles, or edit `team.uniform` before each game's `candidates` run.
