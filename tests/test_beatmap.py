#!/usr/bin/env python3
"""engine/beatmap.py + beatsnap.py bar-map mode self-test.
  1. Synthetic tracks (no NAS): tempo at 90 / 123 / 150 BPM with straight eighths, 70 / 80 / 90 BPM with eighths and no
     16ths (half/double guard, flagged ambiguous), 120 / 150 BPM four on the floor, a planted drop and a planted stop.
  2. beatsnap --barmap with a hand-written bar map: big cuts on downbeats, the payoff on the drop, no cut inside a
     stop, in points untouched, replay speed respected, bar map start vs music in.
BEATMAP_TEST_ENGINE=<dir> runs the beatmap cases against another copy of beatmap.py (e.g. the pre-fix one).
Prints PASS/FAIL/SKIP per case, exits 1 on any FAIL.
"""
import json, math, os, shutil, subprocess, sys, wave
import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO, "tests", "out", "beatmap")
ENGINE = os.environ.get("BEATMAP_TEST_ENGINE", os.path.join(REPO, "engine"))   # point at an old copy to see the fixes fail
sys.path.insert(0, ENGINE)
sys.path.insert(1, os.path.join(REPO, "engine"))
import beatmap, beatsnap  # noqa: E402

ok = True
def res(label, cond, detail=""):
    global ok
    if cond is None:
        print("SKIP " + label + (f"  ({detail})" if detail else "")); return
    print(("PASS " if cond else "FAIL ") + label + (f"  ({detail})" if detail else "")); ok &= bool(cond)


shutil.rmtree(OUT, ignore_errors=True); os.makedirs(OUT)
SR = 22050


def synth(path, bpm, bars, quiet_bars=0, stop_bar=None, seed=1, sixteenths=True, four=False):
    T = 60 / bpm; n = int((bars * 4 * T + 1.0) * SR); y = np.zeros(n)
    rng = np.random.default_rng(seed); tt = np.arange(int(0.12 * SR)) / SR
    kick = np.sin(2 * np.pi * (50 + 80 * np.exp(-tt * 40)) * tt) * np.exp(-tt * 18)
    snare = rng.standard_normal(len(tt)) * np.exp(-tt * 35) * 0.5
    hat = rng.standard_normal(len(tt)) * np.exp(-tt * 250) * 0.12

    def add(t, s, g):
        i = int(t * SR); m = min(len(s), n - i)
        if m > 0: y[i:i + m] += g * s[:m]
    for k in range(bars * 4):
        bar, beat = divmod(k, 4); t = k * T
        if stop_bar is not None and bar == stop_bar:
            continue
        if four:                                  # four on the floor: kick every beat, snare 2 and 4, open hat on the "and"
            add(t, kick, 1.0); add(t + T / 2, hat, 1.0)
            if beat in (1, 3): add(t, snare, 0.8)
            continue
        g = 0.12 if bar < quiet_bars else 1.0
        if bar >= quiet_bars or beat == 0:
            add(t, kick, g * (1.0 if beat == 0 else 0.7))
        if beat in (1, 3): add(t, snare, g)
        add(t, hat, g); add(t + T / 2, hat, g * 0.8)
        if sixteenths:
            add(t + T / 4, hat, g * 0.3); add(t + 3 * T / 4, hat, g * 0.3)   # soft 16ths, as in real tracks
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((np.clip(y / max(1e-9, np.abs(y).max()) * 0.9, -1, 1) * 32000).astype("<i2").tobytes())
    return T


# ---------------------------------------------------------------------------------------------- 1. synthetic
for bpm in (90, 123, 150):
    p = os.path.join(OUT, f"synth_{bpm}.wav"); synth(p, bpm, 12)
    m = beatmap.build(p, fps=29.97)
    res(f"synthetic {bpm} BPM straight eighths -> {m['bpm']}", abs(m['bpm'] - bpm) <= 1.0)
# half/double (fix 2026-11-07): only straight eighths, no 16ths -> the old code counted the eighths (90 read 180)
for bpm in (70, 80, 90):
    p = os.path.join(OUT, f"synth_{bpm}_eighths.wav"); synth(p, bpm, 12, sixteenths=False)
    m = beatmap.build(p, fps=29.97)
    res(f"synthetic {bpm} BPM, straight eighths only (no 16ths) -> {m['bpm']} (flagged ambiguous: {m['tempo_ambiguous']})",
        abs(m['bpm'] - bpm) <= 1.0 and m['tempo_ambiguous'])
# four on the floor (kick on every beat, hat on the "and"): the old code counted half notes (120 read 60)
for bpm in (120, 150):
    p = os.path.join(OUT, f"synth_{bpm}_four.wav"); synth(p, bpm, 12, four=True)
    m = beatmap.build(p, fps=29.97)
    res(f"synthetic {bpm} BPM four on the floor -> {m['bpm']}", abs(m['bpm'] - bpm) <= 1.0)
p = os.path.join(OUT, "synth_drop.wav"); T = synth(p, 128, 20, quiet_bars=8)
m = beatmap.build(p, fps=29.97)
res(f"synthetic drop at bar 9 ({8 * 4 * T:.3f}s) -> {m['drop']}", m['drop'] is not None and abs(m['drop'] - 8 * 4 * T) <= 0.06)
p = os.path.join(OUT, "synth_stop.wav"); T = synth(p, 120, 16, stop_bar=10)
m = beatmap.build(p, fps=29.97)
st = [s for s in m['stops_detail'] if s['t'] < 11 * 4 * T and s['end'] > 10 * 4 * T]
res(f"synthetic stop in bar 11 ({10 * 4 * T:.2f}-{11 * 4 * T:.2f}s) found -> {[(s['t'], s['end']) for s in st]}", bool(st))
res("synthetic stop: next downbeat is the bar after the stop",
    bool(st) and st[0]['next_downbeat'] is not None and abs(st[0]['next_downbeat'] - 11 * 4 * T) <= 0.05)

