#!/usr/bin/env python3
"""qa.py - the video-gates QA run: one command, one review folder, every machine check.

    python3 engine/qa.py <video> [--profile NAME] [--kind edit|motion|explainer|loop] [--holds 3.5-4.0,end:1.2]
                         [--cuts 1.5,4.2,... | --shotlist <out dir>/_parts/list.txt | cuts.json] [--max-scene 2.5] [--out <review dir>]
                         [--allow-stutter] [--silences a-b,...] [--size WxH] [--fps N] [--intended end_tail,hook]

Writes <out>/review.md (verdict, fix lines, gate table, shot table, manual checks), <out>/sheet.jpg (timeline,
one frame per shot with the safe area drawn, evidence strips for the worst flags) and <out>/qa.json.

Checks, in one run:
  spec       size, fps, frames, pixel format, audio present against the profile's delivery block; clean decode.
             Accepted rates: delivery.fps and delivery.fps_allowed (or only --fps when given). The rate is the
             average (avg_frame_rate); when that misses but the file declares an accepted standard rate
             (r_frame_rate) within 0.5%, spec is judged on r_frame_rate and the average is a WARN (timestamp gaps)
  motion     engine/motion_check.py (dead stretches, stutters); --strict for --kind motion. Regular repeat cadences
             are a note when they are delivery-rate material in a file at a multiple of that rate (29.97 in 59.94),
             else a WARN (lower-rate material conformed by repeating frames, e.g. 25p in a 29.97 file)
  audio      engine/audio_check.py with the cut list (hard audio cuts), when there is audio
  loudness   integrated LUFS and true peak against delivery.loudness_lufs (+-1 LU) / delivery.true_peak_db
  cuts       ffmpeg scdet cuts against the planned cuts -> unplanned jumps (only when a cut list is given)
  flashes    1-2 frame luma spikes/drops; single foreign frames (a frame unlike both neighbours, which match)
  pops       an element appearing or vanishing in one frame (warning; motion and explainer only)
  clicks     audio sample discontinuities; dropouts (digital silence inside the programme); silence >= 0.5 s
  hook       something moves in the first 0.5 s; a strong moment (cut or big move) by 2 s
  holds      no hold over 0.8 s without life (motion, explainer); static tail / end card <= 1.5 s
  freshness  explainer only: no stretch longer than --max-scene without a new visual: a cut, a scene change (colour
             histogram), or a local state change (a part of the frame that changes and stays changed: a new element,
             a readout or label changing, a box landing; a dot passing through or a steady drift doesn't count)

Every flag is written as a fix line:  f<start>-f<end> (mm:ss.s) - what - why - fix
Text safe-area and over-face checks are listed in review.md as manual checks to do from the sheet.
--cuts none = "no cuts planned" (every detected cut is unplanned). Without --cuts/--shotlist cuts are listed only.
--shotlist list.txt: a listed part that doesn't exist here (a path from another shell, e.g. /sessions/<id>/mnt/...)
is looked for next to the list; qa says so once, and stops naming both paths when neither exists.
--kind loop: a loop or overlay piece (logo swing, corner bug, lower third). Same gates as motion, except the hook
and end-tail gates, which are listed as SKIP with their measurement (a loop has no opening or ending of its own).
--intended end_tail,hook: those gates (hook, hook_motion, hook_strong, end_tail) still run; a failure becomes an
INFO line "declared intended" and is not counted in the verdict. Use it for designed holds (a logo intro holding
its last frame) and pieces not meant to grab a scroll. It is never a silent PASS.
Default --out: ./qa_<video name>/ in the current folder.
Exit code 0 = PASS, 1 = FAIL, 2 = could not read the file.
Needs ffmpeg/ffprobe (scdet, ebur128), numpy, Pillow.
"""
import argparse
import datetime
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import vprofile as prof  # noqa: E402

# ---- thresholds (measured on synthetic clips and the 2026 previews; see tests/test_qa.py) ---------------------
LEVEL = 3               # grey-level change that counts as a changed pixel (same as motion_check)
STILL_FRAC = 0.003      # a stretch is still while < 0.3% of pixels differ from its first frame (same as motion_check)
SCENE_T = 10.0          # ffmpeg scdet threshold for a hard cut
CUT_TOL = 3             # frames: a detected cut within this of a planned cut is the planned cut
FLASH_Y = 20.0          # mean luma (0-255) jump on both sides of a 1-2 frame flash
GLITCH_D = 12.0         # mean abs difference to both neighbours for a foreign frame
STRONG_LEVEL = 12       # a "big move": share of pixels changing by > 12 levels within 0.2 s ...
STRONG_FRAC = 0.20      # ... at least 20% of the picture
NOV_T = 0.008           # freshness: share of the colour histogram that changed within 0.25 s = a new visual
POP_MIN = 0.004         # pop: >= 0.4% of pixels change in one frame while both neighbours are < 20% of that
SILENT_DB = -60.0       # below this (RMS, 5 ms) is silence
DIGITAL_DB = -80.0      # peak below this is digital silence (a dropout when inside the programme)
CLICK_RATIO = 25.0      # click: peak of the 2nd difference >= 25x its RMS within +-10 ms (real mixes stay < 18) ...
CLICK_MIN = 0.05        # ... and >= 0.05 full scale
HOP = 240               # 5 ms at 48 kHz
STD_RATES = (24000 / 1001, 24, 25, 30000 / 1001, 30, 48000 / 1001, 48, 50, 60000 / 1001, 60, 100,
             120000 / 1001, 120)   # constant rates a file can declare in r_frame_rate

SEV_RANK = {"FAIL": 0, "WARN": 1, "INFO": 2}   # INFO: a gate the run declared intended (--intended), not counted
NOTES = []              # run notes for review.md (e.g. concat-list paths resolved next to the list)
ORDER = ["decode", "spec_size", "spec_fps", "flash", "glitch", "unplanned_cut", "dropout", "click", "audio_hard",
         "silence", "dead", "stutter", "cadence", "loudness", "true_peak", "hook_motion", "hook_strong", "hold_life",
         "end_tail", "freshness", "frames", "pix_fmt", "no_audio", "missing_cut", "pop", "edge_silence"]


# ---- small helpers -------------------------------------------------------------------------------------------
def tc(t):
    t = max(0.0, t)
    return f"{int(t // 60):02d}:{t % 60:04.1f}"


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL, **kw)


def parse_spans(spec, dur):
    """'a-b,start:N,end:N' -> [(t0, t1)] seconds (same grammar as motion_check --holds)."""
    out = []
    for part in filter(None, (spec or "").split(",")):
        part = part.strip()
        if part.startswith("end:"):
            out.append((max(0.0, dur - float(part[4:])), dur + 1))
        elif part.startswith("start:"):
            out.append((-1.0, float(part[6:])))
        else:
            a, b = part.split("-")
            out.append((float(a), float(b)))
    return out


def load_cuts(a):
    """Planned cuts in seconds, or None when no plan was given."""
    if a.cuts is not None:
        if a.cuts.strip().lower() in ("none", "-", ""):
            return []
        return sorted(float(x) for x in a.cuts.split(",") if x.strip())
    if a.shotlist:
        if not a.shotlist.lower().endswith(".json"):
            cuts = concat_list_cuts(a.shotlist)
            if cuts is not None:
                return cuts
        with open(a.shotlist) as f:
            j = json.load(f)
        if isinstance(j, dict) and "items" in j and not any(k in j for k in ("cuts", "starts", "shots")):
            raise SystemExit(f"qa: {a.shotlist} is an edit list (items with in/out), whose reel times depend on the "
                             "renderer (open, cards, replays). Pass the render's concat list instead: "
                             "--shotlist <out dir>/_parts/list.txt (or --cuts).")
        if isinstance(j, list):
            return sorted(float(x) for x in j)
        if "cuts" in j:
            return sorted(float(x) for x in j["cuts"])
        if "starts" in j:
            return sorted(float(x) for x in j["starts"] if float(x) > 0.01)
        if "shots" in j and j["shots"] and isinstance(j["shots"][0], dict):
            for k in ("start", "t0", "t"):
                if k in j["shots"][0]:
                    return sorted(float(s[k]) for s in j["shots"] if float(s[k]) > 0.01)
        raise SystemExit(f"qa: {a.shotlist}: no cut times found (want a list, or 'cuts', 'starts' or shots[].start)")
    return None


# ---- probe -----------------------------------------------------------------------------------------------------
def concat_list_cuts(path):
    """Cut times from an ffmpeg concat list (e.g. render_reel/vreel '_parts/list.txt'): the running sum of the
    parts' durations, without the end of the last part. None when the file is not a concat list.
    render_reel/vreel write the absolute part paths of the shell that rendered (e.g. /sessions/<id>/mnt/... in the
    device shell) and only rewrite the list when concat.mp4 is missing, so a listed path may not exist here: then
    the part is looked for next to the list (<list dir>/<file name>), and that is said once."""
    files, durs = [], {}
    base = os.path.dirname(os.path.abspath(path))
    with open(path, errors="replace") as f:
        for line in f:
            s = line.strip()
            m = re.match(r"file\s+'(.*)'$", s) or re.match(r"file\s+(\S+)$", s)
            if m:
                p = m.group(1).replace("'\\''", "'")
                files.append(p if os.path.isabs(p) else os.path.join(base, p))
            elif s.startswith("duration ") and files:
                durs[len(files) - 1] = float(s.split()[1])
    if not files:
        return None
    moved = 0
    for i, p in enumerate(files[:-1]):
        if durs.get(i) is not None or os.path.exists(p):
            continue
        alt = os.path.join(base, os.path.basename(p))
        if not os.path.exists(alt):
            raise SystemExit(f"qa: {path}: part {i + 1} not found, neither as listed ({p}) nor next to the list "
                             f"({alt}). Pass --cuts instead, or re-render the parts.")
        files[i] = alt
        moved += 1
    if moved:
        NOTES.append(f"{os.path.basename(path)}: {moved} part path(s) in the list don't exist on this machine "
                     f"(written by another shell?); used the parts next to the list in {base}")
        print(f"qa: note: {NOTES[-1]}")
    t, cuts = 0.0, []
    for i, p in enumerate(files[:-1]):
        d = durs.get(i)
        if d is None:
            r = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p])
            if r.returncode != 0 or not r.stdout.strip():
                raise SystemExit(f"qa: {path}: cannot read the duration of part {p}")
            d = float(r.stdout.strip())
        t += d
        cuts.append(round(t, 3))
    return cuts


