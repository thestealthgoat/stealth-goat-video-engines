# Examples

Ready-made inputs for trying the engine end to end with the bundled `demo` profile: a 40-second explainer, two
one-page websites and a 3D data scene. Everything here is generic and made up: ACME TV, Northlight Studio and the Harbor
City Otters are fictional, and every contact is `hello@example.com`. Part of the
[Stealth Goat video engines](../README.md); see [docs/TOOLS.md](../docs/TOOLS.md) for every tool in the repo.

## Quick start

Set up the engine once (`setup.sh` targets macOS with Homebrew; `./setup.sh --check` only reports what is missing):

```bash
git clone https://github.com/thestealthgoat/stealth-goat-video-engines.git ~/video-engine && cd ~/video-engine
./setup.sh                      # ffmpeg, Python packages, the npm packages and Playwright Chromium (logo/setup.sh)
export VIDEO_ENGINE="$HOME/video-engine"      # the engine folder; the Claude plugins look for it here
```

Then try one example from each family. Run every command from the engine folder (`cd "$VIDEO_ENGINE"`); everything
is written under `out/`, which git ignores.

```bash
# Explainer: two stills from the storyboard (seconds)
python3 examples/explain/lissajous/make.py
python3 engine/explain.py examples/explain/lissajous/storyboard.json --out out/lissajous --profile demo --frames 2.0,12.0

# Website: build it, then run the compliance gate in a real browser
python3 web/build.py examples/sites/demo-world/site.json --out out/sites/demo-world --profile demo
python3 web/compliance.py out/sites/demo-world --site examples/sites/demo-world/site.json

# 3D data scene: one still
python3 engine/stage3d.py data out/stage3d Otters --data examples/stage3d/sample_data.json --profile demo --frames 3.8
```

## What is here

| Example | What it is | Tool |
| --- | --- | --- |
| `explain/lissajous/` | "Why some notes sound good together": a 40-second explainer that draws musical intervals as Lissajous figures on an XY scope, with the two real tones as its soundtrack | `engine/explain.py` |
| `sites/demo-world/site.json` | W2 template: a 3D isometric scroll world, "How a live stream reaches you", for a fictional ACME TV | `web/build.py` |
| `sites/demo-studio/site.json` | W5 template: a 3D glass showcase for Northlight Studio, a fictional architecture and interiors photographer | `web/build.py` |
| `stage3d/sample_data.json` | data for the 3D `data` scene: a bar chart and three count-up cards for the fictional Harbor City Otters | `engine/stage3d.py` |

## Explainer: `explain/lissajous/`

Files: `make.py` (builds the storyboard, the tones and the scope data), `storyboard.json` (its output, checked in so
you can read it) and `VO_SCRIPT.md` (the lines to record if you want your own voice on it). `make.py` writes its
generated files to `explain/lissajous/_build/` (ignored by git), so run it once before rendering:

```bash
python3 examples/explain/lissajous/make.py
python3 engine/storyboard.py check examples/explain/lissajous/storyboard.json     # CHECK: OK
python3 engine/explain.py examples/explain/lissajous/storyboard.json --out out/lissajous --profile demo --frames 2.0,12.0
python3 engine/explain.py examples/explain/lissajous/storyboard.json --out out/lissajous --profile demo \
    --music examples/explain/lissajous/_build/tones.wav
```

The `--frames` line writes two stills only (`out/lissajous/storyboard_t2.00.png` and `storyboard_t12.00.png`), a
quick look. The last line renders the full video, about 40 s long (`out/lissajous/storyboard.mp4`, plus
`storyboard.xml` for Premiere); it takes a few minutes. With no voice-over the two tones are the whole soundtrack and
are leveled to the profile's delivery loudness, so `--music-db` has no effect here. Check the render with the QA gate
(the [video-gates skill](../plugins/video-engine/skills/video-gates/SKILL.md)) before you share it:

