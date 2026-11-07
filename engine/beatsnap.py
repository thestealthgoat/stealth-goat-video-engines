#!/usr/bin/env python3
"""Snap an edit list's cuts to the music's beats (faster, punchier reels).
beatsnap.py <edit.json> <music.mp3 (local copy)> [--open 1.6] [--max-shift 0.25]
Reads E['music'][0]['in'] as the music offset; moves each clip's OUT point (never the in point) by at most
--max-shift seconds so every cut lands on a beat. Writes the edit back in place, adds E['beats'] for reference.
DEFAULT (since 2026-11-07): bar map mode with --barmap auto (below), i.e. cuts land on engine/beatmap.py's accurate
beat grid. With no "big"/"payoff" items marked it only snaps every cut to the nearest bar-map beat and keeps cuts out
of music stops. If the bar map cannot be built here, beatsnap prints a note and falls back to the legacy snap.
--legacy-beats: the original beat snap (librosa beat_track), unchanged. Its beats follow librosa's coarse tempo bin
and sit at onset-envelope peaks, so measured against the bar map they run about 40-50 ms late and wander by +/-20 ms
(on two reference tracks). In that mode E['beats']['bpm'] is the coarse bin (e.g. 123.05 for a 120 BPM track) and
E['beats']['bpm_measured'] the tempo engine/beatmap.py measures (left out when beatmap cannot run); neither is read
by any renderer. The legacy mode analyses 300 s from the music in point, or longer when the edit needs more (then
end of the reel + --max-shift per cut + 10 s); edits that fit in 300 s are analysed exactly as before.

Bar map mode (engine/beatmap.py): the default (= --barmap auto, computed here), or --barmap <beatmap.json>.
  beatsnap.py edit.json music.mp3 --open 1.8 --barmap auto [--big-key card.td] [--payoff 9]
  * every cut snaps to the bar map's beats (within --max-shift);
  * the cut INTO a big item lands on a downbeat (within --down-shift, default 1.0 s; else the nearest beat).
    An item is big when its --big-key value is truthy (dotted key, default "big"; e.g. card.td for touchdowns);
  * the cut INTO the payoff item lands on the drop when the drop is within --drop-shift (default 1.5 s) of it;
    otherwise the music in point that would put the drop there is printed. The payoff is the item with
    "payoff": true, or --payoff N (1-based item number);
  * no cut lands inside a music stop or silence: such a cut moves to the stop's start or to the downbeat
    after it, whichever is nearer, even when that is more than the shift limits (it is reported).
  The bar map's times are film seconds from its "start" (the file time of film t=0); they are moved onto the
  reel's clock with E['music'][0]['in'], so a bar map made with --start <music in> lines up exactly.
  E['beats'] then also records the source, the downbeat count, the drop (reel s) and every cut's target.
  A stop counts as over at the downbeat after it (beatmap.py may put that up to 80 ms before the measured end).
--profile <name> (both modes): only used when the music argument is left out (then the edit's own music path,
  mapped for this machine, is used) and for the frame rate of an auto bar map (the edit's fps, else delivery.fps).
"""
import math, os, sys, json
import numpy as np


def arg(k, d=None):
    a = sys.argv
    return a[a.index(k) + 1] if k in a else d


def main():
    if len(sys.argv) < 2 or '-h' in sys.argv or '--help' in sys.argv:
        print(__doc__.strip())
        return
    if '--barmap' in sys.argv:
        return barmap_main()
    if '--legacy-beats' not in sys.argv:
        # Default since 2026-11-07: cuts on the accurate bar-map grid (same as --barmap auto).
        sys.argv += ['--barmap', 'auto']
        if barmap_main(fallback=True) is not False:
            return
        del sys.argv[-2:]
    legacy_main()


