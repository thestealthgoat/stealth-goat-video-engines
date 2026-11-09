#!/usr/bin/env python3
"""talkedit.py - "edit in my style": one command turns a talking-head video into a tight, captioned cut.

    python3 engine/talkedit.py <video> --out <dir> [--profile NAME] [--start S --end S] [--name NAME]
                               [--music track.mp3 [--music-in S]] [--aspects 16:9,9:16] [--fresh]
                               [--plan-only] [--no-captions] [--caption-layer] [--qa] [--preview]

What it does (every number comes from the profile's "talkedit" block; defaults below):
  1. Words. Local faster-whisper through engine/captions.py (E1), with a prompt that makes whisper write the
     fillers ("um", "uh") down, so they can be cut. Written to <out>/<name>.words.json (fix spelling there; it is
     reused on every re-run). An audio stream that starts after the picture (phone mp4s, ~0.17 s) is lined up.
  2. Cuts. Pauses over cut.max_pause and filler words (cut.fillers, plus a stuttered repeat of a short word such
     as "I, I") are removed. Every cut point sits in measured quiet (10 ms energy frames under the noise floor +
     6 dB or more, for at least 30 ms), never inside a word: at least cut.min_after_word (0.03 s) plus the fade
     past the last word and the fade before the next one. cut.keep_pause of the pause is left in for breathing
     room. Every cut fades the voice out and in (cut.fade_ms, never under 40 ms).
  3. Punch-ins. With nothing in the first 2 s (no cut, push or card), the shot opens zoom.hook_push (12%) tighter
     and springs out to its framing (the hook). The framing alternates between 1.0 and zoom.punch_scale at the jump cuts (not more often than
     zoom.min_hold_s), and emphasis words (caption keyword, loud for its sentence, intensifiers) get a spring
     push-in (zoom.push_add, zoom.spring) about every zoom.push_every_s, centred on the face (OpenCV, no AI).
  4. Cutaway cards (T4). A full-frame bold title on the profile colour block replaces the picture for 1.3-2.2 s
     at the start of a new beat (after a sentence end or long pause) while the talk carries on; the title is the
     phrase being said (edit it in the JSON). With --music the card cuts in and out on the beat (beatmap.py).
  5. Pop-up cards on cue (T3). Transcript keywords trigger a small card (16:9: upper third, on the side away from
     the face; 9:16: between the face and the captions): a number said with its noun ("40 years") makes a stat card that counts up; a profile trigger word
     (talkedit.pops.triggers {"word": "CARD TEXT"}) a word card; emphasis words fill the rest (pops.per_min, 3 a
     minute). Each springs in on its word and leaves at the next phrase; never over a cutaway card.
  6. Captions. E1 kinetic captions on the cut (16:9 and 9:16 face-crop), never over a card.
  7. Outputs in --out:
       <name>_16x9.mp4, <name>_9x16.mp4       finished, -14 LUFS / -2 dBTP (the profile's delivery spec)
       <name>_16x9.xml                         Premiere (FCP7 XML) of the cut: source clips with the punch-in
                                               scales, cards on V2, music; File > Import
       <name>.talkedit.json                    every cut, zoom and card (edit it and re-run: it is kept)
       <name>.words.json, <name>.srt           words (fix spelling) and subtitles of the cut
       <name>.cuts.json                        planned cuts and holds per aspect, for qa.py / audio_check.py
       cards/<name>_cardNN.mp4                 the card clips the XML uses
       qa_16x9/, qa_9x16/ (--qa)               engine/qa.py review of each output
       preview/ (--preview)                    720p / 540-wide copies under 30 MB for a phone

Re-runs keep your hand edits: when <name>.talkedit.json exists it is used as it is (set "on": false on a cut to put
the pause back, change a "punch" scale, a zoom's "add", a card's "title" or "dur", or add a cut {"s", "e"}).
Times in it are seconds of the source video. --fresh moves it to <out>/_old/ and plans again.
Nothing is ever written into an existing file: old outputs are moved to <out>/_old/<stamp>/ first (a hard link
into a cache can never be overwritten), and every rendered shot is checked against its source frame.

Ideas: speaker-following 9:16 crop with hard cuts, from clipify (MIT, see NOTICE.md); no clipify code is used.
"""
import argparse
import copy
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
import wave

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import vprofile as prof  # noqa: E402
from spring import clamp01, progress, settle, spring_at  # noqa: E402

FF = "/opt/homebrew/bin/ffmpeg" if os.path.exists("/opt/homebrew/bin/ffmpeg") else "ffmpeg"
FP = "/opt/homebrew/bin/ffprobe" if os.path.exists("/opt/homebrew/bin/ffprobe") else "ffprobe"
SR = 48000
HOP = 0.01                 # energy frame (s)
VERSION = 1

# Whisper leaves fillers out unless the prompt shows them (a known trick; the prompt itself is never transcribed).
FILLER_PROMPT = "Umm, let me think like, hmm... Okay, here's what I'm, like, thinking. Uh, so, you know, I mean."

TRANSITIONS = set("""unfortunately fortunately so and but now well okay ok anyway also then because let let's
here here's there's that's this like actually basically honestly listen look see remember
let me""".split()) | {"let me", "here's what", "and here's", "but here's", "so here's", "now here's", "you know"}

INTENSIFIERS = set("""never always every everything everyone nothing nobody only must need needs biggest best worst most
huge massive crazy amazing incredible important truth true real really love hate everybody all forever change
changed changes power powerful free freedom why""".split())

RECIPE = {
    "cut": {"max_pause": 0.40, "keep_pause": 0.20, "fade_ms": 40, "min_after_word": 0.03, "min_cut": 0.10,
            "head": 0.15, "tail": 0.40, "max_sound_in_gap": 0.30, "clear_s": 0.07, "room_tone_db": -64.0,
            "fillers": ["um", "umm", "uh", "uhh", "uhm", "er", "erm", "ah", "hmm", "hm", "mm", "mhm"],
            "repeats": ["i", "the", "a", "an", "and", "so", "we", "it", "you", "to", "but", "my", "he", "she",
                        "they", "in", "of"]},
    "zoom": {"hook_push": 0.12, "punch_on_cuts": True, "punch_scale": 1.08, "min_hold_s": 1.0, "push_add": 0.07, "push_every_s": 8.0,
             "push_min_gap_s": 4.0, "push_lead_s": 0.12, "push_room_s": 1.0, "spring": "smooth",
             "max_scale": 1.22, "face_y": 0.36, "vertical_face_y": 0.30},
    "captions": {"on": True},
    "cards": {"on": True, "per_min": 1.0, "min_gap_s": 25.0, "min_s": 1.3, "max_s": 2.2, "max_words": 6,
              "bg": "primary", "text": "text", "accent": "accent", "font": "head", "spring": "smooth",
              "uppercase": True, "edge_s": 4.0},
    "music": {"gain_db": -24.0, "fade_in_s": 1.0, "fade_out_s": 1.5, "snap_s": 0.35},
    # T3 pop-up cards on cue: transcript keywords trigger a small card in the upper third (never over a T4 card or the
    # captions). numbers -> a stat card that counts up; profile triggers {"word": "CARD TEXT"} -> a word card; the
    # rest of per_min goes to emphasis words. Each springs in on its word and leaves at the next phrase.
    "pops": {"on": True, "per_min": 3.0, "min_gap_s": 6.0, "min_s": 1.2, "max_s": 2.8, "numbers": True,
             "keywords": True, "triggers": {}, "bg": "primary", "text": "text", "accent": "accent",
             "head_font": "head", "body_font": "body", "spring": "snappy", "uppercase": True, "edge_s": 1.5},
}

TIME_WORDS = set("back then later ago now still again here there today tonight every each more less".split())
NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
                "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20, "thirty": 30, "forty": 40,
                "fifty": 50, "sixty": 60, "hundred": 100, "thousand": 1000, "million": 1000000}


# ---- small helpers ------------------------------------------------------------------------------------------
def run(cmd, **kw):
    r = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, **kw)
    if r.returncode != 0:
        sys.stderr.write(r.stderr.decode(errors="replace")[-3000:])
        raise SystemExit(f"command failed: {' '.join(map(str, cmd[:10]))} ...")
    return r.stdout


def merge(base, over):
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        out[k] = merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def bare(w):
    return "".join(c for c in w.lower() if c.isalnum() or c == "'").strip("'")


def stamp():
    return time.strftime("%Y-%m-%d_%H%M%S")


def move_aside(path, out_dir, st):
    """Never write into an existing file (it may be hard-linked into a cache): move it to <out>/_old/<stamp>/."""
    if os.path.lexists(path):
        dst_dir = os.path.join(out_dir, "_old", st)
        os.makedirs(dst_dir, exist_ok=True)
        shutil.move(path, os.path.join(dst_dir, os.path.basename(path)))
        print(f"  moved old {os.path.basename(path)} -> _old/{st}/")


def probe(video):
    j = json.loads(run([FP, "-v", "error", "-show_entries",
                        "stream=codec_type,width,height,r_frame_rate,start_time:format=duration", "-of", "json",
                        video]))
    vs = [s for s in j["streams"] if s["codec_type"] == "video"]
    aus = [s for s in j["streams"] if s["codec_type"] == "audio"]
    v = vs[0]
    num, den = (int(x) for x in v["r_frame_rate"].split("/"))
    aoff = 0.0
    if aus:
        aoff = max(0.0, float(aus[0].get("start_time") or 0) - float(v.get("start_time") or 0))
    return {"w": int(v["width"]), "h": int(v["height"]), "fn": num, "fd": den, "fps": num / den,
            "dur": float(j["format"]["duration"]), "audio": bool(aus), "aoff": aoff}


def read_audio(src, t0, dur, sr=SR, ch=2):
    """Samples of src (music) from t0 for dur s. Output-side seek: ffmpeg decodes from the start and trims, which
    is sample-exact on every file (its fast input seek can land audio up to a second off, see Audio)."""
    n = int(round(dur * sr))
    out = np.zeros((n, ch), np.float32)
    raw = run([FF, "-nostdin", "-v", "error", "-i", src, "-ss", f"{max(0.0, t0):.6f}", "-t", f"{dur:.6f}",
               "-vn", "-ac", str(ch), "-ar", str(sr), "-f", "f32le", "-"])
    a = np.frombuffer(raw, np.float32).reshape(-1, ch)[:n]
    out[: len(a)] = a
    return out


class Audio:
    """The clip's sound, decoded ONCE from the start of the file into a 48 kHz WAV whose sample 0 is t0 on the
    VIDEO clock (an audio stream that starts after the picture, as phone mp4s do by ~0.17 s, is padded).
    Why: on files with a stream group or an edit list (ATEM / Resolve program files, stream-copied extracts)
    ffmpeg's fast input seek (-ss before -i) puts audio up to a second off and short, which would put every shot
    out of sync. Cuts, the energy map and whisper all read this one file."""

    def __init__(self, src, t0, t1, aoff, path):
        self.t0, self.path = t0, path
        cmd = [FF, "-nostdin", "-v", "error", "-i", src]
        af = []
        if t0 >= aoff:
            cmd += ["-ss", f"{t0:.6f}"]                          # output-side: sample-exact
        else:
            af = ["-af", f"adelay=delays={int(round((aoff - t0) * 1000))}:all=1"]
        cmd += ["-t", f"{t1 - t0:.6f}", "-vn"] + af + ["-ac", "2", "-ar", str(SR), "-c:a", "pcm_s16le", path]
        run(cmd)
        with wave.open(path) as wf:
            self.n = wf.getnframes()

    def get(self, t, dur, mono=False):
        n = int(round(dur * SR))
        out = np.zeros((n, 2), np.float32)
        i0 = int(round((t - self.t0) * SR))
        a, b = max(0, i0), min(self.n, i0 + n)
        if b > a:
            with wave.open(self.path) as wf:
                wf.setpos(a)
                x = np.frombuffer(wf.readframes(b - a), "<i2").reshape(-1, 2).astype(np.float32) / 32768
            out[a - i0: a - i0 + len(x)] = x
        return out.mean(1) if mono else out


