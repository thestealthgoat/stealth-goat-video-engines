# Stealth Goat video engines

Code-first video tools for small production teams: contact sheets, keyframe-safe clip cutting, Premiere-ready XML,
beat-accurate cut snapping, logo vectorizing, 3D and motion graphics with alpha, background-removed cutouts, and a
QA gate that checks every finished video before anyone sees it. Python + ffmpeg, free and open-source tools only.

Nothing about any one organization is hard-coded. Brand colors, fonts, logos, folders and delivery specs live in a
**profile**, so the same tools render for any team, club, church or business.

## What is here

| Folder | What it does |
|---|---|
| `engine/` | the core tools (below) and `vprofile.py`, the profile loader |
| `logo/` | logo vectorize / redraw, 3D extrusion (stills, swing loop, GLB), animated logo templates with alpha |
| `cutouts/` | person cutouts from photos, graded and filed into a per-person library |
| `profiles/_template/` | the starting point for your own profile |
| `packs/<org>/` | where one organization's own workflows go (none ship here) |
| `resources/` | open-licence fonts (`fonts/`, OFL texts beside them); `models/` is where the optional super-resolution models go (not committed; download links in `logo/README.md`) |
| `vendor/` | third-party code kept unchanged, with its licence (see `NOTICE.md`) |
| `tests/` | self-tests on synthetic input |
| `docs/` | `LAYOUT.md` (profile API for tool authors), `ffmpeg-notes.md` |

Core tools in `engine/`:

- `qa.py` - one-command QA gate: spec, dead stretches and stutters, hard audio cuts, loudness and true peak,
  unplanned cuts, flash frames, clicks, hook and hold checks. Writes `review.md` + a review sheet.
- `audio_check.py`, `motion_check.py` - the audio and motion gates on their own.
- `spring.py` / `spring.js` - closed-form damped springs (seekable by time) for anything animated; see
  `engine/README_motion.md`.
- `beatmap.py` + `beatsnap.py` - a bar map of a music track, and cut snapping onto its beats, downbeats and drop.
- `sheet.py` (contact sheets), `clip_plays.py` (stream-copy cuts from a list), `fcp7xml.py` (edit list to FCP7 XML
  that Premiere imports), `vertical.py` (9:16 wrap of a 16:9 piece), `flipbook.py` (burst photos to stop-motion),
  `calls.py` (local faster-whisper transcripts), `cutout.py`, `encode.py`, `offload.py` (safe, resumable card copy).

## Profiles

A profile is one JSON file, `profiles/<name>/profile.json`. Example for a fictional organization, the
**Harbor City Otters**, a rec-league hockey club that streams its games:

```bash
python3 engine/vprofile.py new otters --primary "#0B3D5C" --accent "#F2A900" \
    --head-font ~/Fonts/Oswald-Bold.ttf --body-font ~/Fonts/Inter-SemiBold.ttf \
    --logo otters.svg --root ~/Movies/Otters --sample
python3 engine/vprofile.py show otters --check     # every font, folder and logo exists on this machine?
python3 engine/vprofile.py default otters          # this machine's default (writes local.json, not committed)
```

That writes `profiles/otters/profile.json` (fonts and logo copied into `profiles/otters/assets/`) and a sample lower
third to look at. Then fill in the rest:

```json
{
  "name": "otters",
  "display_name": "Harbor City Otters",
  "brand": {
    "colors": { "primary": "#0B3D5C", "accent": "#F2A900", "text": "#FFFFFF" },
    "fonts":  { "head": "assets/Oswald-Bold.ttf", "body": "assets/Inter-SemiBold.ttf",
                "body_semibold": "assets/Inter-SemiBold.ttf" },
    "logo_svg": "assets/otters.svg",
    "watch_line": "OTTERS TV · YOUTUBE"
  },
  "team": { "home_abbr": "HCO", "home_name": "OTTERS", "foot": "WATCH EVERY OTTERS GAME" },
  "paths": { "root": "{home}/Movies/Otters", "assets": "{root}/Assets", "music": "{assets}/Music" },
  "path_map": [["/srv/otters", "~/otters-share"]],
  "delivery": { "size": "1920x1080", "fps": 29.97002997, "loudness_lufs": -14, "true_peak_db": -1 },
  "layout": { "safe_px": 90 }
}
```

Values can use `{repo}`, `{profile}`, `{home}` and any key under `paths` (`"{assets}/Music"`). `path_map` rewrites
a path from an edit list when its left side is missing on this machine and the right side exists, so one edit list
works on a workstation, a laptop and a cloud box.

Which profile a tool uses: `--profile <name>`, else `$VIDEO_PROFILE`, else `local.json`. Tools that need no brand
or folder values (sheet, clip_plays, fcp7xml, audio_check, motion_check) don't take one.

## Quick start (macOS, Apple silicon)

```bash
./setup.sh --check        # report what is there and what is missing; ./setup.sh installs what is missing
python3 engine/vprofile.py new otters --primary "#0B3D5C" --accent "#F2A900" --sample
python3 engine/sheet.py game.mp4 sheet.jpg 0 60 --n 12
python3 engine/qa.py finished.mp4 --profile otters --kind edit --cuts 1.5,4.2,7.9
python3 logo/motion.py otters.svg out/ Otters intro --profile otters --frames 0.3,0.8,2.0
```

`setup.sh` is safe to run again. It installs with Homebrew `ffmpeg imagemagick tesseract node cairo`, runs
`python3 -m pip install --user -r requirements.txt` and `logo/setup.sh`, warns about known traps, prints the shell
lines to add, and checks your default profile. Notes:

- Use the native ffmpeg from Homebrew (`/opt/homebrew/bin` first in `PATH`). Pass `-nostdin` to every ffmpeg call
  and bound every `apad` (`apad=whole_dur=<s>`): see `docs/ffmpeg-notes.md`.
- cairosvg needs `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib`.
- python.org Python needs its CA certificates (`Install Certificates.command`, or `certifi` + `SSL_CERT_FILE`).
- Install only one OpenCV wheel (`opencv-python-headless`).

## Tests

```bash
for t in tests/test_*.py; do python3 "$t" || echo "FAILED: $t"; done
```

Each test prints PASS / FAIL / SKIP per case, writes to `tests/out/` (and a temporary folder), and exits non-zero on
any failure. They need `ffmpeg`, `node` and the Python packages in `requirements.txt`; no network share or private
media. Optional real-music case: `QA_TEST_MUSIC=<a music file> python3 tests/test_qa.py`.

## Rules the tools follow

- Source footage is read-only. Tools write into the output folder you give them, never over the source.
- Nothing is deleted: superseded renders are moved to `_old/`.
- Every animated thing moves on springs; every cut, start and end fades its audio; nothing ships without `qa.py`.

## Licence

MIT, see `LICENSE`. Third-party code in `vendor/` keeps its own licence (see `NOTICE.md`).
