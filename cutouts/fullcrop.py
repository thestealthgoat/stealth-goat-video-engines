#!/usr/bin/env python3
"""Mac side: cut each requested player out of the full-size in-camera JPEG (rotated) with 8% padding.
fullcrop.py <Games dir> <requests.json> <out dir> [--seconds 150]   -> <out>/<name>.jpg (resumable)"""
import sys, os, io, json, glob, time
from PIL import Image, ImageFile
ImageFile.LOAD_TRUNCATED_IMAGES = True; Image.MAX_IMAGE_PIXELS = None
if len(sys.argv) < 2 or sys.argv[1] in ('-h', '--help'):   # usage before anything runs
    print(__doc__); sys.exit(0)
G, req, out = sys.argv[1], json.load(open(sys.argv[2])), sys.argv[3]
budget = float(sys.argv[sys.argv.index('--seconds') + 1]) if '--seconds' in sys.argv else 150
os.makedirs(out, exist_ok=True); T0 = time.time()
idx = {os.path.basename(p)[:-4]: p for p in glob.glob(G + '/*/Photos/**/*.CR3', recursive=True)}
for n, r in req.items():
    o = f'{out}/{n}.jpg'
    if os.path.exists(o): continue
    if time.time() - T0 > budget: print('TIMESLICE', len(os.listdir(out)), len(req)); sys.exit()
    b = open(idx[n], 'rb').read(30_000_000); i = 0; im = None
    while True:
        i = b.find(b'\xff\xd8\xff', i)
        if i < 0: break
        try:
            c = Image.open(io.BytesIO(b[i:]))
            if c.size[0] > 4000: im = c; break
        except Exception: pass
        i += 3
    if im is None: print('miss', n); continue
    im = im.transpose(Image.ROTATE_90) if r['o'] == 8 else im.transpose(Image.ROTATE_270) if r['o'] == 6 else im
    W, H = im.size; x0, y0, x1, y1 = r['box']; px, py = 0.08 * (x1 - x0), 0.06 * (y1 - y0)
    im.crop((int(max(0, x0 - px) * W), int(max(0, y0 - py) * H), int(min(1, x1 + px) * W), int(min(1, y1 + py) * H))).convert('RGB').save(o, quality=93)
print('DONE', len(os.listdir(out)), len(req))