# ---- energy (silence detection) -----------------------------------------------------------------------------
class Env:
    """10 ms RMS frames of the voice. quiet = under the noise floor + max(6 dB, 30% of the speech range),
    for this frame and both neighbours (30 ms)."""

    def __init__(self, audio, t0, t1):
        k = int(round(HOP * SR))
        dbs = []
        for c0 in np.arange(t0, t1, 60.0):                    # 60 s chunks (= 6000 frames): long sermons fit
            x = audio.get(c0, min(60.0, t1 - c0), mono=True).astype(np.float64)
            n = len(x) // k
            dbs.append(10 * np.log10(np.mean(x[: n * k].reshape(n, k) ** 2, 1) + 1e-12))
        self.db = np.concatenate(dbs)
        self.t0 = t0
        self.floor = float(np.percentile(self.db, 10))
        self.speech = float(np.percentile(self.db, 90))
        # 35 dB under the speech, or 6 dB over the floor when the room is noisier than that (a gated mix sits
        # at digital silence between phrases, so the floor alone would demand dead silence)
        self.thr = max(self.floor + 6.0, self.speech - 35.0)
        q = self.db < self.thr
        q3 = q.copy()
        q3[1:] &= q[:-1]
        q3[:-1] &= q[1:]
        self.q3 = q3

    def i(self, t):
        return int(min(max(round((t - self.t0) / HOP - 0.5), 0), len(self.db) - 1))

    def t(self, i):
        return self.t0 + (i + 0.5) * HOP

    def quiet(self, t):
        return bool(self.q3[self.i(t)])

    def level(self, a, b):
        i, j = self.i(a), self.i(b)
        seg = self.db[i: max(j, i + 1)]
        return float(10 * np.log10(np.mean(10 ** (seg / 10)) + 1e-12))

    def pick(self, target, lo, hi, fps, reach=0.04):
        """A quiet cut point on the video frame grid in [lo, hi]: the quietest grid point within +-reach of
        target, else the quiet grid point nearest to it; None when [lo, hi] has none."""
        if hi < lo:
            return None
        fs = np.arange(int(math.ceil(lo * fps - 1e-6)), int(math.floor(hi * fps + 1e-6)) + 1)
        if not len(fs):
            return None
        ts = fs / fps
        ix = np.array([self.i(t) for t in ts])
        ok = self.q3[ix]
        fs, ts, ix = fs[ok], ts[ok], ix[ok]
        if not len(fs):
            return None
        d = np.abs(ts - target)
        near = np.where(d <= reach)[0]
        k = min(near, key=lambda j: (self.db[ix[j]], d[j])) if len(near) else int(np.argmin(d))
        return float(fs[k] / fps)

    def longest_sound(self, a, b):
        i, j = self.i(a), self.i(b)
        run_, best = 0, 0
        for q in self.q3[i:j + 1]:
            run_ = 0 if q else run_ + 1
            best = max(best, run_)
        return best * HOP


# ---- 1. words ------------------------------------------------------------------------------------------------
def get_words(C, a, audio, out_dir, name, P, t0, t1):
    wp = a.words_file or os.path.join(out_dir, f"{name}.words.json")
    if os.path.exists(wp):
        with open(wp) as f:
            wd = json.load(f)
        print(f"words: {len(wd['words'])} from {wp}")
        return wd, wp
    ctx = P.get("transcribe.context", "") or ""
    prompt = (FILLER_PROMPT + " " + ctx).strip()
    print(f"transcribing locally with faster-whisper {a.model} (fillers kept) ...")
    wd = C.transcribe(audio.path, out_dir, a.model, prompt, a.min_prob)     # the clip's WAV: sample 0 = t0
    for w in wd["words"] + wd["dropped"]:
        w["s"], w["e"] = round(w["s"] + t0, 3), round(w["e"] + t0, 3)
    wd["source"] = os.path.abspath(a.video)
    wd["note"] = wd.get("note", "") + " (talkedit: fillers such as 'um' are kept here on purpose; they are cut.)"
    C.write_words(wp, wd)
    print(f"words: {len(wd['words'])} kept, {len(wd['dropped'])} dropped -> {wp}")
    return wd, wp


def refine(ws, env):
    """Whisper's word edges are loose (a word often runs on over the silence after it). Pull each edge to where
    the voice actually sounds: shrink to the first / last loud frame inside the word, then grow while the voice
    is still loud (up to 0.2 s back / 0.3 s on), never into the neighbouring word."""
    for k, w in enumerate(ws):
        s0, e0 = w["s"], w["e"]
        i, j = env.i(s0), env.i(e0)
        loud = np.nonzero(~env.q3[i:j + 1])[0]
        if not len(loud):
            continue
        s, e = env.t(i + loud[0]) - HOP / 2, env.t(i + loud[-1]) + HOP / 2
        # a pause inside the word (whisper glued the silence after "night." onto "But"): keep the side that
        # sounds; the side touching a neighbouring word is that word's tail, not this word
        a_, b_ = env.i(s), env.i(e)
        q = env.q3[a_:b_ + 1]
        runs, st_ = [], None
        for x, qq in enumerate(q):
            if qq and st_ is None:
                st_ = x
            elif not qq and st_ is not None:
                runs.append((st_, x))
                st_ = None
        runs = [r for r in runs if (r[1] - r[0]) * HOP >= 0.2]
        if runs:
            r0, r1 = max(runs, key=lambda r: r[1] - r[0])
            nl, nr = int((~q[:r0]).sum()), int((~q[r1:]).sum())
            att_p = k > 0 and s0 - ws[k - 1]["e"] < 0.03
            att_n = k + 1 < len(ws) and ws[k + 1]["s"] - e0 < 0.03
            right = (att_p and not att_n) or (att_p == att_n and nr >= nl)
            if right:
                s = env.t(a_ + r1) - HOP / 2
            else:
                e = env.t(a_ + r0 - 1) + HOP / 2
        lo = ws[k - 1]["e"] + 0.02 if k else s0 - 0.2
        hi = ws[k + 1]["s"] - 0.02 if k + 1 < len(ws) else e0 + 0.3
        while s - HOP > max(lo, s0 - 0.2) and not env.q3[env.i(s - HOP)]:
            s -= HOP
        while e + HOP < min(hi, e0 + 0.3) and not env.q3[env.i(e + HOP / 2)]:
            e += HOP
        if e - s >= 0.04:
            w["s"], w["e"] = round(s, 3), round(e, 3)
            if abs(s - s0) > 0.005 or abs(e - e0) > 0.005:
                w["ws"], w["we"] = s0, e0        # whisper's own edges, for reference
    return ws


def classify(wd, env, R, t0, t1):
    """-> (speech, fillers): speech = words that must stay whole (captioned unless 'nocap'); fillers = cut."""
    fill = set(R["cut"]["fillers"])
    reps = set(R["cut"]["repeats"])
    # words whisper was unsure of (dropped) are not protected: most are inventions on a pause ("right?" on
    # silence). Real sound in a gap is still kept by plan_removals' sound check (max_sound_in_gap).
    ws = [dict(w) for w in wd["words"] if w.get("w", "").strip()]
    ws = sorted((w for w in ws if t0 <= w["s"] < t1), key=lambda w: w["s"])
    for w in ws:
        w["e"] = max(w["e"], w["s"] + 0.05)
    ws = refine(ws, env)
    speech, fillers, ghosts = [], [], 0
    for i, w in enumerate(ws):
        w["e"] = max(w["e"], w["s"] + 0.05)
        b = bare(w["w"])
        if env.level(w["s"], w["e"]) < env.thr - 3 and w.get("nocap"):
            ghosts += 1                      # an unsure word on silence: whisper's imagination
            continue
        nxt = ws[i + 1] if i + 1 < len(ws) else None
        if b in fill:
            fillers.append(dict(w, why=f"filler: {b}"))
        elif (b in reps and nxt and bare(nxt["w"]) == b and nxt["s"] - w["e"] < 0.5
              and not w["w"].rstrip().endswith((".", "?", "!"))):
            fillers.append(dict(w, why=f"repeat: {b}"))
        else:
            speech.append(w)
    if ghosts:
        print(f"  ignored {ghosts} unsure words on silence")
    return speech, fillers


def add_islands(speech, fillers, env, R, min_s=0.12):
    """Sound in a long gap that whisper did not write down (an unsure word it dropped, a laugh, a breath) becomes
    a protected, uncaptioned 'word', so the silences on either side of it can still be cut."""
    out = list(speech)
    for prev, nxt in zip(speech, speech[1:]):
        if nxt["s"] - prev["e"] <= R["cut"]["max_pause"]:
            continue
        i, j = env.i(prev["e"] + 0.03), env.i(nxt["s"] - 0.03)
        q = env.q3[i:j + 1]
        x = 0
        while x < len(q):
            if q[x]:
                x += 1
                continue
            y = x
            while y < len(q) and not q[y]:
                y += 1
            a, b = env.t(i + x) - HOP / 2, env.t(i + y - 1) + HOP / 2
            if b - a >= min_s and not any(f["s"] - 0.05 <= a and b <= f["e"] + 0.05 for f in fillers):
                out.append({"w": "", "s": round(a, 3), "e": round(b, 3), "p": 0.0, "nocap": True, "island": True})
            x = y
    out.sort(key=lambda w: w["s"])
    n = len(out) - len(speech)
    if n:
        print(f"  {n} stretches of sound whisper left out are kept whole (uncaptioned)")
    return out