# ---------------------------------------------------------------------------------------------- 2. beatsnap logic
BM = {"bpm": 120.0, "start": 50.0, "beats": [round(0.5 * i, 3) for i in range(0, 200)],
      "downbeats": [2.0 * i for i in range(0, 50)], "drop": 32.0,
      "stops_detail": [{"t": 18.2, "end": 19.6, "kind": "stop", "next_downbeat": 20.0}]}
bmp = os.path.join(OUT, "bm.json"); json.dump(BM, open(bmp, "w"))
E = {"open_dur": 1.6, "music": [{"path": "unused.mp3", "in": 50.0}],
     "items": [{"in": 10.0, "out": 15.27},                                   # cut 1 ~6.87 -> beat 7.0
               {"in": 30.0, "out": 34.3, "big": False},                       # cut 2 ~11.3 -> downbeat 12.0 (item 3 big)
               {"in": 40.0, "out": 46.1, "card": {"td": True}},                # item 3 big by card.td; cut 3 ~18.1 -> beat 18.0
               {"in": 5.0, "out": 6.2, "replay": True, "speed": 0.5},          # cut 4: ~20.4 -> beat 20.5
               {"in": 70.0, "out": 81.1},                                     # cut 5 ~31.6 -> drop 32.0 (item 6 = payoff)
               {"in": 90.0, "out": 93.0}]}
ep = os.path.join(OUT, "edit.json"); json.dump(E, open(ep, "w"))
r = subprocess.run([sys.executable, os.path.join(ENGINE, "beatsnap.py"), ep, "unused.mp3", "--barmap", bmp,
                    "--big-key", "card.td", "--payoff", "6"], capture_output=True, text=True)
res("beatsnap --barmap runs", r.returncode == 0, r.stderr[-400:])
print("     " + r.stdout.replace("\n", "\n     ").rstrip())
if r.returncode == 0:
    E2 = json.load(open(ep)); cuts = [c['cut'] for c in E2['beats']['cuts']]; on = [c['on'] for c in E2['beats']['cuts']]
    res("in points untouched", [it['in'] for it in E2['items']] == [it['in'] for it in E['items']])
    res(f"cut 1 on a beat (7.0) -> {cuts[0]}", abs(cuts[0] - 7.0) < 1e-6 and on[0] == 'beat')
    res(f"cut into the big item on a downbeat (12.0) -> {cuts[1]} {on[1]}", abs(cuts[1] - 12.0) < 1e-6 and on[1] == 'downbeat')
    res(f"cut 3 on a beat (18.0) -> {cuts[2]}", abs(cuts[2] - 18.0) < 1e-6)
    res(f"replay item: out moved in source time at speed 0.5 -> cut {cuts[3]}, out {E2['items'][3]['out']}",
        abs(cuts[3] - 20.5) < 1e-6 and abs(E2['items'][3]['out'] - (5.0 + (20.5 - 18.0) * 0.5)) < 1e-6)
    res(f"payoff cut on the drop (32.0) -> {cuts[4]} {on[4]}", abs(cuts[4] - 32.0) < 1e-6 and on[4] == 'drop')
    res("E['beats'] records source, drop and cuts", E2['beats']['source'] == 'beatmap' and E2['beats']['drop'] == 32.0)
    # a cut that would land inside the stop (18.2-19.6) moves out of it
    E3 = json.loads(json.dumps(E)); E3['items'][2]['out'] = 47.1           # cut 3 ~19.1 -> beat 19.0 is inside the stop
    json.dump(E3, open(ep, "w"))
    r = subprocess.run([sys.executable, os.path.join(ENGINE, "beatsnap.py"), ep, "unused.mp3", "--barmap", bmp],
                       capture_output=True, text=True)
    E4 = json.load(open(ep)); c3 = E4['beats']['cuts'][2]
    res(f"cut inside a music stop moved out -> {c3['cut']} ({c3['on']})",
        r.returncode == 0 and not (18.2 < c3['cut'] < 19.6) and c3['cut'] in (18.2, 20.0) and 'stop' in c3['on'])
    allc = [c['cut'] for c in E4['beats']['cuts']]
    res("no cut inside the stop", not any(18.2 + 1e-3 < c < 20.0 - 1e-3 for c in allc), str(allc))
    # bar map start 2 s before the music in point: every bar-map time moves 2 s earlier on the reel
    BM2 = dict(BM, start=48.0); json.dump(BM2, open(bmp, "w")); json.dump(E, open(ep, "w"))
    rows = beatsnap.plan_cuts(json.loads(json.dumps(E))['items'], BM2, 50.0, 1.6, 0.25, 1.0, 1.5, 'card.td', 5)[1]
    res(f"bar map start != music in is shifted (drop 32 -> reel 30, out of --drop-shift 1.5 reach) -> payoff cut "
        f"{rows[4]['cut']} {rows[4]['on']}", rows[4]['on'] != 'drop' and abs(rows[4]['cut'] - 31.5) < 1e-6)
    rows = beatsnap.plan_cuts(json.loads(json.dumps(E))['items'], BM2, 50.0, 1.6, 0.25, 1.0, 2.0, 'card.td', 5)[1]
    res(f"... and with --drop-shift 2 it lands on reel 30.0 -> {rows[4]['cut']}", abs(rows[4]['cut'] - 30.0) < 1e-6)

print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
