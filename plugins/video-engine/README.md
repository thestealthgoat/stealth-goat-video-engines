# video-engine plugin for Claude

Make videos by asking Claude, on a local, open-source engine: animated logo intros and lower thirds, explainers whose
on-screen numbers are computed rather than guessed, person mattes for text behind the speaker, stats cards and 3D card
scenes, talking-head edits, kinetic captions, cinematic edit effects, and a QA gate that checks every render before
you see it. The plugin is twelve Claude skills; the work is done by the
[Stealth Goat video engines](../../README.md) on your own machine. See [docs/TOOLS.md](../../docs/TOOLS.md) for every
tool the skills call.

## Quick start

1. **Add the plugin.** In Claude Code:

   ```
   /plugin marketplace add thestealthgoat/stealth-goat-video-engines
   /plugin install video-engine@stealth-goat
   ```

   In the Claude desktop app (Cowork), open `video-engine.plugin` from the repo's `plugins/dist/` folder and press
   Install.

2. **Set up the engine.** Ask Claude "set up the video engine" (the `getting-started` skill does the rest), or by
   hand on macOS with Homebrew:

   ```bash
   git clone https://github.com/thestealthgoat/stealth-goat-video-engines.git ~/video-engine && cd ~/video-engine
   ./setup.sh                            # installs what is missing, then checks: ends == Result: 0 missing, N warnings
   export VIDEO_ENGINE="$HOME/video-engine"   # add this line to ~/.zprofile
   ```

   `setup.sh` never edits your shell files: it prints the other lines to add to `~/.zprofile` (its step 5).
   `./setup.sh --check --profile demo` reports again without installing; its profile step ends `CHECK: OK`.

3. **Try it on the demo profile.** Ask "show me what this can do" for a ten-minute guided tour, or render a logo intro
   yourself:

   ```bash
   cd "$VIDEO_ENGINE"
   python3 logo/vectorize.py profiles/demo/assets/demo_logo.png out/tour Demo
   python3 logo/motion.py out/tour/Demo.svg out/tour Demo intro --profile demo --frames 0.5,1.5,3
   ```

4. **Add your brand.** Ask "make a brand profile for my channel": colors, open-license fonts and a logo SVG. Until
   then, every skill works with `--profile demo`.

## What to ask for

| Skill | Say things like |
|---|---|
| `getting-started` | "set up the video engine", "make a brand profile", "show me what this can do" |
| `video` | any video job: "edit this talk and cut the pauses", "caption this", "beat-sync these clips" |
| `video-gates` | "QA this render", "check this video before I post it" |
| `explain` | "make an explainer on why a mic feeds back" |
| `matte` | "cut the speaker out of this clip", "text behind the person" |
| `motion-graphics` | "stats lower third", "quote card", "progress bar", "before/after", "route map of our trip", "3D card scene" |
| `logo-motion` | "logo intro", "end card", "corner bug", "word-swap lower third", "shatter the old logo into the new one" |
| `logo-3d` | "make a 3D version of our logo" |
| `logo-vectorize` | "turn this JPG logo into a clean SVG" |
| `player-cutouts` | "cut out our players from the game photos" |
| `action-pack` | "make a stop-motion pack from these bursts" |
| `reference-intake` | "here's a video I like, break it down" |

Each skill's `SKILL.md` in [`skills/`](skills/) says exactly which engine tools it runs and how it checks the result.

## Requirements

- macOS on Apple silicon with Homebrew (what `setup.sh` targets). The engine is Python, ffmpeg and headless
  Chromium, so other systems can work with the same packages installed by hand.
- The engine folder, found through `$VIDEO_ENGINE`.
- Disk space for models, downloaded on first use: the matte and player-cutouts skills use BiRefNet (close to 1 GB per
  model, stored in the folder `engine/models.py` picks), and transcription uses a faster-whisper model.

## Principles

- Free and open-source tools by default. Nothing leaves your machine unless you choose a service.
- AI tools are fine when you want them, but the skills never make a fake of a real person.
- Every render goes through the QA gate (`engine/qa.py`) before it is shown or delivered.

## License

MIT, like the rest of the repo. Third-party credits are in the repo's [NOTICE.md](../../NOTICE.md).

## See also

- [Root README](../../README.md): install, profiles and the tour of the engine.
- [docs/TOOLS.md](../../docs/TOOLS.md): every tool in the repo.
- [examples/](../../examples/README.md): ready-made inputs on the demo profile.
- [ui-kit plugin](../ui-kit/README.md): design tokens, accessible components and one-page websites.
