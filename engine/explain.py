#!/usr/bin/env python3
"""explain.py - render an explainer from a storyboard.json (E2) with engine/explain.html.

explain.py <storyboard.json> --out <dir> [--name N] [--profile P] [--aspect 16:9|9:16] [--fps 29.97]
           [--frames 1.0,4.2] [--board] [--vo voice.wav] [--music bed.wav] [--music-db -20] [--no-music]

The storyboard (see engine/storyboard.py for the format and the `check` / `pace` / `retime` / `board` commands) holds
the beats: each beat's spoken line (`say`), its keyword (`key`), its time span (t0, t1) and the elements on screen
(`show`), plus staged `changes`. explain.html draws them on one continuous canvas with spring motion.

Captions: with per-word times in the beats (`words`, written by `storyboard.py retime` from a voice-over transcript)
each word lands as it is said; without them the words are paced across the beat by length (on-screen text mode,
until the voice-over is recorded).
Colours: bg / bg2 / panel from the profile's primary_deep / primary, text, dim (text_dim), accent; `signal` (things
moving through the system) defaults to signal gold #F2C14E (the explainer grammar's signal colour) unless the profile
has an `explain.signal`; `hot` (over the line, the answer) is `explain.hot`, else the accent; `key` (the caption
keyword box) is `explain.key`, else the accent. storyboard "colors" may map any role to a profile colour name or a hex.
Profile `explain.font_scale` scales labels and captions (e.g. 1.2 for a condensed face); `explain.head_caps: true`
(a caps-only head face) sets units (dB, ms, Hz, kHz, x1.26) in the body face so they keep their case.
Audio: --vo (your own recording, or a synthetic voice you made, e.g. ElevenLabs) and/or --music (a bed, e.g. from engine/musicbed.py); the stereo mix is
levelled to the profile's delivery.loudness_lufs. --music-db sets the bed against the voice; with no voice-over the
bed is the whole programme and is levelled to the delivery loudness (so --music-db has no effect). Without either the
MP4 is silent.
Outputs: <name>.mp4 (H.264, 1080p at the profile's rate) + <name>.xml (Premiere: one clip a beat, a marker on each), --frames stills, --board: one still per beat (middle of the
beat) tiled into <name>_board.jpg with the beat text, for approval before the final render.
"""
import argparse, base64, functools, http.server, json, os, shutil, subprocess, sys, tempfile, threading

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import vprofile as prof          # noqa: E402

SIGNAL = "#F2C14E"              # the explainer grammar's signal colour (not a brand colour)


def serve():
    h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=HERE)
    h.log_message = lambda *a, **k: None
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), h)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def data_url(path):
    ext = os.path.splitext(path)[1].lstrip(".").lower().replace("jpg", "jpeg")
    kind = "font" if ext in ("ttf", "otf", "woff", "woff2") else "image"
    return f"data:{kind}/{ext};base64," + base64.b64encode(open(path, "rb").read()).decode()


def mix(c1, c2, k):
    a = [int(c1.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)]
    b = [int(c2.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)]
    return "#" + "".join(f"{int(round(x + (y - x) * k)):02X}" for x, y in zip(a, b))


def look(P, sb):
    cols = P.get("brand.colors")
    pick = lambda role, dflt: P.color(role) if role in cols else dflt
    prim = P.color("primary")
    deep = pick("primary_deep", mix(prim, "#000000", 0.45))
    c = {"bg": deep, "bg2": mix(deep, prim, 0.55), "panel": mix(deep, prim, 0.35), "text": pick("text", "#FFFFFF"),
         "dim": pick("text_dim", mix(pick("text", "#FFFFFF"), deep, 0.35)), "accent": P.color("accent"),
         "signal": P.get("explain.signal", SIGNAL), "hot": P.get("explain.hot", P.color("accent")),
         "key": P.get("explain.key", P.color("accent"))}
    for role, v in (sb.get("colors") or {}).items():
        c[role] = v if v.startswith("#") else P.color(v)
    have = P.get("brand.fonts")
    fonts = {"Head": P.font("head"), "Body": P.font("body"),
             "BodySB": P.font("body_semibold" if "body_semibold" in have else "body"),
             "Mono": P.font("mono" if "mono" in have else ("body_semibold" if "body_semibold" in have else "body"))}
    return c, {k: data_url(v) for k, v in fonts.items()}


