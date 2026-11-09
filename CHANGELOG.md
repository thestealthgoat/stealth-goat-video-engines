# Changelog

All notable changes to this project are written down here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Releases are named by date (YYYY-MM-DD).

## Unreleased

### Added

- Contributing guide, this changelog, and issue and pull request templates.
- Getting-started guide and tool reference pages in `docs/`, and showcase images for the README.
- `examples/stage3d/sample_data.json`: sample data for the 3D `data` scene (fictional Harbor City Otters).

### Fixed

- `engine/stage3d.html`: the tilted name labels under the bars in the `data` scene sit on the floor instead of half
  under it.

## 2026-11-09 - Engine update + Claude plugins

### Added

- **Claude plugins** in `plugins/`, installable from this repo
  (`/plugin marketplace add thestealthgoat/stealth-goat-video-engines`, listed in `.claude-plugin/marketplace.json`),
  with packaged `.plugin` files for the desktop app in `plugins/dist/`:
  - `video-engine`, 12 skills: getting-started, video, video-gates, explain, matte, motion-graphics, logo-motion,
    logo-3d, logo-vectorize, player-cutouts, action-pack, reference-intake.
  - `ui-kit`, 2 skills: ui-kit (brand tokens with measured contrast, components, spring UI motion, palette and UI
    checks) and website.
- **Explainer engine:** `engine/storyboard.py` (pace, retime to a recorded voice-over, check, board),
  `engine/explain.py` + `engine/explain.html` (one continuous canvas whose elements persist and spring to new values,
  word-paced captions, a Premiere XML with every render), `engine/sourcecard.py` (a source page screenshot with the
  quoted phrase highlighted) and `engine/musicbed.py` (a synthesized music bed with a drop on a bar).
- **People and talking heads:** `engine/matte.py` (person matte as ProRes 4444 alpha, with an edge-flicker report),
  `engine/behind.py` (text behind the person), `engine/talkedit.py` (talking-head edit with pop-up stat cards planned
  from the transcript), `engine/captions.py` (word-synced kinetic captions, burned in or as an alpha layer, plus `.srt`), `engine/hopwords.py`
  (a character that hops from word to word through a verse or lyric).
- **Motion graphics:** `engine/statcard.py` (stats lower third), `engine/progressbar.py`, `engine/quote.py`,
  `engine/beforeafter.py`, `engine/sketch.py`, `engine/routemap.py` (route maps from Natural Earth data offline, or
  OpenStreetMap with `--map osm`).
- **3D card scenes:** `engine/stage3d.py` + `engine/stage3d.html` with the scenes data, orbit, stack, burst, badge,
  toggle, props, reveal, hop, fly and extrude.
- **Edit tools:** `engine/fxpack.py` (cinematic edit effects, each placed on a music event from the bar map), `engine/aejsx.py` (an editable After Effects
  handoff as an ExtendScript `.jsx`; `statcard.py --ae`), `engine/measure.py` (measure a finished motion piece, fit springs to it, compare a rebuild),
  `engine/fcp7xml.py --single` (Premiere XML for a single rendered MP4).
- **Logo templates** in `logo/motion.py`: lockup, writeon, morph, pixelbuild, linebuild, echo, lightstreak,
  lightpaint, swap, shatter and brandgrid, plus `--finish dark` (a cinematic finish on any template) and
  `--mockup laptop`.
- **Website kit** in `web/`: `build.py` (one `site.json` + a profile to a static site), `compliance.py` (accessibility,
  privacy and consent checks in a real browser), `preview.py` (screenshots and a scroll-through video), the shared
  `web/kit/`, and five hero templates (W1-W5).
- `engine/models.py`: one place that finds the model folder (rembg's `$U2NET_HOME`, or `rembg_models` in
  `local.json`).
- `profiles/demo`: a neutral demo profile with OFL fonts (licenses beside them) and a drawn logo, used by every
  example and skill.
