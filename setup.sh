#!/bin/bash
# setup.sh - set up the video engine on a Mac (Apple silicon + Homebrew). Safe to run again: it only installs what
# is missing and re-checks everything else.
#
#   ./setup.sh                 install what is missing, then check
#   ./setup.sh --check         install nothing; only report what is there and what is missing
#   ./setup.sh --no-brew       skip Homebrew formulas      --no-pip    skip pip      --no-logo   skip logo/setup.sh
#   ./setup.sh --profile NAME  profile to check at the end (default: $VIDEO_PROFILE, then local.json)
#
# What it does:
#   1. Homebrew formulas: ffmpeg (stable, native arm64, /opt/homebrew/bin), imagemagick, tesseract, node, cairo;
#      then which ffmpeg is on PATH (and its encoders and filters), ffprobe, tesseract, magick, node
#   2. python3 -m pip install --user -r requirements.txt, then an import check of every module; warnings for
#      duplicate OpenCV wheels, the cv2 + PyAV dylib clash, missing CA certificates, pip --user scripts not on PATH
#   3. logo/setup.sh (npm packages, Playwright Chromium, the opencv-contrib venv logo/srenv for sr.py)
#   4. resources: the fonts in resources/fonts and the upscaling models in resources/models
#   5. prints the shell lines to add to ~/.zprofile
#   6. python3 engine/vprofile.py show <profile> --check
# Exit code: 0 when every required piece is there, 1 when something required is missing.

set -u
cd "$(dirname "$0")" || exit 1
REPO=$(pwd)

CHECK=0; DO_BREW=1; DO_PIP=1; DO_LOGO=1; PROFILE="${VIDEO_PROFILE:-}"
while [ $# -gt 0 ]; do
  case "$1" in
    --check) CHECK=1 ;;
    --no-brew) DO_BREW=0 ;;
    --no-pip) DO_PIP=0 ;;
    --no-logo) DO_LOGO=0 ;;
    --profile) shift; PROFILE="${1:-}" ;;
    --profile=*) PROFILE="${1#--profile=}" ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "unknown option: $1 (see --help)"; exit 2 ;;
  esac
  shift
done

MISSING=0; WARNINGS=0
ok()   { printf '  ok    %s\n' "$*"; }
miss() { printf '  MISS  %s\n' "$*"; MISSING=$((MISSING + 1)); }
warn() { printf '  WARN  %s\n' "$*"; WARNINGS=$((WARNINGS + 1)); }
step() { printf '\n== %s\n' "$*"; }

# ---------------------------------------------------------------------------------------------------------------
step "1. Homebrew formulas"
BREW=""
if [ -x /opt/homebrew/bin/brew ]; then BREW=/opt/homebrew/bin/brew
elif command -v brew >/dev/null 2>&1; then BREW=$(command -v brew)
fi
if [ -z "$BREW" ]; then
  miss "Homebrew is not installed. Install it from https://brew.sh, then run ./setup.sh again."
else
  ok "brew: $BREW"
  for f in ffmpeg imagemagick tesseract node cairo; do
    if "$BREW" list --versions "$f" >/dev/null 2>&1; then
      ok "$f $("$BREW" list --versions "$f" | awk '{print $2}')"
    elif [ "$CHECK" = 1 ] || [ "$DO_BREW" = 0 ]; then
      miss "$f (brew install $f)"
    else
      echo "  installing $f ..."
      if "$BREW" install "$f"; then ok "$f installed"; else miss "$f: brew install failed"; fi
    fi
  done
fi

# ffmpeg: use the stable native build. The evermeet x86 nightly in /usr/local/bin runs under Rosetta and can stall
# (100% CPU) on an unbounded apad (docs/ffmpeg-notes.md).
FF=$(command -v ffmpeg 2>/dev/null || true)
if [ -z "$FF" ]; then
  miss "ffmpeg not on PATH"
else
  case "$FF" in
    /opt/homebrew/bin/ffmpeg) ok "ffmpeg on PATH: $FF" ;;
    *) warn "ffmpeg on PATH is $FF ($(file -b "$FF" 2>/dev/null | awk '{print $NF}')), not /opt/homebrew/bin/ffmpeg."
       echo "        Put /opt/homebrew/bin first in PATH (lines at the end). The x86 evermeet nightly stalls:"
       echo "        see docs/ffmpeg-notes.md. Keep the old binary until the diff tests pass on the new one." ;;
  esac
  FFC=/opt/homebrew/bin/ffmpeg; [ -x "$FFC" ] || FFC="$FF"
  ENC=$("$FFC" -hide_banner -encoders 2>/dev/null); FIL=$("$FFC" -hide_banner -filters 2>/dev/null)
  for e in libx264 aac prores_ks h264_videotoolbox; do
    echo "$ENC" | grep -qw "$e" && ok "$FFC encoder $e" || warn "$FFC has no encoder $e"
  done
  for x in loudnorm ebur128 scdet; do
    echo "$FIL" | grep -qw "$x" && ok "$FFC filter $x" || warn "$FFC has no filter $x"
  done
  "$FFC" -hide_banner -h full 2>/dev/null | grep -q -- '-fps_mode' && ok "$FFC supports -fps_mode (no -vsync)" \
    || warn "$FFC has no -fps_mode: too old for the engine"
