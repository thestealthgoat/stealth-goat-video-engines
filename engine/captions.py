#!/usr/bin/env python3
"""captions.py - kinetic captions: word-synced 1-4 word captions that spring in word by word, one keyword
per caption in an outlined box. Burned-in MP4 + transparent caption layer (.mov, ProRes 4444) + .srt.

    python3 engine/captions.py <video> --out <dir> [--profile NAME] [--aspect 16:9|9:16]
                               [--words-file words.json] [--prompt "names, places"] [--model small.en]
                               [--start S --end S] [--words-only] [--no-mov] [--no-mp4] [--crf 18]
                               [--vertical-fill auto|band|crop] [--min-prob 0.35] [--name NAME]

Steps:
  1. Words. Local faster-whisper (default small.en, int8 on the CPU, HF_HUB_OFFLINE=1: the audio never leaves the
     machine) with word timestamps and the VAD filter. Hallucinations are dropped: words under --min-prob (0.35)
     unless confident words sit right on both sides of them,
     segments that look like silence (no_speech_prob > 0.6 and avg_logprob < -1), and stock phrases
     ("thanks for watching", "subscribe", ...). Written to <out>/<name>.words.json, one word per line, with the
     dropped words listed under "dropped". Fix spelling there and re-run with --words-file (no transcription).
     Per word: "w" text, "s"/"e" seconds, "p" probability; optional "key": true|false (force / forbid the
     highlight), "break": true (start a new caption at this word). Delete a line to drop a word.
  2. Captions. Greedy grouping: 1-4 words, <= 42 characters, a new caption after . ? ! (and after a comma once a
     caption has 2 words) and at any pause over 0.45 s. On screen from the first word (0.05 s lead) to the last
     word + 0.25 s, then stretched into the gap to the next caption for >= 0.4 s on screen and <= 30 characters
     per second. Anything still breaking a rule is listed in <out>/<name>.captions.json under "violations"
     and printed. Keyword: the strongest content word (numbers, names, long words; never a stop word).
  3. Render. PIL draws only the caption strip; every word springs in at its own start (engine/spring.py:
     y and scale on the profile's spring, default "snappy"; opacity on "ui", clamped), the keyword box springs
     with its word, the caption fades out on "smooth" when there is room, else the next one replaces it. One ffmpeg -nostdin pass
     writes the alpha layer (full frame, ProRes 4444 yuva444p10le) and the burned-in MP4 (libx264, audio copied
     untouched, so no new audio cuts). --aspect 9:16 from a 16:9 source: the full frame as a 1080-wide band
     over a blurred, darkened copy, captions under the band (clear of the Reels/TikTok UI); shots that are
     portrait phone clips pillarboxed in the 16:9 fill the frame instead (--vertical-fill auto; the shot list
     is <out>/<name>.fill.json, editable, reused on re-runs).

Style comes from the profile's "captions" block (every key optional; see profiles/_template/profile.json):
  font (a brand.fonts role or a path), font_index (.ttc face), size / size_vertical (px), uppercase,
  text, stroke, stroke_width, shadow, box_color, box_width, box_fill, box_radius, box_pad,
  y / y_vertical (caption centre as a fraction of the height), max_width / max_width_vertical (fraction),
  band_y_vertical (px, band top in 9:16), spring.
Defaults: brand.fonts.body, white text, brand accent box, centre at 0.82 (16:9) / 0.70 (9:16).

Outputs in --out: <name>.words.json, <name>.captions.json, <name>.srt,
<name>_captions_<16x9|9x16>.mov, <name>_captioned_<16x9|9x16>.mp4.
"""
import argparse
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import vprofile as prof  # noqa: E402
from spring import clamp01, settle, spring_at  # noqa: E402

FF = "/opt/homebrew/bin/ffmpeg" if os.path.exists("/opt/homebrew/bin/ffmpeg") else "ffmpeg"
FP = "/opt/homebrew/bin/ffprobe" if os.path.exists("/opt/homebrew/bin/ffprobe") else "ffprobe"

# ---- caption rules -----------------------------------------------------------------------------------------
MAX_WORDS, MAX_CHARS, MIN_DUR, MAX_CPS = 4, 42, 0.40, 30.0
PAUSE_BREAK = 0.45      # a pause longer than this starts a new caption
LEAD = 0.05             # words start springing this much before they are spoken
TAIL = 0.25             # a caption stays this long after its last word (if there is room)
HOLD_MAX = 0.8          # ... and at most this long into a gap
MIN_PROB = 0.35
GAP_FILL = 1.5          # 9:16 auto fill: band gaps shorter than this between full-frame shots are filled
GAP_SOFT = 8.0          # ... and low-detail stretches with blurred, text-free sides up to this long
SWAP_HEAD = 0.07        # back-to-back captions: the new first word is already ~70% opaque on its first frame

HALLUCINATIONS = [
    "thanks for watching", "thank you for watching", "thank you so much for watching", "please subscribe",
    "like and subscribe", "subscribe to my channel", "see you in the next video", "see you next time",
    "thank you for listening", "subtitles by", "captions by", "transcribed by",
]

STOP = set("""
a an the and or but so if then than that this these those there here it its it's i i'm i've i'll i'd me my mine
we we're we've we'll us our you you're your yours he he's him his she she's her they they're them their what
which who whom whose when where why how is are was were be been being am do does did done doing have has had
having will would shall should can could may might must not no yes yeah yep ok okay oh uh um uhm hmm like just
really very so too also of in on at to for from by with about into onto over under up down out off as all any
some just kind sort gonna wanna gotta got get gets go goes going went come comes came thing things stuff right
well now one ones lot lots more most much many way because cause 'cause let let's that's what's there's here's
don't doesn't didn't can't won't isn't aren't wasn't weren't im ive dont
""".split())


