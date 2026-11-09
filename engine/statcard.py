#!/usr/bin/env python3
"""statcard.py - stats lower third (O1): player cutout, #NN NAME, one big stat line, a row of 2-4 label/value pairs.

statcard.py <stats.json> <out_dir> [--name NAME] [--profile P] [--size 1920x1080] [--fps N] [--dur 5.5] [--start 0.1]
            [--bg <image | video | '#hex'>] [--bg-in SECONDS] [--frames t1,t2,...] [--no-logo]
            [--x0 PX] [--x1 PX] [--y1 PX]

--ae also writes <Name>_stats.jsx + <Name>_stats_ae/ (X1): run it in After Effects (File > Scripts > Run Script File)
to get the same card as a native comp: real text layers in the profile fonts, every spring baked to keyframes.

Writes <out_dir>/<Name>_stats_Alpha.mov (ProRes 4444 with alpha, full frame, for vMix / Premiere),
<Name>_stats.mp4 (preview on --bg) and <Name>_stats.png (the settled card, transparent).
--frames renders only those stills (<Name>_stats_t<t>.png, on --bg) for a quick look.

stats.json (filled in by hand; every key but name and stats is optional):
  {"num": 12, "name": "Player Name",
   "photo": "<cutout png>",          # default: <profile paths.headshot_cutouts>/<num>.png when that file exists
   "big": "77-YARD PICK-SIX",        # the one big stat line, e.g. "HEIGHT 5'2\\"" or "3 TDS"
   "stats": [["INT", "1"], ["RET YDS", "77"], ["TD", "1"]],   # 2-4 pairs; {"label": .., "value": ..} works too
   "count": true}                    # numbers count up (false: they appear as written)
A reel card can hold the same keys inline or point at the file:  "card": {"type": "stats", "file": "stats/12_player.json"}.

Brand comes only from the profile: colours primary / accent / text (text_dim and primary_deep when the profile has
them, else derived), fonts head / body / body_semibold, logo brand.logo_png (top right of the panel; --no-logo or
"logo": false hides it), safe area layout.safe_px (the default position). Nothing here knows any organisation.

Motion is spring.py only, a pure function of t: the panel slides in from the left edge (snappy), the photo rises
(snappy), the text arrives staggered 50-70 ms apart, right behind the panel's edge (snappy position, opacity on smooth, clamped: never overshoots),
every number counts up on one shared critically damped spring (never past its value; the same value
in two places always shows the same count), a light sweep crosses the panel during
the hold and the photo drifts in slowly so the card never sits dead, and the card leaves on smooth springs
(slide left + fade, ~0.33 s) at --dur - 0.35 s (a reel passes its own exit time).

From another tool:
    import statcard
    sc = statcard.StatCard(card, P, size=(1920, 1080), box=(x0, None, y1), start=0.35, exit_at=dur - 0.8)
    sc.frame(t)            # RGBA PIL image of sc.region (x, y, w, h), drawn at time t
    sc.write_mov(path, fps, dur, codec='png' | 'prores', full=False)   # region-sized (overlay at sc.region[:2]) or full frame
"""
import argparse
import json
import math
import os
import re
import subprocess
import sys

from PIL import Image, ImageChops, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import vprofile as prof  # noqa: E402
from spring import clamp01, progress, settle, spring_at, stagger  # noqa: E402

COUNT = {"zeta": 1.0, "omega": 7.0}      # count-up: critically damped, never passes the value, ~1.06 s to settle
EXIT = {"zeta": 1.0, "omega": 20.0}      # exit: slide + fade together, no overshoot, ~0.33 s (the player card fades in 0.3 s)
NUM_RE = re.compile(r"\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?")


# ---- card data -------------------------------------------------------------------------------------------------
def is_stats(card):
    return isinstance(card, dict) and card.get("type") == "stats"


def load_card(card, base_dir=None, map_path=None, P=None):
    """A stats card from a dict (inline, or {"file": ...} merged under inline keys) or a JSON path.
    Returns a clean dict: num, name, photo (path or None), big, stats [(label, value)], count, logo."""
    mp = map_path or (lambda p: p)
    if isinstance(card, str):
        card = {"file": os.path.abspath(card)}
    c = dict(card)
    if c.get("file"):
        f = mp(c["file"])
        if not os.path.isabs(f) and base_dir:
            f = os.path.join(base_dir, f)
        with open(f) as fh:
            data = json.load(fh)
        base_dir = os.path.dirname(os.path.abspath(f))
        data.update({k: v for k, v in c.items() if k not in ("file", "type")})
        c = data
    if not c.get("name"):
        raise ValueError("stats card: 'name' is required")
    stats = c.get("stats") or []
    if isinstance(stats, dict):
        stats = list(stats.items())
    pairs = []
    for s in stats:
        if isinstance(s, dict):
            pairs.append((str(s["label"]), str(s["value"])))
        else:
            pairs.append((str(s[0]), str(s[1])))
    if not 2 <= len(pairs) <= 4:
        raise ValueError(f"stats card {c['name']!r}: 'stats' needs 2-4 label/value pairs, got {len(pairs)}")
    photo = c.get("photo")
    if photo:
        photo = mp(photo)
        if not os.path.isabs(photo) and base_dir:
            photo = os.path.join(base_dir, photo)
    elif c.get("num") is not None and P is not None and P.has_path("headshot_cutouts"):
        cand = os.path.join(P.path("headshot_cutouts"), f"{c['num']}.png")
        photo = cand if os.path.isfile(cand) else None
    return {"num": c.get("num"), "name": str(c["name"]).upper(), "photo": photo,
            "big": str(c["big"]).upper() if c.get("big") else "", "stats": [(l.upper(), v.upper()) for l, v in pairs],
            "count": bool(c.get("count", True)), "logo": c.get("logo", True), "_loaded": True}


