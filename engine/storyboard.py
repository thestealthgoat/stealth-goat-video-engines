#!/usr/bin/env python3
"""storyboard.py - E2 visual-per-phrase storyboard for explainers: one beat per spoken line, a new visual or state
every 1-2 s, times snapped to the words.

storyboard.py pace   <sb.json> [--wps 2.6] [--min 1.6] [--pad 0.45]     # time beats from the text (no voice-over yet)
storyboard.py retime <sb.json> --vo vo.wav | --words <vo.words.json>  # snap beats to the voice-over (local whisper)
storyboard.py check  <sb.json> [--max-scene 2.5]                         # the rules below; exit 1 on a FAIL
storyboard.py board  <sb.json> --out <dir> [--profile P]                 # approval sheet (explain.py --board)

storyboard.json:
{ "topic": "Why a mic feeds back", "approved": false, "colors": {"hot": "accent"}, "images": {"wiki": "wiki.png"},
  "beats": [
    { "say": "That squeal isn't the mic. It's a loop.",      # the voice-over line (on-screen captions until VO exists)
      "key": "loop",                                         # the one highlighted word
      "t0": 0.0, "t1": 2.3,                                  # written by pace / retime
      "show": [ {"id": "title", "type": "text", "role": "title", "text": "LOOP", "x": 0.5, "y": 0.2},
                {"id": "flow", "type": "flow", "nodes": [...], "edges": [...], "pulses": [{"at": 0.3, ...}]} ],
      "changes": [ {"at": 1.1, "id": "gain", "set": {"value": 6}} ],   # state changes inside the beat (s after t0)
      "keep": ["title"] } ] }                                # ids that stay although this beat doesn't list them
Element types (engine/explain.html): text (role eyebrow | title | body), readout, flow (nodes, edges, pulses), bars,
plot, wave, knob, burst (a sound-wave hit: shock rings + glow, for the hook), image (E3 source card: src, box, rects from sourcecard.py),
scope (E7/E8: XY / spectrum / wave frames from real audio, storyboard "data": {name: file.json}), scale (E9: nested real
sizes, z = log10 of the frame width in metres, springs beat to beat). A flow re-listed with more nodes builds up: each new
node enters when its beat comes and its edges draw on. An element listed again with the same id
stays on screen and its numbers spring to the new values; one that disappears exits; "in": s delays an entrance.
Times inside a beat ("at" on changes, pulses, bar items, markAt) are seconds after the beat's t0, so pace / retime
can move beats without breaking them.

check (the explain skill's rules): every beat has a line and something on screen; beats are contiguous; no stretch
longer than --max-scene without a planned new visual (beat start, change, delayed entrance, bar or pulse); speaking
rate 2.0-3.5 words a second; motion in the first beat at 0 s (the hook); known element types; images exist.
"""
import argparse, difflib, json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
TYPES = {"text", "readout", "flow", "bars", "plot", "wave", "knob", "image", "burst", "scope", "scale"}


def load(p):
    return json.load(open(p))


def save(sb, p):
    json.dump(sb, open(p, "w"), indent=1, ensure_ascii=False)
    print(f"wrote {p}")


def words_of(s):
    return (s or "").split()


def pace(sb, wps=2.6, mn=1.6, pad=0.45):
    """Time beats from their text (no voice-over): drops any earlier voice-over word times."""
    t = 0.0
    sb.pop("vo", None)
    for b in sb["beats"]:
        b.pop("words", None)
        d = max(mn, len(words_of(b.get("say"))) / wps + pad, b.get("min", 0))
        b["t0"], b["t1"] = round(t, 3), round(t + d, 3)
        t += d
    return sb


def norm(w):
    return re.sub(r"[^a-z0-9']", "", w.lower())


