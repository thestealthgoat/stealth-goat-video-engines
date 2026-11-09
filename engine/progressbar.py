#!/usr/bin/env python3
"""progressbar.py - O5 progress bar with a face marker: a thin bar along the bottom of a talk / podcast / sermon that
fills as the video plays, with the speaker's face riding the head of the fill; chapter ticks, and each chapter's title
pops up over the face as it is reached.

progressbar.py <video> --out DIR [--name N] [--t0 S] [--t1 S] (--face face.png | --matte <name>.json from matte.py)
               [--chapters chapters.json] [--fps N] [--frames t1,t2] [--profile P]

--face: any image with the face (a headshot, a player cutout); it is cropped to a circle around its alpha / centre.
--matte: the O2 matte json (engine/matte.py): the face is cut from the person's first matte frame (the head found
          the same way behind.py finds it).
--chapters: [{"t": 0, "title": "Welcome"}, {"t": 95.5, "title": "The story"}, ...] in seconds of the video.
Outputs <name>_progress_Alpha.mov (ProRes 4444, full frame, for Premiere / vMix over the programme) and
<name>_progress.mp4 (the bar over the video window, with its sound, for a look). The fill is the real clock (it moves
at a constant rate: it is the position in the video); every other move is a spring (the bar rises in, the marker
pops at each chapter, titles spring in and out on smooth / uiExit; opacity never overshoots).
Brand from the profile: accent (fill, ring), text (titles), primary (track), fonts head / body_semibold, safe area.
"""
import argparse, json, os, subprocess, sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import vprofile as prof  # noqa: E402
from spring import clamp01, progress  # noqa: E402


def kick(t, t0, v0, preset="snappy"):
    if t < t0:
        return 0.0
    return progress(t, start=t0, preset=preset, v0=v0) - progress(t, start=t0, preset=preset)


def probe(path):
    """Display size (a phone clip's 90/-90 rotation flag applied, as ffmpeg auto-rotates on decode), rate, duration."""
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height,r_frame_rate:stream_side_data=rotation:stream_tags=rotate:format=duration",
                          "-of", "json", path], capture_output=True, text=True, stdin=subprocess.DEVNULL, check=True).stdout
    d = json.loads(out); s = d["streams"][0]; a, b = s["r_frame_rate"].split("/")
    rot = 0
    for sd in s.get("side_data_list", []):
        if "rotation" in sd:
            rot = int(float(sd["rotation"]))
    rot = rot or int(float((s.get("tags") or {}).get("rotate", 0)))
    w, h = int(s["width"]), int(s["height"])
    if abs(rot) % 180 == 90:
        w, h = h, w
    return w, h, float(a) / float(b), float(d["format"]["duration"])


def has_audio(path):
    return bool(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", path],
                               capture_output=True, text=True, stdin=subprocess.DEVNULL).stdout.strip())


