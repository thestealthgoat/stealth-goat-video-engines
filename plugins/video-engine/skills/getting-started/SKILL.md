---
name: getting-started
description: Sets up the open-source video engine for the first time and gives a ten-minute guided tour. Clones the engine from GitHub, runs setup.sh (macOS + Homebrew), sets VIDEO_ENGINE, builds the user's own brand profile (colors, OFL fonts, logo SVG) and checks it on a brand card, then renders a logo intro, a stats lower third, a QA run and an explainer on the demo profile, and ends with a map of which skill does what. Use when the user says "set up the video engine", "install the video engine", "get started with the video engine", "first time setup", "make a brand profile", "add my brand / colors / logo", "show me what this can do", "give me a tour", "where is the engine", or when another video skill finds $VIDEO_ENGINE unset or the engine folder missing.
---

# Getting started with the video engine

Take a new user from nothing to their first checked render: clone the engine, install its tools, make their brand
profile, run a short tour on the neutral `demo` profile, then show them which skill to ask for what. Work through the
steps in order, but skip any step that is already done (step 0 tells you which).

The engine folder is a clone of https://github.com/thestealthgoat/stealth-goat-video-engines (MIT). Every command
runs from it: `cd "$VIDEO_ENGINE" && python3 engine/<tool>.py ...`. Every tool that uses a brand takes
`--profile <name>`; without it, the tool uses `$VIDEO_PROFILE`, then the `default_profile` in the engine folder's
`local.json`.

## Ground rules (tell the user once, in plain words)

- Free and open-source tools by default. AI tools (for example an ElevenLabs voice) are fine when the user wants
  them, but never make a fake of a real person.
- Nothing is uploaded anywhere unless the user picks a service. Everything renders on this machine.
- Person cutouts use BiRefNet through rembg. The models download on first use into the folder `engine/models.py`
  picks (`$U2NET_HOME`, else `rembg_models` in `local.json`, else `resources/models/rembg` if it exists, else rembg's default folder).
- Every render goes through `engine/qa.py` (the video-gates skill) before it is shown or delivered.
- One heavy render at a time. Wait for a render to finish before starting the next.
- Ask before installing software, and before editing the user's shell files (`~/.zprofile`, `~/.zshrc`).

## 0. Find out what is already done

Run these and read the results before doing anything else:

```bash
echo "VIDEO_ENGINE=${VIDEO_ENGINE:-<unset>}  VIDEO_PROFILE=${VIDEO_PROFILE:-<unset>}"
[ -n "$VIDEO_ENGINE" ] && [ -x "$VIDEO_ENGINE/setup.sh" ] && echo "engine folder OK"
[ -n "$VIDEO_ENGINE" ] && cd "$VIDEO_ENGINE" && python3 engine/vprofile.py list   # * marks this machine's default
```

- `VIDEO_ENGINE` unset or the folder missing: ask the user whether they already have the engine somewhere (then use
  that folder) or want a fresh clone (step 1).
- Engine there but setup never run, or a tool fails on an import: step 2.
- Setup fine and only a brand is missing: step 4. "Show me what this can do": go straight to step 6.

## 1. Clone the engine

Default location `~/video-engine` (use another folder if the user names one):

```bash
git clone https://github.com/thestealthgoat/stealth-goat-video-engines.git ~/video-engine
cd ~/video-engine && ls
# cutouts/ docs/ engine/ examples/ logo/ plugins/ profiles/ resources/ skills/ tests/ vendor/ web/
# NOTICE.md README.md requirements.txt setup.sh
```

`profiles/` holds `_template` (the copy source for new profiles) and `demo` (the tour's profile: Anton and Barlow
Condensed with their OFL licenses beside them, and a sample logo PNG).

If git is missing, macOS offers to install the Command Line Tools on the first `git` call; let the user accept that
dialog themselves.

## 2. Install the tools with setup.sh

`setup.sh` is for macOS on Apple silicon with Homebrew. It is safe to run again: it installs only what is missing
and re-checks the rest. Tell the user what it installs and get a yes first:

1. Homebrew formulas: `ffmpeg imagemagick tesseract node cairo`.
2. Python packages: `python3 -m pip install --user -r requirements.txt` (numpy, scipy, Pillow, librosa, OpenCV
   headless, vtracer, cairosvg, scikit-learn, fontTools, Playwright, rembg + onnxruntime, faster-whisper, pyshp),
   then an import check of each.
3. `logo/setup.sh`: npm packages for the logo tools (`npm i` in `logo/`), then a second pip install of the logo
   tools' Python packages (vtracer, cairosvg, scikit-learn, OpenCV headless, Pillow, Playwright, fontTools). That
   pip line first tries `--break-system-packages` (an install into the system Python even where it is marked
   externally managed, errors hidden) and only falls back to `--user` if that fails; say so when asking for the yes.
   Then Playwright Chromium, a small venv `logo/srenv` for AI upscaling, and two super-resolution models (EDSR,
   FSRCNN, Apache-2.0, downloaded from GitHub) into `resources/models/`.
4. Warnings for known traps, the shell lines to add, and a profile check.

It never edits shell files. If Homebrew itself is missing, it stops and points at https://brew.sh: the user installs
Homebrew themselves (it asks for their Mac password).

```bash
cd "$VIDEO_ENGINE"            # or ~/video-engine before VIDEO_ENGINE is set
./setup.sh                    # install what is missing, then check
./setup.sh --check --profile demo              # installs nothing; reports
```

Read the `--check` output. Done means: no `MISS` lines, step 6 prints the profile block ending `CHECK: OK`, and
the last line is `== Result: 0 missing, N warnings` (exit code 0). The demo profile's working folders (under
`~/Movies/video-work`) are optional, so its check passes on a fresh machine before they exist.
Warnings are not failures, but explain each one; the common ones and their fixes are in
[references/setup-troubleshooting.md](references/setup-troubleshooting.md). Other `setup.sh` flags: `--no-brew`,
`--no-pip`, `--no-logo`, `--profile NAME`, `--help`.