fi
command -v ffprobe   >/dev/null 2>&1 && ok "ffprobe: $(command -v ffprobe)" || miss "ffprobe not on PATH"
command -v tesseract >/dev/null 2>&1 && ok "tesseract: $(command -v tesseract)" || miss "tesseract not on PATH (scorebug reader)"
command -v magick    >/dev/null 2>&1 && ok "imagemagick: $(command -v magick)" || warn "imagemagick not on PATH (thumbnail scripts)"
command -v node      >/dev/null 2>&1 && ok "node $(node --version 2>/dev/null)" || miss "node not on PATH (logo tools, spring tests)"

# ---------------------------------------------------------------------------------------------------------------
step "2. Python packages"
PY=$(command -v python3 || true)
if [ -z "$PY" ]; then
  miss "python3 not found. Install Python 3.10+ from python.org (the installer is easiest; Homebrew's Python refuses pip --user), then run again."
  PYV=""
else
  PYV=$("$PY" -c 'import sys; print("%d.%d" % sys.version_info[:2])')
  ok "python3 $PYV: $PY"
  "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' || miss "python3 $PYV is too old (need 3.10+)"
  IN_VENV=$("$PY" -c 'import sys; print(int(sys.prefix != sys.base_prefix))')
  USERBASE=$("$PY" -m site --user-base 2>/dev/null)
  if [ "$CHECK" = 0 ] && [ "$DO_PIP" = 1 ]; then
    if [ "$IN_VENV" = 1 ]; then PIPUSER=""; else PIPUSER="--user"; fi
    echo "  pip install $PIPUSER -r requirements.txt ..."
    if ! "$PY" -m pip install $PIPUSER -q -r "$REPO/requirements.txt"; then
      warn "pip install failed. If pip says 'externally-managed-environment' (Homebrew Python), use the python.org"
      echo "        Python or a venv (python3 -m venv ~/.venvs/video && . ~/.venvs/video/bin/activate), then run again."
    fi
  fi
  # import check (cairosvg needs Homebrew's libcairo on the library path)
  for m in numpy scipy PIL librosa soundfile cv2 vtracer cairosvg sklearn fontTools playwright rembg onnxruntime faster_whisper; do
    if DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib "$PY" -c "import $m" >/dev/null 2>&1; then ok "import $m"
    else miss "import $m (python3 -m pip install --user -r requirements.txt)"; fi
  done
  DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib "$PY" -c "import rapidocr_onnxruntime" >/dev/null 2>&1 \
    && ok "import rapidocr_onnxruntime (optional)" || warn "rapidocr_onnxruntime missing (optional: jersey-digit hint in cutouts.py)"
  "$PY" -c "import cairosvg" >/dev/null 2>&1 \
    || echo "        note: cairosvg imports only with DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib (logo tools set it themselves)"

  # duplicate OpenCV wheels share one cv2 folder: uninstalling either breaks the other
  CVS=$("$PY" -m pip list --format=freeze 2>/dev/null | grep -iE '^opencv-(contrib-)?python(-headless)?==' | tr '\n' ' ')
  NCV=$(echo "$CVS" | wc -w | tr -d ' ')
  if [ "$NCV" -gt 1 ]; then
    warn "more than one OpenCV wheel installed: $CVS"
    echo "        They share the cv2 folder. Keep only the headless one:"
    echo "        python3 -m pip uninstall -y opencv-python && python3 -m pip install --user --force-reinstall --no-deps opencv-python-headless"
  fi
  # cv2 and PyAV (pulled in by faster-whisper) each bundle their own libav* dylibs
  if "$PY" -c "import cv2, av" 2>&1 | grep -q "implemented in both"; then
    warn "cv2 and av (PyAV, from faster-whisper) bundle different libavdevice copies: importing both in one process"
    echo "        prints 'Class AVF... is implemented in both' and can crash. No engine tool needs both; keep them in"
    echo "        separate processes (or put faster-whisper in its own venv)."
  fi
  # python.org Python ships without CA certificates until 'Install Certificates.command' has run
  if ! "$PY" -c 'import ssl, os, sys; p = ssl.get_default_verify_paths(); sys.exit(0 if (p.cafile and os.path.exists(p.cafile)) or (p.capath and os.path.isdir(p.capath) and os.listdir(p.capath)) or os.environ.get("SSL_CERT_FILE") else 1)' 2>/dev/null; then
    warn "this Python has no CA certificates (HTTPS model downloads fail with CERTIFICATE_VERIFY_FAILED)."
    echo "        python.org Python: open \"/Applications/Python $PYV/Install Certificates.command\", or"
    echo "        python3 -m pip install --user certifi && export SSL_CERT_FILE=\"\$(python3 -m certifi)\""
  fi
  [ -d "$USERBASE/bin" ] && case ":$PATH:" in *":$USERBASE/bin:"*) ;; *) warn "$USERBASE/bin is not on PATH (pip --user scripts)";; esac
