#!/usr/bin/env python3
"""Transcribe the broadcast call around plays (faster-whisper, local) so the editor can name the player + yards.
calls.py <idx_dir> [--plays 5,17,40] [--minrank 7] [--model small.en] [--roster a.csv,b.csv]
         [--context "Football broadcast, Acme Hawks"] [--profile NAME]
Window per play: start-3 .. end+20 s of audio16k.opus (talent usually recaps after the whistle).
Roster names go into the prompt so whisper spells them right. -> <idx>/calls.json {n: text}
The prompt opens with --context, else the profile's transcribe.context, else the generic
"Sports broadcast, <team.home_abbr> <team.home_name in title case>".
Names/yards are only ever taken from what the talent SAID (plus jersey numbers seen on screen) — never guessed.
"""
import sys, os, json, csv, subprocess
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def arg(k, d=None):
    a = sys.argv
    return a[a.index(k) + 1] if k in a else d


def context():
    if arg('--context'):
        return arg('--context')
    import vprofile as prof
    P = prof.load(arg('--profile'))
    c = P.get('transcribe.context', None)
    return c or f"Sports broadcast, {P.get('team.home_abbr')} {P.get('team.home_name').title()}"


def main():
    d = sys.argv[1]
    P = json.load(open(f'{d}/plays.json'))['plays']
    want = set(int(x) for x in arg('--plays').split(',')) if arg('--plays') else None
    mr = float(arg('--minrank', 7))
    sel = [p for p in P if (p['n'] in want if want else p['rank'] >= mr)]
    names = []
    for f in (arg('--roster') or '').split(','):
        if f:
            names += [r['name'].replace('"', '') for r in csv.DictReader(open(f))]
    raw = subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-i', f'{d}/audio16k.opus', '-ac', '1', '-ar', '16000', '-f', 's16le', '-'],
                         capture_output=True, stdin=subprocess.DEVNULL).stdout
    x = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    from faster_whisper import WhisperModel
    m = WhisperModel(arg('--model', 'small.en'), device='cpu', compute_type='int8', cpu_threads=2)
    prompt = context() + '. Players: ' + ', '.join(names[:120])
    out = {}
    try:
        out = json.load(open(f'{d}/calls.json'))
    except Exception:
        pass
    for p in sel:
        if str(p['n']) in out:
            continue
        a, b = max(p['start'] - 3, 0), p['end'] + 20
        seg, _ = m.transcribe(x[int(a * 16000):int(b * 16000)], language='en', initial_prompt=prompt, vad_filter=True, beam_size=3)
        out[str(p['n'])] = ' '.join(f'[{a + s.start:.0f}] {s.text.strip()}' for s in seg)
        json.dump(out, open(f'{d}/calls.json', 'w'), indent=1)
        print(p['n'], out[str(p['n'])][:200], flush=True)


if __name__ == '__main__':
    if len(sys.argv) < 2 or sys.argv[1] in ('-h', '--help'):
        print(__doc__); sys.exit(0)
    main()