def probe(path):
    r = run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", path])
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or "ffprobe failed")
    j = json.loads(r.stdout)
    vs = [s for s in j.get("streams", []) if s.get("codec_type") == "video"
          and not s.get("disposition", {}).get("attached_pic")]
    if not vs:
        raise RuntimeError("no video stream")
    v = vs[0]
    aus = [s for s in j.get("streams", []) if s.get("codec_type") == "audio"]

    def rate(s):
        try:
            n, d = s.split("/")
            return float(n) / float(d) if float(d) else 0.0
        except (ValueError, AttributeError):
            return 0.0
    avg, rr = rate(v.get("avg_frame_rate")), rate(v.get("r_frame_rate"))
    fps = avg or rr or 30.0
    pf = v.get("pix_fmt", "")
    return {"w": int(v["width"]), "h": int(v["height"]), "fps": fps, "pix_fmt": pf, "codec": v.get("codec_name"),
            "avg_fps": avg, "r_fps": rr, "r_fps_str": v.get("r_frame_rate"),
            "fps_str": v.get("avg_frame_rate") or v.get("r_frame_rate"),
            "nb_frames": int(v["nb_frames"]) if str(v.get("nb_frames", "")).isdigit() else None,
            "alpha": pf.startswith(("yuva", "rgba", "argb", "bgra", "abgr", "gbrap", "ya")),
            "dur": float(j.get("format", {}).get("duration", 0) or 0),
            "audio": bool(aus), "a_codec": aus[0].get("codec_name") if aus else None,
            "a_rate": int(aus[0].get("sample_rate", 0)) if aus else 0,
            "a_ch": int(aus[0].get("channels", 0)) if aus else 0}


# ---- video pass ------------------------------------------------------------------------------------------------
def analyse_video(path, info, width, tmp, keep_small=False):
    """One decode: per-frame stats from a small yuv444 copy, plus ffmpeg scdet scores from the same graph."""
    w = max(2, width - width % 2)
    h = max(2, int(round(info["h"] * w / info["w"])) // 2 * 2)
    meta = os.path.join(tmp, "scdet.txt")
    if info["alpha"]:   # composite on mid grey so an alpha-only fade still reads as change
        head = (f"color=c=0x808080:s={w}x{h}:r={info['fps']}[bg];[0:v]scale={w}:{h},format=rgba[fg];"
                f"[bg][fg]overlay=shortest=1")
    else:
        head = f"[0:v]scale={w}:{h}"
    graph = (f"{head},split=2[o][s];[s]format=yuv420p,scdet=threshold={SCENE_T},"
             f"metadata=mode=print:file='{meta}',nullsink;[o]format=yuv444p[out]")
    errf = open(os.path.join(tmp, "decode_err.txt"), "w+")
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-nostdin", "-i", path, "-filter_complex", graph, "-map", "[out]",
                          "-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", "yuv444p", "-"],
                         stdout=subprocess.PIPE, stderr=errf, stdin=subprocess.DEVNULL)
    plane = w * h
    size = plane * 3
    k_strong = max(1, int(round(0.2 * info["fps"])))
    k_nov = max(1, int(round(0.25 * info["fps"])))
    Y, mad1, madskip, cfrac, dup, strong, nov = [], [], [], [], [], [], []
    small = []                                    # 128-px-wide luma frames for the local freshness measure (E6)
    sx_idx = np.linspace(0, w - 1, min(w, 128)).astype(int)
    sy_idx = np.linspace(0, h - 1, max(2, int(round(min(w, 128) * h / w)))).astype(int)
    stills = []
    ring_y, ring_h = [], []
    prev = prev2 = anchor = None
    a_idx = n = 0
    while True:
        buf = p.stdout.read(size)
        if len(buf) < size:
            break
        arr = np.frombuffer(buf, np.uint8)
        y8 = arr[:plane]
        f = y8.astype(np.int16)
        Y.append(float(f.mean()))
        hist = np.concatenate([np.bincount(arr[i * plane:(i + 1) * plane] >> 3, minlength=32) for i in range(3)])
        hist = hist / float(plane)
        if prev is not None:
            d = np.abs(f - prev)
            mad1.append(float(d.mean()))
            cfrac.append(float((d > LEVEL).mean()))
            dup.append(bool(d.max() == 0))
            if float((np.abs(f - anchor) > LEVEL).mean()) >= STILL_FRAC:
                if n - 1 > a_idx:
                    stills.append((a_idx, n - 1))
                anchor, a_idx = f, n
        else:
            mad1.append(0.0); cfrac.append(0.0); dup.append(False)
            anchor = f
        madskip.append(float(np.abs(f - prev2).mean()) if prev2 is not None else 0.0)
        ring_y.append(f); ring_h.append(hist)
        if len(ring_y) > k_strong + 1:
            ring_y.pop(0)
        if len(ring_h) > k_nov + 1:
            ring_h.pop(0)
        strong.append(float((np.abs(f - ring_y[0]) > STRONG_LEVEL).mean()) if len(ring_y) > 1 else 0.0)
        if keep_small:                            # explainer only: ~9 KB a frame (uint8)
            small.append(y8.reshape(h, w)[np.ix_(sy_idx, sx_idx)].copy())
        nov.append(float(np.abs(hist - ring_h[0]).sum() / 6.0) if len(ring_h) > 1 else 0.0)
        prev2, prev = prev, f
        n += 1
    p.wait()
    errf.seek(0)
    errors = [ln for ln in errf.read().splitlines() if ln.strip()]
    errf.close()
    if n < 2:
        raise RuntimeError("fewer than 2 frames decoded" + (": " + errors[0] if errors else ""))
    if n - 1 > a_idx:
        stills.append((a_idx, n - 1))
    score = np.zeros(n)
    try:
        fr = None
        with open(meta) as fh:
            for ln in fh:
                m = re.match(r"frame:(\d+)", ln)
                if m:
                    fr = int(m.group(1)); continue
                m = re.match(r"lavfi\.scd\.score=([\d.]+)", ln)
                if m and fr is not None and fr < n:
                    score[fr] = float(m.group(1))
    except OSError:
        errors.append("scdet produced no scores")
    return {"n": n, "w": w, "h": h, "Y": np.array(Y), "mad1": np.array(mad1), "madskip": np.array(madskip),
            "c": np.array(cfrac), "dup": np.array(dup), "strong": np.array(strong), "nov": np.array(nov),
            "score": score, "stills": stills, "errors": errors, "small": small}


# ---- audio pass ------------------------------------------------------------------------------------------------
def analyse_audio(path, tmp):
    """One decode: ebur128 (integrated, true peak, LRA) on the way, then 5 ms windows of level, peak and clicks."""
    errp = os.path.join(tmp, "ebur128.txt")
    errf = open(errp, "w")
    p = subprocess.Popen(["ffmpeg", "-nostdin", "-hide_banner", "-nostats", "-i", path, "-vn", "-af",
                          "ebur128=peak=true:framelog=verbose,"
                          "aformat=sample_fmts=flt:sample_rates=48000:channel_layouts=stereo",
                          "-f", "f32le", "-"], stdout=subprocess.PIPE, stderr=errf, stdin=subprocess.DEVNULL)
    chunk = HOP * 200
    db, peak, cr, cmax = [], [], [], []
    ctx = 2 * HOP                                            # click context: +-10 ms around the peak sample
    tail = np.zeros((0, 2), np.float64)                     # last 2 samples, for the 2nd difference
    dtail = np.zeros((0, 2), np.float64)                    # last `ctx` 2nd-difference samples, for context
    rest = b""
    while True:
        buf = p.stdout.read(chunk * 8)
        if not buf:
            break
        buf = rest + buf
        usable = len(buf) // (HOP * 8) * (HOP * 8)
        rest = buf[usable:]
        if not usable:
            continue
        x = np.frombuffer(buf[:usable], np.float32).reshape(-1, 2).astype(np.float64)
        m = len(x) // HOP
        xx = x.reshape(m, HOP, 2)
        db.extend(10 * np.log10((xx ** 2).mean(axis=(1, 2)) + 1e-14))
        peak.extend(20 * np.log10(np.abs(xx).max(axis=(1, 2)) + 1e-12))
        ext = np.concatenate([tail, x])
        d2 = np.abs(ext[2:] - 2 * ext[1:-1] + ext[:-2]) if len(ext) > 2 else np.zeros((0, 2))
        d2 = np.concatenate([np.zeros((len(x) - len(d2), 2)), d2])   # first samples of the file: no history
        D = np.concatenate([dtail, d2])
        pre = len(dtail)
        cs = np.concatenate([np.zeros((1, 2)), np.cumsum(D ** 2, axis=0)])
        win = d2.reshape(m, HOP, 2)
        j = pre + np.arange(m)[:, None] * HOP + win.argmax(axis=1)            # (m, 2) peak sample index in D
        mx = win.max(axis=1)
        lo, hi = np.maximum(0, j - ctx), np.minimum(len(D), j + ctx)
        a0, a1 = np.maximum(lo, j - 4), np.minimum(hi, j + 5)
        col = np.arange(2)[None, :]
        tot = cs[hi, col] - cs[lo, col] - (cs[a1, col] - cs[a0, col])
        cnt = (hi - lo) - (a1 - a0)
        ratio = mx / (np.sqrt(tot / np.maximum(cnt, 1)) + 1e-9)
        best = ratio.argmax(axis=1)
        cr.extend(ratio[np.arange(m), best])
        cmax.extend(mx[np.arange(m), best])
        tail = x[-2:]
        dtail = D[-ctx:]
    p.wait()
    errf.close()
    with open(errp, errors="replace") as fh:
        log = fh.read()
    loud = {}
    summ = log[log.rfind("Summary:"):] if "Summary:" in log else ""
    for key, pat in (("I", r"I:\s+(-?[\d.]+|-inf) LUFS"), ("LRA", r"LRA:\s+(-?[\d.]+) LU"),
                     ("TP", r"True peak:\s+Peak:\s+(-?[\d.]+|-inf) dBFS")):
        m = re.search(pat, summ, re.S)
        if m:
            loud[key] = float(m.group(1)) if m.group(1) != "-inf" else float("-inf")
    return {"db": np.array(db), "peak": np.array(peak), "click_ratio": np.array(cr), "click_max": np.array(cmax),
            "loud": loud, "hop_s": HOP / 48000.0}


