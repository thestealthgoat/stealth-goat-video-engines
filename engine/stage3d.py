#!/usr/bin/env python3
"""stage3d — the 3D card engine (three.js, rendered frame by frame in headless Chromium).

stage3d.py <scene> <out_dir> <Name> [options] [--profile NAME]

scenes:
  data    data scenes from --data (JSON sections: bars, cards (count-up score cards), points (point cloud / map));
          the camera never stops (gentle dolly + hand-held drift) and travels section to section
  orbit   glass cards (--cards "A|B|C") orbit a presenter and pass in front of / behind them by depth;
          --matte <name>_matte.json from engine/matte.py gives the plate and the cut-out
  stack   3D stack of real screenshots (--shots PNGs or --url pages, screenshotted with Playwright)
  burst   mesh-gradient ground, title cards (--lines "A|B|C") swapped behind light bursts (cuts printed)
  badge   two badges (--text1, --text2) fly in and clash (the one slam), sparks + shake
  toggle  a settings panel whose toggle switches (--labels "A|B|C") flip on with UI springs
  props   glossy icon props from simple 3D shapes (--icons check,star,heart,bolt,play,plus,pin,chat)
  reveal  brand glow -> phone (first shot on its screen) -> panels -> toast (--toast) -> tagline (--tagline)
  hop     mascot hop world: a mascot hops platform to platform on the word times of --text
          (--words words.json | --chart | --wpm, like hopwords.py; --character art.png, else a placeholder bean)
  fly     UI flythrough over a tilted app screenshot; --focus JSON list of {x,y,w,h,label} (fractions)
  extrude 3D extruded type flythrough: --text "WORD" (glyph outlines of the profile's head font) or --svg mark.svg;
          the camera flies past the letters and lands square on the lockup (the hit)

Every scene uses the same light standard (warm key with real shadows + cool rim + contact shadows) and springs only.
Outputs <Name>_<scene>.mp4 (on the profile ground, or a gradient / mesh); --alpha also writes <Name>_<scene>_Alpha.mov
(ProRes 4444) with a transparent ground (shadows stay in the alpha). orbit writes the composite .mp4 plus
<Name>_orbit_front_Alpha.mov and _back_Alpha.mov for the edit. The hit time (and cuts) print as "qa: --cuts ...".
--spec file.json merges any scene settings (e.g. {"per": 4.0, "light": {"warm": "#FFD0A0"}}).
--frames t1,t2 renders only those stills.
"""
import argparse, base64, csv, json, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import vprofile as prof  # noqa: E402

SCENES = ["data", "orbit", "stack", "burst", "badge", "toggle", "props", "reveal", "hop", "fly", "extrude"]
FONT_ROLES = {"Head": "head", "Body": "body", "BodySB": "body_semibold", "Mono": "mono"}


def _gpos_kern(f, pairs):
    """{(g1, g2): x advance adjustment} for these glyph pairs from the font's GPOS 'kern' feature (PairPos format 1
    glyph pairs and format 2 class pairs, extension lookups included); None when the font has no GPOS kern feature.
    Per lookup the first subtable that covers the pair wins; lookups add up (as a shaper does)."""
    if "GPOS" not in f: return None
    t = f["GPOS"].table
    if not (t.FeatureList and t.LookupList): return None
    idx = sorted({i for fr in t.FeatureList.FeatureRecord if fr.FeatureTag == "kern" for i in fr.Feature.LookupListIndex})
    if not idx: return None
    out = {p: 0 for p in pairs}
    for li in idx:
        lk = t.LookupList.Lookup[li]
        subs = [(st.ExtensionLookupType, st.ExtSubTable) if lk.LookupType == 9 else (lk.LookupType, st) for st in lk.SubTable]
        for g1, g2 in pairs:
            for typ, st in subs:
                if typ != 2 or g1 not in st.Coverage.glyphs: continue
                if st.Format == 1:
                    ps = st.PairSet[st.Coverage.glyphs.index(g1)]
                    rec = next((r for r in ps.PairValueRecord if r.SecondGlyph == g2), None)
                    if rec is None: continue                                   # not this subtable: try the next one
                    v = rec.Value1
                elif st.Format == 2:
                    c1 = st.ClassDef1.classDefs.get(g1, 0) if st.ClassDef1 else 0
                    c2 = st.ClassDef2.classDefs.get(g2, 0) if st.ClassDef2 else 0
                    v = st.Class1Record[c1].Class2Record[c2].Value1
                else: continue
                out[(g1, g2)] += (getattr(v, "XAdvance", 0) or 0) if v is not None else 0
                break
    return out


