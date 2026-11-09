---
name: ui-kit
description: Applies a small, opinionated design kit to any app or website UI (plain HTML/CSS, React, Vue, Svelte, Tailwind, Electron, desktop web views). Covers brand colour tokens with measured contrast in light and dark themes, a type scale, spacing, radius, shadow and focus tokens, accessible components (buttons, inputs, selects, checkboxes, cards, tables, toasts, dialogs), spring motion for UI transitions (about 0.2 s, no bounce, opacity never overshoots), and an accessibility and honest-design checklist. Verifies the result in a real browser (Playwright screenshots, keyboard tab-through, pixel-measured contrast). Use when the user says "apply the UI kit to this app", "make our app's colours accessible", "add focus states", "fix the contrast", "make the UI on-brand", "style this form", "add dark mode", "make the buttons and inputs consistent", "make the animations feel snappier", or "check my app for accessibility".
---

# UI kit

Restyle an existing app with the kit's tokens and components, measure every colour pair, wire spring motion
for UI transitions, and prove the result in a real browser. The kit is the engine's website kit
(`web/kit/site.css`, `web/kit/site.js`, the `palette()` in `web/build.py`, `engine/spring.js` and the
`web/compliance.py` gate) cut down for any app.

Commands below reach this skill's own files through `${CLAUDE_PLUGIN_ROOT}/skills/ui-kit/` (the plugin root
variable). If `${CLAUDE_PLUGIN_ROOT}` comes through empty, use the absolute path of the folder holding this SKILL.md
instead; never run a command as `/scripts/...` or `/references/...`. Its files:

| File | What it is |
|------|------------|
| [references/tokens.css](references/tokens.css) | CSS custom properties: colours (light + dark), type scale, spacing, radius, shadow, focus ring, motion |
| [references/components.css](references/components.css) | `ui-` classes: buttons, fields, select, checkbox/radio, cards, tables, badges, toasts, dialog, skip link, reduced motion |
| [references/spring.js](references/spring.js) | the engine's `spring.js`, unchanged (presets `ui` and `uiExit` for UI) |
| [references/ui-motion.js](references/ui-motion.js) | `UIMotion.enter / exit / disclose / openDialog / closeDialog / toast` on those springs |
| [references/checklist.md](references/checklist.md) | the accessibility + honest-design checklist, with how each item is checked |
| [references/example/](references/example/) | the worked example: `before.html` (a plain form) and `after.html` (the kit applied) |
| `scripts/palette.py` | brand colours to tokens with measured contrast (`make`), the measuring check (`check`), one pair (`ratio`) |
| `scripts/ui_check.py` | real-browser check: Tab reach + focus rings, pixel contrast, phone width, labels, pre-ticked boxes, dark-pattern wording, reduced motion; screenshots |

## 0. Set up

1. Need `python3`. For the browser check, need Playwright with Chromium:
   `python3 -c "import playwright"`; if missing, ask before installing, then run
   `python3 -m pip install playwright pillow numpy && python3 -m playwright install chromium`.
2. Brand colours come from the user (two hex values: a primary and an accent), or from a brand profile in the
   video engine folder. Without the engine, use `--primary` / `--accent`, or `--profile-json` on any profile.json;
   everything else in this skill works without it. For a profile by name, use `$VIDEO_ENGINE`. If it is unset and the
   user wants their profile's colours, ask where the engine folder is; if they have none, set it up (the
   `setup.sh` script targets macOS with Homebrew):
   ```
   git clone https://github.com/thestealthgoat/stealth-goat-video-engines
   cd stealth-goat-video-engines && ./setup.sh
   export VIDEO_ENGINE="$PWD"
   ```
   (The getting-started skill walks through the same setup, but it is in the separate video-engine plugin, so it is
   only there when that plugin is installed too.) Profiles: `--profile <name>`, else `$VIDEO_PROFILE`, else
   `local.json`. Users make their own from `profiles/_template`
   (`cd "$VIDEO_ENGINE" && python3 engine/vprofile.py new <name>`); `demo` ships with the engine and is the neutral
   one for trying things. A name that is not there prints `make: profile '<name>' not found ...` with the list of
   profiles and exits 1.
3. Do not upload the app or its screenshots anywhere. Everything here runs locally.

## 1. Read the app first

