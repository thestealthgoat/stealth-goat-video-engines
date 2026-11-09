# matte.py: models, flags and troubleshooting

Synopsis with the defaults filled in (the argparse listing itself is `python3 engine/matte.py --help`):

```
matte.py <video> --out <dir> [--name N] [--t0 S] [--t1 S]
         [--model birefnet-general|birefnet-portrait|modnet|u2net_human_seg] [--infer 512]
         [--steady 0.85] [--choke 0] [--feather 1.0] [--bg profile|'#hex'|image|blur|none]
         [--max-height 1080] [--min-region 0.15] [--rotate cw|ccw|180] [--frames 1.0,2.5] [--profile P]
```

## Models

All free and local. rembg models download on first use into the folder `engine/models.py` picks (`$U2NET_HOME`,
else `"rembg_models"` in the engine root's `local.json`, else `resources/models/rembg` in the engine folder, else
rembg's default folder). A fresh clone has no `local.json`: create it (`{ "rembg_models": "/path/on/big/drive/rembg" }`) to keep
the ~1 GB files on another drive; models.py creates that folder if it is missing, and falls back silently when it
cannot (an unmounted drive).

| `--model` | Licence | Download | Use |
|---|---|---|---|
| `birefnet-general` (default) | MIT (BiRefNet, via rembg) | ~1 GB | The most complete people: hair, hands, feet, dark clothing on a dark ground. Keeps the main subject(s), drops bystanders. ~5-6 s a 1080p frame on a laptop CPU. |
| `birefnet-portrait` | MIT | ~1 GB | Just as complete, but keeps everyone in the shot, bystanders too. Use when a second or third person must stay. |
| `u2net_human_seg` | Apache-2.0 (U^2-Net, via rembg) | ~175 MB | Harder edges; lighter. A rough draft, or small far figures. Less complete than BiRefNet. |
| `modnet` | Apache-2.0 (MODNet) | placed by hand | Soft hair-level alpha, fast (~0.15 s a frame): drafts only. Loses dark clothing against dark grounds. Needs `resources/models/modnet_photographic_portrait_matting.onnx` (where it comes from: the engine's `NOTICE.md`); matte.py exits with "model missing" without it. |

Model comparison the defaults are based on (13 frames of mixed portrait and sport material, scored 0-10 for missing
body by independent reviewers, lower is better): MODNet 5.2, U^2-Net 3.2, BiRefNet portrait 1.4, BiRefNet general
1.0. BiRefNet general was best on 11 of 13 frames.

## Flags

| Flag | Default | What it does / when to change it |
|---|---|---|
| `video` | (required) | the source clip |
| `--out` | (required) | output folder (created if missing) |
| `--name` | clip file name | base name of every output (`<name>_matte...`) |
| `--t0`, `--t1` | 0, end of clip | the window in source seconds. Matte only what the composite needs. |
| `--model` | `birefnet-general` | see the table above |
| `--infer` | 512 | `modnet` only: model input size (short side, px). 640-768 for 4K close-ups (slower). Ignored by the other models. |
| `--steady` | 0.85 | temporal hold: where the picture did not change since the last frame, the last alpha wins by this much; where it changed, the new alpha wins. Higher = steadier edges; 0 = raw per frame. No optical flow, so it never drags a moving arm along, but once a hand or arm moves off a textured background that area is "unchanged" again and the old alpha fades out only slowly: a streaky ghost of the background for a few frames. Lower it (0.5, or 0) if you see that. |
| `--min-region` | 0.15 | drop matte islands smaller than this share of the largest region (a lamp, a cymbal, specks). 0 keeps everything. Lower it if a smaller second person is dropped. |
| `--choke` | 0 | erode the edge by this many px (a halo of old background). Try 1. |
| `--feather` | 1.0 | soften the final edge (px of blur). |
| `--bg` | `profile` | preview background only: `profile` (the profile's `brand.colors.primary_deep`, else `primary`), `'#hex'`, an image path, `blur` (the shot blurred), `none` (same as blur in the preview) |
| `--max-height` | 1080 | caps the short side of the output (a 4K clip renders at 1080p; a portrait clip stays 1080 wide) |
| `--rotate` | none | `cw`, `ccw` or `180`: turn the picture first, for a phone clip whose rotation tag is wrong (people sideways). The model needs people upright. |
| `--frames` | none | stills only, at these times (seconds relative to `--t0`): writes `<name>_matte_t<t>.png` (RGBA) and `<name>_matte_check.jpg` |
| `--profile` | `$VIDEO_PROFILE`, then `local.json` | profile name or a path to a `profile.json` |

## What happens to each frame

1. The model runs on the frame (MODNet at `--infer` px).
2. The alpha is refined against the picture with a guided filter, so edges follow the real outline and hair keeps
   its softness.
3. Small islands are dropped (`--min-region`).
4. The temporal hold steadies unchanged edges (`--steady`).
5. Choke, feather, and a clean-up that removes faint haze far from the person.
6. Edge colour is rebuilt from the person's own nearby colour, so the old background does not bleed into the edge
   of the alpha .mov.

## `<name>_matte.json`

Keys: `video`, `t0`, `t1`, `frames`, `size` [W, H], `fps`, `model`, `infer`, `steady`, `choke`, `feather`,
`rotate`, `edge_flicker_mean`, `edge_flicker_p95` (the alpha's second difference in time in the edge band: smooth
motion is near 0, shimmer is high; under about 0.05 reads as solid), `edge_change_mean`, `edge_change_p95`
(frame-to-frame change in the edge band), `seconds` (render time).

## Troubleshooting

| Symptom | Fix |
|---|---|
| People sideways in the check sheet | `--rotate cw` / `ccw` / `180` |
| Edges shimmer, flicker mean over ~0.05 | raise `--steady` to 0.9-0.95 (then check for ghost trails, next row) |
| Streaky ghost of the background where a hand or arm just was (not caught by the flicker number or qa) | lower `--steady` to 0.5, or 0; edges flicker a little more |
| A coloured fringe of the old background | `--choke 1`, maybe `--feather 1.5` |
| A second person dropped | `--min-region 0.05` or 0, or `--model birefnet-portrait` |
| A bystander kept | `--model birefnet-general` (default), raise `--min-region` |
| Arms, legs or dark clothing missing | stay on a BiRefNet model; if still missing, the shot is too wide: use a closer angle |
| "model missing: .../modnet_photographic_portrait_matting.onnx" | use a BiRefNet model, or place the MODNet file (see `NOTICE.md`) |
| First run seems stuck | rembg is downloading ~1 GB into the models folder; wait, and check the disk has room |
| "Broken pipe" / "Error muxing a packet" lines after `--frames` | harmless: the decoder is stopped early once the asked stills are done |
| qa `spec_fps` / `spec_size` FAIL on the matte | the matte keeps the source rate and size: pass `--fps` and `--size` from `<name>_matte.json` to `engine/qa.py` |
