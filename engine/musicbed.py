#!/usr/bin/env python3
"""musicbed.py - a simple music bed synthesised in code (numpy): no samples, no licences, no AI.

musicbed.py <out.wav> --dur 60 [--bpm 92] [--drop 41.4] [--key D] [--prog 1,5,6,4] [--seed 3]

Warm pad chords (one per bar, I-V-vi-IV by default), a soft plucked arpeggio on eighth notes, a noise swell into the
drop, and from the drop on a kick on beats 1 and 3 plus a sine bass on the chord roots. The bar grid is placed so a
bar starts exactly on --drop and starts the chord progression (the explainer's payoff beat: storyboard "drop_at"). Fades in over 1 s and out over 2 s.
48 kHz stereo 16-bit WAV, peak -3 dBFS; explain.py levels the final mix to the profile's loudness.
Writes <out>.json with the bar times (for qa --cuts or edits that snap to bars).
"""
import argparse, json, math, os, wave
import numpy as np

SR = 48000
NOTES = {"C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3, "E": 4, "F": 5, "F#": 6, "Gb": 6, "G": 7, "G#": 8,
         "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11}
MAJOR = [0, 2, 4, 5, 7, 9, 11]


def hz(midi):
    return 440.0 * 2 ** ((midi - 69) / 12)


def chord(key, degree):
    """Triad (MIDI notes around C4) for a scale degree 1-7 in a major key."""
    root = 60 + NOTES[key]
    return [root + MAJOR[(degree - 1 + k) % 7] + 12 * ((degree - 1 + k) // 7) for k in (0, 2, 4)]


def pad(freq, n, rng):
    t = np.arange(n) / SR
    out = np.zeros((n, 2))
    for ch, det in ((0, -0.12), (1, 0.12)):
        f = freq * 2 ** (det / 12 / 10)
        s = sum((0.6 ** h) * np.sin(2 * np.pi * f * (h + 1) * t + rng.uniform(0, 6.28)) for h in range(5))
        out[:, ch] = s
    att = np.minimum(1, t / 0.6); rel = np.minimum(1, (t[-1] - t) / 0.5 + 1e-9)
    return out * (att * rel)[:, None]


def pluck(freq, n):
    t = np.arange(n) / SR
    # 25 ms attack: a soft pluck (an instant attack reads as a click and as a hard audio jump at a cut on the beat)
    s = (np.sin(2 * np.pi * freq * t) + 0.3 * np.sin(4 * np.pi * freq * t)) * np.exp(-t * 7) * np.minimum(1, t / 0.025)
    return np.stack([s, s], 1)


def kick(n):
    t = np.arange(n) / SR
    f = 45 + 75 * np.exp(-t * 28)
    s = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 9) * np.minimum(1, t / 0.010)   # a 10 ms thump: no hard audio jump when a cut lands on it
    return np.stack([s, s], 1)


def main(argv=None):
    ap = argparse.ArgumentParser(description="synthesized music bed")
    ap.add_argument("out"); ap.add_argument("--dur", type=float, required=True)
    ap.add_argument("--bpm", type=float, default=92); ap.add_argument("--drop", type=float)
    ap.add_argument("--key", default="D"); ap.add_argument("--prog", default="1,5,6,4")
    ap.add_argument("--seed", type=int, default=3)
    a = ap.parse_args(argv)
    rng = np.random.default_rng(a.seed)
    beat = 60.0 / a.bpm; bar = 4 * beat
    drop = a.drop if a.drop is not None else a.dur * 0.6
    origin = drop - math.ceil(drop / bar) * bar            # a bar starts on the drop
    n = int(a.dur * SR) + SR
    mix = np.zeros((n, 2))
    prog = [int(x) for x in a.prog.split(",")]
    kd = int(round((drop - origin) / bar))                  # the drop bar starts the progression (on the I chord)
    bars = []
    k = 0
    while origin + k * bar < a.dur:
        t0 = origin + k * bar
        bars.append(round(t0, 4))
        ch = chord(a.key, prog[(k - kd) % len(prog)])
        i0 = int(max(0, t0) * SR); i1 = int(min(a.dur, t0 + bar) * SR)
        if i1 > i0:
            seg = sum(pad(hz(m - 12), i1 - i0, rng) for m in ch) * 0.09
            mix[i0:i1] += seg
        after = t0 >= drop - 1e-6
        for e in range(8):                                   # eighth-note arpeggio
            te = t0 + e * beat / 2
            if te < 0 or te >= a.dur or (te < drop and e % 2):
                continue
            m = ch[[0, 1, 2, 1][e % 4]] + 12
            j = int(te * SR); L = min(int(0.6 * SR), n - j)
            mix[j:j + L] += pluck(hz(m), L) * (0.07 if after else 0.05)
        if after:
            for bt in (0, 2):
                j = int((t0 + bt * beat) * SR); L = min(int(0.5 * SR), n - j)
                if 0 <= j < n:
                    mix[j:j + L] += kick(L) * 0.5
            j = max(0, int(t0 * SR)); L = min(int(bar * SR), n - j)
            tt = np.arange(L) / SR
            bass = np.sin(2 * np.pi * hz(ch[0] - 24) * tt) * np.minimum(1, tt / 0.02) * np.exp(-tt * 0.8) * 0.22
            mix[j:j + L] += np.stack([bass, bass], 1)
        k += 1
    j0, j1 = int(max(0, drop - bar) * SR), min(n, int(drop * SR))   # noise swell into the drop (inside the file)
    if j1 > j0:
        sw = rng.standard_normal((j1 - j0, 2)) * np.linspace(0, 1, j1 - j0)[:, None] ** 3 * 0.05
        sw = np.cumsum(sw, 0) * 0.02 + sw * 0.5                # darker noise
        mix[j0:j1] += sw
    mix = mix[:int(a.dur * SR)]
    tt = np.arange(len(mix)) / SR
    mix *= (np.minimum(1, tt / 1.0) * np.minimum(1, (a.dur - tt) / 2.0))[:, None]
    mix *= 10 ** (-3 / 20) / max(1e-9, np.abs(mix).max())
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with wave.open(a.out, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((mix * 32767).astype("<i2").tobytes())
    json.dump({"bpm": a.bpm, "drop": drop, "bars": [b for b in bars if b >= 0]}, open(a.out + ".json", "w"), indent=1)
    print(f"music bed: {a.out} ({a.dur:.1f} s, {a.bpm:g} bpm, drop on a bar at {drop:.2f} s)")


if __name__ == "__main__":
    main()