def legacy_main():
    E = json.load(open(sys.argv[1]))
    import librosa
    m = E['music'][0]
    music = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith('--') else _music_path(E, _profile(arg('--profile')))
    t = float(arg('--open', E.get('open_dur', 1.6)))
    ms = float(arg('--max-shift', 0.25))
    window = analysis_window(E['items'], t, ms)
    y, sr = librosa.load(music, sr=22050, mono=True, offset=m.get('in', 0.0), duration=window)
    tempo, bf = librosa.beat.beat_track(y=y, sr=sr)
    beats = librosa.frames_to_time(bf, sr=sr)
    for it in E['items']:
        sp = float(it.get('speed', 1.0)) if it.get('replay') else 1.0
        d = (it['out'] - it['in']) / sp
        end = t + d
        cand = beats[(beats > end - ms) & (beats < end + ms)]
        if len(cand):
            b = float(cand[np.argmin(abs(cand - end))])
            it['out'] = round(it['in'] + (b - t) * sp, 3)
        t += (it['out'] - it['in']) / sp
    E['beats'] = {'bpm': float(np.atleast_1d(tempo)[0]), 'n': int(len(beats))}
    bm = measured_bpm(music, float(m.get('in', 0.0)), window)
    if bm is not None:
        E['beats']['bpm_measured'] = bm
    json.dump(E, open(sys.argv[1], 'w'), indent=1)
    print(f"bpm {E['beats']['bpm']:.0f}; reel body {t:.1f}s")


WINDOW = 300.0      # seconds of music analysed from the music in point (the original's fixed window)


def analysis_window(items, t0, ms):
    """Seconds of music to analyse: the original 300 s, or more when the edit runs longer (end of the reel plus
    the most every cut could move, plus 10 s so the beat tracker is not at the edge of the audio)."""
    need = t0 + ms * len(items)
    for it in items:
        sp = float(it.get('speed', 1.0)) if it.get('replay') else 1.0
        need += (it['out'] - it['in']) / sp
    return WINDOW if need <= WINDOW else math.ceil(need) + 10.0


def measured_bpm(music, m_in, window):
    """The track's tempo over the analysed music, measured by engine/beatmap.py (the grid --barmap auto uses).
    librosa's own tempo is a coarse bin (e.g. 123.05 for a 120 BPM track). Recorded for reference only, never used
    for timing; None when beatmap cannot run here (the beat snap itself does not depend on it)."""
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import beatmap
        total = beatmap.probe_duration(music)
        dur = window if total and m_in + window < total else None
        return float(beatmap.build(music, start=m_in, dur=dur, fps=24)['bpm'])
    except (Exception, SystemExit):
        return None


# ---------------------------------------------------------------------------------------------- bar map mode
def _dig(d, dotted):
    for part in dotted.split('.'):
        if not isinstance(d, dict) or part not in d:
            return None
        d = d[part]
    return d


def _profile(name):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import vprofile as prof
    try:
        return prof.load(name)
    except prof.ProfileError:
        if name:
            raise
        return None


def _music_path(E, P):
    a = sys.argv
    if len(a) > 2 and not a[2].startswith('--'):
        return a[2]
    p = E['music'][0]['path']
    return P.map_path(p) if P is not None else p


def load_barmap(spec, music, m_in, fps):
    if spec == 'auto':
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import beatmap
        return beatmap.build(music, start=m_in, dur=None, fps=fps)
    with open(spec) as f:
        return json.load(f)


def in_stop(x, stops, eps=1e-3):
    for s in stops:
        if s[0] + eps < x < s[1] - eps:
            return s
    return None


def plan_cuts(items, bm, m_in, t0, ms, down_shift, drop_shift, big_key, payoff_i):
    """Move out points (in place) so cuts land on the bar map. Returns (reel end, report rows, drop in reel s)."""
    k = float(bm.get('start', 0.0)) - m_in               # bar map film time + k = reel time
    beats = np.asarray(bm.get('beats', []), float) + k
    downs = np.asarray(bm.get('downbeats', []), float) + k
    stops = []
    for s in bm.get('stops_detail', []):
        nd = s.get('next_downbeat')
        nd = s['end'] if nd is None else nd
        # (start, end, escape point, kind); the stop counts as over at its next downbeat (beatmap allows 80 ms early)
        stops.append((s['t'] + k, min(s['end'], nd) + k, nd + k, s.get('kind', 'stop')))
    drop = bm.get('drop')
    drop = drop + k if drop is not None else None
    big = [bool(_dig(it, big_key)) or bool(it.get('payoff')) for it in items]
    rows = []
    t = t0
    for i, it in enumerate(items):
        sp = float(it.get('speed', 1.0)) if it.get('replay') else 1.0
        end = t + (it['out'] - it['in']) / sp
        nxt = i + 1 if i + 1 < len(items) else None
        target, on = None, 'none'
        mind = t + 0.1                                      # never shorter than 0.1 s on the reel

        def nearest(grid, lim):
            c = grid[(grid > end - lim) & (grid < end + lim) & (grid > mind)]
            return float(c[np.argmin(abs(c - end))]) if len(c) else None

        if nxt is not None and nxt == payoff_i and drop is not None and abs(drop - end) <= drop_shift and drop > mind:
            target, on = drop, 'drop'
        if target is None and nxt is not None and big[nxt]:
            target = nearest(downs, down_shift)
            on = 'downbeat' if target is not None else 'none'
        if target is None:
            target = nearest(beats, ms)
            on = 'beat' if target is not None else 'none'
            if on == 'beat' and nxt is not None and big[nxt]:
                on = 'beat (no downbeat in reach)'
        if target is None:
            target = end
        st = in_stop(target, stops)
        if st is not None:
            opts = [x for x in (st[0], st[2]) if x > mind]
            if opts:
                target = min(opts, key=lambda x: abs(x - target))
                on = ('stop start' if target == st[0] else 'downbeat after stop') + f' (moved out of a {st[3]})'
        if on != 'none':
            it['out'] = round(it['in'] + (target - t) * sp, 3)
        new_end = t + (it['out'] - it['in']) / sp
        rows.append(dict(item=i + 1, cut=round(new_end, 3), on=on, moved=round(new_end - end, 3),
                         into_big=bool(nxt is not None and big[nxt]), into_payoff=bool(nxt is not None and nxt == payoff_i)))
        t = new_end
    return t, rows, drop


