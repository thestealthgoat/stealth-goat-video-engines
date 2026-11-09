---
name: player-cutouts
description: Builds and maintains a per-player library of transparent cutout PNGs from a sports team's game photos with the free local cutouts/cutouts.py (BiRefNet via rembg; nothing is uploaded). Picks cutout-able frames, cuts and grades each player (A full body, B three-quarter, X reject), draws review sheets for checking, and files the keepers by roster number into "#12 Jane Doe/{Cutouts,Portraits,Action}" with an index and an overview sheet. Use when the user says "cut out our players from the game photos", "make player cutouts", "build a player library", "transparent PNGs of the team", "headshot cutouts for the stats cards", "do we have a cutout of #12", "file these cutouts by player", "who is unidentified in the library", or "add this week's game to the player library".
---

# Player cutouts

Turn game photos into a checked library of transparent player cutouts, one folder per roster player. The tools are
in the engine folder's `cutouts/`: `cutouts.py` (`candidates`, `cut`, `library`), `fullcrop.py` and
`copy_photos.py`. Everything runs on the user's own machine with free, open-source models.

Library layout (see [references/library.md](references/library.md) for every file):

```
<library>/
  #12 Jane Doe/Cutouts/   transparent PNGs     Portraits/  tight pregame shots     Action/  full-res JPG crops
  _Unidentified/  _Mascot/  _index.csv  _Overview.jpg
```

There is a folder for every player on the roster, so an empty folder means "no usable shot yet".

## 0. Find the engine and the profile

1. Use `$VIDEO_ENGINE` (a clone of https://github.com/thestealthgoat/stealth-goat-video-engines). Run every command
   as `cd "$VIDEO_ENGINE" && python3 cutouts/<tool>.py ...`.
2. If `$VIDEO_ENGINE` is unset or the folder has no `cutouts/cutouts.py`, ask the user where the engine folder is,
   or run the getting-started skill. Do not guess a path.
3. Pick the profile: `--profile <name>` on every `cutouts.py` command (it may go anywhere on the line), else
   `$VIDEO_PROFILE`, else `default_profile` in the engine folder's `local.json`. `fullcrop.py` and `copy_photos.py`
   take no profile. From the profile `cutouts.py` reads:
   - `team.uniform`: the team's jersey colour bands. **Only `candidates` needs it, and there is no default.** The
     `demo` profile has none, so `candidates --profile demo` stops with a message. `cut` and `library` work with
     `demo`.
   - `brand.colors.primary`: the review-sheet background.
   - `brand.fonts.body`: the label font on the sheets.
   - `team.home_abbr`: the prefix of library file names (`ACME #12 - Wk03 - IMG_0001.png`; empty in `demo`).
4. For a real team, have the user make a profile from `profiles/_template`:
   `python3 engine/vprofile.py new myteam --display "ACME Athletics" --primary "#112233" --accent "#E04050"`, then
   set `team.home_abbr` and add `team.uniform` (measure it as in
   [references/uniform-colours.md](references/uniform-colours.md)). Check it with
   `python3 engine/vprofile.py show myteam --check`. `team.uniform` is described in
   [references/uniform-colours.md](references/uniform-colours.md) and the engine's `cutouts/README.md`; `docs/LAYOUT.md`
   covers the other profile keys.
5. Check the dependencies once: `python3 -c "import rembg, onnxruntime, cv2"`. If that fails, run `./setup.sh --check`
   in the engine folder (or the getting-started skill; `setup.sh` targets macOS with Homebrew). `rapidocr_onnxruntime`
   is optional (a jersey-digit hint).
6. Keep work files (crops, `numbers.json`, `out/`, the library) in a work folder outside the engine folder, for
   example under the profile's `paths.root`.

## 1. Pick the route

- **A photo folder (any camera, any phone).** The user has photos and wants cutouts: go to section 3. Copy the
  photos into `<work>/crops/` (never work on the originals), converted to JPEG and loosely cropped to one player
  each as section 3 says. This is the usual route.
- **A culled game with masks.** The user already has a cull folder in the format `candidates` reads (`rows.json`,
  `masks/`, `prev960/`; see [references/cull-folder.md](references/cull-folder.md)) and Canon CR3 raws: start at
  section 2. Do not invent that folder; if the user does not have one, use the photo-folder route.
- **One photo, no library.** `python3 engine/cutout.py in.jpg out.png` cuts one still with the same model, with no
  grading or filing. For a person in a video, use the matte skill.
- **A lookup** ("do we have a cutout of #12?"): list `<library>/#12 */Cutouts/` and read `_index.csv` (grade, source
  photo, game). To pick one for a graphic, `Read` `_Overview.jpg` or the PNG itself.

## 2. Find candidates (cull route only)

```bash
cd "$VIDEO_ENGINE" && python3 cutouts/cutouts.py --profile myteam candidates <cull dir> Wk03
```

`Wk03` is any short game label; it ends up in the library file names. A frame goes forward when:

- one person dominates (a second person larger than 15% of him rejects the frame);
- nothing is cut off at the top or the sides;
- he is at least 35% of the frame height;
- he wears the team uniform: enough of `team.uniform.team`, and no more than `max` of each `team.uniform.reject`
  colour (the opponents);
- within each burst the frames that pass are ranked by the cull's focus score `qa.subj` times his height share (a
  missing score counts as 0). There is no focus threshold: a soft burst still sends its best frame forward, so check
  sharpness on the sheets.