def face_from_image(path, size):
    im = Image.open(path).convert("RGBA")
    a = np.asarray(im)[..., 3]
    if a.min() < 250:                                   # a cutout: the head = the top of the alpha
        ys, xs = np.nonzero(a > 128); top = ys.min(); h = ys.max() - top
        band = a[top:top + max(8, int(0.25 * h))] > 128
        cx = int(np.nonzero(band.any(0))[0].mean()); side = int(min(im.width, 0.42 * h))
        box = (cx - side // 2, top - side // 12, cx + side // 2, top - side // 12 + side)
    else:
        side = min(im.size); box = ((im.width - side) // 2, 0, (im.width + side) // 2, side)
    return circle(im.crop(box), size)


def face_from_matte(mjson, size):
    mj = json.load(open(mjson)); mov = mjson[:-5] + "_Alpha.mov"
    w, h = mj["size"]
    raw = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", mov, "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgba", "-"],
                         capture_output=True, check=True).stdout
    fr = np.frombuffer(raw, np.uint8).reshape(h, w, 4)
    a = fr[..., 3] > 128
    rows = np.nonzero(a.mean(1) > 0.01)[0]
    top = rows.min() if len(rows) else 0
    band = a[top:top + int(0.12 * h)]
    cx = int(np.nonzero(band.any(0))[0].mean()) if band.any() else w // 2
    side = int(0.30 * h)
    # the face from the real picture (not the cut-out edge, and not the matte's colour-decontaminated RGB, which is
    # black / smeared skin off the person): the source frame at the matte's t0, turned and scaled the way matte.py read it
    src = None
    if mj.get("video") and os.path.exists(mj["video"]):
        turn = {"cw": "transpose=1,", "ccw": "transpose=2,", "180": "hflip,vflip,"}.get(mj.get("rotate"), "")
        r = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-ss", f"{float(mj.get('t0', 0.0)):.3f}", "-i", mj["video"], "-frames:v", "1",
                            "-vf", f"{turn}scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True)
        if r.returncode == 0 and len(r.stdout) >= w * h * 3:
            src = np.frombuffer(r.stdout[:w * h * 3], np.uint8).reshape(h, w, 3)
    if src is None:
        print("progressbar: source video for the matte not readable; face taken from the matte RGB", file=sys.stderr)
        src = fr[..., :3]
    im = Image.fromarray(src.copy()).convert("RGBA")
    return circle(im.crop((cx - side // 2, max(0, top - side // 10), cx + side // 2, max(0, top - side // 10) + side)), size)


def circle(im, size):
    im = im.resize((size, size), Image.LANCZOS)
    m = Image.new("L", (size * 4, size * 4), 0); ImageDraw.Draw(m).ellipse((0, 0, size * 4 - 1, size * 4 - 1), fill=255)
    m = m.resize((size, size), Image.LANCZOS)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0)); out.paste(im, (0, 0), m)
    return out


class Bar:
    def __init__(self, P, W, H, dur, face, chapters):
        self.P, self.W, self.H, self.dur = P, W, H, dur
        s = min(W, H) / 1080.0; self.s = s                 # short side: a portrait frame is not laid out at 1.8x
        safe = int(P.get("layout.safe_px", 90) * s)
        self.x0, self.x1 = safe, W - safe
        self.y = H - int(0.55 * safe) - int(14 * s)
        self.th = max(4, int(8 * s)); self.r = int(46 * s)
        self.acc, self.txt = P.rgb("accent"), (P.rgb("text") if "text" in P.get("brand.colors") else (255, 255, 255))
        self.track = tuple(int(v * 0.55) for v in P.rgb("primary"))
        self.face = face.resize((2 * self.r - int(8 * s),) * 2, Image.LANCZOS) if face is not None else None
        fonts = P.get("brand.fonts")
        self.ft = ImageFont.truetype(P.font("head"), int(40 * s))
        self.fs = ImageFont.truetype(P.font("body_semibold" if "body_semibold" in fonts else "body"), int(22 * s))
        self.ch = [c for c in chapters if 0 <= c["t"] < dur]
        self.caps = bool((P.get("explain", {}) or {}).get("head_caps"))

    def frame(self, t):
        s, W, H = self.s, self.W, self.H
        im = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
        rise = progress(t, start=0.0, preset="snappy"); a_in = clamp01(progress(t, start=0.0, preset="smooth"))
        a_out = 1 - clamp01(progress(t, start=self.dur - 0.45, preset="uiExit")) if t > self.dur - 0.45 else 1.0
        A = a_in * a_out
        if A <= 0.003:
            return im
        dy = (1 - rise) * 60 * s
        y = self.y + dy; p = clamp01(t / self.dur)
        xh = self.x0 + p * (self.x1 - self.x0)
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0)); dl = ImageDraw.Draw(layer)
        dl.rounded_rectangle((self.x0, y - self.th / 2, self.x1, y + self.th / 2), radius=self.th / 2, fill=self.track + (200,))
        dl.rounded_rectangle((self.x0, y - self.th / 2, max(self.x0 + self.th, xh), y + self.th / 2), radius=self.th / 2, fill=self.acc + (255,))
        for c in self.ch[1:]:                                       # chapter ticks
            xc = self.x0 + (c["t"] / self.dur) * (self.x1 - self.x0)
            passed = t >= c["t"]
            dl.rounded_rectangle((xc - 2 * s, y - 12 * s, xc + 2 * s, y + 12 * s), radius=2 * s, fill=(self.txt if passed else self.track) + (255,))
        # the face marker: rides the head of the fill; pops (snappy kick) at each chapter it reaches
        k = 1.0 + sum(0.22 * kick(t, c["t"], 5.0) for c in self.ch[1:])
        R = self.r * k
        glow = Image.new("RGBA", (W, H), (0, 0, 0, 0)); ImageDraw.Draw(glow).ellipse((xh - R * 1.3, y - R * 1.3, xh + R * 1.3, y + R * 1.3), fill=self.acc + (90,))
        layer.alpha_composite(glow.filter(ImageFilter.GaussianBlur(10 * s)))
        dl = ImageDraw.Draw(layer)
        dl.ellipse((xh - R, y - R, xh + R, y + R), fill=self.acc + (255,))
        if self.face is not None:
            f = self.face.resize((max(2, int(self.face.width * k)),) * 2, Image.LANCZOS)
            layer.alpha_composite(f, (int(round(xh - f.width / 2)), int(round(y - f.height / 2))))
        # chapter title: springs in above the marker when its chapter starts, holds 2.6 s, leaves on uiExit
        cur = [c for c in self.ch if t >= c["t"]]
        if cur and cur[-1]["title"]:                                # the untitled start (no chapter yet) has no card
            c = cur[-1]; age = t - c["t"]
            if age < 3.2:
                aT = clamp01(progress(t, start=c["t"] + 0.05, preset="smooth")) * (1 - (clamp01(progress(t, start=c["t"] + 2.6, preset="uiExit")) if age > 2.6 else 0))
                ry = (1 - progress(t, start=c["t"] + 0.05, preset="snappy")) * 24 * s
                title = c["title"].upper() if self.caps else c["title"]
                tw = self.ft.getlength(title); lab = f"CHAPTER {c.get('n', self.ch.index(c) + 1)}"
                lw = self.fs.getlength(lab)
                bw = max(tw, lw) + 40 * s; bh = 96 * s
                bx = min(max(self.x0, xh - bw / 2), self.x1 - bw); by = y - R - 22 * s - bh + ry
                card = Image.new("RGBA", (W, H), (0, 0, 0, 0)); dc = ImageDraw.Draw(card)
                dc.rounded_rectangle((bx, by, bx + bw, by + bh), radius=14 * s, fill=(0, 0, 0, 165))
                dc.text((bx + 20 * s, by + 30 * s), lab, font=self.fs, fill=self.acc + (255,), anchor="ls")
                dc.text((bx + 20 * s, by + 76 * s), title, font=self.ft, fill=self.txt + (255,), anchor="ls")
                ca = np.asarray(card).copy(); ca[..., 3] = (ca[..., 3] * aT).astype(np.uint8)
                layer.alpha_composite(Image.fromarray(ca))
        la = np.asarray(layer).copy(); la[..., 3] = (la[..., 3] * A).astype(np.uint8)
        im.alpha_composite(Image.fromarray(la))
        return im


