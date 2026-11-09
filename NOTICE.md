# Third-party notices

## Higgsfield AI — higgsfield-video-engineer (MIT)

- Source: https://github.com/higgsfield-ai/higgsfield-video-engineer, commit `082bfd7` (Oct 28 2026),
  `skills/code-based-films/`.
- Licence: MIT, Copyright (c) 2026 Higgsfield AI. Full text: [`vendor/higgsfield/LICENSE`](vendor/higgsfield/LICENSE).
- Unchanged copies: `vendor/higgsfield/beatmap.py`, `vendor/higgsfield/qa.md` (see `vendor/higgsfield/NOTICE.md`).
- Modified copy: `engine/beatmap.py` (3:2 / 4:3 and non-octave tempo alias guards, half/double guards, `build()` API,
  `--profile` default for `--fps`, BPM cross-check against the profile, ffmpeg/ffprobe run with no stdin; the changes
  are listed in its docstring). The MIT notice is kept in its header.

Keep this notice and the licence file with any copy or modified version of these files.

## clipify — louisedesadeleer/clipify (MIT)

- Source: https://github.com/louisedesadeleer/clipify (MIT licence).
- Used as a reference only, for one idea in `engine/talkedit.py`: a 9:16 crop that follows the speaker and
  changes position only with hard cuts (no drifting pan). No clipify code, captions code or prompts are copied;
  talkedit finds the face with OpenCV's Haar cascade and moves the crop only at its own jump cuts.
- If any clipify code is copied in the future, add its MIT notice (Copyright (c) the clipify authors) here and in
  the file header.

## three.js (MIT)

- https://github.com/mrdoob/three.js, installed with npm into `logo/node_modules/three` (`logo/package.json`), MIT,
  Copyright (c) 2010-2024 three.js authors. Used unmodified by `logo/render.html` and `engine/stage3d.html` (core, plus
  the `RoomEnvironment` and `RoundedBoxGeometry` add-ons it ships). No three.js code is copied into this repo.

## Map data (engine/routemap.py, O6)

- Natural Earth 1:10m layers (roads, rivers, lakes, coastline, borders, populated places): public domain,
  https://www.naturalearthdata.com (downloaded on first use into `_cache/naturalearth/`, not committed). Credited on
  screen as "Map data: Natural Earth".
- OpenStreetMap data (`--map osm`, from the Overpass API): © OpenStreetMap contributors, ODbL. The credit is drawn on
  every frame. OSM's raster tile servers are not used (their usage policy rules out scripted renders).

## Website kit (web/)

- three.js is copied into each built site from `logo/node_modules/three` with its MIT licence (see three.js above).

## Fonts (SIL Open Font License 1.1)

- All bundled fonts are in `resources/fonts/`, each family with its licence text. See `resources/fonts/README.md`.
- Added for a brand profile: Cinzel (Bold) and Inter (Regular, SemiBold), **modified**: static
  instances cut from the Google Fonts variable fonts with fontTools (no Reserved Font Names).
- Added 2026-11-08 for two brand profiles: Montserrat, Pinyon Script, IBM Plex Sans / Mono (unmodified)
  and Fraunces. The two Fraunces files are **modified**: static instances cut from the variable font with fontTools
  and renamed "Fraunces Soft" (Fraunces has no Reserved Font Name). IBM Plex is used unmodified because "Plex" is a
  Reserved Font Name.

## MODNet portrait matting model (Apache-2.0)

- `engine/matte.py` runs MODNet (Ke et al., "MODNet: Real-Time Trimap-Free Portrait Matting via Objective
  Decomposition", https://github.com/ZHKKKe/MODNet, Apache-2.0) from the ONNX export at
  https://huggingface.co/Xenova/modnet (`onnx/model.onnx`), saved as
  `resources/models/modnet_photographic_portrait_matting.onnx`. The model file is not committed; download it from
  there. No MODNet code is copied: the pre/post-processing in matte.py is our own.
- The guided filter in matte.py is written from the published method (He, Sun, Tang, "Guided Image Filtering").

## BiRefNet person segmentation (MIT)

- `engine/matte.py` (default), `engine/cutout.py` and `cutouts/cutouts.py` run BiRefNet (Zheng et al., "Bilateral
  Reference for High-Resolution Dichotomous Image Segmentation", https://github.com/ZhengPeng7/BiRefNet, MIT) through
  rembg (https://github.com/danielgatis/rembg, MIT), which downloads the ONNX weights `birefnet-general` /
  `birefnet-portrait` from its GitHub releases into `$U2NET_HOME` (see `engine/models.py`). The
  model files are not committed. No BiRefNet or rembg code is copied; we call rembg's public API.
