#!/usr/bin/env python3
"""behind.py - O3 text behind the person and T2 big words behind the speaker's head, on the O2 matte.

behind.py <video> --out <dir> [--name N] [--t0 S] [--t1 S] [--profile P]
          (--text "WORD" | --events events.json | --auto <words.json>) [--every 3.5] [--matte <name>_matte.mp4]
          [--fill solid|gradient|<image>] [--color text|accent|'#hex'] [--size 0.30] [--layer] [--frames 1.0,2.0]

Layers, back to front: the shot -> the text -> the person (engine/matte.py, run here first unless --matte points at an
existing <name>_matte.mp4 made from the same window). The text sits in front of the background and behind the
person, so the speaker stands in front of their own word.
  --text "FAITH"        one word for the whole window (O3)
  --events file.json    [{"text": "FAITH", "t0": 1.2, "t1": 3.4}, ...] (seconds in the window) (O3)
  --auto words.json     T2: a faster-whisper word file (captions.py / talkedit.py / hopwords.py write one; times in
                        source seconds). One word per phrase is picked (likely nouns after "my / your / the",
                        words said more than once, emphasis words, numbers, names), at least --every s apart; each shows from just before it is said to the end
                        of its phrase (1.2-3.5 s).
Look: the profile's head font, as big as the frame allows (cap height --size of the frame height, never wider than
the safe area), centred on the speaker's head and set so it rises from behind the head and shoulders (found from the
matte at the word's first frame). --fill solid (--color, default the profile text colour), gradient (the profile's
brand.gradient, else accent -> text), or an image path (the picture shows through the letters).
Motion (engine/spring.py): in = scale 1.35 -> 1 (snappy) and opacity (ui, never overshoots); a slow push while it
holds (critically damped, slow); out = fade (smooth, ~0.3 s). A pure function of t.
Outputs: <name>_behind.mp4 (the window's sound cut sample-exactly, a faint room tone under it, levelled to the
profile's delivery loudness), --layer: <name>_behind_text_Alpha.mov (the text with the
person cut out of it, ProRes 4444, to lay over the original in Premiere), <name>_behind.events.json (what was shown).
"""
import argparse, json, math, os, subprocess, sys

import numpy as np
import cv2

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import vprofile as prof                     # noqa: E402
from spring import spring_at, clamp01        # noqa: E402
import matte as M                            # noqa: E402


FADE_S = 0.7                 # a word's fade-out runs this long after its t1 (the smooth spring settles in ~0.62 s)
DETS = set("my your his her our their own the a an this that these those every each one".split())
WEAK = set("""become became becomes stand stands standing stood before after front middle right left there here came
comes coming going goes went gone make makes made take takes took give gives gave want wants wanted thing things
something anything really actually about would could should might being been doing done said says tell told know
knew think thought look looks looked again still even just only also very much many most more less other another
people person man men woman women time times way ways part kind lot every each both same all some any none
enough whole sure okay yeah half single double""".split())


def pick_words(words, t0, t1, every):
    """T2: one keyword per phrase from a words.json (source seconds) -> events in window seconds. A word scores for
    its length, for following "my / your / the / a ..." (likely a noun: "your children", "a chain"), for being said
    more than once in the window (the theme), and for emphasis (talkedit's intensifiers, numbers, a name mid-phrase);
    common verbs and position words never qualify."""
    import captions as C
    try:
        from talkedit import INTENSIFIERS
    except Exception:                                            # noqa: BLE001
        INTENSIFIERS = set()
    ws = [dict(w) for w in words if t0 <= float(w["s"]) < t1 - 0.6]
    for w in ws:
        w["s"], w["e"] = float(w["s"]) - t0, float(w.get("e", float(w["s"]) + 0.3)) - t0
    count = {}
    for w in ws:
        count[C.bare(w["w"])] = count.get(C.bare(w["w"]), 0) + 1
    caps = C.group(ws) if ws else []
    ev, last = [], -1e9
    for c in caps:
        best, best_sc = None, 0.0
        forced = [w for w in c["words"] if w.get("key") is True]      # words.json "key": true / false are obeyed
        for k, w in enumerate(c["words"]):
            b = C.bare(w["w"])
            if w.get("key") is False or not b or b in C.STOP or b in WEAK or (len(b) < 4 and not b.isdigit()):
                continue
            prev = C.bare(c["words"][k - 1]["w"]) if k else ""
            if len(b) > 5 and b.endswith(("ed", "ing")) and b not in INTENSIFIERS and prev not in DETS:
                continue                                            # likely a verb ("the meeting" stays)
            sc = min(len(b), 8) + (4 if prev in DETS else 0) + (3 if count.get(b, 0) > 1 else 0) \
                + (4 if b in INTENSIFIERS else 0) + (5 if any(ch.isdigit() for ch in b) else 0) \
                + (3 if w["w"][:1].isupper() and k > 0 else 0)
            if sc > best_sc:
                best, best_sc = w, sc
        if forced:
            best, best_sc = forced[0], 99
        if best is None or best_sc < 7:
            continue
        w = best
        if w["s"] - last < every:
            continue
        a = max(0.0, w["s"] - 0.15)
        b = min(t1 - t0, max(a + 1.2, min(a + 3.5, c["last"] + 0.35)))
        if ev and a < ev[-1]["t1"] + FADE_S:                       # the last word has faded out first
            continue
        ev.append({"text": w["w"].strip(".,!?;:\"'").upper(), "t0": round(a, 3), "t1": round(b, 3)})
        last = w["s"]
    return ev


