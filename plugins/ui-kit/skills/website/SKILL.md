---
name: website
description: Builds a cinematic one-page website from a short site.json and a brand profile with the engine's website kit (web/build.py), picking one of five templates (W1 scroll-built story, W2 3D isometric scroll world, W3 drone flyover over an orthomosaic, W4 cinematic service business, W5 3D glass showcase), with draft privacy, terms and data-request pages, consent and accessibility built in, then gates it with a compliance check in a real browser (web/compliance.py) and previews it as desktop and phone sheets plus a scroll-through video (web/preview.py). Static output, no tracking, no CDN. Use when the user says "build a website for my business", "make a one-page site", "landing page for my studio", "a scroll story of our build", "3D explainer page of how it works", "drone flyover map of our site", "portfolio page with glass 3D", or "check my site for privacy and accessibility".
---

# One-page websites with the website kit

Build a static one-page site with the engine's `web/` kit: `build.py` (site.json + profile -> a folder ready for any
static host), `compliance.py` (the gate, run in headless Chromium), `preview.py` (screenshots and a scroll video),
and the hero templates `web/templates/w1.py` to `w5.py`. The kit ships three.js inside the site, loads nothing from
another host, sets no tracking cookies, and writes draft legal pages from the site's own facts.

## 0. Find the engine

1. Use `$VIDEO_ENGINE` (a clone of https://github.com/thestealthgoat/stealth-goat-video-engines). Run every command
   as `cd "$VIDEO_ENGINE" && python3 web/<tool>.py ...`.
2. If `$VIDEO_ENGINE` is unset or the folder has no `web/build.py`, ask the user where the engine folder is. Do not
   guess a path. If they have none, set it up (`setup.sh` targets macOS with Homebrew; on another system install
   the same tools by hand: Python 3 with Pillow and Playwright, ffmpeg, Node):

   ```bash
   git clone https://github.com/thestealthgoat/stealth-goat-video-engines.git ~/video-engine
   cd ~/video-engine && ./setup.sh
   export VIDEO_ENGINE="$HOME/video-engine"   # add this line to ~/.zprofile so it survives a new shell
   ```

   (If the video-engine plugin from the same marketplace is installed, its getting-started skill walks through the
   same setup. This website skill does not need that plugin.)
3. Pick the profile: `--profile <name>` on the build, else the site.json `"profile"` key, else `$VIDEO_PROFILE`,
   else `default_profile` in the engine folder's `local.json`. The engine ships a `demo` profile (Anton + Barlow
   Condensed with their OFL licenses): use it to try things. For the user's own brand, make one from
   `profiles/_template`, e.g. `python3 engine/vprofile.py new acme --display "ACME" --primary "#0B3D2E" --accent
   "#F2B705"` (see `docs/LAYOUT.md`), then set its `brand.colors` (`primary`, `accent`, `text`) and `brand.fonts`
   (`head`, `body`, `body_semibold`) in `profiles/acme/profile.json`. A new profile points at the bundled fonts in
   `{repo}/resources/fonts/`, whose license files sit beside them, so the gate's font check passes as made.
   `python3 engine/vprofile.py show acme --check` prints the resolved fonts and colors; it also lists the video
   `paths` folders as missing until they exist, which does not matter for a website.
4. Check the dependencies once (`./setup.sh --check` in the engine folder lists what is missing):
   - Pillow for every build; `ffmpeg` / `ffprobe` for `preview.py` and for a W4 video sequence;
   - `logo/node_modules/three` for W2, W3 and W5 (`cd logo && npm ci`);
   - Playwright with Chromium for the gate and the preview (`python3 -m playwright install chromium`).

## 1. Gather the facts first

Ask for (or find in what the user gave you) only what the site needs:
- the business: legal name, an email or a phone (one is required: it is the footer contact and the data-deletion
  route), the city; a physical address only if the site sells online;
- what the page is for and the one action a visitor should take (call, email, quote form, watch, visit);
- the real material: photos, footage, a drone orthomosaic, the copy the user already has;
- whether they want a form, and where its messages should go (an email service, Formspree, their CRM). Without an
  endpoint the form is built but does not send, and the gate lists it for the owner;
- whether they want analytics or embeds. The default is none; add them only when the user asks.

Write copy from the user's facts. Never invent figures, awards, reviews or quotes; anything like "#1", "best" or
"guaranteed" needs a source the user gives you.

## 2. Pick one template (one signature technique per page)

