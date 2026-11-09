#!/usr/bin/env python3
"""matte.py - O2 person matte from video: a per-frame cutout of the people in a shot, smoothed at the edges and steady
from frame to frame, with an alpha output for compositing (text behind the person, cards behind or in front).

matte.py <video> --out <dir> [--name N] [--t0 S] [--t1 S] [--model birefnet-general|birefnet-portrait|modnet|u2net_human_seg] [--infer 512]
         [--steady 0.85] [--choke 0] [--feather 1.0] [--bg '#hex'|image|blur|none] [--max-height 1080]
         [--rotate cw|ccw|180] [--frames 1.0,2.5] [--profile P]

Models (free, local; nothing is uploaded):
  birefnet-general   (default) BiRefNet (MIT, ZhengPeng7/BiRefNet; ONNX via rembg): the most complete people: helmets,
                     dark jerseys against a night field, hands and feet (2026-11-09 test on 8 game photos + 5 football
                     ISO frames: missing body 1.0/10 against MODNet 5.2, background 1.4 vs 2.8, edges 1.5 vs 5.7).
                     Keeps the main subject(s) and drops bystanders. ~5-6 s a 1080p frame on this Mac's CPU, so a 5 s
                     clip at 60 fps is about half an hour: render it in the background.
  birefnet-portrait  BiRefNet portrait weights: as complete, but keeps everyone in the shot (bystanders too).
  modnet             MODNet photographic portrait matting (Apache-2.0, ZHKKKe/MODNet; ONNX export Xenova/modnet),
                     resources/models/modnet_photographic_portrait_matting.onnx. Soft hair-level alpha; best on one to
                     a few people at mid/close range. Fast (0.15 s a frame): drafts only; it loses dark helmets
                     and jerseys at night.
  u2net_human_seg    rembg's U^2-Net human segmentation (Apache-2.0); harder edges, better on small far figures
                     (sports wides).
rembg models live in $U2NET_HOME, else local.json "rembg_models" (e.g. a shared drive), else resources/models/rembg,
else rembg's default folder (engine/models.py); rembg downloads a missing one on first use.
Per frame: the model runs at --infer px on the short side; the alpha is upsampled and refined against the picture
with a guided filter (edges follow the real outline, hair keeps its softness); then it is held steady: where the
picture itself didn't change since the last frame, the last alpha wins by --steady, where it changed (something
moved) the new alpha wins, so edges stop shimmering without lagging behind a moving arm. Islands smaller than --min-region (15%) of the largest region are dropped (a cymbal,
a lamp), so a second person stays. --choke px erodes, --feather px softens the final edge.

Outputs in --out:
  <name>_matte_Alpha.mov   ProRes 4444: the person with alpha (full frame, original colours; edge colour from the person, not the old background)
  <name>_matte.mp4         the alpha as greyscale (white = person), for any compositor
  <name>_matte_preview.mp4 the cut-out over --bg (default: the profile's primary_deep; blur = the shot itself blurred)
  <name>_matte.json        settings, frame count, and edge flicker: mean / 95th percentile of the alpha's second
                           difference in time in the edge band (smooth motion ~0, shimmer high). Calibration on a
                           talking head: 0.15 raw per frame, 0.04 at --steady 0.75, 0.02 at 0.9; under ~0.05
                           reads as solid on screen
--frames writes stills only (<name>_matte_t<t>.png RGBA + a preview strip) for a quick look.
"""
import argparse, json, os, subprocess, sys, time

import numpy as np
import cv2

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import vprofile as prof          # noqa: E402

MODNET = os.path.join(REPO, "resources", "models", "modnet_photographic_portrait_matting.onnx")


def probe(path):
    """Display size (rotation applied: phone clips carry a -90/90 flag and ffmpeg auto-rotates when decoding), rate,
    duration."""
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height,r_frame_rate:stream_side_data=rotation:stream_tags=rotate:format=duration",
                          "-of", "json", path], capture_output=True, text=True, stdin=subprocess.DEVNULL, check=True).stdout
    j = json.loads(out); s = j["streams"][0]
    n, d = (int(x) for x in s["r_frame_rate"].split("/"))
    rot = 0
    for sd in s.get("side_data_list", []):
        if "rotation" in sd:
            rot = int(float(sd["rotation"]))
    rot = rot or int(float((s.get("tags") or {}).get("rotate", 0)))
    w, h = int(s["width"]), int(s["height"])
    if abs(rot) % 180 == 90:
        w, h = h, w
    return w, h, n, d, float(j["format"]["duration"])


