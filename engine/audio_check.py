#!/usr/bin/env python3
"""Standing rule: no video ships with a drastic audio cut — everything fades, even if quickly.
audio_check.py <video> [--cuts 1.6,8.2,...] [--drop 18] [--floor -32]
Scans the finished mix in 5 ms windows and FAILS on any sudden level change: a drop of >= --drop dB from above
--floor dBFS within 10 ms (a hard cut-off), or, at the given cut times (+-60 ms), a jump either way >= --drop dB.
Natural attacks (whistles, hits) are rises mid-clip, so only drops are judged away from cuts.
A step into or out of silence (under -60 dBFS: digital zero or codec residue) has no meaningful dB size, so it is
judged in 1 ms peak blocks against the level of the 80 ms next to it: it is a fade when the sound's last (or first)
2 ms of signal are at least 15 dB under that level (a cut stops or starts at the music's own level) and its audible
part, from 3 dB to 20 dB under that level, changes slower than --drop dB per 10 ms (at the default --drop 18 a
linear fade of about 16 ms or longer passes). Anything else at a silence edge is a cut.
Prints PASS or FAIL with timestamps; exit code 1 on FAIL, 2 when there is no audio to check (or it can't be read).
"""
import sys, subprocess
import numpy as np

SILENT = -60.0   # dBFS: a 5 ms window this quiet is silence (digital zero or AAC residue); a dB step into it
                 # has no meaningful size, so steps into/out of it are judged by the fade around them
HI_DB, LO_DB = -3.0, -20.0   # the audible part of a fade: from 3 dB to 20 dB under the level next to it
EDGE_DB = -15.0  # a fade's first/last 2 ms of signal are at least 15 dB under that level; a cut's are not
SIG_DB = -40.0   # "any signal" for finding that edge (above codec residue)
BLK = 48         # 1 ms peak blocks (sample-accurate enough that a cut's position inside a 5 ms window doesn't matter)
CTX = 16         # level reference: 80 ms of 5 ms windows next to the silence


def arg(k, d=None):
    a = sys.argv
    return a[a.index(k) + 1] if k in a else d


def _peaks(x, a, b):
    a, b = max(0, a), min(len(x), b)
    b = a + (b - a) // BLK * BLK
    return np.abs(x[a:b]).reshape(-1, BLK).max(1)


def _soft(p, drop):
    """1 ms peaks p, ordered away from the silence (p[0] touches it): was this edge a fade, not a cut?
    A fade starts from (next to) nothing: the sound's first/last 2 ms with any signal (> -40 dB) stay EDGE_DB under
    the level beside them (a cut lands at the music's own level, however loud or quiet the music is just there); and
    its audible part (-3 to -20 dB under that level, on a 5 ms running median of the peaks) takes longer than a
    `drop` dB per 10 ms change would.
    The level is the 75th percentile of p, so the music's own peaks and dips don't move it much."""
    if not len(p):
        return False
    ref = np.percentile(p, 75)
    sig = np.where(p >= ref * 10 ** (SIG_DB / 20))[0]
    if ref <= 0 or not len(sig) or p[sig[0]:sig[0] + 2].max() > ref * 10 ** (EDGE_DB / 20):
        return False
    env = np.array([np.median(p[max(0, k - 2):k + 3]) for k in range(len(p))])   # 5 ms running median: the fade's
    hi, lo = np.where(env >= ref * 10 ** (HI_DB / 20))[0], np.where(env >= ref * 10 ** (LO_DB / 20))[0]  # shape
    if not len(hi):
        return True    # never back at the level beside it within 80 ms: a long, slow fade
    return (hi[0] - lo[0]) * drop > 10 * (HI_DB - LO_DB)


def soft_into_silence(x, j, drop):
    """Window j is the first silent window after the sound: did it fade out?"""
    return _soft(_peaks(x, (j - CTX) * 240, (j + 1) * 240)[::-1], drop)