def runs(mask):
    """[(start, end_inclusive)] of True runs."""
    out, i, n = [], 0, len(mask)
    while i < n:
        if mask[i]:
            j = i
            while j + 1 < n and mask[j + 1]:
                j += 1
            out.append((i, j)); i = j + 1
        else:
            i += 1
    return out


# ---- the gates -------------------------------------------------------------------------------------------------
class Review:
    def __init__(self, fps, n):
        self.fps, self.n = fps, n
        self.flags, self.gates = [], []

    def f(self, t):
        return int(round(t * self.fps))

    def flag(self, kind, sev, f0, f1, what, why, fix, gate, extra=None):
        f0, f1 = max(0, int(f0)), max(int(f0), int(f1))
        d = {"kind": kind, "sev": sev, "f0": f0, "f1": f1, "t0": round(f0 / self.fps, 3),
             "t1": round((f1 + 1) / self.fps, 3), "what": what, "why": why, "fix": fix, "gate": gate}
        if extra:
            d.update(extra)
        self.flags.append(d)
        return d

    def gate(self, name, result, measured, target):
        self.gates.append({"gate": name, "result": result, "measured": measured, "target": target})

    def line(self, x):
        return f"f{x['f0']}-f{x['f1']} ({tc(x['t0'])}) - {x['what']} - {x['why']} - {x['fix']}"

    def sorted_flags(self):
        return sorted(self.flags, key=lambda x: (SEV_RANK[x["sev"]], ORDER.index(x["kind"])
                                                 if x["kind"] in ORDER else 99, x["f0"]))


def gate_spec(R, info, V, P, a, kind):
    fails = warns = 0
    meas, tgt = [], []
    sizes = {}
    size_ok = None
    if a.size:
        sizes[a.size] = "given"
    elif P is not None:
        for key, label in (("delivery.size", "delivery"), ("delivery.vertical_size", "vertical")):
            v = P.get(key, None)
            if v:
                sizes[v] = label
        pv = P.get("delivery.preview", {}) or {}
        land = str(pv.get("landscape", "")).rstrip("p")
        if land.isdigit():
            sizes[f"{int(land) * 16 // 9}x{land}"] = "preview"
        if str(pv.get("vertical_width", "")).isdigit():
            vw = int(pv["vertical_width"]); sizes[f"{vw}x{vw * 16 // 9}"] = "preview"
    got = f"{info['w']}x{info['h']}"
    meas.append(got)
    if sizes:
        tgt.append(" or ".join(k for k, v in sizes.items() if v != "preview"))
        label = sizes.get(got)
        if label is None:
            fails += 1
            want = next(k for k, v in sizes.items() if v != "preview")
            R.flag("spec_size", "FAIL", 0, R.n - 1, f"frame size {got}, profile delivers {tgt[-1]}",
                   "platforms rescale it and text and safe areas move", f"re-render at {want}", "spec")
        elif label == "preview":
            warns += 1
            R.flag("spec_size", "WARN", 0, R.n - 1, f"frame size {got} is the preview size",
                   "fine for review, not for delivery", "deliver the full-size render", "spec")
    # expected file rates: --fps alone when given, else delivery.fps plus delivery.fps_allowed (other rates the
    # profile delivers, e.g. 59.94 reels made of 29.97 material shown at 2x)
    if a.fps:
        rates = [float(a.fps)]
    elif P is not None and P.get("delivery.fps", None):
        extra = P.get("delivery.fps_allowed", []) or []
        if not isinstance(extra, (list, tuple)):
            extra = [extra]                              # a single rate written without the list brackets
        try:
            extra = [float(x) for x in extra]
        except (TypeError, ValueError):
            print(f"qa: profile {P.name}: delivery.fps_allowed should be a list of frame rates, e.g. "
                  f"[59.94005994] (got {P.get('delivery.fps_allowed')!r})", file=sys.stderr)
            raise SystemExit(2)
        rates = [float(P.get("delivery.fps"))] + extra
    else:
        rates = []
    # the rate the spec is judged on: avg_frame_rate (frames / duration). When that misses every expected rate but
    # the file declares a standard constant rate (r_frame_rate) that is expected and that the average misses by
    # under 0.5%, the difference is timestamp gaps or uneven frame durations, not a different rate: the spec is
    # judged on r_frame_rate and the average stays visible as a WARN (a real problem to look at, not hidden).
    spec_fps, avg_note = info["fps"], None
    rr, av = info.get("r_fps") or 0.0, info.get("avg_fps") or 0.0

    def hit(x):
        return any(abs(x - w) <= 0.01 for w in rates)
    if rates and av and rr and not hit(av) and hit(rr) and abs(av / rr - 1) < 0.005 and \
            any(abs(rr / s_ - 1) < 1e-4 for s_ in STD_RATES):
        spec_fps, avg_note = rr, av
    meas.append(f"{spec_fps:.3f} fps" + (f" (r_frame_rate; average {avg_note:.3f})" if avg_note else ""))
    if rates:
        tgt.append(" or ".join(f"{x:.3f}" for x in rates) + " fps")
        if not hit(spec_fps):
            fails += 1
            want = " or ".join(f"{x:.3f}" for x in rates)
            R.flag("spec_fps", "FAIL", 0, R.n - 1, f"{spec_fps:.3f} fps, profile delivers {want}",
                   "a rate conform at upload drops or repeats frames", f"render at {rates[0]:.3f} fps", "spec")
    if avg_note:
        warns += 1
        R.flag("spec_fps", "WARN", 0, R.n - 1,
               f"average frame rate {avg_note:.3f} fps ({info['fps_str']}) in a file flagged {info['r_fps_str']} "
               f"({rr:.3f} fps): about {abs(rr - avg_note) * R.n / avg_note:.0f} frame(s) of timestamp gaps or "
               "uneven frame durations", "players may hitch where frames are missing or held",
               "check the joins of the parts (stutter flags show where) and re-mux or re-render at a constant rate",
               "spec")
    meas.append(f"{V['n']} frames")
    if info["nb_frames"] and abs(info["nb_frames"] - V["n"]) > 1:
        warns += 1
        R.flag("frames", "WARN", 0, R.n - 1, f"container says {info['nb_frames']} frames, {V['n']} decoded",
               "frames may be missing or the file was cut short", "re-export the file", "spec")
    meas.append(info["pix_fmt"])
    want_pf = P.get("delivery.pix_fmt", "yuv420p") if P is not None else "yuv420p"   # generic default
    if not info["alpha"] and info["pix_fmt"] != want_pf:
        warns += 1
        R.flag("pix_fmt", "WARN", 0, R.n - 1, f"pixel format {info['pix_fmt']}, delivery uses {want_pf}",
               "some players and platforms reject or shift colours", f"encode with -pix_fmt {want_pf}", "spec")
    meas.append("audio" if info["audio"] else "no audio")
    if not info["audio"] and kind not in ("motion", "loop"):
        warns += 1
        R.flag("no_audio", "WARN", 0, R.n - 1, "no audio stream", "an edit or explainer is expected to have sound",
               "mux the mix in (or run with --kind motion for a silent overlay)", "spec")
    if V["errors"]:
        fails += 1
        R.flag("decode", "FAIL", 0, R.n - 1, f"{len(V['errors'])} decode errors (first: {V['errors'][0][:80]})",
               "a damaged file glitches on some players", "re-export from the timeline", "spec")
    R.gate("integrity and spec", "FAIL" if fails else ("WARN" if warns else "PASS"), ", ".join(meas),
           ", ".join(tgt) or "no delivery spec in profile")