def run(cmd, **kw):
    r = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, **kw)
    if r.returncode != 0:
        sys.stderr.write(r.stderr.decode(errors="replace")[-3000:])
        raise SystemExit(f"command failed: {' '.join(map(str, cmd[:8]))} ...")
    return r.stdout


def probe(video):
    j = json.loads(run([FP, "-v", "error", "-show_entries",
                        "stream=codec_type,width,height,r_frame_rate:format=duration", "-of", "json", video]))
    v = next(s for s in j["streams"] if s["codec_type"] == "video")
    num, den = (int(x) for x in v["r_frame_rate"].split("/"))
    has_audio = any(s["codec_type"] == "audio" for s in j["streams"])
    return int(v["width"]), int(v["height"]), num, den, float(j["format"]["duration"]), has_audio


# ---- 1. words ------------------------------------------------------------------------------------------------
def transcribe(video, work, model_name, prompt, min_prob, t0=None, t1=None):
    os.environ.setdefault("HF_HUB_OFFLINE", "1")        # local model only; nothing is uploaded
    tmp = tempfile.TemporaryDirectory(prefix="captions_")
    wav = os.path.join(tmp.name, "audio16k.wav")
    # output-side -ss: sample-exact (an input-side seek can put audio up to ~1 s off on files with an edit list)
    cmd = [FF, "-nostdin", "-v", "error", "-y", "-i", video]
    if t0 is not None:
        cmd += ["-ss", f"{t0:.3f}"]
    if t1 is not None:
        cmd += ["-t", f"{t1 - (t0 or 0):.3f}"]
    run(cmd + ["-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", wav])
    from faster_whisper import WhisperModel
    m = WhisperModel(model_name, device="cpu", compute_type="int8")
    import wave
    with wave.open(wav) as wf:    # hand whisper samples, not a file: its PyAV decoder can be the wrong version
        audio = np.frombuffer(wf.readframes(wf.getnframes()), np.int16).astype(np.float32) / 32768.0
    segs, info = m.transcribe(audio, language="en", word_timestamps=True, vad_filter=True,
                              vad_parameters={"min_silence_duration_ms": 500}, beam_size=5,
                              condition_on_previous_text=False, initial_prompt=prompt or None)
    off = t0 or 0.0
    words, dropped = [], []
    for sg in segs:
        text = re.sub(r"[^a-z ]", "", sg.text.lower()).strip()
        silent = sg.no_speech_prob > 0.6 and sg.avg_logprob < -1.0
        probs = [w.probability for w in (sg.words or [])] or [0.0]
        # a stock phrase on its own (not inside real talk) that whisper is unsure of, or that sits on near-silence
        stock = any(h in text and len(text) <= len(h) + 14 for h in HALLUCINATIONS) and \
            (sg.no_speech_prob > 0.2 or sum(probs) / len(probs) < 0.7)
        for w in (sg.words or []):
            d = {"w": w.word.strip(), "s": round(w.start + off, 3), "e": round(w.end + off, 3),
                 "p": round(w.probability, 3)}
            if not d["w"]:
                continue
            why = "silence segment" if silent else "stock phrase" if stock else \
                  "low probability" if w.probability < min_prob else None
            if why:
                d["why"] = why
                dropped.append(d)
            else:
                words.append(d)
        sys.stdout.write(f"\r  transcribed to {sg.end + off:7.1f} s, {len(words)} words")
        sys.stdout.flush()
    print()
    tmp.cleanup()
    words, dropped = restore_sandwiched(words, dropped)
    return {"source": os.path.abspath(video), "model": model_name, "prompt": prompt or "",
            "made": time.strftime("%Y-%m-%d %H:%M"), "min_prob": min_prob,
            "note": "Fix 'w' to correct spelling. 'key': true forces this word as the highlight, false forbids it. "
                    "'break': true starts a new caption at this word. Delete a line to drop a word. Times in "
                    "seconds of the source video. Re-run captions.py with --words-file this.json.",
            "words": words, "dropped": dropped}


def restore_sandwiched(words, dropped):
    """A low-probability word said in the middle of confident speech is usually real ('the corner store'):
    keep it when the words either side are within 0.3 s and have p >= 0.6. Hallucinations sit on their own."""
    import bisect
    words = sorted(words, key=lambda w: w["s"])
    keep, still = [], []
    starts = [w["s"] for w in words]
    for x in dropped:
        i = bisect.bisect(starts, x["s"])
        pv, nx = (words[i - 1] if i else None), (words[i] if i < len(words) else None)
        if (x.get("why") == "low probability" and pv and nx and x["p"] >= 0.1 and x["e"] - x["s"] >= 0.06
                and x["s"] - pv["e"] < 0.3 and nx["s"] - x["e"] < 0.3 and pv["p"] >= 0.6 and nx["p"] >= 0.6):
            keep.append({k: v for k, v in x.items() if k != "why"})
        else:
            still.append(x)
    return sorted(words + keep, key=lambda w: w["s"]), still


