# Getting started

Your first hour with the engine: install it, check it, render five real pieces on the bundled `demo` profile, read
the QA reviews, then make a brand profile of your own. Every command below was run on a fresh setup and shows the
output it should give.

If you use Claude, you can skip most of this page: install the plugin ([section 8](#8-use-it-with-claude)) and say
"set up the video engine". The `getting-started` skill does the same steps for you and explains each one.

## Contents

1. [Requirements](#1-requirements)
2. [Install](#2-install)
3. [Check the install](#3-check-the-install)
4. [The demo profile](#4-the-demo-profile)
5. [Five first renders](#5-five-first-renders)
6. [Read a QA review](#6-read-a-qa-review)
7. [Make your own profile](#7-make-your-own-profile)
8. [Use it with Claude](#8-use-it-with-claude)
9. [Troubleshooting](#9-troubleshooting)
10. [Where next](#10-where-next)

[Setup details](#setup-details): what `./setup.sh` installs, step by step.

## 1. Requirements

- **A Mac with Apple silicon** (M1 or newer). `setup.sh` is written and tested for macOS; on Linux the engine may
  work with a manual install (see [the setup reference](../plugins/video-engine/skills/getting-started/references/setup-troubleshooting.md#not-on-a-mac)),
  but that is unsupported.
- **[Homebrew](https://brew.sh).** If you do not have it, install it first; it asks for your Mac password.
  `setup.sh` never installs Homebrew for you.
- **Python 3.10 or newer.** The python.org installer is the easiest choice (Homebrew's Python refuses `pip --user`
  installs; see [troubleshooting](#9-troubleshooting)).
- **git.** macOS offers to install the Command Line Tools the first time you type `git`.
- **Disk space: about 3 GB** for the tools, plus 1-2 GB of models that download the first time you use person
  cutouts or transcription. Keep another 10 GB or so free for renders: ProRes alpha files are large.

What `setup.sh` installs (it only installs what is missing, and it is safe to run again):

| Step | What | Roughly |
|---|---|---|
| Homebrew formulas | `ffmpeg imagemagick tesseract node cairo` (and their dependencies) | 1 GB |
| Python packages | everything in [`requirements.txt`](../requirements.txt): numpy, scipy, Pillow, librosa, OpenCV (headless), vtracer, cairosvg, scikit-learn, fontTools, Playwright, rembg + onnxruntime, faster-whisper, pyshp | 1 GB |
| Logo tools (`logo/setup.sh`) | npm packages in `logo/` (three.js and friends), Playwright Chromium, a small Python venv `logo/srenv` for AI upscaling, two Apache-2.0 upscaling models into `resources/models/` | 0.8 GB |
| First use only | BiRefNet cutout models (rembg) and faster-whisper speech models; downloaded once, kept on your machine | 1-2 GB |

Nothing you render is uploaded anywhere. The only network traffic is installing the tools and these one-time model
downloads.

## 2. Install

```bash
git clone https://github.com/thestealthgoat/stealth-goat-video-engines.git ~/video-engine && cd ~/video-engine
./setup.sh
```

`setup.sh` runs in six steps (Homebrew, Python packages, logo tools, resources, shell lines, profile) and prints
`ok`, `MISS` or `WARN` for each item. It never edits your shell files. Instead, step 5 prints the lines to add.
Add them to `~/.zprofile` yourself, together with the engine folder:

```bash
# in ~/.zprofile
export VIDEO_ENGINE="$HOME/video-engine"                  # where the Claude plugins look for the engine
export PATH="/opt/homebrew/bin:$PATH"                     # use the line setup.sh printed: it also adds pip's script folder
export DYLD_FALLBACK_LIBRARY_PATH="/opt/homebrew/lib"     # lets cairosvg find Homebrew's cairo
```

Then open a new terminal, or run `source ~/.zprofile`.

Useful flags: `./setup.sh --no-brew`, `--no-pip` and `--no-logo` skip a step; `./setup.sh --help` lists them all.

## 3. Check the install

```bash
cd "$VIDEO_ENGINE"
./setup.sh --check --profile demo
```

`--check` installs nothing; it only reports. You are ready when:

- there are no `MISS` lines,
- step 6 (the profile check) ends with `CHECK: OK`,
- the last line reads `== Result: 0 missing, N warnings`, and the exit code is 0.

A `WARN` is not a failure, but read each one; the common ones are in [troubleshooting](#9-troubleshooting). The
`logo/srenv missing` and `rapidocr_onnxruntime ... (optional)` warnings are safe to ignore for now.

Optional, and slower: run the self-tests. Each prints PASS, FAIL or SKIP per case and writes only to `tests/out/`.

```bash
for t in tests/test_*.py; do python3 "$t" || echo "FAILED: $t"; done
```

## 4. The demo profile

Every tool that draws a brand reads it from a **profile**: one JSON file with colors, fonts, logo, working folders
and delivery specs (frame size, frame rate, loudness). The engine ships with two:

- `profiles/_template/` is the copy source for new profiles.
- `profiles/demo/` ("Demo Sports") is a neutral profile for trying things out: primary `#0B3D2E` (deep green),
  accent `#F2B705` (gold), Anton and Barlow Condensed (both OFL, with their licenses beside them), a drawn sample
  logo, and delivery at 1920x1080, 29.97 fps, -14 LUFS.

```bash
python3 engine/vprofile.py list                  # demo is listed
python3 engine/vprofile.py show demo --check     # every font and logo resolves: ends CHECK: OK
mkdir -p out/first-hour
python3 engine/vprofile.py sample demo out/first-hour/demo_card.png
open out/first-hour/demo_card.png
```

The brand card shows what a profile is: the display name in the headline face, the logo, one swatch per color with
its contrast, a specimen line per font, and a sample lower third with its `text on primary N:1` contrast.

The demo profile's working folders (under `~/Movies/video-work`) are marked optional, so `CHECK: OK` holds on a
fresh machine before they exist. Every command on this page passes `--profile demo`, so nothing depends on a
default being set.

## 5. Five first renders

Run these from the engine folder, one at a time: each render uses every core, so let one finish before starting the
next. Everything goes to `out/first-hour/`, which git ignores. Each piece follows the same rhythm: look at stills,
render, then run the QA gate.

```bash
cd "$VIDEO_ENGINE"
OUT=out/first-hour; mkdir -p "$OUT"
```

### 5.1 Logo intro (about 20 seconds)

Write a sample mark, a made-up "ACME" hexagon. Your own SVG logo works the same way.

```bash
cat > "$OUT/acme.svg" <<'EOF'
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 400">
  <polygon points="200,20 356,110 356,290 200,380 44,290 44,110" fill="#F2B705"/>
  <path d="M200 90 L310 310 H252 L230 262 H170 L148 310 H90 Z M200 160 L182 215 H218 Z" fill="#0B3D2E"/>
</svg>
EOF

python3 logo/motion.py "$OUT/acme.svg" "$OUT" ACME intro --profile demo --frames 0.3,2.0,3.9   # three stills first
python3 logo/motion.py "$OUT/acme.svg" "$OUT" ACME intro --profile demo                        # the 4-second render
open "$OUT/ACME_intro.mp4"
```

`--frames` writes only transparent stills (`ACME_intro_t0.30.png` and so on) in a few seconds; every motion tool
takes it, and it is the quickest way to check spelling, colors and fonts. The full render writes:

- `ACME_intro_Alpha.mov`: ProRes 4444 with alpha, to drop over footage in any editor,
- `ACME_intro.mp4`: a preview on the profile's primary color.

Swap `intro` for another template: `outro --text1 "THANKS FOR WATCHING" --text2 "SEE YOU NEXT WEEK"` (an end card),
`bug` (a corner bug), `stinger` (a short wipe), `writeon` (a pen tracing the logo), `lockup`, `swap`, `shatter` and
more. [`logo/README.md`](../logo/README.md) lists them all.

QA it. The intro settles at about 1.9 s and holds the finished logo to the end on purpose, so declare that hold
(`--holds end:2.2`, `--intended end_tail`). It renders at 60 fps while the demo profile delivers 29.97, so pass
`--fps 60`:

```bash
python3 engine/qa.py "$OUT/ACME_intro.mp4" --profile demo --kind motion --cuts none --fps 60 \
    --intended end_tail --holds end:2.2 --out "$OUT/qa_intro"
```

Expect `RESULT: PASS (0 warnings, 1 declared intended)`.

### 5.2 Stats lower third (about 15 seconds)

From the sample stats file in [`docs/stats_card_example.json`](stats_card_example.json):

```bash
python3 engine/statcard.py docs/stats_card_example.json "$OUT" --profile demo --name demo_card
python3 engine/qa.py "$OUT/demo_card_stats.mp4" --profile demo --kind loop --cuts none --out "$OUT/qa_card"
open "$OUT/demo_card_stats.mp4"
```

Writes `demo_card_stats_Alpha.mov` (alpha, full frame), `demo_card_stats.mp4` (preview) and `demo_card_stats.png`
(the settled card, transparent). The stats file is plain JSON: `num`, `name`, `big`, two to four `stats` pairs and an
optional `photo` cutout; copy it and fill in your own.

A lower third is an overlay with no opening or ending of its own, so it is checked as `--kind loop`. Expect
`RESULT: PASS (0 warnings)`, with the hook and end-tail gates listed as `SKIP`.

### 5.3 Explainer (about 4 minutes)

[`examples/explain/lissajous/`](../examples/explain/lissajous/) is a 40-second explainer on why some notes sound
good together, drawn as Lissajous figures from the real waveforms. The soundtrack is the same two tones.

```bash
python3 examples/explain/lissajous/make.py                                         # builds the tones and the scope data
python3 engine/storyboard.py check examples/explain/lissajous/storyboard.json       # 12 beats, 39.0 s ... CHECK: OK
python3 engine/explain.py examples/explain/lissajous/storyboard.json --out "$OUT/liss" --name lissajous \
    --profile demo --board                                                         # one still per beat
open "$OUT/liss/lissajous_board.jpg"
```

The board is the approval step: one still per beat with its words. Read it before spending minutes on a render.
Then render and check it:

```bash
python3 engine/explain.py examples/explain/lissajous/storyboard.json --out "$OUT/liss" --name lissajous \
    --profile demo --music examples/explain/lissajous/_build/tones.wav
python3 engine/qa.py "$OUT/liss/lissajous.mp4" --profile demo --kind explainer --out "$OUT/qa_liss"
```

The render takes about three minutes (1186 frames) and writes `lissajous.mp4` plus `lissajous.xml`, a Premiere
timeline with one clip and marker per beat. Expect `RESULT: PASS (0 warnings)`. `--kind explainer` adds the
freshness gate: something new on screen at least every 2.5 seconds. To narrate it yourself, record the lines in
[`VO_SCRIPT.md`](../examples/explain/lissajous/VO_SCRIPT.md); [`examples/README.md`](../examples/README.md) has the
voice-over commands.

### 5.4 A 3D card scene (about 1-2 minutes)

Glossy 3D bars and count-up score cards from [`examples/stage3d/sample_data.json`](../examples/stage3d/sample_data.json)
(made-up numbers for the fictional Harbor City Otters), built in three.js and rendered frame by frame:

```bash
python3 engine/stage3d.py data "$OUT/stage3d" Otters --data examples/stage3d/sample_data.json \
    --profile demo --fps 29.97 --frames 3.8                                        # one still
python3 engine/stage3d.py data "$OUT/stage3d" Otters --data examples/stage3d/sample_data.json \
    --profile demo --fps 29.97
open "$OUT/stage3d/Otters_data.mp4"
```

Pass `--fps 29.97`: stage3d renders at 30 fps unless told otherwise, and the QA spec gate fails a 30 fps file on a
29.97 profile. The render ends with a line like `hit at 0.980 s (qa: --cuts 0.980)`. Give that hint to QA:

```bash
python3 engine/qa.py "$OUT/stage3d/Otters_data.mp4" --profile demo --kind motion --cuts 0.980 --out "$OUT/qa_otters"
```

Expect `RESULT: PASS (1 warning)`. The warning, "planned cut not detected as a hard cut", is expected here: the
scene's hit is a camera move, not a hard cut. Look at that frame on the sheet to confirm it. Other scenes: `burst`,
`badge`, `extrude --text "ACME"`, `stack`, `orbit` and more (`python3 engine/stage3d.py --help`). Add `--alpha` for a
transparent `_Alpha.mov`.

### 5.5 A one-page website (under a minute)

[`examples/sites/demo-studio/site.json`](../examples/sites/demo-studio/site.json) is a 3D glass showcase for
Northlight Studio, a fictional architecture and interiors photographer;
[`demo-world`](../examples/sites/demo-world/site.json) is a 3D isometric scroll world. Build one, then run the compliance gate, which opens every page in a real browser:

```bash
python3 web/build.py examples/sites/demo-studio/site.json --out "$OUT/site" --profile demo
python3 web/compliance.py "$OUT/site" --site examples/sites/demo-studio/site.json
python3 -m http.server 8000 --directory "$OUT/site"           # then open http://localhost:8000 (Ctrl-C to stop)
```

Expect `compliance: PASS (0 fail, 4 for the owner)`. The report is written beside the site
(`out/first-hour/site_compliance.md`). The four "for the owner" lines are expected: the privacy, terms and
data-request pages are drafts until a person who has read them sets `legal.approved` in `site.json`, and a physical
address is needed only if the site sells online. For screenshots and a scroll video:
`python3 web/preview.py "$OUT/site" --out "$OUT/previews" --name demo-studio`.

## 6. Read a QA review

Every render goes through `engine/qa.py` (the video-gates check) before anyone sees it. One command writes one
folder:

| File | What it is |
|---|---|
| `review.md` | the verdict, the fix lines, the gate table, the shots, and a checklist of manual checks |
| `sheet.jpg` | a timeline and one frame per shot with the safe area drawn, plus evidence strips for the worst flags |
| `qa.json` | the same results for scripts |

The exit code is `0` for PASS, `1` for FAIL and `2` when the file could not be read.

**The verdict** is the last line in the terminal and the top of `review.md`: `RESULT: PASS (0 warnings)`,
`RESULT: PASS (1 warning)` or `RESULT: FAIL (1 fail, 1 warning)`. Only a printed `PASS` is a pass.

**The gate table** gives one row per check, each with what was measured and the target:

| Result | Meaning |
|---|---|
| `PASS` | measured and within target |
| `WARN` | worth a look by eye; does not fail the run |
| `FAIL` | must be fixed (or declared, below) before the piece is shown |
| `SKIP` | not run for this kind of piece (for example the hook gate on a `loop`), with the measurement still shown |
| `INFO` | a gate that failed but was declared intended with `--intended`; listed, never silently passed |

The gates: **spec** (size, frame rate, pixel format and audio against the profile), **motion** (dead stretches,
stutters), **flashes** and one-frame **pops**, **cuts** against the plan, **audio** and **loudness** (against the
profile's LUFS and true peak), **hook** (movement in the first 0.5 s, a strong moment by 2 s), **holds** (no still
over 0.8 s, an end tail of 1.5 s or less) and, for explainers, **freshness**.

**Fix lines** name the exact frames, the problem, why it matters and the fix:

```
f0-f287 (00:00.0) - 30.000 fps, profile delivers 29.970 - a rate conform at upload drops or repeats frames - render at 29.970 fps
```

**Pick the right `--kind`.** `edit` (the default) is footage cut to music; `motion` is a stand-alone graphic;
`explainer` adds the freshness gate; `loop` is an overlay or loop with no opening or ending (lower thirds, corner
bugs). Running the stats card as `--kind motion` instead of `loop` fails the hook gate, because the card's biggest
move is about 8% of the frame. That is a real result, and it does not apply to an overlay: the footage under it
carries the opening.

**Declare designed choices, never hide them.** `--holds end:2.2` marks an intentional still; `--intended end_tail`
(or `hook`) turns that gate's failure into an INFO line. Declare only what was designed, like the logo intro's end
hold.

**Then look.** The "Manual checks" in `review.md` are for a person: text inside the safe area (the cyan box on the
sheet), nothing over a face, readable at phone size. The loudness gate measures sound; someone still has to listen.

## 7. Make your own profile

You need a short name (lowercase, no spaces, such as `acme`), a display name, two colors (primary: the ground of
panels and bars; accent: edges and highlights), a headline font, a body font, and your logo as an SVG.

```bash
cd "$VIDEO_ENGINE"
python3 engine/vprofile.py new acme --display "ACME Studio" --primary "#123456" --accent "#E04050" \
    --head-font resources/fonts/BebasNeue-Regular.ttf --body-font resources/fonts/BarlowCondensed-SemiBold.ttf \
    --logo ~/Desktop/acme-logo.svg --sample
mkdir -p ~/Movies/video-work/Assets/Music        # the working folders the new profile points at
python3 engine/vprofile.py show acme --check     # ends CHECK: OK
open profiles/acme/sample_card.png
```

`new` copies the fonts and logo into `profiles/acme/assets/`, with each font's OFL license (`OFL-<Family>.txt`)
beside it, so the profile is self-contained (the website compliance gate checks for a license beside every font).
`--sample` writes the brand card. Check the card: the logo is drawn, every font specimen renders (a font that fails is printed
in red), and the lower third says `text on primary N:1` without a `(below 4.5:1)` warning. If the contrast is low,
choose a darker primary or a different text color.

Then open `profiles/acme/profile.json` and fill in what the flags do not cover: `brand.colors.text`,
`brand.logo_png` (a transparent PNG, used by the stats card and other raster tools), the `delivery` frame rate and
loudness, and `paths.root` for your working folders. Every key is explained in the
[brand profile reference](../plugins/video-engine/skills/getting-started/references/brand-profile.md); the profile API
for tool authors is in [`LAYOUT.md`](LAYOUT.md).

Some guidelines:

- **Fonts:** use open-license (SIL OFL) fonts so renders and project files can be shared. `resources/fonts/` has
  several with their license texts, and every Google Fonts family is OFL (use the static `.ttf` files and keep the
  license beside them).
- **Logo:** SVG with flat fills and text converted to outlines animates and extrudes best. Only have a JPG or PNG?
  `logo/vectorize.py` turns it into a clean SVG (see [`logo/README.md`](../logo/README.md)).
- **Make it the default** so you can drop `--profile`: `python3 engine/vprofile.py default acme` (writes
  `local.json` in the engine folder, which is never committed), or `export VIDEO_PROFILE=acme` in `~/.zprofile`. An
  explicit `--profile` always wins.

Now re-run 5.1 or 5.2 with `--profile acme` and the same pieces come out in your brand.

## 8. Use it with Claude

The repo is also a Claude plugin marketplace with two plugins. You describe what you want in plain words, and the
skills run these same tools, show you stills or a board first, and QA every render before handing it over.

**Claude Code:**

```
/plugin marketplace add thestealthgoat/stealth-goat-video-engines
/plugin install video-engine@stealth-goat
/plugin install ui-kit@stealth-goat
```

**Claude desktop app:** open `plugins/dist/video-engine.plugin` (and `ui-kit.plugin`) from your clone and press
Install.

The video-engine skills and the website skill find the engine through `$VIDEO_ENGINE`. If it is not set, the
`getting-started` skill offers to clone and set it up. Things to say:

| Say | Skill |
|---|---|
| "set up the video engine", "make a brand profile", "show me what this can do" | getting-started |
| "make a 4-second logo intro from our logo", "end card that says thanks for watching" | logo-motion |
| "stats lower third for number 12", "3D bar chart of these numbers", "quote card from this clip" | motion-graphics |
| "make an explainer on why a room echoes" | explain |
| "cut the pauses out of this talk and caption it", "make a vertical version" | video |
| "QA this render", "why did it fail?", "fix the QA notes" | video-gates |
| "turn this JPG logo into an SVG", "3D version of our logo" | logo-vectorize, logo-3d |
| "cut the speaker out of this clip", "put the title behind me" | matte |
| "build a website for my studio", "make our app's colors accessible" | website, ui-kit (ui-kit plugin) |

Give it the file (drag it in or say where it is), name the brand once ("use the acme profile"), and say where the
piece will be shown and roughly how long. The full map is in
[`skill-map.md`](../plugins/video-engine/skills/getting-started/references/skill-map.md), and the plugin pages are
[`plugins/video-engine/README.md`](../plugins/video-engine/README.md) and
[`plugins/ui-kit/README.md`](../plugins/ui-kit/README.md).

## 9. Troubleshooting

The eight problems people hit most often in the first hour. After any fix, run `./setup.sh --check` again. More
lines and their fixes are in the [setup reference](../plugins/video-engine/skills/getting-started/references/setup-troubleshooting.md).

**1. `MISS Homebrew is not installed`.** Install Homebrew from [brew.sh](https://brew.sh) (it asks for your
password), then run `./setup.sh` again.

**2. pip says `externally-managed-environment`.** Homebrew's Python refuses `--user` installs. Use the python.org
Python, or a virtual environment: `python3 -m venv ~/.venvs/video && . ~/.venvs/video/bin/activate`, then
`./setup.sh` again (inside a venv it installs without `--user`). Activate the venv in every new terminal.

**3. `no profile given: pass --profile <name>, set VIDEO_PROFILE, or run ...`.** A fresh clone has no default
profile. Pass `--profile demo`, or set one with `python3 engine/vprofile.py default <name>`. For
`profile 'x' not found`, run `python3 engine/vprofile.py list`: a profile is a folder in `profiles/`.

**4. `CHECK: missing` with `path root` (or `assets`, `music`).** Your profile points at working folders that do not
exist yet. Create them (`mkdir -p ~/Movies/video-work/Assets/Music`), or change `paths.root` in the profile. A wrong
font or logo path shows here too: correct it in `profile.json`.

**5. `logo not drawn: no library called "cairo-2" was found`, or `MISS import cairosvg`.** cairosvg cannot find
Homebrew's cairo. Add `export DYLD_FALLBACK_LIBRARY_PATH="/opt/homebrew/lib"` to `~/.zprofile` and open a new
terminal. (The logo tools set it themselves; `vprofile.py` and others need it from your shell.)

**6. QA fails `integrity and spec` on the frame rate (`30.000 fps, profile delivers 29.970`).** The render's rate
does not match the profile. Render at the delivery rate (`--fps 29.97` on `engine/stage3d.py`, which defaults to
30), or tell QA the rate you meant (`--fps 60` for `logo/motion.py`, which renders 60 fps by default).

**7. `explain.py` stops with `--music ...: no such file (for a topic pack, run its make.py first)`.** The example's
generated files are not built yet. Run `python3 examples/explain/lissajous/make.py`, then render again.

**8. `CERTIFICATE_VERIFY_FAILED` on a first-use model download, or `WARN this Python has no CA certificates`.**
With the python.org Python, open `/Applications/Python 3.x/Install Certificates.command`. Otherwise:
`python3 -m pip install --user certifi && export SSL_CERT_FILE="$(python3 -m certifi)"`.

Also common, and quick:

- `WARN ffmpeg on PATH is ... not /opt/homebrew/bin/ffmpeg`: put `/opt/homebrew/bin` first in `PATH` (the step 5
  line). Old non-native ffmpeg builds can stall at 100% CPU; see [`ffmpeg-notes.md`](ffmpeg-notes.md).
- `WARN more than one OpenCV wheel installed`: run the two commands `setup.sh` prints; keep only
  `opencv-python-headless`.
- `MISS Playwright Chromium`: `python3 -m playwright install chromium`.
- A render seems stuck: check that no other render is running. Run one heavy render at a time.

## 10. Where next

- [`examples/README.md`](../examples/README.md): the examples with every option, including your own voice-over on
  the explainer and the second demo site.
- [`TOOLS.md`](TOOLS.md): every tool, what it takes and what it writes.
- [`logo/README.md`](../logo/README.md): vectorizing, 3D logos and the full template library.
- [`cutouts/README.md`](../cutouts/README.md): transparent person cutouts from photos.
- [`LAYOUT.md`](LAYOUT.md): profiles and the profile API, for tool authors.
- [`NOTICE.md`](../NOTICE.md): third-party credits and licenses.

## Setup details

What `./setup.sh` does, in order (it only installs what is missing, so it is safe to run again):

1. Homebrew formulas: `ffmpeg imagemagick tesseract node cairo`. Then it checks the ffmpeg on `PATH` (a warning
   when it is not the native `/opt/homebrew/bin/ffmpeg`), its encoders and filters, and `ffprobe`, `tesseract`,
   `magick` and `node`.
2. Python packages: `python3 -m pip install --user -r requirements.txt` (inside a virtual environment, without
   `--user`), then an import check of every module. This step also prints the warnings for known Python traps: more
   than one OpenCV wheel installed, an OpenCV and PyAV library clash, a Python with no CA certificates, and pip's
   script folder not on `PATH`. Each one and its fix is in [troubleshooting](#9-troubleshooting).
3. Logo tools, `logo/setup.sh`: the npm packages in `logo/`, a pip install of the logo tools' Python packages (it
   tries `--break-system-packages` first and falls back to `--user`), Playwright Chromium, the small venv
   `logo/srenv` for AI upscaling, and two upscaling models into `resources/models/`.
4. Resources: fonts in `resources/fonts/`, and the two upscaling models in `resources/models/` (a warning when one
   is missing: `vectorize.py` then falls back to Lanczos).
5. The shell lines to add to `~/.zprofile` (it never edits your shell files).
6. A profile check: `python3 engine/vprofile.py show <profile> --check`.

Flags: `--check` (install nothing, only report), `--no-brew`, `--no-pip`, `--no-logo` (skip a step) and
`--profile NAME` (the profile to check at the end; default `$VIDEO_PROFILE`, then `local.json`). The exit code is 0
when every required piece is there.
