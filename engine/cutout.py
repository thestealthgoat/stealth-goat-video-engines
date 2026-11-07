#!/usr/bin/env python3
"""Headshot cutout for player cards: rembg u2net_human_seg -> choke matte 2 px + 1.2 px blur -> decontaminate white spill.
cutout.py <in.jpg> <out.png> [more pairs...]   (no profile values; a --profile NAME pair is accepted and ignored)"""
import sys, numpy as np
from PIL import Image, ImageFilter
from rembg import remove, new_session
S = new_session('u2net_human_seg')
a = sys.argv[1:]
if '--profile' in a: i = a.index('--profile'); del a[i:i + 2]
a = [x for x in a if not x.startswith('--profile=')]
for src, dst in zip(a[::2], a[1::2]):
    im = Image.open(src).convert('RGB')
    m = remove(im, session=S, only_mask=True).convert('L')
    m = m.filter(ImageFilter.MinFilter(5)).filter(ImageFilter.GaussianBlur(1.2))  # 2 px choke + soft edge
    rgb = np.asarray(im).astype(np.float32); al = np.asarray(m).astype(np.float32) / 255
    # decontaminate: un-premultiply against a white background in the soft edge
    edge = (al > 0.02) & (al < 0.98)
    for c in range(3):
        ch = rgb[..., c]
        ch[edge] = np.clip((ch[edge] - 255 * (1 - al[edge])) / np.maximum(al[edge], 0.05), 0, 255)
    out = np.dstack([rgb, al * 255]).astype(np.uint8)
    o = Image.fromarray(out, 'RGBA'); o = o.crop(o.getchannel('A').getbbox()); o.save(dst)
    print('wrote', dst, o.size)
