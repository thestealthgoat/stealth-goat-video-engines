# stage3d: the 3D card engine

```
stage3d.py <scene> <out_dir> <Name> [options] [--profile P]
  scenes: data orbit stack burst badge toggle props reveal hop fly extrude
  common: --alpha  --bg gradient|mesh  --fps 30  --size 1920x1080  --dur S  --frames t1,t2  --spec file.json
```

`engine/stage3d.py` drives `engine/stage3d.html` (three.js) frame by frame in headless Chromium. Needs Playwright
Chromium and `logo/node_modules/three` (both installed by `./setup.sh`, which targets macOS with Homebrew;
`./setup.sh --check` reports them).
It runs fully local; only `--url` loads web pages (to screenshot them).

Every scene uses the same light: a warm key that casts real shadows onto a shadow-catcher floor, a cool rim, a
soft fill, and a contact shadow under each object. The camera never stops (slow dolly plus hand-held drift).
Colours and fonts come from the profile (`head`, `body`, `body_semibold`; `mono` if present); headings are set in
capitals when the profile has `"explain": {"head_caps": true}`.

## Outputs

- `<Name>_<scene>.mp4` on the profile ground (a gradient, or `--bg mesh` for a drifting mesh gradient).
- `--alpha`: also `<Name>_<scene>_Alpha.mov` (ProRes 4444, transparent ground, shadows kept in the alpha).
- `orbit`: the composite `.mp4` plus `<Name>_orbit_front_Alpha.mov` and `<Name>_orbit_back_Alpha.mov`.
- The finish line prints the hit time and cuts as `(qa: --cuts ...)`; pass them to `engine/qa.py --kind motion`
  (with `--out out/mg/qa_<scene>`). Scenes whose cuts are soft swaps (`burst`: titles change behind a light burst)
  get one "planned cut not detected as a hard cut" WARN per cut and still PASS; check those frames on `sheet.jpg`.
- Default 30 fps: pass `--fps 29.97` (or the profile's rate) to match delivery, or give qa `--fps 30`.

## Scenes

| Scene | Inputs | What happens |
|---|---|---|
| `data` | `--data file.json` or a `label,value` CSV | bars grow and count up (top value in the accent), score cards flip in and count up, a map grid draws on with value columns (labels on the top 3) and a point cloud; the camera travels section to section (4.6 s each) |
| `orbit` | `--matte out/m/<name>_matte.json` (from `engine/matte.py`), `--cards "A\|B\|C"` | frosted glass cards orbit the presenter's head and pass behind and in front of them; length = the matte window; size = the plate's |
| `stack` | `--shots a.png,b.png` or `--url https://... [--url ...]` (`--shot-size 390x844` for phone) | screenshot cards drop in, fan out in depth, the first lifts to camera |
| `burst` | `--lines "A\|B\|C"` | mesh gradient from the profile colours; each title swaps behind a light burst (1.8 s a line); cuts printed |
| `badge` | `--text1 "A" --text2 "B"` | two badges fly in and clash at about 1.0 s (the piece's one slam: recoil, sparks, burst, shake) |
| `toggle` | `--labels "A\|B\|C"` | a settings panel; switches flip on, off, on with UI springs, staggered |
| `props` | `--icons check,star,heart,bolt,play,plus,pin,chat` | extruded, bevelled glossy icons pop in and float; use `--alpha` over footage |
| `reveal` | `--shots` (first = phone screen, then panels) or `--panels "A\|B"`, `--toast "..."`, `--tagline "..."` | brand glow, phone rises, panels slide out, a toast drops, tagline word by word |
| `hop` | `--text "the words"`, timing from `--words words.json` or `--chart` or `--wpm 110`, `--character art.png` | a mascot (placeholder bean without art) hops platform to platform; each word lights on its landing |
| `fly` | `--shots app.png`, `--focus` JSON `[{"x":0.1,"y":0.2,"w":0.3,"h":0.2,"label":"Search"}]` (fractions, file or inline) | the camera flies over a tilted screenshot to each region (glow outline + callout), then pulls back |
| `extrude` | `--text "WORD"` (glyphs of the profile head font) or `--svg mark.svg` | 3D extruded type; the camera flies past the letters and lands square on the lockup (the hit) |

Use screenshots at least 1200 px wide for `stack`, `reveal` and `fly`. Use made-up data in demo screenshots.

## `--data` format

CSV: `label,value` rows (an optional header row; commas and `%` in values are stripped). One bars section, titled
by the file name.

JSON, one or more sections:
```json
{"sections": [
  {"kind": "bars",   "title": "Visits per day", "suffix": "", "items": [{"label": "Mon", "value": 12}, {"label": "Tue", "value": 18}]},
  {"kind": "cards",  "title": "This season", "items": [{"label": "Members", "value": 1250}, {"label": "Growth", "value": 12.5, "suffix": "%", "note": "vs last year"}]},
  {"kind": "points", "title": "Where they came from", "points": [{"lat": 46.0, "lon": 7.5, "value": 40, "label": "North"}, {"lat": 45.2, "lon": 8.1, "value": 15}]}
]}
```
- `bars`: any number of items; the top value is drawn in the accent. Section keys `prefix`, `suffix`, `decimals`
  format the numbers.
- `cards`: up to 4 items; per-item `prefix`, `suffix`, `decimals` override the section's.
- `points`: `lat`/`lon` (or `x`/`y`) with an optional `value` (column height) and `label` (shown for the top 3).
- Only real numbers from the user's data; never estimate a value to fill a chart.

## `--spec` overrides (a JSON file merged into the scene settings)

| Key | Scenes | Meaning (default) |
|---|---|---|
| `dur` | most | scene length in seconds (same as `--dur`) |
| `per` | `data` (4.6), `burst` (1.8), `fly` (2.2) | seconds per section / line / focus |
| `light` | all | `{"warm": "#FFD6A8", "cool": "#9EC2FF", "key": 2.6, "rim": 2.2}` |
| `flips` | `toggle` | switch flip times (`[0.8, 2.4, 3.0]`, staggered 0.22 s per switch) |
| `centre`, `rx`, `ry`, `period`, `tilt` | `orbit` | orbit centre (found from the cut-out), radii, seconds per turn (9), tilt |
| `minDist` | `fly` | how close the camera may get (9; raise it if a small screenshot looks soft) |

## Example commands (demo profile)

```bash
cd "$VIDEO_ENGINE"
python3 engine/stage3d.py data    out/mg Demo --data out/mg/visits.csv --profile demo --frames 2.0
python3 engine/stage3d.py toggle  out/mg Demo --labels "Captions|Music|Auto-cut" --profile demo --fps 29.97
python3 engine/stage3d.py props   out/mg Demo --icons check,star,heart --alpha --profile demo --fps 29.97
python3 engine/stage3d.py extrude out/mg Demo --text "ACME" --profile demo --frames 1.0,3.0
python3 engine/stage3d.py hop     out/mg Demo --text "one small hop at a time" --wpm 100 --profile demo --frames 2.0
python3 engine/stage3d.py fly     out/mg Demo --shots app.png --focus '[{"x":0.05,"y":0.1,"w":0.4,"h":0.2,"label":"Search"}]' --profile demo
python3 engine/stage3d.py orbit   out/mg Demo --matte out/m/talk_matte.json --cards "Plan|Build|Ship" --profile demo
```
