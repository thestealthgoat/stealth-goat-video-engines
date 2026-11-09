# Redraw mode reference

Rebuild a logo from measured shapes and real-font lettering when a trace cannot work (3D mockups, embossed or metal
renders, photos of signs, baked-in lighting). Work in a folder outside the engine (e.g. `~/logo-work/<name>/` or the
`_vector/` folder beside the source).

## 1. Gridded enlargements for measuring

`redraw.py` has no measuring tool; write this small helper into the work folder as `grid.py`:

```python
"""grid.py <src> <out.png> <step_px> <scale> [x0,y0,x1,y1]  - enlarged copy with a labeled grid in source pixels."""
import sys
from PIL import Image, ImageDraw
src, out, step, scale = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
box = tuple(int(v) for v in sys.argv[5].split(',')) if len(sys.argv) > 5 else None
im = Image.open(src).convert('RGBA')
bg = Image.new('RGBA', im.size, (128, 128, 128, 255)); bg.alpha_composite(im); im = bg.convert('RGB')
ox, oy = (box[0], box[1]) if box else (0, 0)
if box: im = im.crop(box)
im = im.resize((im.width * scale, im.height * scale), Image.NEAREST)
dr = ImageDraw.Draw(im)
for x in range((ox // step) * step, ox + im.width // scale + 1, step):
    X = (x - ox) * scale; dr.line([(X, 0), (X, im.height)], fill=(255, 0, 255) if x % (step * 4) == 0 else (0, 200, 255)); dr.text((X + 2, 2), str(x), fill=(255, 0, 255))
for y in range((oy // step) * step, oy + im.height // scale + 1, step):
    Y = (y - oy) * scale; dr.line([(0, Y), (im.width, Y)], fill=(255, 0, 255) if y % (step * 4) == 0 else (0, 200, 255)); dr.text((2, Y + 2), str(y), fill=(255, 0, 255))
im.save(out)
```

```bash
python3 grid.py "$VIDEO_ENGINE/profiles/demo/assets/demo_logo.png" grid_full.png 25 2              # whole logo, 25 px grid
python3 grid.py "$VIDEO_ENGINE/profiles/demo/assets/demo_logo.png" grid_M.png 10 4 280,90,420,300  # one area at 4x, 10 px grid
```

Labels are in the reference's own pixel coordinates, so numbers read off any enlargement go straight into the
redraw script. `Read` each image and write down every corner, stroke end and the ink box (left, top, right, bottom)
of each line of lettering. For straight-on flat art you can also measure an ink box with numpy (pixels darker than a
threshold inside a region).

## 2. Font matching: `logo/fontmatch.py`

```
python3 "$VIDEO_ENGINE/logo/fontmatch.py" <image> "<TEXT>" x0,y0,x1,y1 <fonts_dir> [--thresh 72] [--top 6]
```

- Crops the box, builds a letter mask (pixels darker than `--thresh` L*, or lighter than `-thresh` when negative),
  renders TEXT in every `.ttf`/`.otf` directly in `fonts_dir` (variable fonts at weights 600/700/800/900), stretches
  each to the mask's ink box and ranks by IoU.
- Prints `IoU  font-file [wght N]` for the top matches and writes `fontmatch_<TEXT>.png` (gray = logo letters, red =
  font outline) **into the current folder**, so `cd` into the work folder first.
- ≥ 0.80 is usually the same family or close enough to rebuild; compare the overlay for tell-tale letters (R legs,
  G spurs, Q tails).
- `--thresh 62` works for dark letters on a mid-bright ground; use a negative value (e.g. `-60`) for light letters on
  dark.
- The engine ships a few OFL fonts in `resources/fonts/`. For more candidates, download OFL families from the
  google/fonts repository on GitHub into a candidates folder (tell the user what you are fetching), then point
  `fonts_dir` at that folder. Starting points by style:

| Style | Try |
|---|---|
| Squared / rounded tech | Titillium Web Black, Saira, Exo 2, Russo One |
| Condensed sans | Anton, Bebas Neue, Teko, Oswald, Barlow Condensed |
| Slab / collegiate | Graduate, Alfa Slab One |
| Geometric sans | Montserrat, Poppins |
| Script | identify the family first (look up the style), then fetch it |