class Word:
    """One word, rendered once at its base size as an RGBA layer (fill already applied)."""

    def __init__(self, text, P, W, H, size, fill, color, safe):
        from PIL import Image, ImageDraw, ImageFont
        font_path = P.font("head")
        cap = size * H
        f = ImageFont.truetype(font_path, 100)
        hb = -f.getbbox("H", anchor="ls")[1]
        fs = int(100 * cap / max(1, hb))
        maxw = W - 2 * safe
        while True:
            f = ImageFont.truetype(font_path, fs)
            l, t, r, b = f.getbbox(text, anchor="ls")
            if r - l <= maxw or fs < 24:
                break
            fs = int(fs * 0.95)
        pad = int(fs * 0.1)
        w, h = int(r - l + 2 * pad), int(b - t + 2 * pad)
        mask = Image.new("L", (w, h), 0)
        ImageDraw.Draw(mask).text((pad - l, pad - t), text, font=f, fill=255, anchor="ls")
        rgb = self._fill(fill, color, P, w, h)
        self.img = np.dstack([rgb, np.asarray(mask)]).astype(np.uint8)
        self.cap_px = -t                                     # baseline offset inside the image
        self.w, self.h = w, h

    @staticmethod
    def _fill(fill, color, P, w, h):
        if fill == "gradient":
            grad = P.get("brand.gradient", None)
            stops = [c for c in grad] if grad and len(grad) >= 2 else [P.color("accent"), P.color("text")]
            stops = np.array([[int(c.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)] for c in stops], np.float32)
            x = np.linspace(0, len(stops) - 1, w)
            i0 = np.clip(x.astype(int), 0, len(stops) - 2); fr = (x - i0)[:, None]
            row = stops[i0] * (1 - fr) + stops[i0 + 1] * fr
            return np.repeat(row[None], h, 0)
        if fill and os.path.isfile(fill):
            im = cv2.cvtColor(cv2.imread(fill), cv2.COLOR_BGR2RGB)
            k = max(w / im.shape[1], h / im.shape[0])
            im = cv2.resize(im, (int(im.shape[1] * k) + 1, int(im.shape[0] * k) + 1), interpolation=cv2.INTER_AREA)
            y0, x0 = (im.shape[0] - h) // 2, (im.shape[1] - w) // 2
            return im[y0:y0 + h, x0:x0 + w].astype(np.float32)
        c = P.color(color) if color in (P.get("brand.colors") or {}) else color
        rgb = [int(c.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)]
        return np.full((h, w, 3), rgb, np.float32)


def head_anchor(alpha, W, H):
    """(head centre x, head top y) from a matte frame; frame centre / upper third when there's no person."""
    m = alpha > 0.5
    rows = np.where(m.any(1))[0]
    if len(rows) < 8:
        return W / 2, H * 0.35
    top = rows[0]
    band = m[top:top + max(8, int(0.12 * H))]
    xs = np.where(band.any(0))[0]
    return float(xs.mean()) if len(xs) else W / 2, float(top)


