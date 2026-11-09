# ui-kit plugin for Claude

A small, opinionated design kit for apps and websites, plus cinematic one-page websites, as two Claude skills. The
`ui-kit` skill restyles any web UI with brand color tokens whose contrast is measured, not eyeballed, accessible
components and spring motion, then proves the result in a real browser. The `website` skill builds a one-page site
from a short `site.json` with the website kit of the [Stealth Goat video engines](../../README.md). See
[docs/TOOLS.md](../../docs/TOOLS.md) for the engine tools behind them.

## Quick start

1. **Add the plugin.** In Claude Code:

   ```
   /plugin marketplace add thestealthgoat/stealth-goat-video-engines
   /plugin install ui-kit@stealth-goat
   ```

   In the Claude desktop app (Cowork), open `ui-kit.plugin` from the repo's `plugins/dist/` folder and press Install.

2. **Ask for it.** "Apply the UI kit to this app", "make our app's colors accessible", "add focus states", or
   "build a website for my studio".

3. **Or run the kit's scripts yourself** from a clone of the repo (they need Python 3, and Playwright with Chromium for
   the browser check):

   ```bash
   K=plugins/ui-kit/skills/ui-kit
   python3 $K/scripts/palette.py make --profile-json profiles/demo/profile.json   # brand colors -> measured tokens
   python3 $K/scripts/palette.py ratio "#FFFFFF" "#0B3D2E"                         # one pair: 12.20:1, passes
   python3 $K/scripts/ui_check.py $K/references/example/after.html --out out/ui-check   # report.md + screenshots
   ```

   The browser check should report `UI check: PASS`.

## The skills

### ui-kit

- Brand color tokens for light and dark themes with measured contrast: 4.5:1 for text, 3:1 for large text and
  controls (`scripts/palette.py`).
- A type scale, spacing, radius, shadow and focus tokens (`references/tokens.css`).
- Accessible components with visible focus states: buttons, inputs, selects, checkboxes, cards, tables, badges, toasts,
  a dialog and a skip link (`references/components.css`).
- Spring motion for UI with the `ui` and `uiExit` presets: no bounce, and opacity never overshoots
  (`references/spring.js`, `references/ui-motion.js`). The presets are described in
  [engine/README_motion.md](../../engine/README_motion.md).
- An accessibility and honest-design checklist (`references/checklist.md`), and a real-browser check
  (`scripts/ui_check.py`): Tab reach and focus rings, pixel contrast, phone width, labels, pre-ticked boxes,
  dark-pattern wording and reduced motion.
- A worked example: `references/example/before.html` (a plain form) and `after.html` (the kit applied).

Brand colors come from two hex values (`--primary`, `--accent`), any `profile.json` (`--profile-json`), or a named
engine profile (`--profile`, which needs `$VIDEO_ENGINE`). Only the named-profile option needs the engine.

### website

One-page sites from a short `site.json`, in five templates: W1 scroll-built story, W2 3D isometric scroll world, W3
drone flyover, W4 cinematic service business and W5 3D glass showcase. Every site gets draft privacy, terms and
data-request pages, consent handling and a compliance gate run in a real browser. It ships three.js inside the site,
loads nothing from another host and sets no tracking cookies.

This skill needs the engine folder:

```bash
git clone https://github.com/thestealthgoat/stealth-goat-video-engines.git ~/video-engine && cd ~/video-engine
./setup.sh                                        # macOS with Homebrew
export VIDEO_ENGINE="$HOME/video-engine"          # add this line to ~/.zprofile to keep it
```

Two ready-made sites on the `demo` profile, with build and gate commands, are in [examples/](../../examples/README.md).

## License

MIT, like the rest of the repo. Third-party credits are in the repo's [NOTICE.md](../../NOTICE.md).

## See also

- [Root README](../../README.md): install, profiles and the tour of the engine.
- [docs/TOOLS.md](../../docs/TOOLS.md): every tool in the repo.
- [video-engine plugin](../video-engine/README.md): logos, explainers, mattes, motion graphics, edits and the QA gate.