def main(argv=None):
    ap = argparse.ArgumentParser(description="progress bar with a face marker")
    ap.add_argument("video"); ap.add_argument("--out", required=True); ap.add_argument("--name")
    ap.add_argument("--t0", type=float, default=0.0); ap.add_argument("--t1", type=float)
    g = ap.add_mutually_exclusive_group(required=True); g.add_argument("--face"); g.add_argument("--matte")
    ap.add_argument("--chapters"); ap.add_argument("--fps", type=float); ap.add_argument("--frames")
    prof.add_arg(ap)
    a = ap.parse_args(argv)
    P = prof.load(a.profile)
    W, H, vfps, vdur = probe(a.video)
    t1 = a.t1 if a.t1 is not None else vdur
    dur = t1 - a.t0; fps = a.fps or vfps
    os.makedirs(a.out, exist_ok=True)
    name = a.name or os.path.splitext(os.path.basename(a.video))[0]
    face = face_from_image(a.face, 256) if a.face else face_from_matte(a.matte, 256)
    # each chapter keeps its number in the whole video; the one already running at --t0 is carried to 0 (named at the
    # start); with none running, an untitled start sits at 0 (no card, no tick) so the ticks / kicks skip the start
    src = sorted(json.load(open(a.chapters)), key=lambda c: c["t"]) if a.chapters else []
    ch = [{"t": c["t"] - a.t0, "title": c.get("title", ""), "n": i + 1} for i, c in enumerate(src)]
    pre = [c for c in ch if c["t"] <= 0.01]
    chapters = [dict(pre[-1], t=0.0) if pre else {"t": 0.0, "title": "", "n": 0}] + [c for c in ch if c["t"] > 0.01]
    bar = Bar(P, W, H, dur, face, chapters)
    base = os.path.join(a.out, f"{name}_progress")
    if a.frames:
        for t in (float(x) for x in a.frames.split(",")):
            raw = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-ss", f"{a.t0 + t:.3f}", "-i", a.video, "-frames:v", "1", "-f", "rawvideo",
                                  "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
            bg = Image.frombytes("RGB", (W, H), raw).convert("RGBA"); bg.alpha_composite(bar.frame(t))
            bg.convert("RGB").save(f"{base}_t{t:.2f}.jpg", quality=92); print("still", f"{base}_t{t:.2f}.jpg")
        return 0
    fr = "30000/1001" if abs(fps - 30000 / 1001) < 0.01 else ("60000/1001" if abs(fps - 60000 / 1001) < 0.01 else f"{fps:g}")
    n = int(round(dur * fps))
    enc = subprocess.Popen(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{H}", "-framerate", fr,
                            "-i", "pipe:0", "-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le", "-alpha_bits", "16",
                            "-threads", "4", base + "_Alpha.mov"], stdin=subprocess.PIPE)
    for i in range(n):
        enc.stdin.write(bar.frame(i / fps).tobytes())
    enc.stdin.close()
    if enc.wait(): raise SystemExit("progressbar: encode failed")
    lufs, tp = P.get("delivery.loudness_lufs", -14), P.get("delivery.true_peak_db", -2)
    noise = f"anoisesrc=color=pink:amplitude=0.008:sample_rate=48000:duration={dur:.4f},aformat=channel_layouts=stereo"
    if has_audio(a.video):
        ins = ["-i", a.video]
        aud = (f"[2:a]atrim=start={a.t0:.4f}:duration={dur:.4f},asetpts=PTS-STARTPTS,"
               f"aresample=48000,aformat=channel_layouts=stereo,loudnorm=I={lufs}:TP={tp - 1}:LRA=11,aresample=48000[va];"
               f"{noise}[n];[va][n]amix=inputs=2:duration=first:normalize=0[aud]")
    else:                                                           # a silent source (screen recording, B-roll): room tone only
        ins = []
        aud = f"{noise}[aud]"
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-ss", f"{a.t0:.3f}", "-t", f"{dur:.3f}", "-i", a.video, "-i", base + "_Alpha.mov",
                    *ins, "-filter_complex", f"[0:v][1:v]overlay=0:0:shortest=1,format=yuv420p[v];{aud}",
                    "-map", "[v]", "-map", "[aud]", "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-threads", "4", "-c:a", "aac",
                    "-b:a", "192k", "-t", f"{dur:.3f}", "-movflags", "+faststart", base + ".mp4"], check=True, stdin=subprocess.DEVNULL)
    print(f"progress bar: {dur:.1f} s, {len(chapters)} chapters -> {base}_Alpha.mov, {base}.mp4 (qa: --cuts none)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