def _flat_polys(gs, g, dx, upm):
    """glyph g's contours as closed polylines in SVG space (y down), shifted by dx; curves flattened finely"""
    from fontTools.pens.basePen import BasePen
    step = upm / 60.0
    class Flat(BasePen):
        def __init__(s): super().__init__(gs); s.polys, s.cur = [], []
        def _moveTo(s, p): s.cur = [p]
        def _lineTo(s, p): s.cur.append(p)
        def _bez(s, pts):
            p0 = s.cur[-1]; ctrl = [p0] + list(pts)
            ln = sum(((ctrl[i + 1][0] - ctrl[i][0]) ** 2 + (ctrl[i + 1][1] - ctrl[i][1]) ** 2) ** 0.5 for i in range(len(ctrl) - 1))
            n = max(3, min(32, int(ln / step) + 1))
            for j in range(1, n + 1):
                u, q = j / n, ctrl
                while len(q) > 1: q = [((1 - u) * a[0] + u * b[0], (1 - u) * a[1] + u * b[1]) for a, b in zip(q, q[1:])]
                s.cur.append(q[0])
        def _curveToOne(s, p1, p2, p3): s._bez((p1, p2, p3))
        def _qCurveToOne(s, p1, p2): s._bez((p1, p2))
        def _closePath(s):
            if len(s.cur) > 2: s.polys.append(s.cur)
            s.cur = []
        _endPath = _closePath
    pen = Flat(); gs[g].draw(pen)
    return [[(x + dx, -y) for x, y in poly] for poly in pen.polys]


def text_svg(text, font_path):
    """the word as an SVG of real glyph outlines (fontTools: advances + kerning pairs), for the 3D extrusion.
    Baseline at SVG y=0. Kerning from GPOS (else the legacy 'kern' table). Overlapping contours (variable-font
    instances keep them) and touching letters are merged into one outline with pyclipper, so the extrusion has no
    seams across the faces; without pyclipper the raw glyph outlines are used."""
    from fontTools.ttLib import TTFont
    from fontTools.pens.svgPathPen import SVGPathPen
    from fontTools.pens.transformPen import TransformPen
    with open(font_path, "rb") as fh: collection = fh.read(4) == b"ttcf"
    f = TTFont(font_path, fontNumber=0) if collection or font_path.lower().endswith((".ttc", ".otc")) else TTFont(font_path)
    gs = f.getGlyphSet(); cmap = f.getBestCmap(); hm = f["hmtx"]; upm = f["head"].unitsPerEm
    glyphs = [cmap[ord(ch)] for ch in text if ord(ch) in cmap]
    pairs = list(zip(glyphs, glyphs[1:]))
    try: kern = _gpos_kern(f, pairs)
    except Exception as e:                                                     # odd GPOS: set it unkerned, never fail
        print(f"stage3d: GPOS kerning unreadable ({e}); using the legacy kern table if any", file=sys.stderr); kern = None
    if kern is None:
        kern = {}
        if "kern" in f:
            for tb in f["kern"].kernTables: kern.update(getattr(tb, "kernTable", {}))
    x, xs, prev = 0, [], None
    for g in glyphs:
        if prev is not None: x += kern.get((prev, g), 0)
        xs.append(x); x += hm[g][0]; prev = g
    body = None
    try:
        import pyclipper
        polys = [p for g, gx in zip(glyphs, xs) for p in _flat_polys(gs, g, gx, upm)]
        if polys:
            pc = pyclipper.Pyclipper(); pc.AddPaths(pyclipper.scale_to_clipper(polys, 64), pyclipper.PT_SUBJECT, True)
            res = pyclipper.scale_from_clipper(pc.Execute(pyclipper.CT_UNION, pyclipper.PFT_NONZERO, pyclipper.PFT_NONZERO), 64)
            d = "".join("M" + "L".join(f"{px:.2f} {py:.2f}" for px, py in poly) + "Z" for poly in res if len(poly) > 2)
            if d: body = f'<path d="{d}"/>'                                    # one path: holes resolve against their outers
    except ImportError: pass
    except Exception as e: print(f"stage3d: outline merge failed ({e}); using the raw glyph outlines", file=sys.stderr)
    if body is None:
        paths = []
        for g, gx in zip(glyphs, xs):
            pen = SVGPathPen(gs); gs[g].draw(TransformPen(pen, (1, 0, 0, -1, gx, 0)))
            d = pen.getCommands()
            if d: paths.append(f'<path d="{d}"/>')
        body = "".join(paths)
    asc = f["hhea"].ascent; desc = -f["hhea"].descent
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 {-asc} {x} {asc + desc}">{body}</svg>'


