"""Contact sheet: alpha PNGs composited on the profile's primary colour, stacked, each fit to 1280x720.
preview.py <out.png> <in1.png> [in2.png ...] [--profile NAME]"""
import argparse, os, sys
from PIL import Image
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'engine'))
import vprofile as prof  # noqa: E402
ap=argparse.ArgumentParser(); ap.add_argument('out'); ap.add_argument('inputs', nargs='+'); prof.add_arg(ap)
a=ap.parse_args()
out=a.out; ims=[Image.open(p).convert('RGBA') for p in a.inputs]
bg=prof.load(a.profile).rgb('primary')+(255,)
tiles=[]
for im in ims:
    b=Image.new('RGBA',im.size,bg); b.alpha_composite(im); b=b.convert('RGB'); b.thumbnail((1280,720)); tiles.append(b)
W=max(t.width for t in tiles); H=sum(t.height for t in tiles)
c=Image.new('RGB',(W,H)); y=0
for t in tiles: c.paste(t,(0,y)); y+=t.height
c.save(out)