```bash
python3 engine/qa.py out/lissajous/storyboard.mp4 --profile demo --kind explainer --out out/lissajous/qa
```

It should end `RESULT: PASS (0 warnings)`; the review sheet is `out/lissajous/qa/review.md`.

### With your own voice-over

Record the lines in `VO_SCRIPT.md`, save the file as `examples/explain/lissajous/vo.wav`, then:

```bash
python3 engine/storyboard.py retime examples/explain/lissajous/storyboard.json --vo examples/explain/lissajous/vo.wav
python3 examples/explain/lissajous/make.py
python3 engine/storyboard.py check examples/explain/lissajous/storyboard.json     # check again: your timing now
python3 engine/explain.py examples/explain/lissajous/storyboard.json --out out/lissajous --profile demo \
    --vo examples/explain/lissajous/vo.wav --music examples/explain/lissajous/_build/tones.wav --music-db -10
python3 engine/qa.py out/lissajous/storyboard.mp4 --profile demo --kind explainer --out out/lissajous/qa
```

`retime` transcribes the recording on your machine (faster-whisper; the first run downloads its model) and writes
`vo.words.json` beside it; `make.py` then times the beats, tones and scope to your words. Here `--music-db -10` keeps
the tones (what the scope draws) audible under the voice. If the second `check` fails (a gap over 2.5 s with no new
visual, or a beat at an impossible number of words per second), the transcript has usually dropped or merged words:
compare `vo.words.json` with the script, then re-record that part more slowly, with a short pause between lines. Your
`vo.*` files stay out of git.

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
folder (`out/sites/demo-world_compliance.md`), never inside it. Its four "Needs the owner" lines are expected:

- three for the DRAFT legal pages (privacy, terms, data request), because `legal.approved` is deliberately not set in
  these examples (only a person who has read the privacy policy and terms should set it);
- one noting that a physical address is needed only if the site sells online.

`--name` sets the preview file names (`demo-world_desktop.jpg`, `_phone.jpg`, `_laptop.jpg`, `_scroll.mp4`); without
it they are `site_*` and a second site would overwrite the first.

To make your own site, copy one of these folders, change `profile` to your own profile, and replace every piece of
text, the `business` details and the contact address. If your profile's fonts are your own files, put each font's
license (for example `OFL-<Family>.txt`) beside it, or the gate fails on the font license.

## 3D data scene: `stage3d/sample_data.json`

Sections play in order: `bars` (label and value), `cards` (two to four count-up score cards, each with an optional
note) and `points` (a point cloud or map). The camera never stops: a gentle dolly with hand-held drift that travels
from section to section.

```bash
python3 engine/stage3d.py data out/stage3d Otters --data examples/stage3d/sample_data.json --profile demo --frames 3.8   # one still
python3 engine/stage3d.py data out/stage3d Otters --data examples/stage3d/sample_data.json --profile demo --fps 29.97   # the full scene
python3 engine/qa.py out/stage3d/Otters_data.mp4 --profile demo --kind motion --cuts 0.980 --out out/stage3d/qa
```

The still is `out/stage3d/Otters_data_t3.80.png`. Pass `--fps 29.97` on the full render: stage3d renders at 30 fps
unless told otherwise, and the QA spec gate fails a 30 fps file on the 29.97 fps demo profile. The render prints the
hit time to give QA (`hit at 0.980 s (qa: --cuts 0.980)`). Expect `RESULT: PASS (1 warning)`: the warning ("planned
cut not detected as a hard cut") is expected, because the hit is a camera move, not a hard cut. Change the numbers in
a copy of the JSON to make your own; every number in the sample is made up.

## See also

- [Root README](../README.md): install, profiles and the tour of the engine.
- [docs/TOOLS.md](../docs/TOOLS.md): every tool in the repo.
- [plugins/video-engine](../plugins/video-engine/README.md) and [plugins/ui-kit](../plugins/ui-kit/README.md): the
  Claude plugins that drive these tools by conversation.
