#!/usr/bin/env python3
"""quote.py - E5 quote callout: the speaker cut out on one side, their words as a big serif pull-quote on the other.

quote.py --text "..." --by "Name" [--role "..."] --out DIR [--name N]
         (--matte <name>_matte.json from matte.py [--at S] | --cutout person.png) [--bg video.mp4 --bg-t S | --bg '#hex']
         [--dur S] [--fps 29.97] [--size 1920x1080] [--frames t1,t2] [--profile P]

The person comes from the O2 matte (one frame of <name>_Alpha.mov at --at seconds into the matte window) or any cutout
PNG (engine/cutout.py, a player cutout). The ground is the same video, blurred and darkened (so the card is born from
the picture), or the profile ground. Motion (spring.py): the ground pushes in slowly; the person slides in from the
edge (snappy) with a rim of the accent colour; a big opening quote mark lands (the one bouncy moment); the words
arrive one by one (smooth, never growing from zero); the attribution follows; everything leaves on uiExit.
The quote face is the profile's "quote" font role, else a bundled serif (Fraunces Soft, OFL): pull-quotes read best
in a serif. Outputs <name>_quote.mp4 and <name>_quote_Alpha.mov (the card without the ground, for Premiere).
"""
import argparse, json, os, subprocess, sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import vprofile as prof  # noqa: E402
from spring import clamp01, progress  # noqa: E402

SERIF = os.path.join(REPO, "resources", "fonts", "Fraunces-SoftSemiBold.ttf")


def person_from_matte(mjson, at):
    mj = json.load(open(mjson)); w, h = mj["size"]; mov = mjson[:-5] + "_Alpha.mov"
    raw = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-ss", f"{at:.3f}", "-i", mov, "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgba", "-"],
                         capture_output=True, check=True).stdout
    im = Image.frombytes("RGBA", (w, h), raw)
    return im.crop(im.getchannel("A").getbbox()), mj


def frame_at(video, t, size):
    w, h = size
    raw = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-ss", f"{t:.3f}", "-i", video, "-frames:v", "1", "-vf",
                          f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         capture_output=True, check=True).stdout
    return Image.frombytes("RGB", (w, h), raw)


def wrap(words, font, maxw):
    lines, cur = [], []
    for w in words:
        if cur and font.getlength(" ".join(cur + [w])) > maxw:
            lines.append(cur); cur = []
        cur.append(w)
    if cur: lines.append(cur)
    return lines


