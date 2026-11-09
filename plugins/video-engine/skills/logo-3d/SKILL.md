---
name: logo-3d
description: Turns any SVG logo into 3D with the local video engine (logo/render3d.py, three.js extrusion in headless Chromium) - transparent 4K hero and front stills, a seamless swing or spin loop as ProRes 4444 alpha .mov plus an MP4, and a Draco-compressed GLB model - every color kept, layered artwork raised in steps, grays rendered as metal. Use when the user says "3D version of our logo", "make our logo 3D", "extrude this logo", "spinning logo", "logo loop for the stream", "logo turntable", "3D logo for a thumbnail", "GLB of our logo" or "3D logo for Blender".
---

# Logo 3D

Make 3D versions of a logo with `logo/render3d.py` in the engine folder. It loads an SVG with three.js `SVGLoader`,
extrudes every filled path (the same approach as the open-source 3dsvg project, MIT), keeps each fill's own color,
raises stacked artwork in small steps (a new layer each time the fill color changes) and renders neutral grays as
brushed metal. Everything runs locally; nothing is uploaded.

Options, outputs, timings and fixes are in [references/render3d.md](references/render3d.md). Read it before changing
a default.

## 0. Find the engine and the profile

- Use `$VIDEO_ENGINE` as the engine folder and run every command from it: `cd "$VIDEO_ENGINE" && python3 logo/...`.
  If `$VIDEO_ENGINE` is unset or the folder has no `logo/render3d.py`, ask the user where the engine is, or run the
  **getting-started** skill to clone and set it up.
- Make sure the logo tools are installed: `logo/node_modules/.bin/gltf-transform` must exist. If it doesn't, run
  `logo/setup.sh` once (npm packages, Python packages, Playwright Chromium). It works from any folder.
- Pick the profile: `--profile <name>`, else `$VIDEO_PROFILE`, else `local.json`. The profile supplies the default MP4
  background (`brand.colors.primary`) and the `preview.py` background. Use `--profile demo` to try things. When the
  user has no profile yet, offer to make one from `profiles/_template` (`python3 engine/vprofile.py new <name>`, see
  `docs/LAYOUT.md`) or use the **getting-started** skill. `profiles/demo` ships with the engine; if
  `python3 engine/vprofile.py list` doesn't show `demo` (an older clone), make it with
  `python3 engine/vprofile.py new demo --display "Demo" --primary "#0B3D2E" --accent "#F2B705" --sample`.
- Check the profile when in doubt: `python3 engine/vprofile.py show <name> --check`. The demo profile ends
  `CHECK: OK` on a fresh machine (its working folders are optional). A user's own profile may report
  `CHECK: missing` for `paths` folders that don't exist yet; logo-3d uses none of them, so only color and font
  errors matter here.

## 1. Get a vector

- Need an SVG with **filled** paths. Stroke-only paths (`fill="none"`) are skipped by the renderer, so outline
  artwork must be converted to filled shapes first (Inkscape "Stroke to Path", or redraw it).
- Look for the user's master file first: the profile's `brand.logo_svg` (in `profiles/<name>/profile.json`), a
  brand kit, or a file they hand over.
- If there is only a PNG, JPG, screenshot or photo of a mockup, run the **logo-vectorize** skill first and use its SVG.
- Logos that belong to someone else (a partner, sponsor or client) are fine to render for that relationship; ask the
  user to confirm they have permission to use the mark.

## 2. Quick look first (stills only, a few seconds to about 30 s)

Run a stills-only pass, then look at it before spending minutes on the loop:

```bash
cd "$VIDEO_ENGINE"
python3 logo/render3d.py path/to/logo.svg out/logo3d ACME_Mark --profile demo --still-only
python3 logo/preview.py out/logo3d/check.png out/logo3d/ACME_Mark_3D_Hero_4K.png out/logo3d/ACME_Mark_3D_Front_4K.png --profile demo
```

`render3d.py` prints `paths N` (the number of filled shapes it extruded), and a line when `--drop-bg` dropped a
background. `preview.py` composites each transparent still on the profile's primary color and stacks them into one
1280-wide sheet. `Read` the sheet and check:

- **Colors**: every color of the logo is there and nothing has collapsed into one color. A part whose color
  equals the profile's primary color disappears into the preview background; composite on a contrasting color
  as well:
  ```bash
  python3 -c "from PIL import Image;import sys;im=Image.open(sys.argv[1]).convert('RGBA');b=Image.new('RGBA',im.size,sys.argv[2]);b.alpha_composite(im);b.convert('RGB').resize((1280,720)).save(sys.argv[3])" out/logo3d/ACME_Mark_3D_Hero_4K.png '#FFFFFF' out/logo3d/hero_on_white.png
  ```
