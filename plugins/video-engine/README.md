# video-engine (Claude plugin)

Make videos with a local, open-source engine and Claude: animated logo intros and lower thirds, explainers whose
numbers are computed (not guessed), person mattes for text-behind-the-speaker, stats cards and 3D card scenes,
talking-head edits, kinetic captions, cinematic edit effects, and a QA gate that checks every render before you see it.

## Install

1. **The plugin.** In Claude Code: `/plugin marketplace add thestealthgoat/stealth-goat-video-engines`, then
   `/plugin install video-engine@stealth-goat`. In the Claude desktop app (Cowork): open `video-engine.plugin` from
   the repo's `plugins/dist/` folder and press Install.
2. **The engine.** Ask Claude "set up the video engine" (the `getting-started` skill), or by hand:
   ```bash
   git clone https://github.com/thestealthgoat/stealth-goat-video-engines.git ~/video-engine
   cd ~/video-engine && ./setup.sh && ./setup.sh --check     # macOS + Homebrew; ends with CHECK: OK
   export VIDEO_ENGINE=~/video-engine                          # add to ~/.zshrc
   ```
3. **Your brand.** Ask "make a brand profile for my channel": colours, fonts (OFL), logo SVG. Until then use `--profile demo`.

## What to ask for

| Skill | Say things like |
|---|---|
| getting-started | "set up the video engine", "make a brand profile", "show me what this can do" |
| video | any video job: "edit this talk, cut the pauses", "caption this", "beat-sync these clips" |
| video-gates | "QA this render", "check this video before I post it" |
| explain | "make an explainer on why a mic feeds back" |
| matte | "cut the speaker out of this clip", "text behind the person" |
| motion-graphics | "stats lower third", "quote card", "progress bar", "before/after", "route map of our trip", "3D card scene" |
| logo-motion | "logo intro", "end card", "corner bug", "word-swap lower third", "shatter the old logo into the new one" |
| logo-3d / logo-vectorize | "3D version of our logo", "turn this JPG logo into a clean SVG" |
| player-cutouts / action-pack | "cut out our players from the game photos", "stop-motion pack from these bursts" |
| reference-intake | "here's a video I like, break it down" |

Free and open-source by default; nothing leaves your machine unless you choose a service. AI tools are fine, but the
skills never make a fake of a real person. Engine: MIT. See the repo's NOTICE.md for third-party credits.
