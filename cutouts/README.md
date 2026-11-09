# Player cutouts

Turn game photos into checked, transparent cutouts of each player, graded automatically and filed into a per-player
library (`<library>/#<number> <Name>/{Cutouts,Portraits,Action}`) ready for lower thirds, stat cards and thumbnails.
The matte comes from BiRefNet, run locally through rembg, so no photo leaves the machine. Part of the
[Stealth Goat video engines](../README.md); see [docs/TOOLS.md](../docs/TOOLS.md) for every tool in the repo.

## Quick start

Run from the repo root after `./setup.sh`. Bring your own photos: JPEGs named `<name>.jpg`, each loosely cropped to one
player (more under [Preparing photos](#preparing-photos)). The first `cut` downloads the two BiRefNet models, close to
1 GB each.

```bash
W=~/Movies/video-work/cutouts-try && mkdir -p "$W/crops"
cp ~/Pictures/game/IMG_0001.jpg ~/Pictures/game/IMG_0002.jpg "$W/crops/"
printf '{"IMG_0001": "12", "IMG_0002": null}\n' > "$W/numbers.json"       # jersey numbers you can read; null = unreadable
printf 'number,name\n12,Jane Doe\n7,Sam Lee\n' > "$W/roster.csv"
echo '{}' > "$W/cut_requests.json"                                        # no cull folder on this route

python3 cutouts/cutouts.py --profile demo cut "$W/crops" "$W/numbers.json" "$W/out"
python3 cutouts/cutouts.py --profile demo library "$W/out" "$W/roster.csv" "$W/Library" --games-map "$W/cut_requests.json"
python3 cutouts/copy_photos.py "$W/crops" "$W/lib_plan.json" "$W/Library"
```

`cut` prints a grade per photo and writes `out/review_0.jpg`; look at it before filing. The library then holds
`#12 Jane Doe/Cutouts/…png`, an `_index.csv`, and `_Overview.jpg`. For a single cutout with no grading or filing, use
`python3 engine/cutout.py in.jpg out.png`.

## The tools

| Tool | What it does |
|---|---|
| `cutouts.py candidates` | picks cutout-able frames from a culled game (optional route, below) |
| `fullcrop.py` | crops each requested player from the full-size JPEG inside a Canon CR3 raw (optional route) |
| `cutouts.py cut` | cuts, grades (A, B or X) and draws review sheets |
| `cutouts.py library` | files the keepers by roster number, extending an existing library |
| `copy_photos.py` | copies the full-resolution crops into each player's `Portraits/` or `Action/` |

`cutouts.py` takes `--profile <name>` anywhere on the line (default: `$VIDEO_PROFILE`, then `local.json`). From the
profile it reads:

- `brand.colors.primary`: the review-sheet background;
- `brand.fonts.body`: the label font on the sheets;
- `team.home_abbr`: the prefix of library file names (empty in `demo`);
- `team.uniform`: the team's jersey colors, used only by `candidates` ([below](#teamuniform)). There is no
  default, so `candidates --profile demo` stops with a message; `cut` and `library` work with `demo`.

Folders (cull folder, games folder, crops, output, library) are always given on the command line. `fullcrop.py` and
`copy_photos.py` take no profile.

## Two routes

**Photo folder (any camera or phone).** The usual route, shown in the quick start: prepare `crops/` by hand, write
`numbers.json`, then `cut`, `library` and `copy_photos.py`.

**Culled game.** If an earlier culling step produced a cull folder (`rows.json`, `masks/`, `prev960/`, described in
the [player-cutouts skill](../plugins/video-engine/skills/player-cutouts/references/cull-folder.md)) and the raws are
Canon CR3 files, the first two steps can be automatic:

| Step | Command |
|---|---|
| 1. Candidates | `python3 cutouts/cutouts.py --profile myteam candidates <cull dir> Wk03` writes `cut_requests.json` and numbered sheets `cutcand_N.jpg` (`Wk03` is any short game label; it ends up in file names) |
| 2. Read the numbers | look at the sheets and write `numbers.json`: `{"IMG_0001": "12", "IMG_0002": null, "IMG_0003": "MASCOT"}`; leave out anything not worth cutting (a coach, the crowd, a bad crop) |
| 3. Full-resolution crops | `python3 cutouts/fullcrop.py <games dir> <cull dir>/cut_requests.json <work>/crops --seconds 600`; it finds `<games dir>/<game>/Photos/**/<name>.CR3`, stops after `--seconds` printing `TIMESLICE`, and is resumable: run it again until it prints `DONE` |
| 4. Cut and grade | `python3 cutouts/cutouts.py --profile myteam cut <work>/crops numbers.json <work>/out` |
| 5. File | `python3 cutouts/cutouts.py --profile myteam library <work>/out roster.csv <library> --games-map <cull dir>/rows.json`, then `python3 cutouts/copy_photos.py <work>/crops <work>/lib_plan.json <library>` |

`--games-map` takes one path per game; `library` reads `cut_requests.json` from the folder of each path.

## Preparing photos

- Each photo must be a JPEG named `<crops>/<name>.jpg` with a lower-case extension. `cut` silently skips a name in
  `numbers.json` that has no matching file. Convert HEIC or PNG first (on a Mac:
  `sips -s format jpeg IMG_0003.HEIC --out crops/IMG_0003.jpg`).
- One main player per photo, loosely cropped: a margin all round, nothing cut off at the top or sides. For several
  players in one photo, make one crop per player, each with its own name.
- `cut` scales each photo to fit 3,000 px, and a cutout under 1,500 px tall is rejected, so crop before cutting.
- Phone photos stored sideways are turned upright from their EXIF orientation. An export that dropped the tag but
  left the pixels sideways must be rotated first.

## How a cutout is checked

**Before cutting** (`candidates` only), a frame goes forward when:

- one person dominates: a second person larger than 15% of him rejects the frame;
- his head and sides are not cut off by the frame;
- he is at least 35% of the frame height;
- he wears the team uniform: enough of the team color and none of the opponents' colors (`team.uniform`);
- it is the best frame of its burst (ranked by the cull's focus score times his height share).

**The cut.** The alpha comes from BiRefNet general (complete people: helmets, dark jerseys, hands, feet), checked
against BiRefNet portrait. The largest person is kept and stray blobs are dropped.

**The grade.**

- **A**: full body.
- **B**: cut at the bottom of the frame (three-quarter length).
- **X**: rejected. The two masks disagree (IoU under 0.8), more than 25% of the edge is soft (blur or motion), there
  is more than one piece, he is cut at the top or sides, or the cutout is under 1,500 px tall.

A person always checks the review sheets too: the automatic grade catches most problems, not all of them. To change a
grade, add `name=GRADE` pairs to the same `cut` command and run it again (it only re-grades and redraws the sheets):

```bash
python3 cutouts/cutouts.py --profile demo cut "$W/crops" "$W/numbers.json" "$W/out" IMG_0002=X IMG_0005=B
```

**Numbers.** A person reads them. OCR (RapidOCR, optional) is only a hint stored in `grades.json`: it reads clear
numbers on a player's back and misses most others. An unreadable or off-roster number is filed under
`_Unidentified/`, `MASCOT` under `_Mascot/`. Names come only from the roster CSV (`number` and `name` columns).

**Outputs.** `cut` writes `out/png/<name>.png`, `out/grades.json` and `out/review_N.jpg` (40 per sheet) and is
resumable. `library` builds or extends `<library>/#<n> <Name>/{Cutouts,Portraits,Action}`, `_Unidentified/`,
`_Mascot/`, `_index.csv`, `_Overview.jpg`, and writes `lib_plan.json` next to the library folder for `copy_photos.py`.

## Models

The BiRefNet models are downloaded by rembg on first use into the folder `engine/models.py` picks: `$U2NET_HOME` if
set, else `rembg_models` in this machine's `local.json` (for example a shared drive), else `resources/models/rembg` in
the engine folder when it exists, else rembg's own default folder. BiRefNet is MIT-licensed.

## team.uniform

`candidates` keeps a frame only if the main person wears the team's colors. Bands are in OpenCV HSV (H 0-179, S and
V 0-255). This example is a dark-green team playing a red-and-white opponent:

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

`h` is inclusive and cannot wrap past 179 (split red into two bands); `s_gt`, `v_gt` and `v_lt` are strict limits;
the share of the player's pixels in the team band must be at least `min`, and in each reject band at most `max`. How
to measure your own colors is in the skill's
[uniform-colors reference](../plugins/video-engine/skills/player-cutouts/references/uniform-colors.md).

## See also

- [Root README](../README.md): install, profiles and the tour of the engine.
- [docs/TOOLS.md](../docs/TOOLS.md): every tool in the repo.
- [player-cutouts skill](../plugins/video-engine/skills/player-cutouts/SKILL.md): the full workflow as Claude runs it.
