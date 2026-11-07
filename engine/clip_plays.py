#!/usr/bin/env python3
"""Cut every item of a plays list out of a source video (stream copy, no re-encode). Runs on the machine with the source.
clip_plays.py <source.mp4> <plays.json> <out_dir> [--seconds 150] [--only 3,7,12]
plays.json: {"plays": [{"n": 12, "start": 3601.5, "end": 3622.0, ...optional q, clock, offense, before, after, tags}]}
Rerun until it prints DONE (time-sliced). Never touches the source. Skips clips that already exist.
Name: 012_Q1_10-01_HOME_2nd-9_to_1st-10_1ST-DOWN.mp4 (missing fields become Q / na / NA)
-c copy cuts land on keyframes: encode the source with short keyframe intervals (e.g. every 0.2 s) for tight cuts.
"""
import sys, os, json, subprocess, time, re


def name(p):
    q = (p.get('q') or 'Q').replace('1ST', 'Q1').replace('2ND', 'Q2').replace('3RD', 'Q3').replace('4TH', 'Q4')
    c = p.get('clock')
    clk = f'{int(c // 60)}-{int(c % 60):02d}' if isinstance(c, (int, float)) else 'na'
    dd = lambda s: re.sub(r'[^A-Za-z0-9]+', '-', (s or 'na').replace(' & ', '-')).strip('-')
    tags = '_'.join(re.sub(r'[^A-Za-z0-9+]+', '-', t).strip('-') for t in p.get('tags', []))
    parts = [f'{p["n"]:03d}', q, clk, p.get('offense') or 'NA', dd(p.get('before')), 'to', dd(p.get('after'))]
    if tags:
        parts.append(tags)
    return '_'.join(parts) + '.mp4'


def main():
    a = sys.argv
    master, pj, out = a[1], a[2], a[3]
    budget = float(a[a.index('--seconds') + 1]) if '--seconds' in a else 150
    only = set(int(x) for x in a[a.index('--only') + 1].split(',')) if '--only' in a else None
    plays = json.load(open(pj))['plays']
    os.makedirs(out, exist_ok=True)
    t0 = time.time(); done = 0
    for p in plays:
        if only and p['n'] not in only:
            continue
        f = os.path.join(out, name(p))
        if os.path.exists(f) and os.path.getsize(f) > 0:
            done += 1
            continue
        if time.time() - t0 > budget:
            print('TIMESLICE', done, len(plays)); return
        tmp = f + '.part.mp4'
        subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-ss', f'{p["start"]:.2f}', '-i', master, '-t', f'{p["end"] - p["start"]:.2f}',
                        '-map', '0:v:0', '-map', '0:a:0', '-c', 'copy', '-avoid_negative_ts', 'make_zero',
                        '-movflags', '+faststart', tmp], check=True, stdin=subprocess.DEVNULL)
        os.replace(tmp, f)
        done += 1
    print('DONE', done, len(plays))


if __name__ == '__main__':
    main()
