# Player Cutouts

This tool turns culled game photos into checked, transparent player cutouts, filed by player in
`<library>/#<number> <Name>/{Cutouts, Portraits, Action}`.
It runs after Photo Cull, and reuses that run's player masks and 960 px previews.

`cutouts.py` takes `--profile NAME` (default: `$VIDEO_PROFILE`, then `local.json`). From the profile it reads the
team uniform colours (`team.uniform`), the review-sheet background (`brand.colors.primary`), the label font
(`brand.fonts.body`, in `resources/fonts`) and the team abbreviation in library file names (`team.home_abbr`).
`team.uniform` has no built-in default: `candidates` stops with a clear message if the profile lacks it.
Folders (cull dir, Games dir — the profile's `paths.games` —, crops, library) are always given on the command line.

| Step | Where | Command |
|---|---|---|
| 1. Candidates | cloud | `python3 cutouts.py candidates <cull dir> <Wk>` → `cut_requests.json` + numbered `cutcand_N.jpg` |
| 2. Read the numbers | cloud | Look at the sheets and write `numbers.json`: `{"R5_x": "12", "R5_y": null, "R5_z": "MASCOT"}`. Leave out anything not worth cutting (a coach, a crowd, a bad crop) |
| 3. Full-res crops | Mac | `python3 fullcrop.py "<Games/Football/<year>>" cut_requests.json <crops> --seconds 150` (rerun until DONE), then tar the crops and stage them |
| 4. Cut + grade | cloud | `python3 cutouts.py cut <crops> numbers.json <out>`. Look at `review_N.jpg` and override a wrong grade with `R5_x=B` |
| 5. File | cloud → Mac | `python3 cutouts.py library <out> <roster>.csv "<lib>" --games-map <cull dir>/rows.json`. Tar the library and commit it (split if it's over 30 MB), extract it on the NAS, then `python3 copy_photos.py <crops> lib_plan.json "<lib>"` |

## The cutout check (why a cutout is A, B or rejected)
- **Before cutting** (candidates):
  - one dominant person: a second person larger than 15% of him rejects the frame;
  - his head and sides are not cut off by the frame;
  - he is at least 35% of the frame height;
  - he is wearing the team uniform: enough of the team colour, with none of the opponents' colours
    (`team.uniform`, e.g. navy, rejecting light blue and gold);
  - only the best frame of each burst goes forward (ranked by the cull's subject score x his height share).
- **The cut:** the alpha comes from BiRefNet general (crisp, complete people: helmets, dark jerseys, hands),
  checked against BiRefNet portrait; phone photos are turned upright from their EXIF orientation. The largest person is kept and stray blobs are dropped.
- **Grade:**
  - A = full body;
  - B = cut at the bottom of the frame (3/4 length);
  - X = rejected: the two masks disagree (IoU < 0.8), more than 25% of the edge is soft (blur or motion),
    there is more than one piece, he is cut at the top or sides, or the cutout is under 1,500 px tall.
  A person always looks at the review sheet as well. The check catches most problems, not all of them.
- **Numbers:** a person reads them. OCR (RapidOCR) is only a hint, because it reads clear numbers on a player's
  back and misses most others. If the number can't be read, the cutout goes to `_Unidentified/`. Names come only
  from the public roster.