# ---- helpers ---------------------------------------------------------------------------------------------------
def rate(fps):
    """'60000/1001' | 29.97 -> frames per second as a float"""
    if isinstance(fps, str) and "/" in fps:
        a, b = fps.split("/")
        return float(a) / float(b)
    return float(fps)


def count_segments(text):
    """[(segment, is_number)] for a string, numbers split out (1,234 and 4.5 count as one number)"""
    out, pos = [], 0
    for m in NUM_RE.finditer(text):
        if m.start() > pos:
            out.append((text[pos:m.start()], False))
        out.append((m.group(0), True))
        pos = m.end()
    if pos < len(text):
        out.append((text[pos:], False))
    return out


def counted(token, p):
    """number token shown at count progress p (0..1, clamped): never past its own value"""
    p = clamp01(p)
    commas = "," in token
    v = float(token.replace(",", ""))
    dec = len(token.split(".")[1]) if "." in token else 0
    cur = v * p
    if dec:
        return f"{cur:.{dec}f}"
    n = int(math.floor(cur + 0.5)) if p < 1 else int(v)
    n = min(n, int(v))
    return f"{n:,}" if commas else str(n)


def with_opacity(im, op):
    if op >= 0.999:
        return im
    im = im.copy()
    a = im.getchannel("A").point(lambda v: int(v * max(0.0, op) + 0.5))
    im.putalpha(a)
    return im


def comp(dst, src, x, y):
    """alpha_composite src onto dst at (x, y), cropping whatever falls outside dst (negative x/y allowed)"""
    x, y = int(round(x)), int(round(y))
    if x >= dst.width or y >= dst.height or x + src.width <= 0 or y + src.height <= 0:
        return
    l, t = max(0, -x), max(0, -y)
    r, b = min(src.width, dst.width - x), min(src.height, dst.height - y)
    if (l, t, r, b) != (0, 0, src.width, src.height):
        src = src.crop((l, t, r, b))
    dst.alpha_composite(src, (x + l, y + t))


def darker(rgb, k):
    return tuple(int(c * k) for c in rgb)


