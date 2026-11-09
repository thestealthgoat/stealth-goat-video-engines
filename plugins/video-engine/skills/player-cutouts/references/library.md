# Library files and grading (cutouts/cutouts.py)

## What `cut` measures

Each photo `<crops>/<name>.jpg` is scaled to fit 3,000 px, then:

| Step | What happens |
|---|---|
| Masks | `birefnet-portrait` (keeps every person) and `birefnet-general` (crisp, complete edges) through rembg |
| Gate | the general alpha is multiplied by a dilated, blurred copy of the portrait mask (> 0.3), so only people are kept |
| Keep | the largest piece, plus any piece larger than 25% of it; everything else is dropped |
| Crop | the PNG is cropped to its alpha bounding box and saved to `out/png/<name>.png` |

`out/grades.json`, one entry per photo:

| Key | Meaning |
|---|---|
| `number` | from `numbers.json` (`null` = unreadable, `"MASCOT"`) |
| `grade` | `A`, `B` or `X` (see below); `override: true` when set by a `name=GRADE` argument |
| `iou` | agreement of the two masks around the kept player (portrait mask limited to his neighborhood) |
| `soft_edge` | share of semi-transparent pixels (alpha 26-229) against solid ones |
| `parts` | solid pieces larger than 1% of the cutout |
| `cut` | edges the cutout touches: `top`, `left`, `right`, `bottom` |
| `size` | `[width, height]` of the PNG |
| `ocr` | digits RapidOCR read with confidence over 0.6 (a hint only; empty when RapidOCR is not installed) |

## Grades

| Grade | Rule | Filed? |
|---|---|---|
| X | `iou` < 0.8, or `soft_edge` > 0.25, or `parts` > 1, or cut at `top` / `left` / `right`, or height < 1,500 px | no |
| B | none of the above, but cut at the `bottom` (three-quarter length) | yes |
| A | none of the above: full body | yes |

Edge tests: more than 1% of the top row, 3% of a side column or 2% of the bottom row is solid.

## `library` output

| Path | Contents |
|---|---|
| `#<number> <name>/Cutouts/` | `<abbr> #<number> - <game> - <name>.png` |
| `#<number> <name>/Portraits/` | full-res crop, when the cull says the frame is a tight pregame shot (folder `02 Pregame`, category `portrait`, `warmup` or `sideline`, player over 60% of the frame height) |
| `#<number> <name>/Action/` | full-res crop, every other filed frame |
| `_Unidentified/Cutouts/`, `_Unidentified/Photos/` | unreadable or off-roster numbers (`unknown` in the file name) |
| `_Mascot/Cutouts/` | `MASCOT` entries (no full-res copy) |
| `_index.csv` | `player, number, grade, cutout, source_raw, game, size, full_body, mask_agreement`; an existing index keeps its own header |
| `_Overview.jpg` | every filed cutout on the profile's primary color, labeled with folder and grade |
| `../lib_plan.json` | next to the library folder: the copies `copy_photos.py` makes (`src` crop name, `dst` library path) |

`source_raw` is recorded as `<name>.CR3` whatever the source camera; it is how a re-run recognizes photos already
filed. Use the same photo names on later runs so nothing is filed twice.

File names: characters `" \ / : * ? < > |` are removed and runs of spaces collapse, so an empty `team.home_abbr`
or game label leaves `#12 - - IMG_0001.png`.