def retime(sb, words):
    """Snap each beat to the recording: t0 just before its first spoken word, t1 = the next beat's t0; per-word times
    go into beat["words"] (script spelling) for the captions. Changes keep their place as a share of the beat."""
    script = [(bi, w) for bi, b in enumerate(sb["beats"]) for w in words_of(b.get("say"))]
    a = [norm(w) for _, w in script]
    z = [norm(w["w"]) for w in words]
    times = [None] * len(a)
    for blk in difflib.SequenceMatcher(None, a, z, autojunk=False).get_matching_blocks():
        for k in range(blk.size):
            times[blk.a + k] = float(words[blk.b + k]["s"])
    known = [i for i, v in enumerate(times) if v is not None]
    if not known:
        sys.exit("storyboard retime: no script word matched the recording")
    for i in range(len(times)):                     # fill unmatched words between their neighbours
        if times[i] is None:
            lo = max([k for k in known if k < i], default=None); hi = min([k for k in known if k > i], default=None)
            times[i] = (times[lo] + 0.3 * (i - lo)) if hi is None else (times[hi] - 0.3 * (hi - i)) if lo is None else \
                times[lo] + (times[hi] - times[lo]) * (i - lo) / (hi - lo)
    per = {}
    for (bi, w), t in zip(script, times):
        per.setdefault(bi, []).append({"w": w, "s": round(t, 3)})
    if any("t0" not in b or "t1" not in b for b in sb["beats"]):
        pace(sb)                                    # never paced: give it text times first, so inner times can scale
    old = [(b["t0"], b["t1"]) for b in sb["beats"]]
    n = len(sb["beats"])
    starts = [max(0.0, per[bi][0]["s"] - 0.12) if bi in per else None for bi in range(n)]
    starts[0] = 0.0
    for bi in range(1, n):                          # a beat with no line: after the previous line's last word
        if starts[bi] is None:
            prev_end = per[bi - 1][-1]["s"] + 0.45 if bi - 1 in per else starts[bi - 1] + 0.8
            nxt = next((starts[j] for j in range(bi + 1, n) if starts[j] is not None), None)
            starts[bi] = prev_end if nxt is None else min(prev_end, (starts[bi - 1] + nxt) / 2)
    for bi in range(1, n):                          # strictly increasing, at least 0.4 s per beat
        starts[bi] = max(starts[bi], starts[bi - 1] + 0.4)
    last = words[-1].get("e", words[-1]["s"] + 0.4)
    end = max(last, starts[-1] + 1.0) + 0.6
    for bi, b in enumerate(sb["beats"]):
        b["t0"] = round(starts[bi], 3); b["t1"] = round(starts[bi + 1] if bi + 1 < n else end, 3)
        b["words"] = per.get(bi, [])
        k = (b["t1"] - b["t0"]) / max(0.01, old[bi][1] - old[bi][0])
        scale_inner(b, k)
    return sb


def scale_inner(b, k):
    """Every beat-relative time inside a beat follows the beat's new length: changes, delayed entrances, pulses,
    bar items, markers, source-card box landings."""
    r = lambda v: round(v * k, 3)
    for ch in b.get("changes", []):
        ch["at"] = r(ch["at"])
    for e in b.get("show", []):
        for key in ("in", "markAt", "boxAt"):
            if key in e:
                e[key] = r(e[key])
        for pu in e.get("pulses", []):
            pu["at"] = r(pu["at"])
        for it in e.get("items", []):
            if "at" in it:
                it["at"] = r(it["at"])


def check(sb, base_dir, max_scene=2.5):
    fails, warns = [], []
    beats = sb["beats"]
    for i, b in enumerate(beats):
        tag = f"beat {i + 1} ({b.get('t0', '?')}-{b.get('t1', '?')} s)"
        if "t0" not in b or "t1" not in b:
            fails.append(f"{tag}: no times (run pace or retime)"); continue
        if b["t1"] <= b["t0"]:
            fails.append(f"{tag}: ends before it starts")
        if i and abs(b["t0"] - beats[i - 1]["t1"]) > 1e-3:
            fails.append(f"{tag}: not contiguous with beat {i} (gap {b['t0'] - beats[i - 1]['t1']:.2f} s)")
        if not b.get("show"):
            fails.append(f"{tag}: nothing on screen")
        if not b.get("say") and i != len(beats) - 1:
            warns.append(f"{tag}: no line (fine for a pure visual beat)")
        n = len(words_of(b.get("say")))
        rate = n / max(0.01, b["t1"] - b["t0"])
        if n and (rate > 3.5 or (rate < 1.6 and not b.get("words"))):
            warns.append(f"{tag}: {rate:.1f} words/s (aim 2.0-3.5)")
        for e in b.get("show", []):
            if e.get("type") not in TYPES:
                fails.append(f"{tag}: unknown element type {e.get('type')!r} (have {', '.join(sorted(TYPES))})")
            if e.get("type") == "image" and e.get("src") not in (sb.get("images") or {}):
                fails.append(f"{tag}: image {e.get('src')!r} is not in \"images\"")
    for k, v in (sb.get("images") or {}).items():
        if not os.path.isfile(v if os.path.isabs(v) else os.path.join(base_dir, v)):
            fails.append(f"image {k}: file not found: {v}")
    for b in beats:
        for e in b.get("show", []):
            if e.get("type") == "scope" and e.get("src") not in (sb.get("data") or {}):
                fails.append(f"beat {beats.index(b) + 1}: scope data {e.get('src')!r} is not in \"data\"")
    for k, v in (sb.get("data") or {}).items():
        if not os.path.isfile(v if os.path.isabs(v) else os.path.join(base_dir, v)):
            fails.append(f"data {k}: file not found: {v}")
    if not beats or any("t0" not in b or "t1" not in b for b in beats):
        return fails or ["no beats"], warns, [0.0]
    # planned new visuals (tracking which ids are on screen the way explain.html does)
    ev, open_ids, prev_el = [], {}, {}
    for i, b in enumerate(beats):
        tag, dur = f"beat {i + 1}", b["t1"] - b["t0"]
        ev.append(b["t0"])
        shown = {e["id"] for e in b.get("show", [])}
        alive = shown | {x for x in (b.get("keep") or []) if x in open_ids}
        for c in b.get("changes", []):
            if not 0 <= c.get("at", -1) < dur:
                fails.append(f"{tag}: change at {c.get('at')} s is outside the beat (0-{dur:.2f} s)")
            elif c.get("id") not in alive:
                fails.append(f"{tag}: change targets {c.get('id')!r}, which is not on screen in this beat")
            else:
                ev.append(b["t0"] + c["at"])
        for e in b.get("show", []):
            new = open_ids.get(e["id"]) != e.get("type")
            if e.get("in"):
                if e["in"] >= dur - 0.2:
                    warns.append(f"{tag}: {e['id']} enters at {e['in']} s, at the end of a {dur:.2f} s beat (clamped)")
                ev.append(b["t0"] + min(e["in"], dur - 0.2))
            for p in e.get("pulses", []):
                if len(p.get("path", [])) < 2 or "at" not in p:
                    fails.append(f"{tag}: pulse in {e['id']} needs \"at\" and a path of 2+ node ids")
                    continue
                ev.append(b["t0"] + p["at"] + p.get("seg", 0.5) * (len(p["path"]) - 1))
            ev += [b["t0"] + it["at"] for it in e.get("items", []) if "at" in it]
            pe = prev_el.get(e["id"])
            if "markAt" in e and (new or pe is None or pe.get("mark") != e.get("mark")):   # a marker that's new
                ev.append(b["t0"] + e["markAt"])
            if e.get("type") == "image" and new:          # the box lands once per entrance
                ev.append(b["t0"] + e.get("in", 0) + e.get("boxAt", 0.55))
        prev_el = {e["id"]: e for e in b.get("show", [])}
        open_ids = {e["id"]: e.get("type") for e in b.get("show", [])}
        for x in (b.get("keep") or []):
            if x not in open_ids:
                open_ids[x] = "kept"
    ev = sorted(set(round(x, 3) for x in ev)) + [beats[-1]["t1"]]
    for a, z in zip(ev, ev[1:]):
        if z - a > max_scene + 1e-3:
            fails.append(f"{a:.2f}-{z:.2f} s: {z - a:.1f} s with no planned new visual (max {max_scene:g} s): add a change")
    first = beats[0]
    if not any(not e.get("in") for e in first.get("show", [])):
        fails.append("beat 1: nothing on screen at 0 s (the hook needs motion in the first frame)")
    return fails, warns, ev


