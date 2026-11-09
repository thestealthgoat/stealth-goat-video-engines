#!/usr/bin/env python3
"""fxpack.py - cinematic edit pack: flash cuts, zoom punches with radial blur, RGB split, speed ramps, whip pans,
black and white with a color pop, kinetic text. Every effect is placed on the bar map (engine/beatmap.py) and
must pass the gate: it needs a music event (a beat, downbeat, hit, riser or the drop) within one frame AND a
reason measured in the picture (the motion it follows, the color it keeps, the side the action is not on).
An effect with no cause in both is decorative and the render stops (exit 3) and lists it.

fxpack.py <plan.json> --out DIR [--name N] [--profile P] [--fps 29.97] [--size 1920x1080] [--frames t1,t2] [--plan-only]

plan.json:
  {"music": "track.wav", "music_in": 0.0,                 # the bar map is built from here ("bpm": 120 if known)
   "shots": [{"src": "play1.mp4", "in": 3.0, "beats": 4},  # each shot lasts whole beats on the grid
             {"src": "play2.mp4", "in": 1.5, "beats": 4, "hero": true},   # hero: lands on the drop
             ...],
   "text": ["FRIDAY", "NIGHT"],                            # kinetic text: one word per beat from the drop (optional)
   "fx": "auto"}                                           # or a list: [{"type": "flash", "at": 4.0}, ...]
Types: flash · zoom (punch + radial blur) · rgb (RGB split) · ramp (speed ramp into the next cut) · whip (whip pan
across a cut) · pop (black and white keeping one hue) · text. "auto" picks them from the bar map and the pictures.

Writes <N>_fx.mp4 (music under the cut), <N>_fx.xml (Premiere: the shots as cut, the music, a marker per effect)
and <N>_fx.json (the timeline, every effect with its music event and picture reason, the gate result).
Prints the cut list for qa: engine/qa.py <N>_fx.mp4 --kind edit --cuts <printed>.
"""
import argparse, colorsys, json, math, os, subprocess, sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import vprofile as prof  # noqa: E402
from spring import clamp01, progress  # noqa: E402

SAFE_TYPES = ("flash", "zoom", "rgb", "ramp", "whip", "pop", "text")


def sp(t, start, preset="snappy"):
    return progress(t, start=start, preset=preset)


def kick(t, t0, v0, preset="snappy"):
    """impulse response: a spring launched with v0 that returns to rest (punches, recoils)"""
    if t < t0:
        return 0.0
    return progress(t, start=t0, preset=preset, v0=v0) - progress(t, start=t0, preset=preset)


# ------------------------------------------------------------------ media
def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height,r_frame_rate:stream_side_data=rotation:format=duration", "-of", "json", path],
                         capture_output=True, text=True, stdin=subprocess.DEVNULL, check=True).stdout
    d = json.loads(out); s = d["streams"][0]; a, b = s["r_frame_rate"].split("/")
    return {"w": s["width"], "h": s["height"], "fps": float(a) / float(b), "dur": float(d["format"]["duration"])}


