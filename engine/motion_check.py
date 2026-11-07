#!/usr/bin/env python3
"""motion_check.py — the motion gate (pairs with audio_check.py).

Finds the two motion faults a render can ship with:
  dead     a stretch where nothing on screen moves that wasn't meant to hold still
  stutter  a 1-2 frame repeat in the middle of motion (dropped/duplicated frame, render bug)
Repeats on a regular cadence (29.97 material in a 59.94 file, 3:2 pulldown, a steady slow-motion conform) are not
stutters: they are listed once as a "cadence" note. A repeat that breaks the cadence is still a stutter.

Only the flagged spots need eyes: pass --sheet to get one image with the motion timeline and
frames from every flagged span, then Read that image instead of watching every frame.

    python3 motion_check.py <video> [--holds 3.5-4.0,end:1.2] [--sheet out.jpg]

--holds  intentional stills, comma-separated: "a-b" seconds, "start:N" (first N s), "end:N" (last N s).
         e.g. logo-motion intro holds on its last frame -> --holds end:1.5
Exit code 0 = PASS, 1 = FAIL, 2 = could not read the file.
Needs ffmpeg/ffprobe and numpy; Pillow only for --sheet.
"""
import argparse
import json
import subprocess
import sys

import numpy as np


def probe(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height,r_frame_rate,avg_frame_rate,pix_fmt,nb_frames:format=duration",
         "-of", "json", path], capture_output=True, text=True, stdin=subprocess.DEVNULL)
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip() or "ffprobe failed")
    j = json.loads(out.stdout)
    s = j["streams"][0]
    num, den = (s.get("avg_frame_rate") or s["r_frame_rate"]).split("/")
    fps = float(num) / float(den) if float(den) else 30.0
    if fps <= 0:
        num, den = s["r_frame_rate"].split("/")
        fps = float(num) / float(den)
    return {"w": int(s["width"]), "h": int(s["height"]), "fps": fps,
            "alpha": any(k in s.get("pix_fmt", "") for k in ("a", "rgba", "argb", "yuva", "4444")) and
                     s.get("pix_fmt", "").startswith(("yuva", "rgba", "argb", "bgra", "abgr", "gbrap", "ya")),
            "dur": float(j["format"].get("duration", 0))}


