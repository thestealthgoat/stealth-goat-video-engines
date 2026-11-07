#!/bin/bash
# One-time setup for the logo tools (logo/). Works from any folder: it changes into logo/ itself.
# Fonts come from the profile (resources/fonts), the super-resolution models from resources/models.
set -e
cd "$(dirname "$0")"
npm i --no-audit --no-fund
PIP="python3 -m pip"   # a bare 'pip' is missing on some Macs (python.org builds ship only pip3)
$PIP install --break-system-packages -q vtracer cairosvg scikit-learn opencv-python-headless pillow playwright fonttools 2>/dev/null || \
  $PIP install --user -q vtracer cairosvg scikit-learn opencv-python-headless pillow playwright fonttools
python3 -m playwright install chromium 2>/dev/null || true   # skip where Chromium is pre-installed
# opencv-contrib 4.x for AI upscaling (kept in its own venv so it can't clash with the main opencv; logo/srenv is gitignored)
[ -x srenv/bin/python ] || { python3 -m venv srenv && srenv/bin/pip install -q opencv-contrib-python-headless==4.10.0.84 "numpy<2.3"; }
# Super-resolution models (OpenCV dnn_superres, Apache-2.0, from the Saafke repos). Not shipped in the public repo.
mkdir -p ../resources/models
for m in EDSR_x4.pb:EDSR_Tensorflow:dd35ce3cae53ecee2d16045e08a932c3e7242d641bb65cb971d123e06904347f \
         FSRCNN_x4.pb:FSRCNN_Tensorflow:5c68d18db561aed8ead4ffedf1b897ea615baaf60ebf6c35f8e641f8fa4a21bf; do
  f=${m%%:*}; rest=${m#*:}; repo=${rest%%:*}; want=${rest#*:}
  [ -f ../resources/models/$f ] && continue
  if curl -fsSL -o ../resources/models/$f.part "https://raw.githubusercontent.com/Saafke/$repo/master/models/$f"; then
    mv ../resources/models/$f.part ../resources/models/$f
    got=$(shasum -a 256 ../resources/models/$f | cut -d' ' -f1)
    [ "$got" = "$want" ] || echo "note: $f sha256 $got differs from the copy this engine was tested with ($want)"
  else
    rm -f ../resources/models/$f.part
    echo "could not download $f (vectorize.py falls back to Lanczos)"
  fi
done
echo "Logo tools ready."
