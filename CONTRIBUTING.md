# Contributing

Thanks for helping. This is a small, code-first video engine: plain Python, ffmpeg, a headless browser for the
graphics, and a QA gate in front of every render. The rules below keep it portable (any team, any brand) and keep
every render checkable.

- [Set up](#set-up)
- [How the code is written](#how-the-code-is-written)
- [Tests](#tests)
- [QA every render](#qa-every-render)
- [Third-party code and licenses](#third-party-code-and-licenses)
- [Proposing a template](#proposing-a-template)
- [Adding a skill to a Claude plugin](#adding-a-skill-to-a-claude-plugin)
- [Pull requests](#pull-requests)

## Set up

macOS on Apple silicon with Homebrew is the tested platform (`setup.sh` targets it). Elsewhere, install ffmpeg,
Python 3, Node, ImageMagick, tesseract and cairo yourself, then `python3 -m pip install --user -r requirements.txt`
and `logo/setup.sh`; other platforms are untested.

```bash
git clone https://github.com/thestealthgoat/stealth-goat-video-engines.git ~/video-engine && cd ~/video-engine
./setup.sh --check     # report only: what is installed, what is missing
./setup.sh             # install what is missing (Homebrew formulas, pip packages, logo/setup.sh), then check again
export VIDEO_ENGINE="$HOME/video-engine"
```

`setup.sh` ends with `== Result: 0 missing, N warnings` when every required piece is there (exit code 0). It prints
the shell lines to add to `~/.zprofile` (native ffmpeg first in `PATH`, `DYLD_FALLBACK_LIBRARY_PATH` for cairosvg);
it changes no shell files itself. See `./setup.sh --help` for its options.

Use the neutral `demo` profile for everything you try or test:

```bash
python3 engine/vprofile.py list
python3 engine/vprofile.py show demo --check
```

The [README](README.md) has the quick start and the profile format, and [examples/](examples/README.md) has ready
inputs that render on `demo`.

## How the code is written

- **Plain Python 3 + ffmpeg.** Standard library first (`argparse`, `subprocess`, `json`), then the packages already in
  `requirements.txt`. A new dependency needs a reason in the pull request, a lower bound and a "tested" note in
  `requirements.txt`, and must be free and open-source. Browser-drawn graphics use the existing pages
  (`logo/motion.html`, `engine/explain.html`, `engine/stage3d.html`) driven by Playwright.
- **ffmpeg calls:** pass `-nostdin`, bound every `apad` (`apad=whole_dur=<s>`), and read the traps in
  [docs/ffmpeg-notes.md](docs/ffmpeg-notes.md) before writing a filter graph.
- **Every tool is a command-line script.** A module docstring that starts with the usage line, `--help` that works
  with no other arguments, exit code 0 on success and non-zero on failure.
- **Motion moves on springs.** Anything animated uses `engine/spring.py` (Python) or `engine/spring.js` (browser),
  closed-form and seekable by time, so frame `t` is a pure function of `t`. No hand-tuned easing curves, no state
  carried between frames. Pick a preset (`snappy`, `bouncy`, `slam`, `smooth`, `gentle`, and `ui` / `uiExit` for
  interface motion) or set `zeta` / `omega`. See [engine/README_motion.md](engine/README_motion.md).
  `logo/spring.js` is a byte copy of `engine/spring.js`: change both or neither (`tests/test_spring.py` checks).
- **Audio:** every cut, start and end fades its audio. No hard audio cuts.
- **No organization's values in `engine/`, `logo/`, `cutouts/` or `web/`.** Colors, fonts, logos, names, folders and
  delivery specs come from a **profile** (`profiles/<name>/profile.json`), the command line, or `__file__`. Never an
  absolute path. Load one with `vprofile.add_arg(ap)` and `vprofile.load(a.profile)`; read optional values with
  `P.get("some.key", <default>)` and add the new key to `profiles/_template/profile.json`. An explicit flag always
  beats the profile. The full API is in [docs/LAYOUT.md](docs/LAYOUT.md).
- **Source media is read-only.** Tools write only into the output folder they are given. Nothing is deleted:
  superseded renders move to `_old/`.
- **Examples use placeholders only:** the `demo` profile, ACME, Jane Doe, the Harbor City Otters, `hello@example.com`.
  No real people, teams, clients or places, and no personal paths, in code, comments, tests or docs.

## Tests

Every change to a tool comes with a test, or an update to its existing test, in `tests/`:

- **Synthetic input only.** Build what the test needs in code (a generated tone, a drawn cutout, a few frames made
  with ffmpeg's `lavfi` sources). No downloads, no network share, no real footage or photos of people.
- Use `profiles/_template` or `profiles/demo`, or a profile written into a temp folder and passed with
  `VIDEO_PROFILE`.
- Print one `PASS <case>` or `FAIL <case>` line per case (`SKIP` when an optional dependency is missing), write output
  only under `tests/out/<tool>/` or a temp folder, and exit 1 on any failure. `tests/test_statcard.py` is a short
  example to copy.

Run the tests for what you touched, then the whole set:

```bash
python3 tests/test_spring.py                                    # one test
for t in tests/test_*.py; do python3 "$t" || echo "FAILED: $t"; done   # all of them
```

They need `ffmpeg`, `node` and the packages in `requirements.txt`. Optional real-music case for the QA test:
`QA_TEST_MUSIC=<a music file> python3 tests/test_qa.py`.

## QA every render

Nothing is shown or shipped without `engine/qa.py`. If your change affects what a tool renders, render it on the
`demo` profile and put the result through the gate:

```bash
python3 engine/qa.py out/piece.mp4 --profile demo --kind motion --out out/piece_qa   # edit | motion | explainer | loop
```

`--kind loop` is for corner bugs, lower thirds and other loops; add `--cuts 1.5,4.2` or `--cuts none` when the piece
has planned cuts. It writes `review.md`, `sheet.jpg` and `qa.json` into `--out` and exits 0 on PASS, 1 on FAIL. Read
the review sheet as well: a PASS cannot see overlapping text or a graphic that glitches for three frames. The full
review process is the video-gates skill ([skills/video-gates/SKILL.md](skills/video-gates/SKILL.md)). Say in the pull
request which `qa.py` command you ran and its result line.

## Third-party code and licenses

- The engine is MIT. Only bring in code under a license compatible with that (MIT, BSD, Apache-2.0, ISC, public
  domain), and keep its copyright notice.
- **Never copy AGPL, GPL or unlicensed code**, including code from a repository with no license file, a forum post, or
  a tutorial without a stated license. Reading it for the idea is fine; write your own implementation.
- Credit every third-party file, model, dataset or font in [NOTICE.md](NOTICE.md): name, source URL, license, and
  whether it is unchanged or modified. Unchanged copies go in `vendor/<name>/` with their `LICENSE`. A modified copy
  keeps the original notice in its header and lists the changes in its docstring (`engine/beatmap.py` shows how).
- Fonts must be OFL or similar, with the license text beside the font file.
- Models are downloaded at setup or first use, never committed.

## Proposing a template

A template is a reusable look: a logo animation in `logo/motion.html` (`intro`, `writeon`, `shatter`, ...), a 3D scene
in `engine/stage3d.html`, or a website hero in `web/templates/`.

1. Open a feature request and pick "New template". Describe the look in words, give its length and aspect ratios,
   and list its inputs (SVG, text lines, images) and the profile values it reads. A link to a public reference is
   fine; don't attach footage you don't own.
2. Once it is agreed, build it on the existing pieces: the browser-measured SVG outlines and `spring.js` for logo
   templates (register it in the `TEMPLATES` table in `logo/motion.html`; `logo/motion.py` passes the name through),
   the `SCENES` list in `engine/stage3d.py` for 3D scenes, or a `web/templates/wN.py` module with a `build(ctx)`
   function for sites.
3. Every color and font comes from the profile. It must render on `demo` and on `profiles/_template`.
4. Show it: a few stills (`--frames 0.5,1.5,3`) and the full render's `qa.py` result (`--kind motion`, or `--kind loop`
   for loops). For a site, run `web/compliance.py` on the built folder. Add a usage line to the tool's docstring and
   its README.

## Adding a skill to a Claude plugin

The Claude plugins live in `plugins/`: `plugins/video-engine/` and `plugins/ui-kit/`, each with
`.claude-plugin/plugin.json`, a `README.md` and `skills/<name>/`. The repo root's `.claude-plugin/marketplace.json`
lists both plugins.

1. Make `plugins/<plugin>/skills/<skill-name>/SKILL.md` with YAML front matter:

   ```markdown
   ---
   name: skill-name
   description: What it makes, which engine tools it runs, and the phrases a user says when they want it.
   ---
   ```

   Put long material in `references/` and helper scripts in `scripts/` beside it, as the existing skills do.
2. Start the skill by finding the engine (`$VIDEO_ENGINE`, else ask, else point to the `getting-started` skill) and
   the profile (`--profile <name>`, defaulting to `demo` for a try). Run every command from `$VIDEO_ENGINE`.
3. Check every command and flag in the skill against the real tool (`python3 engine/<tool>.py --help` and its code)
   on a fresh clone. A skill that names a flag that doesn't exist is a bug.
4. End with the QA step for anything it renders (the `video-gates` skill).
5. Add the skill to the table in the plugin's `README.md`. If it changes what the plugin does, bump `version` in
   `plugin.json` and update its `description`.
6. Rebuild the desktop-app package: `plugins/dist/<plugin>.plugin` is a zip of the plugin folder's contents:

   ```bash
   cd plugins/video-engine && rm -f ../dist/video-engine.plugin && zip -r ../dist/video-engine.plugin . -x '*.DS_Store'
   ```

Skills follow the same privacy rule as the code: generic wording and placeholder names only. Skills never make a
fake of a real person.

## Pull requests

- One change per pull request, with a short description of what and why.
- Run the relevant tests and `qa.py` for anything that renders; paste the result lines into the template.
- Update the docs your change touches (the tool's docstring, the README tables, [CHANGELOG.md](CHANGELOG.md) under
  "Unreleased").
- Bugs and ideas: use the issue templates. Include the exact command, `./setup.sh --check` output and, for render
  problems, the `review.md` from `qa.py`.