def write_words(path, d):
    """One word per line so the file is easy to fix by hand."""
    head = {k: v for k, v in d.items() if k not in ("words", "dropped")}
    with open(path, "w") as f:
        f.write("{\n")
        for k, v in head.items():
            f.write(f"  {json.dumps(k)}: {json.dumps(v)},\n")
        for key in ("words", "dropped"):
            items = d.get(key, [])
            f.write(f'  "{key}": [\n')
            f.write(",\n".join("    " + json.dumps(w, ensure_ascii=False) for w in items))
            f.write("\n  ]" + (",\n" if key == "words" else "\n"))
        f.write("}\n")


# ---- 2. captions ---------------------------------------------------------------------------------------------
def bare(w):
    return re.sub(r"[^\w'%$&-]", "", w.lower())


def keyword(ws):
    forced = [i for i, w in enumerate(ws) if w.get("key") is True]
    if forced:
        return forced[0]
    best, best_score = None, 0.0
    for i, w in enumerate(ws):
        b = bare(w["w"])
        if w.get("key") is False or not b or b in STOP or (len(b) < 3 and not b.isdigit()):
            continue
        score = len(b)
        if any(c.isdigit() for c in b):
            score += 5
        if w["w"][:1].isupper() and i > 0:
            score += 3               # a name or place mid-caption
        if w["w"].rstrip().endswith("!"):
            score += 2
        if score > best_score:
            best, best_score = i, score
    return best


LEADS_ON = set("the a an to of in on at for with from my your our his her their its and but or so because "
               "that this these those is was are were be".split())
SIZE_COST = {1: 3.0, 2: 0.8, 3: 0.0, 4: 0.2}


def join_fragments(words):
    """Whisper splits '7:20' into '7' '.20' and 'walk-in' into 'walk' '-in': glue those back onto the word before."""
    out = []
    for w in words:
        if out and w["w"][:1] in ".-'" and len(w["w"]) > 1 and w["s"] - out[-1]["e"] < 0.3:
            out[-1] = dict(out[-1], w=out[-1]["w"] + w["w"], e=w["e"], p=min(out[-1]["p"], w["p"]))
        else:
            out.append(dict(w))
    return out


def _chunks(run, gap_after):
    """Split one stretch of talk (no pause over PAUSE_BREAK) into captions of 1-4 words with the lowest cost:
    breaks after sentence ends, commas and small pauses; no caption ending on 'the', 'to', 'and'...;
    no caption too short to read (MIN_DUR, MAX_CPS); 3-4 words preferred over 1."""
    n = len(run)
    best = [0.0] + [math.inf] * n
    back = [0] * (n + 1)
    for j in range(1, n + 1):
        for k in range(1, MAX_WORDS + 1):
            i = j - k
            if i < 0:
                break
            ws = run[i:j]
            text = " ".join(w["w"] for w in ws)
            if len(text) > MAX_CHARS:
                continue
            c = SIZE_COST[k]
            start = ws[0]["s"] - LEAD
            end = run[j]["s"] - LEAD if j < n else ws[-1]["e"] + min(HOLD_MAX, gap_after)
            need = max(MIN_DUR, len(text) / MAX_CPS)
            if end - start < need:
                c += 8 + 10 * (need - (end - start))
            for w in ws[:-1]:                       # a sentence end inside a caption
                c += 4 if w["w"].endswith((".", "?", "!")) else 0.8 if w["w"].endswith((",", ";", ":")) else 0
            if j < n:
                last = ws[-1]["w"]
                if last.endswith((".", "?", "!")):
                    c -= 1.5
                elif last.endswith((",", ";", ":")):
                    c -= 0.8
                elif bare(last) in LEADS_ON:
                    c += 1.5
                c -= 4 * min(run[j]["s"] - ws[-1]["e"], PAUSE_BREAK)
            if best[i] + c < best[j]:
                best[j], back[j] = best[i] + c, i
    cuts, j = [], n
    while j > 0:
        cuts.append((back[j], j))
        j = back[j]
    return [run[a:b] for a, b in reversed(cuts)]


def group(words):
    words = join_fragments(words)
    runs, cur = [], []
    for w in words:
        if cur and (w["s"] - cur[-1]["e"] > PAUSE_BREAK or w.get("break")):
            runs.append(cur)
            cur = []
        cur.append(w)
    if cur:
        runs.append(cur)
    out = []
    for r, run in enumerate(runs):
        gap = (runs[r + 1][0]["s"] - run[-1]["e"]) if r + 1 < len(runs) else HOLD_MAX
        for ws in _chunks(run, gap):
            out.append({"words": ws, "text": " ".join(w["w"] for w in ws), "start": max(0.0, ws[0]["s"] - LEAD),
                        "last": ws[-1]["e"], "key": keyword(ws)})
    return out


def time_captions(caps, dur):
    """End times: last word + TAIL, stretched for MIN_DUR / MAX_CPS, never into the next caption."""
    viol = []
    for i, c in enumerate(caps):
        nxt = caps[i + 1]["start"] if i + 1 < len(caps) else dur
        limit = min(nxt, c["last"] + HOLD_MAX, dur)
        need = max(MIN_DUR, len(c["text"]) / MAX_CPS)
        end = max(c["last"] + TAIL, c["start"] + need)
        c["end"] = round(max(min(end, limit), min(c["last"], nxt)), 3)
        if c["end"] - c["start"] < need - 1e-3:
            # too fast to read here: start it earlier only if the previous caption has room to give
            prev_end = caps[i - 1]["end"] if i else 0.0
            c["start"] = round(max(prev_end, c["end"] - need, 0.0), 3)
        d = c["end"] - c["start"]
        cps = len(c["text"]) / d if d > 0 else 999
        if d < MIN_DUR - 1e-3 or cps > MAX_CPS + 1e-3:
            viol.append({"i": i + 1, "text": c["text"], "dur": round(d, 3), "cps": round(cps, 1)})
    return viol


