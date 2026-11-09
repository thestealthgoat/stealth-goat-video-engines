# UI checklist: accessibility and honest design

Run it on every screen the change touches. **Check** says how: `palette` = `python3 "${CLAUDE_PLUGIN_ROOT}/skills/ui-kit/scripts/palette.py" check tokens.css`,
`ui_check` = `python3 "${CLAUDE_PLUGIN_ROOT}/skills/ui-kit/scripts/ui_check.py" <url>` (a real browser), `eye` = look at the screenshots or try it by hand.
(If `${CLAUDE_PLUGIN_ROOT}` is empty, use the absolute path of the ui-kit skill folder instead.)
The numbers follow WCAG 2.2 level AA. The same rules drive the engine's website gate (`web/compliance.py`).

## Color and contrast

| # | Rule | Check |
|---|------|-------|
| C1 | Body text, labels, links, placeholder and helper text: at least **4.5:1** against what is really behind them | palette, ui_check |
| C2 | Large text (24 px, or 18.66 px bold) at least **3:1**. Aim for 4.5:1 anyway | ui_check |
| C3 | The edges of controls (input and checkbox borders, an outlined button) and the focus ring: at least **3:1** against the page | palette |
| C4 | Text on photos, gradients or video is measured on the pixels, not on the CSS background color. Add a scrim or move the text when it fails | ui_check |
| C5 | Color is never the only signal: an error says "Error:" in words, a status badge has a word, links in text are underlined | eye |
| C6 | Both themes pass. Dark mode is its own palette, not an inverted one | palette, `ui_check --dark` |
| C7 | Disabled controls stay readable. Better: keep the button enabled and explain what is missing when it is pressed | eye |

## Keyboard and focus

| # | Rule | Check |
|---|------|-------|
| K1 | Tab reaches every control: links, buttons, inputs, selects, custom widgets, the close button of every toast and dialog | ui_check |
| K2 | Every focused control shows a visible ring (`:focus-visible` with `--focus-ring`). `outline: none` only with a replacement | ui_check |
| K3 | Tab order follows the reading order. No `tabindex` above 0 | ui_check |
| K4 | A skip link is the first Tab stop on pages with navigation: `<a class="ui-skip" href="#main">` | ui_check |
| K5 | Esc closes menus, popovers and dialogs, and focus returns to the button that opened them | eye |
| K6 | Dialogs keep focus inside while open (native `<dialog>` with `showModal()` does this) | eye |
| K7 | Custom widgets use real elements first (`<button>`, `<details>`, `<dialog>`, `<select>`). ARIA only when nothing native fits | eye |

## Forms

| # | Rule | Check |
|---|------|-------|
| F1 | Every field has a visible `<label for>`. A placeholder is a hint, never the label | ui_check |
| F2 | Optional fields say "(optional)"; required ones are required in the code too | eye |
| F3 | Errors appear next to the field, in words, linked with `aria-describedby`, `aria-invalid="true"` on the field; focus moves to the first problem | eye |
| F4 | Inputs are 16 px or larger (iOS zooms into smaller ones) and use the right `type` and `autocomplete` | eye |
| F5 | Ask only for what the task needs. Every field has a reason you could say out loud | eye |
| F6 | Consent boxes start unticked, one purpose per box (marketing email is its own optional box), with a privacy link | ui_check (pre-ticked boxes) |
| F7 | Tap targets at least 44 px tall (`--target-min`), including a checkbox with its label | eye |

## Layout and motion

| # | Rule | Check |
|---|------|-------|
| L1 | No sideways scroll at 390 px wide; tables scroll inside `.ui-table-wrap`, not the page | ui_check |
| L2 | Text can be zoomed to 200% without losing content (sizes in rem, no fixed-height text boxes) | eye |
| L3 | Images have alt text that says what matters; decorative images use `alt=""` | ui_check |
| M1 | UI motion uses the spring tokens: `--dur-ui` 200 ms in, `--dur-ui-exit` 160 ms out, `--ease-spring`; JS moves use `spring.js` presets `ui` / `uiExit` | eye |
| M2 | No bounce or overshoot on UI (both presets are critically damped); opacity is clamped so it never goes past 1 | eye |
| M3 | `prefers-reduced-motion: reduce` makes every change instant, CSS and JS | ui_check (CSS), eye (JS) |
| M4 | Nothing flashes more than 3 times a second; nothing moves on its own for more than 5 s without a pause button | eye |

## Honest design (no dark patterns)

| # | Rule | Check |
|---|------|-------|
| H1 | The "no" choice looks the same as the "yes" choice: same size, same weight (Accept / Reject, Subscribe / No thanks) | eye |
| H2 | No confirm-shaming ("No thanks, I don't like saving money") | ui_check |
| H3 | No fake urgency or scarcity: countdowns, "only 2 left", "hurry", "offer expires in" unless literally true and sourced | ui_check |
| H4 | No pre-ticked boxes, no sneaking items into a basket, no hidden costs revealed at the last step | ui_check, eye |
| H5 | Canceling or unsubscribing is as easy as signing up, and reachable without a call or a chat | eye |
| H6 | Prices, totals and what happens next are shown before the final button, which says what it does ("Pay $24.00", not "Continue") | eye |
| H7 | Toasts never carry something the user must act on; they stay at least 6 s, pause on hover or focus, and have a Close button | eye |
| H8 | Claims ("#1", "best", "guaranteed") have a source, or are cut | eye |
| H9 | Nothing third-party (analytics, pixels, fonts from a CDN, embeds) loads before the user agrees, where consent is needed. Self-host fonts with their license file | eye (the website gate checks this on sites) |

## Before you call it done

1. `python3 "${CLAUDE_PLUGIN_ROOT}/skills/ui-kit/scripts/palette.py" check <app>/tokens.css` exits 0 and its last line reads
   `palette check: N/N pairs pass` (both numbers equal, no `, K FAIL` on the end).
2. `python3 "${CLAUDE_PLUGIN_ROOT}/skills/ui-kit/scripts/ui_check.py" <url> --dark --out <folder>` prints `PASS`, and you have looked at
   `desktop.png`, `phone.png`, the dark ones and the `focus-NN.png` stops.
3. You have tabbed through the main flow by hand once (open a menu, submit a form with an error, close a dialog with Esc).
4. Every "eye" row above that applies has been looked at.
