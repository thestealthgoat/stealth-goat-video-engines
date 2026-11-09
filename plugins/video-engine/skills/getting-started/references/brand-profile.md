# Brand profile reference

A profile is `profiles/<name>/profile.json` in the engine folder. `python3 engine/vprofile.py new <name>` copies
`profiles/_template/profile.json`, so every key below is already there with a neutral value. Change what the brand
needs; leave out what it does not have. The full tool-author view is `docs/LAYOUT.md` in the engine folder.

## The `new` command

```bash
cd "$VIDEO_ENGINE"
python3 engine/vprofile.py new <name> [--display "Shown Name"] [--primary "#RRGGBB"] [--accent "#RRGGBB"]
                                      [--head-font FILE] [--body-font FILE] [--logo FILE.svg|FILE.png]
                                      [--root FOLDER] [--sample]
```

- Stops if `profiles/<name>` already exists (edit that profile.json instead).
- `--head-font` / `--body-font` / `--logo` are copied into `profiles/<name>/assets/` and the profile points at the
  copies. An `.svg` logo becomes `brand.logo_svg`; anything else becomes `brand.logo_png`. To have both, run `new`
  with the SVG and add the PNG by hand (copy it into `assets/`, add `"logo_png": "assets/<file>.png"` under `brand`).
- `--root` sets `paths.root` (default `{home}/Movies/video-work`).
- `--sample` writes `profiles/<name>/sample_card.png` (the brand card).

Other commands: `list`, `show <name> [--check]`, `default <name>` (writes `local.json`), `sample <name> <out.png>`.

## Keys

| Key | What to put there |
|---|---|
| `name` | the folder name (set by `new`) |
| `display_name` | the name shown on the brand card and some titles, e.g. "ACME Studio" |
| `brand.colors.primary` | panel and bar ground; also the default preview background |
| `brand.colors.accent` | edges, highlights, the second line on end cards |
| `brand.colors.text` | text on primary (usually `#FFFFFF`) |
| `brand.colors.primary_deep`, `text_dim` | optional; tools derive them when missing (a darker primary, a dimmer text) |
| `brand.fonts.head` | headline face (relative paths are inside the profile folder; `{repo}/resources/fonts/...` also works) |
| `brand.fonts.body`, `body_semibold` | body and label faces |
| `brand.fonts.mono` | optional; explainers use it for readouts (else body_semibold) |
| `brand.logo_svg` | the vector logo (logo-motion, logo-3d) |
| `brand.logo_png` | transparent PNG logo (stats card, flipbook, vertical wraps) |
| `brand.watch_line` | the "where to watch" line on end cards, e.g. "ACME TV · YOUTUBE" |
| `team.home_abbr`, `team.home_name`, `team.foot` | short name, display name in caps, footer line (sports and clubs; leave empty otherwise) |
| `paths.root`, `paths.assets`, `paths.music` | working folders; may use `{home}`, `{repo}`, `{profile}` and other `paths` keys (`"{root}/Assets"`) |
| `optional_paths` | `paths` keys that exist only on some machines; `show --check` lists them instead of failing |
| `path_map` | `[["/old/prefix", "~/new/prefix"]]`: rewrites paths from an edit list made on another machine |
| `delivery.size`, `vertical_size` | `"1920x1080"`, `"1080x1920"` |
| `delivery.fps` | `29.97002997` (US), `25` (PAL regions), `59.94005994` for 60p work |
| `delivery.fps_allowed` | other rates qa.py accepts, e.g. `[59.94005994]` |
| `delivery.loudness_lufs`, `true_peak_db` | `-14` and `-2` suit YouTube and social; qa.py checks against them |
| `delivery.outputs` | `["mp4", "premiere_xml"]` |
| `layout.safe_px` | title-safe margin in pixels, drawn on the QA sheet (default 90 at 1080p) |
| `style.audio_fade_ms`, `style.springs_default` | house style: audio fade at every cut; the default spring (`snappy`) |
| `captions.*` | kinetic caption look: font role, size, stroke, box color, position (template values are a good start) |
| `talkedit.*` | talking-head edit defaults: pause trimming, fillers, punch-in zooms, cards, music level |
| `explain.signal`, `explain.hot`, `explain.key` | optional explainer colors (signal gold, the answer color, the caption keyword box) |
| `explain.font_scale`, `explain.head_caps` | optional: scale explainer text (e.g. 1.2 for a condensed face); `true` for a caps-only head face |
| `finish.dark` | optional settings for `motion.py --finish dark` (bg, bloom, floor, dof, grain, vignette) |
| `folders.read_only`, `folders.write_into` | folders tools must never write to, and where outputs go |

Colors in hex with the `#`. Values that are paths are expanded: `{home}` is the user's home folder, `{repo}` the
engine folder, `{profile}` the profile's folder.

## Fonts

- Use open-license (SIL OFL) fonts so renders, project files and the profile can be shared. The engine folder's
  `resources/fonts/` holds several with their `OFL-*.txt` license texts; Google Fonts families are OFL too
  (download the static `.ttf` files, not the variable font, and keep the license text next to them).
- Three roles cover nearly everything: `head` (a bold display face), `body`, `body_semibold`. A condensed body face
  fits more on a lower third.
- After a font change, re-run `vprofile.py sample` and check every specimen line renders.

## Logo

- SVG first. Flat fills and closed shapes animate and extrude best; text should be converted to outlines.
- No SVG? The logo-vectorize skill turns a JPG, PNG or screenshot into a clean SVG plus transparent PNGs.
- Keep the files in `profiles/<name>/assets/` so the profile is self-contained.

## Checking

```bash
python3 engine/vprofile.py show <name> --check    # exit 0 and "CHECK: OK", or a list of what is missing
python3 engine/vprofile.py sample <name> ~/Movies/video-work/<name>_card.png
```

On the brand card, check: the display name in the head face; the logo top right ("no logo in this profile yet" if
there is no `logo_png` or `logo_svg`); one swatch per color with its contrast against the card's dark ground; each
font role as a specimen line (a role that cannot load is printed in red); and the sample lower third with
`text on primary N:1`. Aim for 4.5:1 or more; below that the card adds `(below 4.5:1)`.