def barmap_main(fallback=False):
    E = json.load(open(sys.argv[1]))
    P = _profile(arg('--profile'))
    m = E['music'][0]
    m_in = float(m.get('in', 0.0))
    music = _music_path(E, P)
    fps = float(E.get('fps') or (P.get('delivery.fps', 24) if P is not None else 24))
    spec = arg('--barmap')
    try:
        bm = load_barmap(spec, music, m_in, fps)
    except (Exception, SystemExit) as e:
        if not fallback:
            raise
        print(f"beatsnap: note: bar map unavailable ({e!r}); using the legacy librosa beat snap", file=sys.stderr)
        return False
    t0 = float(arg('--open', E.get('open_dur', 1.6)))
    ms = float(arg('--max-shift', 0.25))
    down_shift = float(arg('--down-shift', 1.0))
    drop_shift = float(arg('--drop-shift', 1.5))
    big_key = arg('--big-key', 'big')
    payoff_i = None
    for i, it in enumerate(E['items']):
        if it.get('payoff'):
            payoff_i = i
    if arg('--payoff') is not None:
        payoff_i = int(arg('--payoff')) - 1
        if not 0 <= payoff_i < len(E['items']):
            sys.exit(f"beatsnap: --payoff {payoff_i + 1}: the edit has {len(E['items'])} items")
    t, rows, drop = plan_cuts(E['items'], bm, m_in, t0, ms, down_shift, drop_shift, big_key, payoff_i)
    E['beats'] = {'bpm': float(bm['bpm']), 'n': int(len(bm.get('beats', []))), 'source': 'beatmap',
                  'barmap': spec, 'downbeats': int(len(bm.get('downbeats', []))),
                  'drop': round(drop, 3) if drop is not None else None, 'cuts': rows}
    json.dump(E, open(sys.argv[1], 'w'), indent=1)
    print(f"bpm {E['beats']['bpm']:.0f}; reel body {t:.1f}s")
    for r in rows:
        tag = ' -> payoff' if r['into_payoff'] else (' -> big' if r['into_big'] else '')
        print(f"  cut {r['item']:2d} at {r['cut']:7.3f}s on {r['on']}{tag} (moved {r['moved']:+.3f}s)")
    if payoff_i is not None:
        pr = rows[payoff_i - 1] if payoff_i > 0 else None
        cut = pr['cut'] if pr else t0
        if drop is None:
            print("  payoff: the bar map has no drop in this music window")
        elif pr and pr['on'] == 'drop':
            print(f"  payoff: lands on the drop at {drop:.3f}s")
        else:
            print(f"  payoff: cut at {cut:.3f}s, drop at {drop:.3f}s ({drop - cut:+.3f}s away); "
                  f"music in {m_in + drop - cut:.3f} would put the drop on the payoff cut")
    elif drop is not None:
        print(f"  drop at {drop:.3f}s (no payoff item: mark one with \"payoff\": true or --payoff N)")
    for s in bm.get('stops_detail', []):
        k = float(bm.get('start', 0.0)) - m_in
        if t0 <= s['t'] + k <= t:
            print(f"  music {s.get('kind', 'stop')} {s['t'] + k:.3f}-{s['end'] + k:.3f}s: no cut inside")


if __name__ == '__main__':
    main()