fi

# ---------------------------------------------------------------------------------------------------------------
step "3. Logo tools (logo/)"
if [ "$DO_LOGO" = 0 ]; then
  echo "  skipped (--no-logo)"
else
  if [ "$CHECK" = 0 ] && command -v npm >/dev/null 2>&1 && [ -n "$PY" ]; then
    # logo/setup.sh calls a bare `pip`; give it this python3's pip so it works where only pip3 exists
    SHIM=$(mktemp -d "${TMPDIR:-/tmp}/vsetup.XXXXXX")
    printf '#!/bin/sh\nexec "%s" -m pip "$@"\n' "$PY" > "$SHIM/pip"; chmod +x "$SHIM/pip"
    echo "  running logo/setup.sh ..."
    if PATH="$SHIM:$PATH" bash "$REPO/logo/setup.sh"; then ok "logo/setup.sh finished"; else warn "logo/setup.sh failed (see above)"; fi
    rm -f "$SHIM/pip"; rmdir "$SHIM" 2>/dev/null
  fi
  [ -d logo/node_modules/three ] && ok "logo/node_modules/three" || miss "logo/node_modules/three (cd logo && npm ci)"
  [ -x logo/node_modules/.bin/gltf-transform ] && ok "logo/node_modules/.bin/gltf-transform" || miss "gltf-transform (cd logo && npm ci)"
  ls -d "$HOME/Library/Caches/ms-playwright"/chromium* >/dev/null 2>&1 && ok "Playwright Chromium" \
    || miss "Playwright Chromium (python3 -m playwright install chromium)"
  [ -x logo/srenv/bin/python ] && ok "logo/srenv (opencv-contrib for sr.py)" \
    || warn "logo/srenv missing: sr.py AI upscaling falls back to Lanczos (logo/setup.sh makes it)"
fi

# ---------------------------------------------------------------------------------------------------------------
step "4. Resources"
NF=$(ls resources/fonts/*.ttf resources/fonts/*.otf 2>/dev/null | wc -l | tr -d ' ')
[ "$NF" -gt 0 ] && ok "resources/fonts: $NF font files" || miss "resources/fonts has no fonts"
for m in EDSR_x4.pb FSRCNN_x4.pb; do
  [ -f "resources/models/$m" ] && ok "resources/models/$m" || warn "resources/models/$m missing (vectorize.py falls back to Lanczos)"
done

# ---------------------------------------------------------------------------------------------------------------
step "5. Shell lines for ~/.zprofile (add them yourself; this script changes no shell files)"
cat <<EOF
  export PATH="/opt/homebrew/bin:${USERBASE:-\$HOME/Library/Python/${PYV:-3.14}}/bin:\$PATH"   # native ffmpeg first; pip --user scripts
  export DYLD_FALLBACK_LIBRARY_PATH="/opt/homebrew/lib"   # cairocffi / cairosvg find Homebrew's libcairo
  # python.org Python only, if the CA warning above showed:  export SSL_CERT_FILE="\$(python3 -m certifi)"
  # export VIDEO_PROFILE=<name>    # or once per machine: python3 engine/vprofile.py default <name>
EOF

# ---------------------------------------------------------------------------------------------------------------
step "6. Profile"
if [ -n "${PY:-}" ]; then
  if [ -z "$PROFILE" ]; then
    PROFILE=$("$PY" engine/vprofile.py list 2>/dev/null | sed -n 's/^\* //p' | head -1)
  fi
  if [ -z "$PROFILE" ]; then
    warn "no default profile on this machine. Profiles: $("$PY" engine/vprofile.py list 2>/dev/null | tr -d ' *' | tr '\n' ' ')"
    echo "        Pick one: python3 engine/vprofile.py default <name>   (or make one: python3 engine/vprofile.py new <name>)"
  else
    echo "  python3 engine/vprofile.py show $PROFILE --check"
    POUT=$("$PY" engine/vprofile.py show "$PROFILE" --check 2>&1); PRC=$?
    printf '%s\n' "$POUT" | sed 's/^/    /'
    if [ "$PRC" = 0 ]; then ok "profile $PROFILE: every font and folder exists"
    else warn "profile $PROFILE: something above is missing (a network share that is not mounted shows up here)"; fi
  fi
fi

printf '\n== Result: %d missing, %d warnings\n' "$MISSING" "$WARNINGS"
[ "$MISSING" = 0 ]
