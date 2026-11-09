#!/usr/bin/env python3
"""hopwords.py - C1 bouncing-character verses and lyrics (2D): a character hops word to word through a memory verse or
a lyric, and each word lights up as the character lands on it.

hopwords.py --text "verse" --out <dir> [--name N] [--profile P]
            [--audio voice.wav | --words words.json | --chart chart.txt | --wpm 110]
            [--ref "Galatians 5:22-23 (WEB)"] [--character art.png|art.svg] [--aspect 16:9|9:16]
            [--bg profile|gradient|'#hex'|image.png|none] [--lead 1.0] [--tail 1.6] [--frames 1.0,2.5]

Word times, first found wins:
  --words words.json   a captions.py / faster-whisper word file ({"words": [{"w", "s", "e"}, ...]}), e.g. edited by hand
  --audio file         transcribed here with local faster-whisper (captions.transcribe; nothing leaves the Mac), and
                       the result is saved as <out>/<name>.words.json for fixing and re-use with --words
  --chart chart.txt    a lyric chart: one cue per line, "<seconds or m:ss.ss> <word or phrase>"; a phrase's words are
                       spread evenly up to the next cue
  --wpm N              no audio: words paced evenly at N words a minute (tests, silent loops)
With --text plus timed words, the shown words are the --text words (the verse spelled right) and each takes the time
of the timed word it matches (difflib alignment); a word with no match is placed between its neighbours.

Look: words in the profile's head font, unlit in text_dim at low opacity, lit in text, the word the character stands
on in accent. Lines are balanced across pages (no orphan last line). Background: the profile's brand.gradient (when it
has one) as a soft field dimmed to --bg-dim (0.62) so the type reads, else primary_deep; --bg
none writes an alpha .mov (ProRes 4444) for compositing as well as the preview MP4.
Character: --character is an RGBA PNG or an SVG (owned or original art only; no AI art). Without it, a placeholder
bean in the profile's accent colour is drawn in code.

Motion: the hop is ballistic (constant horizontal speed, gravity arc), landing on each word's start time. Everything
else is engine/spring.py: the landing squash is the spring's response to the landing speed (bouncy preset, so it
squashes then rebounds), the crouch before take-off is a ui spring, each word's light-up is a smooth spring and its
pop the snappy preset's response to a kick. Pages of up to 3 lines (5 in 9:16) slide on snappy springs, fades are
smooth and clamped. The piece opens with the field lighting up from black (ui spring, ~0.2 s) and the first page rising in, and
ends with the character hopping in place on the last word. Every frame is a pure function of t.

Outputs in --out: <name>_hop.mp4 (H.264, with --audio muxed in), <name>_hop_Alpha.mov when --bg none,
<name>.timing.json (the words and times used), and stills with --frames.
"""
import argparse, difflib, json, math, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import vprofile as prof          # noqa: E402
from spring import PRESETS, solve, progress, clamp01   # noqa: E402
from PIL import Image, ImageDraw, ImageFilter, ImageFont   # noqa: E402

FF = "ffmpeg"


# ---- springs ---------------------------------------------------------------------------------------------------
def kick(t, t0, v0, preset):
    """Response of a spring at rest to a velocity kick v0 at t0 (0 before t0): goes out, comes back, settles."""
    if t <= t0:
        return 0.0
    z, w = PRESETS[preset]
    return solve(t - t0, z, w, v0)[0] - solve(t - t0, z, w, 0.0)[0]


def sp(t, start, preset):
    return clamp01(progress(t, start, preset))


# ---- timing ------------------------------------------------------------------------------------------------------
def norm(w):
    return re.sub(r"[^a-z0-9']", "", w.lower().replace("’", "'"))


def parse_time(s):
    if ":" in s:
        m, sec = s.split(":", 1)
        return int(m) * 60 + float(sec)
    return float(s)


def from_chart(path):
    cues = []
    for ln in open(path, encoding="utf-8"):
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        t, _, phrase = ln.partition(" ")
        cues.append((parse_time(t), phrase.split()))
    words = []
    for i, (t, ws) in enumerate(cues):
        nxt = cues[i + 1][0] if i + 1 < len(cues) else t + 0.45 * len(ws)
        step = (nxt - t) / max(1, len(ws))
        for k, w in enumerate(ws):
            words.append({"w": w, "s": round(t + k * step, 3), "e": round(t + (k + 1) * step, 3)})
    return words