def gate_motion(R, a, kind, out_dir, video, info=None, P=None):
    cmd = [sys.executable, os.path.join(HERE, "motion_check.py"), video, "--json", os.path.join(out_dir, "_motion.json")]
    if a.holds:
        cmd += ["--holds", a.holds]
    if kind in ("motion", "loop"):
        cmd.append("--strict")
    if a.allow_stutter:
        cmd.append("--allow-stutter")
    r = run(cmd)
    res = {"cmd": " ".join(["motion_check.py"] + cmd[2:]), "rc": r.returncode, "stdout": r.stdout.strip()}
    jp = os.path.join(out_dir, "_motion.json")
    if r.returncode == 2 or not os.path.isfile(jp):
        R.gate("motion (motion_check)", "SKIP", "motion_check could not run", "no dead stretch, no stutter")
        return res
    with open(jp) as fh:
        j = json.load(fh)
    os.remove(jp)
    nd = ns = 0
    cad = None
    for x in j["issues"]:
        f0, f1 = R.f(x["t0"]), R.f(x["t1"]) - 1
        if x["kind"] == "dead":
            nd += 1
            R.flag("dead", "FAIL", f0, f1, f"nothing moves for {x['t1'] - x['t0']:.2f} s",
                   "dead air: the eye leaves when the picture stops",
                   "add motion (a 2-4% push-in or a spring move), trim it under 0.5 s, or declare it with --holds",
                   "motion")
        elif x["kind"] == "stutter":
            ns += 1
            R.flag("stutter", "FAIL", f0, f1, f"{x['frames']} repeated frame(s) mid-motion",
                   "a visible hitch", "re-render this range; check the frame-rate conform (or --allow-stutter for "
                   "24p source on purpose)", "motion")
        elif x["kind"] == "cadence":
            cad = x   # regular pulldown / conform repeats: one note, not stutters
    # a cadence is fine when it is delivery-rate material in a file at a multiple of that rate (29.97 material in a
    # 59.94 file: every picture shown twice). Any other cadence means lower-rate material was conformed by repeating
    # frames (e.g. 25p in a 29.97 file: a repeat every ~6 frames), which judders on screen: a render/conform problem
    # worth a look (WARN, not FAIL). In a file AT the delivery rate every cadence is that case. The reference is the
    # profile's delivery.fps (the picture rate the piece is made at; --fps only sets the expected file rate), or --fps
    # when the profile has none.
    deliv = P.get("delivery.fps", None) if P is not None else None
    deliv = float(deliv) if deliv else (float(a.fps) if a.fps else None)
    cad_warn = bool(cad and deliv and info and abs(info["fps"] / cad["every"] / deliv - 1) > 0.01)
    if cad_warn:
        same = abs(info["fps"] - deliv) <= 0.01
        R.flag("cadence", "WARN", R.f(cad["t0"]), R.f(cad["t1"]) - 1,
               f"{cad['count']} repeated frames on a regular cadence (a new picture every ~{cad['every']:g} frames: "
               f"~{info['fps'] / cad['every']:.2f} fps material) in a {info['fps']:.3f} fps file"
               + (", the delivery rate" if same else f", delivery {deliv:.3f} fps"),
               "lower-rate material conformed by repeating frames judders on screen",
               f"conform the source to {deliv:.3f} fps with frame blending or optical flow (or shoot/render it at that "
               f"rate), then re-render", "motion")
    R.gate("motion (motion_check" + (" --strict" if kind in ("motion", "loop") else "") + ")",
           "FAIL" if nd + ns else ("WARN" if cad_warn else "PASS"), f"{nd} dead, {ns} stutter" +
           (f", {cad['count']} repeats on a regular cadence (a new picture every ~{cad['every']:g} frames; " +
            ("not delivery-rate material: a conform judder)" if cad_warn else "not stutters)") if cad else ""),
           "no dead stretch, no stutter")
    return res


def gate_audio_check(R, video, cut_times, P):
    cmd = [sys.executable, os.path.join(HERE, "audio_check.py"), video]
    if cut_times:
        cmd += ["--cuts", ",".join(f"{c:.3f}" for c in cut_times)]
    r = run(cmd)
    out = (r.stdout + r.stderr).strip()
    hits = re.findall(r"([\d.]+)s (drop|cut) (-?[\d.]+)dB", r.stdout)
    fade = int(P.get("style.audio_fade_ms", 40)) if P is not None else 40
    for t, k, d in hits:
        t = float(t)
        f0 = R.f(t)
        R.flag("audio_hard", "FAIL", f0, f0 + 1, f"hard audio {'cut-off' if k == 'drop' else 'jump at a cut'} "
               f"({d} dB in 10 ms)", "an audible chop; the house rule is that everything fades",
               f"add a fade of at least {fade} ms there (crossfade across the cut)", "audio_check")
    res = "FAIL" if r.returncode == 1 else ("PASS" if r.returncode == 0 else "SKIP")
    R.gate("hard audio cuts (audio_check)", res,
           f"{len(hits)} hard changes, {len(cut_times or [])} cut points" if res != "SKIP" else
           (r.stdout.strip().splitlines() or ["audio_check could not run"])[0][:120], "every change fades")
    return {"cmd": " ".join(["audio_check.py"] + cmd[2:]), "rc": r.returncode, "stdout": out}


def gate_loudness(R, A, P):
    target = float(P.get("delivery.loudness_lufs", -14)) if P is not None else -14.0
    tp_max = float(P.get("delivery.true_peak_db", -1)) if P is not None else -1.0
    L = A["loud"]
    I, TP = L.get("I"), L.get("TP")
    if I is None:
        R.gate("loudness", "SKIP", "ebur128 gave no reading", f"{target:g} LUFS +-1")
        return
    if abs(I - target) > 1.0:
        R.flag("loudness", "FAIL", 0, R.n - 1, f"integrated {I:.1f} LUFS, target {target:g} +-1",
               "too quiet: it sounds weak next to everything else in the feed" if I < target else
               "too loud: platforms turn it down and the limiter squashes it",
               f"apply {target - I:+.1f} dB (2-pass loudnorm I={target:g}:TP={tp_max:g})", "loudness")
    R.gate("loudness", "FAIL" if abs(I - target) > 1.0 else "PASS", f"{I:.1f} LUFS, LRA {L.get('LRA', 0):.1f} LU",
           f"{target:g} LUFS +-1")
    if TP is None:
        return
    sev = "FAIL" if TP > tp_max + 1.0 else ("WARN" if TP > tp_max + 0.05 else None)
    if sev:
        R.flag("true_peak", sev, 0, R.n - 1, f"true peak {TP:.1f} dBTP, max {tp_max:g}",
               "inter-sample overs distort after the platform's encode",
               f"limit the true peak to {tp_max:g} dBTP (loudnorm TP={tp_max:g})", "loudness")
    R.gate("true peak", sev or "PASS", f"{TP:.1f} dBTP", f"<= {tp_max:g} dBTP")


def gate_audio_faults(R, A, silences):
    hop = A["hop_s"]
    db, pk = A["db"], A["peak"]
    if not len(db):
        R.gate("clicks, dropouts, silence", "SKIP", "no audio decoded", "none")
        return
    loud = np.where(db > SILENT_DB)[0]
    if not len(loud):
        R.gate("clicks, dropouts, silence", "FAIL", "the whole track is silent", "programme audio")
        R.flag("silence", "FAIL", 0, R.n - 1, "the audio track is silent", "nothing to hear",
               "mux the mix in", "audio")
        return
    p0, p1 = loud[0], loud[-1]

    def planned(t0, t1):
        return any(a <= t0 + 0.05 and t1 <= b + 0.05 for a, b in silences)
    nd = nc = ns = 0
    digital = pk < DIGITAL_DB
    quiet = db < SILENT_DB
    for s, e in runs(quiet):
        t0, t1 = s * hop, (e + 1) * hop
        dur = t1 - t0
        inside = s > p0 and e < p1
        if planned(t0, t1):
            continue
        if inside and digital[s:e + 1].sum() >= 2:
            nd += 1
            R.flag("dropout", "FAIL", R.f(t0), R.f(t1) - 1, f"audio dropout: {dur:.2f} s of digital silence",
                   "the sound vanishes mid-programme", "fill the gap from the source or crossfade across it",
                   "audio", {"dur": round(dur, 3)})
        elif inside and dur >= 0.5:
            ns += 1
            R.flag("silence", "FAIL", R.f(t0), R.f(t1) - 1, f"{dur:.2f} s of silence (below {SILENT_DB:g} dBFS)",
                   "dead air", "bring the bed or room tone under it, or declare it with --silences", "audio")
        elif not inside and dur >= 0.5:
            R.flag("edge_silence", "WARN", R.f(t0), R.f(t1) - 1,
                   f"{dur:.2f} s of silence at the {'head' if s <= p0 else 'tail'}",
                   "the picture plays without sound", "start the sound with the picture or trim the "
                   + ("head" if s <= p0 else "tail"), "audio")
    cl = np.where((A["click_ratio"] >= CLICK_RATIO) & (A["click_max"] >= CLICK_MIN) & (db > SILENT_DB - 20))[0]
    last = -10
    for i in cl:
        if i - last <= 2:
            last = i; continue
        last = i
        t = i * hop
        if planned(t, t):
            continue
        nc += 1
        f0 = R.f(t)
        R.flag("click", "FAIL", f0, f0, f"audio click (sample jump {A['click_max'][i]:.2f}, "
               f"{A['click_ratio'][i]:.0f}x the local level)", "an audible tick",
               "find the edit point or the clipped sample; add a 5-10 ms crossfade or de-click it", "audio",
               {"t_exact": round(t, 4)})
    R.gate("clicks, dropouts, silence", "FAIL" if nd + nc + ns else "PASS",
           f"{nc} clicks, {nd} dropouts, {ns} silences", "none inside the programme")


