#!/usr/bin/env python3
"""Vertical 9:16 (1080x1920) social version of a finished 16:9 piece, without re-cutting it.
vertical.py <in_16x9.mp4> <out_9x16.mp4> [--profile NAME] [--assets <org Assets>] [--fontdir <fonts dir>]
            [--kicker "WEEK 8 · SENIOR NIGHT"] [--head "HIGHLIGHTS"] [--sub "HOME 23 · AWAY 6"]
            [--foot TEXT (default: the profile's team.foot)] [--sponsor "PRESENTED BY <SPONSOR>"]
Layout: the full 16:9 frame (cards + scorebug intact) as a 1080-wide band, a blurred moving copy of the same shot
filling the frame behind it, the org's header (logo) above the band, footer below it kept clear of the Reels/TikTok UI.
Brand (logo, fonts, colors, footer line team.foot, watch line brand.watch_line) comes from the profile
(--profile, else $VIDEO_PROFILE, else local.json); --assets / --fontdir override the profile's assets folder and fonts.
Audio is copied untouched (the 16:9 master already passed audio_check), so no new cuts are introduced.
"""
import sys, os, subprocess
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vprofile as prof  # noqa: E402


def arg(k, d=None):
    a = sys.argv
    return a[a.index(k) + 1] if k in a else d


P = prof.load(arg('--profile'))


def color(role, fallback):
    """brand.colors.<role>, or the generic role <fallback> when the profile has no vertical-specific colour"""
    return P.rgb(role if role in P.get('brand.colors', {}) else fallback)


WHITE = P.rgb('text')
RED = color('vertical_accent', 'accent')      # rules, kicker chip
SUBC = color('vertical_sub', 'text')          # sub + watch line
SPONC = color('vertical_sponsor', 'text')     # sponsor line
W, H, BAND = 1080, 1920, 608
BY = 560  # band top: a little above centre so the footer clears the app UI


def font(fd, role, size):
    """profile font for role ('head'|'body'); a --fontdir holding the same file name overrides it"""
    p = P.font(role)
    if fd and os.path.isfile(os.path.join(fd, os.path.basename(p))):
        p = os.path.join(fd, os.path.basename(p))
    return ImageFont.truetype(p, size)


def brand_asset(assets, key):
    """a brand file (e.g. 'brand.logo_png') under --assets when it lives inside the profile's assets folder"""
    a = P.asset(key)
    rel = os.path.relpath(a, P.path('assets'))
    return a if (not assets or rel.startswith('..')) else f'{assets}/{rel}'


def watch_line():
    """the profile's watch line, drawn with wide separators ('A · B' -> 'A  ·  B')"""
    return P.get('brand.watch_line').replace(' · ', '  ·  ')


def overlay_png(path, fd, logo, kicker, head, sub, foot, sponsor):
    im = Image.new('RGBA', (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    beb = lambda s: font(fd, 'head', s)
    bar = lambda s: font(fd, 'body', s)
    def ctext(y, t, f, fill):
        d.text(((W - f.getlength(t)) / 2, y), t, font=f, fill=fill)
    # header: logo, kicker, head, sub
    lg = Image.open(logo).convert('RGBA'); lg = lg.crop(lg.getchannel('A').getbbox()); lg.thumbnail((360, 110), Image.LANCZOS)
    im.alpha_composite(lg, ((W - lg.width) // 2, 150))
    y = 150 + lg.height + 22
    if kicker:
        f = bar(40); tw = f.getlength(kicker.upper()) + 44
        d.rectangle([(W - tw) / 2, y, (W + tw) / 2, y + 54], fill=RED + (255,)); ctext(y + 4, kicker.upper(), f, WHITE); y += 70
    if head:
        f = beb(124 if len(head) <= 14 else 96); ctext(y, head.upper(), f, WHITE); y += f.size + 2
    if sub:
        ctext(y, sub.upper(), bar(50), SUBC)
    # thin accent rules hugging the band
    d.rectangle([0, BY - 8, W, BY - 1], fill=RED + (255,)); d.rectangle([0, BY + BAND + 1, W, BY + BAND + 8], fill=RED + (255,))
    # footer
    y = BY + BAND + 60
    if foot:
        ctext(y, foot.upper(), beb(70), WHITE); y += 80
    ctext(y, watch_line(), bar(36), SUBC); y += 56
    if sponsor:
        ctext(y, sponsor.upper(), bar(30), SPONC)
    im.save(path)


def main():
    src, out = sys.argv[1], sys.argv[2]
    assets, fd = arg('--assets'), arg('--fontdir')
    png = os.path.splitext(out)[0] + '_overlay.png'
    overlay_png(png, fd, brand_asset(assets, 'brand.logo_png'), arg('--kicker'), arg('--head'), arg('--sub'),
                arg('--foot', P.get('team.foot')), arg('--sponsor'))
    fc = (f"[0:v]split=2[a][b];"
          f"[a]scale=-2:480,crop=270:480,boxblur=12:2,scale={W}:{H},eq=brightness=-0.22:saturation=0.8[bg];"
          f"[b]scale={W}:{BAND}:flags=lanczos[fg];"
          f"[bg][fg]overlay=0:{BY}[v0];"
          f"[1:v]format=rgba,fade=in:st=0:d=0.4:alpha=1[ov];[v0][ov]overlay=0:0,format=yuv420p[v]")
    tmp = out + '.part.mp4'
    r = subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-i', src, '-loop', '1', '-i', png, '-filter_complex', fc,
                        '-map', '[v]', '-map', '0:a', '-shortest', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20',
                        '-r', '30000/1001', '-g', '60', '-c:a', 'copy', '-movflags', '+faststart', tmp], capture_output=True, text=True,
                       stdin=subprocess.DEVNULL)
    if r.returncode:
        raise SystemExit(r.stderr[-1500:])
    os.replace(tmp, out); print('DONE', out)


if __name__ == '__main__':
    if len(sys.argv) < 3 or sys.argv[1] in ('-h', '--help'):
        print(__doc__); sys.exit(0 if len(sys.argv) > 1 else 2)
    main()