def serve():
    import http.server, socketserver, threading
    class Q(http.server.SimpleHTTPRequestHandler):
        def __init__(s, *a, **k): super().__init__(*a, directory=REPO, **k)
        def log_message(s, *a): pass
    srv = socketserver.TCPServer(("127.0.0.1", 0), Q)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def data_url(path, kind):
    ext = os.path.splitext(path)[1].lstrip(".").lower().replace("jpg", "jpeg")
    return f"data:{kind}/{ext};base64," + base64.b64encode(open(path, "rb").read()).decode()


def save(url, path):
    with open(path, "wb") as f:
        f.write(base64.b64decode(url.split(",", 1)[1]))


def look(P):
    have = P.get("brand.fonts", {}) or {}
    cols = P.get("brand.colors", {}) or {}
    colors = {k: P.color(k) for k in cols}
    colors.setdefault("primary", P.color("primary")); colors.setdefault("accent", P.color("accent"))
    colors.setdefault("text", "#ffffff")
    pal = [colors["accent"], colors["text"]] + [v for k, v in colors.items() if k not in ("primary", "accent", "text")][:4] + [colors["primary"]]
    fonts = {fam: data_url(P.font(role if role in have else "body"), "font") for fam, role in FONT_ROLES.items()}
    ex = P.get("explain", {}) or {}
    return {"fonts": fonts, "colors": colors, "palette": pal, "headCaps": bool(ex.get("head_caps")),
            "display": P.get("display_name", P.name)}


def read_data(path):
    """--data: JSON ({"sections": [...]}) or a CSV of label,value rows (one bars section, titled by the file name)."""
    if path.lower().endswith(".csv"):
        clean = lambda v: v.strip().replace(",", "").rstrip("%")
        rows = [r for r in csv.reader(open(path, encoding="utf-8-sig")) if len(r) >= 2 and r[1].strip()]
        if rows and not _num(clean(rows[0][1])): rows = rows[1:]            # a header row
        bad = [r for r in rows if not _num(clean(r[1]))]
        if bad: sys.exit(f"stage3d: --data {path}: not a number in row {bad[0]!r}")
        title = os.path.splitext(os.path.basename(path))[0].replace("_", " ")
        return {"sections": [{"kind": "bars", "title": title, "items": [{"label": r[0].strip(), "value": float(clean(r[1]))} for r in rows]}]}
    d = json.load(open(path, encoding="utf-8"))
    for s in d.get("sections", []):
        for k in ("items", "points"):
            for it in s.get(k, []) or []:
                if "value" in it: it["value"] = float(it["value"])
    return d


def _num(s):
    try: float(s); return True
    except ValueError: return False


def screenshots(urls, size, out_dir):
    """Real Playwright screenshots of pages (http(s) URLs or local .html files)."""
    from playwright.sync_api import sync_playwright
    w, h = (int(v) for v in size.split("x")); paths = []
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(viewport={"width": w, "height": h}, device_scale_factor=2)
        for i, u in enumerate(urls):
            if os.path.exists(u): u = "file://" + os.path.abspath(u)
            pg.goto(u, wait_until="networkidle"); pg.wait_for_timeout(400)
            f = os.path.join(out_dir, f"shot{i}.png"); pg.screenshot(path=f); paths.append(f)
        b.close()
    return paths


def word_times(a):
    """C2 hop timing: reuse hopwords.py (words.json from E1 captions / a lyric chart / a steady pace), aligned to the
    text; each word's start is the mascot's landing."""
    import hopwords as hw
    words = a.text.split()
    if a.words: timed = json.load(open(a.words))["words"]
    elif a.chart: timed = hw.from_chart(a.chart)
    else: timed = None
    out = hw.align(words, timed) if timed else hw.paced(words, a.wpm, 0.9)
    return [w["w"] for w in out], [w["s"] for w in out]


