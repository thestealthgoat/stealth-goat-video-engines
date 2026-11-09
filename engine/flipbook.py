#!/usr/bin/env python3
"""Burst flipbook: turn photographer bursts into a fast stop-motion "action pack".
flipbook.py <plan.json> <frames dir> <out.mp4> [--profile NAME] [--wide] [--fps-photo 12] [--label "WK06 + WK07"]
  [--root <org root>] [--fontdir DIR] [--slam DIR of PNG frames] [--keep-temp]
Defaults come from the profile: colors (primary / accent / text), fonts (head / body), logo (brand.logo_png),
end-card slam = frames pulled from brand.logo_3d_swing_alpha_mov (cached in <repo>/_cache/flipbook/<profile>/slam/<key>,
the key changes with the asset file, its size and date, and the extraction settings),
end-card lines team.foot + brand.watch_line, opponent captions schedule.opponents {"Wk06": "VS ..."} (none if absent).
Default --label: "<team.home_abbr> <team.home_name> · " + the plan's weeks, e.g. "ACME HAWKS · WK06 + WK07".
The working frames (<out>_frames/) and <out>.wav are removed after a good render (kept with --keep-temp, and kept
when the render fails, for debugging).
--root re-roots the profile's assets under another copy of the org folder.
--fontdir DIR uses the profile's font file names from DIR.
plan.json: [{"name":..., "wk":"Wk06", "frames":["R5_x",...], "opp": "VS ..." (optional)}, ...] in play order.
"""
import sys, os, json, glob, subprocess, math, re, shutil, hashlib, tempfile
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
FPS = 30000 / 1001
WIDE = '--wide' in sys.argv
W, H = (1920, 1080) if WIDE else (1080, 1920)
def arg(k, d=None): return sys.argv[sys.argv.index(k) + 1] if k in sys.argv else d
PHOTO_FPS = float(arg('--fps-photo', 12))
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import vprofile as prof  # noqa: E402
if any(x in ('-h', '--help') for x in sys.argv[1:]):   # help before the profile loads
    print(__doc__); sys.exit(0)
P = prof.load(arg('--profile'))
ROOT = P.path('root')
KV = arg('--root')
def org(p):
    """A profile asset path, re-rooted under --root when one is given."""
    if KV and (p == ROOT or p.startswith(ROOT + '/')): return KV.rstrip('/') + p[len(ROOT):]
    return p
FONTS = arg('--fontdir')
def _font(role): return os.path.join(FONTS, os.path.basename(P.font(role))) if FONTS else P.font(role)
BEB = _font('head'); BAR = _font('body')
LOGO = Image.open(org(P.asset('brand.logo_png'))).convert('RGBA')
SLAM_VF, SLAM_PIX = 'fps=30000/1001,scale=1920:1080', 'rgba'
def _slam():
    """End-card slam frames: --slam DIR, else frames pulled from the profile's 3D swing (cached; the cache key is the
    asset's path, size and modification time plus the extraction settings, so a changed asset or --root re-extracts)."""
    d = arg('--slam')
    if not d:
        src = os.path.abspath(org(P.asset('brand.logo_3d_swing_alpha_mov'))); st = os.stat(src)
        key = hashlib.sha1(json.dumps([src, st.st_size, st.st_mtime_ns, SLAM_VF, SLAM_PIX]).encode()).hexdigest()[:16]
        base = os.path.join(REPO, '_cache', 'flipbook', P.name, 'slam'); d = os.path.join(base, key)
        if not glob.glob(f'{glob.escape(d)}/f*.png'):
            os.makedirs(base, exist_ok=True)
            part = tempfile.mkdtemp(prefix=key + '.part', dir=base)   # extract aside, then move in whole
            try:
                subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-i', src, '-vf', SLAM_VF,
                                '-pix_fmt', SLAM_PIX, f'{part}/f%04d.png'], check=True, stdin=subprocess.DEVNULL)
                with open(f'{part}/source.json', 'w') as fh:
                    json.dump({'asset': src, 'size': st.st_size, 'mtime_ns': st.st_mtime_ns, 'vf': SLAM_VF,
                               'pix_fmt': SLAM_PIX}, fh, indent=1)
                shutil.rmtree(d, ignore_errors=True); os.rename(part, d)
            finally:
                shutil.rmtree(part, ignore_errors=True)
    return sorted(glob.glob(f'{glob.escape(d)}/f*.png'))   # escape: folders like "[C] ..."
NAVY, RED, WHITE = P.rgb('primary'), P.rgb('accent'), P.rgb('text')
FLASH = (255, 255, 255)   # white flash frames (not a brand color)
OPP = P.get('schedule.opponents', {})   # {"Wk06": "VS ..."}; no caption for a week it doesn't list
FOOT, WATCH = P.get('team.foot'), P.get('brand.watch_line')
def default_label(plan):
    """'<abbr> <name> · WK06 + WK07' from the weeks the plan actually contains (in week order)."""
    wks = sorted({b['wk'] for b in plan if b.get('wk')}, key=lambda w: [int(x) if x.isdigit() else x.lower()
                                                                       for x in re.split(r'(\d+)', w)])
    team = f"{P.get('team.home_abbr')} {P.get('team.home_name')}"
    return f"{team} · {' + '.join(w.upper() for w in wks)}" if wks else team

