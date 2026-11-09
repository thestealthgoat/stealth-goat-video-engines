#!/usr/bin/env python3
"""beforeafter.py - T6 before / after showcase: one frame, a divider that sweeps across to show the change.

beforeafter.py --before A --after B --out DIR [--name N] [--a0 S] [--b0 S] [--dur S] [--labels "BEFORE|AFTER"]
               [--fps 29.97] [--size 1920x1080] [--frames t1,t2] [--profile P]

A and B are videos (or stills) of the same framing: a raw clip and its grade, a plate and its matte, a cut before and
after the edit pack. --a0 / --b0 are their in-points. The divider (a thin line in the accent colour with a round
handle) sweeps in from the left edge on a spring, holds at the middle, scrubs back toward BEFORE and across to AFTER
(two smooth moves, so the eye compares the same spot), then clears to show AFTER whole. Each side carries its label,
clipped to its own side. Sound: B's sound (when it has any), levelled to the profile's loudness. Outputs
<name>_ba.mp4. Every move is a spring (spring.py); the labels' opacity never overshoots.
"""
import argparse, json, os, subprocess, sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import vprofile as prof  # noqa: E402
from spring import clamp01, progress  # noqa: E402


def frames(src, t0, dur, size, fps):
    w, h = size
    still = os.path.splitext(src)[1].lower() in (".png", ".jpg", ".jpeg", ".tif", ".tiff")
    cmd = ["ffmpeg", "-nostdin", "-v", "error"] + (["-loop", "1"] if still else ["-ss", f"{max(0, t0 - 1):.3f}"]) + ["-i", src] + \
          ([] if still else ["-ss", f"{min(1.0, t0):.3f}"]) + ["-t", f"{dur:.3f}", "-vf",
          f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1,fps={fps}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True, stdin=subprocess.DEVNULL).stdout
    n = len(raw) // (w * h * 3)
    return np.frombuffer(raw[: n * w * h * 3], np.uint8).reshape(n, h, w, 3)


def divider_x(t, dur):
    """divider position as a share of the width: left of it is BEFORE, right of it is AFTER (1 = all BEFORE, 0 = all AFTER)"""
    x = 1.0 - 0.5 * progress(t, start=0.15, preset="snappy")          # sweeps in from the right edge to the middle (AFTER slides in)
    clear = dur - 1.3
    # a scrub pair plays only when its return move starts by the time the clear starts: a shorter --dur drops the
    # scrubs (right first) instead of letting a late scrub pull the divider back out after the clear
    if 2.5 <= clear:
        x += -0.22 * progress(t, start=1.6, preset="smooth") + 0.22 * progress(t, start=2.5, preset="smooth")   # scrub left...
    if 4.3 <= clear:
        x += 0.24 * progress(t, start=3.4, preset="smooth") - 0.24 * progress(t, start=4.3, preset="smooth")    # ...and right
    x -= 0.5 * progress(t, start=clear, preset="smooth")               # clears to show AFTER whole
    return x


