# site.json reference

Everything `web/build.py` reads. Relative image and frame paths resolve against the folder that holds the
`site.json`. Keys not listed here are ignored.

## Top level

| Key | Required | Meaning |
|---|---|---|
| `template` | yes | `w1`, `w2`, `w3`, `w4` or `w5` (lowercase; the module in `web/templates/`) |
| `profile` | no | profile used when `--profile` is not given (then `$VIDEO_PROFILE`, then `local.json`) |
| `title` | no | the page `<title>` (default: `business.legal_name`) |
| `description` | no | the meta description |
| `lang` | no | page language, default `en` |
| `brand_text` | no | the wordmark at the top left (default: `business.legal_name`) |
| `business` | yes | `legal_name` (required), `email` and/or `phone` (at least one, or the build stops), `city`, `address` (needed only if the site sells online) |
| `legal` | no | `effective` (date shown on the legal pages), `retention` (how long form messages are kept; a 2-year default is written otherwise), `approved` (set only once the owner accepts the wording, e.g. `"2026-11-09 by Jane Doe"`; it removes the DRAFT notice) |
| `nav` | no | `[{"id": "work", "label": "Work"}]`: links to `index.html#<id>` (match a section's `id` or the hero's) |
| `hero` | yes | the template's fields (below) |
| `sections` | no | the section kit, in page order (below) |
| `third_party` | no | only when the owner wants analytics or embeds: `[{"name", "collects", "why", "src", "cookie"}]`. Any entry turns on the cookie policy page and a consent banner; each `src` loads only after Accept |
| `images_owner`, `images_licence` | when there are images | default source and licence for every image (per-image `credit` / `licence` win). Write `"UNSPECIFIED"` to flag an open question for the owner; leaving them out FAILs the gate |
| `credits` | no | a line in the footer (e.g. "3D scene drawn in code. No photos.") |
| `email_list` | no | set only if the site signs people up for marketing email. The gate then stops reporting "no marketing email" as done; the kit has no sign-up block, so make sure the email service gives every message an unsubscribe link |

## Section kit (`sections[]`)

Every section takes `type`, optional `id` (default: the type), `eyebrow`, `title`, `lede`.

| `type` | Fields |
|---|---|
| `stats` | `items: [{"value": "250+", "label": "...", "source": "..."}]` (numbers count up on a spring; give a `source` for any claim) |
| `features` | `items: [{"title", "text", "href"?, "link"?}]`, optional `image: {"src", "alt", "credit"?, "licence"?}` (with an image: split layout; without: full-width columns) |
| `process` | `steps: [{"title", "text"}]` (numbered 01, 02, ...) |
| `area` | `places: ["Town A", "Town B"]`, optional `note` |
| `gallery` | `images: [{"src", "alt", "caption"?, "credit"?, "licence"?}]` |
| `faq` | `items: [{"q", "a"}]` (native `<details>`) |
| `cta` | `href` (default `#contact`), `button` (default "Get in touch") |
| `text` | `paragraphs: ["...", "..."]` |
| `form` | `fields`, `action`, `processor`, `consent_text`, `button` (below) |

### Form

```json
{"type": "form", "id": "contact", "title": "Ask for a quote", "button": "Send",
 "action": "", "processor": "Formspree",
 "fields": [
   {"name": "name",  "label": "Your name", "required": true, "autocomplete": "name", "why": "so we know who to reply to"},
   {"name": "email", "label": "Email", "type": "email", "required": true, "autocomplete": "email", "why": "to send you the quote"},
   {"name": "kind",  "label": "What do you need?", "type": "select", "options": ["A", "B"], "why": "to route your request"},
   {"name": "msg",   "label": "Details", "type": "textarea", "why": "to understand the job"}
 ]}
```

- `type`: any `<input>` type (`text` default, `email`, `tel`, ...), `textarea` or `select` (with `options`).
- `why` is required on every field or the build stops; it is printed in the privacy policy.
- An unchecked consent box with the privacy link is always added (`consent_text` changes its wording).
- `action` empty: the form shows "not connected yet", does not send, and the gate lists the endpoint for the owner.
  When set, the action's host is named in the privacy policy as a form processor (`processor` gives its name).

## Hero, per template

### W1 scroll-built story