def fit_cover(im, w, h, zoom=1.0, cy=0.45):
    s = max(w / im.width, h / im.height) * zoom; nw, nh = int(im.width * s), int(im.height * s)
    im = im.resize((nw, nh), Image.LANCZOS); x = (nw - w) // 2; y = int(min(max((nh - h) * cy, 0), nh - h))
    return im.crop((x, y, x + w, y + h))

def photo_canvas(im, zoom):
    if not WIDE: return fit_cover(im, W, H, zoom)
    bg = fit_cover(im, W, H, 1.0).resize((W // 8, H // 8)).filter(ImageFilter.GaussianBlur(3)).resize((W, H), Image.BICUBIC)
    bg = Image.fromarray((np.asarray(bg, np.float32) * 0.35 + np.array(NAVY, np.float32) * 0.65).astype(np.uint8))
    card = fit_cover(im, int(H * 0.62 * zoom), int(H * zoom * 0.93)); x = (W - card.width) // 2; y = (H - card.height) // 2
    bg.paste(Image.new('RGB', (card.width + 16, card.height + 16), (246, 244, 238)), (x - 8, y - 8)); bg.paste(card, (x, y)); return bg

def text(d, s, xy, size, fill, font=BEB, anchor='la', track=0):
    f = ImageFont.truetype(font, size)
    if not track: d.text(xy, s, font=f, fill=fill, anchor=anchor); return
    x, y = xy
    if anchor[0] == 'm': x -= (sum(f.getlength(c) for c in s) + track * (len(s) - 1)) / 2
    for c in s: d.text((x, y), c, font=f, fill=fill, anchor='l' + anchor[1]); x += f.getlength(c) + track

def chrome(c, k, total, wk, burst_i, nb, opp=None):
    d = ImageDraw.Draw(c, 'RGBA'); s = 0.72 if not WIDE else 0.6
    lw = 300 if not WIDE else 280; lg = LOGO.resize((lw, int(LOGO.height * lw / LOGO.width)), Image.LANCZOS)
    m = 54 if not WIDE else 60
    c.paste(lg, (m, m + (90 if not WIDE else 0)), lg)
    # burst counter, viewfinder-style
    y = H - (330 if not WIDE else 110)
    d.rectangle([m, y, m + 14, y + 14], fill=RED + (255,))
    text(d, f'BURST {burst_i + 1:02d}/{nb:02d}', (m + 28, y - 8), 38, WHITE + (235,), BAR, 'la', 3)
    text(d, f'{wk.upper()} {OPP.get(wk, "") if opp is None else opp}', (m, y + 34), 54, WHITE + (255,), BEB, 'la', 2)
    # frame ticks
    for i in range(total):
        x0 = m + i * 22; d.rectangle([x0, y + 100, x0 + 14, y + 106], fill=(RED + (255,)) if i <= k else (255, 255, 255, 90))
    # corner brackets
    L, t = 60, 5
    for (x, yy, sx, sy) in ((30, 30, 1, 1), (W - 30, 30, -1, 1), (30, H - 30, 1, -1), (W - 30, H - 30, -1, -1)):
        d.rectangle([min(x, x + sx * L), min(yy, yy + sy * t), max(x, x + sx * L), max(yy, yy + sy * t)], fill=(255, 255, 255, 200))
        d.rectangle([min(x, x + sx * t), min(yy, yy + sy * L), max(x, x + sx * t), max(yy, yy + sy * L)], fill=(255, 255, 255, 200))

def main():
    plan = json.load(open(sys.argv[1])); FR = sys.argv[2]; out = sys.argv[3]
    LABEL = arg('--label'); LABEL = default_label(plan) if LABEL is None else LABEL; SLAM = _slam()
    tmp = out + '_frames'; os.makedirs(tmp, exist_ok=True)
    for f in glob.glob(f'{glob.escape(tmp)}/f*.jpg'): os.remove(f)   # frames left by an earlier failed run must not be encoded
    timeline = []   # list of (kind, payload)
    # title card 1.0 s
    n_title = int(round(1.0 * FPS)); clicks = []; booms = []
    fi = 0
    def emit(img):
        nonlocal fi; img.convert('RGB').save(f'{tmp}/f{fi:05d}.jpg', quality=92); fi += 1
    for i in range(n_title):
        c = Image.new('RGB', (W, H), NAVY); d = ImageDraw.Draw(c); p = min(1, i / (0.25 * FPS))
        text(d, 'ACTION', (W // 2, H // 2 - 70), int(230 * (1.4 - 0.4 * p)) if not WIDE else int(200 * (1.4 - 0.4 * p)), WHITE, BEB, 'mm', 8)
        text(d, 'PACK', (W // 2, H // 2 + 130), int(230 * (1.4 - 0.4 * p)) if not WIDE else int(200 * (1.4 - 0.4 * p)), RED, BEB, 'mm', 8)
        text(d, LABEL, (W // 2, H // 2 + 290), 52, WHITE, BAR, 'mm', 6)
        lw = 560; lg = LOGO.resize((lw, int(LOGO.height * lw / LOGO.width)), Image.LANCZOS); c.paste(lg, ((W - lg.width) // 2, H // 2 - 480 if not WIDE else 60), lg)
        if i in (0, 1): c = Image.blend(c, Image.new('RGB', (W, H), FLASH), 0.7 if i == 0 else 0.35)
        emit(c)
    booms.append(0.0)
    per = FPS / PHOTO_FPS
    for bi, b in enumerate(plan):
        imgs = [Image.open(f"{FR}/{n}.jpg").convert('RGB') for n in b['frames']]
        booms.append(fi / FPS); acc = 0.0
        for k, im in enumerate(imgs):
            nfr = int(round(acc + per) - round(acc)); acc += per
            clicks.append(fi / FPS)
            for j in range(nfr):
                c = photo_canvas(im, 1.04 + 0.01 * k).convert('RGBA'); chrome(c, k, len(imgs), b['wk'], bi, len(plan), b.get('opp'))
                if k == 0 and j < 2: c = Image.blend(c.convert('RGB'), Image.new('RGB', (W, H), FLASH), 0.75 if j == 0 else 0.35)
                emit(c)
        # hold the last frame with a punch-in
        hold = int(round(0.30 * FPS))
        for j in range(hold):
            z = 1.04 + 0.01 * len(imgs) + 0.05 * (1 - (1 - j / hold) ** 3)
            c = photo_canvas(imgs[-1], z).convert('RGBA'); chrome(c, len(imgs) - 1, len(imgs), b['wk'], bi, len(plan), b.get('opp')); emit(c)
    # end card: 3D logo slam over the primary color + where to watch
    booms.append(fi / FPS)
    for j, f in enumerate(SLAM):
        c = Image.new('RGBA', (W, H), NAVY + (255,)); s = Image.open(f).convert('RGBA')
        if not WIDE: s = s.resize((1180, 664), Image.LANCZOS); c.alpha_composite(s.crop((50, 0, 1130, 664)), (0, (H - 664) // 2 - 120))
        else: c.alpha_composite(s, (0, -60))
        d = ImageDraw.Draw(c); p = min(1, max(0, (j - 15) / 10))
        if p > 0:
            yy = H // 2 + (260 if not WIDE else 300)
            text(d, FOOT, (W // 2, yy), 64 if not WIDE else 60, WHITE + (int(255 * p),), BEB, 'mm', 4)
            text(d, WATCH, (W // 2, yy + 70), 40 if not WIDE else 38, RED + (int(255 * p),), BAR, 'mm', 2)
        if j < 2: c = Image.blend(c.convert('RGB'), Image.new('RGB', (W, H), FLASH), 0.7 if j == 0 else 0.3).convert('RGBA')
        if j > len(SLAM) - 12: c = Image.blend(c.convert('RGB'), Image.new('RGB', (W, H), (0, 0, 0)), (j - (len(SLAM) - 12)) / 12).convert('RGBA')
        emit(c)
    dur = fi / FPS
    # audio: shutter clicks + low booms, synthesized (no music licence needed)
    sr = 48000; a = np.zeros(int(dur * sr) + sr, np.float32); rng = np.random.default_rng(3)
    def click(t, g=0.55):
        n = int(0.045 * sr); env = np.exp(-np.arange(n) / (0.006 * sr)); env2 = np.exp(-np.maximum(0, np.arange(n) - 0.018 * sr) / (0.004 * sr)) * (np.arange(n) > 0.018 * sr)
        x = rng.normal(0, 1, n).astype(np.float32); x = np.diff(np.concatenate([[0], x]))  # brighter
        s = int(t * sr); a[s:s + n] += g * (x * env + 0.7 * x * env2)
    def boom(t, g=0.9):
        n = int(0.6 * sr); tt = np.arange(n) / sr; f = 48 + 40 * np.exp(-tt * 18)
        s = int(t * sr); a[s:s + n] += g * np.sin(2 * np.pi * np.cumsum(f) / sr) * np.exp(-tt * 6)
    for t in clicks: click(t)
    for t in booms: boom(t)
    a = np.tanh(a * 1.2) * 0.8; a = a[:int(dur * sr)]
    wav = out + '.wav'
    import wave
    with wave.open(wav, 'w') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes((a * 32767).astype(np.int16).tobytes())
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-framerate', '30000/1001', '-i', f'{tmp}/f%05d.jpg', '-i', wav, '-c:v', 'libx264', '-crf', '17',
                    '-preset', 'slow', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', '-c:a', 'aac', '-b:a', '256k', '-ac', '2', '-shortest', out],
                   check=True, stdin=subprocess.DEVNULL)
    if '--keep-temp' not in sys.argv:   # a failed render raises above and keeps them for debugging
        shutil.rmtree(tmp, ignore_errors=True); os.remove(wav)
    print('done', out, round(dur, 2), 's', fi, 'frames')

if __name__ == '__main__':
    main()