def caption_words(beat):
    """Per-word times for a beat: from `words` (voice-over) or paced by length across the beat."""
    key = (beat.get("key") or "").lower().strip(".,!?;:")
    if beat.get("words"):
        ws = [dict(w) for w in beat["words"]]
    else:
        toks = (beat.get("say") or "").split()
        if not toks:
            return []
        a, b = beat["t0"] + 0.08, max(beat["t0"] + 0.3, beat["t1"] - 0.35)
        wt = [len(x) + 2 for x in toks]
        tot, acc, ws = sum(wt), 0, []
        for x, k in zip(toks, wt):
            ws.append({"w": x, "s": round(a + (b - a) * acc / tot, 3)}); acc += k
    for w in ws:
        if key and w["w"].lower().strip(".,!?;:\"'") == key:
            w["key"] = True
    return ws


def absolute_times(sb):
    """Beat-relative times -> absolute for the page: pulse "at" -> start, bar item "at", markAt. All pulses of one
    flow id (across beats) go on every keyframe of it, so a lap started in one beat finishes in the next. An element
    listed again in the next beat keeps its earlier times for unchanged bar items and its marker (no replayed rise,
    no blinking marker). "in" is clamped inside its beat. Pulses default to seg 0.5 s, amp 1."""
    pulses, last = {}, {}
    for bi, b in enumerate(sb["beats"]):
        dur = b["t1"] - b["t0"]
        listed = set()
        for e in b.get("show", []):
            listed.add(e["id"])
            prev = last.get(e["id"])
            if e.get("in"):
                e["in"] = round(max(0.0, min(e["in"], dur - 0.2)), 3)
            for pu in e.get("pulses", []):
                pu.setdefault("seg", 0.5); pu.setdefault("amp", 1.0)
                pu["start"] = round(b["t0"] + pu["at"], 4)
                pulses.setdefault(e["id"], []).append(pu)
            items = e.get("items", [])
            pit = (prev or {}).get("items") or []
            for j, it in enumerate(items):
                if "at" not in it:
                    continue
                if j < len(pit) and pit[j].get("label") == it.get("label") and pit[j].get("value") == it.get("value"):
                    it["at"] = pit[j]["at"]                    # same bar as before: keep its time
                else:
                    it["at"] = round(b["t0"] + it["at"], 4)
            if "markAt" in e:
                if prev is not None and prev.get("mark") == e.get("mark") and "markAt" in prev:
                    e["markAt"] = prev["markAt"]
                else:
                    e["markAt"] = round(b["t0"] + e["markAt"], 4)
            last[e["id"]] = e
        for k in list(last):                                  # a gap breaks continuity
            if k not in listed and k not in (b.get("keep") or []):
                del last[k]
    for b in sb["beats"]:
        for e in b.get("show", []):
            if e["id"] in pulses:
                e["pulses"] = pulses[e["id"]]


