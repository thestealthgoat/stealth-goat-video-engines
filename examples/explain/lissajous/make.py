#!/usr/bin/env python3
"""Why some notes sound good together: an example explainer, harmony drawn as Lissajous figures.

Two tones, one on each axis of an XY scope: the picture closes into a still shape when their frequencies make a small
whole-number ratio, and the smaller the numbers, the simpler the shape (unison 1:1, octave 2:1, fifth 3:2, fourth 4:3,
major third 5:4). A tritone (45:32) takes so long to repeat that it never settles. The surprising truth: a piano's
fifth is not 3:2. Equal temperament makes it 2^(7/12) = 1.4983, so the shape slowly turns; the readout shows how fast
(the beat rate, Hz) for the A it starts on. Every figure is drawn from the actual waveforms, and the soundtrack is
those same two tones (synthesised here, a plain sine pair with a soft envelope: no samples). The tritone, whose
shape cycles too fast for 30 fps, is shown stroboscopically (real windows of the tones, sampled at a slow phase step).
Writes _build/tones.wav, _build/xy.json and storyboard.json (all next to this file). Run from the engine folder:

    python3 examples/explain/lissajous/make.py
    python3 engine/explain.py examples/explain/lissajous/storyboard.json --out out/lissajous --profile demo \
        --music examples/explain/lissajous/_build/tones.wav --music-db -10

With a recorded voice-over (vo.wav in this folder; see VO_SCRIPT.md), retime first, then run this again.
"""
import json, math, os, sys, wave
from fractions import Fraction
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))   # the engine folder (examples/explain/lissajous -> ../../..)
sys.path.insert(0, os.path.join(REPO, "engine"))
import storyboard as sbt   # noqa: E402

SR, FPS, BASE = 48000, 30000 / 1001, 220.0          # the lower tone: A3
BUILD = os.path.join(HERE, "_build")
INTERVALS = [("UNISON", 1, 1), ("OCTAVE", 2, 1), ("FIFTH", 3, 2), ("FOURTH", 4, 3), ("MAJOR THIRD", 5, 4), ("TRITONE", 45, 32)]


def write_wav(path, a):
    pcm = (np.clip(a, -1, 1) * 32767).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.tobytes())


