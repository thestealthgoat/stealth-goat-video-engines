#!/usr/bin/env python3
"""sketch.py - T5 sketch -> real shot: a pencil drawing of the first frame draws itself, shades in, then the real
footage paints in through it and plays on. OpenCV only (edges + a dodge-blend pencil shade): no AI.

sketch.py <video|still> --out DIR [--name N] [--t0 S] [--dur S] [--draw S] [--fps 29.97] [--size 1920x1080]
          [--frames t1,t2] [--profile P]

Order of events (spring.py; --draw sets the drawing time, default 2.2 s):
  1. lines: the image's edges (Canny on a bilateral-smoothed frame) are drawn stroke by stroke, longest strokes
     first, each stroke growing along its own length from one end (a pen, not a fade);
  2. shading: the pencil shade (grey / inverted-blur dodge) settles in under the lines;
  3. the real shot paints in through a soft brush that sweeps from the action outward (the brightest motion of the
     first second) while the footage starts to play; the paper colour is the profile's text colour (warm white) and
     the lines its primary ink.
Outputs <name>_sketch.mp4 with the source's sound from where the footage starts to play (levelled).
"""
import argparse, os, subprocess, sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import vprofile as prof  # noqa: E402
from spring import clamp01, progress  # noqa: E402


def read(src, t0, dur, size, fps):
    w, h = size
    still = os.path.splitext(src)[1].lower() in (".png", ".jpg", ".jpeg")
    cmd = ["ffmpeg", "-nostdin", "-v", "error"] + (["-loop", "1"] if still else ["-ss", f"{max(0, t0 - 1):.3f}"]) + ["-i", src] + \
          ([] if still else ["-ss", f"{min(1.0, t0):.3f}"]) + ["-t", f"{dur:.3f}", "-vf",
          f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1,fps={fps}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True, stdin=subprocess.DEVNULL).stdout
    n = len(raw) // (w * h * 3)
    return np.frombuffer(raw[: n * w * h * 3], np.uint8).reshape(n, h, w, 3)