def person_centre(alpha_mov, size):
    """Where the cards orbit: the presenter's head (O2 cut-out, first frame). Centre x = the middle of the cut-out's
    top quarter, centre y a little below the top of the head; returns ([cx, cy] in frame fractions, head width)."""
    import numpy as np
    w, h = size
    raw = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", alpha_mov, "-frames:v", "1", "-vf", f"scale={w}:{h}",
                          "-f", "rawvideo", "-pix_fmt", "rgba", "-"], capture_output=True, check=True).stdout
    a = np.frombuffer(raw, np.uint8).reshape(h, w, 4)[..., 3] > 128
    rows = np.nonzero(a.mean(1) > 0.01)[0]
    if not len(rows): return [0.5, 0.4], 0.2
    top, bot = rows.min(), rows.max()
    band = a[top:top + max(4, (bot - top) // 4)]
    cols = np.nonzero(band.mean(0) > 0.05)[0]
    if not len(cols): return [0.5, (top + 0.2 * (bot - top)) / h], 0.2
    return [float(np.median(cols) / w), float((top + 0.2 * (bot - top)) / h)], float((cols.max() - cols.min()) / w)


def ff(*args):
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", *map(str, args)], check=True, stdin=subprocess.DEVNULL)


def encode_alpha(frames, fps, out):
    ff("-framerate", fps, "-i", os.path.join(frames, "f%05d.png"), "-threads", "4", "-c:v", "prores_ks", "-profile:v", "4444",
       "-pix_fmt", "yuva444p10le", "-alpha_bits", "16", out)


def encode_mp4(frames, fps, out, bg=None, size=None):
    if bg:
        w, h = size
        ff("-f", "lavfi", "-i", f"color=c=0x{bg.lstrip('#')}:s={w}x{h}:r={fps}", "-framerate", fps, "-i", os.path.join(frames, "f%05d.png"),
           "-filter_complex", "[0][1]overlay=shortest=1,format=yuv420p", "-c:v", "libx264", "-crf", "17", "-preset", "slow",
           "-threads", "4", "-movflags", "+faststart", out)
    else:
        ff("-framerate", fps, "-i", os.path.join(frames, "f%05d.png"), "-vf", "format=yuv420p", "-c:v", "libx264", "-crf", "17",
           "-preset", "slow", "-threads", "4", "-movflags", "+faststart", out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("scene", choices=SCENES); ap.add_argument("out"); ap.add_argument("name")
    ap.add_argument("--spec", help="JSON file merged into the scene settings")
    ap.add_argument("--data", help="data: JSON sections or a label,value CSV")
    ap.add_argument("--shots", help="stack / reveal / fly: comma-separated screenshot PNGs")
    ap.add_argument("--url", action="append", help="stack / reveal / fly: page(s) to screenshot (repeat)")
    ap.add_argument("--shot-size", default="1440x900", help="viewport for --url screenshots (phone: 390x844)")
    ap.add_argument("--cards", help="orbit: card labels, '|' between them")
    ap.add_argument("--matte", help="orbit: the <name>.json written by engine/matte.py (plate + _Alpha.mov cut-out)")
    ap.add_argument("--lines", help="burst: title lines, '|' between them")
    ap.add_argument("--labels", help="toggle: switch labels, '|' between them")
    ap.add_argument("--icons", help="props: icon names, comma-separated")
    ap.add_argument("--text1"); ap.add_argument("--text2")
    ap.add_argument("--toast"); ap.add_argument("--tagline"); ap.add_argument("--panels", help="reveal: text panels, '|' between")
    ap.add_argument("--focus", help="fly: JSON file or inline JSON list of {x,y,w,h,label}")
    ap.add_argument("--text", help="hop: the words; extrude: the word to extrude"); ap.add_argument("--words", help="hop: words.json (start times)")
    ap.add_argument("--svg", help="extrude: an SVG mark instead of --text")
    ap.add_argument("--chart", help="hop: lyric chart (see hopwords.py)"); ap.add_argument("--wpm", type=float, default=110)
    ap.add_argument("--character", help="hop: mascot art (PNG with alpha); default a placeholder bean")
    ap.add_argument("--alpha", action="store_true", help="transparent ground: also write _Alpha.mov")
    ap.add_argument("--bg", choices=["gradient", "mesh"], default="gradient")
    ap.add_argument("--fps", type=float, default=30); ap.add_argument("--size", help="WxH (default 1920x1080; orbit: the matte's own size)")
    ap.add_argument("--dur", type=float); ap.add_argument("--frames")
    prof.add_arg(ap)
    a = ap.parse_args(argv)
    P = prof.load(a.profile)
    os.makedirs(a.out, exist_ok=True)
    w, h = (int(v) for v in (a.size or "1920x1080").split("x"))
    if a.scene == "orbit" and a.matte and not a.size:          # the plate's own frame: never stretch a portrait plate
        msz = json.load(open(a.matte)).get("size")
        if msz: w, h = (int(v) for v in msz)
    L = look(P)
    cfg = {"scene": a.scene, "width": w, "height": h, "alpha": a.alpha, "bg": a.bg, "fonts": L["fonts"], "colors": L["colors"],
           "palette": L["palette"], "headCaps": L["headCaps"], "text1": a.text1, "text2": a.text2}
    if a.dur: cfg["dur"] = a.dur
    tmpd = tempfile.mkdtemp()
    shots = [s for s in (a.shots or "").split(",") if s]
    if a.url: shots += screenshots(a.url, a.shot_size, tmpd)
    if shots: cfg["shots"] = [data_url(s, "image") for s in shots]
    if a.data: cfg["data"] = read_data(a.data)
    if a.cards: cfg["cards"] = a.cards.split("|")
    if a.lines: cfg["lines"] = a.lines.split("|")
    if a.labels: cfg["labels"] = a.labels.split("|")
    if a.icons: cfg["icons"] = a.icons.split(",")
    if a.toast: cfg["toast"] = a.toast
    if a.tagline: cfg["tagline"] = a.tagline
    if a.panels: cfg["panels"] = a.panels.split("|")
    if a.focus: cfg["focus"] = json.load(open(a.focus)) if os.path.exists(a.focus) else json.loads(a.focus)
    if a.character: cfg["character"] = data_url(a.character, "image")
    if a.scene == "extrude":
        if not (a.svg or a.text): sys.exit("stage3d: extrude needs --text or --svg")
        cfg["svg"] = open(a.svg, encoding="utf-8").read() if a.svg else text_svg(a.text.upper() if L["headCaps"] else a.text, P.font("head"))
        if not a.svg: cfg["baseline"] = 0                                    # text_svg sets the baseline at SVG y=0
    if a.scene == "hop":
        if not a.text: sys.exit("stage3d: hop needs --text")
        cfg["words"], cfg["times"] = word_times(a)
    if a.spec: cfg.update(json.load(open(a.spec)))
    plate = None
    if a.scene == "orbit":
        if not a.matte: sys.exit("stage3d: orbit needs --matte <name>_matte.json from engine/matte.py")
        mj = json.load(open(a.matte)); base = a.matte[:-5]
        person = base + "_Alpha.mov"
        if not os.path.exists(person): sys.exit(f"stage3d: no cut-out next to the matte json ({person})")
        turn = {"cw": "transpose=1,", "ccw": "transpose=2,", "180": "hflip,vflip,"}.get(mj.get("rotate") or "", "")
        plate = {"video": mj["video"], "t0": mj["t0"], "t1": mj["t1"], "person": person, "turn": turn}
        a.fps = mj.get("fps", a.fps)
        if cfg.get("dur") and abs(cfg["dur"] - (mj["t1"] - mj["t0"])) > 1e-3:
            print(f"stage3d: orbit runs the matte window's length ({mj['t1'] - mj['t0']:.2f} s), not --dur", file=sys.stderr)
        cfg["dur"] = round(mj["t1"] - mj["t0"], 3)
        if "centre" not in cfg:
            cfg["centre"], hw = person_centre(person, (w, h)); cfg.setdefault("rx", min(0.34, max(0.22, 1.6 * hw)))
        cfg["alpha"] = True
    if a.alpha: cfg["alpha"] = True
    from playwright.sync_api import sync_playwright, Error as PWError
    srv = serve(); port = srv.server_address[1]
    with sync_playwright() as p:
        b = p.chromium.launch(args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"])
        pg = b.new_page(viewport={"width": w, "height": h}); pg.set_default_timeout(0)
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(f"http://127.0.0.1:{port}/engine/stage3d.html"); pg.wait_for_function("window.ready === true")
        try:
            info = pg.evaluate("c => setup(c)", cfg)
        except PWError as e:
            b.close(); srv.shutdown(); sys.exit(f"stage3d: {a.scene}: setup failed: {str(e).splitlines()[0]}")
        base = os.path.join(a.out, f"{a.name}_{a.scene}")
        if a.frames:
            for t in (float(v) for v in a.frames.split(",")):
                save(pg.evaluate(f"frameAt({t})"), f"{base}_t{t:.2f}.png")
            b.close(); srv.shutdown(); shutil.rmtree(tmpd, ignore_errors=True)
            if errs: print("page errors:", errs[:3])
            return 0
        n = int(round(info["duration"] * a.fps))
        layers = ["back", "front"] if a.scene == "orbit" else ["all"]
        dirs = {}
        for ly in layers:
            d = os.path.join(tmpd, ly); os.makedirs(d); dirs[ly] = d
        for i in range(n):
            for ly in layers:
                save(pg.evaluate(f"frameAt({i / a.fps}, '{ly}')"), os.path.join(dirs[ly], f"f{i:05d}.png"))
            if i % 60 == 0: print(f"frame {i}/{n}", flush=True)
        b.close()
    srv.shutdown()
    if errs: print("page errors:", errs[:3])
    fps_s = "30000/1001" if abs(a.fps - 30000 / 1001) < 0.01 else ("60000/1001" if abs(a.fps - 60000 / 1001) < 0.01 else f"{a.fps:g}")
    if a.scene == "orbit":
        for ly in layers: encode_alpha(dirs[ly], fps_s, f"{base}_{ly}_Alpha.mov")
        dur = plate["t1"] - plate["t0"]
        lufs, tp = P.get("delivery.loudness_lufs", -14), P.get("delivery.true_peak_db", -2)
        # the plate's sound is cut sample-exactly in a filter (an input-side seek can be ~1 s off on edit-list files),
        # levelled to the profile's loudness, with a faint pink room tone under it (a gated mic is never dead silence)
        has_a = bool(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0",
                                     plate["video"]], capture_output=True, text=True, stdin=subprocess.DEVNULL).stdout.strip())
        src_a = (f"[4:a]atrim=start={plate['t0']:.4f}:duration={dur:.4f},asetpts=PTS-STARTPTS,aresample=48000,"
                 f"aformat=channel_layouts=stereo,loudnorm=I={lufs}:TP={tp - 1}:LRA=11,aresample=48000[va];") if has_a else \
                (f"anullsrc=channel_layout=stereo:sample_rate=48000,atrim=duration={dur:.4f}[va];")   # a silent plate: room tone only
        aud = (src_a +
               f"anoisesrc=color=pink:amplitude=0.008:sample_rate=48000:duration={dur:.4f},aformat=channel_layouts=stereo[n];"
               f"[va][n]amix=inputs=2:duration=first:normalize=0[a]")
        ff("-ss", plate["t0"], "-t", dur, "-i", plate["video"], "-i", f"{base}_back_Alpha.mov", "-i", plate["person"],
           "-i", f"{base}_front_Alpha.mov", "-i", plate["video"], "-filter_complex",
           f"[0:v]{plate['turn']}scale={w}:{h},setsar=1[p];[p][1:v]overlay=shortest=1[a0];[2:v]scale={w}:{h}[c];[a0][c]overlay=shortest=1[b];"
           f"[b][3:v]overlay=shortest=1,format=yuv420p[v];" + aud,
           "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-crf", "17", "-preset", "slow", "-threads", "4",
           "-r", fps_s, "-c:a", "aac", "-b:a", "192k", "-t", f"{dur:.4f}", "-movflags", "+faststart", base + ".mp4")
    elif cfg.get("alpha"):
        encode_alpha(dirs["all"], fps_s, base + "_Alpha.mov")
        encode_mp4(dirs["all"], fps_s, base + ".mp4", bg=P.color("primary"), size=(w, h))
    else:
        encode_mp4(dirs["all"], fps_s, base + ".mp4")
    shutil.rmtree(tmpd, ignore_errors=True)
    msg = f"{a.scene}: {info['duration']} s at {a.fps:g} fps -> {base}.mp4"
    cuts = [c for c in (info.get("cuts") or [])]
    if info.get("hit") is not None: msg += f", hit at {info['hit']:.3f} s"
    if cuts: msg += f", cuts {','.join(f'{c:.3f}' for c in cuts)}"
    if info.get("hit") is not None or cuts:
        msg += f" (qa: --cuts {','.join(f'{c:.3f}' for c in cuts) if cuts else f'{info['hit']:.3f}'})"
    print(msg, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
