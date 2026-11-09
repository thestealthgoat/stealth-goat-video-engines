# What the compliance gate checks

`web/compliance.py <site folder> --site <site.json> [--out report.md]` serves the built folder on 127.0.0.1, opens
every page in headless Chromium (Playwright) and checks the list below. The report goes to
`<site folder>_compliance.md` beside the folder (never inside it, so it never ships). Exit code 1 means FAIL.
Numbers in brackets are the checklist item numbers printed in the report.

| # | Check | FAIL when |
|---|---|---|
| 1-5 | legal pages | `privacy.html`, `terms.html`, `data-request.html` (and `cookies.html` when `third_party` is set) are missing, or any page's footer doesn't link them; the privacy policy lacks retention or sharing |
| 4 | consent banner | Accept and Reject differ in size, weight or colour; any request leaves for another host before a choice |
| 6-7 | forms | a form lacks an unchecked consent box with a privacy link; a field has no label |
| 8 | third-party audit | a page loads from a host not in `third_party`; a form posts to a host the privacy policy doesn't name |
| 11 | data deletion | the data-deletion paragraph on the privacy and data-request pages has no working `mailto:` or `tel:` link |
| 12 | dark patterns | a box is pre-checked (in the live page); urgency or countdown wording ("only 3 left", "hurry", "act now", "limited time"...); confirm-shaming ("no thanks, I don't want...") |
| 15 | claims | never fails: "#1", "best", "guaranteed", "leading", "unbeatable", "cheapest" are listed under Needs the owner (is there a source?) |
| 16 | alt text | an image has no alt (empty alt only when decorative or aria-hidden) |
| 17 | contrast | the page is scrolled top to bottom at 1440x900 and 390x844 (plus the first screen at 1366x657 and 390x664), every reveal forced visible and every FAQ open; each visible text line is measured against the real pixels behind it. The 5th percentile must be at least 4.5:1, or 3:1 for large text (24 px, or 18.7 px bold). Only text inside `[data-decorative]` is exempt |
| 17+ | cut-off text | text clipped by its container, past the side of the window, or under the fixed header on the first screen |
| 18 | keyboard | Tab misses a visible control; a control has no visible focus style; any `tabindex` above 0 |
| 19 | business details | no legal name plus email or phone (a missing address is only listed for the owner) |
| 20 | assets | a font or image file in the site isn't in `assets.json`; an asset has no source or licence (`MISSING`); a font's licence file isn't shipped |
| + | phone width | more than 2 px of sideways scroll on a 390 px phone |
| + | broken files | any file fails to load (HTTP 400+) |

## "Needs the owner" (decisions and facts only a person can give)

- each legal page still marked DRAFT (until `legal.approved` is set);
- the form endpoint, when a form has no `action`;
- images whose licence is `"UNSPECIFIED"` in site.json;
- claims that need a source;
- a physical address, if the site sells online.

## Fixing common FAILs

| Report line | Fix |
|---|---|
| `font ...: its licence file is not shipped` | put the font's licence text beside the font file in the profile as `OFL-<Family>.txt` (the engine's `resources/fonts/` holds the OFL texts for the bundled fonts), or point the profile's font at `{repo}/resources/fonts/...`; rebuild |
| `no source / licence for N asset(s)` | set `images_owner` / `images_licence`, or per-image `credit` / `licence`; use `"UNSPECIFIED"` only to flag an open question |
| `contrast 3.9:1 on ...` | for text over a photo, pick a darker or calmer frame, or shorten the copy so it sits on the shaded area; for kit text, change the profile's colours (`primary`, `accent`, `text`) rather than adding CSS |
| `... is cut off by its container` / `runs past the side` | shorten the headline lines (each `headline` entry is one line) or the stage titles |
| `requests to <host> BEFORE any cookie choice` | the host must be in `third_party` with a `src`, so it loads only after Accept; remove anything else that loads from outside |
| `N px of sideways scroll` | a long unbreakable word or URL in the copy; shorten or break it |