def detect_cuts(V):
    """Group scdet hits; return [(frame, score)] for the first frame of each new shot."""
    hits = np.where(V["score"] >= SCENE_T)[0]
    groups = []
    for i in hits:
        if groups and i - groups[-1][-1] <= 2:
            groups[-1].append(int(i))
        else:
            groups.append([int(i)])
    return [(g[0], float(V["score"][g].max()), g) for g in groups]


def gate_flashes(R, V, planned_f):
    Y, m1, ms, n = V["Y"], V["mad1"], V["madskip"], V["n"]
    events = []
    near_plan = lambda i: any(abs(i - p) <= CUT_TOL for p in planned_f)  # noqa: E731
    i = 1
    while i < n - 1:
        hit = None
        a, b = Y[i] - Y[i - 1], Y[i] - Y[i + 1]
        if abs(a) >= FLASH_Y and abs(b) >= FLASH_Y and np.sign(a) == np.sign(b) and \
                abs(Y[i + 1] - Y[i - 1]) <= 0.5 * min(abs(a), abs(b)):
            hit = ("flash", i, i, a)
        elif i < n - 2:
            a, b = Y[i] - Y[i - 1], Y[i + 1] - Y[i + 2]
            if abs(a) >= FLASH_Y and abs(b) >= FLASH_Y and np.sign(a) == np.sign(b) and \
                    abs(Y[i + 1] - Y[i]) < 0.5 * min(abs(a), abs(b)) and \
                    abs(Y[i + 2] - Y[i - 1]) <= 0.5 * min(abs(a), abs(b)):
                hit = ("flash", i, i + 1, a)
        if hit is None and m1[i] >= GLITCH_D and m1[i + 1] >= GLITCH_D and \
                ms[i + 1] <= 0.3 * min(m1[i], m1[i + 1]):
            hit = ("glitch", i, i, m1[i])
        if hit:
            kind, s, e, mag = hit
            planned = near_plan(s)
            events.append({"kind": kind, "f0": s, "f1": e, "mag": float(mag), "planned": planned})
            if not planned:
                if kind == "flash":
                    R.flag("flash", "FAIL", s, e, f"{e - s + 1}-frame {'white' if mag > 0 else 'black'} flash "
                           f"(luma {mag:+.0f} against both neighbours)",
                           "reads as a glitch and is a photosensitivity risk",
                           f"replace f{s}-f{e} with f{s - 1} (or move the flash onto a planned cut)", "flashes")
                else:
                    R.flag("glitch", "FAIL", s, e, f"single foreign frame (differs from both neighbours by "
                           f"{mag:.0f}, they match each other)", "a stray frame from another shot or a render seam",
                           f"delete f{s} or fix the edit point", "flashes")
            i = e + 2
        else:
            i += 1
    nf = sum(1 for x in events if not x["planned"])
    R.gate("flashes and foreign frames", "FAIL" if nf else "PASS",
           f"{nf} unplanned" + (f", {len(events) - nf} on planned cuts" if len(events) > nf else ""), "none")
    return events


def gate_cuts(R, V, cuts, planned, flash_events):
    """cuts: [(frame, score, group)]. planned: list of frames or None."""
    in_flash = set()
    for x in flash_events:
        # a foreign or flash frame makes two scdet hits; they are that event, not cuts (unless the shot changes
        # across a 1-frame flash: then it is a flash cut and the cut stays)
        same_shot = x["f1"] > x["f0"] or \
            V["madskip"][min(x["f0"] + 1, V["n"] - 1)] <= 0.3 * max(1e-6, V["mad1"][x["f0"]])
        if x["kind"] == "glitch" or (x["kind"] == "flash" and not x["planned"] and same_shot):
            in_flash.update(range(x["f0"], x["f1"] + 2))
    real = [c for c in cuts if not set(c[2]) <= in_flash]
    table = []
    for f0, sc, _ in real:
        p = None if planned is None else next((q for q in planned if abs(q - f0) <= CUT_TOL), None)
        table.append({"frame": f0, "t": round(f0 / R.fps, 3), "score": round(sc, 1),
                      "planned": None if planned is None else p is not None,
                      "offset": None if p is None else f0 - p})
    if planned is None:
        R.gate("cuts vs plan", "SKIP", f"{len(real)} cuts detected", "pass --cuts or --shotlist to check")
        return table
    nu = 0
    for row in table:
        if not row["planned"]:
            nu += 1
            f = row["frame"]
            R.flag("unplanned_cut", "FAIL", max(0, f - 1), f, f"hard cut not in the cut list (scdet {row['score']})",
                   "a jump the plan didn't ask for: wrong in-point, missing frames or a render seam",
                   f"check the edit at f{f}; if intended add {f / R.fps:.3f} to the cut list, else close the gap",
                   "cuts")
    nm = 0
    for q in planned:
        if not any(abs(row["frame"] - q) <= CUT_TOL for row in table):
            nm += 1
            R.flag("missing_cut", "WARN", q, q, "planned cut not detected as a hard cut",
                   "a soft cut, a dissolve, or the cut is missing from the render",
                   "check the edit at this frame by eye", "cuts")
    R.gate("cuts vs plan", "FAIL" if nu else ("WARN" if nm else "PASS"),
           f"{len(table)} detected, {nu} unplanned, {nm} planned not found", f"{len(planned)} planned cuts")
    return table


def gate_pops(R, V, cuts, flash_events):
    c, n = V["c"], V["n"]
    cutf = {f for _, _, g in cuts for f in g}
    busy = {f for x in flash_events for f in range(x["f0"], x["f1"] + 2)}
    k = 0
    for i in range(1, n - 1):
        if c[i] >= POP_MIN and c[i - 1] < 0.2 * c[i] and c[i + 1] < 0.2 * c[i] and i not in cutf and i not in busy:
            k += 1
            if k <= 20:
                R.flag("pop", "WARN", i, i, f"{c[i] * 100:.1f}% of the picture changes in one frame",
                       "an element appears or vanishes with no move (G1: nothing grows from zero or pops on)",
                       "bring it in on a spring from oversize or off-frame, 6-10 frames", "pops")
    R.gate("pops", "WARN" if k else "PASS", f"{k} one-frame pops", "none (warning only)")


# --intended names -> the flag kinds they cover (gates that no --holds / --cuts / --silences can declare)
INTENDED = {"hook": ("hook_motion", "hook_strong"), "hook_motion": ("hook_motion",),
            "hook_strong": ("hook_strong",), "end_tail": ("end_tail",)}
LOOP_SKIP = "not gated for --kind loop (a loop or overlay has no opening or ending of its own)"


def parse_intended(spec):
    out = set()
    for name in filter(None, (x.strip() for x in (spec or "").split(","))):
        if name not in INTENDED:
            raise SystemExit(f"qa: --intended {name!r}: not a gate that can be declared intended "
                             f"(choose from {', '.join(INTENDED)}; planned stills, cuts and silences go in "
                             "--holds, --cuts and --silences)")
        out.update(INTENDED[name])
    return out


def _fail_or_intended(R, fkind, gate, f0, f1, what, why, fix, gname, measured, target, intended):
    """A failing hook/tail gate: a FAIL, or an INFO line when the run declared it intended (never a silent PASS)."""
    if fkind in intended:
        R.flag(fkind, "INFO", f0, f1, what + f" (declared intended: --intended {fkind})", why,
               "none: declared intended (drop it from --intended to gate it again)", gate)
        R.gate(gname, "INFO", measured, target + f"; declared intended (--intended {fkind}), not counted")
    else:
        R.flag(fkind, "FAIL", f0, f1, what, why, fix, gate)
        R.gate(gname, "FAIL", measured, target)