# ---- the card --------------------------------------------------------------------------------------------------
class StatCard:
    """Layout once, then frame(t) draws the card at time t (pure function of t)."""

    def __init__(self, card, P, size=(1920, 1080), box=None, start=0.35, exit_at=None, font=None, logo=None,
                 base_dir=None, map_path=None):
        self.P = P
        self.c = card if card.get("_loaded") else load_card(card, base_dir, map_path, P)
        self.W, self.H = size
        self.start = float(start)
        self.exit_at = exit_at
        self._font = font or (lambda role, sz: ImageFont.truetype(P.font(role), sz))
        cols = P.get("brand.colors")
        self.primary, self.accent = P.rgb("primary"), P.rgb("accent")
        self.text = P.rgb("text") if "text" in cols else (255, 255, 255)
        self.dim = P.rgb("text_dim") if "text_dim" in cols else tuple(int(0.8 * a + 0.2 * b) for a, b in zip(self.text, self.primary))
        self.deep = P.rgb("primary_deep") if "primary_deep" in cols else darker(self.primary, 0.6)
        fonts = P.get("brand.fonts")
        self.label_role = "body_semibold" if "body_semibold" in fonts else "body"
        show_logo = self.c.get("logo", True) if logo is None else logo
        self.logo = None
        if show_logo:
            try:
                lg = Image.open(P.asset("brand.logo_png")).convert("RGBA")
                self.logo = lg.crop(lg.getchannel("A").getbbox())
            except Exception:  # noqa: BLE001  (no logo in the profile, or not on this machine)
                self.logo = None
        safe = int(P.get("layout.safe_px", 90))
        b = list(box or (None, None, None))
        while len(b) < 3:
            b.append(None)
        self.bx0 = safe if b[0] is None else int(b[0])
        self.bx1 = self.W - safe if b[1] is None else int(b[1])
        self.by1 = self.H - safe if b[2] is None else int(b[2])
        self.s = min(self.W, self.H) / 1080.0
        self._layout()

    # -- layout --
    def _layout(self):
        s, c = self.s, self.c
        F = self._font
        sizes = {"name": 64, "big": 132, "val": 62, "lab": 34}
        self.photo = None
        if c.get("photo"):
            try:
                ph = Image.open(c["photo"]).convert("RGBA")
                ph = ph.crop(ph.getchannel("A").getbbox())
                k = min(360 * s / ph.height, 300 * s / ph.width)
                self.photo = ph.resize((max(1, int(ph.width * k)), max(1, int(ph.height * k))), Image.LANCZOS)
            except Exception:  # noqa: BLE001
                self.photo = None
        # fit: each line that is wider than the room in the text column shrinks by the ratio it is over (floors keep it
        # readable); the column's left edge depends only on the photo, so a few passes settle it
        floors = {"name": 28, "big": 40, "val": 30, "lab": 16}
        for _ in range(8):
            L = self._try_layout(sizes)
            room = self.bx1 - int(40 * s) - L["tx"]
            if L["x1"] <= self.bx1 or room <= 0:
                break
            for key, w in (("big", L["big_w"]), ("name", L["name_w"] + L["logo_room"]), ("val", L["cells_w"])):
                if w > room:
                    k = room / w * 0.98
                    sizes[key] = max(floors[key], int(sizes[key] * k))
                    if key == "val":
                        sizes["lab"] = max(floors["lab"], int(sizes["lab"] * k))
        L = self._try_layout(sizes)
        self.L = L
        self.F = {k: F("head" if k != "lab" else self.label_role, int(v * s)) for k, v in sizes.items()}
        self.F["lab"] = F(self.label_role, int(sizes["lab"] * s))
        self._static_layers()

    def _try_layout(self, sizes):
        s, c, F = self.s, self.c, self._font
        fN, fB = F("head", int(sizes["name"] * s)), F("head", int(sizes["big"] * s))
        fV, fL = F("head", int(sizes["val"] * s)), F(self.label_role, int(sizes["lab"] * s))
        cap = lambda f: -f.getbbox("H", anchor="ls")[1]
        x0, y1 = self.bx0, self.by1
        bar = int(12 * s); rule = int(6 * s); pad = int(26 * s)
        pw = self.photo.width if self.photo else 0
        tx = x0 + bar + (int(20 * s) + pw + int(26 * s) if self.photo else pad)
        num = f"#{c['num']}" if c.get("num") is not None else ""
        name_w = fN.getlength((num + "  " if num else "") + c["name"])
        big_w = fB.getlength(c["big"]) if c["big"] else 0
        cellpad = int(30 * s)
        cells, cx = [], tx
        for i, (lab, val) in enumerate(c["stats"]):
            w = max(fL.getlength(lab), fV.getlength(val))
            cells.append((cx, w))
            cx += w + (2 * cellpad if i + 1 < len(c["stats"]) else 0)
        cells_w = cx - tx
        logo_h = int(46 * s) if self.logo else 0
        logo_w = int(self.logo.width * logo_h / self.logo.height) if self.logo else 0
        logo_room = logo_w + int(40 * s) if self.logo else 0
        x1 = int(max(tx + name_w + logo_room, tx + big_w, tx + cells_w) + int(40 * s))
        x1 = max(x1, x0 + int(560 * s))
        capN, capB, capV = cap(fN), cap(fB), cap(fV)
        band_h = int(38 * s) + int(10 * s) + capV + int(20 * s)
        top_pad = int(22 * s)
        name_base = top_pad + capN
        big_base = name_base + (int(20 * s) + capB if c["big"] else 0)
        band_top = big_base + int(24 * s)
        panel_h = band_top + band_h + rule
        y0 = y1 - panel_h
        return {"x0": x0, "y0": y0, "x1": x1, "y1": y1, "tx": tx, "bar": bar, "rule": rule, "num": num,
                "name_w": name_w, "big_w": big_w, "cells": cells, "cells_w": cells_w, "cellpad": cellpad,
                "logo_h": logo_h, "logo_w": logo_w, "logo_room": logo_room,
                "name_base": y0 + name_base, "big_base": y0 + big_base, "band_top": y0 + band_top,
                "lab_base": y0 + band_top + int(38 * s), "val_base": y0 + band_top + int(38 * s) + int(10 * s) + capV,
                "capN": capN}

    def _static_layers(self):
        L, s = self.L, self.s
        pw, ph = L["x1"] - L["x0"], L["y1"] - L["y0"]
        # panel: primary body, deep stat band, accent bar on the left and accent rule along the bottom
        pan = Image.new("RGBA", (pw, ph), (0, 0, 0, 0)); d = ImageDraw.Draw(pan)
        d.rectangle([0, 0, pw, ph], fill=self.primary + (250,))
        d.rectangle([0, L["band_top"] - L["y0"], pw, ph], fill=self.deep + (255,))
        d.rectangle([0, 0, L["bar"], ph], fill=self.accent + (255,))
        d.rectangle([L["bar"], ph - L["rule"], pw, ph], fill=self.accent + (255,))
        self.panel = pan
        self.panel_mask = pan.getchannel("A")
        # region that holds everything (the panel slides in from the left frame edge, so it starts at x=0)
        top = L["y0"]
        if self.photo is not None:
            top = min(top, L["y1"] - L["rule"] - self.photo.height - int(60 * s))
        self.ry = max(0, top - int(8 * s))
        self.region = (0, self.ry, min(self.W, L["x1"] + int(8 * s)), L["y1"] + 2 - self.ry)
        if self.logo is not None:
            self.logo_s = self.logo.resize((max(1, L["logo_w"]), max(1, L["logo_h"])), Image.LANCZOS)

    # -- timing --
    def times(self):
        T = self.start
        n = len(self.c["stats"])
        cell_t = stagger(n, T + 0.18, 0.06)
        return {"panel": T, "photo": T + 0.05, "name": T + 0.07, "big": T + 0.12, "logo": T + 0.16, "cells": cell_t,
                "sweep": cell_t[-1] + 0.45, "count": T + 0.12,      # every number counts on one clock (no 77 vs 54)
                "settled": max(T + 0.12 + settle(**COUNT), cell_t[-1] + settle("smooth"))}

    def still_time(self):
        return self.times()["settled"]

    # -- drawing --
    def _text(self, layer, xy, segs_final, f, fill, num_fill, p_count):
        """draw a string at its final layout; numbers count up right-aligned in their final width (no jitter)"""
        d = ImageDraw.Draw(layer)
        x, y = xy
        for seg, isnum in segs_final:
            w = f.getlength(seg)
            if isnum and self.c["count"]:
                cur = counted(seg, p_count)
                d.text((x + w - f.getlength(cur), y), cur, font=f, fill=num_fill, anchor="ls")
            else:
                d.text((x, y), seg, font=f, fill=num_fill if isnum else fill, anchor="ls")
            x += w

    def frame(self, t, sweep=True):
        """the card at time t (RGBA, size of self.region). sweep=False leaves out the light sweep (for stills)."""
        L, s, c, tm = self.L, self.s, self.c, self.times()
        rx, ry, rw, rh = self.region
        im = Image.new("RGBA", (rw, rh), (0, 0, 0, 0))
        gx = spring_at(t, frm=-(L["x1"] + 40 * s), to=0, start=tm["panel"], preset="snappy")
        ga = 1.0
        if self.exit_at is not None:
            gx += spring_at(t, frm=0, to=-90 * s, start=self.exit_at, **EXIT)
            ga = 1 - clamp01(progress(t, start=self.exit_at, **EXIT))
        if t < tm["panel"] or ga <= 0.002:
            return im
        ox = int(round(gx))
        # panel + light sweep during the hold (clipped to the panel)
        pan = self.panel
        # light sweep: one pass from the left edge, starting at full speed (v0 = omega: a critically damped spring
        # that only decelerates) and still crossing the panel when the card leaves, so the hold never goes dead
        hold_end = self.exit_at if self.exit_at is not None else tm["sweep"] + 3.0
        omega = min(3.0, max(0.25, 2.3 / max(0.6, hold_end - tm["sweep"])))
        if sweep and t > tm["sweep"]:
            pw, ph = pan.size
            sw = int(140 * s)
            sx = spring_at(t, frm=-sw, to=pw + ph * 0.5, start=tm["sweep"], zeta=1.0, omega=omega, v0=omega)
            sh = Image.new("RGBA", pan.size, (0, 0, 0, 0)); ds = ImageDraw.Draw(sh)
            for k, a in ((0, 10), (int(40 * s), 22), (int(80 * s), 10)):   # soft-edged band
                ds.polygon([(sx + k, 0), (sx + k + int(60 * s), 0), (sx + k + int(60 * s) - ph * 0.5, ph),
                            (sx + k - ph * 0.5, ph)], fill=(255, 255, 255, a))
            sh.putalpha(ImageChops.multiply(sh.getchannel("A"), self.panel_mask))
            pan = pan.copy(); pan.alpha_composite(sh)
        comp(im, pan, L["x0"] + ox - rx, L["y0"] - ry)
        # photo: rises out of the panel (clipped at the bottom rule), then drifts in slowly
        if self.photo is not None and t >= tm["photo"]:
            push = 1 + 0.035 * clamp01(progress(t, start=tm["photo"] + 0.3, zeta=1.0, omega=0.45))
            ph_ = self.photo
            if push > 1.0005:
                ph_ = ph_.resize((int(ph_.width * push), int(ph_.height * push)), Image.BILINEAR)
            dy = spring_at(t, frm=90 * s, to=0, start=tm["photo"], preset="snappy")
            op = clamp01(progress(t, start=tm["photo"], preset="smooth"))
            base_x = L["x0"] + L["bar"] + int(20 * s) + (self.photo.width - ph_.width) // 2
            bottom = L["y1"] - L["rule"]
            y = int(round(bottom - ph_.height + dy))
            vis = max(0, min(ph_.height, bottom - y))
            if vis > 0:
                comp(im, with_opacity(ph_.crop((0, 0, ph_.width, vis)), op), base_x + ox - rx, y - ry)
        # text, staggered: slide 36 px in from the left on snappy, opacity on smooth (clamped)
        def arrive(t0):
            return (spring_at(t, frm=-36 * s, to=0, start=t0, preset="snappy"),
                    clamp01(progress(t, start=t0, preset="smooth")))
        lay = Image.new("RGBA", im.size, (0, 0, 0, 0))
        if t >= tm["name"]:
            dx, op = arrive(tm["name"])
            a = int(255 * op)
            d = ImageDraw.Draw(lay)
            x = L["tx"] + ox + dx - rx
            if L["num"]:
                d.text((x, L["name_base"] - ry), L["num"], font=self.F["name"], fill=self.accent + (a,), anchor="ls")
                x += self.F["name"].getlength(L["num"] + "  ")
            d.text((x, L["name_base"] - ry), c["name"], font=self.F["name"], fill=self.text + (a,), anchor="ls")
        if c["big"] and t >= tm["big"]:
            dx, op = arrive(tm["big"])
            a = int(255 * op)
            self._text(lay, (L["tx"] + ox + dx - rx, L["big_base"] - ry), count_segments(c["big"]), self.F["big"],
                       self.text + (a,), self.accent + (a,), progress(t, start=tm["count"], **COUNT))
        for (lab, val), (cx, w), t0 in zip(c["stats"], L["cells"], tm["cells"]):
            if t < t0:
                continue
            dy = spring_at(t, frm=18 * s, to=0, start=t0, preset="snappy")
            op = clamp01(progress(t, start=t0, preset="smooth")); a = int(255 * op)
            d = ImageDraw.Draw(lay)
            if t0 != tm["cells"][0]:          # the divider before this cell arrives with it
                xd = cx - L["cellpad"] + ox - rx; hw = max(1, int(s))
                d.rectangle([xd - hw, L["band_top"] + int(18 * s) + dy - ry, xd + hw,
                             L["y1"] - L["rule"] - int(16 * s) + dy - ry], fill=self.accent + (int(150 * op),))
            d.text((cx + ox - rx, L["lab_base"] + dy - ry), lab, font=self.F["lab"], fill=self.dim + (a,), anchor="ls")
            self._text(lay, (cx + ox - rx, L["val_base"] + dy - ry), count_segments(val), self.F["val"],
                       self.text + (a,), self.text + (a,), progress(t, start=tm["count"], **COUNT))
        im.alpha_composite(lay)
        # logo: arrives from slightly oversize (never from 0), opacity on smooth
        if self.logo is not None and t >= tm["logo"]:
            k = spring_at(t, frm=1.25, to=1.0, start=tm["logo"], preset="snappy")
            op = clamp01(progress(t, start=tm["logo"], preset="smooth"))
            lg = self.logo_s.resize((max(1, int(self.logo_s.width * k)), max(1, int(self.logo_s.height * k))), Image.LANCZOS)
            cxl = L["x1"] - int(28 * s) - L["logo_w"] / 2 + ox
            cyl = L["name_base"] - L["capN"] / 2
            comp(im, with_opacity(lg, op), cxl - lg.width / 2 - rx, cyl - lg.height / 2 - ry)
        if ga < 0.999:
            im = with_opacity(im, ga)
        return im

    def full_frame(self, t, sweep=True):
        fr = Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))
        comp(fr, self.frame(t, sweep), *self.region[:2])
        return fr

    # -- output --
    def write_mov(self, out, fps, dur, codec="png", full=False):
        """frames 0..dur at fps -> .mov with alpha. codec 'png' (lossless, small: reel intermediates) or 'prores'
        (ProRes 4444, yuva444p10le). full=False writes only self.region (overlay it at self.region[:2])."""
        fr = rate(fps)
        n = int(round(dur * fr))
        w, h = (self.W, self.H) if full else self.region[2:]
        enc = (["-c:v", "png", "-pix_fmt", "rgba"] if codec == "png" else
               ["-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le", "-alpha_bits", "16",
                "-vendor", "apl0"])
        cmd = ["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{w}x{h}",
               "-framerate", str(fps), "-i", "pipe:0"] + enc + [out]
        p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        try:
            for i in range(n):
                t = i / fr
                p.stdin.write((self.full_frame(t) if full else self.frame(t)).tobytes())
        finally:
            p.stdin.close()
        if p.wait():
            raise SystemExit(f"statcard: ffmpeg failed writing {out}")
        return out