1. Find where styles live: global CSS files, CSS modules, Tailwind config (`tailwind.config.*` or `@theme` in CSS),
   CSS-in-JS theme objects, an Electron renderer's stylesheet. Note the framework and how styles are loaded.
2. Inventory the ad-hoc values. Colours:
   `grep -rhoE '#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\)|hsla?\([^)]*\)' src | sort | uniq -c | sort -rn`
   (point it at the real source folders; skip `node_modules`, builds and vendored files). Do the same for
   `font-size`, `border-radius`, `box-shadow`, `transition` and `outline: none`.
3. Write a short mapping table before editing: each existing value, where it is used (body text, muted text, page
   background, card, border, primary button, link, error...), and the token it becomes. Show it to the user when
   the app is big or the brand choice is unclear.
4. Find the interactive parts: forms, menus, popovers, dialogs, toasts, tables, custom widgets. These get the
   components, the focus ring and the motion.

## 2. Make the tokens from the brand

1. Copy the kit into the app, beside its other styles (for example `src/styles/ui-kit/`):
   `tokens.css` and `components.css` always; `spring.js` and `ui-motion.js` when the app needs JS-driven
   enter/exit motion. Load `tokens.css` before `components.css`, both before the app's own CSS.
2. Generate the colour block from the brand and write it into the copied `tokens.css`:
   - `python3 "${CLAUDE_PLUGIN_ROOT}/skills/ui-kit/scripts/palette.py" make --primary "#2348b8" --accent "#d9480f" --write src/styles/ui-kit/tokens.css`
   - from an engine profile (needs `$VIDEO_ENGINE`, see step 0): `python3 "${CLAUDE_PLUGIN_ROOT}/skills/ui-kit/scripts/palette.py" make --profile demo --write src/styles/ui-kit/tokens.css`
   - from any `profile.json`: `--profile-json path/to/profile.json` (reads `brand.colors.primary / accent / text`).
   It nudges each role until it passes, the way the website kit's `palette()` does: text 7:1 on every ground; muted
   text, links and status text 4.5:1; button labels 4.5:1; control borders, button fills and the focus ring 3:1.
   The light theme is `:root`; dark follows the OS unless `<html data-theme="light">`, and `data-theme="dark"`
   forces it.
3. Measure it: `python3 "${CLAUDE_PLUGIN_ROOT}/skills/ui-kit/scripts/palette.py" check src/styles/ui-kit/tokens.css`. Every pair must say `ok`, and the last line reads
   `palette check: N/N pairs pass` (with `, K FAIL` added when any fail; it then exits 1).
   If the user insists on an exact brand colour that fails (a yellow link on white), keep the brand colour for fills
   and large display text only, and say which pairs it fails and by how much.
4. Fonts: keep the app's fonts unless asked. When adding a brand face, self-host it with its licence file
   (OFL fonts ship `OFL-<Family>.txt`), declare it with `@font-face` and `font-display: swap`, and put it first in
   `--font-body` / `--font-head`. Do not add a font CDN request.
5. Leave the type scale, spacing, radius, shadow and motion tokens as they are unless the app's existing scale is
   deliberate; then map the app's values onto the nearest tokens instead of inventing new steps.

Roles to map onto (full list in `tokens.css`):

| Existing use | Token |
|--------------|-------|
| page background / cards and inputs / zebra rows, hovers | `--color-bg` / `--color-surface` / `--color-surface-2` |
| body text / secondary text, hints, placeholders | `--color-text` / `--color-text-muted` |
| links, accent text | `--color-link` |
| primary button fill / its label | `--color-action` / `--color-on-action` |
| badges, highlights / their text | `--color-highlight` / `--color-on-highlight` |
| input, checkbox, outlined-button borders / decorative lines | `--color-border` / `--color-divider` |
| errors, success, warnings (text and fills) | `--color-danger` (+ `--color-on-danger`), `--color-success`, `--color-warning` |
| focus ring | `--focus-ring` (built from `--color-focus`) |

## 3. Replace the ad-hoc values

1. Work one screen or component at a time. Replace each literal with its token (`color: #333` becomes
   `color: var(--color-text)`). Do not change layout, copy or behaviour beyond what the user asked.
