#!/usr/bin/env python3
"""Find the font that best matches a line of lettering in a logo image.

fontmatch.py <image> "<TEXT>" x0,y0,x1,y1 <fonts_dir> [--thresh 72] [--top 6]

Crops the box, makes a letter mask (pixels darker than --thresh L*, or lighter with a negative value), renders
TEXT in every .ttf/.otf in fonts_dir (variable fonts are tried at weights 600/700/800/900), stretches each render to
the box, and ranks the fonts by overlap (IoU). Writes fontmatch_<text>.png with the top matches overlaid for a
visual check. A match ≥ 0.80 IoU is usually the same family or close enough to rebuild a logo.
"""
import argparse, glob, os, sys
import numpy as np, cv2
from PIL import Image, ImageDraw, ImageFont


def letter_mask(img, box, thresh):
    x0, y0, x1, y1 = box
    crop = np.array(img.convert('RGB').crop(box))
    L = cv2.cvtColor(crop, cv2.COLOR_RGB2LAB)[..., 0].astype(float) * 100 / 255
    m = (L < thresh) if thresh > 0 else (L > -thresh)
    m = cv2.morphologyEx(m.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    return m > 0


def render(font_path, text, size_wh, wght=None):
    W, H = size_wh
    f = ImageFont.truetype(font_path, 400)
    if wght:
        try:
            axes = f.get_variation_axes(); vals = [wght if a.get('name', b'') in (b'Weight', 'Weight') else a['default'] for a in axes]
            f.set_variation_by_axes(vals)
        except Exception:
            return None
    bb = f.getbbox(text)
    im = Image.new('L', (bb[2] - bb[0] + 20, bb[3] - bb[1] + 20), 0)
    ImageDraw.Draw(im).text((10 - bb[0], 10 - bb[1]), text, font=f, fill=255)
    a = np.array(im) > 127
    ys, xs = np.where(a)
    if not len(xs): return None
    a = a[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    return cv2.resize(a.astype(np.uint8) * 255, (W, H), interpolation=cv2.INTER_AREA) > 127


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('image'); ap.add_argument('text'); ap.add_argument('box'); ap.add_argument('fonts')
    ap.add_argument('--thresh', type=float, default=72); ap.add_argument('--top', type=int, default=6)
    a = ap.parse_args()
    img = Image.open(a.image)
    box = tuple(int(v) for v in a.box.split(','))
    m = letter_mask(img, box, a.thresh)
    ys, xs = np.where(m); m = m[ys.min():ys.max() + 1, xs.min():xs.max() + 1]   # tight to the ink
    H, W = m.shape
    res = []
    for fp in sorted(glob.glob(os.path.join(a.fonts, '*.[ot]tf'))):
        is_var = '[' in fp or os.path.basename(fp).count('-') == 0
        for w in ([600, 700, 800, 900] if is_var else [None]):
            r = render(fp, a.text, (W, H), w)
            if r is None: continue
            iou = (r & m).sum() / max((r | m).sum(), 1)
            res.append((iou, os.path.basename(fp), w, r))
    res.sort(key=lambda x: -x[0])
    for iou, n, w, _ in res[:a.top]:
        print(f'{iou:.3f}  {n}' + (f' wght {w}' if w else ''))
    # overlay sheet: original mask grey, font render red outline
    rows = []
    for iou, n, w, r in res[:a.top]:
        v = np.full((H, W, 3), 255, np.uint8); v[m] = (170, 170, 170)
        edge = cv2.morphologyEx(r.astype(np.uint8), cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8)) > 0
        v[edge] = (220, 0, 0)
        cv2.putText(v, f'{n} {w or ""} {iou:.2f}', (5, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 200), 2)
        rows.append(v)
    out = np.vstack(rows)
    safe = ''.join(c for c in a.text if c.isalnum())[:20]
    Image.fromarray(out).save(f'fontmatch_{safe}.png')


if __name__ == '__main__':
    main()