- `examples/`: an explainer topic pack (`explain/lissajous`) and two sample sites (`sites/demo-world`,
  `sites/demo-studio`), plus `logo/stories/placeholder_story.svg` for the lightpaint template.
- Self-tests for the stats lower third and the bouncing-character verses (`tests/test_statcard.py`,
  `tests/test_hopwords.py`).

### Changed

- Person cutouts and mattes use BiRefNet by default (through rembg): `engine/matte.py`, `engine/cutout.py` and
  `cutouts/cutouts.py`. MODNet and U2Net stay selectable in `matte.py --model`.
- `engine/qa.py`: for explainers, a local state change (a new element, a readout changing) counts as a fresh visual,
  not only cuts and scene changes.
- `logo/motion.py`: `intro` and `outro` open with a big move in the first half second; `bug_out` and `presented`
  exits end on the clip's last frame; the `lockup` text defaults come from the profile (`brand.lockup_title`,
  `brand.lockup_line`).
- `engine/encode.py`: `--preset` defaults to the profile's `delivery.default_preset`, else `web`; the demo and
  template profiles ship a `delivery.web` preset.
- No organization names, brand values or machine paths anywhere in `engine/`, `logo/` or `web/`: everything comes
  from the profile.
- `requirements.txt`: `rembg>=2.0.80` (BiRefNet sessions).

### Fixed

- `--help` works for `vertical.py`, `flipbook.py`, `fcp7xml.py` and `cutout.py`; `sfx_build.py -h` prints help
  instead of writing a file named `-h`.
- `vertical.py` and `musicbed.py` create their output folder; `models.py` creates a named model folder.
- `explain.py` refuses a missing `--music` / `--vo` file before rendering, and removes its temporary frames when a
  render is interrupted.
- `qa.py`: the hook gate counts a strong moment at exactly 2.0 s.
- `cutouts/cutouts.py` turns sideways phone photos upright (EXIF orientation), and no longer crashes on newer
  RapidOCR versions that return scores as text.
- `vprofile.py show demo --check` is clean: the demo profile's folders are optional.

## 2026-11-07 - First public release

### Added

- **Profiles:** `engine/vprofile.py` and `profiles/_template`. Brand colors, fonts, logos, folders and delivery specs
  live in one JSON file per organization; nothing is hard-coded in the tools.
- **QA gate:** `engine/qa.py` (spec, motion, stutters, unplanned cuts, flash frames, loudness and true peak, clicks,
  hook and hold checks, with `review.md` and a review sheet), built on `engine/audio_check.py` and
  `engine/motion_check.py`.
- **Springs:** `engine/spring.py` / `engine/spring.js`, closed-form damped springs seekable by time, with camera,
  hand-held and impact-shake helpers (`engine/README_motion.md`).
- **Music:** `engine/beatmap.py` (a bar map of a track, adapted from Higgsfield AI's MIT code, see `NOTICE.md`) and
  `engine/beatsnap.py` (snap cuts to beats, downbeats and the drop); `engine/sfx_build.py` (a synthesized build,
  impact and drop).
- **Editing:** `engine/sheet.py` (contact sheets), `engine/clip_plays.py` (stream-copy cuts from a list),
  `engine/fcp7xml.py` (edit list to Premiere-ready XML), `engine/vertical.py` (9:16 from 16:9),
  `engine/flipbook.py` (burst photos to stop-motion), `engine/calls.py` (local transcripts with faster-whisper),
  `engine/cutout.py`, `engine/encode.py` (delivery masters) and `engine/offload.py` (safe, resumable card copy).
- **Logo tools** in `logo/`: vectorize, redraw and font matching, 3D extrusion (stills, swing loop, GLB), and
  animated templates with alpha (intro, outro, bug, stinger, presented, slam).
- **Person cutouts** in `cutouts/`: cut out, grade and file people from photos into a per-person library.
- `setup.sh` for macOS with Homebrew (`--check` reports without installing), `requirements.txt`, OFL fonts in
  `resources/fonts/`, and self-tests in `tests/` on synthetic input.
- MIT license; third-party credits in `NOTICE.md`.