## 3. `logo/redraw.py` API

```python
import os, sys
sys.path.insert(0, os.path.join(os.environ['VIDEO_ENGINE'], 'logo'))
from redraw import Doc
```

| Call | Draws |
|---|---|
| `Doc(w, h)` | A canvas in the reference image's pixel space. |
| `d.poly(pts, fill, holes=())` | A straight-edged shape from `[(x, y), ...]`; each entry of `holes` is another point list cut out (even-odd). |
| `d.rect(x0, y0, x1, y1, fill, holes=())` | A rectangle (with optional holes). |
| `Doc.rect_pts(x0, y0, x1, y1)` | The four corner points, handy as a hole: `holes=[Doc.rect_pts(...)]`. |
| `d.line(a, b, width, fill)` | A stroke from point a to b, as a filled quad (extrudes in 3D). |
| `d.polyline(pts, width, fill)` | Joined strokes (one quad per segment). |
| `d.text(s, font_path, (x0, y0, x1, y1), fill, tracking=0.0)` | The string in real font outlines, its ink box stretched to exactly fill the box. `tracking` adds letter spacing in em. |
| `d.save(path)` / `d.svg()` | Write / return the SVG. |
| `d.check(ref_path, out_path, scale=2)` | Reference \| redraw on gray \| redraw outline (cyan) over the reference. |

There are no curves or rounded corners: approximate arcs with short segments, e.g.

```python
import math
def rounded(x0, y0, x1, y1, r, n=8):
    pts = []
    for cx, cy, a0 in ((x1 - r, y0 + r, -90), (x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180)):
        pts += [(cx + r * math.cos(math.radians(a0 + 90 * i / n)), cy + r * math.sin(math.radians(a0 + 90 * i / n)))
                for i in range(n + 1)]
    return pts
```

For a complex illustration (a mascot, a crest), redraw the lettering and geometric parts, and consider tracing a
cleaned, flat-colored crop of the illustration with `vectorize.py`, then stacking both in one SVG.

## 4. Worked example (demo profile logo)

`redraw_demo.py` in the work folder:

```python
import math, os, sys
E = os.environ['VIDEO_ENGINE']
sys.path.insert(0, os.path.join(E, 'logo'))
from redraw import Doc

def rounded(x0, y0, x1, y1, r, n=8):
    pts = []
    for cx, cy, a0 in ((x1 - r, y0 + r, -90), (x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180)):
        pts += [(cx + r * math.cos(math.radians(a0 + 90 * i / n)), cy + r * math.sin(math.radians(a0 + 90 * i / n)))
                for i in range(n + 1)]
    return pts

ref = os.path.join(E, 'profiles/demo/assets/demo_logo.png')     # 551 x 320
d = Doc(551, 320)
d.poly(rounded(0, 20, 551, 300, 40), '#F2B705')                 # the plate
d.text('DEMO', os.path.join(E, 'resources/fonts/Anton-Regular.ttf'), (49, 98, 503, 290), '#0B3D2E')
d.save('demo_redraw.svg')
d.check(ref, 'demo_redraw_check.png')
```

```bash
mkdir -p ~/logo-work/demo && cd ~/logo-work/demo && python3 redraw_demo.py
```

The ink box (49, 98, 503, 290) was measured off the grid; Anton came from `fontmatch.py`. A first guess of 258 for
the bottom edge made the letters visibly short in the check image; measuring again fixed it. That is the loop: check,
re-measure, re-run, until no edge drifts more than a few px.

## 5. Finish

- Keep the per-logo script with the outputs (`_vector/`), so the redraw can be adjusted later.
- Render a transparent PNG from the SVG if needed:
  `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib python3 -c "import cairosvg; cairosvg.svg2png(url='demo_redraw.svg', write_to='demo_redraw-4000px.png', output_width=4000)"`
  (the variable lets cairosvg find Homebrew's libcairo on macOS; it is harmless elsewhere).
- Report it as a redraw, never as the original artwork.