def paced(text_words, wpm, lead):
    step = 60.0 / wpm
    out, t = [], lead
    for w in text_words:
        out.append({"w": w, "s": round(t, 3), "e": round(t + step * 0.9, 3)})
        t += step * (1.6 if re.search(r"[.;:!?]$", w) else 1.25 if w.endswith(",") else 1.0)
    return out


def align(text_words, timed):
    """Give each --text word the time of the timed word it matches; interpolate the rest."""
    a = [norm(w) for w in text_words]
    b = [norm(w["w"]) for w in timed]
    s = [None] * len(a)
    for blk in difflib.SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks():
        for k in range(blk.size):
            s[blk.a + k] = (timed[blk.b + k]["s"], timed[blk.b + k]["e"])
    known = [i for i, v in enumerate(s) if v]
    if not known:
        raise SystemExit("hopwords: none of the --text words matched the timed words; check --text / --words")
    out = []
    for i, w in enumerate(text_words):
        if s[i]:
            st, en = s[i]
        else:
            lo = max([k for k in known if k < i], default=None)
            hi = min([k for k in known if k > i], default=None)
            if lo is None:
                st = s[hi][0] - 0.35 * (hi - i)
            elif hi is None:
                st = s[lo][1] + 0.35 * (i - lo - 1)
            else:
                st = s[lo][1] + (s[hi][0] - s[lo][1]) * (i - lo) / (hi - lo)
            en = st + 0.3
        out.append({"w": w, "s": round(st, 3), "e": round(en, 3), **({} if s[i] else {"guessed": True})})
    for i in range(1, len(out)):                      # strictly increasing landings
        if out[i]["s"] <= out[i - 1]["s"] + 0.12:
            out[i]["s"] = round(out[i - 1]["s"] + 0.12, 3)
    return out


# ---- layout --------------------------------------------------------------------------------------------------------
class Layout:
    def __init__(self, words, font, W, H, ch, max_lines, ref_h):
        self.words = words
        space = font.getlength(" ")
        maxw = 0.84 * W
        lines, cur, cw = [], [], 0.0
        for i, w in enumerate(words):
            wl = font.getlength(w["w"])
            if cur and cw + space + wl > maxw:
                lines.append(cur); cur, cw = [], 0.0
            cur.append((i, wl)); cw += (space if len(cur) > 1 else 0) + wl
        if cur:
            lines.append(cur)
        asc, desc = font.getmetrics()
        cap = -font.getbbox("H", anchor="ls")[1]
        pitch = cap + ch * 1.12 + 0.25 * asc
        self.pages, self.page_of = [], {}
        npages = max(1, math.ceil(len(lines) / max_lines))
        base_n, extra = divmod(len(lines), npages)    # balanced pages: 7 lines -> 3,2,2; never an orphan line
        at = 0
        for p in range(npages):
            take = base_n + (1 if p < extra else 0)
            self.pages.append(lines[at:at + take]); at += take
        avail_top, avail_bot = 0.06 * H + ch, H - 0.07 * H - ref_h
        for pi, pl in enumerate(self.pages):
            block = cap + pitch * (len(pl) - 1)
            top = avail_top + max(0.0, (avail_bot - avail_top - block) / 2)
            for li, line in enumerate(pl):
                base = top + cap + pitch * li
                tot = sum(wl for _, wl in line) + space * (len(line) - 1)
                x = (W - tot) / 2
                for i, wl in line:
                    w = words[i]
                    w["x"], w["base"], w["wl"], w["cx"] = x, base, wl, x + wl / 2
                    w["top"] = base - cap
                    self.page_of[i] = pi
                    x += wl + space
        self.cap = cap