- **Thickness**: letters are not too fat. Default `--depth 0.03` (fraction of the logo's longest side). Use `0.02` for thin type
  and lettering, `0.05` for a chunky single mark.
- **Framing**: nothing is clipped at the frame edge (`--fill` is the share of the frame the widest side fills,
  default 0.78), and the hero angle reads well (`--hero "rx,ry"` in radians, default `"0.10,-0.30"`).
- **Background plate**: if a white or colored rectangle fills the whole canvas behind the logo, it is an export
  background; rerun with `--drop-bg`. Leave it on for a square badge or a traced silhouette that is part of the logo.

Fix and rerun the stills until they are right.

### Worked example (fresh clone, demo profile)

No logo needed: write a small three-color mark and render it.

```bash
cd "$VIDEO_ENGINE" && mkdir -p out/logo3d
cat > out/logo3d/acme.svg <<'EOF'
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 300">
  <path fill="#F2B705" d="M200 20 L380 280 L20 280 Z"/>
  <path fill="#0B3D2E" d="M200 90 L310 250 L90 250 Z"/>
  <rect fill="#9A9A9A" x="160" y="200" width="80" height="30"/>
</svg>
EOF
python3 logo/render3d.py out/logo3d/acme.svg out/logo3d ACME_Mark --profile demo --still-only
python3 logo/preview.py out/logo3d/check.png out/logo3d/ACME_Mark_3D_Hero_4K.png out/logo3d/ACME_Mark_3D_Front_4K.png --profile demo
```

Expected: `paths 3`, then `ACME_Mark_3D_Hero_4K.png`, `ACME_Mark_3D_Front_4K.png` and `ACME_Mark_3D.glb` in
`out/logo3d/`. The gray bar renders as metal. A new layer starts at each fill-color change, so yellow is layer 0,
green layer 1 and gray layer 2: the gray bar sits one step in front of the green triangle it rests on (two above the
yellow). The green inner triangle matches
the demo profile's primary color, so it vanishes in `check.png`: this is the case the contrasting composite above
is for.

## 3. Full render (under a minute for simple marks, several minutes for detailed traced logos)

```bash
python3 logo/render3d.py path/to/logo.svg out/logo3d ACME_Mark --profile demo --bg '#FFFFFF'
```

- `--bg` sets the MP4 background only (with or without `#`; quote it, `#` starts a shell comment). Default: the
  profile's primary color. Pick a color the logo reads on: a dark brand color for light logos, white for dark ones.
  Every PNG and the .mov stay transparent.
- The default loop is **swing**: a seamless sway of about +/-25 degrees with a slight nod, so the logo is never seen
  backwards. Use `--anim spin` (a full turn) only when the user asks for it. Loop length is `--spin-seconds`
  (default 4) at `--fps` (default 60).
- Run one heavy render at a time. For several logos, run them one after another in a single background shell loop,
  never in parallel:
  ```bash
  for f in logos/*.svg; do n=$(basename "$f" .svg); python3 logo/render3d.py "$f" out/logo3d "$n" --profile demo; done
  ```
- Reuse the same `--depth`, `--hero`, `--fill` and `--drop-bg` you settled on in step 2.

## 4. Check the loop, then QA it

1. Tile frames from the MP4 and `Read` the image (eight frames from a 4 s, 60 fps loop):
   ```bash
   ffmpeg -nostdin -v error -y -i out/logo3d/ACME_Mark_3D_Swing.mp4 -vf "select='not(mod(n,30))',scale=640:-1,tile=4x2" -frames:v 1 out/logo3d/loop_tiles.png
   ```
   Look for clipping at the extremes of the sway, a face going dark, and colors that change between frames.
2. Run the **video-gates** QA run before showing or delivering anything:
   ```bash
   python3 engine/qa.py out/logo3d/ACME_Mark_3D_Swing.mp4 --profile demo --kind loop --cuts none --fps 60 --out out/logo3d/qa_ACME_Mark
   ```
   On the worked example's swing loop this prints `RESULT: PASS (0 warnings)` with the hook, strong-moment and
   end-tail gates listed as SKIP and audio as SKIP (the loop has no audio stream).
   `--kind loop` lists the hook and end-tail gates as SKIP (an ambient loop has no opening or ending of its own).
   `--fps 60` because the loop is 1080p60 while profiles usually deliver 29.97. `--cuts none` because the loop has no
   cuts, so any detected cut is a fault. Read `review.md` and `sheet.jpg` in the review folder and fix every FAIL.
   Exit code 0 is PASS, 1 is FAIL.

## 5. Deliver

Name files `<Owner>_<Logo>` (for example `ACME_Mark`) so a set sorts together. Outputs, all in the output folder:

| File | Use |
|---|---|
| `<Name>_3D_Hero_4K.png`, `<Name>_3D_Front_4K.png` | 3840x2160 transparent stills: thumbnails, graphics, print |
| `<Name>_3D_Swing_Alpha.mov` | 1920x1080 60 fps ProRes 4444 with alpha: overlays and stingers in vMix, Premiere, Resolve |
| `<Name>_3D_Swing.mp4` | the same loop on the `--bg` color, H.264: social and web |
| `<Name>_3D.glb` | Draco-compressed 3D model: Blender, After Effects, a web page |

With `--anim spin` the loop files are `<Name>_3D_Spin_Alpha.mov` and `<Name>_3D_Spin.mp4`.

- Save to the folder the user names. If they don't name one, use a `3D/` folder next to the source SVG. Never overwrite the user's source logo.
- Write a short `README.txt` in that folder listing each file and what it is for, plus the settings used
  (`--depth`, `--hero`, `--bg`, `--anim`) so the set can be re-rendered.
- Delete working files (`check.png`, contrast composites, `loop_tiles.png`) or leave them out of the delivery folder.

## 6. Report

Report in one or two lines: which logos, where the files are, the QA verdict, and anything worth knowing (for example
"the crest was traced from a PNG, not a master file" or "used --drop-bg to remove a white export background").

## Related skills

- **logo-vectorize**: PNG/JPG/screenshot to a clean SVG before this skill.
- **logo-motion**: animated 2D logo graphics (intro, end card, corner bug, stinger) from the same SVG.
- **video-gates**: the QA gate every render passes before delivery.
- **getting-started**: install the engine and make a brand profile.