# ---- 2. cuts -------------------------------------------------------------------------------------------------
def plan_removals(speech, fillers, env, R, t0, t1, fps):
    c = R["cut"]
    f = max(40, c["fade_ms"]) / 1000.0
    min_after = max(c["min_after_word"], 0.01 + f, c["clear_s"])   # audio_check looks +-60 ms around a cut
    min_before = max(0.01 + f, c["clear_s"])
    pad_after, pad_before = max(min_after, c["keep_pause"] * 0.55), max(min_before, c["keep_pause"] * 0.45)
    out, skipped = [], []

    def add(s, e, why):
        out.append({"s": round(s, 3), "e": round(e, 3), "why": why, "on": True})

    if not speech:
        return out, skipped
    # head and tail
    first, last = speech[0], speech[-1]
    if first["s"] - t0 > c["head"] + c["min_cut"]:
        x2 = env.pick(first["s"] - c["head"], t0, first["s"] - min_before, fps)
        if x2 and x2 - t0 > c["min_cut"]:
            add(t0, x2, "head")
    if t1 - last["e"] > c["tail"] + c["min_cut"]:
        x1 = env.pick(last["e"] + c["tail"], last["e"] + min_after, t1, fps)
        if x1 and t1 - x1 > c["min_cut"]:
            add(x1, t1, "tail")
    for prev, nxt in zip(speech, speech[1:]):
        gap = nxt["s"] - prev["e"]
        inner = [w for w in fillers if w["s"] >= prev["e"] - 0.02 and w["e"] <= nxt["s"] + 0.02]
        if gap <= c["max_pause"] and not inner:
            continue
        lo, hi = prev["e"] + min_after, nxt["s"] - min_before
        x1t, x2t = prev["e"] + pad_after, nxt["s"] - pad_before
        hi1, lo2 = hi, lo
        if inner:
            x1t, hi1 = min(x1t, inner[0]["s"] - 0.01), inner[0]["s"] - 0.01
            x2t, lo2 = max(x2t, inner[-1]["e"] + 0.01), inner[-1]["e"] + 0.01
            why = ", ".join(w["why"] for w in inner) + (f" + pause {gap:.2f} s" if gap > c["max_pause"] else "")
        else:
            why = f"pause {gap:.2f} s"
        x1t, x2t = max(x1t, lo), min(x2t, hi)
        if x2t - x1t < c["min_cut"]:
            continue
        x1 = env.pick(x1t, lo, min(hi1, x2t), fps)
        x2 = env.pick(x2t, max(lo2, (x1 or lo) + c["min_cut"]), hi, fps) if x1 else None
        if not x1 or not x2 or x2 - x1 < c["min_cut"]:
            skipped.append({"at": round(prev["e"], 2), "why": why, "reason": "no clean quiet point"})
            continue
        # sound in the gap that whisper did not write down (a word it missed, a laugh): keep it
        rest = [(x1, x2)]
        for w in inner:
            rest = [p for a_, b_ in rest for p in ((a_, min(b_, w["s"])), (max(a_, w["e"]), b_)) if p[1] > p[0]]
        loud = max((env.longest_sound(a_, b_) for a_, b_ in rest), default=0)
        if loud > c["max_sound_in_gap"]:
            skipped.append({"at": round(prev["e"], 2), "why": why, "reason": f"{loud:.2f} s of sound in the gap"})
            continue
        add(x1, x2, why)
    out.sort(key=lambda r: r["s"])
    for k, r in enumerate(out, 1):
        r["id"] = k
    return out, skipped


def segments(removals, t0, t1, fps):
    """Kept stretches on the frame grid. A cut-out point rounds later and a cut-in point earlier, so quantising
    only ever keeps a little more around the words."""
    rs = sorted((r["s"], r["e"], r) for r in removals if r.get("on", True))
    merged = []
    for s, e, r in rs:
        if merged and s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
            merged[-1][2] = r
        else:
            merged.append([s, e, r])
    tol = 0.05                       # frames: times in the JSON are rounded to 1 ms (up to 0.015 frame off)
    segs, cur, cur_r = [], int(math.ceil(t0 * fps - tol)), None
    for s, e, r in merged:
        out_f = int(math.ceil(s * fps - tol)) if s > t0 + 1e-6 else int(math.ceil(t0 * fps - tol))
        if out_f > cur:
            segs.append({"in_f": cur, "out_f": out_f, "after": cur_r})
        cur, cur_r = max(cur, int(math.floor(e * fps + tol))), r
    end_f = int(math.floor(t1 * fps + tol))
    if end_f > cur:
        segs.append({"in_f": cur, "out_f": end_f, "after": cur_r})
    o = 0
    for sg in segs:
        sg["n"] = sg["out_f"] - sg["in_f"]
        sg["o_f"] = o
        sg["in"], sg["out"] = sg["in_f"] / fps, sg["out_f"] / fps
        o += sg["n"]
    return segs, o


class Mapper:
    def __init__(self, segs, fps):
        self.segs, self.fps = segs, fps

    def seg_of(self, t):
        for k, sg in enumerate(self.segs):
            if sg["in"] - 1e-6 <= t < sg["out"] + 1e-6:
                return k
        return None

    def out(self, t):
        k = self.seg_of(t)
        if k is None:
            return None
        sg = self.segs[k]
        return sg["o_f"] / self.fps + (min(t, sg["out"]) - sg["in"])


def check_cuts(segs, speech, env, fps, clear=0.03):
    """Every cut: no word within 0.03 s after the cut-out point or 0.02 s before the cut-in point, and both
    points in quiet. Returns the list of problems (empty = no cut lands mid-word)."""
    bad = []
    for k in range(len(segs) - 1):
        x1, x2 = segs[k]["out_f"] / fps, segs[k + 1]["in_f"] / fps
        hit = [w["w"] for w in speech if w["s"] < x2 + 0.02 and w["e"] > x1 - clear]
        q = (env.quiet(x1), env.quiet(x2))
        if hit or not all(q):
            bad.append({"cut": k + 1, "out_s": round(x1, 3), "in_s": round(x2, 3), "words": hit,
                        "quiet": list(q)})
    return bad


# ---- 3. punch-ins and push-ins -------------------------------------------------------------------------------
def plan_punches(removals, segs, R, fps):
    z = R["zoom"]
    level, since = 1.0, -1e9              # the first cut always punches in (a strong moment early: the hook)
    for k, sg in enumerate(segs):
        r = sg["after"]
        if k == 0 or r is None or r.get("why") == "head":
            if r is not None and "punch" not in r:
                r["punch"] = 1.0
            continue
        t = sg["o_f"] / fps
        if "punch" not in r:
            if z["punch_on_cuts"] and t - since >= z["min_hold_s"] and sg["n"] / fps >= 0.8:
                level = 1.0 if level != 1.0 else z["punch_scale"]
                since = t
            r["punch"] = level
        else:
            level = r["punch"]


def seg_levels(segs):
    lv = []
    for sg in segs:
        r = sg["after"]
        lv.append(float(r.get("punch", 1.0)) if r is not None and r.get("why") != "head" else 1.0)
    return lv


def plan_pushes(C, speech, env, segs, mp, cards_out, R, fps, total_s):
    z = R["zoom"]
    caps = C.group([dict(w) for w in speech if not w.get("nocap")])
    keyset = {round(c["words"][c["key"]]["s"], 3) for c in caps if c["key"] is not None}
    lv = np.array([env.level(w["s"], w["e"]) for w in speech]) if speech else np.array([])
    cands = []
    for i, w in enumerate(speech):
        b = bare(w["w"])
        if w.get("nocap") or len(b) < 3 or b in C.STOP:
            continue
        to = mp.out(w["s"])
        if to is None:
            continue
        k = mp.seg_of(w["s"])
        sg = segs[k]
        if to - sg["o_f"] / fps < 0.6 or (sg["o_f"] + sg["n"]) / fps - to < z["push_room_s"]:
            continue
        if any(a - 0.6 <= to <= b + 0.6 for a, b in cards_out):
            continue
        near = [lv[j] for j in range(len(speech)) if abs(speech[j]["s"] - w["s"]) < 3.0]
        zsc = (lv[i] - float(np.median(near))) / 3.0 if near else 0.0
        sc = len(b) * 0.5 + (5 if any(ch.isdigit() for ch in b) else 0) + (6 if b in INTENSIFIERS else 0) \
            + (3 if round(w["s"], 3) in keyset else 0) + (2 if w["w"].rstrip().endswith("!") else 0) + 4 * zsc
        cands.append((sc, to, w))
    want = int(total_s / z["push_every_s"])
    picked = []
    for sc, to, w in sorted(cands, key=lambda c: -c[0]):
        if len(picked) >= want:
            break
        if all(abs(to - p[1]) >= z["push_min_gap_s"] for p in picked):
            picked.append((sc, to, w))
    out = [{"t": round(w["s"], 3), "word": w["w"].strip(".,!?"), "add": z["push_add"], "on": True,
            "score": round(sc, 1)} for sc, to, w in sorted(picked, key=lambda p: p[1])]
    for k, p in enumerate(out, 1):
        p["id"] = k
    return out


# ---- 4. cutaway cards ----------------------------------------------------------------------------------------
def plan_cards(speech, mp, R, fps, total_s):
    cc = R["cards"]
    if not cc["on"]:
        return []
    import captions as C
    cands = []
    for i in range(1, len(speech)):
        w = speech[i]
        if w.get("nocap"):
            continue
        prevs = [x for x in speech[:i] if not x.get("island")]      # a breath before the line is still a pause
        if not prevs:
            continue
        prev = prevs[-1]
        gap = w["s"] - prev["e"]
        sent = prev["w"].rstrip().endswith((".", "?", "!"))
        if not (sent or gap >= 0.7):
            continue
        to = mp.out(w["s"])
        if to is None or to < cc["edge_s"] or to > total_s - cc["edge_s"]:
            continue
        phrase = [w]
        for x in speech[i + 1:]:
            if len(phrase) >= cc["max_words"] or phrase[-1]["w"].rstrip().endswith((".", "?", "!", ",")) \
                    or x["s"] - phrase[-1]["e"] > 0.35 or x.get("nocap"):
                break
            phrase.append(x)
        complete = phrase[-1]["w"].rstrip().endswith((".", "?", "!", ",")) or \
            (speech.index(phrase[-1]) + 1 < len(speech) and
             speech[speech.index(phrase[-1]) + 1]["s"] - phrase[-1]["e"] > 0.35)
        while len(phrase) > 2 and bare(phrase[-1]["w"]) in C.LEADS_ON | C.STOP and not complete:
            phrase.pop()
        content = [x for x in phrase if bare(x["w"]) not in C.STOP and len(bare(x["w"])) >= 3]
        if len(phrase) < 2 or not content:
            continue
        end = mp.out(phrase[-1]["e"])
        if end is None:
            continue
        dur = min(cc["max_s"], max(cc["min_s"], end + 0.3 - (to - 0.06)))
        title = " ".join(x["w"].strip(".,!?;:\"") for x in phrase)
        # a card should carry an idea, not a transition ("Let me give you...", "Unfortunately today")
        lead = bare(phrase[0]["w"])
        two = " ".join(bare(x["w"]) for x in phrase[:2])
        filler_lead = lead in TRANSITIONS or two in TRANSITIONS
        dens = len(content) / len(phrase)
        cands.append((gap + (1.0 if sent else 0.0) + (1.5 if complete else 0.0) + 1.5 * dens
                      - (2.5 if filler_lead else 0.0), to, w, dur, title))
    want = max(1, int(round(cc["per_min"] * total_s / 60.0)))
    picked = []
    for sc, to, w, dur, title in sorted(cands, key=lambda c: -c[0]):
        if len(picked) >= want:
            break
        if all(abs(to - p[1]) >= cc["min_gap_s"] for p in picked):
            picked.append((sc, to, w, dur, title))
    out = [{"t": round(w["s"], 3), "dur": round(dur, 2), "title": title, "on": True}
           for sc, to, w, dur, title in sorted(picked, key=lambda p: p[1])]
    for k, c in enumerate(out, 1):
        c["id"] = k
    return out


