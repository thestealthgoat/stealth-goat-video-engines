#!/usr/bin/env python3
"""Helpers for the action-pack skill: everything engine/flipbook.py does not do itself.

ap_helpers.py bursts <photos dir> <work dir> [--gap 2.0] [--min 5] [--long 1800]
    Read every JPEG's capture time (EXIF DateTimeOriginal + SubSecTimeOriginal; file order when a photo has none),
    group photos taken <= --gap seconds apart, keep groups of --min or more, and write
    <work>/img/<stem>.jpg (upright, long edge --long px) and <work>/bursts.json
    [{"i": 0, "t0": "2026:05:02 14:03:11", "n": 14, "frames": [stems...]}, ...] in capture order.
ap_helpers.py sheet <work dir> [--from 0] [--per 32]
    Contact sheets of the bursts (first / middle / last frame, 4 bursts a row, --per bursts a sheet), each labelled
    with its burst number and frame count: <work>/sheets/bursts_NN.jpg.
ap_helpers.py plan <work dir> <picks.json> [--max 10]
    picks.json: [{"b": 3, "tag": "GAME 1", "opp": "VS ACME", "trim": 0}, ...] in play order (b = burst number,
    tag = the bold line, opp = optional second half of it, trim = frames to drop from the burst's end).
    Writes <work>/plan.json for flipbook.py (<= --max frames a burst, evenly sampled) and <work>/sheets/chosen.jpg
    (every chosen frame, one row a burst).
ap_helpers.py cuts <plan.json> <out.cuts.json> [--fps-photo 12]
    The planned cut times of the render flipbook.py makes from that plan (the title card's flash, title end, every
    photo change, end card), as {"cuts": [...], "holds": "a-b", "bursts": [...], "end_card": t} for qa.py
    --shotlist and audio_check.py --cuts. "holds" is the title card's still stretch (its text zooms for 0.25 s, then
    holds until the first burst), for qa.py --holds.
ap_helpers.py get <out.cuts.json> cuts|holds
    Print one value of that file as a command-line string: "cuts" comma-separated (audio_check.py --cuts, qa.py
    --cuts), "holds" as qa.py --holds wants it.
ap_helpers.py packprofile <profile name or dir> <out dir> [--aspect 2.0]
    Run from the engine folder. flipbook.py draws brand.logo_png 560 px wide above "ACTION" on the title card with no
    height limit, so a logo narrower than about 1.75:1 (width:height) runs into the title text. This copies the
    profile folder to <out dir>, trims the logo to its visible pixels, pads it with transparent sides to --aspect
    (only when it is narrower) as <out dir>/assets/logo_pack.png and points brand.logo_png at it. Pass
    --profile <out dir> to flipbook.py only; keep the real profile for everything else.
ap_helpers.py slam <logo.png> <out dir> [--frames 54]
    A plain end-card slam for flipbook.py --slam when you have no logo-motion PNG sequence: 1920x1080 transparent
    PNGs f0000.png..., the logo drops in from 150% with a settle, then breathes slowly.
"""
import argparse, json, math, os, re, sys
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont, ImageOps

FPS = 30000 / 1001
JPG = re.compile(r"\.(jpe?g)$", re.I)


def capture_time(path):
    try:
        ex = Image.open(path).getexif()
        sub = ex.get_ifd(0x8769)
        s = sub.get(0x9003) or ex.get(0x0132)            # DateTimeOriginal, else DateTime
        if not s:
            return None, None
        t = datetime.strptime(str(s).strip()[:19], "%Y:%m:%d %H:%M:%S").timestamp()
        ss = str(sub.get(0x9291) or "").strip()          # SubSecTimeOriginal
        if ss.isdigit():
            t += int(ss) / 10 ** len(ss)
        return t, str(s).strip()[:19]
    except Exception:
        return None, None


def cmd_bursts(a):
    names = sorted(n for n in os.listdir(a.photos) if JPG.search(n) and not n.startswith("."))
    if not names:
        sys.exit(f"no JPEGs in {a.photos} (export JPEGs first)")
    rows = []
    for k, n in enumerate(names):
        t, label = capture_time(os.path.join(a.photos, n))
        rows.append((t, k, n, label))
    timed = [r for r in rows if r[0] is not None]
    if len(timed) < len(rows):
        print(f"warning: {len(rows) - len(timed)} of {len(rows)} photos have no capture time; "
              "they are left out (rename or re-export them with EXIF to include them)")
    if not timed:
        sys.exit("no capture times found: grouping by time needs EXIF; pick bursts by file name instead")
    timed.sort()
    groups, cur = [], [timed[0]]
    for r in timed[1:]:
        if r[0] - cur[-1][0] <= a.gap:
            cur.append(r)
        else:
            groups.append(cur); cur = [r]
    groups.append(cur)
    keep = [g for g in groups if len(g) >= a.min]
    img = os.path.join(a.work, "img"); os.makedirs(img, exist_ok=True)
    out = []
    for i, g in enumerate(keep):
        stems = []
        for (_, _, n, _) in g:
            stem = os.path.splitext(n)[0]; dst = os.path.join(img, stem + ".jpg")
            if not os.path.exists(dst):
                im = ImageOps.exif_transpose(Image.open(os.path.join(a.photos, n))).convert("RGB")
                im.thumbnail((a.long, a.long), Image.LANCZOS); im.save(dst, quality=92)
            stems.append(stem)
        out.append({"i": i, "t0": g[0][3], "n": len(stems), "frames": stems})
    with open(os.path.join(a.work, "bursts.json"), "w") as f:
        json.dump(out, f, indent=1)
    print(f"{len(timed)} photos, {len(groups)} groups, {len(out)} bursts of {a.min}+ -> {a.work}/bursts.json")