def main(argv=None):
    ap = argparse.ArgumentParser(description="before / after showcase")
    ap.add_argument("--before", required=True); ap.add_argument("--after", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--name", default="showcase"); ap.add_argument("--a0", type=float, default=0.0); ap.add_argument("--b0", type=float, default=0.0)
    ap.add_argument("--dur", type=float, default=6.5); ap.add_argument("--labels", default="BEFORE|AFTER")
    ap.add_argument("--fps", type=float, default=29.97); ap.add_argument("--size", default="1920x1080"); ap.add_argument("--frames")
    prof.add_arg(ap)
    a = ap.parse_args(argv)
    P = prof.load(a.profile); W, H = (int(v) for v in a.size.split("x")); s = min(W, H) / 1080
    A = frames(a.before, a.a0, a.dur, (W, H), a.fps); B = frames(a.after, a.b0, a.dur, (W, H), a.fps)
    acc = P.rgb("accent"); txt = P.rgb("text") if "text" in P.get("brand.colors") else (255, 255, 255)
    fonts = P.get("brand.fonts"); f = ImageFont.truetype(P.font("body_semibold" if "body_semibold" in fonts else "body"), int(30 * s))
    lb, la = a.labels.split("|"); safe = int(P.get("layout.safe_px", 90) * s)
    def pill(text):
        tw = f.getlength(text); im = Image.new("RGBA", (int(tw + 44 * s), int(58 * s)), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
        d.rounded_rectangle((0, 0, im.width - 1, im.height - 1), radius=im.height / 2, fill=(0, 0, 0, 150))
        d.text((22 * s, im.height / 2), text, font=f, fill=txt + (255,), anchor="lm"); return im
    PB, PA = pill(lb), pill(la)
    os.makedirs(a.out, exist_ok=True); base = os.path.join(a.out, f"{a.name}_ba")
    def frame(t):
        i = min(len(A) - 1, int(round(t * a.fps))); j = min(len(B) - 1, int(round(t * a.fps)))
        x = int(round(clamp01(divider_x(t, a.dur)) * W))
        im = B[j].copy(); im[:, :x] = A[i][:, :x]
        img = Image.fromarray(im).convert("RGBA"); d = ImageDraw.Draw(img)
        lab_a = clamp01(progress(t, start=0.3, preset="smooth")) * (1 - clamp01(progress(t, start=a.dur - 1.1, preset="uiExit")))
        for p_, px, side in ((PB, safe, "L"), (PA, W - safe - PA.width, "R")):
            lay = Image.new("RGBA", img.size, (0, 0, 0, 0)); q = p_.copy(); q.putalpha(q.getchannel("A").point(lambda v: int(v * lab_a)))
            lay.alpha_composite(q, (px, safe)); m = np.asarray(lay).copy()
            if side == "L": m[:, x:, 3] = 0
            else: m[:, :x, 3] = 0
            img.alpha_composite(Image.fromarray(m))
        if 0 < x < W:
            lw = max(2, int(4 * s)); d.rectangle((x - lw // 2, 0, x + lw // 2, H), fill=acc + (255,))
            r = int(30 * s); d.ellipse((x - r, H // 2 - r, x + r, H // 2 + r), fill=acc + (255,))
            for k in (-1, 1):                                   # the handle's arrows
                cx = x + k * r * 0.45; d.polygon([(cx + k * r * 0.25, H // 2), (cx - k * r * 0.1, H // 2 - r * 0.3), (cx - k * r * 0.1, H // 2 + r * 0.3)], fill=txt + (255,))
        return img.convert("RGB")
    if a.frames:
        for t in (float(v) for v in a.frames.split(",")):
            frame(t).save(f"{base}_t{t:.2f}.jpg", quality=92); print("still", f"{base}_t{t:.2f}.jpg")
        return 0
    has_audio = bool(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", a.after],
                                    capture_output=True, text=True).stdout.strip())
    lufs, tp = P.get("delivery.loudness_lufs", -14), P.get("delivery.true_peak_db", -2)
    fr = "30000/1001" if abs(a.fps - 30000 / 1001) < 0.01 else f"{a.fps:g}"
    aud = (["-i", a.after, "-filter_complex", f"[1:a]atrim=start={a.b0:.4f}:duration={a.dur:.4f},asetpts=PTS-STARTPTS,aresample=48000,"
            f"aformat=channel_layouts=stereo,afade=t=in:d=0.05,afade=t=out:st={a.dur - 0.6:.3f}:d=0.6,loudnorm=I={lufs}:TP={tp - 1}:LRA=11,aresample=48000[a]",
            "-map", "0:v", "-map", "[a]", "-c:a", "aac", "-b:a", "192k"] if has_audio else [])
    enc = subprocess.Popen(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-framerate", fr,
                            "-i", "pipe:0", *aud, "-c:v", "libx264", "-crf", "17", "-preset", "medium", "-pix_fmt", "yuv420p", "-threads", "4",
                            "-t", f"{a.dur:.3f}", "-movflags", "+faststart", base + ".mp4"], stdin=subprocess.PIPE)
    for k in range(int(round(a.dur * a.fps))):
        enc.stdin.write(frame(k / a.fps).tobytes())
    enc.stdin.close()
    if enc.wait(): raise SystemExit("beforeafter: encode failed")
    print(f"before/after: {a.dur:.2f} s -> {base}.mp4 (qa: --kind motion --cuts none)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