# ---- X1: the same card as a native After Effects comp ---------------------------------------------------------
def ae_export(sc, jsx_path, fps, dur):
    """Write <jsx_path> (+ <name>_ae/ assets): the card rebuilt in After Effects with native text layers and every
    spring baked to keyframes, sampled from the same functions frame() draws (so the AE comp moves like the render).
    Approximations: the photo's bottom clip is a track matte (same result); text uses the profile fonts by PostScript
    name (install them for AE)."""
    import aejsx
    L, s, c, tm = sc.L, sc.s, sc.c, sc.times()
    fr = rate(fps); n = int(round(dur * fr))
    ts = [i / fr for i in range(n + 1)]
    W, H = sc.W, sc.H
    name = os.path.splitext(os.path.basename(jsx_path))[0]
    adir = os.path.join(os.path.dirname(os.path.abspath(jsx_path)), name + "_ae"); os.makedirs(adir, exist_ok=True)
    C = aejsx.Comp(name, W, H, fr, dur)
    col = lambda rgb: [v / 255 for v in rgb]
    hold_end = sc.exit_at if sc.exit_at is not None else tm["sweep"] + 3.0
    def gx(t):
        x = spring_at(t, frm=-(L["x1"] + 40 * s), to=0, start=tm["panel"], preset="snappy")
        if sc.exit_at is not None:
            x += spring_at(t, frm=0, to=-90 * s, start=sc.exit_at, **EXIT)
        return x
    def ga(t):                                      # per-layer part: off before the panel starts (the exit fade is the
        return 0.0 if t < tm["panel"] else 1.0      # group opacity on the precomp, like frame()'s whole-card fade)
    card = C.null("Card (slide)")
    card.track("position", [(t, (gx(t), 0)) for t in ts])
    # panel (+ a hidden copy as the sweep's matte)
    sc.panel.save(os.path.join(adir, "panel.png"))
    op_all = [(t, 100 * ga(t)) for t in ts]
    # logo
    if sc.logo is not None:
        sc.logo_s.save(os.path.join(adir, "logo.png"))
        lw, lh = sc.logo_s.size
        lg = C.image("Logo", os.path.join(adir, "logo.png"), pos=(L["x1"] - int(28 * s) - L["logo_w"] / 2, L["name_base"] - L["capN"] / 2),
                     anchor=(lw / 2, lh / 2), parent=card)
        lg.track("scale", [(t, (100 * spring_at(t, frm=1.25, to=1.0, start=tm["logo"], preset="snappy"),) * 2) for t in ts])
        lg.track("opacity", [(t, 100 * ga(t) * (clamp01(progress(t, start=tm["logo"], preset="smooth")) if t >= tm["logo"] else 0)) for t in ts])
    # text
    def arrive(t, t0):
        if t < t0:
            return -36 * s, 0.0
        return spring_at(t, frm=-36 * s, to=0, start=t0, preset="snappy"), clamp01(progress(t, start=t0, preset="smooth"))
    head_ps, lab_ps = aejsx.ps_name(sc.P.font("head")), aejsx.ps_name(sc.P.font(sc.label_role))
    def text_run(nm, x0, base, segs, font, ps, fill, num_fill, t0, slide="x", size=None):
        x = x0
        for k, (seg, isnum) in enumerate(segs):
            w = font.getlength(seg)
            counting = isnum and c["count"]
            lay = C.text(f"{nm} {k + 1}", seg, ps, size or font.size, col(num_fill if isnum else fill),
                         pos=(x + w, base) if counting else (x, base), justify="right" if counting else "left", parent=card)
            def pos(t, X=(x + w if counting else x)):
                d, _ = arrive(t, t0) if slide == "x" else (0, 0)
                dy = (spring_at(t, frm=18 * s, to=0, start=t0, preset="snappy") if t >= t0 else 18 * s) if slide == "y" else 0
                return (X + d, base + dy)
            lay.track("position", [(t, pos(t)) for t in ts])
            lay.track("opacity", [(t, 100 * ga(t) * arrive(t, t0)[1]) for t in ts])
            if counting:
                lay.source_track([(t, counted(seg, progress(t, start=tm["count"], **COUNT))) for t in ts])
            x += w
    if L["num"]:
        text_run("Number", L["tx"], L["name_base"], [(L["num"], False)], sc.F["name"], head_ps, sc.accent, sc.accent, tm["name"])
    nx = L["tx"] + (sc.F["name"].getlength(L["num"] + "  ") if L["num"] else 0)
    text_run("Name", nx, L["name_base"], [(c["name"], False)], sc.F["name"], head_ps, sc.text, sc.text, tm["name"])
    if c["big"]:
        text_run("Big", L["tx"], L["big_base"], count_segments(c["big"]), sc.F["big"], head_ps, sc.text, sc.accent, tm["big"])
    for i, ((lab, val), (cx, w), t0) in enumerate(zip(c["stats"], L["cells"], tm["cells"])):
        text_run(f"Label {i + 1}", cx, L["lab_base"], [(lab, False)], sc.F["lab"], lab_ps, sc.dim, sc.dim, t0, slide="y")
        text_run(f"Value {i + 1}", cx, L["val_base"], count_segments(val), sc.F["val"], head_ps, sc.text, sc.text, t0, slide="y")
        if i:
            hw = max(1, int(s)); xd = cx - L["cellpad"]
            hgt = (L["y1"] - L["rule"] - int(16 * s)) - (L["band_top"] + int(18 * s)) + 1    # both edges, like the render
            wd = 2 * hw + 1; sw = max(4, wd)                 # AE solids are at least 4 px: build it wider, scale it back
            dv = C.solid(f"Divider {i}", (sw, hgt), col(sc.accent), pos=(xd - hw, L["band_top"] + int(18 * s)), parent=card)
            if sw != wd:
                dv.track("scale", [(0.0, (100.0 * wd / sw, 100.0))])
            dv.track("position", [(t, (xd - hw, L["band_top"] + int(18 * s) + (spring_at(t, frm=18 * s, to=0, start=t0, preset="snappy") if t >= t0 else 18 * s))) for t in ts])
            dv.track("opacity", [(t, 100 * ga(t) * (150 / 255) * arrive(t, t0)[1]) for t in ts])
    # photo, clipped at the panel's bottom rule by a matte that moves with the card
    if sc.photo is not None:
        sc.photo.save(os.path.join(adir, "photo.png"))
        pw_, ph_ = sc.photo.size
        bottom = L["y1"] - L["rule"]
        ph = C.image("Photo", os.path.join(adir, "photo.png"), pos=(L["x0"] + L["bar"] + int(20 * s) + pw_ / 2, bottom),
                     anchor=(pw_ / 2, ph_), parent=card)
        clip = C.solid("Photo clip (matte)", (W + 400, bottom), [1, 1, 1], pos=(-200, 0), parent=card)
        C.matte(ph, clip)
        push = lambda t: 100 * (1 + 0.035 * clamp01(progress(t, start=tm["photo"] + 0.3, zeta=1.0, omega=0.45)))
        ph.track("scale", [(t, (push(t), push(t))) for t in ts])
        ph.track("position", [(t, (L["x0"] + L["bar"] + int(20 * s) + pw_ / 2,
                                   bottom + (spring_at(t, frm=90 * s, to=0, start=tm["photo"], preset="snappy") if t >= tm["photo"] else 90 * s))) for t in ts])
        ph.track("opacity", [(t, 100 * ga(t) * (clamp01(progress(t, start=tm["photo"], preset="smooth")) if t >= tm["photo"] else 0)) for t in ts])
    # light sweep across the panel during the hold (matte: a copy of the panel)
    pw, phh = sc.panel.size
    sw = int(140 * s); o = int(phh * 0.5)
    band = Image.new("RGBA", (o + int(80 * s) + int(60 * s) + 4, phh), (0, 0, 0, 0)); ds = ImageDraw.Draw(band)
    for k, a in ((0, 10), (int(40 * s), 22), (int(80 * s), 10)):
        ds.polygon([(o + k, 0), (o + k + int(60 * s), 0), (o + k + int(60 * s) - phh * 0.5, phh), (o + k - phh * 0.5, phh)], fill=(255, 255, 255, a))
    band.save(os.path.join(adir, "sweep.png"))
    omega = min(3.0, max(0.25, 2.3 / max(0.6, hold_end - tm["sweep"])))
    sweep = C.image("Light sweep", os.path.join(adir, "sweep.png"), pos=(L["x0"] - sw - o, L["y0"]), parent=card)
    sweep.track("position", [(t, (L["x0"] - o + (spring_at(t, frm=-sw, to=pw + phh * 0.5, start=tm["sweep"], zeta=1.0, omega=omega, v0=omega)
                                                 if t > tm["sweep"] else -sw), L["y0"])) for t in ts])
    sweep.track("opacity", op_all)
    pm = C.image("Panel (sweep matte)", os.path.join(adir, "panel.png"), pos=(L["x0"], L["y0"]), parent=card)
    C.matte(sweep, pm)
    pan = C.image("Panel", os.path.join(adir, "panel.png"), pos=(L["x0"], L["y0"]), parent=card)
    pan.track("opacity", op_all)
    if sc.exit_at is not None:
        C.group_opacity([(t, 100 * (1 - clamp01(progress(t, start=sc.exit_at, **EXIT)))) for t in ts])
    # paint order: the spec lists layers top first, so move the panel to the bottom (null stays on top)
    C.layers.remove(pan); C.layers.append(pan)
    return C.write(jsx_path, adir)