import models                    # noqa: E402
models.rembg_home()              # where the BiRefNet / U^2-Net files live ($U2NET_HOME, local.json "rembg_models", ...)


class Model:
    def __init__(self, name, infer):
        self.name, self.infer = name, infer
        if name == "modnet":
            import onnxruntime as ort
            if not os.path.isfile(MODNET):
                sys.exit(f"matte: model missing: {MODNET} (see the docstring for where it comes from)")
            self.sess = ort.InferenceSession(MODNET, providers=["CPUExecutionProvider"])
        else:
            from rembg import new_session
            self.sess = new_session(name)

    def __call__(self, rgb):
        h, w = rgb.shape[:2]
        if self.name == "modnet":
            k = self.infer / min(h, w)
            ih, iw = max(32, int(round(h * k / 32)) * 32), max(32, int(round(w * k / 32)) * 32)
            x = cv2.resize(rgb, (iw, ih), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0
            x = ((x - 0.5) / 0.5).transpose(2, 0, 1)[None]
            a = self.sess.run(None, {"input": x})[0][0, 0]
            return cv2.resize(a, (w, h), interpolation=cv2.INTER_LINEAR).clip(0, 1)
        from rembg import remove
        from PIL import Image
        m = remove(Image.fromarray(rgb), session=self.sess, only_mask=True)
        return np.asarray(m, dtype=np.float32) / 255.0


def guided(I, p, r, eps):
    """He et al. guided filter (grey guide), box filters via OpenCV: edges of p snap to edges of I."""
    box = lambda x: cv2.boxFilter(x, -1, (2 * r + 1, 2 * r + 1))
    mI, mp = box(I), box(p)
    a = (box(I * p) - mI * mp) / (box(I * I) - mI * mI + eps)
    b = mp - a * mI
    return box(a) * I + box(b)


class Steady:
    """Temporal hold: where the picture didn't change since the last frame, the alpha shouldn't either. Per pixel, the
    image change (grey levels, lightly blurred) gates a blend: unchanged (< 4 levels) keeps `steady` of the last alpha,
    changed (> 16 levels: something moved) takes the new alpha, linear in between. No optical flow needed, so it can't
    smear a moving arm, and edges on still parts of the frame stop shimmering."""
    def __init__(self, steady, w, h):
        self.k, self.prev, self.prev_g = steady, None, None

    def __call__(self, a, g):
        gb = cv2.GaussianBlur(g, (0, 0), 1.5).astype(np.float32)
        if self.prev is None:
            self.prev, self.prev_g = a, gb
            return a, None
        moved = np.clip((np.abs(gb - self.prev_g) - 4.0) / 12.0, 0, 1)
        hold = self.k * (1 - moved)
        out = hold * self.prev + (1 - hold) * a
        edge = (out > 0.03) & (out < 0.97)
        jitter = float(np.abs(out - self.prev)[edge].mean()) if edge.any() else 0.0
        self.prev, self.prev_g = out, gb
        return out, jitter


def fg_colour(rgb, a):
    """Edge colour without the old background: in the soft edge, the person's own colour nearby (a blur of the frame
    weighted by alpha: normalised convolution), blending to the real pixel as alpha nears 1. Solving
    fg = (rgb - bg (1 - a)) / a instead amplifies any background texture (wall slats, crowds) into specks."""
    w = a.astype(np.float32)
    est = cv2.GaussianBlur(rgb.astype(np.float32) * w[..., None], (0, 0), 6) / \
        np.maximum(cv2.GaussianBlur(w, (0, 0), 6), 1e-3)[..., None]
    k = np.clip((a - 0.55) / 0.4, 0, 1)[..., None]               # 0 below a=0.55, 1 above a=0.95
    k = k * k * (3 - 2 * k)
    return (est * (1 - k) + rgb.astype(np.float32) * k).clip(0, 255).astype(np.uint8)


def drop_islands(a, keep_frac):
    """Keep the regions of the matte that are at least keep_frac of the largest one (people), drop small islands
    (a cymbal, a lamp, specks). The soft edge of each kept region is kept as is."""
    if keep_frac <= 0:
        return a
    m = (a > 0.5).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
    if n <= 2:
        return a
    areas = st[1:, cv2.CC_STAT_AREA]
    keep = np.zeros(n, bool); keep[1:] = areas >= keep_frac * areas.max()
    km = keep[lab].astype(np.uint8)
    km = cv2.dilate(km, np.ones((15, 15), np.uint8))            # include each kept region's soft edge
    return a * km


def make_bg(mode, P, rgb_shape):
    h, w = rgb_shape[:2]
    if mode == "none" or mode == "blur":
        return None
    if mode.startswith("#"):
        c = [int(mode.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)]
        return np.full((h, w, 3), c, np.uint8)
    if os.path.isfile(mode):
        im = cv2.cvtColor(cv2.imread(mode), cv2.COLOR_BGR2RGB)
        return cv2.resize(im, (w, h), interpolation=cv2.INTER_AREA)
    cols = P.get("brand.colors")
    c = P.rgb("primary_deep") if "primary_deep" in cols else P.rgb("primary")
    return np.full((h, w, 3), c, np.uint8)


def main(argv=None):
    ap = argparse.ArgumentParser(description="O2 person matte from video")
    ap.add_argument("video"); ap.add_argument("--out", required=True); ap.add_argument("--name")
    ap.add_argument("--t0", type=float, default=0.0); ap.add_argument("--t1", type=float)
    ap.add_argument("--model", default="birefnet-general", choices=["birefnet-general", "birefnet-portrait", "modnet", "u2net_human_seg"])
    ap.add_argument("--infer", type=int, default=512, help="model input, short side px (modnet)")
    ap.add_argument("--steady", type=float, default=0.85, help="0 = raw per frame, 0.9 = very steady")
    ap.add_argument("--choke", type=float, default=0.0, help="erode the edge by this many px")
    ap.add_argument("--feather", type=float, default=1.0, help="soften the final edge (px)")
    ap.add_argument("--bg", default="profile", help="preview background: profile | '#hex' | image | blur | none")
    ap.add_argument("--max-height", type=int, default=1080)
    ap.add_argument("--min-region", type=float, default=0.15,
                    help="drop matte islands smaller than this share of the largest region (0 = keep everything)")
    ap.add_argument("--rotate", choices=["cw", "ccw", "180"], help="turn the picture first (a phone clip whose rotation "
                    "tag is wrong: people sideways); the model needs people upright")
    ap.add_argument("--frames", help="stills only, at these times (s, relative to --t0)")
    prof.add_arg(ap)
    a = ap.parse_args(argv)
    P = prof.load(a.profile)
    os.makedirs(a.out, exist_ok=True)
    name = a.name or os.path.splitext(os.path.basename(a.video))[0]
    W0, H0, fn, fd, dur = probe(a.video)
    if a.rotate in ("cw", "ccw"):
        W0, H0 = H0, W0
    turn = {"cw": "transpose=1,", "ccw": "transpose=2,", "180": "hflip,vflip,"}.get(a.rotate, "")
    fps = fn / fd
    t1 = min(dur, a.t1) if a.t1 else dur
    scale = min(1.0, a.max_height / min(W0, H0))      # caps the short side: a portrait clip stays 1080 wide
    W, H = int(round(W0 * scale / 2)) * 2, int(round(H0 * scale / 2)) * 2
    model = Model(a.model, a.infer)
    steady = Steady(a.steady, W, H)

    def frames(times=None):
        """rgb frames from the window (decoded once, sequentially)."""
        # video only, so an input-side seek is frame-exact (ffmpeg decodes from the keyframe and drops up to t0)
        cmd = ["ffmpeg", "-nostdin", "-v", "error", "-ss", f"{a.t0:.3f}", "-i", a.video, "-t", f"{t1 - a.t0:.3f}",
               "-vf", f"{turn}scale={W}:{H}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-threads", "4", "-"]
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stdin=subprocess.DEVNULL)
        i = 0
        try:
            while True:
                buf = p.stdout.read(W * H * 3)
                if len(buf) < W * H * 3:
                    break
                yield i, np.frombuffer(buf, np.uint8).reshape(H, W, 3)
                i += 1
        finally:                                          # stopping early (stills): end the decoder quietly
            if p.poll() is None:
                p.stdout.close(); p.terminate()
            p.wait()

    def process(rgb):
        g = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        raw = model(rgb)
        gf = g.astype(np.float32) / 255.0
        ref = guided(gf, raw.astype(np.float32), r=max(4, H // 135), eps=1e-3)
        ref = drop_islands(np.clip(ref, 0, 1), a.min_region)
        out, jit = steady(ref, g)
        if a.choke > 0:
            out = cv2.erode(out, np.ones((int(2 * a.choke + 1),) * 2, np.uint8))
        if a.feather > 0:
            out = cv2.GaussianBlur(out, (0, 0), a.feather)
        out = np.clip((out - 0.03) / 0.94, 0, 1)                 # no faint haze far from the person
        return out, jit

    bgmode = a.bg
    base = os.path.join(a.out, f"{name}_matte")
    if a.frames:
        want = sorted(float(v) for v in a.frames.split(","))
        need = {int(round(t * fps)) for t in want}
        last = max(need)
        strip = []
        for i, rgb in frames():                                   # run the steady filter through, keep the asked frames
            al, _ = process(rgb)
            if i in need:
                rgba = np.dstack([fg_colour(rgb, al),
                                  (al * 255).astype(np.uint8)])
                pth = f"{base}_t{i / fps:.2f}.png"
                cv2.imwrite(pth, cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGRA))
                bg = make_bg(bgmode, P, rgb.shape)
                bg = cv2.GaussianBlur(rgb, (0, 0), 25) if bg is None else bg
                comp = (rgba[..., :3] * al[..., None] + bg * (1 - al[..., None])).astype(np.uint8)
                strip.append(np.hstack([rgb, np.dstack([al * 255] * 3).astype(np.uint8), comp]))
                print("still", pth)
            if i >= last:
                break
        if strip:
            sh = np.vstack(strip)
            k = 1800 / sh.shape[1]
            cv2.imwrite(f"{base}_check.jpg", cv2.cvtColor(cv2.resize(sh, (1800, int(sh.shape[0] * k))), cv2.COLOR_RGB2BGR))
            print("check", f"{base}_check.jpg")
        return

    enc = lambda args, out: subprocess.Popen(
        ["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", args[0], "-s", f"{W}x{H}",
         "-framerate", f"{fn}/{fd}", "-i", "-", *args[1:], "-threads", "4", out], stdin=subprocess.PIPE)
    pa = enc(["rgba", "-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le", "-alpha_bits", "16"], base + "_Alpha.mov")
    pm = enc(["gray", "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p"], base + ".mp4")
    pp = enc(["rgb24", "-c:v", "libx264", "-crf", "18", "-preset", "slow", "-pix_fmt", "yuv420p", "-movflags", "+faststart"],
             base + "_preview.mp4")
    jit, flick, hist, n, t_start = [], [], [], 0, time.time()
    total = int((t1 - a.t0) * fps)
    for i, rgb in frames():
        al, j = process(rgb)
        if j is not None:
            jit.append(j)
        small = cv2.resize(al, (480, max(16, int(round(H * 480 / W)))), interpolation=cv2.INTER_AREA)
        hist = (hist + [small])[-3:]
        if len(hist) == 3:                                     # flicker: the alpha's second difference in time
            band = (hist[1] > 0.03) & (hist[1] < 0.97)          # (smooth motion ~0, shimmer large), edge band only
            if band.any():
                flick.append(float(np.abs(hist[2] - 2 * hist[1] + hist[0])[band].mean()))
        clean = fg_colour(rgb, al)
        a8 = (al * 255).astype(np.uint8)
        pa.stdin.write(np.dstack([clean, a8]).tobytes())
        pm.stdin.write(a8.tobytes())
        bg = make_bg(bgmode, P, rgb.shape)
        bg = cv2.GaussianBlur(rgb, (0, 0), 25) if bg is None else bg
        pp.stdin.write((clean * al[..., None] + bg * (1 - al[..., None])).astype(np.uint8).tobytes())
        n += 1
        if n % 30 == 0:
            sys.stdout.write(f"\r  frame {n}/{total}  {n / max(1e-6, time.time() - t_start):.1f} fps"); sys.stdout.flush()
    for p in (pa, pm, pp):
        p.stdin.close(); p.wait()
    jj = np.array(jit) if jit else np.zeros(1)
    ff = np.array(flick) if flick else np.zeros(1)
    rep = {"rotate": a.rotate, "video": os.path.abspath(a.video), "t0": a.t0, "t1": t1, "frames": n, "size": [W, H], "fps": round(fps, 3),
           "model": a.model, "infer": a.infer, "steady": a.steady, "choke": a.choke, "feather": a.feather,
           "edge_flicker_mean": round(float(ff.mean()), 4), "edge_flicker_p95": round(float(np.percentile(ff, 95)), 4),
           "edge_change_mean": round(float(jj.mean()), 4), "edge_change_p95": round(float(np.percentile(jj, 95)), 4),
           "seconds": round(time.time() - t_start, 1)}
    json.dump(rep, open(base + ".json", "w"), indent=1)
    print(f"\r  wrote {base}_Alpha.mov, {base}.mp4, {base}_preview.mp4  ({n} frames; edge flicker mean "
          f"{rep['edge_flicker_mean']}, p95 {rep['edge_flicker_p95']})")


if __name__ == "__main__":
    main()
