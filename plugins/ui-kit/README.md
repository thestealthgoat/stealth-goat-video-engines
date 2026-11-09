# ui-kit (Claude plugin)

A small, opinionated design kit for apps and websites, plus one-page cinematic websites.

- **ui-kit**: brand colour tokens with measured contrast (4.5:1 text, 3:1 large text and controls), a type scale,
  spacing and radius tokens, spring motion for UI (`ui` / `uiExit`, no bounce, opacity never overshoots),
  accessible components (buttons, inputs, cards, tables, toasts) with visible focus states, and an accessibility +
  honest-design checklist. Say: "apply the UI kit to this app", "make our app's colours accessible", "add focus states".
- **website**: one-page sites (scroll-built story, 3D isometric world, drone flyover, service business, glass
  showcase) from a short `site.json`, with draft legal pages, consent, and a compliance gate run in a real browser.
  Say: "build a website for my studio". Needs the engine folder:
  `git clone https://github.com/thestealthgoat/stealth-goat-video-engines`, then `./setup.sh` inside it (macOS with
  Homebrew) and `export VIDEO_ENGINE=<that folder>`. The ui-kit skill only needs the engine for named brand profiles.

## Install

Claude Code: `/plugin marketplace add thestealthgoat/stealth-goat-video-engines`, then `/plugin install ui-kit@stealth-goat`.
Claude desktop (Cowork): open `ui-kit.plugin` from the repo's `plugins/dist/` folder (built when the plugins are
packaged) and press Install.