Only the best frame of each burst goes forward. It writes `<cull dir>/cut_requests.json` and contact sheets
`<cull dir>/cutcand_0.jpg`, `cutcand_1.jpg`, ... (96 per sheet). Then make the full-res crops from the raws:

```bash
cd "$VIDEO_ENGINE" && python3 cutouts/fullcrop.py <games dir> <cull dir>/cut_requests.json <work>/crops --seconds 600
```

It finds `<games dir>/<game folder>/Photos/**/<name>.CR3`, takes the full-size JPEG embedded in each raw, rotates it
upright and crops the player with a margin. It stops after `--seconds` (default 150) printing `TIMESLICE`; run it
again until it prints `DONE` (finished crops are skipped). A `miss` line means no large embedded JPEG was found; a
`KeyError` means a requested raw is not under `<games dir>` (details in
[references/cull-folder.md](references/cull-folder.md)).

## 3. Read the jersey numbers and write numbers.json

`Read` every sheet yourself: `cutcand_N.jpg` on the cull route, or the photos themselves on the photo-folder route.
Write `<work>/numbers.json`, keyed by photo name (the file name without `.jpg`):

```json
{"IMG_0001": "12", "IMG_0002": null, "IMG_0003": "MASCOT"}
```

- On a `cutcand` sheet the label is `<index> <last 5 characters of the name>`; the index is the position of that
  photo in `cut_requests.json` (sheet N starts at index 96 x N). Map each label back to the full name from there.
- Write a number only when you can actually read it. A partly hidden digit is `null` (it goes to `_Unidentified`).
  Never guess from build, position or hair.
- Every number must be on the roster. A number that is not becomes `_Unidentified` at filing.
- Leave out coaches, officials, fans, opponents, groups and blurry or badly cropped frames. A photo not in
  `numbers.json` is not cut.
- On the photo-folder route prepare the crops folder before cutting:
  - Each photo must be a JPEG named `<crops>/<name>.jpg`. `cut` silently skips any name in `numbers.json` with no
    such file (no message), so check that every key has its `.jpg`. Convert HEIC (the iPhone default), PNG or other
    formats first; on a Mac: `sips -s format jpeg IMG_0003.HEIC --out <work>/crops/IMG_0003.jpg`. Use a lower-case
    `.jpg` extension (an upper-case `.JPG` only works on a case-insensitive disk, the macOS default).
  - One main player per photo. Crop each player loosely (a margin all round, nothing cut off at the top or sides)
    before cutting; for several players in one photo, make one crop per player with its own name.
  - Size: `cut` scales every photo to fit 3,000 px first, and the cutout must then be at least 1,500 px tall, or it
    is graded X. In a full, uncropped 4000x3000 landscape photo (scaled to 3000x2250) the player would have to fill
    about two-thirds of the frame height, so crop first. A player under 1,500 px tall in the original photo grades
    X whatever the crop; tell the user that photo is too small for a library cutout (`engine/cutout.py` still cuts
    it for a one-off).
  - Rotation: `cut` applies the EXIF orientation, so sideways-stored phone photos come out upright. An export that
    drops the orientation tag but leaves the pixels sideways does not; rotate those upright first.

## 4. Cut and grade

```bash
cd "$VIDEO_ENGINE" && python3 cutouts/cutouts.py --profile myteam cut <work>/crops <work>/numbers.json <work>/out
```

- The alpha is BiRefNet general (complete people: helmets, dark jerseys, hands, feet), gated by BiRefNet portrait,
  and only the largest person (plus any large piece of him) is kept. Photos larger than 3,000 px are scaled to fit
  3,000 px first.