2. Framework notes:
   - Tailwind: point the theme colours at the variables (`primary: 'var(--color-action)'`, and so on) instead of
     hex values, so dark mode and contrast come from `tokens.css`.
   - CSS-in-JS / theme objects: set the theme values to `'var(--color-text)'` strings.
   - Existing component libraries: set their theme variables to the kit tokens rather than restyling each part.
3. Use the `ui-` components where the app has none, or copy their rules into the app's own class names. Use real
   elements: `<button>` for actions, `<a href>` for navigation, `<label for>` for every field, native `<dialog>`,
   `<details>` and `<select>` before ARIA widgets.
4. Put a skip link first in `<body>`: `<a class="ui-skip" href="#main">Skip to content</a>` and `id="main"` on the
   main region.
5. Delete every `outline: none` / `outline: 0` that has no replacement. The global
   `:focus-visible { outline: var(--focus-ring); outline-offset: var(--focus-offset); }` in `components.css` gives
   every control the same ring. Custom widgets that draw their own focus must still show something at 3:1.
6. Forms: visible labels (a placeholder is a hint only), "(optional)" on optional fields, errors in words next to
   the field with `aria-describedby` and `aria-invalid="true"`, focus moved to the first error, consent and
   marketing boxes unticked and separate. See the worked example.
7. Honest design: the "no" button gets the same size and weight as the "yes" (`ui-btn--secondary`, never a grey
   link); remove confirm-shaming, fake urgency, countdowns and pre-ticked boxes. Rules: [references/checklist.md](references/checklist.md).

## 4. Measure contrast; never judge it by eye

1. `palette.py check` covers the token pairs.
2. For a pair outside the tokens (text on a brand illustration, a chart label):
   `python3 "${CLAUDE_PLUGIN_ROOT}/skills/ui-kit/scripts/palette.py" ratio "#767676" "#ffffff"` prints the ratio and whether it passes for text
   (4.5:1) and for large text and controls (3:1).
3. Text over photos, gradients or video can only be judged on the pixels: `ui_check.py` (step 6) hides the text,
   photographs the page and measures each text line against what is really behind it (5th percentile, the same
   method as the engine's website gate). When it fails, add a scrim behind the text or move it; do not lighten the
   photo until it looks "probably fine".

## 5. Wire spring motion

Use the engine's springs, not ease-in-out curves. For UI only `ui` (`{zeta: 1, omega: 37}`, settles in about
0.20 s) and `uiExit` (`{zeta: 1, omega: 46}`, about 0.16 s): both critically damped, so nothing bounces. The
`snappy`, `bouncy` and `slam` presets in `spring.js` are for video graphics, not app UI.

1. State changes (hover, pressed, selected, colour changes): CSS transitions with the tokens:
   `transition: background-color var(--dur-hover) var(--ease-spring)` and `var(--dur-ui)` for movement.
   `--ease-spring` is the `ui` spring sampled into CSS `linear()`, with a close `cubic-bezier` fallback.
2. Things that appear and disappear (menus, popovers, dialogs, toasts): load `spring.js` then `ui-motion.js` and use
   `UIMotion.enter(el)` / `UIMotion.exit(el)`, `UIMotion.disclose(button, panel)` (sets `aria-expanded`, Esc closes,
   outside click closes), `UIMotion.openDialog(dlg)` / `UIMotion.closeDialog(dlg, value)`, and
   `UIMotion.toast(text, {title, tone})` into one `<div class="ui-toasts" role="status" aria-live="polite">`.
   Moves are time-based and start from wherever the element is, so a fast open-close-open never jumps; opacity is
   clamped to 0..1.
3. In React, Vue or Svelte call the same functions from an effect or ref callback on the mounted element, and remove
   the element only after the `exit()` Promise resolves.
4. Entering things travel `--move-ui` (8 px) at most. No parallax, no scroll-jacking, no motion that starts on its own
   and runs longer than 5 s without a pause control.
5. Reduced motion: `tokens.css` sets the durations to 0, `components.css` stops every transition and animation, and
   `ui-motion.js` makes every change instant. Do not add motion that bypasses all three.

## 6. Verify in a real browser

1. Start the app the way the project does (its dev server, or open the built HTML). For Electron, check the
   renderer through its dev-server URL or the built `index.html`; for native desktop UI (SwiftUI, WPF...) the
   tokens still apply but this check does not: measure pairs with `palette.py ratio` and tab through by hand.