def main():
    os.makedirs(BUILD, exist_ok=True)
    et_fifth = 2 ** (7 / 12)
    beat_hz = abs(BASE * 3 - BASE * et_fifth * 2)          # 3rd harmonic of A vs 2nd harmonic of the tempered E
    # layout: the scope sits left of centre and the words get their own column on the right, clear of the trace (the
    # trace reaches 0.46 x min(w, h) from the scope's centre; the graticule's axis line reaches w / 2) and inside the
    # 4% side margin: a centred line there has 2 x (0.96 - COL) of the width, ~690 px at 1080p
    SX, COL = 0.40, 0.78
    show = lambda extra=(): [{"id": "liss", "type": "scope", "mode": "xy", "src": "xy", "color": "text", "x": SX, "y": 0.47, "w": 0.36, "h": 0.62, "trail": 3}] + list(extra)
    name = lambda s, d=0.0: {"id": "name", "type": "text", "role": "title", "text": s, "x": COL, "y": 0.4, "size": 0.075, "in": d}
    ratio = lambda p, q, d=0.0: {"id": "ratio", "type": "text", "role": "body", "text": f"{p} : {q}", "x": COL, "y": 0.52, "size": 0.05, "color": "hot", "in": d}
    IV = {n: (p, q) for n, p, q in INTERVALS}
    TP, TQ = IV["TRITONE"]
    beats = [
        {"say": "This is what a perfect fifth looks like.", "key": "fifth", "seg": ("FIFTH", 3, 2),
         "show": show([{"id": "eyebrow", "type": "text", "role": "eyebrow", "text": "TWO NOTES, ONE ON EACH AXIS", "x": 0.5, "y": 0.08},
                       {"id": "hit", "type": "burst", "x": SX, "y": 0.47, "at": 0.05, "r": 0.42},
                       {"id": "notes", "type": "text", "role": "title", "text": "A + E", "x": COL, "y": 0.45, "size": 0.07, "in": 1.4}])},
        {"say": "One note moves the dot sideways,", "key": "sideways", "seg": ("FIFTH", 3, 2),
         "show": show([{"id": "slow", "type": "text", "role": "eyebrow", "text": "SLOWED WAY DOWN", "x": SX, "y": 0.08, "in": 0.2},
                       {"id": "lab_x", "type": "text", "role": "eyebrow", "text": "NOTE 1 →", "x": SX, "y": 0.86 - 0.05, "in": 1.0}])},
        {"say": "the other moves it up and down.", "key": "up", "seg": ("FIFTH", 3, 2),
         "show": show([{"id": "slow", "type": "text", "role": "eyebrow", "text": "SLOWED WAY DOWN", "x": SX, "y": 0.08},
                       {"id": "lab_y", "type": "text", "role": "eyebrow", "text": "NOTE 2 ↑", "x": 0.13, "y": 0.47, "in": 1.0}])},
        {"say": "Same note twice: a still circle.", "key": "circle", "seg": ("UNISON", 1, 1),
         "show": show([name("UNISON"), ratio(*IV["UNISON"], 0.3)])},
        {"say": "An octave: twice as fast, a figure eight.", "key": "octave", "seg": ("OCTAVE", 2, 1),
         "show": show([name("OCTAVE"), ratio(*IV["OCTAVE"], 0.3),
                       {"id": "loops", "type": "text", "role": "eyebrow", "text": "2 LOOPS ACROSS, 1 UP", "x": COL, "y": 0.62, "in": 1.6}])},
        {"say": "A fifth: three against two.", "key": "three", "seg": ("FIFTH", 3, 2),
         "show": show([name("FIFTH"), ratio(*IV["FIFTH"], 0.3)])},
        {"say": "Small numbers, simple shapes, and they sound smooth.", "key": "smooth", "seg": ("FOURTH", 4, 3),
         "show": show([name("FOURTH"), ratio(*IV["FOURTH"], 0.3)]), "changes": [{"at": 1.6, "id": "name", "set": {"text": "MAJOR THIRD"}}, {"at": 1.6, "id": "ratio", "set": {"text": "%d : %d" % IV["MAJOR THIRD"]}}],
         "seg2": (1.6, "MAJOR THIRD", 5, 4)},
        {"say": "A tritone is forty five against thirty two.", "key": "tritone", "seg": ("TRITONE", TP, TQ),
         "show": show([name("TRITONE"), ratio(TP, TQ, 0.3),
                       {"id": "loops", "type": "text", "role": "eyebrow", "text": f"{TP} LOOPS BEFORE IT REPEATS", "x": COL, "y": 0.62, "in": 1.5}])},
        {"say": "It never settles, and it sounds tense.", "key": "tense", "seg": ("TRITONE", TP, TQ),
         "show": show([name("TRITONE"), ratio(TP, TQ), {"id": "never", "type": "text", "role": "eyebrow", "text": "NEVER REPEATS IN VIEW", "x": COL, "y": 0.62, "in": 0.8}])},
        {"say": "Here's the twist: a piano's fifth isn't three to two.", "key": "twist", "seg": ("FIFTH", 3, 2), "seg2": (1.8, "ET FIFTH", et_fifth, 1), "drop": True,
         "show": show([name("PIANO FIFTH"), {"id": "ratio", "type": "text", "role": "body", "text": f"1 : {3 / 2:.4f}", "x": COL, "y": 0.52, "size": 0.05, "color": "hot"}]),
         "changes": [{"at": 1.8, "id": "ratio", "set": {"text": f"1 : {et_fifth:.4f}"}}]},
        {"say": "It's tuned a hair flat, so the shape slowly turns.", "key": "turns", "seg": ("ET FIFTH", et_fifth, 1),
         "show": show([name("PIANO FIFTH"), {"id": "ratio", "type": "text", "role": "body", "text": f"1 : {et_fifth:.4f}", "x": COL, "y": 0.52, "size": 0.05, "color": "hot"},
                       {"id": "beat", "type": "readout", "label": "IT TURNS", "value": 0, "decimals": 2, "unit": "Hz", "x": COL, "y": 0.72, "size": 0.05},
                       {"id": "period", "type": "text", "role": "eyebrow", "text": f"ONE TURN EVERY {1 / beat_hz:.2f} S", "x": COL, "y": 0.84 - 0.04, "in": 2.0}]),
         "changes": [{"at": 0.3, "id": "beat", "set": {"value": round(beat_hz, 2)}}]},
        {"say": "Which interval should we draw next?", "key": "next", "seg": ("FIFTH", 3, 2),
         "show": show([{"id": "end", "type": "text", "role": "title", "text": "NEXT?", "x": COL, "y": 0.4, "size": 0.09},
                       {"id": "ask", "type": "text", "role": "eyebrow", "text": "TELL ME IN THE COMMENTS", "x": COL, "y": 0.52, "in": 1.2}])},
    ]
    sb = {"topic": "Why some notes sound good together", "approved": False, "version": 1, "audio": "linear",
          "data": {"xy": "_build/xy.json"}, "beats": beats}
    # timing: the voice-over when it exists (storyboard.py retime --vo vo.wav writes vo.words.json), else paced text;
    # the soundtrack and the scope data are built from these beat times, so they stay in sync with the words
    vo_words = os.path.join(HERE, "vo.words.json")
    if os.path.isfile(vo_words):
        sbt.pace(sb)                                         # retime scales a beat's inner times by its new / old length:
        old = [b["t1"] - b["t0"] for b in sb["beats"]]       # scale this topic's own inner times the same way
        sbt.retime(sb, json.load(open(vo_words))["words"])
        for b, o in zip(sb["beats"], old):
            k = (b["t1"] - b["t0"]) / max(0.01, o)
            if "seg2" in b: at, *rest = b["seg2"]; b["seg2"] = (round(at * k, 3), *rest)
    else:
        sbt.pace(sb, wps=2.7, mn=2.1, pad=0.5)
    B = sb["beats"]; dur = B[-1]["t1"] + 0.6
    # the tones: for each beat, note 1 = BASE, note 2 = BASE * ratio (equal power, 15 ms crossfades between beats)
    n = int(dur * SR); t = np.arange(n) / SR
    f1 = np.full(n, BASE); f2 = np.full(n, BASE)
    for b in B:
        a0, a1 = int(b["t0"] * SR), int((B[B.index(b) + 1]["t0"] if b is not B[-1] else dur) * SR)
        _, p, q = b["seg"]; f2[a0:a1] = BASE * p / q
        if "seg2" in b:
            at, _, p2, q2 = b["seg2"]; f2[int((b["t0"] + at) * SR):a1] = BASE * p2 / q2
    # integrate frequency into phase (no clicks at the changes); a short glide where the ratio changes
    k = int(0.015 * SR); ker = np.ones(k) / k
    f2s = np.convolve(np.pad(f2, (k, k), mode="edge"), ker, mode="same")[k:-k]
    ph1 = 2 * np.pi * np.cumsum(f1) / SR; ph2 = 2 * np.pi * np.cumsum(f2s) / SR
    # each interval starts at a chosen phase so its figure is the textbook one (unison = a circle: 90 degrees apart;
    # the others 0): the correction eases in over the same 15 ms glide, so the tones never click
    target = {(1, 1): np.pi / 2}
    starts = []
    for b in B:
        _, p, q = b["seg"]; starts.append((int(b["t0"] * SR), p / q, target.get((p, q), 0.0)))
        if "seg2" in b:
            at, _, p2, q2 = b["seg2"]; starts.append((int((b["t0"] + at) * SR), p2 / q2, target.get((p2, q2), 0.0)))
    acc = np.zeros(n)
    for a0, r, off in sorted(starts):
        a0 = min(a0, n - 1); a1 = min(a0 + k, n - 1)         # measured once the 15 ms frequency glide has finished
        cur = ph2[a1] + acc[a1] - r * ph1[a1]
        d = (off - cur + np.pi) % (2 * np.pi) - np.pi
        ramp = np.clip((np.arange(n) - a1) / max(1, k), 0, 1)
        acc += d * ramp
    ph2 = ph2 + acc
    x = np.sin(ph1); y = np.sin(ph2)
    env = np.minimum(1, np.minimum(t / 0.3, (dur - t) / 0.8)).clip(0, 1)
    audio = np.stack([x, y], 1) * 0.35 * env[:, None]
    write_wav(os.path.join(BUILD, "tones.wav"), audio)
    # XY frames: the last 1/15 s as a curve (the shape a scope with phosphor shows)
    win = int(SR / 30) * 2; frames = []
    # a ratio change clears the trace: a window never mixes the old figure, the 15 ms glide and the 15 ms phase ease
    # (that mix drew a burst of diagonal strokes on the cut). Until the new figure has a whole period of clean signal the frame
    # keeps the old figure's last clean window; the engine's 3-frame phosphor trail then crossfades old into new.
    segs = []                                              # [start sample, p, q, clean start]
    for a0, p, q in sorted([(int(b["t0"] * SR),) + tuple(b["seg"][1:]) for b in B] +
                           [(int((b["t0"] + b["seg2"][0]) * SR),) + tuple(b["seg2"][2:]) for b in B if "seg2" in b]):
        if segs and segs[-1][1] / segs[-1][2] == p / q: continue        # same interval: the trace runs on
        segs.append([a0, p, q, 0 if not segs else min(n - 1, a0 + 2 * k)])
    # the new figure appears whole: it waits for one full period of itself (q / BASE s) of clean signal, so the first
    # frame is the complete shape, never a stray partial stroke (a stroboscopic figure is computed whole from the start)
    # (the tempered fifth counts as the 3:2 it nearly is)
    minnew = lambda p, q: int(SR * Fraction(p / q).limit_denominator(8).denominator / BASE) if q / BASE <= win / SR else 0
    # a figure whose full period (q / BASE s) is longer than the window never closes in view (the tritone: 32 / 220 =
    # 0.145 s against a 0.067 s window), and its shape cycles at BASE / q = 6.9 Hz: sampled at 29.97 fps that aliases
    # into a frame-to-frame strobe. Those intervals are shown stroboscopically, as a triggered scope does: every frame
    # is a real 1/15 s window of the same two tones, but the window's start advances STROBE x the real time step,
    # so the open lattice drifts smoothly through its true sequence of shapes (one full cycle every q / BASE / STROBE s).
    STROBE = 0.05
    def win_pts(e0, e1, step):
        return np.stack([x[e0:e1:step], y[e0:e1:step]], 1)
    # the two "the dot moves" beats: the dot itself, slowed way down (labelled on screen), first on one axis, then the
    # other; halfway through the second beat both move together and the dot starts drawing the 3:2 figure
    KB = {b["key"]: b for b in B}
    s0, u0, u1 = KB["sideways"]["t0"], KB["up"]["t0"], KB["up"]["t1"]
    def slow_pts(tb):
        trail = np.linspace(-0.22, 0.0, 40)
        if tb < u0:                                          # note 1 alone: side to side
            tt = tb - s0 + trail; return np.stack([0.9 * np.sin(2 * np.pi * 0.55 * tt), 0 * tt], 1)
        tu = tb - u0; half = 0.45 * (u1 - u0)
        if tu < half:                                        # note 2 alone: up and down
            tt = tu + trail; return np.stack([0 * tt, 0.9 * np.sin(2 * np.pi * 0.55 * tt)], 1)
        tt = np.linspace(0.0, tu - half, 300)                # both: the dot draws the fifth (3 across, 2 up), starting
        yh = np.sin(2 * np.pi * 0.55 * half)                 # where the up-and-down dot was (no jump)
        ph = np.arcsin(np.clip(yh, -1, 1)) if np.cos(2 * np.pi * 0.55 * half) >= 0 else np.pi - np.arcsin(np.clip(yh, -1, 1))
        return np.stack([0.9 * np.sin(2 * np.pi * 0.36 * tt), 0.9 * np.sin(2 * np.pi * 0.24 * tt + ph)], 1)
    for i in range(int(dur * FPS)):
        if s0 <= i / FPS < u1:
            frames.append([round(float(v), 3) for v in slow_pts(i / FPS).ravel()]); continue
        c = min(n - 1, int(i / FPS * SR))
        j = max(m for m in range(len(segs)) if segs[m][0] <= c)
        a0, p, q, cs = segs[j]
        if j > 0 and c - cs < max(16, minnew(p, q)):                       # not enough of the new figure yet: hold the old one
            j -= 1; a0, p, q, cs = segs[j]
        if j + 1 < len(segs): c = min(c, segs[j + 1][0] - k)   # the centred 15 ms glide starts k / 2 before a change
        if q / BASE > win / SR:                              # stroboscopic (see above), from the exact phases
            u = (c - cs) / SR * STROBE                       # strobe time since the clean start
            tt = u + np.linspace(0, win / SR, 800)
            p1, p2 = ph1[cs], ph2[cs]
            pts = np.stack([np.sin(p1 + 2 * np.pi * BASE * tt), np.sin(p2 + 2 * np.pi * BASE * p / q * tt)], 1)
        else:
            a = max(cs, c - win)
            if c - a < 16: frames.append([]); continue
            pts = win_pts(a, c, max(1, (c - a) // 400))
        frames.append([round(float(v), 3) for v in pts.ravel()])
    tri_cycle = TQ / BASE / STROBE
    json.dump({"fps": FPS, "t0": 0.0, "mode": "xy", "frames": frames}, open(os.path.join(BUILD, "xy.json"), "w"), separators=(",", ":"))
    for b in B:
        b.pop("seg", None); b.pop("seg2", None)
        if b.get("drop"): sb["drop_at"] = b["t0"]
    sb["duration"] = round(dur, 3)
    sb["measured"] = {"base_hz": BASE, "et_fifth_ratio": round(et_fifth, 5), "et_fifth_beat_hz": round(beat_hz, 3)}
    sbt.save(sb, os.path.join(HERE, "storyboard.json"))
    print(f"equal-tempered fifth 1:{et_fifth:.4f}, turns {beat_hz:.2f} Hz on A{BASE:.0f}; {len(B)} beats, {dur:.1f} s")
    print(f"tritone {TP}:{TQ}: full period {TQ / BASE * 1000:.1f} ms (window {win / SR * 1000:.1f} ms), shape cycle {BASE / TQ:.2f} Hz,"
          f" shown stroboscopically: one cycle every {tri_cycle:.1f} s")


if __name__ == "__main__":
    main()