def main(argv=None):
    ap = argparse.ArgumentParser(description="render an explainer storyboard")
    ap.add_argument("storyboard"); ap.add_argument("--out", required=True); ap.add_argument("--name")
    ap.add_argument("--aspect", default="16:9", choices=["16:9", "9:16"]); ap.add_argument("--fps", type=float)
    ap.add_argument("--frames"); ap.add_argument("--board", action="store_true")
    ap.add_argument("--vo"); ap.add_argument("--music"); ap.add_argument("--music-db", type=float, default=-18.0)
    ap.add_argument("--no-music", action="store_true")
    prof.add_arg(ap)
    a = ap.parse_args(argv)
    P = prof.load(a.profile)
    for k in ("music", "vo"):                     # fail now, not after rendering every frame
        f = getattr(a, k)
        if f and not (k == "music" and a.no_music) and not os.path.isfile(f):
            ap.error(f"--{k} {f}: no such file (for a topic pack, run its make.py first)")
    sb = json.load(open(a.storyboard))
    base_dir = os.path.dirname(os.path.abspath(a.storyboard))
    name = a.name or os.path.splitext(os.path.basename(a.storyboard))[0]
    os.makedirs(a.out, exist_ok=True)
    W, H = (1920, 1080) if a.aspect == "16:9" else (1080, 1920)
    fps = a.fps or float(P.get("delivery.fps", 29.97002997))
    for b in sb["beats"]:
        b["words"] = caption_words(b)
    absolute_times(sb)
    dur = sb.get("duration") or (sb["beats"][-1]["t1"] + 0.6)
    colors, fonts = look(P, sb)
    images = {k: data_url(v if os.path.isabs(v) else os.path.join(base_dir, v)) for k, v in (sb.get("images") or {}).items()}
    data = {k: json.load(open(v if os.path.isabs(v) else os.path.join(base_dir, v))) for k, v in (sb.get("data") or {}).items()}
    cfg = {"width": W, "height": H, "colors": colors, "fonts": fonts, "images": images, "data": data,
           "fontScale": float(P.get("explain.font_scale", 1.0)), "headCaps": bool(P.get("explain.head_caps", False)),
           "board": {"beats": sb["beats"], "duration": dur}}
    from playwright.sync_api import sync_playwright
    srv = serve(); port = srv.server_address[1]
    stills = []
    if a.frames:
        stills = [float(v) for v in a.frames.split(",")]
    if a.board:
        stills = [round((b["t0"] + b["t1"]) / 2 + 0.25, 3) for b in sb["beats"]]
    with sync_playwright() as p:
        br = p.chromium.launch()
        pg = br.new_page(viewport={"width": W, "height": H}); pg.set_default_timeout(0)
        pg.goto(f"http://127.0.0.1:{port}/explain.html"); pg.wait_for_function("window.ready === true")
        info = pg.evaluate("c => setup(c)", cfg)
        grab = lambda t: base64.b64decode(pg.evaluate(f"frameAt({t})").split(",", 1)[1])
        if stills:
            paths = []
            for t in stills:
                path = os.path.join(a.out, f"{name}_t{t:.2f}.png")
                open(path, "wb").write(grab(t)); paths.append(path)
            br.close(); srv.shutdown()
            if a.board:
                make_board(sb, paths, os.path.join(a.out, f"{name}_board.jpg"), P)
            else:
                for path in paths: print("still", path)
            return
        n = int(round(info["duration"] * fps)); tmp = tempfile.mkdtemp(prefix="explain_")
        try:
            for i in range(n):
                open(os.path.join(tmp, f"f{i:05d}.png"), "wb").write(grab(i / fps))
                if i % 60 == 0:
                    sys.stdout.write(f"\r  frame {i}/{n}"); sys.stdout.flush()
        except BaseException:
            shutil.rmtree(tmp, ignore_errors=True)   # an interrupted render leaves no frames behind
            raise
        br.close()
    srv.shutdown()
    out = os.path.join(a.out, f"{name}.mp4")
    try:
        encode(tmp, fps, out, a.vo, None if a.no_music else a.music, a.music_db, info["duration"], P,
               linear=sb.get("audio") == "linear")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)   # the frames are temporary, even when the encode fails
    xml = write_xml(sb, out, name, fps, info["duration"], W, H)
    print(f"\r  wrote {out} ({n} frames, {info['duration']:.2f} s) + {xml}")


def write_xml(sb, mp4, name, fps, dur, W, H):
    """Premiere XML next to the MP4: the render cut into one clip a beat (labelled with its keyword) with a marker on
    each beat, so a beat can be retimed or swapped in the edit without re-rendering the rest."""
    import fcp7xml
    edges = sorted({0.0, dur, *[min(dur, max(0.0, float(b["t0"]))) for b in sb["beats"]]})
    keys = {round(float(b["t0"]), 3): (b.get("key") or b.get("say") or "")[:40] for b in sb["beats"]}
    items = [{"file": "master", "in": t0, "out": t1, "label": keys.get(round(t0, 3), "open")}
             for t0, t1 in zip(edges, edges[1:]) if t1 - t0 > 0.5 / fps]
    E = {"name": name, "fps": fps, "w": W, "h": H,
         "files": {"master": {"path": os.path.abspath(mp4), "dur": dur, "audio_ch": 2}},
         "items": items, "markers": [{"at": float(b["t0"]), "name": (b.get("key") or "beat")[:40]} for b in sb["beats"]]}
    path = os.path.splitext(mp4)[0] + ".xml"
    with open(path, "w") as f:
        f.write(fcp7xml.build(E))
    return path


def measure(inputs, filt, dur, lufs, tp):
    """first loudnorm pass over the same mix: the measured values for a linear second pass"""
    cmd = ["ffmpeg", "-nostdin", "-hide_banner", "-y"] + inputs + ["-filter_complex",
           filt + f",loudnorm=I={lufs}:TP={tp - 1}:LRA=20:print_format=json[a]", "-map", "[a]", "-t", f"{dur:.3f}", "-f", "null", "-"]
    err = subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL).stderr
    j = json.loads(err[err.rindex("{"): err.rindex("}") + 1])
    return j