def soft_out_of_silence(x, j, drop):
    """Window j is the last silent window before the sound: did it fade in?"""
    return _soft(_peaks(x, j * 240, (j + 1 + CTX) * 240), drop)


def has_audio(v):
    r = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'a', '-show_entries', 'stream=index',
                        '-of', 'csv=p=0', v], capture_output=True, text=True, stdin=subprocess.DEVNULL)
    return r.returncode == 0 and bool(r.stdout.strip())


def main():
    v = sys.argv[1]
    drop = float(arg('--drop', 18)); floor = float(arg('--floor', -32))
    cuts = [float(x) for x in arg('--cuts', '').split(',') if x]
    r = subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-i', v, '-vn', '-ac', '1', '-ar', '48000', '-f', 's16le',
                        '-'], capture_output=True, stdin=subprocess.DEVNULL)
    raw = r.stdout
    x = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    hop = 240  # 5 ms
    n = len(x) // hop
    if n == 0:
        if not has_audio(v):
            print(f'NO AUDIO {v} has no audio stream: nothing to check')
        else:
            err = r.stderr.decode(errors='replace').strip().splitlines()
            print(f'NO AUDIO {v}: could not decode any audio' + (f' ({err[-1]})' if err else ''))
        sys.exit(2)
    e = 20 * np.log10(np.sqrt((x[:n * hop].reshape(n, hop) ** 2).mean(1)) + 1e-7)
    t = np.arange(n) * hop / 48000
    bad = []
    d2 = e[2:] - e[:-2]  # change over 10 ms
    for i in np.where((d2 <= -drop) & (e[:-2] > floor))[0]:
        # the last 10-20 ms of a fade into silence fall steeply in dB (and the step into silence is "infinite"):
        # when the sound reaches silence right there, judge how fast its audible part went down instead
        if e[i + 2:i + 5].min() < SILENT and soft_into_silence(x, i + 2 + int(np.argmax(e[i + 2:i + 5] < SILENT)), drop):
            continue
        # a real cut-off stays down (not a single-window dip)
        if e[i + 2:i + 12].max(initial=-200) < e[i] - drop + 6:
            bad.append((round(float(t[i]), 3), 'drop', round(float(d2[i]), 1)))
    for c in cuts:
        w = (t > c - 0.06) & (t < c + 0.06)
        idx = np.where(w)[0]
        if len(idx) > 3:
            steps = []
            for k in idx[:-1]:
                a, b = e[k], e[k + 1]
                if a < SILENT and b < SILENT:
                    continue   # inside silence (codec residue dying away)
                if b < a and e[k + 1:k + 4].min() < SILENT and \
                        soft_into_silence(x, k + 1 + int(np.argmax(e[k + 1:k + 4] < SILENT)), drop):
                    continue   # the tail of a fade-out into silence
                if b > a and e[max(0, k - 2):k + 1].min() < SILENT and \
                        soft_out_of_silence(x, k - int(np.argmax(e[max(0, k - 2):k + 1][::-1] < SILENT)), drop):
                    continue   # the start of a fade-in out of silence
                steps.append(abs(b - a))
            dd = max(steps, default=0.0)
            if dd >= drop and e[idx].max() > floor:
                bad.append((c, 'cut', round(float(dd), 1)))
    # merge near-duplicates
    out = []
    for b in sorted(bad):
        if not out or b[0] - out[-1][0] > 0.05:
            out.append(b)
    if out:
        print('FAIL', len(out), 'hard audio changes:', ', '.join(f'{a}s {k} {v}dB' for a, k, v in out[:20]))
        sys.exit(1)
    print(f'PASS no hard audio cuts ({len(cuts)} cut points checked, {t[-1]:.1f}s)')


if __name__ == '__main__':
    if len(sys.argv) < 2 or sys.argv[1] in ('-h', '--help'):
        print(__doc__); sys.exit(0)
    main()