# ---- character -----------------------------------------------------------------------------------------------------
def placeholder_char(h, fill, ink):
    """A simple bean with two eyes, drawn in code (stand-in until the real character art is set)."""
    S = 4
    w = int(h * 0.82)
    im = Image.new("RGBA", (w * S, h * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    lw = int(0.045 * h * S)
    d.ellipse([lw, lw, w * S - lw, h * S - lw], fill=fill + (255,), outline=ink + (255,), width=lw)
    hl = tuple(min(255, int(c + (255 - c) * 0.45)) for c in fill)
    d.ellipse([0.22 * w * S, 0.14 * h * S, 0.42 * w * S, 0.30 * h * S], fill=hl + (255,))
    for ex in (0.36, 0.64):
        cx, cy, r = ex * w * S, 0.42 * h * S, 0.085 * h * S
        d.ellipse([cx - r, cy - r * 1.2, cx + r, cy + r * 1.2], fill=(255, 255, 255, 255))
        d.ellipse([cx - r * 0.5 + r * 0.25, cy - r * 0.55, cx + r * 0.5 + r * 0.25, cy + r * 0.55], fill=ink + (255,))
    d.arc([0.38 * w * S, 0.52 * h * S, 0.62 * w * S, 0.68 * h * S], 20, 160, fill=ink + (255,), width=int(lw * 0.8))
    return im.resize((w, h), Image.LANCZOS)


def load_char(path, h):
    if path.lower().endswith(".svg"):
        os.environ.setdefault("DYLD_FALLBACK_LIBRARY_PATH", "/opt/homebrew/lib")
        import io, cairosvg
        im = Image.open(io.BytesIO(cairosvg.svg2png(url=path, output_height=h * 3))).convert("RGBA")
    else:
        im = Image.open(path).convert("RGBA")
    bb = im.getbbox()
    im = im.crop(bb) if bb else im
    return im.resize((max(1, int(im.width * h / im.height)), h), Image.LANCZOS)


# ---- the piece ---------------------------------------------------------------------------------------------------
class Hop:
    def __init__(self, P, words, W, H, char_img, ref, bg, fps):
        self.P, self.W, self.H, self.fps = P, W, H, fps
        cols = P.get("brand.colors")
        self.text = P.rgb("text")
        self.accent = P.rgb("accent")
        self.dim = P.rgb("text_dim") if "text_dim" in cols else self.text
        vertical = H > W
        fs = int((0.13 if vertical else 0.082) * min(W, H))
        self.font = ImageFont.truetype(P.font("head"), fs)
        self.ch = int(fs * 1.5)
        ref_font = ImageFont.truetype(P.font("body"), int(fs * 0.42))
        self.ref = ref
        self.ref_font = ref_font
        self.L = Layout(words, self.font, W, H, self.ch, 5 if vertical else 3, int(fs * 0.9) if ref else 0)
        # a hop between words that have a line above them stays low: the head may reach only half a body into the gap
        # above (the layout leaves 0.12 of a body + a quarter ascent of air over a standing character)
        asc = self.font.getmetrics()[0]
        self.hcap = 0.62 * self.ch + 0.25 * asc
        self.words = words
        for k, w in enumerate(words):               # is there a line above this word on its page?
            w["above"] = any(self.L.page_of[j] == self.L.page_of[k] and o["base"] < w["base"] - 1 for j, o in enumerate(words))
        self.char = char_img
        self.bg = bg
        self.dark = Image.new("RGBA", (W, H), (0, 0, 0, 255)) if bg is not None else None
        if bg is not None:                          # mean luma decides the light-up (a bright field from black reads as a cut)
            lum = _mean_luma(bg)
            self.lightup = ("ui", 0.0) if lum < 60 else ("smooth", 0.22)
        # flight times: land on each word's start
        prev_t = None
        for i, w in enumerate(words):
            gap = (w["s"] - prev_t) if prev_t is not None else 0.55
            w["T"] = max(0.16, min(0.46, 0.72 * gap))
            prev_t = w["s"]
        words[0]["T"] = max(0.3, min(0.75, words[0]["s"] - 0.25))   # the drop-in starts by ~0.25 s
        self.word_imgs = [self._word_imgs(w["w"]) for w in words]
        self.firsts = [min(i for i, p in self.L.page_of.items() if p == q) for q in range(len(self.L.pages))]
        self.end = words[-1]["e"]

    def _word_imgs(self, s):
        asc, desc = self.font.getmetrics()
        wl = int(math.ceil(self.font.getlength(s))) + 8
        out = []
        for col, a in ((self.dim, 0.42), (self.text, 1.0), (self.accent, 1.0)):
            im = Image.new("RGBA", (wl, asc + desc + 8), (0, 0, 0, 0))
            d = ImageDraw.Draw(im)
            if col == self.accent or a == 1.0:      # a soft shadow under lit words so they read on a light field
                sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
                ImageDraw.Draw(sh).text((4, asc + 4 + 3), s, font=self.font, fill=(0, 0, 0, 150), anchor="ls")
                im = Image.alpha_composite(im, sh.filter(ImageFilter.GaussianBlur(5)))
                d = ImageDraw.Draw(im)
            d.text((4, asc + 4), s, font=self.font, fill=col + (int(255 * a),), anchor="ls")
            out.append(im)
        return out, asc + 4

    # page offset (px) and opacity for page pi at time t
    def page_state(self, pi, t):
        firsts = self.firsts
        y, a = 0.0, 1.0
        if pi == 0:                                 # the first page rises in as the field lights up
            p = progress(t, 0.08, "snappy")
            y += (1 - p) * 0.05 * self.H
            a *= sp(t, 0.08, "smooth")
        if pi > 0:                                  # comes in as the hop to its first word takes off
            t_in = self.words[firsts[pi]]["s"] - self.words[firsts[pi]]["T"] - 0.25
            p = progress(t, t_in, "snappy")
            y += (1 - p) * 0.06 * self.H
            a *= sp(t, t_in, "smooth")
        if pi + 1 < len(self.L.pages):              # leaves as the hop to the next page takes off
            nx = firsts[pi + 1]
            t_out = self.words[nx]["s"] - self.words[nx]["T"] - 0.05
            y -= progress(t, t_out, "snappy") * 0.06 * self.H if t > t_out else 0.0
            a *= 1 - sp(t, t_out, "smooth")
        return y, a

    def char_state(self, t):
        """(x, feet_y, sx, sy, tilt_deg, word index, ground_y) of the character at t (None before it drops in)."""
        ws, H = self.words, self.H
        i = 0
        while i + 1 < len(ws) and t >= ws[i + 1]["s"] - ws[i + 1]["T"]:
            i += 1
        def spot(k):
            yo, _ = self.page_state(self.L.page_of[k], ws[k]["s"])
            return ws[k]["cx"], ws[k]["top"] - 0.004 * H + yo
        w = ws[i]
        to = w["s"] - w["T"]
        if i == 0:                                  # drops in from just above the frame
            x1, y1 = spot(0)
            x0, y0, h = x1, -0.02 * H, 0.0
        else:
            x0, y0 = spot(i - 1)
            x1, y1 = spot(i)
            h = min(0.20 * H, max(0.07 * H, 0.32 * abs(x1 - x0) + 0.5 * max(0.0, y0 - y1)))
            if ws[i].get("above") and ws[i - 1].get("above"):
                h = min(h, self.hcap)
        T = w["T"]
        sx = sy = 1.0
        tilt = 0.0
        if t < w["s"]:                               # in the air (or before take-off)
            u = max(0.0, (t - to) / T)
            if i == 0 and t < to:
                return None
            x = x0 + (x1 - x0) * u
            y = y0 + (y1 - y0) * u - 4 * h * u * (1 - u)
            vy = ((y1 - y0) - 4 * h * (1 - 2 * u)) / T
            vx = (x1 - x0) / T
            st = min(0.16, abs(vy) / H * 0.05)      # stretch along the fall / rise
            sy, sx = 1 + st, 1 - 0.5 * st
            tilt = -max(-14.0, min(14.0, 5.0 * vx / H))       # leans into the hop, at most 14 degrees
        else:                                       # standing on word i
            x, y = x1, y1
            vland = ((y1 - y0) + 4 * h) / T / H     # screens per second, down
            sq = min(0.32, max(-0.2, kick(t, w["s"], 3.6 * vland, "bouncy")))
            if i + 1 < len(ws):                     # crouch before the next take-off
                nt = ws[i + 1]["s"] - ws[i + 1]["T"]
                sq += 0.10 * sp(t, nt - 0.11, "ui") if t < nt else 0.0
            else:                                   # last word: keeps breathing
                sq += 0.025 * math.sin(2 * math.pi * 1.1 * (t - w["s"])) * sp(t, w["s"] + 0.4, "gentle")
            sy, sx = 1 - sq, 1 + 0.6 * sq
            if i + 1 == len(ws) and t > w["s"] + 0.55:   # after the last word: little hops in place, 0.8 s apart
                k = t - w["s"] - 0.55
                n, u = int(k // 0.8), (k % 0.8) / 0.38
                hh = 0.035 * H
                if u < 1:                               # in the air
                    y -= 4 * hh * u * (1 - u)
                    sy, sx = 1 + 0.06 * math.sin(math.pi * u), 1 - 0.03 * math.sin(math.pi * u)
                else:                                   # landed: squash from the landing speed (bouncy spring)
                    tl = w["s"] + 0.55 + n * 0.8 + 0.38
                    q = min(0.25, max(-0.15, kick(t, tl, 3.6 * (4 * hh / 0.38) / H, "bouncy")))
                    sy, sx = 1 - q, 1 + 0.6 * q
        return x, y, sx, sy, tilt, i, y1

    def frame(self, t):
        W, H = self.W, self.H
        if self.bg is not None:                     # the field lights up from dark on a smooth spring at frame 0
            pre, lo = self.lightup                  # dark field: fast from black; bright field: smooth from dim
            up = lo + (1 - lo) * sp(t, 0.0, pre) if t < 1.5 else 1.0
            im = self.bg.copy() if up >= 0.999 else Image.blend(self.dark, self.bg, up)
        else:
            im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        cs = self.char_state(t)
        cur = cs[5] if cs else -1
        # the words on lines above the character's line are drawn after it: a hop that rises into the line above passes
        # behind those words, so they always stay readable
        my_base = self.words[cur]["base"] if cur >= 0 else -1e9
        over = []
        for pi in range(len(self.L.pages)):
            yo, pa = self.page_state(pi, t)
            if pa <= 0.003:
                continue
            for i, pg in self.L.page_of.items():
                if pg != pi:
                    continue
                w = self.words[i]
                (dimI, litI, accI), asc = self.word_imgs[i]
                lit = sp(t, w["s"], "smooth") if t >= w["s"] else 0.0
                if lit <= 0.001:
                    wi = dimI
                else:
                    on = accI if i == cur else litI
                    if i != cur and i < cur:            # a passed word fades from accent to text
                        nx = self.words[i + 1]["s"]
                        k = sp(t, nx, "smooth")
                        on = Image.blend(accI, litI, k)
                    wi = Image.blend(dimI, on, lit) if lit < 0.999 else on
                pop = 1 + 0.10 * kick(t, w["s"], 6.0, "snappy") / 0.35 if t > w["s"] else 1.0
                if abs(pop - 1) > 0.002:
                    nw, nh = int(wi.width * pop), int(wi.height * pop)
                    wi2 = wi.resize((nw, nh), Image.BICUBIC)
                    px = w["x"] - 4 - (nw - wi.width) / 2
                    py = w["base"] + yo - asc * pop
                else:
                    wi2, px, py = wi, w["x"] - 4, w["base"] + yo - asc
                if pa < 0.999:
                    a = wi2.getchannel("A").point(lambda v, k=pa: int(v * k))
                    wi2 = wi2.copy(); wi2.putalpha(a)
                if cur >= 0 and pi == self.L.page_of[cur] and w["base"] < my_base - 1:
                    over.append((wi2, (int(round(px)), int(round(py)))))
                else:
                    im.alpha_composite(wi2, (int(round(px)), int(round(py))))
        if self.ref:
            f = self.ref_font
            a = sp(t, self.words[0]["s"] - 0.3, "smooth")
            tw = f.getlength(self.ref)
            lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            ImageDraw.Draw(lay).text(((W - tw) / 2, H - 0.075 * H), self.ref, font=f,
                                     fill=self.dim + (int(200 * a),), anchor="ls")
            im.alpha_composite(lay)
        if cs:
            x, y, sx, sy, tilt, _, ground = cs
            c = self.char
            cw, chh = max(1, int(c.width * sx)), max(1, int(c.height * sy))
            ci = c.resize((cw, chh), Image.BICUBIC)
            if abs(tilt) > 0.2:                        # about its centre; the feet stay near the anchor at these angles
                ci = ci.rotate(tilt, resample=Image.BICUBIC, expand=True)
            # contact shadow on the word, smaller and fainter the higher the character is
            if self.bg is not None:
                hgt = max(0.0, ground - y)
                k = max(0.0, 1 - hgt / (0.25 * H))
                if k > 0.02:
                    sw, shh = int(c.width * (0.5 + 0.4 * k)), max(2, int(c.width * 0.12))
                    sh = Image.new("RGBA", (sw + 20, shh + 20), (0, 0, 0, 0))
                    ImageDraw.Draw(sh).ellipse([10, 10, sw + 10, shh + 10], fill=(0, 0, 0, int(70 * k)))
                    sh = sh.filter(ImageFilter.GaussianBlur(5))
                    im.alpha_composite(sh, (int(x - sh.width / 2), int(ground - sh.height / 2)))
            im.alpha_composite(ci, (int(round(x - ci.width / 2)), int(round(y - ci.height))))
        for wi2, at in over:
            im.alpha_composite(wi2, at)
        return im


def _mean_luma(im):
    import numpy as np
    return float(np.asarray(im.convert("L").resize((64, 36))).mean())


def make_bg(P, mode, W, H, dim=0.62):
    if mode == "none":
        return None
    if mode.startswith("#"):
        return Image.new("RGBA", (W, H), tuple(int(mode.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)) + (255,))
    if os.path.isfile(mode):
        im = Image.open(mode).convert("RGBA")
        k = max(W / im.width, H / im.height)
        im = im.resize((int(im.width * k) + 1, int(im.height * k) + 1), Image.LANCZOS)
        return im.crop(((im.width - W) // 2, (im.height - H) // 2, (im.width - W) // 2 + W, (im.height - H) // 2 + H))
    grad = P.get("brand.gradient", None)
    cols = P.get("brand.colors")
    if mode in ("profile", "gradient") and grad and len(grad) >= 2:
        import numpy as np
        stops = np.array([[int(c.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)] for c in grad], float)
        xs = np.linspace(0, 1, W)[None, :] * 0.8 + np.linspace(0, 1, H)[:, None] * 0.2   # soft diagonal field
        pos = xs * (len(stops) - 1)
        i0 = np.clip(pos.astype(int), 0, len(stops) - 2)
        f = (pos - i0)[..., None]
        arr = stops[i0] * (1 - f) + stops[i0 + 1] * f
        arr *= dim                                     # dimmed so the profile's type colour reads on it
        im = Image.fromarray(arr.astype("uint8"), "RGB").filter(ImageFilter.GaussianBlur(40)).convert("RGBA")
        return im
    base = P.rgb("primary_deep") if "primary_deep" in cols else P.rgb("primary")
    return Image.new("RGBA", (W, H), base + (255,))


def main(argv=None):
    ap = argparse.ArgumentParser(description="bouncing-character verse / lyric (2D)")
    ap.add_argument("--text", help="the verse or lyric as it should read on screen")
    ap.add_argument("--out", required=True)
    ap.add_argument("--name", default="verse")
    ap.add_argument("--audio"); ap.add_argument("--words"); ap.add_argument("--chart")
    ap.add_argument("--wpm", type=float, default=0, help="pace words evenly (no audio)")
    ap.add_argument("--ref", default="", help="small reference line at the bottom, e.g. 'Galatians 5:22-23 (WEB)'")
    ap.add_argument("--character", help="RGBA PNG or SVG of the character (owned art only)")
    ap.add_argument("--aspect", default="16:9", choices=["16:9", "9:16"])
    ap.add_argument("--bg", default="profile", help="profile | gradient | '#hex' | image | none (alpha .mov)")
    ap.add_argument("--bg-dim", type=float, default=0.62, help="brightness of the profile gradient field (1 = as is)")
    ap.add_argument("--lead", type=float, default=1.0, help="seconds before the first word (paced / chart)")
    ap.add_argument("--tail", type=float, default=1.4, help="seconds after the last word (the character hops in place)")
    ap.add_argument("--fps", type=float, help="default: the profile's delivery.fps")
    ap.add_argument("--frames", help="only render these stills (seconds, comma separated)")
    ap.add_argument("--model", default="small.en"); ap.add_argument("--prompt", default="")
    prof.add_arg(ap)
    a = ap.parse_args(argv)
    P = prof.load(a.profile)
    os.makedirs(a.out, exist_ok=True)
    fps = a.fps or float(P.get("delivery.fps", 29.97002997))
    W, H = (1920, 1080) if a.aspect == "16:9" else (1080, 1920)

    text_words = a.text.split() if a.text else None
    timed = None
    if a.words:
        timed = json.load(open(a.words))["words"]
    elif a.audio:
        import captions
        d = captions.transcribe(a.audio, a.out, a.model, a.prompt or (a.text or ""), 0.3)
        captions.write_words(os.path.join(a.out, f"{a.name}.words.json"), d)
        timed = d["words"]
    elif a.chart:
        timed = from_chart(a.chart)
    if timed is None:
        if not (text_words and a.wpm):
            sys.exit("hopwords: give word times (--words, --audio or --chart) or --text with --wpm")
        words = paced(text_words, a.wpm, a.lead)
    elif text_words:
        words = align(text_words, timed)
    else:
        words = [{"w": w["w"], "s": float(w["s"]), "e": float(w["e"])} for w in timed]
    if not words:
        sys.exit("hopwords: no words")
    json.dump({"words": words}, open(os.path.join(a.out, f"{a.name}.timing.json"), "w"), indent=1)

    probe_h = int((0.13 if H > W else 0.082) * min(W, H) * 1.5)
    if a.character:
        char = load_char(a.character, probe_h)
    else:
        cols = P.get("brand.colors")
        ink = P.rgb("primary_deep") if "primary_deep" in cols else (30, 30, 30)
        char = placeholder_char(probe_h, P.rgb("accent"), ink)
    bg = make_bg(P, a.bg, W, H, a.bg_dim)
    hop = Hop(P, words, W, H, char, a.ref, bg, fps)
    dur = max(words[-1]["e"], words[-1]["s"]) + a.tail
    if a.audio:
        try:
            ad = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                       a.audio], capture_output=True, text=True, stdin=subprocess.DEVNULL).stdout)
            dur = max(dur, ad)
        except ValueError:
            pass
    base = os.path.join(a.out, f"{a.name}_hop")
    if a.frames:
        for t in (float(v) for v in a.frames.split(",")):
            fr = hop.frame(t)
            p = f"{base}_t{t:.2f}.png"
            fr.save(p); print("still", p)
        return
    n = int(round(dur * fps))
    mp4 = base + ".mp4"
    cmd = [FF, "-nostdin", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{H}",
           "-framerate", f"{fps}", "-i", "-"]
    if a.audio:
        cmd += ["-i", a.audio, "-map", "0:v", "-map", "1:a", "-c:a", "aac", "-b:a", "192k", "-shortest"]
    cmd += ["-c:v", "libx264", "-crf", "17", "-preset", "slow", "-pix_fmt", "yuv420p", "-threads", "4",
            "-movflags", "+faststart", mp4]
    procs = [subprocess.Popen(cmd, stdin=subprocess.PIPE)]
    if bg is None:
        procs.append(subprocess.Popen([FF, "-nostdin", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgba",
                                       "-s", f"{W}x{H}", "-framerate", f"{fps}", "-i", "-", "-c:v", "prores_ks",
                                       "-profile:v", "4444", "-pix_fmt", "yuva444p10le", "-threads", "4",
                                       base + "_Alpha.mov"], stdin=subprocess.PIPE))
    for i in range(n):
        fr = hop.frame(i / fps)
        raw = fr.tobytes()
        if bg is None:
            procs[1].stdin.write(raw)
            flat = Image.new("RGBA", fr.size, P.rgb("primary") + (255,)); flat.alpha_composite(fr); raw = flat.tobytes()
        procs[0].stdin.write(raw)
        if i % 30 == 0:
            sys.stdout.write(f"\r  frame {i}/{n}"); sys.stdout.flush()
    for p in procs:
        p.stdin.close(); p.wait()
    print(f"\r  wrote {mp4}" + (f" and {base}_Alpha.mov" if bg is None else "") + f"  ({n} frames, {dur:.2f} s)")


if __name__ == "__main__":
    main()