def encode(frames, fps, out, vo, music, music_db, dur, P, linear=False):
    """linear=True (storyboard "audio": "linear"): measured once, then one gain for the whole programme plus a peak
    limiter, so a before/after demo (compression, EQ) keeps its real dynamics instead of being evened out by loudnorm."""
    cmd = ["ffmpeg", "-nostdin", "-v", "error", "-y", "-framerate", f"{fps}", "-i", os.path.join(frames, "f%05d.png")]
    ins, filt = [], []
    if vo:
        cmd += ["-i", vo]; ins.append(("vo", len(ins) + 1))
    if music:
        cmd += ["-stream_loop", "-1", "-i", music]; ins.append(("mu", len(ins) + 1))
    lufs = P.get("delivery.loudness_lufs", -14); tp = P.get("delivery.true_peak_db", -2)
    if ins:
        parts = []
        for kind, idx in ins:
            if kind == "vo":   # a mono recording goes to both sides; the mix is always stereo
                filt.append(f"[{idx}:a]aresample=48000,aformat=channel_layouts=stereo,apad[vo]"); parts.append("[vo]")
            else:
                filt.append(f"[{idx}:a]aresample=48000,aformat=channel_layouts=stereo,volume={music_db}dB,"
                            f"afade=t=out:st={max(0, dur - 1.2):.2f}:d=1.2[mu]")
                parts.append("[mu]")
        mixer = (f"{''.join(parts)}amix=inputs={len(parts)}:duration=longest:normalize=0," if len(parts) > 1
                 else f"{parts[0]}anull,")
        # loudnorm (one pass) can land a few tenths over its TP target: aim 1 dB under the delivery ceiling
        if linear:
            # pass 1 measures the same mix (a silent stand-in takes input 0, the frames' slot, so indices match)
            audio_in = cmd[cmd.index(os.path.join(frames, "f%05d.png")) + 1:]
            j = measure(["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"] + audio_in,
                        ";".join(filt) + ";" + f"{mixer}atrim=0:{dur:.3f}", dur, lufs, tp)
            # one gain for the whole programme (linear loudnorm would quietly fall back to dynamic mode when the peaks
            # don't allow its gain), then a peak limiter at the true-peak ceiling: the demo keeps its real dynamics
            gain = lufs - float(j["input_i"]); lim = 10 ** ((tp - 1.5) / 20)
            filt.append(f"{mixer}atrim=0:{dur:.3f},volume={gain:.2f}dB,alimiter=limit={lim:.4f}:attack=2:release=60:level=false,aresample=48000[a]")
        else:
            filt.append(f"{mixer}atrim=0:{dur:.3f},loudnorm=I={lufs}:TP={tp - 1}:LRA=11,aresample=48000[a]")
        cmd += ["-filter_complex", ";".join(filt), "-map", "0:v", "-map", "[a]", "-c:a", "aac", "-b:a", "192k"]
    cmd += ["-c:v", "libx264", "-crf", "17", "-preset", "slow", "-pix_fmt", "yuv420p", "-threads", "4",
            "-movflags", "+faststart", "-t", f"{dur:.3f}", out]
    subprocess.run(cmd, check=True, stdin=subprocess.DEVNULL)


def make_board(sb, paths, out, P):
    """Storyboard approval sheet: one still per beat with its number, time, line and visual."""
    from PIL import Image, ImageDraw, ImageFont
    tw, th, cols = 480, 270, 4
    rows = (len(paths) + cols - 1) // cols
    f = ImageFont.truetype(P.font("body"), 18); fb = ImageFont.truetype(P.font("head"), 26)
    sheet = Image.new("RGB", (cols * (tw + 16) + 16, 70 + rows * (th + 120)), (24, 24, 26))
    d = ImageDraw.Draw(sheet)
    d.text((16, 16), f"{sb.get('topic', 'explainer')} - storyboard for approval ({len(paths)} beats, "
                     f"{sb['beats'][-1]['t1']:.1f} s)", font=fb, fill=(240, 240, 240))
    for i, (b, pth) in enumerate(zip(sb["beats"], paths)):
        x, y = 16 + (i % cols) * (tw + 16), 70 + (i // cols) * (th + 120)
        sheet.paste(Image.open(pth).convert("RGB").resize((tw, th)), (x, y))
        d.text((x, y + th + 6), f"{i + 1}  {b['t0']:.1f}-{b['t1']:.1f} s  [{', '.join(e['type'] for e in b.get('show', []))}]",
               font=f, fill=(170, 170, 170))
        words, line, ly = (b.get("say") or "").split(), "", y + th + 30
        for w in words:
            if d.textlength(line + " " + w, font=f) > tw:
                d.text((x, ly), line.strip(), font=f, fill=(235, 235, 235)); ly += 22; line = ""
            line += " " + w
        d.text((x, ly), line.strip(), font=f, fill=(235, 235, 235))
    sheet.save(out, quality=88)
    print("board", out)


if __name__ == "__main__":
    main()
