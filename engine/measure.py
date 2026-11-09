#!/usr/bin/env python3
"""measure.py - measure a finished motion piece (an After Effects show open, a sting, a lower third) so it can be
rebuilt on springs in logo/motion.html. Free tools only: ffmpeg, OpenCV, numpy, scipy.

  measure.py probe   <video> --out DIR [--start S] [--end S] [--dump]
        cuts, flashes and motion events (frame numbers + seconds), colour palette of every shot.
        Writes DIR/probe.json and DIR/probe.jpg (timeline + one frame per shot with its palette). --dump also saves
        every analysed frame (half size JPG) to DIR/frames/ for looking.
  measure.py track   <video> --out DIR --start S --end S --ref T --el name:x,y,w,h [--el ...] [--scale 0.5]
        follows each element (a box drawn on the frame at --ref seconds, full-size pixels) through S..E and measures
        its position (centre, px), scale and rotation (relative to --ref) and opacity (contrast gain against --ref,
        1 = as at --ref). ECC alignment (cv2.findTransformECC, affine), frame to frame outward from --ref. Where an
        element fades below what ECC can lock onto, its geometry holds and only opacity keeps being measured
        ("ok": false). Writes DIR/track.json and DIR/track.jpg (every channel against time).
  measure.py fit     DIR/track.json [--out DIR/fit.json] [--max-springs 2] [--only a,b] [--start-at S] [--op-step 0.1]
        fits springs (spring.py maths) to every channel that moves: start, from, to, zeta, omega, launch speed. Up to
        --max-springs chained springs per channel (added like spring.camera_at keys). Prints the nearest preset and
        a ready motion.html call (timed('<preset>', settle, launch)). Opacity is also written as a step track
        (op_steps: [time, level] each time the level, quantised to --op-step of the end level, changes), which is how
        flicker-on and blinks come out. --start-at pins the first spring to the section's first frame, so the curve
        extrapolates back over frames the tracker could not lock (motion blur). Writes fit.json and fit.jpg.
  measure.py compare <original> <rebuild> --out side.mp4 [--start S] [--dur S] [--labels "A|B"] [--audio]
        side-by-side MP4 (original | rebuild, same frame numbers, per-frame SSIM graph under them) and per-frame SSIM
        on luma (Wang et al. 2004, 11x11 Gaussian, sigma 1.5) at full size. Writes <out>.ssim.csv and prints
        mean / median / min / worst frames. Both videos must have the same frame rate.

Method for a whole open (what the steps are for): probe to find the cuts, events and palette; for each section
pick the elements (sheet.py or probe --dump to see them) and track them from a frame where all are fully visible;
fit springs; write the template in motion.html with the fitted presets and the measured beats as named constants;
render it at the original frame rate (motion.py --fps 29.97002997) and compare. Read every sheet.
"""
import argparse, json, math, os, subprocess, sys
import numpy as np
import cv2

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import spring as S  # noqa: E402


# ------------------------------------------------------------------------------------------------ video io
def vinfo(path):
    o = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height,r_frame_rate,nb_frames:format=duration", "-of", "json", path],
                       capture_output=True, text=True, check=True).stdout
    j = json.loads(o); st = j["streams"][0]
    n, d = st["r_frame_rate"].split("/")
    return {"w": int(st["width"]), "h": int(st["height"]), "fps": float(n) / float(d),
            "dur": float(j["format"]["duration"])}


def frames(path, start=0.0, dur=None, size=None, gray=False):
    """Yield (index_from_start, frame) as uint8 arrays (BGR, or gray). Exact frames: decodes from the start and
    selects by frame number, so frame k is the k-th frame at or after `start`."""
    info = vinfo(path); fps = info["fps"]
    w, h = size or (info["w"], info["h"])
    n0 = int(round(start * fps))
    sel = f"select='gte(n\\,{n0})" + (f"*lt(n\\,{n0 + int(round(dur * fps))})'" if dur else "'")
    vf = sel + (f",scale={w}:{h}:flags=area" if (w, h) != (info["w"], info["h"]) else "")
    pf, ch = ("gray", 1) if gray else ("bgr24", 3)
    p = subprocess.Popen(["ffmpeg", "-nostdin", "-v", "error", "-i", path, "-vf", vf, "-fps_mode", "passthrough",
                          "-f", "rawvideo", "-pix_fmt", pf, "-"], stdout=subprocess.PIPE, stdin=subprocess.DEVNULL)
    sz = w * h * ch; k = 0
    try:
        while True:
            b = p.stdout.read(sz)
            if len(b) < sz: break
            a = np.frombuffer(b, np.uint8).reshape((h, w) if gray else (h, w, 3))
            yield k, a; k += 1
    finally:
        p.stdout.close(); p.kill(); p.wait()


