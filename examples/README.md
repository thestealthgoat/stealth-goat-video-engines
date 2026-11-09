# Examples

Ready-made inputs for trying the engine with the neutral `demo` profile. Everything here is generic: ACME TV and
Jane Doe Studio are made up, and every contact is `hello@example.com`.

Set up the engine once, then run every command below from the engine folder (your clone of the repo).
`setup.sh` targets macOS with Homebrew; `./setup.sh --check` only reports what is missing.

```bash
git clone https://github.com/thestealthgoat/stealth-goat-video-engines
cd stealth-goat-video-engines
./setup.sh                      # ffmpeg, Python packages, the npm packages and Playwright Chromium (logo/setup.sh)
export VIDEO_ENGINE="$PWD"      # the engine folder; the Claude plugins look for it here
```

Already set up? `cd "$VIDEO_ENGINE"`. Everything is written under `out/`, which git ignores.

| Example | What it is | Tool |
| --- | --- | --- |
| `explain/lissajous/` | "Why some notes sound good together": a 40-second explainer that draws musical intervals as Lissajous figures on an XY scope, with the two real tones as its soundtrack | `engine/explain.py` |
| `sites/demo-world/site.json` | W2 template: a 3D isometric scroll world, "How a live stream reaches you" for a fictional ACME TV | `web/build.py` |
| `sites/demo-studio/site.json` | W5 template: a 3D glass showcase for a fictional Jane Doe Studio | `web/build.py` |

## Explainer: `explain/lissajous/`

Files: `make.py` (builds the storyboard, the tones and the scope data), `storyboard.json` (its output, checked in so you
can read it), `VO_SCRIPT.md` (the lines to record if you want your own voice on it). `make.py` writes its generated
files to `explain/lissajous/_build/` (ignored by git), so run it once before rendering:

```bash
python3 examples/explain/lissajous/make.py
python3 engine/storyboard.py check examples/explain/lissajous/storyboard.json     # CHECK: OK
python3 engine/explain.py examples/explain/lissajous/storyboard.json --out out/lissajous --profile demo --frames 2.0,12.0
python3 engine/explain.py examples/explain/lissajous/storyboard.json --out out/lissajous --profile demo \
    --music examples/explain/lissajous/_build/tones.wav
```

The `--frames` line writes two stills only (`out/lissajous/storyboard_t2.00.png` and `_t12.00.png`, a quick look). The
last line renders the full video, about 40 s (`out/lissajous/storyboard.mp4`, plus `storyboard.xml` for Premiere); it
takes a few minutes. With no voice-over the two tones are the whole soundtrack and are levelled to the profile's
delivery loudness, so `--music-db` has no effect here. QA the render (the video-gates skill) before you share it:

```bash
python3 engine/qa.py out/lissajous/storyboard.mp4 --profile demo --kind explainer --out out/lissajous/qa
```

It should end `RESULT: PASS (0 warnings)`; the review sheet is `out/lissajous/qa/review.md`.

With your own voice-over: record the lines in `VO_SCRIPT.md`, save the file as `examples/explain/lissajous/vo.wav`, then

```bash
python3 engine/storyboard.py retime examples/explain/lissajous/storyboard.json --vo examples/explain/lissajous/vo.wav
python3 examples/explain/lissajous/make.py
python3 engine/storyboard.py check examples/explain/lissajous/storyboard.json     # check again: your timing now
python3 engine/explain.py examples/explain/lissajous/storyboard.json --out out/lissajous --profile demo \
    --vo examples/explain/lissajous/vo.wav --music examples/explain/lissajous/_build/tones.wav --music-db -10
python3 engine/qa.py out/lissajous/storyboard.mp4 --profile demo --kind explainer --out out/lissajous/qa
```

`retime` transcribes the recording on your machine (faster-whisper; the first run downloads its model) and writes `vo.words.json` beside it; `make.py`
then times the beats, tones and scope to your words. Here `--music-db -10` keeps the tones (what the scope draws)
audible under the voice. If the second `check` fails (a gap over 2.5 s with no new visual, or a beat at an impossible
words per second), the transcript has usually dropped or merged words: compare `vo.words.json` with the script, then
re-record that part more slowly, with a short pause between lines. Your `vo.*` files stay out of git.

## Websites: `sites/demo-world/` and `sites/demo-studio/`

Build to a folder outside the example, then run the compliance gate on the built site (it opens the pages in a real
browser):

```bash
python3 web/build.py examples/sites/demo-world/site.json --out out/sites/demo-world --profile demo
python3 web/compliance.py out/sites/demo-world --site examples/sites/demo-world/site.json

python3 web/build.py examples/sites/demo-studio/site.json --out out/sites/demo-studio --profile demo
python3 web/compliance.py out/sites/demo-studio --site examples/sites/demo-studio/site.json

python3 web/preview.py out/sites/demo-world --out out/sites/previews --name demo-world   # optional: screenshots, scroll video
```

`build.py` needs the npm packages from `./setup.sh`; `compliance.py` and `preview.py` open the pages in Playwright
Chromium. Each gate should end `compliance: PASS (0 fail, 4 for the owner)`. The report is written beside the built
folder (`out/sites/demo-world_compliance.md`), never inside it. Its four "Needs the owner" lines are expected: the three
DRAFT legal pages (privacy, terms, data request), because `legal.approved` is deliberately not set in these examples
(only a person who has read the privacy policy and terms should set it), and a note that a physical address is needed
only if the site sells online. The `--name` sets the preview file names (`demo-world_desktop.jpg`, `_phone.jpg`,
`_laptop.jpg`, `_scroll.mp4`); without it they are `site_*` and a second site would overwrite the first.

To make your own site, copy one of these folders, change `profile` to your own profile, and replace every piece of
text, the `business` details and the contact address. If your profile's fonts are your own files, put each font's
licence (for example `OFL-<Family>.txt`) beside it, or the gate fails on the font licence.