def _font(size):
    for p in ("/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/Library/Fonts/Arial Bold.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def _tile(path, w, h):
    im = Image.open(path).convert("RGB"); im.thumbnail((w, h), Image.LANCZOS)
    c = Image.new("RGB", (w, h), (24, 24, 24)); c.paste(im, ((w - im.width) // 2, (h - im.height) // 2)); return c


def cmd_sheet(a):
    bursts = json.load(open(os.path.join(a.work, "bursts.json")))[a.start:]
    d = os.path.join(a.work, "sheets"); os.makedirs(d, exist_ok=True)
    tw, th, lab = 200, 200, 30
    bw = 3 * tw + 8; cols = 4; f = _font(20)
    for s in range(0, len(bursts), a.per):
        chunk = bursts[s:s + a.per]; rows = math.ceil(len(chunk) / cols)
        sheet = Image.new("RGB", (cols * (bw + 16), rows * (th + lab + 12)), (0, 0, 0)); dr = ImageDraw.Draw(sheet)
        for j, b in enumerate(chunk):
            x, y = (j % cols) * (bw + 16), (j // cols) * (th + lab + 12)
            fr = b["frames"]; pick = [fr[0], fr[len(fr) // 2], fr[-1]]
            for k, n in enumerate(pick):
                sheet.paste(_tile(os.path.join(a.work, "img", n + ".jpg"), tw, th), (x + k * (tw + 4), y + lab))
            dr.text((x + 2, y + 4), f"b{b['i']:02d}  {b['n']} fr  {b['t0'][11:]}", fill=(255, 220, 0), font=f)
        p = os.path.join(d, f"bursts_{s // a.per:02d}.jpg"); sheet.save(p, quality=85); print(p)


def cmd_plan(a):
    bursts = {b["i"]: b for b in json.load(open(os.path.join(a.work, "bursts.json")))}
    picks = json.load(open(a.picks)); plan = []
    for p in picks:
        fr = bursts[p["b"]]["frames"]
        fr = fr[:len(fr) - int(p.get("trim", 0))] if p.get("trim") else fr
        if len(fr) > a.max:
            fr = [fr[round(k * (len(fr) - 1) / (a.max - 1))] for k in range(a.max)]
        e = {"name": f"b{p['b']:02d}", "wk": p.get("tag", ""), "frames": fr}
        if "opp" in p:
            e["opp"] = p["opp"]
        plan.append(e)
    with open(os.path.join(a.work, "plan.json"), "w") as f:
        json.dump(plan, f, indent=1)
    d = os.path.join(a.work, "sheets"); os.makedirs(d, exist_ok=True)
    tw, th, lab = 150, 150, 26; cols = max(len(e["frames"]) for e in plan)
    sheet = Image.new("RGB", (cols * (tw + 4) + 120, len(plan) * (th + 6)), (0, 0, 0)); dr = ImageDraw.Draw(sheet)
    for r, e in enumerate(plan):
        y = r * (th + 6); dr.text((4, y + 4), f"{r + 1:02d} {e['name']}", fill=(255, 220, 0), font=_font(18))
        for k, n in enumerate(e["frames"]):
            sheet.paste(_tile(os.path.join(a.work, "img", n + ".jpg"), tw, th), (120 + k * (tw + 4), y))
    sheet.save(os.path.join(d, "chosen.jpg"), quality=85)
    print(f"{len(plan)} bursts, {sum(len(e['frames']) for e in plan)} frames -> {a.work}/plan.json, {d}/chosen.jpg")


def cmd_cuts(a):
    """Mirror flipbook.py's timeline: 1.0 s title (a 2-frame white flash on frames 0-1, text zoom for 0.25 s, then
    still), then per burst round(n * FPS / photo fps) frames + a 0.30 s hold."""
    plan = json.load(open(a.plan)); per = FPS / a.fps_photo
    fi = int(round(1.0 * FPS)); cuts, starts = [1 / FPS, fi / FPS], []     # title flash ends at frame 1
    holds = f"0.25-{fi / FPS:.3f}"                                        # title text still from 0.25 s
    for b in plan:
        starts.append(fi / FPS); acc = 0.0
        for _ in b["frames"]:
            cuts.append(fi / FPS); nfr = int(round(acc + per) - round(acc)); acc += per; fi += nfr
        fi += int(round(0.30 * FPS))
    cuts.append(fi / FPS)
    out = {"cuts": sorted({round(c, 3) for c in cuts}), "holds": holds, "bursts": [round(s, 3) for s in starts],
           "end_card": round(fi / FPS, 3)}
    with open(a.out, "w") as f:
        json.dump(out, f, indent=1)
    print(f"{len(out['cuts'])} cuts, title hold {holds} s, end card at {out['end_card']} s -> {a.out}")


def cmd_get(a):
    v = json.load(open(a.cutsfile))[a.key]
    print(",".join(str(c) for c in v) if isinstance(v, list) else v)


def cmd_packprofile(a):
    import shutil
    eng = os.path.join(os.environ.get("VIDEO_ENGINE") or os.getcwd(), "engine")
    if not os.path.isfile(os.path.join(eng, "vprofile.py")):
        sys.exit("run this from the engine folder (cd \"$VIDEO_ENGINE\") or set VIDEO_ENGINE")
    sys.path.insert(0, eng)
    import vprofile
    P = vprofile.load(a.profile)
    src = P.asset("brand.logo_png")
    logo = Image.open(src).convert("RGBA"); box = logo.getchannel("A").getbbox()
    if box:
        logo = logo.crop(box)
    w, h = logo.size
    if os.path.abspath(a.out) != os.path.abspath(P.folder):
        shutil.copytree(P.folder, a.out, dirs_exist_ok=True)
    os.makedirs(os.path.join(a.out, "assets"), exist_ok=True)
    if w < a.aspect * h:
        c = Image.new("RGBA", (int(round(a.aspect * h)), h), (0, 0, 0, 0)); c.paste(logo, ((c.width - w) // 2, 0)); logo = c
    logo.save(os.path.join(a.out, "assets", "logo_pack.png"))
    pj = os.path.join(a.out, "profile.json"); data = json.load(open(pj))
    data["brand"]["logo_png"] = "assets/logo_pack.png"
    with open(pj, "w") as f:
        json.dump(data, f, indent=2)
    print(f"logo {w}x{h} -> {logo.width}x{logo.height}; pass --profile {a.out} to flipbook.py")


def cmd_slam(a):
    logo = Image.open(a.logo).convert("RGBA"); W, H = 1920, 1080
    s0 = min(900 / logo.width, 420 / logo.height)
    os.makedirs(a.out, exist_ok=True)
    for i in range(a.frames):
        t = i / FPS
        if t < 0.3:      # drop in from 150%, ease-out
            p = t / 0.3; z = 1.5 - 0.56 * (1 - (1 - p) ** 3)
        elif t < 0.5:    # settle back to 100%
            p = (t - 0.3) / 0.2; z = 0.94 + 0.06 * (1 - (1 - p) ** 2)
        else:            # slow breathe so the hold stays alive
            z = 1.0 + 0.02 * (t - 0.5)
        lg = logo.resize((max(1, int(logo.width * s0 * z)), max(1, int(logo.height * s0 * z))), Image.LANCZOS)
        if t < 0.3:
            lg.putalpha(lg.getchannel("A").point(lambda v, p=t / 0.3: int(v * min(1, p * 2))))
        c = Image.new("RGBA", (W, H), (0, 0, 0, 0)); c.alpha_composite(lg, ((W - lg.width) // 2, (H - lg.height) // 2 - 60))
        c.save(os.path.join(a.out, f"f{i:04d}.png"))
    print(f"{a.frames} frames -> {a.out}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    b = sp.add_parser("bursts"); b.add_argument("photos"); b.add_argument("work")
    b.add_argument("--gap", type=float, default=2.0); b.add_argument("--min", type=int, default=5)
    b.add_argument("--long", type=int, default=1800)
    s = sp.add_parser("sheet"); s.add_argument("work"); s.add_argument("--from", dest="start", type=int, default=0)
    s.add_argument("--per", type=int, default=32)
    p = sp.add_parser("plan"); p.add_argument("work"); p.add_argument("picks"); p.add_argument("--max", type=int, default=10)
    c = sp.add_parser("cuts"); c.add_argument("plan"); c.add_argument("out")
    c.add_argument("--fps-photo", type=float, default=12)
    g = sp.add_parser("get"); g.add_argument("cutsfile"); g.add_argument("key", choices=["cuts", "holds"])
    q = sp.add_parser("packprofile"); q.add_argument("profile"); q.add_argument("out")
    q.add_argument("--aspect", type=float, default=2.0)
    m = sp.add_parser("slam"); m.add_argument("logo"); m.add_argument("out"); m.add_argument("--frames", type=int, default=54)
    a = ap.parse_args()
    {"bursts": cmd_bursts, "sheet": cmd_sheet, "plan": cmd_plan, "cuts": cmd_cuts, "get": cmd_get, "packprofile": cmd_packprofile,
     "slam": cmd_slam}[a.cmd](a)


if __name__ == "__main__":
    main()