def gate_hook_holds(R, V, cuts, kind, max_scene, holds, intended=frozenset()):
    fps, n = R.fps, R.n
    stills = V["stills"]
    loop = kind == "loop"
    # 1. motion in the first 0.5 s
    first = next((s for s in stills if s[0] == 0), None)
    t_move = (first[1] + 1) / fps if first else 1 / fps
    ok = t_move <= 0.5 + 1e-6
    if loop:
        R.gate("hook: motion by 0.5 s", "SKIP", f"first change at {t_move:.2f} s", LOOP_SKIP)
    elif not ok:
        _fail_or_intended(R, "hook_motion", "hook", 0, first[1], f"nothing moves until {t_move:.2f} s",
                          "viewers decide in the first half second; a still opening reads as a frozen player",
                          "start on motion: something moving at f0 (a push-in, an element arriving), or trim the head",
                          "hook: motion by 0.5 s", f"first change at {t_move:.2f} s", "<= 0.50 s", intended)
    else:
        R.gate("hook: motion by 0.5 s", "PASS", f"first change at {t_move:.2f} s", "<= 0.50 s")
    # 2. a strong moment by 2 s
    lim = int(round(2.0 * fps))
    t_cut = next((f / fps for f, _, _ in cuts if f <= lim), None)
    big = np.where(V["strong"][:lim + 1] >= STRONG_FRAC)[0]
    t_big = big[0] / fps if len(big) else None
    cands = [t for t in (t_cut, t_big) if t is not None]
    if cands:
        R.gate("hook: strong moment by 2 s", "SKIP" if loop else "PASS",
               f"{'cut' if t_cut == min(cands) else 'big move'} at {min(cands):.2f} s",
               LOOP_SKIP if loop else "<= 2.0 s")
    else:
        mx = float(V["strong"][:lim + 1].max()) * 100
        if loop:
            R.gate("hook: strong moment by 2 s", "SKIP", f"none (biggest move {mx:.0f}%)", LOOP_SKIP)
        else:
            _fail_or_intended(R, "hook_strong", "hook", 0, min(lim, n - 1), f"no strong moment by 2 s (no cut; "
                              f"biggest move {mx:.0f}% of the frame)", "a weak hook loses the scroll",
                              "put a cut, a hit or a big move (>= 20% of the frame in 0.2 s) by 1-2 s",
                              "hook: strong moment by 2 s", f"none (biggest move {mx:.0f}%)", "<= 2.0 s", intended)
    # 3. holds without life (motion graphics and explainers)
    tail = stills[-1] if stills and stills[-1][1] == n - 1 else None
    if kind in ("motion", "explainer", "loop"):
        bad = [s for s in stills if s is not tail and (s[1] - s[0] + 1) / fps > 0.8 + 0.5 / fps]
        for s, e in bad:
            R.flag("hold_life", "FAIL", s, e, f"{(e - s + 1) / fps:.2f} s hold with no life",
                   "over ~0.8 s fully static reads as frozen, planned or not",
                   "keep something alive (1-2 px/frame drift, a 1-2% breathing scale) or cut it to 0.8 s", "holds")
        longest = max([(e - s + 1) / fps for s, e in stills if (s, e) != tail] or [0])
        R.gate("holds: none over 0.8 s without life", "FAIL" if bad else "PASS", f"longest {longest:.2f} s",
               "<= 0.8 s")
    # 4. static tail / end card
    t_tail = (tail[1] - tail[0] + 1) / fps if tail else 0.0
    if loop:
        R.gate("end card / static tail", "SKIP", f"{t_tail:.2f} s", LOOP_SKIP)
    elif t_tail > 1.5 + 0.5 / fps:
        _fail_or_intended(R, "end_tail", "holds", tail[0], tail[1], f"static tail of {t_tail:.2f} s",
                          "the end card overstays and the viewer leaves before the end",
                          f"trim the tail to 0.6-1.4 s (cut {t_tail - 1.2:.1f} s) or keep it alive",
                          "end card / static tail", f"{t_tail:.2f} s", "<= 1.5 s", intended)
    else:
        R.gate("end card / static tail", "PASS", f"{t_tail:.2f} s", "<= 1.5 s")


TILE_T = 3.0            # freshness, local: mean abs luma change of one tile (8x6 grid) that counts as new
SHIFT = 8               # ... unless the old tile shifted up to 8 px (of 128; ~120 px/s at 1080p) explains it (motion)
def local_events(small, fps):
    """Frames where some part of the picture gets a new state: a tile (8x6 grid) differs from 0.25 s before, still
    differs 0.25 s later, and has (mostly) settled by then. A new element arriving, a readout changing ('25 ms' to
    '100 ms') or a box landing counts; a dot moving through a tile (changes, then changes back) or a steady drift (never
    settles) does not, and neither does a change the old picture shifted by up to SHIFT px explains (something moving
    in or out of the tile; compared blurred, with a tolerance relative to the change, so sub-pixel moves and slow
    pushes count as motion), nor a tile going back to a state it showed in the last second (a blink or toggle). Changes over more than 60% of the tiles are left to the colour-histogram measure (cuts,
    scene changes)."""
    n = len(small)
    k = max(1, int(round(0.25 * fps)))
    if n < 2 * k + 1:
        return np.zeros(n, bool)
    hh, ww = small[0].shape
    ty, tx = np.linspace(0, hh, 7).astype(int), np.linspace(0, ww, 9).astype(int)
    F = lambda j: small[j].astype(np.int16)
    def blur(a):                                  # 3x3 box blur: sub-pixel moves and pushes match after a shift
        p = np.pad(a.astype(np.float32), 1, mode="edge")
        return sum(p[dy:dy + a.shape[0], dx:dx + a.shape[1]] for dy in range(3) for dx in range(3)) / 9.0
    def tiles(a, b):
        d = np.abs(a - b)
        return np.array([[d[ty[r]:ty[r + 1], tx[c]:tx[c + 1]].mean() for c in range(8)] for r in range(6)])
    out = np.zeros(n, bool)
    for i in range(k, n - k):
        cur, old = F(i), F(i - k)
        before = tiles(cur, old)
        if before.max() < TILE_T:
            continue
        new = F(i + k)
        after = tiles(new, cur)
        span = tiles(new, old)
        hit = (before >= TILE_T) & (span >= TILE_T) & (after <= 0.5 * before)
        if not hit.any() or hit.mean() > 0.6:
            continue
        seen = [F(j) for j in (i - 2 * k, i - 3 * k, i - 4 * k) if j >= 0]   # earlier states (a toggle comes back)
        bn, bo = blur(new), blur(old)
        for r, c in zip(*np.nonzero(hit)):
            y0, y1, x0, x1 = ty[r], ty[r + 1], tx[c], tx[c + 1]
            new_t = new[y0:y1, x0:x1]
            if any(np.abs(new_t - e[y0:y1, x0:x1]).mean() < TILE_T for e in seen):
                continue                          # back to a state shown in the last second: a blink, not news
            tol = max(TILE_T, 0.35 * span[r, c])  # motion, not news: the old picture shifted explains the new one
            bt, best = bn[y0:y1, x0:x1], span[r, c]
            for dy in range(-SHIFT, SHIFT + 1):
                for dx in range(-SHIFT, SHIFT + 1):
                    if y0 - dy < 0 or y1 - dy > hh or x0 - dx < 0 or x1 - dx > ww:
                        continue
                    best = min(best, float(np.abs(bt - bo[y0 - dy:y1 - dy, x0 - dx:x1 - dx]).mean()))
                    if best < tol:
                        break
                if best < tol:
                    break
            if best >= tol:
                out[i] = True
                break
    return out


def gate_freshness(R, V, cuts, max_scene):
    fps, n = R.fps, R.n
    ev = {0} | {f for f, _, _ in cuts}
    nov = V["nov"]
    loc = local_events(V.get("small") or [], fps)
    new = [(nov[i] >= NOV_T) or bool(loc[i]) if i < len(loc) else nov[i] >= NOV_T for i in range(n)]
    refr = max(1, int(round(0.5 * fps)))
    last = -refr
    for i in range(1, n):
        if new[i] and (not new[i - 1] or i - last >= refr):
            if i - last >= int(0.2 * fps):
                ev.add(i); last = i
    ev = sorted(ev)
    gaps = [(ev[k], (ev[k + 1] if k + 1 < len(ev) else n)) for k in range(len(ev))]
    longest = max(((b - a) / fps for a, b in gaps), default=0)
    bad = [(a, b) for a, b in gaps if (b - a) / fps > max_scene + 0.5 / fps]
    for a, b in bad:
        R.flag("freshness", "FAIL", a, b - 1, f"{(b - a) / fps:.1f} s without a new visual",
               "an explainer stalls when nothing new arrives; the eye wants a new element or state every 1-2 s",
               f"add a new element, readout or state change every 1-2 s in this span (max {max_scene:g} s)",
               "freshness")
    R.gate("freshness (E6)", "FAIL" if bad else "PASS", f"longest {longest:.1f} s, {len(ev)} new visuals",
           f"<= {max_scene:g} s")
    return [round(f / fps, 3) for f in ev]