- The first run downloads both models (close to 1 GB each) through rembg into the models folder that
  `engine/models.py` picks (`$U2NET_HOME`, else `rembg_models` in `local.json`, else `resources/models/rembg`, else
  rembg's default folder). Tell the user before that download. Do not run `cut` alongside a video render: one heavy job at a time.
- It writes `out/png/<name>.png`, `out/grades.json` and `out/review_0.jpg`, `review_1.jpg`, ... (40 per sheet, on the
  profile's primary colour, labelled `<index> <grade> #<number> <last 5 characters>`). It is resumable: photos
  already in `grades.json` are not cut again.
- The grade (details in [references/library.md](references/library.md)):
  - **A** full body; **B** cut at the bottom of the frame (three-quarter);
  - **X** reject: the two masks disagree (IoU under 0.8), more than 25% soft edge (blur, motion), more than one
    piece, cut at the top or sides, or under 1,500 px tall.

**Then `Read` every `review_N.jpg`.** The automatic grade catches most problems, not all. Look for:

- a second player's arm, leg or helmet left in;
- missing feet, hands or the top of the helmet;
- a halo or chunks of background (turf, crowd, a pylon);
- the wrong number on the label.

Fix a grade by adding `name=GRADE` pairs to the same command and re-running it (it only re-grades and redraws the
sheets):

```bash
cd "$VIDEO_ENGINE" && python3 cutouts/cutouts.py --profile myteam cut <work>/crops <work>/numbers.json <work>/out IMG_0002=X IMG_0005=B
```

The `ocr` digits in `grades.json` are only a hint to cross-check your reading; they miss most numbers. To fix a
wrong number, edit `number` for that photo in `out/grades.json` before filing.

## 5. File into the library

```bash
cd "$VIDEO_ENGINE" && python3 cutouts/cutouts.py --profile myteam library <work>/out <roster.csv> "<work>/Library" --games-map <cull dir>/rows.json
cd "$VIDEO_ENGINE" && python3 cutouts/copy_photos.py <work>/crops <work>/lib_plan.json "<work>/Library"
```

- The roster is a CSV with `number` and `name` columns. Folder names are `#<number> <name>` with
  `" \ / : * ? < > |` removed.
- `--games-map` is required. `library` reads `cut_requests.json` from the folder of each path after it (one per
  game; list several to file several games). On the photo-folder route, write `{}` to `<work>/cut_requests.json`
  and pass `--games-map <work>/cut_requests.json`.
- X grades are skipped. Unreadable or off-roster numbers go to `_Unidentified/`, `MASCOT` to `_Mascot/`.
- It extends an existing library and skips photos already in `_index.csv`. It writes `lib_plan.json` next to the
  library folder; `copy_photos.py` then copies the full-res crops into `Portraits/` or `Action/` (never overwriting).

## Worked example (photo-folder route, demo profile)

Works on a fresh clone with `setup.sh` done (the `demo` profile ships with the engine; `python3 engine/vprofile.py
list` shows it). Put the user's own photos in `crops/`, prepared as in section 3 (JPEG, `<name>.jpg`, one loosely
cropped player each). The first `cut` downloads the two models (close to 1 GB each); tell the user first.

```bash
W=~/Movies/video-work/cutouts-try && mkdir -p "$W/crops"
cp ~/Pictures/game/IMG_0001.jpg ~/Pictures/game/IMG_0002.jpg "$W/crops/"
printf '{"IMG_0001": "12", "IMG_0002": null}\n' > "$W/numbers.json"
printf 'number,name\n12,Jane Doe\n7,Sam Lee\n' > "$W/roster.csv"
echo '{}' > "$W/cut_requests.json"
cd "$VIDEO_ENGINE"
python3 cutouts/cutouts.py --profile demo cut "$W/crops" "$W/numbers.json" "$W/out"
python3 cutouts/cutouts.py --profile demo library "$W/out" "$W/roster.csv" "$W/Library" --games-map "$W/cut_requests.json"
python3 cutouts/copy_photos.py "$W/crops" "$W/lib_plan.json" "$W/Library"
```

Result, when both photos grade A or B (`cut` prints each grade; an X is not filed):
`Library/#12 Jane Doe/Cutouts/#12 - - IMG_0001.png` (the dashes hold the empty `home_abbr` and game label) with the
full-res copy in `#12 Jane Doe/Action/`, `Library/_Unidentified/Cutouts/unknown - - IMG_0002.png` (and its photo in
`_Unidentified/Photos/`), an empty `#7 Sam Lee/`, an empty `_Mascot/`, `_index.csv` and `_Overview.jpg`. `library`
prints `2 cutouts in the library; 1 players` and `copy_photos.py` prints `copied 2`. If a photo grades X, `Read` the
review sheet to see why (usually too small, cut off at the top or a side, or a second person attached) and fix the
crop or override the grade. To put a game label in the names on this route, give each photo an entry in `cut_requests.json`:
`{"IMG_0001": {"n": "IMG_0001", "wk": "Wk03"}}`.

## Rules

- Names come only from the user's own roster. If the players are minors, confirm the user may use their photos (the
  team's or school's media permission); leave out injured players and anything embarrassing.
- Never delete or overwrite library files. Re-runs only add files.
- When the user says who an unidentified player is, move the files from `_Unidentified/` into that player's folder
  (rename `unknown` to `#<number>` in the file names) and fix that line in `_index.csv` (`player`, `number`,
  `cutout`).
- A cutout is a derivative of a photo of a real person. Use it for the team's own graphics; never composite a
  player into a scene that misrepresents them (an endorsement, an event they were not at).
- Nothing is uploaded. Do not send photos or cutouts to an online service unless the user chooses one.

## Using the cutouts

- `engine/statcard.py` stats lower third: `"photo": "<cutout png>"` in the stats JSON (`docs/stats_card_example.json`).
- `engine/quote.py --cutout <png>` quote card; `engine/progressbar.py --face <png>` progress-bar face.
- Any video that uses them goes through the video-gates skill (`engine/qa.py`) before delivery.

## Report

One line per game: how many cutouts were filed, how many players now have at least one, and how many are
unidentified. Point the user to `_Overview.jpg` and the review sheets that had overrides.