def main(argv=None):
    ap = argparse.ArgumentParser(description="text behind the person")
    ap.add_argument("video"); ap.add_argument("--out", required=True); ap.add_argument("--name")
    ap.add_argument("--t0", type=float, default=0.0); ap.add_argument("--t1", type=float)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--text"); g.add_argument("--events"); g.add_argument("--auto", help="words.json: one keyword per phrase, picked automatically")
    ap.add_argument("--every", type=float, default=3.5, help="--auto: seconds between words at least")
    ap.add_argument("--matte", help="an existing <name>_matte.mp4 of this window (else matte.py runs first)")
    ap.add_argument("--fill", default="solid"); ap.add_argument("--color", default="text")
    ap.add_argument("--size", type=float, default=0.30, help="cap height as a share of the frame height")
    ap.add_argument("--rotate", choices=["cw", "ccw", "180"]); ap.add_argument("--layer", action="store_true")
    ap.add_argument("--frames"); ap.add_argument("--max-height", type=int, default=1080)
    prof.add_arg(ap)
    a = ap.parse_args(argv)
    P = prof.load(a.profile)
    os.makedirs(a.out, exist_ok=True)
    name = a.name or os.path.splitext(os.path.basename(a.video))[0]
    W0, H0, fn, fd, dur = M.probe(a.video)
    if a.rotate in ("cw", "ccw"):
        W0, H0 = H0, W0
    fps = fn / fd
    t1 = min(dur, a.t1) if a.t1 else dur
    sc = min(1.0, a.max_height / min(W0, H0))          # caps the short side: a portrait clip stays 1080 wide
    W, H = int(round(W0 * sc / 2)) * 2, int(round(H0 * sc / 2)) * 2
    span = t1 - a.t0

    if a.text:
        events = [{"text": a.text, "t0": 0.0, "t1": round(span, 3)}]
    elif a.events:
        events = json.load(open(a.events))
    else:
        events = pick_words(json.load(open(a.auto))["words"], a.t0, t1, a.every)
    if not events:
        sys.exit("behind: no words to show")
    json.dump(events, open(os.path.join(a.out, f"{name}_behind.events.json"), "w"), indent=1)
    print(f"behind: {len(events)} word(s): " + ", ".join(f"{e['text']}@{e['t0']:.1f}" for e in events))

    stills = sorted(float(x) for x in a.frames.split(",")) if a.frames else None
    matte_mp4 = a.matte
    if not matte_mp4:
        mt1 = min(t1, a.t0 + stills[-1] + 3.0 / fps) if stills else t1      # stills only need the matte up to them
        margs = [a.video, "--out", a.out, "--name", name, "--t0", str(a.t0), "--t1", str(mt1), "--profile", P.name,
                 "--max-height", str(a.max_height)] + (["--rotate", a.rotate] if a.rotate else [])
        M.main(margs)
        matte_mp4 = os.path.join(a.out, f"{name}_matte.mp4")
    else:                                                       # an existing matte must be this window
        mj = os.path.splitext(matte_mp4)[0] + ".json"
        if os.path.isfile(mj):
            m = json.load(open(mj))
            if abs(float(m.get("t0", a.t0)) - a.t0) > 0.02 or float(m.get("t1", t1)) < t1 - 0.05:
                sys.exit(f"behind: {matte_mp4} covers {m.get('t0')}-{m.get('t1')} s, this run needs {a.t0}-{t1} s")

    turn = {"cw": "transpose=1,", "ccw": "transpose=2,", "180": "hflip,vflip,"}.get(a.rotate, "")
    src = subprocess.Popen(["ffmpeg", "-nostdin", "-v", "error", "-ss", f"{a.t0:.3f}", "-i", a.video, "-t", f"{span:.3f}",
                            "-vf", f"{turn}scale={W}:{H}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                           stdout=subprocess.PIPE, stdin=subprocess.DEVNULL)
    mat = subprocess.Popen(["ffmpeg", "-nostdin", "-v", "error", "-i", matte_mp4, "-vf", f"scale={W}:{H}",
                            "-f", "rawvideo", "-pix_fmt", "gray", "-"], stdout=subprocess.PIPE, stdin=subprocess.DEVNULL)
    safe = int(P.get("layout.safe_px", 90) * H / 1080)
    words = {}
    place = {}
    base = os.path.join(a.out, f"{name}_behind")
    encs = []
    if not stills:
        has_audio = bool(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index",
                                         "-of", "csv=p=0", a.video], capture_output=True, text=True,
                                        stdin=subprocess.DEVNULL).stdout.strip())
        # the sound is cut sample-exactly in a filter (an input-side seek can be ~1 s off on edit-list files)
        lufs, tp = P.get("delivery.loudness_lufs", -14), P.get("delivery.true_peak_db", -2)
        # sample-exact cut, levelled to the profile's delivery loudness, then a faint pink room tone (~-56 dB) under
        # it, so a gated camera track is never digital silence or dead air (ready to post)
        graph = (f"[1:a]atrim=start={a.t0:.4f}:duration={span:.4f},asetpts=PTS-STARTPTS,aresample=48000,"
                 f"aformat=channel_layouts=stereo,loudnorm=I={lufs}:TP={tp - 1}:LRA=11,aresample=48000[v];"
                 f"anoisesrc=color=pink:amplitude=0.008:sample_rate=48000:duration={span:.4f},"   # ~-56 dB room tone
                 f"aformat=channel_layouts=stereo[n];[v][n]amix=inputs=2:duration=first:normalize=0[a]")
        aud = (["-i", a.video, "-filter_complex", graph, "-map", "0:v", "-map", "[a]", "-c:a", "aac", "-b:a", "192k"]
               if has_audio else ["-map", "0:v"])
        encs.append(subprocess.Popen(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
                                      "-s", f"{W}x{H}", "-framerate", f"{fn}/{fd}", "-i", "-", *aud, "-c:v", "libx264",
                                      "-crf", "17", "-preset", "slow", "-pix_fmt", "yuv420p", "-threads", "4",
                                      "-t", f"{span:.4f}", "-movflags", "+faststart", base + ".mp4"],
                                     stdin=subprocess.PIPE))
        if a.layer:
            encs.append(subprocess.Popen(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgba",
                                          "-s", f"{W}x{H}", "-framerate", f"{fn}/{fd}", "-i", "-", "-c:v", "prores_ks",
                                          "-profile:v", "4444", "-pix_fmt", "yuva444p10le", "-threads", "4",
                                          base + "_text_Alpha.mov"], stdin=subprocess.PIPE))
    i = 0
    while True:
        bf = src.stdout.read(W * H * 3); bm = mat.stdout.read(W * H)
        if len(bf) < W * H * 3 or len(bm) < W * H:
            break
        t = i / fps
        frame = np.frombuffer(bf, np.uint8).reshape(H, W, 3)
        al = np.frombuffer(bm, np.uint8).reshape(H, W).astype(np.float32) / 255.0
        txt_rgb = np.zeros((H, W, 3), np.float32); txt_a = np.zeros((H, W), np.float32)
        for k, e in enumerate(events):
            if not (e["t0"] <= t < e["t1"] + FADE_S):
                continue
            if k not in words:
                words[k] = Word(e["text"], P, W, H, a.size, a.fill, a.color, safe)
            wd = words[k]
            if k not in place:                                       # anchor on the head at the word's first frame
                hx, ht = head_anchor(al, W, H)
                cx = min(max(hx, safe + wd.w / 2), W - safe - wd.w / 2)
                cy = min(max(ht + 0.02 * H, safe + wd.h / 2), H * 0.62)
                place[k] = (cx, cy)
            cx, cy = place[k]
            lt = t - e["t0"]
            # in: 1.12 -> 1 (snappy); hold: a slow push (critically damped, omega 1.2: still moving after 3 s)
            s = spring_at(lt, 1.35, 1.0, 0.0, "snappy") * (1 + 0.04 * clamp01(spring_at(lt, 0, 1, 0.0, zeta=1.0, omega=1.2)))
            op = clamp01(spring_at(lt, 0, 1, 0.0, "ui"))
            if t >= e["t1"]:
                op *= 1 - clamp01(spring_at(t - e["t1"], 0, 1, 0.0, "smooth"))
                s *= 1 - 0.03 * clamp01(spring_at(t - e["t1"], 0, 1, 0.0, "smooth"))
            if op <= 0.003:
                continue
            Mx = np.array([[s, 0, cx - s * wd.w / 2], [0, s, cy - s * wd.h / 2]], np.float32)
            lay = cv2.warpAffine(wd.img, Mx, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
            la = lay[..., 3].astype(np.float32) / 255.0 * op
            txt_rgb = txt_rgb * (1 - la[..., None]) + lay[..., :3].astype(np.float32) * la[..., None]
            txt_a = txt_a + la * (1 - txt_a)
        # txt_rgb is premultiplied by txt_a (the "over" sums above): un-premultiply once for the straight colour
        straight = txt_rgb / np.maximum(txt_a, 1e-6)[..., None]
        vis = txt_a * (1 - al)                                       # the person stands in front of the word
        out = frame.astype(np.float32) * (1 - vis[..., None]) + straight * vis[..., None]
        out = out.clip(0, 255).astype(np.uint8)
        if stills:
            if any(abs(t - x) < 0.5 / fps for x in stills):
                p = f"{base}_t{t:.2f}.png"; cv2.imwrite(p, cv2.cvtColor(out, cv2.COLOR_RGB2BGR)); print("still", p)
            if t > stills[-1]:
                break
        else:
            encs[0].stdin.write(out.tobytes())
            if a.layer:
                encs[1].stdin.write(np.dstack([straight.clip(0, 255).astype(np.uint8), (vis * 255).astype(np.uint8)]).tobytes())
        i += 1
    for p in (src, mat):
        if p.poll() is None:
            p.stdout.close(); p.terminate()
        p.wait()
    bad = 0
    for e in encs:
        e.stdin.close(); bad += e.wait() != 0
    if i == 0:
        sys.exit("behind: no frames read (check the clip, the window and the matte)")
    if bad:
        sys.exit("behind: the encoder failed")
    if not stills:
        print(f"  wrote {base}.mp4" + (f" and {base}_text_Alpha.mov" if a.layer else "") + f" ({i} frames)")


if __name__ == "__main__":
    main()
