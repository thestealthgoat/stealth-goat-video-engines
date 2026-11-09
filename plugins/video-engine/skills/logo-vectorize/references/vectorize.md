# vectorize.py reference

```
python3 logo/vectorize.py <input> <out_dir> <name> [--colors N] [--palette "#hex,#hex"] [--bg auto|none|#hex]
                          [--png-width 4000] [--detail 1.0] [--target 2400] [--flatten-shading] [--bg-light 74]
```

`out_dir` is created if missing. Run it from the engine folder (`cd "$VIDEO_ENGINE"`); input and output paths can
be anywhere.

## Options

| Option | Default | What it does | When to change it |
|---|---|---|---|
| `--palette` | none | Brand hexes, comma-separated. Every palette colour is a candidate layer (so thin outlines in those colours survive) and auto-found colours snap to them. Auto colours far (≥ 60 RGB units) from every palette entry are kept as extra layers. | Always, when you know the brand colours. Add any colour the trace merged or dropped. |
| `--colors` | auto (2–10, by k-means elbow) | Forces the number of flat colours found before palette snapping. | Set it to the real count when you know it; it stops anti-aliased edges becoming a fringe layer. Raise it if two colours merged. |
| `--bg` | `auto` | `auto`: if the image has no transparency and its border is a solid colour, key that colour out, but only where it touches the edge (a same-coloured shape inside the logo stays). `none`: keep everything. `#hex`: key out that exact colour (edge-connected only). | `none` when the logo's own plate or white field is part of the art; `#hex` when `auto` picks the wrong background. |
| `--png-width` | 4000 | Width of the transparent PNG (height follows the aspect). | Larger for print. |
| `--detail` | 1.0 | > 1 keeps smaller details (speckle filter shrinks); < 1 smooths more. | 1.5 for fine lettering or thin rules; 0.7 for noisy JPGs. |
| `--target` | 2400 | Working resolution (long side) for clustering and tracing. | Rarely; raise for very intricate logos. |
| `--flatten-shading` | off | For logos that are already 3D, embossed or photographed: light near-neutral pixels (L* above `--bg-light`) become background, stray shadow blobs are dropped, and colours are grouped by hue/chroma with brightness down-weighted. | Mild lighting or drop shadows. Heavy lighting, perspective or metal: go to a redraw. |
| `--bg-light` | 74 | With `--flatten-shading`: the L* above which a near-neutral pixel counts as background. | Lower if a light-grey shadow survives; raise if light logo parts vanish. |

## Outputs

| File | Contents |
|---|---|
| `<name>.svg` | One `<g fill="#hex">` per colour, stacked bottom (outermost colour) to top; each layer is filled under everything above it, so there are no hairline seams. viewBox is the working size (about 2400 px long side). |
| `<name>_Transparent_<W>px.png` | The SVG rendered with a transparent background at `--png-width`. |
| `<name>_vector_check.png` | Three panels on grey: original, vector, difference. Difference: red = shape the vector missed, blue = shape it added, elsewhere colour error ×3 (near black = match). |

Printed lines: `layer #hex  area NN.N%  paths N` per colour, then
`FIDELITY silhouette IoU X.XXX  mean colour error N.N/255  colours N`.

## Reading the score

- **IoU** compares the silhouette (alpha > 50 %) of the vector with the background-removed original at the working
  size. ≥ 0.98 is good; 0.97–0.98 needs a close look at the check image; below 0.97 something is missing or added.
- **Colour error** is the mean RGB difference over pixels both cover. ≤ 20/255 is good. A high error with a high IoU
  usually means a colour snapped to the wrong palette entry, or gradients were flattened (expected for gradient
  logos: say so).
- A good score does not prove thin details survived: a 1 px outline barely moves IoU. Always read the check image.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Two brand colours merged into one layer | Put both in `--palette`, or raise `--colors`. |
| A thin outline vanished | Add its colour to `--palette`; raise `--detail` to 1.5. |
| Extra small layer of an in-between colour (anti-aliasing fringe) | Set `--colors` to the true count. |
| Lumpy curves, rounded corners that should be sharp | Raise `--detail`; use a larger source. |
| JPEG blocks or noise traced as speckles | Lower `--detail` to 0.7. |
| White inner plate or field removed | `--bg none` (and crop the image to the logo first if it has a big border). |
| Background left behind | `--bg "#hex"` with the measured background colour. |
| Small source (< 700 px) looks soft | Check `logo/srenv/bin/python` and the model exist (`resources/models/EDSR_x4.pb` up to 600 px long side, `FSRCNN_x4.pb` for 601–699 px; `logo/setup.sh` makes them) and that no `sr.py` traceback was printed; otherwise it used Lanczos. |
| Shadows join shapes, colours a few units apart, blotchy check | Try `--flatten-shading` once, then switch to a redraw. |
| `ImportError` for vtracer / cairosvg / sklearn | Run `logo/setup.sh`; on macOS cairosvg also needs Homebrew `cairo` (`./setup.sh` installs it). |

## Notes for scripts you write

- `vectorize.py` calls vtracer with **positional** arguments on purpose: some vtracer builds crash on keyword
  arguments under newer Python versions. Any vtracer call you write yourself must be positional too.
- On macOS, cairosvg finds Homebrew's libcairo only when `/opt/homebrew/lib` is on the library search path.
  `vectorize.py` and `redraw.py` set this themselves for the import; your own scripts that import cairosvg should do
  the same (or run with `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib`).