class Card:
    def __init__(self, P, size, person, ground, text, by, role, dur):
        self.P, (self.W, self.H) = P, size
        W, H = size; s = min(W, H) / 1080.0; self.s = s     # short side: a portrait frame is not laid out at 1.8x
        self.acc = P.rgb("accent"); self.txt = P.rgb("text") if "text" in P.get("brand.colors") else (255, 255, 255)
        self.dim = tuple(int(0.75 * a + 0.25 * b) for a, b in zip(self.txt, P.rgb("primary")))
        fonts = P.get("brand.fonts") or {}
        qf = P.font("quote") if "quote" in fonts else SERIF
        self.ground, self.dur = ground, dur
        safe = int(P.get("layout.safe_px", 90) * s)
        # person: right side, up to 86% of the frame tall and half its width, standing on the bottom edge
        ph = int(0.86 * H); k = min(ph / person.height, 0.5 * W / person.width)    # never wider than half the frame
        self.person = person.resize((max(1, int(person.width * k)), max(1, int(person.height * k))), Image.LANCZOS)
        self.px = W - self.person.width + int(0.12 * self.person.width); self.py = H - self.person.height   # bleeds off the right
        a = self.person.getchannel("A")
        rim = Image.new("RGBA", self.person.size, self.acc + (0,)); rim.putalpha(a.filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.GaussianBlur(6 * s)))
        self.rim = rim
        # quote text: the left 58% of the frame and clear of the person (in portrait the person starts near 0.56 W),
        # the largest size that fits 4 lines (7 in a portrait frame, where the column is narrow and tall) with every
        # line (a long single word too) inside the column
        self.left = safe + int(30 * s); maxw = min(int(0.58 * W), self.px - int(30 * s)) - self.left
        max_lines = 4 if W >= H else 7
        words = text.split(); size_px = int(96 * s)
        while True:
            self.f = ImageFont.truetype(qf, size_px); lines = wrap(words, self.f, maxw)
            widest = max(self.f.getlength(" ".join(l)) for l in lines)
            if (len(lines) <= max_lines and widest <= maxw) or size_px < 24 * s: break
            size_px = int(size_px * 0.92)
        self.lines = lines; self.lh = int(size_px * 1.18)
        self.fq = ImageFont.truetype(qf, int(size_px * 2.6)); self._qf, self._fqc = qf, {}
        self.fb = ImageFont.truetype(P.font("head"), int(40 * s))
        self.fr = ImageFont.truetype(P.font("body_semibold" if "body_semibold" in fonts else "body"), int(26 * s))
        self.by, self.role = by, role
        n = sum(len(l) for l in lines)
        self.t_words = [0.75 + 0.11 * i for i in range(n)]
        self.t_by = self.t_words[-1] + 0.45
        top = int(H * 0.5 - (len(lines) * self.lh) / 2 + 32.4 * s); self.top = top

    def fq_at(self, px):
        if px not in self._fqc: self._fqc[px] = ImageFont.truetype(self._qf, px)
        return self._fqc[px]

    def frame(self, t, with_ground=True):
        W, H, s = self.W, self.H, self.s
        out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ex = clamp01(progress(t, start=self.dur - 0.4, preset="uiExit")) if t > self.dur - 0.4 else 0.0
        if with_ground and self.ground is not None:
            push = 1.0 + 0.10 * clamp01(progress(t, start=0.0, zeta=1.0, omega=3.0 / max(1.0, self.dur)))   # a slow spring push-in: never still
            # sub-pixel scale about the centre (an integer resize steps the whole ground 1 px every few frames)
            g = self.ground.transform((W, H), Image.AFFINE, (1 / push, 0, W / 2 * (1 - 1 / push), 0, 1 / push, H / 2 * (1 - 1 / push)),
                                      resample=Image.BILINEAR)
            lift = clamp01(progress(t, start=0.0, zeta=1.0, omega=14.0))      # lights up from black: the opening hit (~0.2 s)
            if lift < 0.999: g = Image.eval(g, lambda v: int(v * lift))
            out.paste(g, (0, 0))
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        # the person slides in from the right edge
        dx = ((1 - progress(t, start=0.0, preset="snappy")) * 0.75 * W            # in from off the right edge (the opening move)
              - 0.02 * W * clamp01(progress(t, start=1.0, zeta=1.0, omega=2.5 / max(1.0, self.dur)))   # then a slow drift: the hold lives
              + ex * 0.08 * W)
        pa = clamp01(progress(t, start=0.05, preset="smooth"))
        # placed at the whole pixel, then the fraction is a bilinear shift: the slow drift glides instead of stepping 1 px
        # every few frames
        X = self.px + dx; xi = int(np.floor(X)); fx = X - xi
        pl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        rim = self.rim.copy(); rim.putalpha(rim.getchannel("A").point(lambda v: int(v * pa * 0.9)))
        if -rim.width < xi < W: pl.alpha_composite(rim, (max(0, xi), self.py), (max(0, -xi), 0))
        per = self.person.copy(); per.putalpha(per.getchannel("A").point(lambda v: int(v * pa)))
        if -per.width < xi < W: pl.alpha_composite(per, (max(0, xi), self.py), (max(0, -xi), 0))
        if fx > 1e-3:
            pl = pl.transform((W, H), Image.AFFINE, (1, 0, -fx, 0, 1, 0), resample=Image.BILINEAR)
        layer.alpha_composite(pl)
        d = ImageDraw.Draw(layer)
        # the opening quote mark: the one bouncy landing
        qk = progress(t, start=0.4, preset="bouncy"); qa = clamp01(progress(t, start=0.4, preset="smooth"))
        if t >= 0.4:
            sc = 1.25 - 0.25 * qk                                     # lands from 125% (never grows from zero)
            fq = self.fq_at(max(8, int(self.fq.size * sc)))
            d.text((self.left - 0.01 * W, self.top + 48.6 * s), "“", font=fq, fill=self.acc + (int(255 * qa),), anchor="ls")
        # words, one by one
        i = 0
        for li, line in enumerate(self.lines):
            x = self.left; y = self.top + li * self.lh + self.lh * 0.8
            for w in line:
                tw = self.t_words[i]; i += 1
                if t >= tw - 0.02:
                    a = clamp01(progress(t, start=tw, preset="smooth")); yy = y + (1 - progress(t, start=tw, preset="snappy")) * 21.6 * s
                    d.text((x, yy), w, font=self.f, fill=self.txt + (int(255 * a),), anchor="ls")
                x += self.f.getlength(w + " ")
        if t >= self.t_by:
            a = clamp01(progress(t, start=self.t_by, preset="smooth")); bx = self.left + (1 - progress(t, start=self.t_by, preset="snappy")) * 30 * s
            yb = self.top + len(self.lines) * self.lh + 75.6 * s
            d.rounded_rectangle((bx, yb - 34 * s, bx + 60 * s, yb - 28 * s), radius=3 * s, fill=self.acc + (int(255 * a),))
            d.text((bx, yb + 12 * s), self.by, font=self.fb, fill=self.txt + (int(255 * a),), anchor="ls")
            if self.role:
                d.text((bx, yb + 52 * s), self.role, font=self.fr, fill=self.dim + (int(255 * a),), anchor="ls")
        if ex > 0:
            la = np.asarray(layer).copy(); la[..., 3] = (la[..., 3] * (1 - ex)).astype(np.uint8); layer = Image.fromarray(la)
        out.alpha_composite(layer)
        return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="E5 quote callout")
    ap.add_argument("--text", required=True); ap.add_argument("--by", required=True); ap.add_argument("--role", default="")
    ap.add_argument("--out", required=True); ap.add_argument("--name", default="quote")
    g = ap.add_mutually_exclusive_group(required=True); g.add_argument("--matte"); g.add_argument("--cutout")
    ap.add_argument("--at", type=float, default=1.0, help="--matte: seconds into the matte window for the person still")
    ap.add_argument("--bg", help="ground: a video (blurred, darkened) or '#hex' (default: the matte's own video)")
    ap.add_argument("--bg-t", type=float, help="time in the --bg video (default: the matte window + --at)")
    ap.add_argument("--dur", type=float); ap.add_argument("--fps", type=float, default=29.97); ap.add_argument("--size", default="1920x1080")
    ap.add_argument("--frames"); prof.add_arg(ap)
    a = ap.parse_args(argv)
    P = prof.load(a.profile); W, H = (int(v) for v in a.size.split("x"))
    mj = None
    if a.matte: person, mj = person_from_matte(a.matte, a.at)
    else:
        person = Image.open(a.cutout).convert("RGBA"); person = person.crop(person.getchannel("A").getbbox())
    bg = a.bg or (mj["video"] if mj else None); ground = None
    if bg and bg.startswith("#"):
        ground = Image.new("RGB", (W, H), bg)
    elif bg:
        t = a.bg_t if a.bg_t is not None else ((mj["t0"] + a.at) if mj else 0.0)
        ground = frame_at(bg, t, (W, H)).filter(ImageFilter.GaussianBlur(28 * H / 1080))
        ground = Image.blend(ground, Image.new("RGB", (W, H), tuple(int(v * 0.25) for v in P.rgb("primary"))), 0.62)
    else:
        ground = Image.new("RGB", (W, H), tuple(int(v * 0.4) for v in P.rgb("primary")))
    n_words = len(a.text.split())
    dur = a.dur or max(4.0, 0.75 + 0.11 * n_words + 0.45 + 2.6)
    card = Card(P, (W, H), person, ground, a.text, a.by, a.role, dur)
    os.makedirs(a.out, exist_ok=True); base = os.path.join(a.out, f"{a.name}_quote")
    if a.frames:
        for t in (float(x) for x in a.frames.split(",")):
            card.frame(t).convert("RGB").save(f"{base}_t{t:.2f}.jpg", quality=92); print("still", f"{base}_t{t:.2f}.jpg")
        return 0
    fr = "30000/1001" if abs(a.fps - 30000 / 1001) < 0.01 else f"{a.fps:g}"
    n = int(round(dur * a.fps))
    encs = [subprocess.Popen(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-framerate", fr, "-i", "pipe:0",
                              "-c:v", "libx264", "-crf", "17", "-preset", "medium", "-pix_fmt", "yuv420p", "-threads", "4", "-movflags", "+faststart", base + ".mp4"], stdin=subprocess.PIPE),
            subprocess.Popen(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{H}", "-framerate", fr, "-i", "pipe:0",
                              "-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le", "-alpha_bits", "16", "-threads", "4", base + "_Alpha.mov"], stdin=subprocess.PIPE)]
    for i in range(n):
        t = i / a.fps
        encs[0].stdin.write(card.frame(t).convert("RGB").tobytes())
        encs[1].stdin.write(card.frame(t, with_ground=False).tobytes())
    for e in encs:
        e.stdin.close()
        if e.wait(): raise SystemExit("quote: encode failed")
    print(f"quote: {dur:.2f} s, {n_words} words -> {base}.mp4, {base}_Alpha.mov (qa: --kind motion --cuts none --holds end:2.4)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