def put(img, text, org, scale=0.5, color=(255, 255, 255), bg=(0, 0, 0)):
    (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, 1)
    x, y = org
    cv2.rectangle(img, (x - 2, y - th - 4), (x + tw + 2, y + 4), bg, -1)
    cv2.putText(img, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale, color, 1, cv2.LINE_AA)


def hexc(bgr): return "#%02X%02X%02X" % (int(bgr[2]), int(bgr[1]), int(bgr[0]))


def plot(series, w, h, title="", marks=(), colors=None, t=None, ylim=None):
    """Tiny line plot with OpenCV: series = {name: array}; marks = x positions (same units as t) to draw as lines."""
    img = np.full((h, w, 3), 24, np.uint8)
    pal = colors or [(80, 200, 255), (120, 255, 120), (255, 160, 80), (200, 120, 255), (90, 90, 255), (220, 220, 220)]
    items = [(k, np.asarray(v, float)) for k, v in series.items() if len(v)]
    if not items: return img
    n = max(len(v) for _, v in items)
    t = np.arange(n) if t is None else np.asarray(t, float)
    lo = min(np.nanmin(v) for _, v in items) if ylim is None else ylim[0]
    hi = max(np.nanmax(v) for _, v in items) if ylim is None else ylim[1]
    if hi - lo < 1e-9: hi = lo + 1
    L, R, T, B = 50, 10, 22, 18
    X = lambda x: int(L + (x - t[0]) / max(t[-1] - t[0], 1e-9) * (w - L - R))
    Y = lambda y: int(h - B - (y - lo) / (hi - lo) * (h - T - B))
    for m in marks: cv2.line(img, (X(m), T), (X(m), h - B), (60, 60, 200), 1)
    cv2.putText(img, f"{hi:.3g}", (2, T + 8), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (160, 160, 160), 1)
    cv2.putText(img, f"{lo:.3g}", (2, h - B), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (160, 160, 160), 1)
    for i, (k, v) in enumerate(items):
        c = pal[i % len(pal)]
        pts = [(X(t[j]), Y(v[j])) for j in range(len(v)) if np.isfinite(v[j])]
        if len(pts) > 1: cv2.polylines(img, [np.array(pts, np.int32)], False, c, 1, cv2.LINE_AA)
        cv2.putText(img, k, (L + 4 + 90 * i, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.4, c, 1, cv2.LINE_AA)
    if title: cv2.putText(img, title, (w - 8 - 7 * len(title), 14), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (230, 230, 230), 1)
    cv2.putText(img, f"{t[0]:.2f}s", (L, h - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (160, 160, 160), 1)
    cv2.putText(img, f"{t[-1]:.2f}s", (w - 50, h - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (160, 160, 160), 1)
    return img


# ------------------------------------------------------------------------------------------------ probe
def palette(imgs, k=6):
    px = np.concatenate([cv2.resize(i, (160, 90), interpolation=cv2.INTER_AREA).reshape(-1, 3) for i in imgs])
    lab = cv2.cvtColor(px.reshape(-1, 1, 3), cv2.COLOR_BGR2LAB).reshape(-1, 3).astype(np.float32)
    k = min(k, len(np.unique(px, axis=0)))
    _, lbl, cen = cv2.kmeans(lab, k, None, (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 40, 0.5), 3,
                             cv2.KMEANS_PP_CENTERS)
    share = np.bincount(lbl.ravel(), minlength=k) / len(lbl)
    bgr = cv2.cvtColor(cen.reshape(-1, 1, 3).astype(np.uint8), cv2.COLOR_LAB2BGR).reshape(-1, 3)
    # saturated accents get lost in a dark frame's share: also report the most saturated cluster-free pixels
    hsv = cv2.cvtColor(px.reshape(-1, 1, 3), cv2.COLOR_BGR2HSV).reshape(-1, 3)
    sat = px[(hsv[:, 1] > 120) & (hsv[:, 2] > 90)]
    accent = hexc(np.median(sat, 0)) if len(sat) > 30 else None
    order = np.argsort(-share)
    return [{"hex": hexc(bgr[i]), "share": round(float(share[i]), 3)} for i in order], accent


def cmd_probe(a):
    info = vinfo(a.video); fps = info["fps"]
    start = a.start or 0.0; dur = (a.end - start) if a.end else None
    os.makedirs(a.out, exist_ok=True)
    if a.dump: os.makedirs(os.path.join(a.out, "frames"), exist_ok=True)
    sw, sh = 480, int(round(480 * info["h"] / info["w"] / 2) * 2)
    small, luma, diff, hcorr = [], [], [], []
    prev = prevh = None
    for k, f in frames(a.video, start, dur, (sw, sh)):
        g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
        hsv = cv2.cvtColor(f, cv2.COLOR_BGR2HSV)
        hst = cv2.calcHist([hsv], [0, 1, 2], None, [16, 8, 8], [0, 180, 0, 256, 0, 256]); cv2.normalize(hst, hst)
        luma.append(float(g.mean()))
        diff.append(float(np.abs(g.astype(np.int16) - prev).mean()) if prev is not None else 0.0)
        hcorr.append(float(cv2.compareHist(prevh, hst, cv2.HISTCMP_CORREL)) if prevh is not None else 1.0)
        prev, prevh = g.astype(np.int16), hst
        small.append(f)
        if a.dump: cv2.imwrite(os.path.join(a.out, "frames", f"f{k:05d}.jpg"), f, [cv2.IMWRITE_JPEG_QUALITY, 85])
    n = len(small); luma, diff, hcorr = map(np.array, (luma, diff, hcorr))
    ts = start + np.arange(n) / fps
    # cuts: a frame that differs much more than its neighbourhood AND changes the colour histogram
    med = np.array([np.median(diff[max(0, i - 8):i + 9]) for i in range(n)])
    cuts = [i for i in range(1, n) if diff[i] > max(a.cut_min, 3.5 * med[i]) and hcorr[i] < a.cut_hist]
    # flashes: luma jumps up for 1-4 frames and comes back
    base = np.array([np.median(luma[max(0, i - 6):i + 7]) for i in range(n)])
    flashes = [i for i in range(n) if luma[i] - base[i] > a.flash and (i == 0 or luma[i - 1] - base[i - 1] <= a.flash)]
    # events: peaks of motion energy that are not cuts (hits, whips, landings)
    ev = []
    for i in range(2, n - 2):
        if i in cuts: continue
        if diff[i] == diff[i - 2:i + 3].max() and diff[i] > max(2.0, 2.5 * med[i]):
            ev.append((float(diff[i]), i))
    ev = [i for _, i in sorted(ev, reverse=True)[:a.events]]
    # flicker: three or more "cuts" no more than 3 frames apart are a strobe / neon flicker inside one shot, not cuts
    flick, grp = [], []
    for c in cuts + [10 ** 9]:
        if grp and c - grp[-1] > 3:
            if len(grp) >= 3: flick.append((grp[0], grp[-1]))
            grp = []
        grp.append(c)
    inflick = {c for f0, f1 in flick for c in cuts if f0 <= c <= f1}
    cuts = [c for c in cuts if c not in inflick]
    bounds = [0] + cuts + [n]
    shots = []
    for s0, s1 in zip(bounds[:-1], bounds[1:]):
        if s1 - s0 < 1: continue
        pick = [small[j] for j in np.linspace(s0, s1 - 1, min(5, s1 - s0)).astype(int)]
        pal, acc = palette(pick)
        shots.append({"from_frame": int(s0), "to_frame": int(s1 - 1), "t0": round(float(ts[s0]), 3),
                      "t1": round(float(ts[s1 - 1] + 1 / fps), 3), "palette": pal, "accent": acc})
    fr = lambda i: {"frame": int(i + round(start * fps)), "t": round(float(ts[i]), 3)}
    res = {"video": a.video, "fps": fps, "size": [info["w"], info["h"]], "start": start, "frames": n,
           "cuts": [fr(i) | {"score": round(float(diff[i]), 2)} for i in cuts],
           "flashes": [fr(i) | {"rise": round(float(luma[i] - base[i]), 1)} for i in flashes],
           "events": [fr(i) | {"motion": round(float(diff[i]), 2)} for i in sorted(ev)],
           "flicker": [{"from": fr(f0), "to": fr(f1)} for f0, f1 in flick],
           "shots": shots,
           "per_frame": {"luma": [round(float(x), 2) for x in luma], "motion": [round(float(x), 3) for x in diff]}}
    json.dump(res, open(os.path.join(a.out, "probe.json"), "w"), indent=1)
    # sheet
    W = 1600
    top = plot({"motion": diff, "luma/10": luma / 10}, W, 220, "motion (mean |diff|) and luma",
               marks=[ts[i] for i in cuts], t=ts)
    for i in flashes: cv2.circle(top, (int(50 + (ts[i] - ts[0]) / max(ts[-1] - ts[0], 1e-9) * (W - 60)), 30), 5, (255, 255, 255), -1)
    for i in ev: cv2.circle(top, (int(50 + (ts[i] - ts[0]) / max(ts[-1] - ts[0], 1e-9) * (W - 60)), 40), 4, (80, 255, 255), -1)
    tiles = []
    for s in shots:
        m = (s["from_frame"] + s["to_frame"]) // 2
        tile = cv2.resize(small[m], (320, 180)).copy()
        put(tile, f"{s['t0']:.2f}-{s['t1']:.2f}s f{s['from_frame'] + int(round(start * fps))}", (4, 16), 0.42)
        sw_ = np.zeros((26, 320, 3), np.uint8); x = 0
        for c in s["palette"]:
            wpx = max(1, int(round(c["share"] * 320)))
            sw_[:, x:x + wpx] = [int(c["hex"][5:7], 16), int(c["hex"][3:5], 16), int(c["hex"][1:3], 16)]; x += wpx
        if s["accent"]:
            cv2.rectangle(sw_, (296, 2), (318, 24), [int(s["accent"][5:7], 16), int(s["accent"][3:5], 16), int(s["accent"][1:3], 16)], -1)
        tiles.append(np.vstack([tile, sw_]))
    rows = [np.hstack(tiles[i:i + 5] + [np.zeros_like(tiles[0])] * (5 - len(tiles[i:i + 5]))) for i in range(0, len(tiles), 5)]
    grid = np.vstack(rows) if rows else np.zeros((10, W, 3), np.uint8)
    grid = cv2.copyMakeBorder(grid, 0, 0, 0, W - grid.shape[1], cv2.BORDER_CONSTANT) if grid.shape[1] < W else grid[:, :W]
    cv2.imwrite(os.path.join(a.out, "probe.jpg"), np.vstack([top, grid]), [cv2.IMWRITE_JPEG_QUALITY, 88])
    print(f"probe: {n} frames at {fps:.3f} fps, {len(cuts)} cuts, {len(flick)} flicker runs, {len(flashes)} flashes, {len(ev)} events, {len(shots)} shots")
    for c in res["cuts"]: print(f"  cut   f{c['frame']}  {c['t']:.3f}s  score {c['score']}")
    for c in res["flashes"]: print(f"  flash f{c['frame']}  {c['t']:.3f}s  +{c['rise']} luma")
    for c in res["events"]: print(f"  event f{c['frame']}  {c['t']:.3f}s  motion {c['motion']}")
    for c in res["flicker"]: print(f"  flicker f{c['from']['frame']}-f{c['to']['frame']}  {c['from']['t']:.3f}-{c['to']['t']:.3f}s")
    print(f"wrote {a.out}/probe.json, probe.jpg")


# ------------------------------------------------------------------------------------------------ track
def decompose(M):
    a, b, tx = M[0]; c, d, ty = M[1]
    s = math.sqrt(abs(a * d - b * c)); rot = math.degrees(math.atan2(c, a))
    return s, rot


def cmd_track(a):
    info = vinfo(a.video); fps = info["fps"]; k = a.scale
    sw, sh = int(round(info["w"] * k / 2) * 2), int(round(info["h"] * k / 2) * 2)
    fr = [f for _, f in frames(a.video, a.start, a.end - a.start, (sw, sh), gray=True)]
    n = len(fr); ts = a.start + np.arange(n) / fps
    ri = int(np.argmin(np.abs(ts - a.ref)))
    els = {}
    for spec in a.el:
        name, box = spec.split(":"); x, y, w, h = (float(v) * k for v in box.split(","))
        els[name] = (int(x), int(y), int(w), int(h))
    crit = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 80, 1e-5)
    out = {"video": a.video, "fps": fps, "start": a.start, "end": a.end, "ref": float(ts[ri]), "scale": k, "elements": {}}
    for name, (x, y, w, h) in els.items():
        tmpl = cv2.GaussianBlur(fr[ri][y:y + h, x:x + w].astype(np.float32), (3, 3), 0)
        tz = tmpl - tmpl.mean(); tv = float((tz * tz).sum()) or 1.0
        res = [None] * n
        res[ri] = {"M": np.array([[1, 0, x], [0, 1, y]], np.float32), "rho": 1.0, "ok": True}
        for order in (range(ri + 1, n), range(ri - 1, -1, -1)):
            M = res[ri]["M"].copy()
            for i in order:
                img = cv2.GaussianBlur(fr[i].astype(np.float32), (3, 3), 0)
                ok, rho = True, 0.0
                try:
                    rho, M2 = cv2.findTransformECC(tmpl, img, M.copy(), cv2.MOTION_AFFINE, crit, None, 5)
                    s2, _ = decompose(M2)
                    if rho < a.min_rho or not (0.2 < s2 < 5): ok = False
                    else: M = M2
                except cv2.error:
                    ok = False
                res[i] = {"M": M.copy(), "rho": float(rho), "ok": ok}
        rows = []
        for i in range(n):
            M = res[i]["M"]
            src = cv2.GaussianBlur(fr[i].astype(np.float32), (3, 3), 0)      # blurred like the template, so gain at --ref is 1
            warped = cv2.warpAffine(src, M, (w, h), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP)
            cz = warped - warped.mean()
            gain = float((cz * tz).sum() / tv)                      # least-squares contrast gain against the reference
            s, rot = decompose(M)
            cx, cy = M @ np.array([w / 2, h / 2, 1.0])
            rows.append({"t": round(float(ts[i]), 4), "x": round(float(cx / k), 2), "y": round(float(cy / k), 2),
                         "s": round(s, 5), "rot": round(rot, 3), "op": round(gain, 4), "rho": round(res[i]["rho"], 3),
                         "ok": res[i]["ok"]})
        out["elements"][name] = {"roi": [v / k for v in (x, y, w, h)], "frames": rows}
    os.makedirs(a.out, exist_ok=True)
    json.dump(out, open(os.path.join(a.out, "track.json"), "w"), indent=1)
    # sheet: per element one row of plots (x/y relative, scale, rotation, opacity) + reference crop
    rows = []
    for name, e in out["elements"].items():
        f = e["frames"]; t = [r["t"] for r in f]
        x0, y0 = f[ri]["x"], f[ri]["y"]
        p1 = plot({"dx px": [r["x"] - x0 for r in f], "dy px": [r["y"] - y0 for r in f]}, 420, 160, name + " position", t=t)
        p2 = plot({"scale": [r["s"] for r in f]}, 360, 160, "scale", t=t)
        p3 = plot({"rot deg": [r["rot"] for r in f]}, 300, 160, "rotation", t=t)
        p4 = plot({"opacity": [r["op"] for r in f], "rho": [r["rho"] for r in f]}, 360, 160, "opacity / lock", t=t)
        x, y, w, h = (int(v * k) for v in e["roi"])
        crop = cv2.cvtColor(fr[ri][y:y + h, x:x + w], cv2.COLOR_GRAY2BGR)
        crop = cv2.resize(crop, (160, max(1, int(160 * h / max(w, 1)))))[:160]
        crop = cv2.copyMakeBorder(crop, 0, 160 - crop.shape[0], 0, 0, cv2.BORDER_CONSTANT)
        rows.append(np.hstack([crop, p1, p2, p3, p4]))
    cv2.imwrite(os.path.join(a.out, "track.jpg"), np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 88])
    for name, e in out["elements"].items():
        lost = sum(not r["ok"] for r in e["frames"])
        print(f"track {name}: {len(e['frames'])} frames, {lost} without a lock (geometry held, opacity still measured)")
    print(f"wrote {a.out}/track.json, track.jpg")


# ------------------------------------------------------------------------------------------------ fit
def solve_np(t, zeta, omega, v0=0.0):
    """spring.solve over a numpy array of times (offset from target, starts at -1; -1 for t <= 0)."""
    t = np.maximum(np.asarray(t, float), 0.0); y0 = -1.0
    if abs(zeta - 1) < 1e-6:
        b = v0 + omega * y0; y = np.exp(-omega * t) * (y0 + b * t)
    elif zeta < 1:
        wd = omega * math.sqrt(1 - zeta * zeta); b = (v0 + zeta * omega * y0) / wd
        y = np.exp(-zeta * omega * t) * (y0 * np.cos(wd * t) + b * np.sin(wd * t))
    else:
        r = omega * math.sqrt(zeta * zeta - 1); r1, r2 = -zeta * omega + r, -zeta * omega - r
        c2 = (v0 - r1 * y0) / (r2 - r1); c1 = y0 - c2
        y = c1 * np.exp(r1 * t) + c2 * np.exp(r2 * t)
    return y


def spring_curve(t, start, frm, to, zeta, omega, launch):
    return frm + (to - frm) * (1 + solve_np(np.asarray(t, float) - start, zeta, omega, launch * omega))


def chain(t, base, springs):
    """Value = base + sum of (to - from) * progress for each spring (spring.camera_at style)."""
    y = np.full_like(t, base, dtype=float)
    for sp in springs:
        y += (sp["to"] - sp["from"]) * (spring_curve(t, sp["start"], 0.0, 1.0, sp["zeta"], sp["omega"], sp["launch"]))
    return y


def fit_channel(t, v, max_springs=2, start_at=None):
    from scipy.optimize import least_squares
    rng = float(np.nanmax(v) - np.nanmin(v))
    if rng < 1e-9: return None
    best = None
    t0, t1 = float(t[0]), float(t[-1])
    for ns in range(1, max_springs + 1):
        for launch_free in (False, True):
            # parameters per spring: start, delta, log(zeta), log(omega), launch
            def unpack(p):
                sps, frm = [], float(p[0])
                cur = frm
                for j in range(ns):
                    st, dl, lz, lw, ln = p[1 + 5 * j:6 + 5 * j]
                    sps.append({"start": float(st), "from": cur, "to": cur + float(dl), "zeta": float(math.exp(lz)),
                                "omega": float(math.exp(lw)), "launch": float(ln) if launch_free else 0.0})
                    cur += float(dl)
                return frm, sps
            def resid(p):
                frm, sps = unpack(p)
                return (chain(t, frm, sps) - v) / rng
            tries = []
            for frac in ([0.0, 0.2, 0.5] if ns == 1 else [0.0, 0.3]):
                p0 = [float(v[0])]
                for j in range(ns):
                    st = t0 + (t1 - t0) * (frac + j * 0.4) * 0.8
                    p0 += [st, (float(v[-1]) - float(v[0])) / ns, math.log(0.8), math.log(10.0), 0.5 if launch_free else 0.0]
                lo = [float(np.nanmin(v)) - rng]; hi = [float(np.nanmax(v)) + rng]
                for j in range(ns):
                    s_lo, s_hi = (start_at - 1e-3, start_at + 1e-3) if (start_at is not None and j == 0) else (t0 - 1.0, t1)
                    lo += [s_lo, -4 * rng, math.log(0.08), math.log(0.5), 0.0]
                    hi += [s_hi, 4 * rng, math.log(2.5), math.log(80.0), 3.0 if launch_free else 1e-9]
                p0 = np.clip(p0, np.array(lo) + 1e-9, np.array(hi) - 1e-9)
                try:
                    r = least_squares(resid, p0, bounds=(lo, hi), max_nfev=4000)
                    tries.append(r)
                except Exception:
                    pass
            if not tries: continue
            r = min(tries, key=lambda q: q.cost)
            rms = float(np.sqrt(np.mean(r.fun ** 2)))
            k = len(r.x)
            score = len(t) * math.log(rms ** 2 + 1e-10) + 2 * k          # AIC-style: more springs must earn their keep
            frm, sps = unpack(r.x)
            if best is None or score < best["score"] - 2:
                best = {"score": score, "rms_frac": rms, "base": frm, "springs": sps}
    return best


def nearest_preset(zeta, omega):
    return min(S.PRESETS, key=lambda n: (math.log(S.PRESETS[n][0] / zeta)) ** 2 * 4 + (math.log(S.PRESETS[n][1] / omega)) ** 2 * 0.25)


def cmd_fit(a):
    j = json.load(open(a.track))
    out = {"track": a.track, "fps": j["fps"], "elements": {}}
    lines, rows = [], []
    for name, e in j["elements"].items():
        f = e["frames"]; t = np.array([r["t"] for r in f])
        ok = np.array([r["ok"] for r in f])
        out["elements"][name] = {}
        prow = []
        for ch, tol in (("x", 1.5), ("y", 1.5), ("s", 0.004), ("rot", 0.3), ("op", 0.03)):
            v = np.array([r[ch] for r in f], float)
            if a.only and name not in a.only.split(","): continue
            use = np.ones_like(ok) if ch == "op" else ok          # geometry only where the tracker had a lock
            if use.sum() < 6: continue
            tv, vv = t[use], v[use]
            if np.nanmax(vv) - np.nanmin(vv) < tol:
                out["elements"][name][ch] = {"static": float(np.median(vv))}; continue
            if ch == "op":                                        # flicker / step track: opacity quantised, run-length coded
                full = float(np.median(vv[-max(3, len(vv) // 4):])) or 1.0
                q = np.clip(np.round(vv / full / a.op_step) * a.op_step, 0, 1.5)
                steps = [[round(float(tv[0]), 4), round(float(q[0]), 2)]]
                for tt, qq in zip(tv[1:], q[1:]):
                    if abs(qq - steps[-1][1]) > 1e-6: steps.append([round(float(tt), 4), round(float(qq), 2)])
                out["elements"][name]["op_steps"] = steps
                lines.append(f"{name}.op steps ({len(steps)}): " + " ".join(f"{t_:.3f}:{l_:g}" for t_, l_ in steps[:24]) + (" ..." if len(steps) > 24 else ""))
            fit = fit_channel(tv, vv, a.max_springs, a.start_at)
            if not fit: continue
            for sp in fit["springs"]:
                sp["settle"] = S.settle(zeta=sp["zeta"], omega=sp["omega"], v0=sp["launch"] * sp["omega"])
                sp["overshoot"] = S.overshoot(zeta=sp["zeta"], omega=sp["omega"], v0=sp["launch"] * sp["omega"])
                sp["preset"] = nearest_preset(sp["zeta"], sp["omega"])
                sp["js"] = (f"move(t, {sp['start']:.3f}, {sp['from']:.4g}, {sp['to']:.4g}, "
                            f"timed('{sp['preset']}', {sp['settle']:.2f}{', %.2f' % sp['launch'] if sp['launch'] > 0.05 else ''}))")
                for kk in ("start", "from", "to", "zeta", "omega", "launch", "settle", "overshoot"):
                    sp[kk] = round(float(sp[kk]), 4)
            out["elements"][name][ch] = {"base": round(fit["base"], 4), "rms_frac": round(fit["rms_frac"], 4), "springs": fit["springs"]}
            for sp in fit["springs"]:
                lines.append(f"{name}.{ch}: start {sp['start']:.3f}s {sp['from']:.4g} -> {sp['to']:.4g}  zeta {sp['zeta']:.2f} "
                             f"omega {sp['omega']:.1f} launch {sp['launch']:.2f}  settle {sp['settle']:.2f}s overshoot "
                             f"{sp['overshoot'] * 100:.1f}%  ~{sp['preset']}  (rms {fit['rms_frac'] * 100:.1f}% of range)")
            prow.append(plot({"measured": vv, "fit": chain(tv, fit["base"], fit["springs"])}, 380, 150, f"{name}.{ch}", t=tv))
        if prow: rows.append(np.hstack(prow + [np.full_like(prow[0], 24)] * (5 - len(prow))))
    of = a.out or os.path.join(os.path.dirname(a.track), "fit.json")
    json.dump(out, open(of, "w"), indent=1)
    if rows: cv2.imwrite(os.path.splitext(of)[0] + ".jpg", np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 88])
    print("\n".join(lines) if lines else "fit: nothing moves")
    print(f"wrote {of}")


# ------------------------------------------------------------------------------------------------ compare
def ssim(a, b):
    a = a.astype(np.float64); b = b.astype(np.float64)
    C1, C2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
    g = lambda x: cv2.GaussianBlur(x, (11, 11), 1.5)
    ma, mb = g(a), g(b)
    va, vb, cab = g(a * a) - ma * ma, g(b * b) - mb * mb, g(a * b) - ma * mb
    m = ((2 * ma * mb + C1) * (2 * cab + C2)) / ((ma * ma + mb * mb + C1) * (va + vb + C2))
    return float(m[5:-5, 5:-5].mean())


def cmd_compare(a):
    from PIL import Image, ImageDraw, ImageFont
    io_, ir = vinfo(a.original), vinfo(a.rebuild)
    if abs(io_["fps"] - ir["fps"]) > 0.01:
        sys.exit(f"compare: frame rates differ ({io_['fps']:.3f} vs {ir['fps']:.3f}); render the rebuild at the original's rate")
    fps = io_["fps"]; dur = a.dur or ir["dur"]
    W, H = io_["w"], io_["h"]
    fonts = os.path.join(os.path.dirname(HERE), "resources", "fonts")
    try:
        fb = ImageFont.truetype(os.path.join(fonts, "BarlowCondensed-SemiBold.ttf"), 34)
        fs = ImageFont.truetype(os.path.join(fonts, "BarlowCondensed-Medium.ttf"), 24)
    except OSError:
        fb = fs = ImageFont.load_default()
    la, lb = (a.labels or "ORIGINAL|REBUILD").split("|")
    go = frames(a.original, a.start, dur); gr = frames(a.rebuild, 0.0, dur, (W, H))
    scores = []
    base = os.path.splitext(a.out)[0]
    cmd = ["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", "1920x1080",
           "-r", f"{fps:.6f}", "-i", "-"]
    if a.audio: cmd += ["-ss", f"{a.start:.4f}", "-t", f"{dur:.4f}", "-i", a.original, "-map", "0:v", "-map", "1:a?", "-c:a", "aac", "-b:a", "192k"]
    cmd += ["-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p", "-movflags", "+faststart", a.out]
    enc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    n_total = int(round(dur * fps))
    for (i, fo), (_, fr_) in zip(go, gr):
        so = ssim(cv2.cvtColor(fo, cv2.COLOR_BGR2GRAY), cv2.cvtColor(fr_, cv2.COLOR_BGR2GRAY))
        scores.append(so)
        canvas = np.full((1080, 1920, 3), 16, np.uint8)
        canvas[150:690, 0:960] = cv2.resize(fo, (960, 540), interpolation=cv2.INTER_AREA)
        canvas[150:690, 960:1920] = cv2.resize(fr_, (960, 540), interpolation=cv2.INTER_AREA)
        # SSIM graph
        gx0, gy0, gw, gh = 80, 760, 1760, 260
        cv2.rectangle(canvas, (gx0, gy0), (gx0 + gw, gy0 + gh), (40, 40, 40), 1)
        for yv in (0.25, 0.5, 0.75, 1.0):
            yy = int(gy0 + gh - yv * gh); cv2.line(canvas, (gx0, yy), (gx0 + gw, yy), (45, 45, 45), 1)
        pts = [(int(gx0 + j / max(n_total - 1, 1) * gw), int(gy0 + gh - s_ * gh)) for j, s_ in enumerate(scores)]
        if len(pts) > 1: cv2.polylines(canvas, [np.array(pts, np.int32)], False, (80, 200, 255), 2, cv2.LINE_AA)
        cv2.circle(canvas, pts[-1], 6, (255, 255, 255), -1)
        im = Image.fromarray(cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB)); d = ImageDraw.Draw(im)
        d.text((24, 92), la, font=fb, fill=(255, 255, 255)); d.text((984, 92), lb, font=fb, fill=(255, 255, 255))
        d.text((24, 30), f"frame {i:4d}   {i / fps:5.2f} s", font=fs, fill=(200, 200, 200))
        d.text((984, 30), f"SSIM this frame {so:.3f}    mean so far {np.mean(scores):.3f}", font=fs, fill=(200, 200, 200))
        d.text((gx0, gy0 - 34), "per-frame SSIM (luma, full size)", font=fs, fill=(170, 170, 170))
        for yv in (0.25, 0.5, 0.75, 1.0): d.text((24, gy0 + gh - yv * gh - 12), f"{yv:.2f}", font=fs, fill=(120, 120, 120))
        enc.stdin.write(cv2.cvtColor(np.asarray(im), cv2.COLOR_RGB2BGR).tobytes())
    enc.stdin.close(); enc.wait()
    sc = np.array(scores)
    with open(base + ".ssim.csv", "w") as fh:
        fh.write("frame,t,ssim\n")
        for i, s_ in enumerate(sc): fh.write(f"{i},{i / fps:.4f},{s_:.5f}\n")
    worst = np.argsort(sc)[:5]
    print(f"compare: {len(sc)} frames  SSIM mean {sc.mean():.4f}  median {np.median(sc):.4f}  min {sc.min():.4f} "
          f"(frame {int(sc.argmin())})  p10 {np.percentile(sc, 10):.4f}")
    print("  worst frames: " + ", ".join(f"f{int(w)} {sc[w]:.3f}" for w in worst))
    print(f"wrote {a.out}, {base}.ssim.csv")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("probe"); p.add_argument("video"); p.add_argument("--out", required=True)
    p.add_argument("--start", type=float, default=0.0); p.add_argument("--end", type=float)
    p.add_argument("--dump", action="store_true"); p.add_argument("--cut-min", type=float, default=10.0)
    p.add_argument("--cut-hist", type=float, default=0.75, help="histogram correlation below this (with a big diff) = cut")
    p.add_argument("--flash", type=float, default=25.0, help="luma rise over the local median that counts as a flash")
    p.add_argument("--events", type=int, default=12)
    p = sub.add_parser("track"); p.add_argument("video"); p.add_argument("--out", required=True)
    p.add_argument("--start", type=float, required=True); p.add_argument("--end", type=float, required=True)
    p.add_argument("--ref", type=float, required=True); p.add_argument("--el", action="append", required=True)
    p.add_argument("--scale", type=float, default=0.5); p.add_argument("--min-rho", type=float, default=0.55)
    p = sub.add_parser("fit"); p.add_argument("track"); p.add_argument("--out"); p.add_argument("--max-springs", type=int, default=2)
    p.add_argument("--only", help="comma list of element names to fit (default all)")
    p.add_argument("--start-at", type=float, help="fix the first spring's start (s), e.g. the section's first frame")
    p.add_argument("--op-step", type=float, default=0.1, help="opacity step size for the flicker track (default 0.1)")
    p = sub.add_parser("compare"); p.add_argument("original"); p.add_argument("rebuild"); p.add_argument("--out", required=True)
    p.add_argument("--start", type=float, default=0.0); p.add_argument("--dur", type=float)
    p.add_argument("--labels"); p.add_argument("--audio", action="store_true")
    a = ap.parse_args()
    {"probe": cmd_probe, "track": cmd_track, "fit": cmd_fit, "compare": cmd_compare}[a.cmd](a)


if __name__ == "__main__":
    main()