# ---- sheet -----------------------------------------------------------------------------------------------------
def grab(path, info, frames, tw, th):
    """One decode: the listed frames as RGB arrays at tw x th."""
    frames = sorted(set(int(f) for f in frames if f >= 0))
    if not frames:
        return {}
    sel = "+".join(f"eq(n,{f})" for f in frames)
    if info["alpha"]:
        vf = (f"color=c=0x808080:s={tw}x{th}:r={info['fps']}[bg];[0:v]scale={tw}:{th},format=rgba[fg];"
              f"[bg][fg]overlay=shortest=1,select='{sel}'[out]")
    else:
        vf = f"[0:v]select='{sel}',scale={tw}:{th}[out]"
    r = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-i", path, "-filter_complex", vf, "-map", "[out]",
                        "-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True,
                       stdin=subprocess.DEVNULL)
    sz = tw * th * 3
    got = [np.frombuffer(r.stdout[i * sz:(i + 1) * sz], np.uint8).reshape(th, tw, 3)
           for i in range(len(r.stdout) // sz)]
    return dict(zip(frames, got))


def make_sheet(path, out, info, V, A, R, cuts_table, planned_f, holds, safe_px, verdict, kind):
    from PIL import Image, ImageDraw, ImageFont
    try:
        font = ImageFont.load_default(size=14)
        small = ImageFont.load_default(size=12)
    except TypeError:
        font = small = ImageFont.load_default()
    fps, n = R.fps, R.n
    W = 1600
    portrait = info["h"] > info["w"]
    th = 200 if portrait else 144
    tw = max(2, int(round(th * info["w"] / info["h"])) // 2 * 2)
    # frames: one per shot (first and last too for shots over 2 s), at least 12 in all
    bounds = [0] + [r["frame"] for r in cuts_table] + [n]
    shots = []
    for a, b in zip(bounds[:-1], bounds[1:]):
        if b - a < 1:
            continue
        pick = [a + (b - a) // 2]
        if (b - a) / fps > 2:   # first frame a few frames in, so a flash-cut frame doesn't stand for the shot
            pick = [min(a + 3, b - 1), a + (b - a) // 2, b - 1]
        shots.extend(pick)
    if len(shots) < 12:
        shots = sorted(set(shots) | {int(x) for x in np.linspace(0, n - 1, 12 - len(shots) + 2)[1:-1]})
    shots = sorted(set(shots))[:48]
    strong = [x for x in R.sorted_flags() if x["kind"] not in ("loudness", "true_peak", "spec_size", "spec_fps",
                                                               "pix_fmt", "no_audio", "frames", "decode")][:10]
    strips = []
    for x in strong:
        s, e = x["f0"], x["f1"]
        fr = [s - 2, s - 1, *range(s, e + 1), e + 1, e + 2] if e - s < 3 else [s - 1, s, (s + e) // 2, e, e + 1]
        strips.append((x, [min(max(0, f), n - 1) for f in fr]))
    imgs = grab(path, info, shots + [f for _, fr in strips for f in fr], tw, th)
    cols = max(1, (W - 24) // (tw + 8))
    grid_rows = (len(shots) + cols - 1) // cols
    GH = 300
    H = 40 + GH + 30 + grid_rows * (th + 24) + 30 + len(strips) * (th + 44) + 20
    img = Image.new("RGB", (W, H), (22, 22, 26))
    d = ImageDraw.Draw(img)
    d.text((12, 10), f"qa  {os.path.basename(path)}   {kind}   {info['w']}x{info['h']} {fps:.3f} fps  {n} frames  "
           f"{n / fps:.2f} s   {verdict}", font=font, fill=(255, 90, 90) if verdict.startswith("FAIL")
           else (120, 230, 140))
    # timeline
    x0, x1, y0 = 60, W - 20, 40
    tx = lambda f: x0 + (x1 - x0) * f / max(1, n - 1)  # noqa: E731
    d.rectangle([x0, y0, x1, y0 + GH], fill=(32, 32, 38))
    for s, e in holds:
        d.rectangle([tx(max(0, s * fps)), y0, tx(min(n - 1, e * fps)), y0 + GH], fill=(30, 45, 70))
    for x in R.flags:
        if x["f0"] == 0 and x["f1"] >= n - 1:
            continue                                     # whole-film flags (spec, loudness) are in the text
        col = (120, 30, 30) if x["sev"] == "FAIL" else ((110, 80, 20) if x["sev"] == "WARN" else (70, 70, 90))
        d.rectangle([tx(x["f0"]), y0 + 2, max(tx(x["f0"]) + 2, tx(x["f1"])), y0 + 18], fill=col)
    lanes = [("change", np.clip(V["c"] * 4, 0, 1), (200, 200, 200)), ("luma", V["Y"] / 255.0, (240, 220, 90)),
             ("big move", np.clip(V["strong"] / max(STRONG_FRAC * 2, 1e-6), 0, 1), (90, 200, 240))]
    if A is not None and len(A["db"]):
        idx = np.minimum((np.arange(n) / fps / A["hop_s"]).astype(int), len(A["db"]) - 1)
        lev = A["db"][idx]
        lanes.append(("audio dB", np.clip((lev + 60) / 60, 0, 1), (120, 230, 140)))
    lh = (GH - 30) / len(lanes)
    step = max(1, n // (x1 - x0))
    for k, (name, arr, col) in enumerate(lanes):
        top = y0 + 24 + k * lh
        d.text((4, top), name, font=small, fill=col)
        pts = [(tx(i), top + lh - 4 - (lh - 8) * float(arr[min(i, len(arr) - 1)])) for i in range(0, len(arr), step)]
        if len(pts) > 1:
            d.line(pts, fill=col, width=1)
    for f in planned_f:
        d.line([tx(f), y0, tx(f), y0 + GH], fill=(60, 160, 80), width=1)
    for row in cuts_table:
        col = (255, 255, 255) if row["planned"] in (None, True) else (255, 60, 60)
        d.line([tx(row["frame"]), y0 + 20, tx(row["frame"]), y0 + GH], fill=col, width=2)
    dur = n / fps
    tick = next(t for t in (0.5, 1, 2, 5, 10, 30, 60, 300, 600) if dur / t <= 30)
    t = 0.0
    while t <= dur:
        d.text((tx(t * fps) - 8, y0 + GH + 4), tc(t) if tick >= 1 else f"{t:.1f}", font=small, fill=(150, 150, 150))
        t += tick
    d.text((x0, y0 + GH + 16), "red bar FAIL, amber WARN, blue = declared holds, green line = planned cut, white = "
           "detected cut (red = unplanned)", font=small, fill=(150, 150, 150))
    y = y0 + GH + 36
    d.text((12, y), f"frames (one per shot, cyan = {safe_px} px safe area)", font=font, fill=(220, 220, 220))
    y += 20
    sp = safe_px * tw / info["w"]
    for k, f in enumerate(shots):
        cx, cy = 12 + (k % cols) * (tw + 8), y + (k // cols) * (th + 24)
        if f in imgs:
            img.paste(Image.fromarray(imgs[f]), (cx, cy))
            d.rectangle([cx + sp, cy + sp * 1, cx + tw - sp, cy + th - sp], outline=(0, 200, 220))
        d.text((cx, cy + th + 2), f"f{f}  {tc(f / fps)}", font=small, fill=(200, 200, 200))
    y += grid_rows * (th + 24) + 10
    if strips:
        d.text((12, y), "evidence strips (before | flagged | after)", font=font, fill=(220, 220, 220))
        y += 20
    for x, fr in strips:
        d.text((12, y), f"{x['sev']} {x['kind']}  f{x['f0']}-f{x['f1']} ({tc(x['t0'])})  {x['what']}"[:150],
               font=small, fill=(255, 120, 120) if x["sev"] == "FAIL" else
               ((240, 180, 80) if x["sev"] == "WARN" else (170, 170, 200)))
        for c, f in enumerate(fr):
            cx = 12 + c * (tw + 8)
            if f in imgs:
                img.paste(Image.fromarray(imgs[f]), (cx, y + 16))
            on = x["f0"] <= f <= x["f1"]
            if on:
                d.rectangle([cx - 2, y + 14, cx + tw + 1, y + 16 + th + 1], outline=(255, 60, 60), width=2)
            d.text((cx + 3, y + 18), f"f{f}", font=small, fill=(255, 255, 0))
        y += th + 44
    img.save(out, quality=88)


# ---- review.md ------------------------------------------------------------------------------------------------
def write_review(path, R, info, V, A, a, kind, profile_name, cuts_table, planned, tools, verdict, coverage, fresh):
    fl = R.sorted_flags()
    L = []
    L.append(f"# QA review: {os.path.basename(path)}\n")
    L.append(f"**Verdict: {verdict}**  ")
    L.append(f"kind `{kind}` · profile `{profile_name}` · {info['w']}x{info['h']} · {R.fps:.3f} fps · {V['n']} frames "
             f"· {V['n'] / R.fps:.2f} s · run {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
    L.append("Command: `python3 engine/qa.py " + " ".join(a._argv) + "`\n")
    L.append("## Fixes (most severe first)\n")
    if fl:
        for x in fl:
            L.append(f"- **{x['sev']}** {R.line(x)}")
    else:
        L.append("- none from the machine pass")
    L.append("\nJudge every flag by frame on `sheet.jpg` (evidence strips): real, intended or false alarm.\n")
    if NOTES:
        L.append("## Notes\n")
        L.extend(f"- {x}" for x in NOTES)
        L.append("")
    L.append("## Gates\n")
    L.append("| gate | result | measured | target |")
    L.append("|---|---|---|---|")
    for g in R.gates:
        L.append(f"| {g['gate']} | {g['result']} | {g['measured']} | {g['target']} |")
    L.append("\n## Spec\n")
    L.append(f"- file: {info['w']}x{info['h']}, {info['fps_str']} ({R.fps:.3f} fps), {info['codec']} "
             f"{info['pix_fmt']}, {V['n']} frames decoded (container {info['nb_frames']}), "
             f"{V['n'] / R.fps:.2f} s, duplicate frames {int(V['dup'].sum())}")
    L.append(f"- audio: {info['a_codec']} {info['a_rate']} Hz {info['a_ch']} ch" if info["audio"] else "- audio: none")
    if A is not None:
        lo = A["loud"]
        L.append(f"- loudness: integrated {lo.get('I', float('nan')):.1f} LUFS, true peak "
                 f"{lo.get('TP', float('nan')):.1f} dBTP, LRA {lo.get('LRA', float('nan')):.1f} LU "
                 "(measured, not heard: a person listens before acceptance)")
    L.append("\n## Shots\n")
    if planned is None:
        L.append("No cut list given (`--cuts` / `--shotlist`): cuts are listed, not checked against a plan.\n")
    L.append("| # | first frame | time | scdet | planned | offset (frames) |")
    L.append("|---|---|---|---|---|---|")
    L.append(f"| 1 | f0 | {tc(0)} | - | - | - |")
    for k, r in enumerate(cuts_table):
        pl = "-" if r["planned"] is None else ("yes" if r["planned"] else "**NO**")
        L.append(f"| {k + 2} | f{r['frame']} | {tc(r['t'])} | {r['score']} | {pl} | "
                 f"{'' if r['offset'] is None else r['offset']} |")
    if fresh is not None:
        L.append(f"\nNew visuals (freshness events, s): {', '.join(f'{t:g}' for t in fresh[:80])}"
                 + (" ..." if len(fresh) > 80 else ""))
    safe = a._safe_px
    L.append("\n## Manual checks (Claude, from sheet.jpg and frame crops)\n")
    L.append(f"- [ ] Text clear of the edges: at least 24 px, and inside the house safe area ({safe} px, the cyan box "
             "on every sheet frame)")
    L.append("- [ ] Text never over a face or over other text; readable at phone size")
    L.append("- [ ] Every cut has a visible cause that comes first (motion, a hit, a look); no reversals or ghost frames")
    L.append("- [ ] No decorative wipes, inverts, added shake or light leaks; every effect is born from the picture and "
             "lands on the music")
    L.append("- [ ] Slop list (G1): corner labels, counters, timecodes, corner brackets, \"headline left / card right\" "
             "deck layouts, typed-out headlines with a caret, fades everywhere")
    L.append("- [ ] Continuity across cuts; nothing cut by the frame edge; no slow \"nothing new\" stretches")
    L.append("- [ ] Every machine flag above judged by frame: real, intended or false alarm")
    L.append("- [ ] Sound was measured, not heard: a person listens before acceptance")
    L.append("\n## Fresh-eyes review (H4)\n")
    L.append("Not run yet. Spawn a reviewer with no context (see the video-gates skill): what it is about, score /10 "
             "against the last version, cheap or templated moments, fixes in the fix-line format.\n")
    L.append("- about: _\n- score: _/10 (last version: _/10)\n- fixes: _\n")
    L.append("## Coverage\n")
    L.append(coverage + "\n")
    L.append("## Tool output\n")
    for name, t in tools.items():
        L.append(f"**{name}** (`{t.get('cmd', '')}`, exit {t.get('rc')})\n")
        L.append("```\n" + (t.get("stdout") or "").strip()[:3000] + "\n```\n")
    with open(os.path.join(a.out, "review.md"), "w") as fh:
        fh.write("\n".join(L) + "\n")


# ---- main ------------------------------------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video")
    prof.add_arg(ap)
    ap.add_argument("--kind", choices=["edit", "motion", "explainer", "loop"], default="edit",
                    help="edit (default): footage cut to music; motion: motion graphics (strict motion gate, hold "
                         "gate); explainer: motion + the freshness gate; loop: a loop or overlay piece (logo swing, "
                         "corner bug, lower third): as motion, but the hook and end-tail gates are not run")
    ap.add_argument("--intended", default="",
                    help="gates that fail on purpose, e.g. \"end_tail,hook\" (hook, hook_motion, hook_strong, "
                         "end_tail): a failure there becomes an INFO line saying it was declared intended")
    ap.add_argument("--holds", default="", help='intentional stills: "a-b,start:N,end:N" seconds (as motion_check)')
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--cuts", help='planned cut times in seconds, "1.5,4.2" ("none" = no cuts planned)')
    g.add_argument("--shotlist", help="planned cuts: a render's concat list (<out dir>/_parts/list.txt), or a JSON list / "
                   "'cuts' / 'starts' / shots[].start")
    ap.add_argument("--max-scene", type=float, default=2.5,
                    help="explainer: longest stretch without a new visual, seconds (default 2.5)")
    ap.add_argument("--out", help="review folder (default ./qa_<video name>/)")
    ap.add_argument("--allow-stutter", action="store_true",
                    help="pass to motion_check: 24p source conformed to 30p repeats frames on purpose")
    ap.add_argument("--silences", default="", help='planned silences "a-b,..." seconds (not flagged)')
    ap.add_argument("--size", help="expected frame size WxH (default: the profile's delivery sizes)")
    ap.add_argument("--fps", type=float, help="expected frame rate (default: the profile's delivery.fps)")
    ap.add_argument("--width", type=int, default=320, help="analysis width in px (default 320)")
    ap.add_argument("--no-sheet", action="store_true", help="skip sheet.jpg")
    a = ap.parse_args(argv)
    a._argv = [x if " " not in x else f'"{x}"' for x in (argv if argv is not None else sys.argv[1:])]
    kind = a.kind
    try:
        intended = parse_intended(a.intended)
    except SystemExit as e:                              # a usage error: exit 2 like any other bad argument
        ap.error(str(e.code)[len("qa: "):] if str(e.code).startswith("qa: ") else str(e.code))
    del NOTES[:]

    try:
        P = prof.load(a.profile)
        profile_name = P.name
    except prof.ProfileError as e:
        if a.profile:
            print(f"qa: {e}")
            return 2
        P, profile_name = None, "none (generic defaults)"
    a._safe_px = int(P.get("layout.safe_px", 90)) if P is not None else 90

    if not a.out:
        a.out = os.path.join(os.getcwd(), "qa_" + os.path.splitext(os.path.basename(a.video))[0])
    os.makedirs(a.out, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="qa_")
    try:
        try:
            info = probe(a.video)
            V = analyse_video(a.video, info, a.width, tmp, keep_small=(kind == "explainer"))
        except Exception as e:  # noqa: BLE001
            print(f"qa: cannot read {a.video}: {e}")
            return 2
        fps, n = info["fps"], V["n"]
        R = Review(fps, n)
        holds = parse_spans(a.holds, n / fps)
        silences = parse_spans(a.silences, n / fps)
        planned_t = load_cuts(a)
        planned_f = [int(round(t * fps)) for t in planned_t] if planned_t is not None else None
        tools = {}

        gate_spec(R, info, V, P, a, kind)
        tools["motion_check"] = gate_motion(R, a, kind, a.out, a.video, info, P)
        cuts = detect_cuts(V)
        flash_events = gate_flashes(R, V, planned_f or [])
        cuts_table = gate_cuts(R, V, cuts, planned_f, flash_events)
        cuts_ok = [(c, s, gg) for c, s, gg in cuts if any(r["frame"] == c for r in cuts_table)]
        if kind in ("motion", "explainer", "loop"):
            gate_pops(R, V, cuts, flash_events)
        gate_hook_holds(R, V, cuts_ok, kind, a.max_scene, holds, intended)
        fresh = gate_freshness(R, V, cuts_ok, a.max_scene) if kind == "explainer" else None
        A = None
        if info["audio"]:
            A = analyse_audio(a.video, tmp)
            cut_times = planned_t if planned_t else [r["t"] for r in cuts_table]
            tools["audio_check"] = gate_audio_check(R, a.video, cut_times, P)
            gate_loudness(R, A, P)
            gate_audio_faults(R, A, silences)
        else:
            R.gate("audio", "SKIP", "no audio stream", "-")

        nfail = sum(1 for x in R.flags if x["sev"] == "FAIL")
        nwarn = sum(1 for x in R.flags if x["sev"] == "WARN")
        ninfo = sum(1 for x in R.flags if x["sev"] == "INFO")
        verdict = (f"FAIL ({nfail} fail, {nwarn} warning" if nfail else
                   f"PASS ({nwarn} warning{'s' if nwarn != 1 else ''}") + \
            (f", {ninfo} declared intended)" if ninfo else ")")
        sheet = os.path.join(a.out, "sheet.jpg")
        sheet_note = "sheet skipped"
        if not a.no_sheet:
            try:
                make_sheet(a.video, sheet, info, V, A, R, cuts_table, planned_f or [], holds, a._safe_px, verdict,
                           kind)
                nshots = len(cuts_table) + 1
                sheet_note = f"sheet.jpg: timeline, frames for {nshots} shot(s), evidence strips for up to 10 flags"
            except ImportError:
                sheet_note = "sheet skipped: Pillow not installed"
        coverage = (f"Machine pass: {n} frames decoded at {V['w']}x{V['h']} (every frame), "
                    + (f"{len(A['db']) * A['hop_s']:.1f} s of audio in 5 ms windows, " if A is not None else "")
                    + f"scdet on every frame. {sheet_note}. Classes left to eyes: see Manual checks.")
        write_review(a.video, R, info, V, A, a, kind, profile_name, cuts_table, planned_t, tools, verdict, coverage,
                     fresh)
        result = {"video": os.path.abspath(a.video), "kind": kind, "profile": profile_name,
                  "result": "FAIL" if nfail else "PASS", "verdict": verdict,
                  "spec": {k: info[k] for k in ("w", "h", "fps", "fps_str", "pix_fmt", "codec", "nb_frames", "audio",
                                                "a_codec", "a_rate", "a_ch", "alpha")} | {"frames": n,
                                                                                         "duration": n / fps},
                  "loudness": A["loud"] if A is not None else None,
                  "planned_cuts": planned_t, "cuts": cuts_table, "freshness_events": fresh,
                  **({"intended": sorted(intended)} if intended else {}), **({"notes": list(NOTES)} if NOTES else {}),
                  "gates": R.gates, "flags": R.sorted_flags(), "fix_lines": [R.line(x) for x in R.sorted_flags()]}
        with open(os.path.join(a.out, "qa.json"), "w") as fh:
            json.dump(result, fh, indent=2, default=float)
        print(f"qa: {a.video}  [{kind}, profile {profile_name}]")
        for gg in R.gates:
            print(f"  {gg['result']:4s} {gg['gate']}: {gg['measured']}")
        for x in R.sorted_flags():
            print(f"  {x['sev']} {R.line(x)}")
        print(f"  review: {os.path.join(a.out, 'review.md')}")
        print(f"RESULT: {verdict}")
        return 1 if nfail else 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
