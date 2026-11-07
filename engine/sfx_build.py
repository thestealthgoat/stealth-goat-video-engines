#!/usr/bin/env python3
"""Synthesize a beat-synced build -> impact -> sub drop (no samples, no licence).
sfx_build.py <out.wav> --bpm 152 --beats 8 --tail 2.2
The file starts `beats` beats before the hit (hit time inside the file = beats*60/bpm) and runs `tail` s after it.
Build: snare roll that doubles each bar (quarters, eighths, sixteenths, 32nds) rising -14 -> -2 dB, plus a
noise riser sweeping 400 Hz -> 9 kHz. Hit: short crash + sub drop (110 -> 28 Hz). Starts and ends with fades.
"""
import sys, wave
import numpy as np

SR = 48000


def arg(k, d):
    a = sys.argv
    return float(a[a.index(k) + 1]) if k in a else d


def onepole_lp(x, fc):
    """time-varying one-pole low-pass; fc: array of cutoff Hz per sample"""
    a = np.exp(-2 * np.pi * fc / SR)
    y = np.empty_like(x); s = 0.0
    for i in range(len(x)):
        s = (1 - a[i]) * x[i] + a[i] * s
        y[i] = s
    return y


def main():
    out = sys.argv[1]
    bpm, nb, tail = arg('--bpm', 152), int(arg('--beats', 8)), arg('--tail', 2.2)
    beat = 60 / bpm; T = nb * beat; n = int((T + tail) * SR)
    rng = np.random.default_rng(7)
    mix = np.zeros(n)
    # snare roll: per beat subdivision grows 1,1,1,1,2,2,4,8
    subdiv = ([1] * (nb // 2) + [2] * (nb // 4) + [4] * max(nb // 8, 1) + [8] * max(nb - nb // 2 - nb // 4 - max(nb // 8, 1), 1))[:nb]
    hits = []
    for bi, sd in enumerate(subdiv):
        for k in range(sd):
            hits.append(bi * beat + k * beat / sd)
    for j, t0 in enumerate(hits):
        prog = t0 / T
        g = 10 ** ((-14 + 12 * prog) / 20)
        nxt = hits[j + 1] if j + 1 < len(hits) else T
        L = int(min(0.16, nxt - t0 + 0.02) * SR)
        tt = np.arange(L) / SR
        noise = rng.standard_normal(L)
        noise = np.diff(np.concatenate([[0], noise]))  # tilt to the top end
        body = 0.5 * np.sin(2 * np.pi * 190 * tt) * np.exp(-tt / 0.035)
        s = (0.6 * noise * np.exp(-tt / 0.055) + body) * g
        s *= np.minimum(1, tt / 0.002)  # 2 ms attack
        i0 = int(t0 * SR)
        mix[i0:i0 + L] += s[:max(0, min(L, n - i0))]
    # noise riser up to the hit
    Lr = int(T * SR); tt = np.arange(Lr) / SR; p = tt / T
    fc = 400 * (9000 / 400) ** p
    r = onepole_lp(rng.standard_normal(Lr) * 0.7, fc) * 10 ** ((-28 + 22 * p ** 1.3) / 20) * 4
    r[-int(0.008 * SR):] *= np.linspace(1, 0, int(0.008 * SR))
    mix[:Lr] += r
    # impact: crash + sub drop
    h = int(T * SR); Lt = n - h; tt = np.arange(Lt) / SR
    crash = np.diff(np.concatenate([[0], rng.standard_normal(Lt)])) * np.exp(-tt / 0.45) * 10 ** (-14 / 20)
    k = np.log(110 / 28) / max(tail * 0.8, 0.1)
    sub = np.sin(2 * np.pi * 110 * (1 - np.exp(-k * tt)) / k) * np.exp(-1.0 * tt) * (1 - np.exp(-tt / 0.008)) * 10 ** (-3 / 20)
    mix[h:] += crash * np.minimum(1, tt / 0.002) + sub
    # fades: in 50 ms, out 0.4 s
    mix[:int(0.05 * SR)] *= np.linspace(0, 1, int(0.05 * SR))
    mix[-int(0.4 * SR):] *= np.linspace(1, 0, int(0.4 * SR))
    mix *= 10 ** (-3 / 20) / max(np.abs(mix).max(), 1e-9)
    pcm = (np.clip(mix, -1, 1) * 32767).astype(np.int16)
    st = np.stack([pcm, pcm], 1).ravel()
    with wave.open(out, 'w') as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(st.tobytes())
    print(f'wrote {out} {n / SR:.2f}s, hit at {T:.3f}s')


if __name__ == '__main__':
    main()