def frames(path, info, width):
    """Yield grayscale frames (uint8, h x w). Alpha video is composited on mid grey first,
    so a fade done only in the alpha channel still counts as motion."""
    w = width - width % 2
    h = max(2, int(round(info["h"] * w / info["w"])) // 2 * 2)
    if info["alpha"]:
        vf = (f"color=c=0x808080:s={w}x{h}:r={info['fps']}[bg];"
              f"[0:v]scale={w}:{h},format=rgba[fg];[bg][fg]overlay=shortest=1,format=gray")
        cmd = ["ffmpeg", "-nostdin", "-v", "error", "-i", path, "-filter_complex", vf]
    else:
        cmd = ["ffmpeg", "-nostdin", "-v", "error", "-i", path, "-vf", f"scale={w}:{h},format=gray"]
    cmd += ["-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", "gray", "-"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stdin=subprocess.DEVNULL)
    size = w * h
    while True:
        buf = p.stdout.read(size)
        if len(buf) < size:
            break
        yield np.frombuffer(buf, np.uint8).reshape(h, w)
    p.wait()


def parse_holds(spec, dur):
    out = []
    for part in filter(None, (spec or "").split(",")):
        part = part.strip()
        if part.startswith("end:"):
            out.append((max(0.0, dur - float(part[4:])), dur + 1))
        elif part.startswith("start:"):
            out.append((-1, float(part[6:])))
        else:
            a, b = part.split("-")
            out.append((float(a), float(b)))
    return out


def covered(a, b, holds, slack):
    """True if [a,b] lies inside one hold (with a little slack for frame rounding)."""
    return any(ha - slack <= a and b <= hb + slack for ha, hb in holds)


def uncovered(a, b, holds):
    """Seconds of [a,b] outside every hold (holds assumed not to overlap)."""
    inside = sum(max(0.0, min(b, hb) - max(a, ha)) for ha, hb in holds)
    return max(0.0, (b - a) - inside)


def analyse(path, width, level, still_frac):
    """One pass. fracs[i] = share of pixels changed from frame i to i+1 (for stutters).
    Stills are found against an anchor frame instead of the previous frame, so a 1 px tick at
    the end of a spring doesn't break a still, and a slow drift still counts as motion once it adds up."""
    info = probe(path)
    fracs, stills = [], []
    prev = anchor = None
    a_idx = 0
    n = 0
    for f in frames(path, info, width):
        f16 = f.astype(np.int16)
        if prev is not None:
            fracs.append(float((np.abs(f16 - prev) > level).mean()))
            if float((np.abs(f16 - anchor) > level).mean()) >= still_frac:
                if n - 1 > a_idx:
                    stills.append((a_idx, n - 1))
                anchor, a_idx = f16, n
        else:
            anchor = f16
        prev = f16
        n += 1
    if n < 2:
        raise RuntimeError("fewer than 2 frames decoded")
    if n - 1 > a_idx:
        stills.append((a_idx, n - 1))
    return info, n, np.array(fracs), stills


def _runs(b):
    """[(is_low, start, length)] runs of a boolean array."""
    out, s = [], 0
    for k in range(1, len(b) + 1):
        if k == len(b) or b[k] != b[s]:
            out.append((bool(b[s]), s, k - s))
            s = k
    return out


def _balanced(v):
    """Run lengths that a constant frame-rate conform produces: one value, or two adjacent values where the rarer one
    never comes twice in a row and comes at a steady spacing (a Beatty pattern, e.g. 2,2,3,2,2,3)."""
    s = sorted(set(v))
    if len(s) == 1:
        return True
    if len(s) > 2 or s[1] - s[0] != 1:
        return False
    rare = s[0] if v.count(s[0]) <= v.count(s[1]) else s[1]
    pos = [k for k, x in enumerate(v) if x == rare]
    if len(pos) < 2:
        return False   # a one-off longer/shorter run is the irregularity we are looking for
    gaps = [q - p - 1 for p, q in zip(pos, pos[1:])]
    return min(gaps) >= 1 and max(gaps) - min(gaps) <= 1 and pos[0] <= max(gaps) and len(v) - 1 - pos[-1] <= max(gaps)


def _regular(rs, min_low):
    lo = [n for k, _, n in rs if k]
    ch = [n for k, _, n in rs if not k]
    if len(lo) < min_low or len(ch) < min_low - 1:
        return False
    # one kind of run is always single frames (repeats or new frames), the other follows a steady pattern
    return (set(lo) == {1} and _balanced(ch)) or (set(ch) == {1} and _balanced(lo))


def repeat_frames(fracs, dup=0.0005, rel=0.3):
    """True where frame i+1 repeats frame i: (almost) no change, or under `rel` x the change on both sides
    (an encoder leaves a little noise on a repeated frame)."""
    n = len(fracs)
    b = np.zeros(n, bool)
    for i in range(n):
        hb = fracs[max(0, i - 3):i].max(initial=0)
        ha = fracs[i + 1:i + 4].max(initial=0)
        b[i] = fracs[i] < dup or fracs[i] < rel * min(hb, ha)
    return b


def cadence_of(R, e, b, min_low=6, reach=24, max_period=12):
    """Is run e (a repeat) one beat of a regular repeat cadence (pulldown / frame-rate conform)? Yes when the
    repeat/new-picture pattern around it repeats exactly with a period of up to `max_period` frames for 3 periods
    (at least 12 frames) on one side, or when a stretch of runs around it (up to `reach` runs each side) follows one
    steady Beatty pattern (fractional rates). Returns the cadence's frames per new picture, or None."""
    s, n = R[e][1], R[e][2]
    for P in range(2, max_period + 1):
        L = max(3 * P, 12)
        for a in (s + n + 1 - L, s - 1):        # window ending just after the repeat / starting just before it
            w = b[a:a + L]
            if a < 0 or len(w) < L:
                continue
            if np.array_equal(w[P:], w[:-P]) and 3 <= w.sum() <= L - 2:
                return P / float(P - w[:P].sum())
    for k1 in range(0, reach + 1):
        a = e - 1 - k1
        if a < 0:
            break
        for k2 in range(0, reach + 1):
            z = e + 2 + k2
            if z > len(R):
                break
            rs = R[a:z]
            if _regular(rs, min_low):
                span = rs[-1][1] + rs[-1][2] - rs[0][1]
                return span / sum(n for k, _, n in rs if not k)
    return None


def find_issues(fracs, stills, fps, holds, min_dead, allow_stutter, busy=0.01, dup=0.0005):
    """stills: (first, last) frame index of each stretch that stays within still_frac of its first frame.
    Repeats that keep a regular cadence (e.g. 29.97 material in a 59.94 file repeats every other frame) are not
    stutters: they are summed up in one "cadence" note. A repeat that breaks the cadence is still a stutter."""
    issues = []
    slack = 1.5 / fps
    for a, b in stills:
        t0, t1 = a / fps, (b + 1) / fps          # frame b is on screen until (b+1)/fps
        if (b - a + 1) / fps >= min_dead:
            # a still that settles into a planned hold is fine; only the part outside holds counts
            kind = "dead" if uncovered(t0, t1, holds) >= min_dead else "hold"
            issues.append({"kind": kind, "t0": t0, "t1": t1, "frames": b - a + 1})
    if not allow_stutter:
        n = len(fracs)
        R = idx = rep = None
        cad = []
        i = 1
        while i < n - 1:
            if fracs[i] < dup:
                j = i
                while j + 1 < n and fracs[j + 1] < dup and j - i < 2:
                    j += 1
                if j - i < 2 and j + 1 < n and fracs[i - 1] > busy and fracs[j + 1] > busy:
                    t0, t1 = i / fps, (j + 2) / fps
                    if not covered(t0, t1, holds, slack):
                        if R is None:
                            rep = repeat_frames(fracs, dup)
                            R = _runs(rep)
                            idx = np.repeat(np.arange(len(R)), [r[2] for r in R])
                        per = cadence_of(R, int(idx[i]), rep)
                        if per:
                            cad.append((t0, t1, j - i + 1, per))
                        else:
                            issues.append({"kind": "stutter", "t0": t0, "t1": t1, "frames": j - i + 1})
                i = j + 1
            else:
                i += 1
        if cad:
            pers = sorted(c[3] for c in cad)
            issues.append({"kind": "cadence", "t0": cad[0][0], "t1": cad[-1][1], "frames": sum(c[2] for c in cad),
                           "count": len(cad), "every": round(pers[len(pers) // 2], 2),
                           "spans": [[round(c[0], 3), round(c[1], 3)] for c in cad]})
    issues.sort(key=lambda x: x["t0"])
    return issues


def make_sheet(path, out, info, fracs, issues, holds):
    from PIL import Image, ImageDraw
    fps, n = info["fps"], len(fracs) + 1
    W, GH = 1600, 220
    flagged = [x for x in issues if x["kind"] not in ("hold", "cadence")][:6]
    tw = 300
    th = int(round(tw * info["h"] / info["w"]))
    rows = len(flagged)
    img = Image.new("RGB", (W, GH + 40 + rows * (th + 34)), (24, 24, 28))
    d = ImageDraw.Draw(img)
    d.text((12, 8), f"motion_check  {path.split('/')[-1]}   {n / fps:.2f}s @ {fps:.2f}fps   "
                    f"red = dead/stutter, blue = allowed hold, green = frame-to-frame change (log)", fill=(220, 220, 220))
    x0, y0, gw, gh = 12, 30, W - 24, GH - 40
    d.rectangle([x0, y0, x0 + gw, y0 + gh], outline=(70, 70, 80))
    def xt(t): return x0 + gw * t / (n / fps)
    for ha, hb in holds:
        d.rectangle([xt(max(0, ha)), y0, xt(min(n / fps, hb)), y0 + gh], fill=(30, 50, 90))
    for x in issues:
        if x["kind"] not in ("hold", "cadence"):
            d.rectangle([xt(x["t0"]), y0, max(xt(x["t1"]), xt(x["t0"]) + 3), y0 + gh], fill=(120, 30, 30))
    lg = lambda v: np.log10(max(v, 1e-5))
    lo, hi = -5.0, 0.0
    def yv(v): return y0 + gh - gh * (lg(v) - lo) / (hi - lo)
    pts = [(xt((i + 1) / fps), yv(v)) for i, v in enumerate(fracs)]
    d.line(pts, fill=(120, 220, 140), width=2)
    for s in range(0, int(n / fps) + 1):
        d.line([(xt(s), y0 + gh), (xt(s), y0 + gh + 5)], fill=(150, 150, 150))
        d.text((xt(s) + 2, y0 + gh + 4), f"{s}s", fill=(150, 150, 150))
    y = GH + 30
    for x in flagged:
        d.text((12, y), f"{x['kind'].upper()}  {x['t0']:.2f}-{x['t1']:.2f}s  ({x['frames']} frames)", fill=(255, 120, 120))
        ts = [x["t0"] - 2 / fps, x["t0"], (x["t0"] + x["t1"]) / 2, x["t1"], x["t1"] + 2 / fps]
        for c, t in enumerate(ts):
            t = min(max(0.0, t), n / fps - 1 / fps)
            r = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-ss", f"{t:.4f}", "-i", path, "-frames:v", "1",
                                "-vf", f"scale={tw}:{th}", "-f", "image2pipe", "-vcodec", "png", "-"],
                               capture_output=True, stdin=subprocess.DEVNULL)
            if r.returncode == 0 and r.stdout:
                import io
                fr = Image.open(io.BytesIO(r.stdout)).convert("RGBA")
                bg = Image.new("RGBA", fr.size, (128, 128, 128, 255))
                img.paste(Image.alpha_composite(bg, fr).convert("RGB"), (12 + c * (tw + 8), y + 16))
                d.text((14 + c * (tw + 8), y + 18), f"{t:.2f}s", fill=(255, 255, 0))
        y += th + 34
    img.save(out, quality=88)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video")
    ap.add_argument("--holds", default="", help='intentional stills: "a-b,start:N,end:N" (seconds)')
    ap.add_argument("--min-dead", type=float, default=0.5, help="shortest still that counts as dead (s, default 0.5)")
    ap.add_argument("--strict", action="store_true",
                    help="motion-graphics mode: more than 3 flat frames in a row outside a hold is dead "
                         "(pros keep motion on ~99%% of frames); edits keep the 0.5 s default")
    ap.add_argument("--still-frac", type=float, default=0.003,
                    help="a stretch is still while under this share of pixels differs from its first frame "
                         "(default 0.003 = 0.3%%: a spring's sub-pixel settle stays under it; a small element "
                         "drifting across the frame goes over)")
    ap.add_argument("--level", type=int, default=3, help="grey-level change that counts as a changed pixel (default 3)")
    ap.add_argument("--width", type=int, default=480, help="analysis width in px (default 480)")
    ap.add_argument("--allow-stutter", action="store_true",
                    help="skip the stutter check (source footage with 24p->30p pulldown repeats frames on purpose)")
    ap.add_argument("--sheet", help="write a timeline + flagged-frames image here (needs Pillow)")
    ap.add_argument("--json", help="also write the result as JSON")
    a = ap.parse_args()

    try:
        info, n, fracs, stills = analyse(a.video, a.width, a.level, a.still_frac)
    except Exception as e:  # noqa: BLE001
        print(f"motion_check: cannot read {a.video}: {e}")
        return 2
    fps = info["fps"]
    dur = n / fps
    if a.strict:
        # strict: a frame is flat when almost nothing changed since the previous frame (~0.03% of pixels),
        # so slow drifts still count as motion; more than 3 flat frames in a row is dead
        a.min_dead = 4 / fps
        flat = fracs < 0.0003
        stills, i = [], 0
        while i < len(flat):
            if flat[i]:
                j = i
                while j + 1 < len(flat) and flat[j + 1]:
                    j += 1
                stills.append((i, j + 1))
                i = j + 1
            else:
                i += 1
    holds = parse_holds(a.holds, dur)
    issues = find_issues(fracs, stills, fps, holds, a.min_dead, a.allow_stutter)
    fails = [x for x in issues if x["kind"] not in ("hold", "cadence")]

    print(f"motion_check: {a.video}")
    print(f"  {dur:.2f} s @ {fps:.3f} fps, {n} frames{'  (alpha composited on grey)' if info['alpha'] else ''}")
    for x in issues:
        if x["kind"] == "hold" and x["t1"] - x["t0"] < 0.5:
            continue  # tiny allowed holds (strict mode) are noise
        if x["kind"] == "cadence":
            print(f"  note cadence  {x['count']} repeated frames between {x['t0']:.2f} and {x['t1']:.2f} s keep a regular "
                  f"cadence (a new picture about every {x['every']:g} frames: lower-rate material conformed to "
                  f"{fps:.2f} fps), not stutters")
            continue
        tag = "ok  " if x["kind"] == "hold" else "FAIL"
        what = {"hold": "allowed hold", "dead": "nothing moves",
                "stutter": "repeated frame mid-motion"}[x["kind"]]
        span = f"{x['t0']:.2f}-{x['t1']:.2f} s ({x['t1'] - x['t0']:.2f} s, {x['frames']} frames)"
        print(f"  {tag} {x['kind']:8s}{span}  {what}")
    still_s = sum((e - s + 1) for s, e in stills if (e - s + 1) / fps >= a.min_dead) / fps
    print(f"  still {still_s:.2f} s of {dur:.2f} s (holds included)")
    if a.sheet:
        try:
            make_sheet(a.video, a.sheet, info, fracs, issues, holds)
            print(f"  sheet: {a.sheet}")
        except ImportError:
            print("  sheet skipped: Pillow not installed (pip install pillow)")
    if a.json:
        with open(a.json, "w") as fh:
            json.dump({"video": a.video, "fps": fps, "frames": n, "result": "FAIL" if fails else "PASS",
                       "issues": issues}, fh, indent=2)
    print(f"RESULT: {'FAIL (' + str(len(fails)) + ')' if fails else 'PASS'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
