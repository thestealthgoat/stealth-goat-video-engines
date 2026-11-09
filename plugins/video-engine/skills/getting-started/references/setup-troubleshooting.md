# setup.sh: what it checks, and fixes

`./setup.sh --check` installs nothing and prints `ok`, `MISS` (required, counted) or `WARN` (worth knowing) per
item, in six steps. The last line is `== Result: <missing> missing, <warnings> warnings`; exit code 0 only when
nothing required is missing. `./setup.sh --help` prints the options.

| Step | What it looks at |
|---|---|
| 1. Homebrew formulas | brew itself; `ffmpeg imagemagick tesseract node cairo`; which ffmpeg is on PATH; encoders `libx264 aac prores_ks h264_videotoolbox`; filters `loudnorm ebur128 scdet`; `-fps_mode` support |
| 2. Python packages | Python 3.10 or newer; `pip install --user -r requirements.txt` (not with `--check`); an import of each module; duplicate OpenCV wheels; cv2 + PyAV clash; CA certificates; pip's script folder on PATH |
| 3. Logo tools | `logo/setup.sh` (not with `--check`); `logo/node_modules`; Playwright Chromium; the `logo/srenv` venv |
| 4. Resources | fonts in `resources/fonts/`; the EDSR / FSRCNN upscaling models in `resources/models/` |
| 5. Shell lines | the lines to add to `~/.zprofile` (it never edits them itself) |
| 6. Profile | `python3 engine/vprofile.py show <profile> --check` for `--profile NAME`, else `$VIDEO_PROFILE`, else the `local.json` default |

## Common lines and their fixes

| Line | Fix |
|---|---|
| `MISS Homebrew is not installed` | the user installs it from https://brew.sh (it asks for their password), then `./setup.sh` |
| `WARN ffmpeg on PATH is ... not /opt/homebrew/bin/ffmpeg` | put `/opt/homebrew/bin` first in PATH (step 5 line). Old non-native builds can stall at 100% CPU (`docs/ffmpeg-notes.md`) |
| `WARN ... has no -fps_mode: too old` | `brew upgrade ffmpeg` |
| pip says `externally-managed-environment` | Homebrew's Python refuses `--user` installs. Use the python.org Python, or a venv: `python3 -m venv ~/.venvs/video && . ~/.venvs/video/bin/activate`, then `./setup.sh` again (inside a venv it installs without `--user`). Note that `logo/setup.sh` (step 3) installs its own Python packages with `--break-system-packages` first (errors hidden), falling back to `--user`; inside a venv that line lands in the venv |
| `MISS import cairosvg` (others import fine) | it needs Homebrew's libcairo: `export DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib` (the logo tools set it themselves) |
| `MISS import <module>` | `python3 -m pip install --user -r requirements.txt`, and check `python3` is the same Python setup.sh used (step 2 prints its path) |
| `WARN more than one OpenCV wheel installed` | run the two commands setup.sh prints (keep only `opencv-python-headless`) |
| `WARN cv2 and av (PyAV ...)` | informational: no engine tool imports both in one process |
| `WARN this Python has no CA certificates` | python.org Python: run `"/Applications/Python 3.x/Install Certificates.command"`; or `python3 -m pip install --user certifi` and `export SSL_CERT_FILE="$(python3 -m certifi)"`. Without it, first-use model downloads fail with `CERTIFICATE_VERIFY_FAILED` |
| `WARN .../bin is not on PATH (pip --user scripts)` | add the PATH line from step 5 |
| `MISS logo/node_modules/three` or `gltf-transform` | `cd "$VIDEO_ENGINE/logo" && npm ci` |
| `MISS Playwright Chromium` | `python3 -m playwright install chromium` |
| `WARN logo/srenv missing` | optional: AI upscaling in the logo tools falls back to Lanczos. `bash logo/setup.sh` makes it |
| `WARN resources/models/EDSR_x4.pb missing` | optional: `bash logo/setup.sh` downloads both models; without them vectorizing upscales with Lanczos |
| `WARN rapidocr_onnxruntime missing (optional ...)` | optional; skip unless cutouts need jersey-number hints |
| `WARN profile <name>: something above is missing` | read the profile block above it: usually a folder that does not exist yet (`mkdir -p` it) or a font/logo path to correct |
| `WARN no default profile on this machine` | `python3 engine/vprofile.py default <name>`, or run with `--profile <name>` |

## First-use downloads

These happen once, the first time a tool needs them, and stay on this machine (no media is uploaded):

- rembg models (BiRefNet for person cutouts and mattes): into the folder `engine/models.py` picks
  (`$U2NET_HOME`, else `rembg_models` in `local.json`, else `resources/models/rembg` if it exists, else rembg's
  default folder). To keep them somewhere else, add `"rembg_models": "<folder>"` to `local.json` (the folder is
  created if it does not exist yet).
- faster-whisper speech models (transcripts, caption timing, talking-head edits).
- Playwright Chromium (motion, 3D and explainer pages render in a headless browser).

## Self-tests

```bash
cd "$VIDEO_ENGINE" && for t in tests/test_*.py; do python3 "$t" || echo "FAILED: $t"; done
```

Each prints PASS / FAIL / SKIP per case and writes only to `tests/out/` and a temporary folder.

## Not on a Mac

`setup.sh` is written for macOS on Apple silicon with Homebrew and is untested elsewhere. The engine itself is
Python 3.10+ and ffmpeg, so a manual setup may work; tell the user it is unsupported and try:

1. Install with the system's package manager: ffmpeg (a recent build with `-fps_mode`, libx264, prores_ks,
   loudnorm, ebur128, scdet), node + npm, cairo, tesseract, ImageMagick.
2. `python3 -m pip install --user -r requirements.txt` (or in a venv).
3. `bash logo/setup.sh` (npm packages, Playwright Chromium, the upscaling venv and models).
4. `python3 engine/vprofile.py show demo --check`, then the tour's `--frames` stills before any full render.

`h264_videotoolbox` is macOS-only; its warning elsewhere is expected.