def read_span(path, t0, dur, size, fps):
    """frames of path from t0 for dur seconds at size (cover-cropped: a portrait phone clip fills a 16:9 frame and
    the other way round, never stretched; rotation tags applied), resampled to fps (output-side seek keeps them exact)."""
    w, h = size
    cmd = ["ffmpeg", "-nostdin", "-v", "error", "-ss", f"{max(0.0, t0 - 1.0):.3f}", "-i", path, "-ss", f"{min(1.0, t0):.3f}",
           "-t", f"{dur:.3f}", "-vf", f"scale={w}:{h}:force_original_aspect_ratio=increase:flags=bicubic,crop={w}:{h},setsar=1,fps={fps}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    raw = subprocess.run(cmd, capture_output=True, stdin=subprocess.DEVNULL, check=True).stdout
    n = len(raw) // (w * h * 3)
    if not n:
        raise SystemExit(f"fxpack: no frames from {path} at {t0:.2f} s")
    return np.frombuffer(raw[: n * w * h * 3], np.uint8).reshape(n, h, w, 3)


# ------------------------------------------------------------------ picture analysis
def analyse(frames):
    """per-frame motion (mean flow vector, magnitude, centroid of moving pixels, as frame fractions) and the
    dominant saturated hue of the shot. Low-res, so it is cheap."""
    import cv2
    H0, W0 = frames[0].shape[:2]
    sc_ = 320 / max(W0, H0); SW, SH = max(1, round(W0 * sc_)), max(1, round(H0 * sc_))
    K = 1920 / max(SW, SH)                     # px per frame on a 1920 px long side, the same scale on both axes
    small = [cv2.cvtColor(cv2.resize(f, (SW, SH), interpolation=cv2.INTER_AREA), cv2.COLOR_RGB2GRAY) for f in frames]
    mot = []
    for a, b in zip(small, small[1:]):
        fl = cv2.calcOpticalFlowFarneback(a, b, None, 0.5, 3, 15, 3, 5, 1.2, 0)
        mag = np.hypot(fl[..., 0], fl[..., 1])
        # camera pan = median flow; action = what moves against it
        med = np.median(fl.reshape(-1, 2), axis=0)
        res = np.hypot(fl[..., 0] - med[0], fl[..., 1] - med[1])
        wgt = res * (res > np.percentile(res, 90))
        tot = wgt.sum() + 1e-6
        ys, xs = np.mgrid[0:SH, 0:SW]
        cx, cy = (xs * wgt).sum() / tot / SW, (ys * wgt).sum() / tot / SH
        mot.append({"pan": [float(med[0] * K), float(med[1] * K)], "mag": float(mag.mean() * K), "act": float(res.mean() * K),
                    "centre": [float(cx), float(cy)]})   # px per frame on a 1920 px long side
    mot.insert(0, dict(mot[0]) if mot else {"pan": [0, 0], "mag": 0, "act": 0, "centre": [0.5, 0.5]})
    # hue: the most common hue among saturated pixels THAT MOVE against the camera (the players, not the field),
    # measured on the middle of the shot; share = that hue's part of the moving, saturated pixels
    i = len(frames) // 2; j = min(len(frames) - 1, i + 1)
    a_, b_ = small[i], small[j] if j != i else small[max(0, i - 1)]
    fl = cv2.calcOpticalFlowFarneback(a_, b_, None, 0.5, 3, 15, 3, 5, 1.2, 0)
    med = np.median(fl.reshape(-1, 2), axis=0); res = np.hypot(fl[..., 0] - med[0], fl[..., 1] - med[1])
    hsv = cv2.cvtColor(cv2.resize(frames[i], (SW, SH)), cv2.COLOR_RGB2HSV)
    moving = res > max(0.5, np.percentile(res, 85))
    m = moving & (hsv[..., 1] > 90) & (hsv[..., 2] > 60)
    hue, share = None, 0.0
    if m.sum() > 60:
        # the hue the movers carry more than the frame does (a field or a sky is everywhere, a jersey is not)
        hist = np.bincount((hsv[..., 0][m] // 10).ravel(), minlength=18).astype(float)
        allm = (hsv[..., 1] > 90) & (hsv[..., 2] > 60)
        hall = np.bincount((hsv[..., 0][allm] // 10).ravel(), minlength=18).astype(float)
        lift = (hist / hist.sum()) / (hall / max(1.0, hall.sum()) + 0.02)
        lift[hist < max(20, 0.08 * hist.sum())] = 0
        if lift.max() > 1.2:
            k = int(lift.argmax()); hue = k * 10 + 5; share = float(hist[k] / max(1, moving.sum()))
    return {"motion": mot, "hue": hue, "hue_share": share}


# ------------------------------------------------------------------ plan
def build_timeline(plan, bm, fps):
    """shots on the beat grid: each shot is `beats` beats; the hero shot starts on the drop when there is one."""
    beats = bm["beats"]; shots = plan["shots"]
    starts = []
    hero = next((i for i, s in enumerate(shots) if s.get("hero")), None)
    drop = bm.get("drop")
    if hero is not None and drop is not None:
        bd = int(np.argmin([abs(b - drop) for b in beats]))
        b0 = bd - sum(int(s.get("beats", 4)) for s in shots[:hero])
    else:
        b0 = int(np.argmin([abs(b - bm["downbeats"][0]) for b in beats]))
    if b0 < 0:
        raise SystemExit(f"fxpack: the shots before the hero need {-b0} more beats of music before the drop; "
                         f"start the music earlier (music_in) or cut fewer beats before the hero")
    k = b0
    for s in shots:
        n = int(s.get("beats", 4))
        if k + n >= len(beats):
            raise SystemExit("fxpack: the music is shorter than the shots; use a longer track or fewer beats")
        starts.append((beats[k], beats[k + n], k, k + n)); k += n
    origin = starts[0][0]                      # the edit starts on its first cut
    tl = []
    for s, (a, b, ka, kb) in zip(shots, starts):
        tl.append({"src": s["src"], "in": float(s.get("in", 0.0)), "start": round(a - origin, 4), "end": round(b - origin, 4),
                   "beats": [round(x - origin, 4) for x in beats[ka:kb + 1]], "hero": bool(s.get("hero")),
                   "label": s.get("label", os.path.basename(s["src"]))})
    return tl, origin


def music_events(bm, origin, dur):
    """bar-map events in edit time (s), each with its kind"""
    ev = []
    sh = lambda x: round(x - origin, 4)
    for b in bm["beats"]:
        if -0.01 <= b - origin <= dur: ev.append((sh(b), "beat"))
    for b in bm["downbeats"]:
        if -0.01 <= b - origin <= dur: ev.append((sh(b), "downbeat"))
    for h in bm.get("hits_detail", []):
        if 0 <= h["t"] - origin <= dur: ev.append((sh(h["t"]), f"hit#{h['rank']}"))
    for r in bm.get("risers", []):
        d = r.get("into_downbeat")
        if isinstance(d, (int, float)) and not isinstance(d, bool) and 0 <= d - origin <= dur: ev.append((sh(d), "riser"))
    if bm.get("drop") is not None and 0 <= bm["drop"] - origin <= dur:
        ev.append((sh(bm["drop"]), "drop"))
    return sorted(ev)


def nearest_event(t, events, kinds=None):
    best = None
    for et, k in events:
        if kinds and not any(k.startswith(x) for x in kinds):
            continue
        if best is None or abs(et - t) < abs(best[0] - t):
            best = (et, k)
    return best


def motion_at(sh, u, fps):
    """motion record of shot sh at local time u (output seconds into the shot)"""
    m = sh["an"]["motion"]; i = min(len(m) - 1, max(0, int(round(u * fps))))
    return m[i]


def auto_fx(tl, events, plan, fps, P):
    fx = []
    drop = next((t for t, k in events if k == "drop"), None)
    for i, sh in enumerate(tl):
        nxt = tl[i + 1] if i + 1 < len(tl) else None
        # flash on the drop cut; whip on a cut whose outgoing shot pans hard into it
        if i and drop is not None and abs(sh["start"] - drop) < 1.5 / fps:
            fx.append({"type": "flash", "at": sh["start"], "event": "drop",
                       "reason": f"the hero shot lands on the drop ({sh['label']})"})
        if nxt is not None:
            last = sh["an"]["motion"][-max(2, int(0.3 * fps)):]
            pan = np.mean([m["pan"][0] for m in last])
            if abs(pan) > 6 and not (drop is not None and abs(nxt["start"] - drop) < 1.5 / fps):
                fx.append({"type": "whip", "at": nxt["start"], "dir": 1 if pan > 0 else -1, "event": "beat",
                           "reason": f"the outgoing shot pans {abs(pan):.0f} px/frame {'right' if pan > 0 else 'left'} into the cut"})
        # speed ramp into the drop: the shot before the hero slows at its motion peak
        acts = [m["act"] for m in sh["an"]["motion"]]
        if (nxt is not None and drop is not None and abs(nxt["start"] - drop) < 1.5 / fps and sh["end"] - sh["start"] >= 1.2
                and max(acts) >= 2.0):                       # only slow something that is moving
            fx.append({"type": "ramp", "at": nxt["start"], "from": round(sh["end"] - 2 * (sh["beats"][1] - sh["beats"][0]), 4),
                       "speed": 0.35, "event": "riser" if any(k == "riser" and abs(t - nxt["start"]) < 1.5 / fps for t, k in events) else "drop",
                       "reason": f"slows the action (peak {max(acts):.1f} px/frame) into the drop"})
        # zoom punch on the strongest hit inside the shot, centred on the action
        hits = [(t, k) for t, k in events if k.startswith("hit#") and sh["start"] + 0.25 < t < sh["end"] - 0.25]
        if hits:
            t, k = min(hits, key=lambda e: int(e[1][4:]))
            m = motion_at(sh, t - sh["start"], fps)
            if m["act"] > 0.6:
                fx.append({"type": "zoom", "at": t, "centre": m["centre"], "event": k,
                           "reason": f"punches in on the action at ({m['centre'][0]:.2f}, {m['centre'][1]:.2f}), moving {m['act']:.1f} px/frame"})
                if k in ("hit#1", "hit#2") and m["act"] > 2.0:
                    ang = math.atan2(m["pan"][1], m["pan"][0]) if abs(m["pan"][0]) + abs(m["pan"][1]) > 0.5 else 0.0
                    fx.append({"type": "rgb", "at": t, "angle": ang, "event": k,
                               "reason": f"the loudest transient on fast action ({m['act']:.1f} px/frame)"})
        # black and white keeping the hero's own colour
        if sh["hero"] and sh["an"]["hue"] is not None and sh["an"]["hue_share"] > 0.05:
            fx.append({"type": "pop", "at": sh["start"], "until": sh["end"], "hue": sh["an"]["hue"] * 2, "event": "drop" if drop is not None else "downbeat",
                       "reason": f"keeps the action's own color (hue {sh['an']['hue'] * 2} deg, {100 * sh['an']['hue_share']:.0f}% of what moves)"})
    # whips are the loudest transition: keep the two strongest pans, never on neighbouring cuts (no repeated wipes)
    wh = sorted([e for e in fx if e["type"] == "whip"], key=lambda e: -float(e["reason"].split(" px")[0].split()[-1]))
    keep = []
    for e in wh:
        if len(keep) < 2 and all(abs(e["at"] - k["at"]) > 3.0 for k in keep):
            keep.append(e)
    fx = [e for e in fx if e["type"] != "whip" or e in keep]
    # kinetic text from the drop (or the first downbeat), one word a beat, opposite the action
    words = plan.get("text") or []
    if words:
        t0 = drop if drop is not None else next((t for t, k in events if k == "downbeat"), 0.0)
        end = tl[-1]["end"]
        bts = [t for t, k in events if k == "beat" and t >= t0 - 1e-3 and t < end - 1e-6][: len(words)]
        if len(bts) < len(words):
            print(f"fxpack: only {len(bts)} beats after the drop for {len(words)} words; leaving out {words[len(bts):]}", file=sys.stderr)
        for w, t in zip(words, bts):
            sh = next((s for s in tl if s["start"] - 1e-6 <= t < s["end"]), tl[-1])
            m = motion_at(sh, t - sh["start"], fps)
            side = "left" if m["centre"][0] > 0.5 else "right"
            fx.append({"type": "text", "at": t, "word": w, "side": side, "event": "beat",
                       "reason": f"the action is on the {'right' if side == 'left' else 'left'} (x {m['centre'][0]:.2f})"})
    return fx


def gate(fx, events, fps):
    """H3: every effect needs a music event within one frame and a measured picture reason."""
    bad = []
    for e in fx:
        if e["type"] not in SAFE_TYPES:
            bad.append((e, "unknown effect type")); continue
        ne = nearest_event(e["at"], events)
        if ne is None or abs(ne[0] - e["at"]) > 1.0 / fps + 1e-6:
            bad.append((e, "not on the bar map (no beat, hit, riser or drop within one frame)")); continue
        if not e.get("reason") or not any(ch.isdigit() for ch in e["reason"]) and e["type"] not in ("flash",):
            bad.append((e, "no measured reason in the picture")); continue
        e["event"] = e.get("event") or ne[1]
    return bad


# ------------------------------------------------------------------ effects (per output frame)
def radial_zoom(img, k, centre, blur):
    import cv2
    h, w = img.shape[:2]; cx, cy = centre[0] * w, centre[1] * h
    def zoomed(s):
        M = np.float32([[s, 0, cx * (1 - s)], [0, s, cy * (1 - s)]])
        return cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    if blur < 0.004:
        return zoomed(k)
    n = 6; acc = np.zeros((h, w, 3), np.float32)
    for i in range(n):
        acc += zoomed(k * (1 + blur * i / (n - 1)))
    return (acc / n).astype(np.uint8)


def motion_blur(img, length, horizontal=True):
    import cv2
    L = int(max(1, length)) | 1
    if L <= 1:
        return img
    ker = np.zeros((L, L), np.float32)
    if horizontal: ker[L // 2, :] = 1.0 / L
    else: ker[:, L // 2] = 1.0 / L
    return cv2.filter2D(img, -1, ker, borderType=cv2.BORDER_REFLECT)


def shift(ch, dx, dy):
    import cv2
    M = np.float32([[1, 0, dx], [0, 1, dy]])
    return cv2.warpAffine(ch, M, (ch.shape[1], ch.shape[0]), borderMode=cv2.BORDER_REFLECT)


def colour_pop(img, hue_deg, amount):
    import cv2
    hsv = cv2.cvtColor(img, cv2.COLOR_RGB2HSV).astype(np.float32)
    d = np.abs(((hsv[..., 0] * 2 - hue_deg) + 180) % 360 - 180)
    keep = np.clip((28 - d) / 14, 0, 1) * np.clip((hsv[..., 1] - 50) / 60, 0, 1)
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY).astype(np.float32)[..., None]
    gray = np.clip((gray - 128) * 1.15 + 128, 0, 255)          # a little contrast for the B&W
    m = 1 - amount * (1 - keep[..., None])
    return (img.astype(np.float32) * m + gray * (1 - m)).astype(np.uint8)


class TextArt:
    def __init__(self, P, size):
        from PIL import ImageFont
        self.P, self.W, self.H = P, size[0], size[1]
        self.font = ImageFont.truetype(P.font("head"), int(0.16 * min(size)))   # from the short side: 16:9 and 9:16 alike
        self.cache = {}

    def word(self, w):
        from PIL import Image, ImageDraw
        if w not in self.cache:
            caps = (self.P.get("explain", {}) or {}).get("head_caps", True)
            s = w.upper() if caps else w
            bb = self.font.getbbox(s); pad = int(0.02 * self.H)
            im = Image.new("RGBA", (bb[2] - bb[0] + 2 * pad, bb[3] - bb[1] + 2 * pad), (0, 0, 0, 0))
            d = ImageDraw.Draw(im)
            d.text((pad - bb[0] + 4, pad - bb[1] + 4), s, font=self.font, fill=(0, 0, 0, 140))   # soft drop shadow
            d.text((pad - bb[0], pad - bb[1]), s, font=self.font, fill=self.P.rgb("text") if "text" in self.P.get("brand.colors") else (255, 255, 255))
            self.cache[w] = im
        return self.cache[w]


def level_music(music, t0, dur, out_wav, P):
    """the music under the cut: trimmed sample-exactly, 1.2 s fade out, measured (loudnorm pass 1), then one gain to the
    profile's delivery loudness and a peak limiter at the true-peak ceiling"""
    lufs, tp = P.get("delivery.loudness_lufs", -14), P.get("delivery.true_peak_db", -2)
    pre = f"atrim=start={t0:.4f}:duration={dur:.4f},asetpts=PTS-STARTPTS,aresample=48000,afade=t=out:st={max(0, dur - 1.2):.3f}:d=1.2"
    err = subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-i", music, "-af", pre + f",loudnorm=I={lufs}:TP={tp - 1}:LRA=20:print_format=json",
                          "-f", "null", "-"], capture_output=True, text=True, stdin=subprocess.DEVNULL).stderr
    j = json.loads(err[err.rindex("{"): err.rindex("}") + 1])
    gain = lufs - float(j["input_i"])
    # one gain for the whole track, then a peak limiter at the true-peak ceiling (1 dB under it, the way the rest of
    # the engine aims): the music keeps its dynamics and lands on the loudness target; only rare peaks are touched
    lim = 10 ** ((tp - 1.5) / 20)
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", music, "-af",
                    pre + f",volume={gain:.2f}dB,alimiter=limit={lim:.4f}:attack=2:release=60:level=false,aresample=48000",
                    "-c:a", "pcm_s16le", out_wav], check=True, stdin=subprocess.DEVNULL)


def render(tl, fx, out_mp4, music, origin, music_in, fps, size, P, frames_only=None):
    from PIL import Image
    W, H = size
    dur = tl[-1]["end"]
    accent = np.array(P.rgb("accent"), np.float32)
    art = TextArt(P, size)
    safe = int(P.get("layout.safe_px", 90))
    times = frames_only if frames_only is not None else [i / fps for i in range(int(round(dur * fps)))]
    enc = None
    if frames_only is None:
        wav = os.path.splitext(out_mp4)[0] + "_music.wav"
        level_music(music, origin + music_in, dur, wav, P)
        enc = subprocess.Popen(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                                "-framerate", f"{fps}", "-i", "pipe:0", "-i", wav,
                                "-map", "0:v", "-map", "1:a",
                                "-c:v", "libx264", "-crf", "17", "-preset", "medium", "-threads", "4", "-pix_fmt", "yuv420p",
                                "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", out_mp4], stdin=subprocess.PIPE)
    stills = []
    for t in times:
        k = next(i for i, s in enumerate(tl) if t < s["end"] - 1e-9 or i == len(tl) - 1)
        sh = tl[k]; u = t - sh["start"]
        q = sh["src_at"](u) * sh["rfps"]; i0 = min(len(sh["frames"]) - 1, max(0, int(math.floor(q)))); i1 = min(len(sh["frames"]) - 1, i0 + 1)
        fr = q - math.floor(q)
        if sh.get("ramp") and fr > 0.02 and i1 != i0:              # frame blending between source frames
            img = (sh["frames"][i0].astype(np.float32) * (1 - fr) + sh["frames"][i1].astype(np.float32) * fr).astype(np.uint8)
        else:
            img = sh["frames"][i0 if sh.get("ramp") else min(len(sh["frames"]) - 1, max(0, int(round(sh["src_at"](u) * fps))))].copy()
        for e in fx:
            a = e["at"]
            if e["type"] == "whip" and abs(t - a) < 0.2:
                # outgoing slides out and smears; incoming slides in from the other side, cut at the beat
                # p -1..0: the outgoing shot carries on in its own pan direction; 0..1: the incoming one arrives
                # from behind it; the smear peaks at the cut. Offsets ride a smooth spring, not a fixed ease.
                p = (t - a) / 0.2; d = e["dir"]
                off = d * 0.22 * W * (clamp01(progress(1 + p, start=0, preset="smooth")) if p < 0 else
                                      -(1 - clamp01(progress(p, start=0, preset="smooth"))))
                img = motion_blur(np.roll(img, int(off), axis=1), (1 - abs(p)) * 0.18 * W)
            elif e["type"] == "zoom" and t >= a and t - a < 1.2:
                kz = kick(t, a, 2.2, "snappy")
                vel = (kick(t + 1 / fps, a, 2.2, "snappy") - kz) * fps
                img = radial_zoom(img, 1 + 0.16 * max(0.0, kz), e["centre"], min(0.08, max(0.0, vel) * 0.02))
            elif e["type"] == "rgb" and 0 <= t - a < 0.25:
                amp = 22 * (1 - clamp01((t - a) / 0.25)) ** 2
                dx, dy = amp * math.cos(e["angle"]), amp * math.sin(e["angle"])
                img = np.dstack([shift(img[..., 0], dx, dy), img[..., 1], shift(img[..., 2], -dx, -dy)])
            elif e["type"] == "pop" and e["at"] - 1e-6 <= t < e["until"]:
                amt = clamp01(progress(t, start=e["at"] + 0.15, preset="smooth"))
                img = colour_pop(img, e["hue"], amt)
        for e in fx:                                        # light and type go over the picture
            a = e["at"]
            if e["type"] == "flash" and 0 <= t - a < 0.4:
                f = (1 - clamp01(progress(t, start=a, preset="smooth"))) ** 1.5
                tint = 255 * (1 - 0.35 * clamp01((t - a) / 0.12)) + accent * 0.35 * clamp01((t - a) / 0.12)
                img = (img.astype(np.float32) * (1 - f) + tint * f).astype(np.uint8)
            elif e["type"] == "text" and t >= a:
                nxt = [x["at"] for x in fx if x["type"] == "text" and x["at"] > a]
                t_out = nxt[0] if nxt else a + 1.2
                if t >= t_out + 0.2:
                    continue
                sc = 1.35 - 0.35 * progress(t, start=a, preset="snappy")
                op = clamp01(progress(t, start=a, preset="smooth")) * (1 - clamp01(progress(t, start=t_out, preset="uiExit")))
                im = art.word(e["word"])
                room = W - 2 * safe
                if im.width * sc > room:                      # never wider than the safe area
                    sc *= room / (im.width * sc)
                im = im.resize((max(1, int(im.width * sc)), max(1, int(im.height * sc))), Image.BILINEAR)
                x = safe if e["side"] == "left" else W - safe - im.width
                y = int(H * (0.62 if W >= H else 0.70) - im.height / 2)
                base = Image.fromarray(img)
                if op < 0.999:
                    al = im.getchannel("A").point(lambda v: int(v * op)); im = im.copy(); im.putalpha(al)
                base.paste(im, (int(x + (im.width * 0 if e["side"] == "left" else 0)), y), im)
                img = np.asarray(base)
        if enc is not None:
            enc.stdin.write(np.ascontiguousarray(img).tobytes())
        else:
            stills.append(img)
    if enc is not None:
        enc.stdin.close()
        if enc.wait():
            raise SystemExit("fxpack: encode failed")
    return stills


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("plan"); ap.add_argument("--out", required=True); ap.add_argument("--name")
    ap.add_argument("--fps", type=float); ap.add_argument("--size", default="1920x1080")
    ap.add_argument("--frames", help="stills only, at these edit times (s)")
    ap.add_argument("--plan-only", action="store_true", help="write the timeline + effects JSON and stop")
    prof.add_arg(ap)
    a = ap.parse_args(argv)
    P = prof.load(a.profile)
    plan = json.load(open(a.plan))
    base_dir = os.path.dirname(os.path.abspath(a.plan))
    rel = lambda p: p if os.path.isabs(p) else os.path.join(base_dir, p)
    fps = a.fps or 29.97
    W, H = (int(v) for v in a.size.split("x"))
    name = a.name or os.path.splitext(os.path.basename(a.plan))[0]
    os.makedirs(a.out, exist_ok=True)
    import beatmap
    music = rel(plan["music"]); music_in = float(plan.get("music_in", 0.0))
    bm = beatmap.build(music, start=music_in, fps=fps, bpm=plan.get("bpm"))     # "bpm" in the plan when the tempo is known
    for s in plan["shots"]:
        s["src"] = rel(s["src"])
    tl, origin = build_timeline(plan, bm, fps)
    dur = tl[-1]["end"]
    events = music_events(bm, origin, dur)
    # load and analyse each shot (ramped shots read enough source for their slow part)
    for s in tl:
        info = probe(s["src"]); span = s["end"] - s["start"]
        if s["in"] + span > info["dur"] + 1.0 / fps:
            raise SystemExit(f"fxpack: {s['label']} needs {span:.2f} s from {s['in']:.2f} s but the clip is only {info['dur']:.2f} s long; "
                             f"use an earlier 'in' or fewer beats")
        s["probe"] = info; s["rfps"] = fps
        s["frames"] = read_span(s["src"], s["in"], min(span + 0.1, info["dur"] - s["in"]), (W, H), fps)
        s["src_f0"] = 0
        s["src_at"] = (lambda u: u)
        s["an"] = analyse(s["frames"])
    fx = auto_fx(tl, events, plan, fps, P) if plan.get("fx", "auto") == "auto" else plan["fx"]
    # a ramped shot is re-read at the source's own rate (at least 2x the output) and blended between neighbouring
    # source frames, so slow motion never shows repeated frames
    for e in fx:
        if e["type"] == "ramp":
            s = next(x for x in tl if abs(x["end"] - e["at"]) < 1e-3)
            s["ramp"] = True; s["rfps"] = s["probe"]["fps"]       # the source's own frames: blends never repeat one
            s["frames"] = read_span(s["src"], s["in"], min(s["end"] - s["start"] + 0.1, s["probe"]["dur"] - s["in"]), (W, H), s["rfps"])
    bad = gate(fx, events, fps)
    # speed ramps change how a shot reads its source: slow from `from` to the cut (source time = integral of speed)
    for e in fx:
        if e["type"] == "ramp":
            s = next(x for x in tl if abs(x["end"] - e["at"]) < 1e-3)
            r0, spd = e["from"] - s["start"], e["speed"]
            def src_at(u, r0=r0, spd=spd):
                if u <= r0:
                    return u
                # speed eases 1 -> spd on a smooth spring from r0 (closed-form integral by summing small steps)
                n = 24; dt = (u - r0) / n; acc = 0.0
                for i in range(n):
                    tt = r0 + (i + 0.5) * dt
                    acc += (1 - (1 - spd) * clamp01(progress(tt, start=r0, preset="smooth"))) * dt
                return r0 + acc
            s["src_at"] = src_at
    report = {"name": name, "fps": fps, "size": [W, H], "music": music, "music_in": music_in, "origin": round(origin, 4),
              "bpm": bm["bpm"], "drop": None if bm.get("drop") is None else round(bm["drop"] - origin, 4),
              "shots": [{k: v for k, v in s.items() if k in ("src", "in", "start", "end", "hero", "label")} for s in tl],
              "fx": fx, "gate": "PASS" if not bad else "FAIL",
              "decorative": [{"fx": e, "why": w} for e, w in bad]}
    jp = os.path.join(a.out, f"{name}_fx.json")
    json.dump(report, open(jp, "w"), indent=1)
    if bad:
        for e, w in bad:
            print(f"gate: {e['type']} at {e['at']:.3f} s - {w}", file=sys.stderr)
        print(f"fxpack: {len(bad)} decorative effect(s); nothing rendered (see {jp})", file=sys.stderr)
        return 3
    cuts = [s["start"] for s in tl[1:]]
    print(f"plan: {len(tl)} shots, {dur:.2f} s at {bm['bpm']:.1f} BPM, {len(fx)} effects: "
          + ", ".join(f"{e['type']}@{e['at']:.2f}" for e in fx))
    if a.plan_only:
        return 0
    if a.frames:
        from PIL import Image
        ts = [float(x) for x in a.frames.split(",")]
        for t, im in zip(ts, render(tl, fx, None, music, origin, music_in, fps, (W, H), P, frames_only=ts)):
            p = os.path.join(a.out, f"{name}_fx_t{t:.2f}.jpg"); Image.fromarray(im).save(p, quality=92); print("still", p)
        return 0
    mp4 = os.path.join(a.out, f"{name}_fx.mp4")
    render(tl, fx, mp4, music, origin, music_in, fps, (W, H), P)
    # Premiere XML: the shots as cut (ramped shots at their source span), the music, a marker per effect
    import fcp7xml
    E = {"name": f"{name} fx", "fps": fps, "w": W, "h": H, "files": {}, "items": [], "markers": [],
         "music": [{"path": music, "dur": beatmap.probe_duration(music), "at": 0.0, "in": origin + music_in, "out": origin + music_in + math.ceil(dur * fps - 1e-9) / fps, "gain_db": 0}]}
    for i, s in enumerate(tl):
        key = f"s{i}"
        E["files"][key] = {"path": s["src"], "dur": s["probe"]["dur"], "audio_ch": 2}
        lab = s["label"] + (" (speed ramp in the render)" if any(e["type"] == "ramp" and abs(e["at"] - s["end"]) < 1e-3 for e in fx) else "")
        cf = lambda t: math.ceil(t * fps - 1e-9)               # the cut frame the render uses (frame i shows i/fps)
        i0 = round(s["in"] * fps) / fps
        E["items"].append({"file": key, "in": i0, "out": i0 + (cf(s["end"]) - cf(s["start"])) / fps, "label": lab})
    for e in fx:
        E["markers"].append({"at": e["at"], "name": f"{e['type']}: {e['reason']}"})
    with open(os.path.join(a.out, f"{name}_fx.xml"), "w") as f:
        f.write(fcp7xml.build(E))
    print(f"{mp4} ({dur:.2f} s); qa: --kind edit --cuts {','.join(f'{c:.3f}' for c in cuts)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