def strokes(img):
    """edge strokes, longest first: each a list of pixel coords ordered along the stroke"""
    import cv2
    g = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY); g = cv2.bilateralFilter(g, 9, 60, 9)
    e = cv2.Canny(g, 60, 150)
    e = cv2.dilate(e, np.ones((2, 2), np.uint8))
    cs, _ = cv2.findContours(e, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    cs = [c[:, 0, :] for c in cs if len(c) > 24]
    cs.sort(key=len, reverse=True)
    return cs


def main(argv=None):
    import cv2
    ap = argparse.ArgumentParser(description="sketch -> real shot")
    ap.add_argument("src"); ap.add_argument("--out", required=True); ap.add_argument("--name", default="sketch")
    ap.add_argument("--t0", type=float, default=0.0); ap.add_argument("--dur", type=float, default=6.0)
    ap.add_argument("--draw", type=float, default=2.2); ap.add_argument("--fps", type=float, default=29.97)
    ap.add_argument("--size", default="1920x1080"); ap.add_argument("--frames"); prof.add_arg(ap)
    a = ap.parse_args(argv)
    P = prof.load(a.profile); W, H = (int(v) for v in a.size.split("x"))
    # the shading lands at 60% of the draw; the brush starts 0.3 s later (the strong moment, before 2 s) and the footage
    # plays from that same instant, so it comes to life as it paints in (no held frame between the brush and the play)
    T_SHADE = a.draw * 0.6; T_BRUSH = T_SHADE + 0.3; T_REAL = T_BRUSH
    hold = T_REAL                                  # the footage is held on its first frame until it starts to play
    play = max(0.0, a.dur - hold)                  # seconds of footage that actually play (0: a sketch-only bumper)
    F = read(a.src, a.t0, play + 0.2, (W, H), a.fps)   # always at least 0.2 s, so the first frame exists
    if not len(F):
        ap.error(f"no frames read from {a.src} at --t0 {a.t0:g} (past the end of the clip?)")
    first = F[0]
    paper = np.array(P.rgb("text") if "text" in P.get("brand.colors") else (246, 242, 232), np.float32)
    ink = np.array([int(v * 0.35) for v in P.rgb("primary")], np.float32)
    # pencil shade: dodge blend of the grey frame with its inverted blur, softened to paper
    g = cv2.cvtColor(first, cv2.COLOR_RGB2GRAY).astype(np.float32)
    blur = cv2.GaussianBlur(255 - g, (0, 0), 12)
    shade = np.clip(g * 255 / np.maximum(1, 255 - blur), 0, 255) / 255.0          # 1 = paper, 0 = dark
    shade = 0.55 + 0.45 * shade
    cs = strokes(first)
    total = sum(len(c) for c in cs); cum = np.cumsum([0] + [len(c) for c in cs])
    # the action: where the first second moves most (the brush starts there)
    if len(F) > 8:
        d = np.abs(F[min(len(F) - 1, int(a.fps))].astype(np.int16) - F[0].astype(np.int16)).mean(2)
        d = cv2.GaussianBlur(d.astype(np.float32), (0, 0), 25); cy, cx = np.unravel_index(int(d.argmax()), d.shape)
    else:
        cy, cx = H // 2, W // 2
    yy, xx = np.mgrid[0:H, 0:W]; dist = np.hypot(xx - cx, yy - cy) / np.hypot(W, H)
    noise = cv2.GaussianBlur(np.random.default_rng(7).random((H // 8, W // 8)).astype(np.float32), (0, 0), 2)
    noise = cv2.resize(noise, (W, H)); noise = (noise - noise.min()) / (noise.max() - noise.min() + 1e-6)
    brush_key = dist + 0.12 * noise                  # paint order: from the action outward, with a ragged brush edge
    lw = max(1, int(round(2.2 * H / 1080)))
    def frame(t):
        # 1. lines drawn up to share p of the total stroke length (a spring over --draw seconds, launched)
        p = clamp01(progress(t, start=0.05, zeta=1.0, omega=4.6 / a.draw, v0=1.0))
        drawn = p * total
        canvas = np.ones((H, W), np.float32)
        sh = clamp01(progress(t, start=T_SHADE, zeta=1.0, omega=16.0))          # the shading lands as one moment (~0.35 s)
        canvas = canvas * (1 - sh) + shade * sh
        lines = np.zeros((H, W), np.uint8)
        for k, c in enumerate(cs):
            if cum[k] >= drawn: break
            m = int(min(len(c), drawn - cum[k]))
            if m > 1: cv2.polylines(lines, [c[:m].reshape(-1, 1, 2)], False, 255, lw, cv2.LINE_AA)
        L = lines.astype(np.float32)[..., None] / 255.0
        sketch = paper[None, None, :] * canvas[..., None]
        sketch = sketch * (1 - L * 0.9) + ink[None, None, :] * (L * 0.9)
        # 2. the real shot paints in through the brush, starting where the action is; footage plays from T_REAL
        r = clamp01(progress(t, start=T_BRUSH, zeta=1.0, omega=6.5))            # the brush starts right after the shading (~1.1 s sweep)
        q = r * 1.25
        m = np.clip((q - brush_key) / 0.08, 0, 1)[..., None] if r > 0 else 0
        fi = 0 if t < T_REAL else min(len(F) - 1, int(round((t - T_REAL) * a.fps)))
        out = sketch * (1 - m) + F[fi].astype(np.float32) * m
        return np.clip(out, 0, 255).astype(np.uint8)
    os.makedirs(a.out, exist_ok=True); base = os.path.join(a.out, f"{a.name}_sketch")
    if a.frames:
        from PIL import Image
        for t in (float(v) for v in a.frames.split(",")):
            Image.fromarray(frame(t)).save(f"{base}_t{t:.2f}.jpg", quality=92); print("still", f"{base}_t{t:.2f}.jpg")
        return 0
    lufs, tp = P.get("delivery.loudness_lufs", -14), P.get("delivery.true_peak_db", -2)
    fr = "30000/1001" if abs(a.fps - 30000 / 1001) < 0.01 else f"{a.fps:g}"
    has_audio = play > 0.05 and os.path.splitext(a.src)[1].lower() not in (".png", ".jpg", ".jpeg") and bool(subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", a.src], capture_output=True, text=True).stdout.strip())
    aud = (["-i", a.src, "-filter_complex", f"[1:a]atrim=start={a.t0:.4f}:duration={play:.4f},asetpts=PTS-STARTPTS,aresample=48000,"
            f"aformat=channel_layouts=stereo,afade=t=in:d=0.4,adelay={int(hold * 1000)}|{int(hold * 1000)},apad,"
            f"afade=t=out:st={a.dur - 0.6:.3f}:d=0.6,loudnorm=I={lufs}:TP={tp - 1}:LRA=11,aresample=48000[a]",
            "-map", "0:v", "-map", "[a]", "-c:a", "aac", "-b:a", "192k"] if has_audio else [])
    enc = subprocess.Popen(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-framerate", fr,
                            "-i", "pipe:0", *aud, "-c:v", "libx264", "-crf", "17", "-preset", "medium", "-pix_fmt", "yuv420p", "-threads", "4",
                            "-t", f"{a.dur:.3f}", "-movflags", "+faststart", base + ".mp4"], stdin=subprocess.PIPE)
    for k in range(int(round(a.dur * a.fps))):
        enc.stdin.write(frame(k / a.fps).tobytes())
    enc.stdin.close()
    if enc.wait(): raise SystemExit("sketch: encode failed")
    print(f"sketch: {a.dur:.2f} s, {len(cs)} strokes; the real shot from {T_REAL:.2f} s -> {base}.mp4 (qa: --kind motion --cuts none)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