# ---- CLI -------------------------------------------------------------------------------------------------------
def _bg_input(bg, bg_in, W, H, fps, dur, P):
    """ffmpeg input args + filter for the preview background"""
    if bg and os.path.isfile(bg):
        if bg.lower().endswith((".png", ".jpg", ".jpeg")):
            return ["-loop", "1", "-framerate", str(fps), "-t", f"{dur:.3f}", "-i", bg], \
                f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,format=yuv420p[b]"
        return ["-ss", f"{bg_in:.3f}", "-t", f"{dur:.3f}", "-i", bg], \
            (f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,fps={fps},"
             f"format=yuv420p[b]")
    col = (bg or ("#%02x%02x%02x" % (P.rgb("primary_deep") if "primary_deep" in P.get("brand.colors")
                                    else darker(P.rgb("primary"), 0.6)))).lstrip("#")
    return ["-f", "lavfi", "-i", f"color=c=0x{col}:s={W}x{H}:r={fps}:d={dur:.3f}"], "[0:v]format=yuv420p[b]"


def bg_frame(bg, bg_in, W, H, t, P):
    """one background frame (RGBA) for still previews"""
    if bg and os.path.isfile(bg) and not bg.lower().endswith((".png", ".jpg", ".jpeg")):
        r = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-ss", f"{bg_in + t:.3f}", "-i", bg, "-frames:v", "1",
                            "-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}", "-f", "rawvideo",
                            "-pix_fmt", "rgba", "-"], capture_output=True, stdin=subprocess.DEVNULL)
        return Image.frombytes("RGBA", (W, H), r.stdout)
    if bg and os.path.isfile(bg):
        im = Image.open(bg).convert("RGBA")
        k = max(W / im.width, H / im.height)
        im = im.resize((int(im.width * k + 0.5), int(im.height * k + 0.5)), Image.LANCZOS)
        return im.crop(((im.width - W) // 2, (im.height - H) // 2, (im.width - W) // 2 + W, (im.height - H) // 2 + H))
    col = (bg or "").lstrip("#")
    rgb = tuple(int(col[i:i + 2], 16) for i in (0, 2, 4)) if len(col) == 6 else (
        P.rgb("primary_deep") if "primary_deep" in P.get("brand.colors") else darker(P.rgb("primary"), 0.6))
    return Image.new("RGBA", (W, H), rgb + (255,))


def main(argv=None):
    ap = argparse.ArgumentParser(description="stats lower third: ProRes 4444 alpha .mov + MP4 preview + PNG still")
    ap.add_argument("stats"); ap.add_argument("out")
    ap.add_argument("--name", help="output name (default: the stats file name)")
    prof.add_arg(ap)
    ap.add_argument("--size", default=None, help="WxH (default: the profile's delivery.size)")
    ap.add_argument("--fps", default=None, help="frame rate, e.g. 29.97 or 60000/1001 (default: the profile's delivery.fps)")
    ap.add_argument("--dur", type=float, default=5.5, help="length in seconds (default 5.5; the card leaves at dur - 0.35)")
    ap.add_argument("--start", type=float, default=0.0, help="when the panel starts in (s; default 0: moving from frame 1)")
    ap.add_argument("--bg", help="preview background: an image, a video or '#hex' (default: the profile's deep primary)")
    ap.add_argument("--bg-in", type=float, default=0.0, help="start time in a --bg video")
    ap.add_argument("--frames", help="only render these stills (seconds, comma separated) on --bg")
    ap.add_argument("--no-logo", action="store_true")
    ap.add_argument("--ae", action="store_true", help="X1: also write <name>_stats.jsx (+ _ae/ assets): the card as a "
                    "native After Effects comp, springs baked to keyframes (File > Scripts > Run Script File)")
    ap.add_argument("--x0", type=int); ap.add_argument("--x1", type=int); ap.add_argument("--y1", type=int)
    a = ap.parse_args(argv)
    P = prof.load(a.profile)
    W, H = (int(v) for v in (a.size or P.get("delivery.size", "1920x1080")).split("x"))
    fps = a.fps or P.get("delivery.fps", 29.97002997)
    if isinstance(fps, float) and abs(fps - 30000 / 1001) < 0.01:
        fps = "30000/1001"
    elif isinstance(fps, float) and abs(fps - 60000 / 1001) < 0.01:
        fps = "60000/1001"
    card = load_card(a.stats, P=P)
    name = a.name or os.path.splitext(os.path.basename(a.stats))[0]
    os.makedirs(a.out, exist_ok=True)
    sc = StatCard(card, P, size=(W, H), box=(a.x0, a.x1, a.y1), start=a.start, exit_at=a.dur - 0.35,
                  logo=False if a.no_logo else None)
    base = os.path.join(a.out, f"{name}_stats")
    if a.frames:
        for t in (float(x) for x in a.frames.split(",")):
            im = bg_frame(a.bg, a.bg_in, W, H, t, P)
            im.alpha_composite(sc.full_frame(t))  # noqa
            p = f"{base}_t{t:.2f}.png"; im.convert("RGB").save(p); print("still", p)
        return 0
    still = sc.full_frame(sc.still_time(), sweep=False)
    still.save(base + ".png"); print("still", base + ".png", f"(t={sc.still_time():.2f} s)")
    sc.write_mov(base + "_Alpha.mov", fps, a.dur, codec="prores", full=True); print("alpha", base + "_Alpha.mov")
    ins, bgf = _bg_input(a.bg, a.bg_in, W, H, fps, a.dur, P)
    r = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y"] + ins + ["-i", base + "_Alpha.mov", "-filter_complex",
                       bgf + ";[b][1:v]overlay=0:0:shortest=1:format=auto,format=yuv420p[v]", "-map", "[v]",
                       "-t", f"{a.dur:.3f}", "-r", str(fps), "-c:v", "libx264", "-crf", "18", "-preset", "medium",
                       "-pix_fmt", "yuv420p", "-movflags", "+faststart", base + ".mp4"],
                       stdin=subprocess.DEVNULL, capture_output=True, text=True)
    if r.returncode:
        sys.stderr.write(r.stderr[-2000:]); raise SystemExit("statcard: preview encode failed")
    print("preview", base + ".mp4")
    if a.ae:
        print("after effects", ae_export(sc, base + ".jsx", fps, a.dur))
    print("DONE", base)
    return 0


if __name__ == "__main__":
    sys.exit(main())