| Template | When | Hero | Needs |
|---|---|---|---|
| `w4` cinematic service business | a trade or service company | a pinned, scroll-scrubbed build sequence with one editorial headline per stage, ending on the money shot and the CTA | 3+ real photos of one job from start to finish, or a video of it |
| `w1` scroll-built story | something gets built or set up (a remodel, an event setup) | an image sequence scrubbed by scroll, one caption per stage, a stage rail of real buttons | frames from one walk-through or time-lapse |
| `w2` 3D isometric scroll world | explaining a system or a journey | the camera travels one 3D world, one scene per step, a cable lighting up between them | nothing: scenes are drawn in code |
| `w3` drone flyover | a campus, a venue, a site | an orthomosaic as the ground; scroll flies to each place and stops with a card | a real orthomosaic (stitched top-down drone map), 2 to 8 places with pixel positions |
| `w5` 3D glass showcase | a portfolio or studio page | glass orbs and shards refracting under big editorial type, chapter by chapter | nothing: the stage is generated |

- Anti-repeat: when the user already has a site from this kit, make the new one differ on at least 4 of palette,
  type, hero layout, technique, CTA style, corners.
- Use real photos and footage first. AI images are fine when the user wants them, but never of a real person, and
  label them as illustration in their `credit`.
- When a W1 or W4 sequence doesn't exist yet, write the user a shot list instead of faking one: one continuous move
  or a fixed tripod, the same framing, steady exposure, a clearly different start and end.
- Every 3D template (W2, W3, W5) falls back to a still, readable page with reduced motion or without WebGL, and
  never loads three.js in that case.

## 3. Write the site.json

Put it in its own folder (e.g. `sites/<slug>/site.json` in the engine folder, with its images beside it); relative
paths resolve from there. The engine's `.gitignore` ignores `sites/` and every `out/`, so the user's photos and
builds never show up in the engine's git; any folder outside the engine works too. The shape:

```json
{
  "template": "w2", "profile": "demo",
  "title": "How it works | ACME", "description": "One sentence for search results.",
  "brand_text": "ACME",
  "business": {"legal_name": "ACME Ltd", "email": "hello@example.com", "city": "Springfield"},
  "legal": {"effective": "2026-11-09"},
  "nav": [{"id": "how", "label": "How it works"}, {"id": "contact", "label": "Contact"}],
  "hero": { "...": "the template's fields" },
  "sections": [{"type": "features", "id": "why", "title": "...", "items": [{"title": "...", "text": "..."}]}],
  "images_owner": "ACME Ltd", "images_licence": "owned by ACME Ltd"
}
```

The full reference (every top-level key, each template's hero fields, the nine section types `stats`, `features`,
`process`, `area`, `gallery`, `form`, `faq`, `cta`, `text`, and the form field rules) is in
[references/site-json.md](references/site-json.md). Read it before writing a hero.

Rules the build enforces (it stops with a message when one is broken):
- every image has `alt` text; a W4 photo sequence has one `alts` entry per photo;
- every form field has a `why` (what it is for; it goes into the privacy policy). Collect only what is needed;
- `business` has an email or a phone;
- W1 / W4 frames stay under 32 MiB desktop and 16 MiB phone; a W3 map under 8 MiB with 2 to 8 places.

Leave `legal.approved` out. Set it (e.g. `"2026-11-09 by Jane Doe"`) only after the user has read the legal pages
and accepts the wording; it removes the DRAFT notice. Recommend a lawyer's review before launch.

## 4. Build, gate, look

Build into a folder outside the site's sources (the build refuses an `--out` that holds them, and clears what an
earlier build generated there):

```bash
cd "$VIDEO_ENGINE"
python3 web/build.py sites/acme/site.json --out out/acme --profile acme
python3 web/compliance.py out/acme --site sites/acme/site.json       # the gate: must PASS
python3 web/preview.py out/acme --out out/acme_preview --name acme    # desktop + phone sheets, scroll video
```

- `build.py` prints the template, the section count, the logged assets and the size. The folder holds
  `index.html`, `privacy.html`, `terms.html`, `data-request.html` (`cookies.html` and a consent banner only when
  `third_party` is set), `assets/`, `fonts/` with their license files, `img/`, and `assets.json` (every font, image
  and library with its source and license).
- `compliance.py` writes `out/acme_compliance.md` beside the folder (never inside it, so it never ships) and exits 1
  on FAIL. What it checks and how to fix each FAIL: [references/compliance-gate.md](references/compliance-gate.md).
  Fix the site.json or the profile and rebuild until it says PASS. Never hand-edit the built HTML to get a PASS.
- `preview.py` writes `acme_desktop.jpg` (1440 wide strip), `acme_phone.jpg` (390 wide), `acme_laptop.jpg` (the
  first screen at 1366x657, where a tall hero gets cut off first) and `acme_scroll.mp4` (a 14 s spring scroll at
  1440x900, 30 fps, no sound; `--seconds` changes it). It drives a browser and encodes a video (a couple of minutes,
  more on a slow machine): run it once the gate passes, and only one at a time alongside any other heavy job.