def srt_time(t):
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def write_srt(path, caps, offset=0.0):
    with open(path, "w") as f:
        for i, c in enumerate(caps, 1):
            f.write(f"{i}\n{srt_time(c['start'] - offset)} --> {srt_time(c['end'] - offset)}\n{c['text']}\n\n")


# ---- 3. style + render ---------------------------------------------------------------------------------------
def style(P, vertical):
    C = P.get("captions", {}) or {}
    colors = P.get("brand.colors", {})

    def col(v, default):
        v = C.get(v, default)
        v = colors.get(v, v) if isinstance(v, str) else v
        if isinstance(v, str):
            v = v.lstrip("#")
            if len(v) == 6:
                v += "ff"
            return tuple(int(v[i:i + 2], 16) for i in (0, 2, 4, 6))
        return tuple(v) + ((255,) if len(v) == 3 else ())

    f = C.get("font", "body")
    fpath = P.font(f) if f in P.get("brand.fonts", {}) else os.path.expanduser(P._expand(f))
    return {
        "font": fpath, "font_index": int(C.get("font_index", 0)),
        "size": int(C.get("size_vertical" if vertical else "size", 84 if vertical else 76)),
        "upper": bool(C.get("uppercase", False)),
        "text": col("text", "#FFFFFF"), "stroke": col("stroke", "#000000"),
        "stroke_width": int(C.get("stroke_width", 5)), "shadow": float(C.get("shadow", 0.55)),
        "box": col("box_color", P.color("accent")), "box_w": int(C.get("box_width", 6)),
        "box_fill": col("box_fill", "#000000A6"), "box_r": int(C.get("box_radius", 14)),
        "box_pad": C.get("box_pad", [16, 6]),
        "y": float(C.get("y_vertical" if vertical else "y", 0.70 if vertical else 0.82)),
        "max_w": float(C.get("max_width_vertical" if vertical else "max_width", 0.86 if vertical else 0.78)),
        "band_y": int(C.get("band_y_vertical", 520)),
        "spring": C.get("spring", P.get("style.springs_default", "snappy")),
    }


class Renderer:
    """Draws one caption strip per frame. A frame is a pure function of t."""

    def __init__(self, caps, S, W, H):
        self.S, self.W = S, W
        self.font = ImageFont.truetype(S["font"], S["size"], index=S["font_index"])
        asc, desc = self.font.getmetrics()
        self.lh = int((asc + desc) * 1.12)
        self.pad = S["box_pad"][1] + S["box_w"] + 30           # room for the spring rise and the box
        self.SH = 2 * self.lh + 2 * self.pad + 40
        self.SH += self.SH % 2
        self.y0 = int(round(S["y"] * H - self.SH / 2))
        self.y0 -= self.y0 % 2
        self.space = self.font.getlength(" ")
        self.blank = bytes(W * self.SH * 4)
        self.layout = [self._layout(c) for c in caps]
        self.caps = caps
        self.sp = S["spring"]
        self.st = settle(self.sp)
        self.sf = settle("smooth")
        self.su = settle("ui")

    def _word_img(self, txt, keyword):
        S, f = self.S, self.font
        sw = S["stroke_width"]
        l, t, r, b = f.getbbox(txt, stroke_width=sw)
        px, py = (S["box_pad"][0] + S["box_w"], S["box_pad"][1] + S["box_w"]) if keyword else (0, 0)
        m = 14
        w, h = int(r - l) + 2 * (px + m), self.lh + 2 * (py + m)
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ox, oy = px + m - l, py + m + (self.lh - (f.getmetrics()[0] + f.getmetrics()[1])) // 2
        if keyword:
            box = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            ImageDraw.Draw(box).rounded_rectangle((m, m, w - m - 1, h - m - 1), radius=S["box_r"],
                                                  fill=S["box_fill"], outline=S["box"], width=S["box_w"])
            img.alpha_composite(box)
        if S["shadow"] > 0:
            sh = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            ImageDraw.Draw(sh).text((ox, oy + 4), txt, font=f, fill=(0, 0, 0, int(255 * S["shadow"])),
                                    stroke_width=sw + 2, stroke_fill=(0, 0, 0, int(255 * S["shadow"])))
            img.alpha_composite(sh.filter(ImageFilter.GaussianBlur(5)))
        ImageDraw.Draw(img).text((ox, oy), txt, font=f, fill=S["text"], stroke_width=sw, stroke_fill=S["stroke"])
        return img, px + m

    def _layout(self, c):
        S = self.S
        txts = [w["w"].rstrip(".,;:") or w["w"] for w in c["words"]]   # no trailing . , on screen (.srt keeps them)
        txts = [t.upper() if S["upper"] else t for t in txts]
        imgs = [self._word_img(t, i == c["key"]) for i, t in enumerate(txts)]
        kx = S["box_pad"][0] + S["box_w"] + 2          # the keyword box gets its own room on both sides
        ext = [kx if i == c["key"] else 0 for i in range(len(txts))]
        widths = [self.font.getlength(t) + 2 * ext[i] for i, t in enumerate(txts)]
        maxw = S["max_w"] * self.W
        total = sum(widths) + self.space * (len(txts) - 1)
        lines = [list(range(len(txts)))]
        if total > maxw and len(txts) > 1:      # two balanced lines
            best = None
            for k in range(1, len(txts)):
                a = sum(widths[:k]) + self.space * (k - 1)
                b = sum(widths[k:]) + self.space * (len(txts) - k - 1)
                if best is None or max(a, b) < best[0]:
                    best = (max(a, b), k)
            k = best[1]
            lines = [list(range(k)), list(range(k, len(txts)))]
        cy = self.SH / 2 - self.lh * len(lines) / 2
        place = {}
        for li, idx in enumerate(lines):
            lw = sum(widths[i] for i in idx) + self.space * (len(idx) - 1)
            x = (self.W - lw) / 2
            for i in idx:
                img, inset = imgs[i]
                place[i] = (img, x + ext[i] - inset, cy + li * self.lh - (img.size[1] - self.lh) / 2)
                x += widths[i] + self.space
        return [place[i] for i in range(len(txts))]

    def frame(self, t, ci):
        """(bytes, static) for caption ci at time t."""
        c = self.caps[ci]
        out_start = c["end"] - self.sf if c.get("_fade_out") else c["end"]
        static = True
        im = None
        for i, (img, x, y) in enumerate(self.layout[ci]):
            ws = max(c["start"], c["words"][i]["s"] - LEAD)
            if t < ws:
                static = False
                continue
            dt = t - ws
            # readable within ~0.2 s, never overshoots; a caption that replaces another starts its first word
            # SWAP_HEAD s into the fade, so the swap is never a blank frame
            a = clamp01(spring_at(t, 0, 1, ws - (SWAP_HEAD if i == 0 and c.get("_swap_in") else 0), "ui"))
            if t >= out_start:
                a *= 1 - clamp01(spring_at(t, 0, 1, out_start, "smooth"))
                static = False
            if dt < max(self.st, self.su):
                static = False
            if a <= 0.004:
                continue
            dy = spring_at(t, 26, 0, ws, self.sp)
            sc = spring_at(t, 0.86, 1.0, ws, self.sp)
            if im is None:
                im = Image.new("RGBA", (self.W, self.SH), (0, 0, 0, 0))
            w = img
            if abs(sc - 1) > 0.002:
                nw, nh = max(1, int(round(img.size[0] * sc))), max(1, int(round(img.size[1] * sc)))
                w = img.resize((nw, nh), Image.BILINEAR)
            if a < 0.996:
                w = w.copy()
                w.putalpha(w.split()[3].point(lambda p, a=a: int(p * a)))
            px = x + (img.size[0] - w.size[0]) / 2
            py = y + dy + (img.size[1] - w.size[1]) * 0.75     # grow from the baseline, not the middle
            im.alpha_composite(w, (int(round(px)), int(round(py))))
        if im is None:
            return self.blank, static
        return im.tobytes(), static