def plan_pops(speech, mp, R, total_s, cards_out):
    """T3: pop-up cards on cue. -> [{"t", "dur", "kind": "stat"|"word", "big", "label", "on", "id"}] (source seconds).
    A number said with its noun ("40 years", "three things") makes a stat card (the number counts up); a profile
    trigger word makes a word card with its own text; emphasis words fill the rest of per_min. Each card stays until
    the next phrase starts (a pause or sentence end), clamped to min_s..max_s, and never overlaps a T4 card."""
    pc = R.get("pops", {})
    if not pc.get("on", True):
        return []
    import captions as C
    trig = {k.lower(): v for k, v in (pc.get("triggers") or {}).items()}
    ws = [w for w in speech if not w.get("nocap") and not w.get("island")]

    def phrase_end(i):
        for j in range(i, len(ws) - 1):
            if ws[j]["w"].rstrip().endswith((".", "?", "!", ",")) or ws[j + 1]["s"] - ws[j]["e"] > 0.3:
                return ws[j]["e"]
        return ws[-1]["e"]

    import re as _re

    def num(w):
        """'2.5' / '1,200' / '40%' / '$5' / 'forty' -> (number string, prefix, suffix) or None. Parsed from the raw
        word, so a decimal point and the % or $ survive."""
        raw = w.strip().strip(".,!?;:\"'()")
        pre = "$" if raw.startswith("$") else ""
        suf = "%" if raw.endswith("%") else ""
        core = raw.lstrip("$").rstrip("%").replace(",", "")
        if _re.fullmatch(r"\d+(\.\d+)?", core):
            return core, pre, suf
        b = bare(w)
        return (str(NUMBER_WORDS[b]), "", "") if b in NUMBER_WORDS else None

    cands = []
    used = -1                                            # words already read as part of an earlier number
    for i, w in enumerate(ws):
        if i <= used:
            continue
        b = bare(w["w"])
        to = mp.out(w["s"])
        if to is None or to < pc["edge_s"] or to > total_s - pc["edge_s"] - pc["min_s"]:
            continue
        kind = big = label = None
        score = 0.0
        if b in trig:
            kind, big, label, score = "word", str(trig[b]), "", 10.0
        elif pc.get("numbers", True) and num(w["w"]) is not None:
            n, pre, suf = num(w["w"])
            rest = ws[i + 1:i + 7]
            j = 0
            if bare(w["w"]) in NUMBER_WORDS:                 # "twenty five" -> 25, "two hundred" -> 200
                val = int(n)
                while j < len(rest) and bare(rest[j]["w"]) in NUMBER_WORDS:
                    v = NUMBER_WORDS[bare(rest[j]["w"])]
                    val = val * v if v >= 100 else val + v
                    j += 1
                n = str(val)
            if [bare(x["w"]) for x in rest[j:j + 3]] == ["and", "a", "half"]:     # "two and a half acres" -> 2.5
                n, j = (str(float(n) + 0.5).rstrip("0").rstrip(".") if "." not in n else n), j + 3
            pct = bool(rest[j:j + 1]) and bare(rest[j]["w"]) == "percent"
            if pct:
                j += 1
            if (pct or suf) and rest[j:j + 1] and bare(rest[j]["w"]) == "of":   # "40% of people" -> 40% / people
                j += 1
            used = i + j
            lab = []                                     # the noun phrase right after it, up to a stop word or pause
            for x in rest[j:j + 3]:
                if bare(x["w"]) in C.STOP or bare(x["w"]) in TIME_WORDS or len(bare(x["w"])) < 3 \
                        or (lab and x["s"] - lab[-1]["e"] > 0.3) or (lab and bare(x["w"]).endswith("ed")):
                    break
                lab.append(x)
                if x["w"].rstrip().endswith((".", ",", "?", "!")):
                    break
            said = rest[j - 1]["e"] if j else w["e"]       # the number ends after "and a half"
            if lab and lab[0]["s"] - said < 0.8:
                kind, big = "stat", pre + n + ("%" if pct or suf else "")
                label = " ".join(x["w"].strip(".,!?;:\"") for x in lab)
                score = 6.0
        elif pc.get("keywords", True) and b in INTENSIFIERS and len(b) >= 4:
            kind, big, label, score = "word", w["w"].strip(".,!?;:\""), "", 2.0 + min(2.0, len(b) / 4)
        if not kind:
            continue
        end = phrase_end(i)
        dur = min(pc["max_s"], max(pc["min_s"], end - w["s"] + 0.25))
        if any(ca - 0.5 <= to <= cb + 0.5 or ca - 0.5 <= to + dur <= cb + 0.5 for ca, cb in cards_out):
            continue
        cands.append((score, to, w["s"], dur, kind, big, label))
    want = max(1, int(round(pc["per_min"] * total_s / 60.0)))
    picked = []
    for c in sorted(cands, key=lambda c: (-c[0], c[1])):
        if len(picked) >= want:
            break
        if all(abs(c[1] - p[1]) >= pc["min_gap_s"] for p in picked):
            picked.append(c)
    out = []
    for k, (sc, to, t, dur, kind, big, label) in enumerate(sorted(picked, key=lambda p: p[1]), 1):
        out.append({"id": k, "t": round(t, 3), "dur": round(dur, 2), "kind": kind, "big": big, "label": label, "on": True})
    return out


def card_times(cards, mp, fps, total_n, beats, snap_s, cc, edges=()):
    """Cards in output frames [(f0, n, card)]. With music: start and end on the nearest beat (within snap_s).
    A card's cuts are picture-only, but audio_check judges +-60 ms around every planned cut, so neither end lands
    within 0.08 s of a word starting or stopping (edges: word edges on the cut's clock)."""
    edges = np.array(sorted(edges), float)

    def clear(t):
        return not len(edges) or float(np.min(np.abs(edges - t))) >= 0.08

    def nudge(t, lo, hi):
        if clear(t):
            return t
        for k in range(1, int(0.4 * fps) + 1):          # the nearest clear frame, either way
            for x in (t - k / fps, t + k / fps):
                if lo <= x <= hi and clear(x):
                    return x
        return t
    out = []
    for c in cards:
        if not c.get("on", True):
            continue
        to = mp.out(c["t"])
        if to is None:
            print(f"  card {c.get('id')} '{c['title']}' starts in a cut: skipped")
            continue
        # cut to the card on the jump cut before the beat's first word (or 0.25 s before it), never closer than
        # 0.08 s to the voice (audio_check judges +-60 ms around every planned cut)
        k = mp.seg_of(c["t"])
        seg0 = mp.segs[k]["o_f"] / fps
        a = max(seg0, to - 0.25)
        if a > to - 0.08:
            a = seg0
        dur = float(c["dur"]) + (to - 0.06 - a)
        b = a + dur
        if beats is not None and len(beats) and c.get("snap", True):
            ok = beats[(np.abs(beats - a) <= snap_s) & (beats <= to - 0.08)]
            if len(ok):
                a = float(ok[np.argmin(np.abs(ok - a))])
            ends = [x for x in beats if cc["min_s"] - 0.05 <= x - a <= cc["max_s"] + 0.05 and clear(x)]
            if ends:
                b = float(min(ends, key=lambda x: abs(x - b)))
            else:
                b = nudge(a + dur, a + cc["min_s"], a + cc["max_s"] + 0.3)
        else:
            a = nudge(a, a - 0.3, to - 0.08)
            b = nudge(b, a + cc["min_s"], a + cc["max_s"] + 0.3)
        f0 = max(0, int(round(a * fps)))
        f1 = min(total_n, int(round(b * fps)))
        if out and f0 < out[-1][0] + out[-1][1] + int(fps):
            continue
        if f1 - f0 >= int(0.8 * fps):
            out.append((f0, f1 - f0, c))
    return out


# ---- faces (subprocess: OpenCV and faster-whisper's PyAV must not share a process) --------------------------
def faces_main(src, t0, t1, step):
    import cv2
    W, H = 640, None
    info = probe(src)
    H = int(round(info["h"] * W / info["w"] / 2) * 2)
    raw = run([FF, "-nostdin", "-v", "error", "-ss", f"{t0:.3f}", "-i", src, "-t", f"{t1 - t0:.3f}", "-an",
               "-vf", f"fps=1/{step},scale={W}:{H},format=gray", "-f", "rawvideo", "-"])
    n = len(raw) // (W * H)
    sx = info["w"] / W
    xml = os.path.join(getattr(getattr(cv2, "data", None), "haarcascades", ""), "haarcascade_frontalface_default.xml")
    if not hasattr(cv2, "CascadeClassifier") or not os.path.exists(xml):
        print(json.dumps(motion_speaker(raw, n, W, H, sx, t0, step)))     # OpenCV 5 has no Haar cascades
        return
    cas = cv2.CascadeClassifier(xml)
    res = []
    for i in range(n):
        g = np.frombuffer(raw, np.uint8, W * H, i * W * H).reshape(H, W)
        f = cas.detectMultiScale(g, scaleFactor=1.1, minNeighbors=5, minSize=(28, 28))
        if len(f):
            x, y, w, h = max(f, key=lambda r: r[2] * r[3])
            res.append([round(t0 + (i + 0.5) * step, 2), round((x + w / 2) * sx, 1), round((y + h / 2) * sx, 1),
                        round(w * sx, 1)])
    print(json.dumps(res))