Read the gate report and look at every preview sheet yourself before calling the site done: check the hero reads
on the laptop screen, nothing overlaps on the phone, and the story order makes sense. Judge the site from the three
sheets, not from the scroll video.

The scroll video is a rough review aid, not a deliverable. It is recorded from headless Chromium with software
WebGL, so it starts with a few seconds of the page loading (the still fallback, then a font swap), and on the 3D
templates the recording stalls and jumps: on W2 it can show no scroll at all, only the hero. Do not post it or
hand it over as a video. If the user wants a video of the site to post, make that as its own piece (a screen
recording of the live page, edited) and gate that file with the engine's QA run (`engine/qa.py`; the video-gates
skill in the video-engine plugin explains the report). Do not run `qa.py` on `_scroll.mp4` to "check" it: it
FAILs by design (1440x900 at 30 fps with no sound against the profile's delivery size and rate, the load hold and
the end hold flagged as dead air, no strong moment by 2 s), and none of that is a fault in the site.

## 5. Worked examples (fresh clone, demo profile)

**W2 isometric world** (`examples/sites/demo-world/site.json`): "How a live stream reaches you" for a placeholder
ACME TV. Five scenes (`field`, `switcher`, `encoder`, `stream`, `home`), then text, features and FAQ sections. No
photos.

```bash
cd "$VIDEO_ENGINE"
python3 web/build.py examples/sites/demo-world/site.json --out out/demo-world --profile demo
python3 web/compliance.py out/demo-world --site examples/sites/demo-world/site.json
python3 web/preview.py out/demo-world --out out/demo-world_preview --name demo-world
```

**W5 glass showcase** (`examples/sites/demo-studio/site.json`): a fictional architecture and interiors photography
studio (Northlight Studio) with three portfolio chapters (residential, hospitality, workplaces), a second ghost
button (`cta2`), then features, process, text and a mailto CTA (no form, so no endpoint to set).

```bash
cd "$VIDEO_ENGINE"
python3 web/build.py examples/sites/demo-studio/site.json --out out/demo-studio --profile demo
python3 web/compliance.py out/demo-studio --site examples/sites/demo-studio/site.json
python3 web/preview.py out/demo-studio --out out/demo-studio_preview --name demo-studio
```

Expected on a fresh clone (both checked): the build line ends `template w2, 3 sections, 4 logged assets, 1.0 MB`
(`w5, 4 sections` for the studio), and each gate prints `compliance: PASS (0 fail, 4 for the owner)`. The 4 owner
items are the three DRAFT legal pages and the physical-address question; they are expected, not failures. The
sheets show every scene and chapter; the scroll videos behave as described in section 4.

To start a new site, copy the example closest to the job into a new folder, change the template if needed, and
rewrite every fact. If the gate reports a font license FAIL on a profile, put the `OFL-<Family>.txt` license beside
each font file in that profile (the bundled fonts' licenses are in `resources/fonts/`) and rebuild.

## 6. Built in: what the kit does so you don't have to

- **Legal pages** drafted from the site's facts: what each form field is for, who it is shared with (form
  processors, any `third_party`), retention, cookies, children, and a data-deletion route with a working mailto or
  tel link. All linked in every footer, all marked DRAFT until approved.
- **Consent**: a cookie policy and banner only when something non-essential loads; Accept and Reject the same size
  and weight; nothing loads before a choice.
- **Forms**: labels, an unchecked consent box with the privacy link, no pre-checked boxes, native validation, no
  urgency, countdowns or confirm-shaming.
- **Accessibility**: a skip link, Tab reaches every control with a visible focus style, alt text on every image,
  contrast measured in the browser against the real pixels (4.5:1, 3:1 large), no sideways scroll on a phone,
  `prefers-reduced-motion` respected.
- **Colors** derived from the profile until body text, muted text and the accent pass 4.5:1 on a dark ground.
  Change the profile's colors, not the CSS, when the user wants a different look.
- **Motion**: UI springs from `engine/spring.js` (`ui` in, `uiExit` out, no bounce, opacity never overshoots).
- **Assets**: the profile's fonts ship with their license files; `assets.json` lists every file's source and
  license; three.js (MIT) ships inside the site.

Don't add analytics, chat widgets, ad pixels, embeds, web fonts from a CDN or anything that uploads visitor data
unless the user asks; when they do, add it through `third_party` so it is consent-gated and named in the policies.

## 7. Report back

Tell the user where the built folder is (it is ready to upload to any static host they choose; nothing is
published by these tools), show the preview sheets, give the gate verdict, and list only what needs them, taken
from the report's "Needs the owner": the form endpoint, the legal wording review, image rights marked
`UNSPECIFIED`, an address if they sell online, and any claim that needs a source.