def main(argv=None):
    ap = argparse.ArgumentParser(description="explainer storyboard tools")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pace"); p.add_argument("sb"); p.add_argument("--wps", type=float, default=2.6)
    p.add_argument("--min", type=float, default=1.6); p.add_argument("--pad", type=float, default=0.45)
    r = sub.add_parser("retime"); r.add_argument("sb"); g = r.add_mutually_exclusive_group(required=True)
    g.add_argument("--words", help="a faster-whisper words.json of the recording")
    g.add_argument("--vo", help="the recording itself: transcribed here with local faster-whisper (small.en)")
    c = sub.add_parser("check"); c.add_argument("sb"); c.add_argument("--max-scene", type=float, default=2.5)
    bd = sub.add_parser("board"); bd.add_argument("sb"); bd.add_argument("--out", required=True)
    bd.add_argument("--profile")
    a = ap.parse_args(argv)
    sb = load(a.sb)
    if a.cmd == "pace":
        save(pace(sb, a.wps, a.min, a.pad), a.sb)
    elif a.cmd == "retime":
        if a.vo:
            sys.path.insert(0, HERE)
            import captions
            d = captions.transcribe(a.vo, os.path.dirname(os.path.abspath(a.sb)), "small.en",
                                    " ".join(b.get("say", "") for b in sb["beats"])[:800], 0.3)
            wp = os.path.splitext(a.vo)[0] + ".words.json"
            captions.write_words(wp, d); print(f"wrote {wp}")
            words = d["words"]
            sb["vo"] = os.path.abspath(a.vo)
        else:
            words = json.load(open(a.words))["words"]
        save(retime(sb, words), a.sb)
    elif a.cmd == "check":
        fails, warns, ev = check(sb, os.path.dirname(os.path.abspath(a.sb)), a.max_scene)
        for w in warns: print("WARN", w)
        for f in fails: print("FAIL", f)
        print(f"{len(sb['beats'])} beats, {sb['beats'][-1]['t1']:.1f} s, {len(ev) - 1} planned new visuals, "
              f"longest gap {max((z - x for x, z in zip(ev, ev[1:])), default=0):.1f} s")
        print("CHECK: OK" if not fails else "CHECK: FAIL")
        sys.exit(1 if fails else 0)
    elif a.cmd == "board":
        cmd = [sys.executable, os.path.join(HERE, "explain.py"), a.sb, "--out", a.out, "--board"]
        if a.profile:
            cmd += ["--profile", a.profile]
        sys.exit(subprocess.run(cmd).returncode)


if __name__ == "__main__":
    main()