Not on a Mac: say that `setup.sh` targets macOS + Homebrew and is untested elsewhere. The engine is Python + ffmpeg,
so offer the manual route from the troubleshooting reference, without promising it works.

## 3. Set VIDEO_ENGINE (and the shell lines setup.sh printed)

Every skill in this plugin finds the engine through `$VIDEO_ENGINE`. Show the user these lines (the PATH and DYLD
lines are the ones `setup.sh` printed under "Shell lines for ~/.zprofile"), and with their OK append them to
`~/.zprofile`:

```bash
export VIDEO_ENGINE="$HOME/video-engine"
export PATH="/opt/homebrew/bin:$PATH"                     # native Homebrew ffmpeg first (setup.sh prints the full line)
export DYLD_FALLBACK_LIBRARY_PATH="/opt/homebrew/lib"     # cairosvg finds Homebrew's libcairo
```

Then `source ~/.zprofile` (or open a new terminal). In this session, also `export` them in each command until the
shell picks them up.

## 4. Make the user's brand profile

A profile is one file, `profiles/<name>/profile.json`, copied from `profiles/_template/profile.json`. Ask the user
for: a short profile name (lowercase, no spaces, e.g. `acme`), the display name, two brand colors (primary = the
ground of panels and bars, accent = the edge and highlight color) as hex, a headline font and a body font, and
their logo as an SVG.

- Fonts: open-license (OFL) only, so renders can be shared. Several ship in `resources/fonts/` with their license
  texts (`ls resources/fonts`); any Google Fonts family is OFL too. If the user names a commercial font, say why it
  is a problem and offer the closest OFL face.
- Logo: an SVG. If they only have a JPG or PNG, use the logo-vectorize skill first. Tools that draw a raster logo
  (the stats card) read `brand.logo_png`, so add a transparent PNG as well when there is one.

```bash
cd "$VIDEO_ENGINE"
python3 engine/vprofile.py new acme --display "ACME Studio" --primary "#123456" --accent "#E04050" \
    --head-font resources/fonts/BebasNeue-Regular.ttf --body-font resources/fonts/BarlowCondensed-SemiBold.ttf \
    --logo ~/Desktop/acme-logo.svg --sample
python3 engine/vprofile.py show acme --check      # every font, folder and logo exists here: ends CHECK: OK
python3 engine/vprofile.py sample acme ~/Movies/video-work/acme_card.png    # the brand card, to look at
```

`new` copies the fonts and logo into `profiles/acme/assets/` and, with `--sample`, writes
`profiles/acme/sample_card.png`. Then open `profiles/acme/profile.json` and fill in what the flags do not cover
(`brand.colors.text`, `brand.logo_png`, `delivery` frame rate and loudness, `paths.root`). Every key, with sensible
values, is in [references/brand-profile.md](references/brand-profile.md). Fix anything `show --check` lists as
missing (a folder: `mkdir -p` it; a font or logo: correct the path).

Open the brand card and look at it with the user before anyone renders with the profile: the logo is drawn, every
color swatch shows its contrast, every font role renders (a font that fails is printed in red), and the sample lower
third says `text on primary N:1` with no `(below 4.5:1)` warning. If the contrast is low, suggest a darker primary or
a different text color.

## 5. Choose the default profile

Either one line per machine (writes `local.json` in the engine folder, never committed):

```bash
cd "$VIDEO_ENGINE" && python3 engine/vprofile.py default acme
```

or per shell: `export VIDEO_PROFILE=acme` in `~/.zprofile`. An explicit `--profile` on any command always wins.
Keep using `--profile demo` in the tour so the user's own brand stays untouched until they like it.

## 6. The ten-minute tour (demo profile)

Run these one at a time, in this order, and show the user each result before the next. The full script, with the
exact output names and what to point out, is in [references/tour.md](references/tour.md). Output goes to
`~/Movies/video-work/tour`.

```bash
cd "$VIDEO_ENGINE" && T="$HOME/Movies/video-work/tour" && mkdir -p "$T"
python3 engine/vprofile.py list        # check `demo` is listed (tour.md says what to do if it is not)
```