```json
"hero": {
  "label": "Walkthrough of the build", "eyebrow": "...", "headline": ["Line one", "line two"], "text": "...",
  "hint": "Scroll to walk through", "credit": "Footage: ...", "licence": "...",
  "frame_ratio": "9/16", "unit_vh": 75, "hold": 0.25,
  "intro":  {"frames": "frames/s0-*.jpg", "alt": "...", "weight": 0.6},
  "stages": [{"title": "...", "text": "...", "alt": "...", "frames": "frames/s1-*.jpg", "weight": 1}]
}
```

`frames` is a glob (sorted) or a list. `frame_ratio` is the footage's shape; `unit_vh` is the scroll length of one
stage of weight 1 (in viewport-height percent); `hold` is the share of the last stage that holds on the final frame.
Budgets: desktop frames under 32 MiB, the phone set under 16 MiB, or the build stops. Pull frames from footage with
ffmpeg, e.g. `ffmpeg -i walk.mp4 -vf "fps=6,scale=1280:-2" -q:v 3 frames/s1-%04d.jpg`, then keep the sharp ones.

### W2 3D isometric scroll world

```json
"hero": {
  "id": "how", "label": "How it works", "eyebrow": "ACME · HOW IT WORKS", "headline": ["From here", "to there"],
  "text": "...", "cta": {"label": "Get started", "href": "#contact"}, "short": "Start",
  "scenes": [{"kind": "field", "short": "Step", "title": "...", "text": "...", "cta": {"label": "...", "href": "..."}}]
}
```

Scene `kind`: `field` (cameras round a pitch), `switcher` (a control room cut away), `encoder` (an equipment rack),
`stream` (servers and a cloud), `home` (a living room and houses), `blocks` (a generic tile for anything else; the
default). `short` is the label on the step rail. A glowing cable lights up from scene to scene.

### W3 drone flyover

```json
"hero": {
  "label": "Site map", "eyebrow": "Site map", "headline": ["Find your way", "around."], "text": "...",
  "hint": "Scroll to fly", "still_text": "...",
  "map": {"src": "img/ortho.jpg", "alt": "...", "credit": "Aerial map: ...", "licence": "..."},
  "places": [{"label": "Main entrance", "x": 1077, "y": 1938, "r": 340, "heading": -8, "text": "..."}],
  "outro": {"title": "...", "text": "...", "cta": {"label": "...", "href": "#contact"}}
}
```

`map.src` must be a real orthomosaic (a stitched top-down drone map). `x` / `y` are pixel positions on that image,
`r` the ground radius in pixels the camera frames (default 380), `heading` the camera turn in degrees. 2 to 8 places,
or the build stops. The map is kept within 4096 px on its long side and must stay under 8 MiB.

### W4 cinematic service business

```json
"hero": {
  "label": "Build sequence", "eyebrow": "SPRINGFIELD · EST. 1998", "headline": ["BUILT TO", "LAST."], "text": "...",
  "cta": {"label": "Get a quote", "href": "#contact"},
  "sequence": {"frames": ["a.jpg", "b.jpg", "c.jpg"]},
  "alts": ["...", "...", "..."],
  "stages": [{"at": 0.0, "title": "The frame"}, {"at": 0.35, "title": "Walls go on"}]
}
```

`sequence` is either `frames` (photos, one `alts` entry each, or the build stops) or `{"video": "build.mp4",
"count": 72}` with one `alt`. `at` is the share of the scroll where a stage headline appears. The last frame is the
money shot (it is also the still for reduced motion). Same 32 / 16 MiB budgets as W1.

### W5 3D glass showcase

```json
"hero": {
  "label": "ACME Studio: video and design", "eyebrow": "VIDEO · DESIGN",
  "headline": ["Stories.", "Shapes.", "Tools."], "text": "...",
  "cta": {"label": "Get in touch", "href": "#contact"}, "cta2": {"label": "See the work", "href": "#work"},
  "chapters": [{"at": 0.22, "kicker": "01 · Video", "title": "...", "text": "..."}],
  "glass": {"seed": 7, "tint": 0.45}
}
```

No photos: the glass stage is generated. `at` is the share of the scroll for each chapter; `glass.seed` changes the
layout, `glass.tint` how much of the accent colours the glass (0 = clear). The hero's id is `top`.

## Colours and fonts (from the profile)

The site's palette is derived from the profile's `primary`, `accent` and `text` (and `primary_deep` if present): the
ground is always dark, and body text, muted text and the accent are adjusted until each passes 4.5:1. Fonts are the
profile's `head`, `body` and `body_semibold`, copied into the site with the licence file found beside each font
(`OFL-<Family>.txt`, `LICENSE-<Family>.txt`, or a bare `OFL.txt`). A font with no licence file beside it FAILs the gate.