def plan_exits(caps, sf, fps):
    """With room before the next caption it fades out on "smooth"; back to back, it is replaced the frame the next
    caption's first word springs in (a fade there would overlap two captions in one place)."""
    for i, c in enumerate(caps):
        gap_after = (caps[i + 1]["start"] - c["end"]) if i + 1 < len(caps) else 9.0
        room = c["end"] - c["last"]
        c["_fade_out"] = room + gap_after >= sf * 0.6
        if i + 1 < len(caps):
            caps[i + 1]["_swap_in"] = not c["_fade_out"]
        if c["_fade_out"] and room < sf * 0.6:   # use some of the gap so the fade starts after the last word
            c["end"] = round(min(c["last"] + sf * 0.6, c["end"] + gap_after), 3)


def find_vertical_shots(video, t0, t1, fps):
    """Shots in a 16:9 file that are really a portrait clip pillarboxed on a blurred fill (a phone clip in a
    16:9 edit). Per frame at 320x180: detail in the centre 9:16 strip and none over the sides (blurred, and no
    burned-in text: one sharp line in any 12-row band keeps the band). Shots are split at hard cuts; a shot fills
    the frame when 95% of its frames pass. Low-detail shots between two such stretches fill too when their sides
    are blurred and text-free (GAP_SOFT).
    Returns [[start, end, crop_width_px], ...]: source seconds and the clip's width in source pixels (the crop
    is that wide, 9:16, centred)."""
    w, h = 320, 180
    W, H = probe(video)[:2]
    cw = int(round(h * 9 / 16))                 # centre strip, 101 px
    c0 = (w - cw) // 2
    p = subprocess.Popen([FF, "-nostdin", "-v", "error", "-ss", f"{t0:.3f}", "-i", video, "-t", f"{t1 - t0:.3f}",
                          "-vf", f"scale={w}:{h},format=gray", "-f", "rawvideo", "-"],
                         stdout=subprocess.PIPE, stdin=subprocess.DEVNULL)
    portrait, blurred, spans, diffs, cuts, prev, n = [], [], [], [], [0], None, 0
    while True:
        buf = p.stdout.read(w * h)
        if len(buf) < w * h:
            break
        f = np.frombuffer(buf, np.uint8).reshape(h, w).astype(np.float32)
        g2 = np.abs(np.diff(f[6:h - 6], axis=1))
        mid = g2[:, c0 + 6:c0 + cw - 6].mean()
        # side detail per 12-row band (8-column peaks): one line of burned-in text over the blur keeps the band
        bands = g2[:g2.shape[0] // 12 * 12].reshape(-1, 12, w - 1).mean(axis=1)
        sides = np.concatenate([bands[:, 2:c0 - 8], bands[:, c0 + cw + 8:w - 3]], axis=1)
        k = np.ones(8) / 8
        side_peak = max(np.convolve(r, k, "valid").max() for r in sides)
        side_mean = max(bands[:, 2:c0 - 8].mean(axis=1).max(), bands[:, c0 + cw + 8:w - 3].mean(axis=1).max())
        blurred.append(side_peak < 10.0)        # blur peaks <= ~4, a line of text 50+ (measured on a phone vlog)
        ok = mid > 2.0 and side_mean < 0.45 * mid and side_peak < 10.0
        portrait.append(ok)
        span = 0
        if ok:            # the clip's width: from the centre out while some row still has an edge in the column
            sharp = np.percentile(g2, 90, axis=0) > 4.0
            x0 = x1 = w // 2
            while x0 > 0 and sharp[max(x0 - 6, 0):x0].any():
                x0 -= 1
            while x1 < w - 2 and sharp[x1:x1 + 6].any():
                x1 += 1
            span = x1 - x0
        spans.append(span)
        dif = float(np.abs(f - prev).mean()) if prev is not None else 0.0
        diffs.append(dif)
        if dif > 14:                            # a hard cut (whip pans split too; the gap fill rejoins them)
            cuts.append(n)
        prev, n = f, n + 1
    p.wait()
    cuts.append(n)
    segs = []                                   # [start frame, end frame, kind, width]
    for a, b in zip(cuts, cuts[1:]):
        cwid = 0
        kind = "full" if b - a >= int(fps * 0.5) and sum(portrait[a:b]) >= 0.95 * (b - a) else \
            "soft" if sum(blurred[a:b]) >= 0.98 * (b - a) else "band"
        segs.append([a, b, kind, cwid])
    # a low-detail stretch with blurred, text-free sides between two phone-clip stretches (a close-up, a plain
    # wall) is the same phone clip: fill it too, so the layout doesn't flip band -> full -> band
    for i, sg in enumerate(segs):
        if sg[2] != "soft":
            continue
        j0 = i
        while j0 > 0 and segs[j0 - 1][2] == "soft":
            j0 -= 1
        j1 = i
        while j1 + 1 < len(segs) and segs[j1 + 1][2] == "soft":
            j1 += 1
        if (j0 > 0 and j1 + 1 < len(segs) and segs[j0 - 1][2] == "full" and segs[j1 + 1][2] in ("full", "fill")
                and (segs[j1][1] - segs[j0][0]) / fps <= GAP_SOFT):
            for sgx in segs[j0:j1 + 1]:
                sgx[2], sgx[3] = "fill", max(segs[j0 - 1][3], segs[j1 + 1][3])
    shots = []
    for a, b, kind, cwid in segs:
        if kind not in ("full", "fill"):
            continue
        if shots and t0 + a / fps - shots[-1][1] < GAP_FILL:
            shots[-1][1] = round(t0 + b / fps, 3)
            shots[-1][3].extend(x for x in spans[a:b] if x)
        else:
            shots.append([round(t0 + a / fps, 3), round(t0 + b / fps, 3), 0, [x for x in spans[a:b] if x]])
    full_w = int(round(H * 9 / 16 / 2) * 2)

    # the layout may only change on a hard cut or inside a fast pan (frame change > 25), never on a still or slow
    # frame. An edge that is not on one moves out to the nearest real cut within 3 s when everything in
    # between has clean blurred sides, else in to the nearest real cut inside the stretch.
    def real_cut(i):                            # a hard cut, or a fast pan (frame change > 25), which hides it
        return i <= 0 or i >= n or diffs[i] > 25
    snapped = []
    for x, y, _, sp in shots:
        a, b = int(round((x - t0) * fps)), int(round((y - t0) * fps))
        if not real_cut(a):
            out_a = next((i for i in range(a - 1, max(a - int(3 * fps), 0) - 1, -1) if real_cut(i)), None)
            if out_a is not None and all(blurred[out_a:a]):
                a = out_a
            else:
                a = next((i for i in range(a + 1, b) if real_cut(i)), b)
        if not real_cut(b):
            out_b = next((i for i in range(b + 1, min(b + int(3 * fps), n) + 1) if real_cut(i)), None)
            if out_b is not None and all(blurred[b:out_b]):
                b = out_b
            else:
                b = next((i for i in range(b - 1, a, -1) if real_cut(i)), a)
        if (b - a) / fps >= 1.0:
            snapped.append([round(t0 + a / fps, 3), round(t0 + b / fps, 3), sp])
    out = []
    for x, y, sp in snapped:
        # one crop per stretch (no zoom jumps inside it): the median clip width, cut just inside its edge
        cwid = int(round(sorted(sp)[len(sp) // 2] / w * W / 8)) * 8 - 8 if sp else full_w
        out.append([x, y, min(full_w, max(cwid, 320))])
    return out


def base_filter(aspect, W, H, S, full=None, t0=0.0):
    """16:9: the source as is. 9:16 from 16:9: the frame as a band over a blurred copy; shots listed in `full`
    (portrait clips that were pillarboxed in the 16:9) are cropped to their centre 9:16 strip and fill the frame."""
    if aspect == "16:9":
        return f"[1:v]setsar=1,format=yuv420p[base]", W, H
    VW, VH, BH = 1080, 1920, int(round(1080 * H / W / 2) * 2)
    by = S["band_y"]
    full_w = int(round(H * 9 / 16 / 2) * 2)
    groups = {}
    for sh in (full or []):
        groups.setdefault(int(sh[2]) if len(sh) > 2 and sh[2] else full_w, []).append(sh)
    f = (f"[1:v]setsar=1,split={2 + max(1, len(groups))}" + "".join(f"[s{k}]" for k in range(2 + max(1, len(groups))))
         + ";[s0]null[a];[s1]null[b];"
         f"[a]scale={VW}:{VH}:force_original_aspect_ratio=increase,crop={VW}:{VH},"
         f"scale={VW // 4}:{VH // 4},boxblur=12:2,scale={VW}:{VH},eq=brightness=-0.10:saturation=0.85[bg];"
         f"[b]scale={VW}:{BH}[fg];[bg][fg]overlay=0:{by}[band];")
    if not groups:
        return f + "[s2]nullsink;[band]format=yuv420p[base]", VW, VH
    last = "band"
    for k, (cw, shots) in enumerate(sorted(groups.items())):
        cw -= cw % 2
        ch = min(H, int(round(cw * 16 / 9 / 2) * 2))
        en = "+".join(f"between(t,{sh[0] - t0:.3f},{sh[1] - t0 - 0.001:.3f})" for sh in shots)
        f += (f"[s{k + 2}]crop={cw}:{ch}:{(W - cw) // 2}:{(H - ch) // 2},scale={VW}:{VH},setsar=1[full{k}];"
              f"[{last}][full{k}]overlay=0:0:enable='{en}'[o{k}];")
        last = f"o{k}"
    return f + f"[{last}]format=yuv420p[base]", VW, VH


def render(video, out_dir, name, caps, S, aspect, fps_n, fps_d, t0, t1, has_audio, make_mov, make_mp4, crf,
           full=None):
    fps = fps_n / fps_d
    W0, H0 = probe(video)[:2]
    fchain, VW, VH = base_filter(aspect, W0, H0, S, full, t0)
    R = Renderer(caps, S, VW, VH)
    plan_exits(caps, R.sf, fps)
    n0 = int(round(t0 * fps))
    n1 = int(round(t1 * fps))
    tag = aspect.replace(":", "x")
    mov = os.path.join(out_dir, f"{name}_captions_{tag}.mov")
    mp4 = os.path.join(out_dir, f"{name}_captioned_{tag}.mp4")
    cmd = [FF, "-nostdin", "-v", "error", "-y",
           "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{VW}x{R.SH}", "-framerate", f"{fps_n}/{fps_d}",
           "-i", "pipe:0"]
    cmd += ["-i", video]
    graph = [fchain, "[0:v]format=rgba,split[c1][c2]"]
    aud, acodec = "1:a:0", ["-c:a", "copy"]          # whole file: the audio is copied untouched
    if t0 > 0:
        # a test range: trim in the graph, frame- and sample-exact (no input-side seek: on files with an edit
        # list it can put the audio up to ~1 s off). The trimmed audio is re-encoded.
        graph[0] = graph[0].replace("[1:v]", "[src]", 1)
        graph.insert(0, f"[1:v]trim=start={t0:.6f},setpts=PTS-STARTPTS[src]")
        if has_audio:
            graph.insert(1, f"[1:a]atrim=start={t0:.6f},asetpts=PTS-STARTPTS[aud]")
            aud, acodec = "[aud]", ["-c:a", "aac", "-b:a", "256k"]
    maps = []
    if make_mov:
        graph.append(f"[c1]pad={VW}:{VH}:0:{R.y0}:color=black@0,format=yuva444p10le[lay]")
        maps += ["-map", "[lay]", "-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le",
                 "-vendor", "apl0", "-alpha_bits", "8", "-frames:v", str(n1 - n0), mov]
    else:
        graph.append("[c1]nullsink")
    if make_mp4:
        graph.append(f"[base][c2]overlay=0:{R.y0}:eof_action=pass:format=auto,format=yuv420p[v]")
        maps += ["-map", "[v]"] + (["-map", aud] + acodec if has_audio else []) + \
                ["-c:v", "libx264", "-preset", "medium", "-crf", str(crf), "-pix_fmt", "yuv420p",
                 "-profile:v", "high", "-movflags", "+faststart", "-frames:v", str(n1 - n0)]
        if t1 is not None:
            maps += ["-t", f"{(n1 - n0) / fps:.3f}"]
        maps += [mp4]
    else:
        graph.append("[base][c2]overlay=0:0[v];[v]nullsink")
    cmd += ["-filter_complex", ";".join(graph)] + maps
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    ci, cache, t_start = 0, (None, None), time.time()
    try:
        for n in range(n0, n1):
            t = n / fps
            while ci < len(caps) and caps[ci]["end"] <= t:
                ci += 1
            if ci < len(caps) and caps[ci]["start"] <= t:
                if cache[0] == ci:
                    buf = cache[1]
                else:
                    buf, static = R.frame(t, ci)
                    cache = (ci, buf) if static else (None, None)
            else:
                buf = R.blank
            p.stdin.write(buf)
            if (n - n0) % 900 == 0:
                el = time.time() - t_start
                sys.stdout.write(f"\r  {aspect}: {(n - n0) / fps:7.1f} / {(n1 - n0) / fps:.1f} s "
                                 f"({(n - n0) / max(el, 1e-6):.0f} fps)")
                sys.stdout.flush()
        p.stdin.close()
    except BrokenPipeError:
        pass
    err = p.stderr.read().decode(errors="replace")
    if p.wait() != 0:
        sys.stderr.write(err[-3000:])
        raise SystemExit("ffmpeg failed")
    print(f"\r  {aspect}: done in {time.time() - t_start:.0f} s" + " " * 30)
    return (mov if make_mov else None), (mp4 if make_mp4 else None), R


# ---- main ----------------------------------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("video")
    ap.add_argument("--out", required=True, help="output folder")
    prof.add_arg(ap)
    ap.add_argument("--aspect", choices=["16:9", "9:16"], default="16:9")
    ap.add_argument("--words-file", help="use this words.json (edited) instead of transcribing")
    ap.add_argument("--model", default="small.en", help="faster-whisper model (local; default small.en)")
    ap.add_argument("--prompt", default=None, help="names and places to steer spelling (default: profile)")
    ap.add_argument("--min-prob", type=float, default=MIN_PROB, help="drop words below this probability")
    ap.add_argument("--start", type=float, default=0.0, help="render from S seconds (a test range)")
    ap.add_argument("--end", type=float, default=None, help="render to S seconds")
    ap.add_argument("--name", help="output base name (default: the video's name)")
    ap.add_argument("--words-only", action="store_true", help="transcribe + group + .srt, no render")
    ap.add_argument("--no-mov", action="store_true", help="skip the alpha caption layer")
    ap.add_argument("--no-mp4", action="store_true", help="skip the burned-in MP4")
    ap.add_argument("--crf", type=int, default=18)
    ap.add_argument("--vertical-fill", choices=["auto", "band", "crop"], default="auto",
                    help="9:16 only. auto: shots that are portrait clips pillarboxed in the 16:9 fill the frame, "
                         "the rest sit as a band over a blurred copy (shots in <name>.fill.json, editable, reused "
                         "on re-runs); band: always the band; crop: always the center 9:16 crop")
    a = ap.parse_args(argv)

    P = prof.load(a.profile)
    os.makedirs(a.out, exist_ok=True)
    name = a.name or os.path.splitext(os.path.basename(a.video))[0].replace(" ", "_")
    W, H, fn, fd, dur, has_audio = probe(a.video)
    t0 = max(0.0, a.start)
    t1 = min(dur, a.end) if a.end else dur

    if a.words_file:
        with open(a.words_file) as f:
            wd = json.load(f)
        print(f"words: {len(wd['words'])} from {a.words_file}")
    else:
        prompt = a.prompt if a.prompt is not None else P.get("transcribe.context", "")
        print(f"transcribing locally with faster-whisper {a.model} ...")
        wd = transcribe(a.video, a.out, a.model, prompt, a.min_prob,
                        t0 if t0 > 0 else None, t1 if a.end else None)
        wp = os.path.join(a.out, f"{name}.words.json")
        write_words(wp, wd)
        print(f"words: {len(wd['words'])} kept, {len(wd['dropped'])} dropped -> {wp}")

    words = sorted((w for w in wd["words"] if w.get("w", "").strip() and t0 <= w["s"] < t1), key=lambda w: w["s"])
    for w in words:
        w["e"] = max(w["e"], w["s"] + 0.05)
    caps = group(words)
    viol = time_captions(caps, t1)
    cj = os.path.join(a.out, f"{name}.captions.json")
    with open(cj, "w") as f:
        json.dump({"rules": {"max_words": MAX_WORDS, "max_chars": MAX_CHARS, "min_dur": MIN_DUR, "max_cps": MAX_CPS},
                   "violations": viol,
                   "captions": [{"n": i + 1, "start": c["start"], "end": c["end"], "text": c["text"],
                                 "keyword": c["words"][c["key"]]["w"] if c["key"] is not None else None}
                                for i, c in enumerate(caps)]}, f, indent=1)
    srt = os.path.join(a.out, f"{name}.srt")
    write_srt(srt, caps, offset=t0)
    nk = sum(c["key"] is not None for c in caps)
    print(f"captions: {len(caps)} ({nk} with a keyword), rule breaks: {len(viol)} -> {srt}")
    for v in viol[:12]:
        print(f"  #{v['i']} {v['dur']:.2f} s {v['cps']:.0f} cps  {v['text']}")
    if a.words_only:
        return 0
    S = style(P, a.aspect == "9:16")
    full = None
    if a.aspect == "9:16" and W * 9 < H * 16 - 1:
        a.vertical_fill = "band"                  # source is not wider than 16:9: nothing to detect
    if a.aspect == "9:16" and a.vertical_fill == "crop":
        full = [[t0, t1, 0]]
    elif a.aspect == "9:16" and a.vertical_fill == "auto":
        fp = os.path.join(a.out, f"{name}.fill.json")
        if os.path.exists(fp):
            full = json.load(open(fp))["full_frame_shots"]
            print(f"9:16 full-frame shots: {len(full)} from {fp}")
        else:
            print("finding portrait clips for the 9:16 ...")
            full = find_vertical_shots(a.video, t0, t1, fn / fd)
            with open(fp, "w") as f:
                json.dump({"note": "9:16: these [start, end, width] source seconds are cropped to a centred 9:16 "
                                   "box <width> px wide (the phone clip) and fill the frame; everything else is the 16:9 band over a blur. Edit and "
                                   "re-run to change.", "full_frame_shots": full}, f, indent=1)
            print(f"9:16 full-frame shots: {len(full)} ({sum(f[1] - f[0] for f in full):.0f} s) -> {fp}")
        full = [[max(f[0], t0), min(f[1], t1)] + f[2:] for f in full if f[1] > t0 and f[0] < t1]
    mov, mp4, R = render(a.video, a.out, name, caps, S, a.aspect, fn, fd, t0, t1, has_audio,
                         not a.no_mov, not a.no_mp4, a.crf, full)
    for pth in (mov, mp4):
        if pth:
            print(f"wrote {pth} ({os.path.getsize(pth) / 1e6:.0f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