1. **Logo intro** (logo-motion skill). Write the sample ACME mark from tour.md to `$T/acme.svg`, look at three
   stills first, then render:
   ```bash
   python3 logo/motion.py "$T/acme.svg" "$T" ACME intro --profile demo --frames 0.3,2.0,3.9
   python3 logo/motion.py "$T/acme.svg" "$T" ACME intro --profile demo
   ```
   Writes `ACME_intro_Alpha.mov` (ProRes 4444 with alpha, for an editor) and `ACME_intro.mp4` (preview on the
   profile's primary color). Other templates: `outro`, `bug`, `stinger`, `presented`, `lockup`, `writeon`, `swap`,
   `shatter` and more (the logo-motion skill).
2. **Stats lower third** (motion-graphics skill), from the sample stats file that ships in `docs/`:
   ```bash
   python3 engine/statcard.py docs/stats_card_example.json "$T" --profile demo --name demo_card
   ```
   Writes `demo_card_stats_Alpha.mov`, `demo_card_stats.mp4` and `demo_card_stats.png`.
3. **QA run** (video-gates skill) on the card. A lower third is an overlay, so it is checked as `--kind loop`
   (the motion gates, without the hook and end-tail gates, which are listed as SKIP):
   ```bash
   python3 engine/qa.py "$T/demo_card_stats.mp4" --profile demo --kind loop --cuts none --out "$T/qa_card"
   ```
   Expect `RESULT: PASS (0 warnings)`, exit code 0. Open `$T/qa_card/review.md` and `$T/qa_card/sheet.jpg`
   together with the user: the verdict, the gate table, the manual checks. To show what a fix line looks like, tour.md
   section 3 then runs the same card as `--kind motion`, which honestly FAILS one gate (no strong moment by 2 s:
   the card's biggest move is about 8% of the frame), exit code 1, and the logo intro with its designed end hold
   declared. Never present a FAIL as a pass. Explain that every finished piece goes through this before anyone
   sees it.
4. **Explainer** (explain skill) from `examples/explain/lissajous/`: why some notes sound good together, drawn as
   Lissajous figures from the real waveforms. Read the docstring at the top of
   `examples/explain/lissajous/make.py` for its exact commands; the usual sequence is:
   ```bash
   python3 examples/explain/lissajous/make.py
   python3 engine/storyboard.py check examples/explain/lissajous/storyboard.json
   python3 engine/explain.py examples/explain/lissajous/storyboard.json --out "$T/liss" --name lissajous \
       --profile demo --board
   python3 engine/explain.py examples/explain/lissajous/storyboard.json --out "$T/liss" --name lissajous \
       --profile demo --music examples/explain/lissajous/_build/tones.wav
   python3 engine/qa.py "$T/liss/lissajous.mp4" --profile demo --kind explainer --out "$T/qa_liss"
   ```
   The board (`lissajous_board.jpg`) is the approval step before the full render. The full render takes about
   three minutes; its QA should end `RESULT: PASS`. The docstring adds `--music-db -10`; leave it out here, because
   with no voice-over the bed is the whole program and is leveled to the profile loudness anyway (explain.py's own
   help says `--music-db` then has no effect). `VO_SCRIPT.md` in the same folder is the voice-over script, for when
   the user wants to record their own voice.

Then re-run step 1 or 2 with `--profile <their name>` so they see their own brand on the same pieces.

## 7. Map: which skill does what, and how to ask

Finish by showing the map in [references/skill-map.md](references/skill-map.md) (one line a skill, with example
requests), and these habits for asking:

- Say what you want in plain words; no flags needed. "Make a 4-second logo intro from our logo", "cut the pauses
  out of this talk and caption it", "make an explainer on why a room echoes".
- Give the file: drag it in or say where it is. Give the brand once: "use the acme profile".
- Say where it will be shown (YouTube, a 9:16 reel, a live stream overlay) and roughly how long.
- Ask to see stills or a board first for anything long.
- Expect a QA review with each render; ask "why did it fail?" or "fix the QA notes" when it does.

## When something goes wrong

- A tool says `no profile given`: pass `--profile demo`, or do step 5.
- `profile 'x' not found`: `python3 engine/vprofile.py list` shows the names; a profile is a folder in `profiles/`.
- `CHECK: missing` on a `path` (the user's own profile; demo has none): create the folder (`mkdir -p`), or edit
  `paths.root` in the profile.
- `explain.py` stops before rendering with `--music <file>: no such file (for a topic pack, run its make.py first)`
  (or the same for `--vo`): usually `examples/explain/lissajous/_build/tones.wav` before `make.py` ran. Run `make.py`,
  then re-render.
- `motion.py` stops on a font: every profile font must load in the browser page; check the paths with
  `vprofile.py show <name> --check`.
- Import errors, ffmpeg problems, `CERTIFICATE_VERIFY_FAILED` on a model download, a cairo error: see
  [references/setup-troubleshooting.md](references/setup-troubleshooting.md), then `./setup.sh --check` again.