2. Run `python3 "${CLAUDE_PLUGIN_ROOT}/skills/ui-kit/scripts/ui_check.py" <url or file.html> --dark --out <folder>`. It exits 1 on any FAIL and
   writes `report.md`, `desktop.png`, `phone.png`, the `-dark` versions and `focus-NN.png` (the first focus stops).
3. Read the screenshots: the layout at 390 px, the dark theme, each focus ring. Fix every FAIL, then run it again
   until it says PASS.
4. Tab through the main flow yourself once with the Playwright page (open a menu, submit a form with an error,
   close a dialog with Esc and check focus returns to its button).
5. Go down [references/checklist.md](references/checklist.md) for the rows marked "eye".
6. For a whole one-page website built from a `site.json` (legal pages, consent banner, the full website gate), use
   the website skill instead: it runs the engine's `web/build.py` and `web/compliance.py`.

## Worked example: style a plain HTML form

`references/example/before.html` is a typical ad-hoc contact form: placeholders instead of labels, `outline: none`,
grey hint text at 2.2:1, an orange button with white text at 2.0:1, a fixed 520 px width, a pre-ticked "Send me
offers" box and a confirm-shaming "No thanks" link. `references/example/after.html` is the same form with the kit.

1. Check the "before":
   `python3 "${CLAUDE_PLUGIN_ROOT}/skills/ui-kit/scripts/ui_check.py" "${CLAUDE_PLUGIN_ROOT}/skills/ui-kit/references/example/before.html" --out /tmp/ui-before`
   It FAILs on: four unlabelled fields, the pre-ticked box, three contrast pairs, no focus style on six controls,
   188 px of sideways scroll on a phone, confirm-shaming wording; and notes the missing skip link.
2. The changes that make up `after.html`:
   - `tokens.css` + `components.css` linked; every colour is a token.
   - a skip link and `<main id="main">`;
   - each field in a `ui-field` with a `<label for>`, the hint as `ui-hint` linked by `aria-describedby`, "(optional)"
     on the topic, `autocomplete` and `type="email"`;
   - the form in a `ui-card` with `max-width: 36rem` instead of `width: 520px`;
   - the marketing box unticked and optional, a separate required consent box with a privacy link, the shaming link
     removed, Clear as a `ui-btn--secondary` the same size as Send;
   - errors in words ("Error: enter your name.") next to each field, `aria-invalid`, focus to the first problem;
   - a success toast through `UIMotion.toast` (springs in on `ui`, stays 6 s, has Close).
3. Check the "after": `python3 "${CLAUDE_PLUGIN_ROOT}/skills/ui-kit/scripts/ui_check.py" "${CLAUDE_PLUGIN_ROOT}/skills/ui-kit/references/example/after.html" --dark --out /tmp/ui-after`
   prints PASS: every text node passes in both themes at both sizes, Tab reaches all 11 controls with a ring, the
   skip link is the first stop, no CSS motion is left under reduced motion.
4. Re-brand it from the engine's `demo` profile and measure again (needs `$VIDEO_ENGINE`; without the engine, swap
   `--profile demo` for `--primary "#2348b8" --accent "#d9480f"`):
   ```
   mkdir -p /tmp/ui-demo/example
   cp "${CLAUDE_PLUGIN_ROOT}/skills/ui-kit"/references/*.css "${CLAUDE_PLUGIN_ROOT}/skills/ui-kit"/references/*.js /tmp/ui-demo/
   cp "${CLAUDE_PLUGIN_ROOT}/skills/ui-kit/references/example/after.html" /tmp/ui-demo/example/
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/ui-kit/scripts/palette.py" make --profile demo --write /tmp/ui-demo/tokens.css
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/ui-kit/scripts/palette.py" check /tmp/ui-demo/tokens.css
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/ui-kit/scripts/ui_check.py" /tmp/ui-demo/example/after.html --dark --out /tmp/ui-demo/check
   ```

## Report back

Tell the user, briefly: which files changed, the colour mapping (old value to token), the `palette.py check` and
`ui_check.py` results with the screenshot folder, anything that still fails and why (for example an exact brand
colour they chose to keep), and the checklist rows that need their decision (copy, claims, consent wording).
