# Layout and the profile API (for tool authors)

## Where things go

- `engine/` generic tools. No organization's paths, colors, fonts or names in code: ask the profile.
- `packs/<org>/` optional: your own workflows (one organization's recipes and logic). Git-ignored, so they stay
  out of the engine's repository. They use the profile too.
- `logo/`, `cutouts/` generic tool groups with their own setup.
- `web/` the website kit (`build.py`, the compliance gate, previews, templates).
- `examples/` ready-made inputs for the demo profile.
- `plugins/` the Claude plugins (`video-engine`, `ui-kit`).
- `profiles/<name>/profile.json` one organization; `profiles/_template/profile.json` is copied by `vprofile.py new`.
- `resources/fonts/`, `resources/models/` shared files that profiles point at with `{repo}/resources/...`.
- `tests/` self-tests (synthetic input, output only under `tests/out/`).
- Paths in code come from the profile, the command line or `__file__`. Never an absolute path.

## Using a profile in a tool

```python
import argparse, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "engine"))
import vprofile as prof                     # (from an optional packs/<org>/ folder, go up one more level)

ap = argparse.ArgumentParser()
prof.add_arg(ap)                            # adds --profile
a = ap.parse_args()
P = prof.load(a.profile)                    # --profile, else $VIDEO_PROFILE, else local.json "default_profile"
```

| Call | Returns |
|---|---|
| `P.color('primary' \| 'accent' \| 'text')` | `"#RRGGBB"` |
| `P.rgb(role)` | `(r, g, b)` |
| `P.font('head' \| 'body' \| 'body_semibold')` | absolute path of the font file |
| `P.path('assets' \| 'music' \| 'root' \| ...)` | absolute folder, path map applied |
| `P.has_path(key)` | whether the profile defines that folder |
| `P.asset('brand.logo_png')` | a file stored anywhere in the profile, expanded and path-mapped |
| `P.get('team.home_name')`, `P.get('delivery.loudness_lufs', -14)` | any value by dotted key; a default instead of an error |
| `P.text('brand.watch_line')` | a string with `{tokens}` expanded |
| `P.map_path(p)` | a path from an edit list, rewritten for this machine |
| `P.check()` | list of missing fonts, folders and assets (what `vprofile.py show --check` prints) |

Rules:
- An explicit command-line flag always beats the profile (keep old flags working when you generalize a tool).
- A value the profile may lack: `P.get('some.key', <default>)`, and add the key to `profiles/_template/profile.json`.
- Paths inside edit-list JSON are data: map them when you read them (`P.map_path`), don't rewrite the file.
- Tools that need no brand or folder values don't load a profile at all.

## profile.json keys

| Key | Meaning |
|---|---|
| `name`, `display_name` | folder name; the name shown on sample cards |
| `brand.colors.*` | `primary`, `accent`, `text`, plus any extra roles a tool asks for |
| `brand.fonts.*` | `head`, `body`, `body_semibold` (paths; relative ones are inside the profile folder) |
| `brand.logo_svg`, `brand.logo_png`, ... | logo files (keys ending `_png`, `_svg`, `_mp4`, `_mov` are checked by `--check`) |
| `brand.watch_line` | the "where to watch" line on end cards |
| `brand.call_sign`, `brand.lockup_title`, `brand.lockup_line` | optional defaults for the logo `lockup` template's three lines (top line, outlined headline, subline) when `--text1/2/3` aren't given |
| `team.home_abbr`, `team.home_name`, `team.foot` | short name, display name, footer line |
| `paths.*` | folders; may use `{repo}`, `{profile}`, `{home}` and other `paths` keys. `*_out` folders may not exist yet |
| `path_map` | `[[from, to], ...]`: a path under `from` becomes `to` when `from` is missing here and `to` exists |
| `delivery.*` | `size`, `fps`, `vertical_size`, `loudness_lufs`, `true_peak_db`, `outputs` (qa.py checks against these) |
| `layout.safe_px` | title-safe margin in pixels (drawn on the qa.py sheet) |
| `style.*` | house style, e.g. `audio_fade_ms`, `springs_default` |
| `folders.read_only`, `folders.write_into` | folders tools must never write to, and where outputs go |

Check a profile with `python3 engine/vprofile.py show <name> --check`.