def motion_speaker(raw, n, W, H, sx, t0, step, win_s=6.0):
    """No face model: the speaker is where the picture moves (head and hands; the set is still). Per window of
    win_s: the moving pixels (top 3 % of the mean frame difference); x = the median of the top quarter of them (the head, not the hands), face y = near the top of
    the moving blob (10th percentile of y + 7 % of the height)."""
    fr = [np.frombuffer(raw, np.uint8, W * H, i * W * H).reshape(H, W).astype(np.float32) for i in range(n)]
    per = max(2, int(round(win_s / step)))
    res = []
    for a in range(0, n - 1, per):
        d = [np.abs(fr[i + 1] - fr[i]) for i in range(a, min(a + per, n - 1))]
        if not d:
            continue
        m = np.mean(d, 0)
        k = max(1, W // 64)
        m = m[: H // k * k, : W // k * k].reshape(H // k, k, W // k, k).mean((1, 3))
        thr = np.percentile(m, 97)
        if thr < 1.0:
            continue
        ys, xs = np.nonzero(m >= thr)
        top = ys <= np.percentile(ys, 25)             # the head is the highest thing that moves; hands are lower
        cx = (float(np.median(xs[top])) + 0.5) * k
        cy = (float(np.percentile(ys, 10)) + 0.5) * k + 0.07 * H
        t = t0 + (a + min(per, n - 1 - a) / 2) * step
        res.append([round(t, 2), round(cx * sx, 1), round(cy * sx, 1), 0.0])
    return res


def find_faces(src, t0, t1, step=1.0):
    out = subprocess.run([sys.executable, os.path.abspath(__file__), "_faces", src, str(t0), str(t1), str(step)],
                         stdin=subprocess.DEVNULL, capture_output=True, text=True)
    if out.returncode != 0:
        print("  face finder failed; framing on the frame centre:", out.stderr[-400:])
        return []
    return json.loads(out.stdout.strip().splitlines()[-1])


def face_centres(faces, segs, info):
    W, H = info["w"], info["h"]
    if faces:
        g = (float(np.median([f[1] for f in faces])), float(np.median([f[2] for f in faces])))
    else:
        g = (W / 2, H * 0.35)
    out = []
    for sg in segs:
        fs = [f for f in faces if sg["in"] <= f[0] < sg["out"]]
        c = g
        if len(fs) >= 2:
            m = (float(np.median([f[1] for f in fs])), float(np.median([f[2] for f in fs])))
            if abs(m[0] - g[0]) > 0.08 * W or abs(m[1] - g[1]) > 0.08 * H:
                c = m                       # the speaker really moved (or another camera): follow
        out.append([round(c[0], 1), round(c[1], 1)])
    return out


# ---- audio ---------------------------------------------------------------------------------------------------
def build_audio(audio, segs, fps, R, total_n, music, music_in, path):
    f = max(40, R["cut"]["fade_ms"]) / 1000.0
    total = int(round(total_n / fps * SR))
    mix = np.zeros((total, 2), np.float32)
    for k, sg in enumerate(segs):
        L = int(round(sg["n"] / fps * SR))
        a = audio.get(sg["in"], sg["n"] / fps)[:L]
        env = np.ones(len(a), np.float32)
        ri = int((f if k > 0 else max(f, 0.05)) * SR)
        ro = int((f if k < len(segs) - 1 else 0.25) * SR)
        ri, ro = min(ri, len(a) // 2), min(ro, len(a) // 2)
        if ri:
            env[:ri] = np.sin(np.linspace(0, np.pi / 2, ri)) ** 2
        if ro:
            env[len(a) - ro:] *= np.cos(np.linspace(0, np.pi / 2, ro)) ** 2
        pos = int(round(sg["o_f"] / fps * SR))
        end = min(total, pos + len(a))
        mix[pos:end] += (a * env[:, None])[: end - pos]
    if music:
        m = R["music"]
        mu = read_audio(music, music_in, total / SR, SR, 2) * (10 ** (m["gain_db"] / 20))
        e = np.ones(total, np.float32)
        fi, fo = int(m["fade_in_s"] * SR), int(m["fade_out_s"] * SR)
        e[:fi] = np.sin(np.linspace(0, np.pi / 2, fi)) ** 2
        e[total - fo:] *= np.cos(np.linspace(0, np.pi / 2, fo)) ** 2
        mix += mu * e[:, None]
    pk = float(np.abs(mix).max()) if len(mix) else 0
    if pk > 0.98:
        mix *= 0.98 / pk
    with wave.open(path, "wb") as wv:
        wv.setnchannels(2)
        wv.setsampwidth(2)
        wv.setframerate(SR)
        wv.writeframes((np.clip(mix, -1, 1) * 32767).astype("<i2").tobytes())


def room_tone(path, rms_db, seed=7):
    """A gated mix drops to digital silence between phrases: lay a soft, steady room tone (pink-ish noise,
    100 Hz-5 kHz) under the whole cut so no pause is a dropout. Deterministic (seeded)."""
    with wave.open(path) as wf:
        n, ch = wf.getnframes(), wf.getnchannels()
        x = np.frombuffer(wf.readframes(n), "<i2").reshape(-1, ch).astype(np.float32) / 32768
    rng = np.random.default_rng(seed)
    w = rng.normal(0, 1, (len(x) + SR, 1)).astype(np.float32)
    import scipy.signal as sg_
    b, a_ = sg_.butter(2, [100, 5000], btype="band", fs=SR)
    pink = sg_.lfilter([0.049922035, -0.095993537, 0.050612699, -0.004408786],
                       [1, -2.494956002, 2.017265875, -0.522189400], w[:, 0])
    t = sg_.lfilter(b, a_, pink)[SR:]
    t = t / (np.sqrt(np.mean(t ** 2)) + 1e-12) * 10 ** (rms_db / 20)
    fade = int(0.3 * SR)
    t[:fade] *= np.linspace(0, 1, fade)
    t[-fade:] *= np.linspace(1, 0, fade)
    x = x + t[:, None].astype(np.float32)
    with wave.open(path + ".rt.wav", "wb") as wv:
        wv.setnchannels(ch)
        wv.setsampwidth(2)
        wv.setframerate(SR)
        wv.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())
    os.replace(path + ".rt.wav", path)


def measure(wav):
    r = subprocess.run([FF, "-nostdin", "-hide_banner", "-i", wav, "-af", "ebur128=peak=true", "-f", "null", "-"],
                       stdin=subprocess.DEVNULL, capture_output=True, text=True)
    tail = r.stderr[r.stderr.rfind("Summary:"):]
    return float(tail.split("I:")[1].split("LUFS")[0]), float(tail.split("Peak:")[1].split("dBFS")[0])


def loudnorm(wav, out_wav, target, tp):
    """Linear gain + a gentle compressor + a 4x oversampled limiter, re-measured until within 0.2 LU."""
    i0, _ = measure(wav)
    gain = target - i0
    lim = 10 ** ((tp - 1.6) / 20)
    for _ in range(8):
        tmp = out_wav + ".tmp.wav"
        run([FF, "-nostdin", "-v", "error", "-y", "-i", wav, "-af",
             f"volume={gain:.2f}dB,acompressor=threshold=0.5:ratio=2:attack=10:release=250:knee=6,"
             f"aresample={SR * 4},alimiter=limit={lim:.3f}:attack=5:release=200:level=false,aresample={SR}",
             "-c:a", "pcm_s16le", tmp])
        os.replace(tmp, out_wav)
        i1, p1 = measure(out_wav)
        if abs(i1 - target) <= 0.2:
            break
        gain += target - i1
    print(f"  loudness {i1:.1f} LUFS, true peak {p1:.1f} dBTP")
    return i1, p1


# ---- render (subprocess) -------------------------------------------------------------------------------------
def window(J, s):
    """Crop window (x0, y0, w, h) in source pixels for scale s."""
    W, H = J["src_w"], J["src_h"]
    bw, bh = J["win"]
    w, h = bw / s, bh / s
    cx, cy = J["_c"]
    x0 = min(max(cx - w / 2, 0.0), W - w)
    y0 = min(max(cy - J["face_y"] * h, 0.0), H - h)
    return x0, y0, w, h


def scale_at(sg, t, preset):
    s = sg["level"]
    for p in sg["pushes"]:
        if t >= p["t"]:
            s = p["from"] + (p["to"] - p["from"]) * progress(t - p["t"], 0.0, p.get("preset", preset))
    return s


class CardArt:
    """Full-frame colour block; the title springs up line by line (whole lines, not typed-out words) and an
    accent rule slides in under it. The type is as big as fits: every line inside the safe area (+24 px)."""

    def __init__(self, st, W, H):
        self.st, self.W, self.H = st, W, H
        vertical = H > W
        self.size0 = int(W * 0.17) if vertical else int(H * 0.21)    # bold: the title owns the frame
        self.maxw = W - 2 * (int(st.get("safe_px", 90)) + 24)
        self.cache = {}

    def _layout(self, title):
        from PIL import Image, ImageDraw, ImageFont
        words = title.upper().split() if self.st["uppercase"] else title.split()
        size = self.size0
        while True:
            font = ImageFont.truetype(self.st["font"], size)
            lines, cur = [], []
            for w in words:
                if cur and font.getlength(" ".join(cur + [w])) > self.maxw:
                    lines.append(cur)
                    cur = []
                cur.append(w)
            if cur:
                lines.append(cur)
            widest = max(font.getlength(" ".join(ln)) for ln in lines)
            if (widest <= self.maxw and len(lines) <= 3) or size < 40:
                break
            size = int(size * 0.93)
        asc, desc = font.getmetrics()
        lh = int(asc * 1.02)
        block = lh * len(lines)
        y = self.H * 0.46 - block / 2
        items = []
        for li, ln in enumerate(lines):
            text = " ".join(ln)
            l_, t_, r_, b_ = font.getbbox(text)
            img = Image.new("RGBA", (int(r_ - l_) + 8, asc + desc + 8), (0, 0, 0, 0))
            ImageDraw.Draw(img).text((4 - l_, 4), text, font=font, fill=tuple(self.st["text"]))
            x = (self.W - font.getlength(text)) / 2
            items.append((img, x + l_ - 4, y + li * lh - 4))
        bar_w, bar_h = int(self.W * 0.16), max(8, int(size * 0.07))
        bar_y = int(y + block + size * 0.18)
        return items, (bar_w, bar_h, bar_y), size

    @staticmethod
    def _paste(canvas, img, x, y):
        """Paste at a sub-pixel position (bilinear shift of the fraction): a spring's slow tail then moves a
        little every frame instead of a whole pixel every other frame (which reads as a repeated-frame hitch)."""
        from PIL import Image
        ix, iy = math.floor(x), math.floor(y)
        fx, fy = x - ix, y - iy
        if fx > 1e-3 or fy > 1e-3:
            pad = Image.new("RGBA", (img.size[0] + 2, img.size[1] + 2), (0, 0, 0, 0))
            pad.paste(img, (1, 1))
            img = pad.transform(pad.size, Image.AFFINE, (1, 0, -fx, 0, 1, -fy), resample=Image.BILINEAR)
            ix, iy = ix - 1, iy - 1
        canvas.alpha_composite(img, (max(ix, 0), max(iy, 0)))

    def frame(self, title, t):
        from PIL import Image, ImageDraw
        if title not in self.cache:
            self.cache[title] = self._layout(title)
        items, (bw, bh, by), size = self.cache[title]
        sp = self.st["spring"]
        img = Image.new("RGBA", (self.W, self.H), tuple(self.st["bg"]) + (255,))
        for k, (limg, x, y) in enumerate(items):
            st = 0.08 * k                       # line 1 moves from the first frame (no repeated frame)
            if t < st:
                continue
            a = clamp01(spring_at(t, 0, 1, st, "ui"))
            dy = spring_at(t, size * 0.35, 0, st, sp)
            w = limg
            if a < 0.996:
                w = limg.copy()
                w.putalpha(w.split()[3].point(lambda p, a=a: int(p * a)))
            self._paste(img, w, x, y + dy)
        st = 0.08 * len(items)
        if t >= st:
            x = spring_at(t, -bw - 40, (self.W - bw) / 2, st, sp)
            bar = Image.new("RGBA", (bw, bh), tuple(self.st["accent"]) + (255,))
            if x + bw > 0:
                if x < 0:
                    bar = bar.crop((int(-x), 0, bw, bh))
                    x = 0.0              # still sliding in fast: whole pixels are fine here
                self._paste(img, bar, x, by)
        return np.asarray(img.convert("RGB"), np.uint8)

    def settle_s(self, title):
        if title not in self.cache:
            self.cache[title] = self._layout(title)
        return 0.08 * len(self.cache[title][0]) + settle(self.st["spring"])


class PopArt:
    """T3 pop-up card (E3/E4 style): a rounded panel in the brand colour with an accent edge, upper third on the side
    away from the face. "stat": a big number that counts up (critically damped spring, never past its value) over a
    small label; "word": one big word. In: slides from its side (pops.spring, snappy) and fades in (ui); out: the last
    0.3 s slides back and fades (smooth). Everything is a function of t."""

    def __init__(self, st, W, H):
        self.st, self.W, self.H = st, W, H
        self.vertical = H > W
        self.cache = {}

    def _fonts(self):
        from PIL import ImageFont
        base = self.W * (0.11 if self.vertical else 0.07)
        return ImageFont.truetype(self.st["head"], int(base)), ImageFont.truetype(self.st["body"], int(base * 0.34))

    def _panel(self, kind, big, label):
        """RGBA panel for the final text (its size fixes the layout; a counting number is drawn into it per frame).
        Never wider than the room beside the face (16:9: 42% of the width; 9:16: the safe width): the type shrinks."""
        from PIL import ImageFont
        fb, fl = self._fonts()
        up = (lambda x: x.upper()) if self.st["uppercase"] else (lambda x: x)
        big, label = up(big), up(label)
        safe = self.st["safe_px"]
        maxw = (self.W - 2 * safe) * 0.92 if self.vertical else self.W * 0.42
        while True:
            pad = int(fb.size * 0.32)
            bw = fb.getlength(big); lw = fl.getlength(label) if label else 0
            if max(bw, lw) + 2 * pad + fb.size * 0.12 <= maxw or fb.size < 24:
                break
            k = 0.92
            fb = ImageFont.truetype(self.st["head"], int(fb.size * k)); fl = ImageFont.truetype(self.st["body"], max(10, int(fl.size * k)))
        pad = int(fb.size * 0.32)
        w = int(max(bw, lw) + 2 * pad + fb.size * 0.12)
        asc, desc = fb.getmetrics()
        h = int(asc * 0.9 + (fl.size * 1.35 if label else 0) + 2 * pad)
        return {"w": w, "h": h, "pad": pad, "big": big, "label": label, "fb": fb, "fl": fl, "asc": asc}

    def frame(self, pop, t):
        """-> (RGBA PIL image, x, y) for this frame, or None when fully out."""
        from PIL import Image, ImageDraw
        key = (pop["kind"], pop["big"], pop["label"])
        if key not in self.cache:
            self.cache[key] = self._panel(*key)
        L = self.cache[key]
        dur = pop["n"] / pop["fps"]
        out_t = dur - 0.3                                # uiExit settles in ~0.16 s: gone well before the end
        a_in = clamp01(spring_at(t, 0, 1, 0.0, "ui"))
        a_out = 1 - clamp01(spring_at(t, 0, 1, out_t, "uiExit")) if t >= out_t else 1.0
        a = a_in * a_out
        if a <= 0.003:
            return None
        safe = self.st["safe_px"]
        # 16:9: upper third beside the face; 9:16: the band between the face (~30%) and the captions (~70%)
        y = int(self.H * 0.50) if self.vertical else int(self.H * 0.12)
        side = pop.get("side", "right")
        x_end = safe if side == "left" else self.W - safe - L["w"]
        off = (L["w"] + safe) * (-1 if side == "left" else 1)
        x = x_end + off * (1 - spring_at(t, 0, 1, 0.0, self.st["spring"]))
        if t >= out_t:
            x += off * 0.35 * clamp01(spring_at(t, 0, 1, out_t, "uiExit"))
        img = Image.new("RGBA", (L["w"], L["h"]), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        r = int(L["fb"].size * 0.18)
        d.rounded_rectangle([0, 0, L["w"] - 1, L["h"] - 1], radius=r, fill=tuple(self.st["bg"]) + (238,))
        ew = max(6, int(L["fb"].size * 0.07))
        edge_x = 0 if side == "left" else L["w"] - ew
        d.rounded_rectangle([edge_x, 0, edge_x + ew, L["h"] - 1], radius=min(r, ew), fill=tuple(self.st["accent"]) + (255,))
        big = L["big"]
        if pop["kind"] == "stat":                        # count up: one critically damped spring, never past the value
            num = "".join(ch for ch in big if ch.isdigit() or ch == ".")
            try:
                v = float(num)
                cur = v * clamp01(spring_at(t, 0, 1, 0.05, "smooth"))
                shown = f"{cur:.0f}" if "." not in num else f"{cur:.1f}"
                big = big.replace(num, shown, 1)
            except ValueError:
                pass
        d.text((L["pad"] + ew * (side == "left"), L["pad"] - int(L["asc"] * 0.12)), big, font=L["fb"],
               fill=tuple(self.st["text"]) + (255,))
        if L["label"]:
            d.text((L["pad"] + ew * (side == "left"), L["pad"] + int(L["asc"] * 0.92)), L["label"], font=L["fl"],
                   fill=tuple(self.st["accent"]) + (255,))
        if a < 0.997:
            img.putalpha(img.getchannel("A").point(lambda p, a=a: int(p * a)))
        return img, x, y


def paste_rgba(frame, img, x, y):
    """Alpha-composite a PIL RGBA image onto an RGB uint8 frame at (x, y) (sub-pixel x via a bilinear shift)."""
    from PIL import Image
    ix = math.floor(x); fx = x - ix
    if fx > 1e-3:
        pad = Image.new("RGBA", (img.size[0] + 1, img.size[1]), (0, 0, 0, 0)); pad.paste(img, (0, 0))
        img = pad.transform(pad.size, Image.AFFINE, (1, 0, -fx, 0, 1, 0), resample=Image.BILINEAR)
    H, W = frame.shape[:2]
    w, h = img.size
    x0, y0, x1, y1 = max(0, ix), max(0, y), min(W, ix + w), min(H, y + h)
    if x1 <= x0 or y1 <= y0:
        return frame
    src = np.asarray(img, np.float32)[y0 - y:y1 - y, x0 - ix:x1 - ix]
    out = frame.copy()
    al = src[..., 3:4] / 255.0
    out[y0:y1, x0:x1] = (src[..., :3] * al + out[y0:y1, x0:x1].astype(np.float32) * (1 - al)).astype(np.uint8)
    return out


READ_VF = "scale=in_color_matrix=bt709:in_range=tv,format=rgb24"
WRITE_VF = "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p"


def reader(src, f0, n, fps, W, H):
    return subprocess.Popen([FF, "-nostdin", "-v", "error", "-ss", f"{(f0 - 0.5) / fps:.6f}", "-i", src,
                             "-frames:v", str(n), "-an", "-sn", "-dn", "-vf", READ_VF, "-fps_mode", "passthrough",
                             "-f", "rawvideo", "-"],
                            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, bufsize=W * H * 3 * 2)


def warp(cv2, img, J, s, interp):
    W, H, OW, OH = J["src_w"], J["src_h"], J["out_w"], J["out_h"]
    x0, y0, w, h = window(J, s)
    if abs(w - W) < 0.5 and abs(h - H) < 0.5 and (OW, OH) == (W, H):
        return img
    sx, sy = OW / w, OH / h
    M = np.array([[sx, 0, -x0 * sx], [0, sy, -y0 * sy]], np.float64)
    return cv2.warpAffine(img, M, (OW, OH), flags=interp, borderMode=cv2.BORDER_REPLICATE)


def render_main(plan_path):
    import cv2
    with open(plan_path) as f:
        J = json.load(f)
    fn, fd = J["fps"]
    fps = fn / fd
    W, H, OW, OH = J["src_w"], J["src_h"], J["out_w"], J["out_h"]
    up = OW / J["win"][0]
    interp = cv2.INTER_CUBIC if up > 1.05 else cv2.INTER_AREA if up < 0.95 else cv2.INTER_LINEAR
    art = CardArt(J["card_style"], OW, OH)
    pops = PopArt(J["pop_style"], OW, OH) if J.get("pop_style") else None
    pop_at = {}
    for p in J.get("pops", []):
        p["fps"] = fps
        for k in range(p["f0"], p["f0"] + p["n"]):
            pop_at[k] = p
    card_at = {}
    for c in J["cards"]:
        for k in range(c["f0"], c["f0"] + c["n"]):
            card_at[k] = c
    enc = subprocess.Popen([FF, "-nostdin", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{OW}x{OH}",
                            "-framerate", f"{fn}/{fd}", "-i", "pipe:0", "-i", J["audio"], "-map", "0:v", "-map", "1:a",
                            "-vf", WRITE_VF, "-c:v", "libx264", "-preset", "medium", "-crf", str(J["crf"]),
                            "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
                            "-c:a", "aac", "-b:a", "192k", "-frames:v", str(J["total_n"]), "-movflags", "+faststart",
                            J["out"]], stdin=subprocess.PIPE)
    card_w = {}
    t_start, done, short = time.time(), 0, 0
    pre = J["zoom_spring"]
    for sg in J["segs"]:
        J["_c"] = sg["c"]
        rd = reader(J["src"], sg["in_f"], sg["n"], fps, W, H)
        last = None
        for i in range(sg["n"]):
            buf = rd.stdout.read(W * H * 3)
            if len(buf) < W * H * 3:
                short += 1
                img = last
            else:
                img = np.frombuffer(buf, np.uint8).reshape(H, W, 3)
                last = img
            k = sg["o_f"] + i
            c = card_at.get(k)
            if c is not None:
                fr = art.frame(c["title"], (k - c["f0"]) / fps)
                if c.get("file"):
                    if c["file"] not in card_w:
                        card_w[c["file"]] = subprocess.Popen(
                            [FF, "-nostdin", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{OW}x{OH}",
                             "-framerate", f"{fn}/{fd}", "-i", "pipe:0", "-vf", WRITE_VF, "-c:v", "libx264",
                             "-crf", "16", "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
                             c["file"]], stdin=subprocess.PIPE)
                    card_w[c["file"]].stdin.write(fr.tobytes())
                    if k == c["f0"] + c["n"] - 1:
                        card_w[c["file"]].stdin.close()
            else:
                fr = warp(cv2, img, J, scale_at(sg, i / fps, pre), interp)
                pp = pop_at.get(k)
                if pp is not None and pops is not None:
                    got = pops.frame(pp, (k - pp["f0"]) / fps)
                    if got is not None:
                        fr = paste_rgba(np.ascontiguousarray(fr), *got)
            enc.stdin.write(np.ascontiguousarray(fr).tobytes())
            done += 1
        rd.stdout.close()
        rd.wait()
        el = time.time() - t_start
        sys.stdout.write(f"\r  {J['aspect']}: {done / fps:6.1f} / {J['total_n'] / fps:.1f} s ({done / max(el, 1e-6):.0f} fps)")
        sys.stdout.flush()
    enc.stdin.close()
    if enc.wait() != 0:
        raise SystemExit("encoder failed")
    for p in card_w.values():
        p.wait()
    print(f"\r  {J['aspect']}: rendered {done} frames in {time.time() - t_start:.0f} s"
          + (f" ({short} short reads repeated)" if short else "") + " " * 20)


def verify_main(plan_path, video):
    """Each shot: its middle frame in the render against the source frame it came from (same crop)."""
    import cv2
    with open(plan_path) as f:
        J = json.load(f)
    fn, fd = J["fps"]
    fps = fn / fd
    W, H, OW, OH = J["src_w"], J["src_h"], J["out_w"], J["out_h"]
    cards = [(c["f0"], c["f0"] + c["n"]) for c in J["cards"]] + [(p["f0"], p["f0"] + p["n"]) for p in J.get("pops", [])]
    up = OW / J["win"][0]
    interp = cv2.INTER_CUBIC if up > 1.05 else cv2.INTER_AREA if up < 0.95 else cv2.INTER_LINEAR

    def grab(path, f, w, h):
        p = reader(path, f, 1, fps, w, h)
        b = p.stdout.read(w * h * 3)
        p.stdout.close()
        p.wait()
        return np.frombuffer(b, np.uint8).reshape(h, w, 3) if len(b) == w * h * 3 else None

    def small(img):
        return cv2.resize(cv2.cvtColor(img, cv2.COLOR_RGB2GRAY), (OW // 4, OH // 4), interpolation=cv2.INTER_AREA
                          ).astype(np.float32)

    res = []
    for k, sg in enumerate(J["segs"]):
        J["_c"] = sg["c"]
        picks = [i for i in (sg["n"] // 2, 2, sg["n"] - 3) if 0 <= i < sg["n"]
                 and not any(a <= sg["o_f"] + i < b for a, b in cards)]
        if not picks:
            res.append({"shot": k + 1, "skip": "card"})
            continue
        i = picks[0]
        out = grab(video, sg["o_f"] + i, OW, OH)
        mads = {}
        for off in (0, -1, 1):
            src = grab(J["src"], sg["in_f"] + i + off, W, H)
            if src is None or out is None:
                continue
            exp = warp(cv2, src, J, scale_at(sg, i / fps, J["zoom_spring"]), interp)
            mads[off] = float(np.mean(np.abs(small(out) - small(exp))))
        best = None
        if mads:
            o = min(mads, key=mads.get)
            best = (o, mads[o]) if o == 0 or mads.get(0, 99) - mads[o] > 0.3 else (0, mads[0])
        res.append({"shot": k + 1, "out_s": round((sg["o_f"] + i) / fps, 2), "src_s": round((sg["in_f"] + i) / fps, 2),
                    "offset": best[0] if best else None, "mad": round(best[1], 2) if best else None})
    print(json.dumps(res))


def audio_sync(video, audio, segs, fps, cards_out=()):
    """Each shot's sound in the render against the source (10 ms energy envelopes, cross-correlated within
    +-0.5 s): the lag must be 0 (+-20 ms). Returns [{shot, lag_s}] for shots that are off."""
    raw = run([FF, "-nostdin", "-v", "error", "-i", video, "-vn", "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"])
    y = np.frombuffer(raw, np.float32).astype(np.float64)
    k = int(round(HOP * SR))

    def env(x):
        n = len(x) // k
        return 10 * np.log10(np.mean(x[: n * k].reshape(n, k) ** 2, 1) + 1e-9)
    off, maxl = [], 50
    for i, sg in enumerate(segs):
        if sg["n"] / fps < 1.2:
            continue
        a0 = int(round(sg["o_f"] / fps * SR))
        o = env(y[a0: a0 + int(round(sg["n"] / fps * SR))])
        sr_ = env(audio.get(sg["in"], sg["n"] / fps, mono=True).astype(np.float64))
        m = min(len(o), len(sr_))
        o, sr_ = np.maximum(o[:m], -60), np.maximum(sr_[:m], -60)
        if np.std(sr_) < 3:
            continue
        best = max(range(-maxl, maxl + 1), key=lambda L: np.corrcoef(
            o[max(0, L):m + min(0, L)], sr_[max(0, -L):m - max(0, L)])[0, 1])
        if abs(best) > 2:
            off.append({"shot": i + 1, "lag_s": round(best * HOP, 2)})
    return off


# ---- XML -----------------------------------------------------------------------------------------------------
def probe_any_dur(path):
    return float(run([FP, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path]).strip())


def write_xml(path, name, src, info, segs, levels, pushes_by_seg, fps, cards16, music, music_in, total_s):
    import fcp7xml
    items = []
    for k, sg in enumerate(segs):
        cuts = [(sg["in"], levels[k], f"shot {k + 1}")]
        for p in pushes_by_seg[k]:
            cuts.append((sg["in_f"] / fps + round(p["t"] * fps) / fps, p["to"], f"push: {p['word']}"))
        for j, (a, sc, lab) in enumerate(cuts):
            b = cuts[j + 1][0] if j + 1 < len(cuts) else sg["out"]
            if b - a < 0.5 / fps:
                continue
            items.append({"file": "src", "in": a, "out": b, "label": lab, "scale": round(sc * 100, 2)})
    E = {"name": name, "fps": fps, "w": info["w"], "h": info["h"],
         "files": {"src": {"path": os.path.abspath(src), "dur": info["dur"], "audio_ch": 2}},
         "items": items,
         "overlays": [{"path": os.path.abspath(p), "dur": n / fps, "at": f0 / fps, "in": 0, "out": n / fps,
                       "label": f"card: {title}"} for f0, n, title, p in cards16],
         "markers": [{"at": f0 / fps, "name": f"card: {title}"} for f0, n, title, p in cards16]}
    if music:
        E["music"] = [{"path": os.path.abspath(music), "dur": probe_any_dur(music),
                       "at": 0.0, "in": music_in, "out": music_in + total_s, "gain_db": 0}]
    with open(path, "w") as f:
        f.write(fcp7xml.build(E))


# ---- main ----------------------------------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("video")
    ap.add_argument("--out", required=True, help="output folder")
    prof.add_arg(ap)
    ap.add_argument("--name", help="output base name (default: the video's name)")
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--end", type=float, default=None)
    ap.add_argument("--music", help="music bed (cards cut on its beat)")
    ap.add_argument("--music-in", type=float, default=0.0, help="music start offset (s)")
    ap.add_argument("--aspects", default="16:9,9:16")
    ap.add_argument("--words-file", help="use this words.json instead of <out>/<name>.words.json")
    ap.add_argument("--model", default="small.en")
    ap.add_argument("--min-prob", type=float, default=0.35)
    ap.add_argument("--fresh", action="store_true", help="plan again (moves the old talkedit.json to _old/)")
    ap.add_argument("--plan-only", action="store_true", help="write the plan JSON and stop")
    ap.add_argument("--no-captions", action="store_true")
    ap.add_argument("--caption-layer", action="store_true", help="also keep the captions' ProRes 4444 caption layer (.mov)")
    ap.add_argument("--crf", type=int, default=18)
    ap.add_argument("--qa", action="store_true", help="run engine/qa.py on every output")
    ap.add_argument("--preview", action="store_true", help="phone previews under 30 MB in <out>/preview/")
    a = ap.parse_args(argv)

    import captions as C
    P = prof.load(a.profile)
    R = merge(RECIPE, P.get("talkedit", {}) or {})
    R["cut"]["fade_ms"] = max(40, R["cut"]["fade_ms"])
    out_dir = os.path.abspath(a.out)
    os.makedirs(out_dir, exist_ok=True)
    st = stamp()
    name = a.name or os.path.splitext(os.path.basename(a.video))[0].replace(" ", "_")
    info = probe(a.video)
    if not info["audio"]:
        raise SystemExit("no audio stream: talkedit needs the voice")
    fps = info["fps"]
    t0 = max(0.0, a.start)
    t1 = min(info["dur"], a.end) if a.end else info["dur"]
    t1 = min(t1, info["dur"] - 1.0 / fps)
    print(f"{os.path.basename(a.video)}: {info['w']}x{info['h']} {fps:.3f} fps, {t1 - t0:.1f} s"
          + (f", audio starts {info['aoff']:.3f} s late" if info["aoff"] > 0.001 else ""))

    work = tempfile.TemporaryDirectory(prefix=f".talkedit_{name}_", dir=out_dir)
    print("audio: decoding the clip's sound (sample-exact, on the picture's clock) ...")
    audio = Audio(a.video, t0, t1, info["aoff"], os.path.join(work.name, "source.wav"))
    wd, words_path = get_words(C, a, audio, out_dir, name, P, t0, t1)
    env = Env(audio, t0, t1)
    print(f"  voice: floor {env.floor:.0f} dB, speech {env.speech:.0f} dB, quiet under {env.thr:.0f} dB")
    speech, fillers = classify(wd, env, R, t0, t1)
    speech = add_islands(speech, fillers, env, R)

    plan_path = os.path.join(out_dir, f"{name}.talkedit.json")
    D = None
    if os.path.exists(plan_path) and a.fresh:
        move_aside(plan_path, out_dir, st)
    if os.path.exists(plan_path):
        with open(plan_path) as f:
            D = json.load(f)
        print(f"plan: using {plan_path} (your edits are kept; --fresh plans again)")
        removals = D["removals"]
        for r in removals:
            r.setdefault("on", True)
            r.setdefault("why", "added by hand")
    else:
        removals, skipped = plan_removals(speech, fillers, env, R, t0, t1, fps)
        print(f"cuts: {len(removals)} planned ({sum('filler' in r['why'] or 'repeat' in r['why'] for r in removals)}"
              f" with fillers), {len(skipped)} left in (no clean quiet point or sound in the gap)")
    segs, total_n = segments(removals, t0, t1, fps)
    mp = Mapper(segs, fps)
    total_s = total_n / fps
    if D is None:
        plan_punches(removals, segs, R, fps)
    levels = seg_levels(segs)

    # music beats
    beats = None
    if a.music:
        import beatmap
        print("music: measuring the beat grid (beatmap.py) ...")
        m = beatmap.build(a.music, start=a.music_in, dur=total_s + 2.0, fps=fps)
        beats = np.array(m["beats"], float)
        print(f"  {len(beats)} beats")

    if D is None:
        cards = plan_cards(speech, mp, R, fps, total_s)
    else:
        cards = D.get("cards", [])
    edges = [x for w in speech for x in (mp.out(w["s"]), mp.out(w["e"])) if x is not None]
    ct = card_times(cards, mp, fps, total_n, beats, R["music"]["snap_s"], R["cards"], edges)
    cards_out = [(f0 / fps, (f0 + n) / fps) for f0, n, c in ct]
    if D is None:
        zooms = plan_pushes(C, speech, env, segs, mp, cards_out, R, fps, total_s)
    else:
        zooms = D.get("zooms", [])
    if D is None or "pops" not in D:
        pops = plan_pops(speech, mp, R, total_s, cards_out)
    else:
        pops = D.get("pops", [])

    bad = check_cuts(segs, speech, env, fps)
    removed_s = (t1 - t0) - total_s
    D = {"version": VERSION, "source": os.path.abspath(a.video), "range": [round(t0, 3), round(t1, 3)],
         "fps": f"{info['fn']}/{info['fd']}", "profile": P.name,
         "words": os.path.abspath(words_path), "made": time.strftime("%Y-%m-%d %H:%M"),
         "note": "Times are seconds of the source video. Edit and re-run talkedit.py with the same --out: "
                 "removals[].on=false puts that pause/filler back; 'punch' is the framing scale after that cut; "
                 "add a cut with {\"s\": a, \"e\": b}; zooms[].add / on; cards[].title / dur / on; pops[].big / label / dur / on. "
                 "--fresh throws this plan away (moved to _old/) and plans again.",
         "recipe": R, "result": {"source_s": round(t1 - t0, 2), "cut_s": round(total_s, 2),
                                 "removed_s": round(removed_s, 2), "cuts": len(segs) - 1,
                                 "fillers_found": len(fillers), "mid_word_problems": bad},
         "removals": removals, "zooms": zooms, "cards": cards, "pops": pops}
    tmp = plan_path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(D, f, indent=1, default=lambda o: None)
    if os.path.exists(plan_path):
        move_aside(plan_path, out_dir, st)
    os.replace(tmp, plan_path)
    print(f"plan: {t1 - t0:.1f} s -> {total_s:.1f} s ({len(segs) - 1} cuts, {len(fillers)} fillers, "
          f"{sum(1 for z in zooms if z.get('on', True))} push-ins, {len(ct)} cards, "
          f"{sum(1 for p in pops if p.get('on', True))} pop-ups) -> {plan_path}")
    if bad:
        print(f"  WARNING: {len(bad)} cuts are not clean (word too close or no quiet):")
        for b in bad[:10]:
            print("   ", b)
    else:
        print("  every cut is clear of words and in quiet")
    if a.plan_only:
        work.cleanup()
        return 0

    # pushes per segment (output-relative seconds)
    pushes_by_seg = [[] for _ in segs]
    for z in zooms:
        if not z.get("on", True):
            continue
        k = mp.seg_of(z["t"])
        if k is None:
            continue
        sg = segs[k]
        rel = max(0.0, z["t"] - sg["in"] - R["zoom"]["push_lead_s"])
        frm = pushes_by_seg[k][-1]["to"] if pushes_by_seg[k] else levels[k]
        to = min(R["zoom"]["max_scale"], frm + float(z.get("add", R["zoom"]["push_add"])))
        pushes_by_seg[k].append({"t": round(rel, 4), "from": frm, "to": to, "word": z.get("word", "")})

    # the hook: with no cut or push in the first 2 s, the shot opens 12% tighter and springs out to its framing
    hp = float(R["zoom"].get("hook_push", 0) or 0)
    first_event = min([sg["o_f"] / fps for sg in segs[1:]] + [z["t"] for z in pushes_by_seg[0]] + [99.0])
    if hp > 0 and first_event > 2.0 and not any(ca < 2.0 for ca, cb in cards_out):
        lv = levels[0]
        pushes_by_seg[0].insert(0, {"t": 0.0, "from": round(lv + hp, 4), "to": lv, "word": "(hook)", "preset": "smooth"})

    wav0, wav = os.path.join(work.name, "mix.wav"), os.path.join(work.name, "mix_ln.wav")
    print("audio: cutting with fades ...")
    build_audio(audio, segs, fps, R, total_n, a.music, a.music_in, wav0)
    loudnorm(wav0, wav, float(P.get("delivery.loudness_lufs", -14)), float(P.get("delivery.true_peak_db", -2)))
    if env.floor < -80 and R["cut"].get("room_tone_db") is not None and not a.music:
        room_tone(wav, R["cut"]["room_tone_db"])
        print(f"  gated source (silence at {env.floor:.0f} dB): room tone at {R['cut']['room_tone_db']:.0f} dBFS under it")

    cc = R["cards"]

    def colour(v):
        v = P.color(v) if v in (P.get("brand.colors", {}) or {}) else v
        v = v.lstrip("#")
        return [int(v[i:i + 2], 16) for i in (0, 2, 4)]

    fnt = cc["font"]
    card_style = {"font": P.font(fnt) if fnt in (P.get("brand.fonts", {}) or {}) else os.path.expanduser(fnt),
                  "bg": colour(cc["bg"]), "text": colour(cc["text"]), "accent": colour(cc["accent"]),
                  "spring": cc["spring"], "uppercase": cc["uppercase"],
                  "safe_px": int(P.get("layout.safe_px", 90))}
    pc = R["pops"]
    pfont = lambda role: P.font(role) if role in (P.get("brand.fonts", {}) or {}) else os.path.expanduser(role)
    pop_style = {"head": pfont(pc["head_font"]), "body": pfont(pc["body_font"]), "bg": colour(pc["bg"]),
                 "text": colour(pc["text"]), "accent": colour(pc["accent"]), "spring": pc["spring"],
                 "uppercase": pc["uppercase"], "safe_px": int(P.get("layout.safe_px", 90))}
    cards_dir = os.path.join(out_dir, "cards")
    os.makedirs(cards_dir, exist_ok=True)

    # captions words on the cut's clock, never under a card
    cap_words = []
    for w in speech:
        if w.get("nocap"):
            continue
        s, e = mp.out(w["s"]), mp.out(w["e"])
        if s is None:
            continue
        e = e if e is not None and e > s else s + (w["e"] - w["s"])
        if any(ca - 0.02 <= s < cb for ca, cb in cards_out):
            continue
        cw = {"w": w["w"], "s": round(s, 3), "e": round(e, 3), "p": w.get("p", 1.0)}
        for k_ in ("key", "break"):
            if k_ in w:
                cw[k_] = w[k_]
        if any(abs(s - cb) < 0.5 for ca, cb in cards_out):
            cw["break"] = True
        cap_words.append(cw)
    caps_srt = C.group([dict(w) for w in cap_words])
    C.time_captions(caps_srt, total_s)
    srt = os.path.join(out_dir, f"{name}.srt")
    move_aside(srt, out_dir, st)
    C.write_srt(srt, caps_srt)

    outputs, cutinfo = {}, {}
    cut_times = [round(sg["o_f"] / fps, 3) for sg in segs[1:]]
    print("faces: finding the speaker for the framing ...")
    faces = find_faces(a.video, t0, t1)
    faces_c = face_centres(faces, segs, info)
    print(f"  {len(faces)} face samples")
    for asp in [x.strip() for x in a.aspects.split(",") if x.strip()]:
        vertical = asp == "9:16"
        tag = asp.replace(":", "x")
        ow, oh = (int(x) for x in P.get("delivery.vertical_size" if vertical else "delivery.size",
                                        "1080x1920" if vertical else "1920x1080").split("x"))
        W, H = info["w"], info["h"]
        ar = ow / oh
        win = [H * ar, H] if W / H >= ar else [W, W / ar]
        J = {"src": os.path.abspath(a.video), "fps": [info["fn"], info["fd"]], "src_w": W, "src_h": H,
             "out_w": ow, "out_h": oh, "win": win, "aspect": asp, "crf": 14, "total_n": total_n,
             "face_y": R["zoom"]["vertical_face_y" if vertical else "face_y"], "zoom_spring": R["zoom"]["spring"],
             "audio": wav, "card_style": card_style, "pop_style": pop_style,
             "segs": [{"in_f": sg["in_f"], "n": sg["n"], "o_f": sg["o_f"], "level": levels[k],
                       "pushes": pushes_by_seg[k], "c": faces_c[k]} for k, sg in enumerate(segs)],
             "cards": []}
        J["pops"] = []
        for pp in pops:
            if not pp.get("on", True):
                continue
            to = mp.out(pp["t"])
            if to is None:
                continue
            f0, n = int(round(to * fps)), int(round(float(pp["dur"]) * fps))
            k = mp.seg_of(pp["t"])
            fx = faces_c[k][0] / W if k is not None and faces_c[k] else 0.5
            J["pops"].append({"f0": f0, "n": min(n, total_n - f0), "kind": pp.get("kind", "word"), "big": str(pp["big"]),
                              "label": pp.get("label", ""), "side": "left" if fx > 0.5 else "right"})
        for f0, n, c in ct:
            cf = os.path.join(cards_dir, f"{name}_card{c.get('id', 0):02d}.mp4") if not vertical else None
            if cf:
                move_aside(cf, out_dir, st)
            J["cards"].append({"f0": f0, "n": n, "title": c["title"], "file": cf})
        base = os.path.join(work.name, f"base_{tag}.mp4")
        J["out"] = base
        jp = os.path.join(work.name, f"plan_{tag}.json")
        with open(jp, "w") as f:
            json.dump(J, f)
        print(f"render {asp} {ow}x{oh} ...")
        r = subprocess.run([sys.executable, os.path.abspath(__file__), "_render", jp], stdin=subprocess.DEVNULL)
        if r.returncode != 0:
            raise SystemExit("render failed")
        print("  checking every shot against its source ...")
        vr = subprocess.run([sys.executable, os.path.abspath(__file__), "_verify", jp, base],
                            stdin=subprocess.DEVNULL, capture_output=True, text=True)
        checks = json.loads(vr.stdout.strip().splitlines()[-1]) if vr.returncode == 0 else []
        badshots = [x for x in checks if x.get("mad") is not None and (x["offset"] != 0 or x["mad"] > 4.0)]
        print(f"  {len(checks)} shots checked, {len(badshots)} off" + (f": {badshots[:5]}" if badshots else ""))
        final = os.path.join(out_dir, f"{name}_{tag}.mp4")
        if a.no_captions or not R["captions"].get("on", True):
            move_aside(final, out_dir, st)
            shutil.move(base, final)
        else:
            caps = C.group([dict(w) for w in cap_words])
            C.time_captions(caps, total_s)
            for c in caps:                       # never over a card
                nxt = [ca for ca, cb in cards_out if ca >= c["start"]]
                if nxt:
                    c["end"] = round(min(c["end"], nxt[0] - 1.0 / fps), 3)
            # E1 lets a caption fade out into the gap after it; an empty caption at each card's first frame
            # closes that gap, so the caption before a card is gone by the cut
            for ca, cb in cards_out:
                caps.append({"words": [{"w": " ", "s": ca, "e": ca + 1.0 / fps, "p": 1.0}], "text": " ",
                             "start": round(ca, 3), "last": round(ca + 1.0 / fps, 3),
                             "end": round(ca + 2.0 / fps, 3), "key": None})
            caps.sort(key=lambda c: c["start"])
            S = C.style(P, vertical)
            print(f"  captions ({len(caps)}) ...")
            mov, mp4, _ = C.render(base, work.name, f"cap_{tag}", caps, S, "16:9", info["fn"], info["fd"], 0.0,
                                   total_s, True, a.caption_layer, True, a.crf)
            move_aside(final, out_dir, st)
            shutil.move(mp4, final)
            if mov:
                lay = os.path.join(out_dir, f"{name}_captions_{tag}.mov")
                move_aside(lay, out_dir, st)
                shutil.move(mov, lay)
        sync = audio_sync(final, audio, segs, fps)
        print(f"  sound in sync with the picture in every shot" if not sync else f"  SOUND OFF in {len(sync)} shots: {sync[:6]}")
        outputs[asp] = final
        holds = []
        for f0, n, c in ct:
            s_ = f0 / fps + CardArt(card_style, ow, oh).settle_s(c["title"])
            if s_ < (f0 + n) / fps - 0.05:
                holds.append(f"{s_:.2f}-{(f0 + n) / fps:.2f}")
        cutinfo[asp] = {"file": final, "cuts": sorted(cut_times + [round(x, 3) for ca, cb in cards_out
                                                                     for x in (ca, cb)]),
                        "audio_cuts": cut_times, "holds": ",".join(holds), "shot_checks": checks,
                        "sound_off": sync}
        print(f"  wrote {final} ({os.path.getsize(final) / 1e6:.0f} MB)")

    cj = os.path.join(out_dir, f"{name}.cuts.json")
    move_aside(cj, out_dir, st)
    with open(cj, "w") as f:
        json.dump(cutinfo, f, indent=1)

    xml = os.path.join(out_dir, f"{name}_16x9.xml")
    move_aside(xml, out_dir, st)
    cards16 = [(f0, n, c["title"], os.path.join(cards_dir, f"{name}_card{c.get('id', 0):02d}.mp4"))
               for f0, n, c in ct]
    cards16 = [x for x in cards16 if os.path.exists(x[3])]
    write_xml(xml, f"{name} talkedit", a.video, info, segs, levels, pushes_by_seg, fps, cards16, a.music,
              a.music_in, total_s)
    print(f"wrote {xml}")
    work.cleanup()

    if a.qa:
        for asp, ci in cutinfo.items():
            qdir = os.path.join(out_dir, f"qa_{asp.replace(':', 'x')}")
            if os.path.exists(qdir):
                move_aside(qdir, out_dir, st)
            cmd = [sys.executable, os.path.join(HERE, "qa.py"), ci["file"], "--kind", "edit",
                   "--cuts", ",".join(f"{x:.3f}" for x in ci["cuts"]) or "none", "--out", qdir]
            if a.profile:
                cmd += ["--profile", a.profile]
            if ci["holds"]:
                cmd += ["--holds", ci["holds"]]
            print(f"qa {asp}: {' '.join(cmd[2:3])} ...")
            r = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True)
            print("  " + "\n  ".join(r.stdout.strip().splitlines()[-4:]))
    if a.preview:
        pdir = os.path.join(out_dir, "preview")
        os.makedirs(pdir, exist_ok=True)
        for asp, fpath in outputs.items():
            vertical = asp == "9:16"
            pv = os.path.join(pdir, os.path.basename(fpath).replace(".mp4", "_540w.mp4" if vertical else "_720p.mp4"))
            move_aside(pv, out_dir, st)
            make_preview(fpath, pv, vertical)
            print(f"preview {pv} ({os.path.getsize(pv) / 1e6:.1f} MB)")
    return 0


def make_preview(src, dst, vertical, max_mb=29.0):
    d = probe(src)["dur"]
    kbps = int(min(2500, (max_mb * 8000 / d) - 128) * 0.92)
    vf = "scale=540:960" if vertical else "scale=1280:720"
    run([FF, "-nostdin", "-v", "error", "-i", src, "-vf", vf, "-c:v", "libx264", "-preset", "medium",
         "-b:v", f"{kbps}k", "-maxrate", f"{int(kbps * 1.4)}k", "-bufsize", f"{kbps * 2}k", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", dst])


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "_faces":
        faces_main(sys.argv[2], float(sys.argv[3]), float(sys.argv[4]), float(sys.argv[5]))
    elif len(sys.argv) > 1 and sys.argv[1] == "_render":
        render_main(sys.argv[2])
    elif len(sys.argv) > 1 and sys.argv[1] == "_verify":
        verify_main(sys.argv[2], sys.argv[3])
    else:
        sys.exit(main())
