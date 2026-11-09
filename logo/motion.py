#!/usr/bin/env python3
"""Logo motion graphics with a transparent background.

motion.py <logo.svg> <out_dir> <Name> <template> [--text1 "..."] [--text2 "..."] [--text3 "..."] [--sponsor img.png] [--plate img.png]
          [--fps 60] [--size 1920x1080] [--bg 112233 | --bg '#112233'] [--accent "#E04050"] [--depth 0.03] [--frames 0.5,1.2]
          [--profile NAME]

templates: slam (2 s or --dur, lands in --place) · intro (4 s) · outro (6 s end card, text1 + text2) · bug (writes bug_in, bug_loop, bug_out) ·
           stinger (1.2 s, full-frame wipe, cut point printed) · presented (5 s lower third, text1 + --sponsor) ·
           lockup (4.17 s full-frame: camera settles onto a lit sign, text1 small top line, text2 outlined headline,
           text3 spaced subline, measured flicker-on; --plate puts a background still under it, else a drawn sign) ·
           writeon (4.5 s or --dur, signature write-on: a glowing pen traces the logo's outlines, then its fills fade in;
           --write SECONDS pen time, default 48% of the length up to 2.2 s; the fills land as a hit at 0.86 x --write,
           printed as "hit at" for qa --cuts; text1 optional line under it; --place works) ·
           morph (3.6 s: circles float in and morph into each part of the mark; hit printed) ·
           pixelbuild (3.4 s: a dot grid springs out from the center into the logo, glows, resolves; hit printed) ·
           linebuild (7.5 s: outline pieces converge, fills land, then construction grid -> profile page (text1 =
           the name, default the profile's display name) -> pressed into fabric) ·
           echo (1.2 s outline stinger, cut printed) · lightstreak (3.5 s, hit printed) ·
           lightpaint (the SVG's top-level <g> groups are scenes drawn in turn by one light; 2.4 s a scene + 0.8 s, hit printed) ·
           swap (kinetic word swaps: --text1 "___ is next" --text2 "faster|bolder|yours"; 0.9 s a word + 1.5 s) ·
           shatter (3.2 s: the mark shatters and re-forms as --svg2 / --text2; hit printed) ·
           brandgrid (5 s: logo, colors, type, a stat counting up: --text1 label --text2 value)
--finish dark [--mockup laptop]: cinematic finish on any template (opaque output; profile finish.dark settings).
Outputs <Name>_<template>_Alpha.mov (ProRes 4444, alpha) and <Name>_<template>.mp4 (preview on --bg).
--frames t1,t2,... renders only those stills (PNG) for a quick look.
Brand colors (panel/bar color, accent edge, text color) and fonts (head, body, body_semibold) come from the profile;
--bg (preview .mp4 background, with or without the '#') defaults to the profile's primary color, --accent (outro line 2)
to its accent color. Every profile font must load in the page; if one does not, motion.py stops with an error.
"""
import argparse, base64, os, shutil, subprocess, sys, tempfile
from playwright.sync_api import sync_playwright
from playwright.sync_api import Error as PlaywrightError
from render3d import serve, save, ffmpeg_color, HERE

sys.path.insert(0, os.path.join(os.path.dirname(HERE), "engine"))
import vprofile as prof  # noqa: E402

# font family name used in motion.html -> profile font role
FONT_ROLES = {"Head": "head", "Body": "body", "BodySB": "body_semibold", "BodyM": "body_medium"}


# F1 defaults (a neutral near-black stage; a profile's finish.dark block overrides any of them)
FINISH_DEFAULTS = {"bg": "#05070A", "bg2": "#161B22", "bloom": 0.5, "floor": 0.3, "dof": 6, "grain": 0.3, "vignette": 0.55}


def data_url(path, kind):
    ext = os.path.splitext(path)[1].lstrip(".").lower()
    return f"data:{kind}/{ext};base64," + base64.b64encode(open(path, "rb").read()).decode()


def brand(P):
    """Fonts (as data: URLs, so the served page needs no font files) and colours for motion.html, from the profile."""
    cols, have = P.get("brand.colors", {}), P.get("brand.fonts", {})
    return {"fontNames": {fam: os.path.splitext(os.path.basename(P.font(role if role in have else "body")))[0].replace("-", " ")
                          for fam, role in FONT_ROLES.items()},
            "fonts": {fam: data_url(P.font(role if role in have else "body"), "font") for fam, role in FONT_ROLES.items()},
            "colors": {"primary": P.color("primary"), "accent": P.color("accent"),
                       "text": P.color("text") if "text" in cols else "#fff"},
            "display": P.get("display_name", P.name), "callSign": P.get("brand.call_sign", None),
            "lockupTitle": P.get("brand.lockup_title", None), "lockupLine": P.get("brand.lockup_line", None)}


def encode(frames_dir, fps, out_base, bg, size):
    w, h = size
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-framerate", str(fps), "-i", os.path.join(frames_dir, "f%05d.png"), "-threads", "4",
                    "-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le", "-alpha_bits", "16",
                    out_base + "_Alpha.mov"], check=True, stdin=subprocess.DEVNULL)
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c={ffmpeg_color(bg)}:s={w}x{h}:r={fps}",
                    "-framerate", str(fps), "-i", os.path.join(frames_dir, "f%05d.png"),
                    "-filter_complex", "[0][1]overlay=shortest=1,format=yuv420p", "-c:v", "libx264", "-crf", "16",
                    "-preset", "slow", "-threads", "4", "-movflags", "+faststart", out_base + ".mp4"], check=True, stdin=subprocess.DEVNULL)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("svg"); ap.add_argument("out"); ap.add_argument("name"); ap.add_argument("template")
    ap.add_argument("--text1"); ap.add_argument("--text2"); ap.add_argument("--text3", help="lockup: third (small) line")
    ap.add_argument("--svg2", help="shatter: the NEW mark the pieces re-form as (else --text2 in the head font)")
    ap.add_argument("--sponsor"); ap.add_argument("--plate", help="lockup: background still (PNG/JPG) the camera moves over")
    ap.add_argument("--fps", type=float, default=60); ap.add_argument("--size", default="1920x1080")
    ap.add_argument("--bg", help="preview .mp4 background hex, 112233 or '#112233' (default: profile primary)")
    ap.add_argument("--accent", help="outro line 2 color (default: profile accent)"); ap.add_argument("--depth", type=float, default=0.03)
    ap.add_argument("--frames")
    ap.add_argument("--dur", type=float, help="override length (slam)")
    ap.add_argument("--place", help="cx,cy,bw,bh landing box for slam / writeon, frame fractions")
    ap.add_argument("--write", type=float, help="writeon: seconds the pen takes to trace the logo")
    ap.add_argument("--finish", choices=["dark"], help="cinematic finish on any template: dark ground, bloom, reflective "
                    "floor, depth of field, grain, vignette (settings: the profile's finish.dark block)")
    ap.add_argument("--mockup", choices=["laptop"], help="with --finish: the finished frame on a laptop screen")
    ap.add_argument("--png-seq", action="store_true", help="write a transparent PNG sequence instead of encoding")
    prof.add_arg(ap)
    a = ap.parse_args()
    P = prof.load(a.profile)
    if a.bg is None: a.bg = P.color("primary").lstrip("#")
    if a.accent is None: a.accent = P.color("accent")
    look = brand(P)
    finish = None
    if a.finish:
        finish = dict(FINISH_DEFAULTS, **(P.get(f"finish.{a.finish}", {}) or {}))
        for k in ("bg", "bg2"):
            if not str(finish[k]).startswith("#"):
                finish[k] = P.color(finish[k])
        finish["mockup"] = a.mockup
    os.makedirs(a.out, exist_ok=True)
    w, h = (int(v) for v in a.size.split("x"))
    svg = open(a.svg, encoding="utf-8").read()
    sponsor = None
    if a.sponsor:
        ext = os.path.splitext(a.sponsor)[1].lstrip(".").lower().replace("jpg", "jpeg")
        sponsor = f"data:image/{ext};base64," + base64.b64encode(open(a.sponsor, "rb").read()).decode()
    plate = None
    if a.plate:
        ext = os.path.splitext(a.plate)[1].lstrip(".").lower().replace("jpg", "jpeg")
        plate = f"data:image/{ext};base64," + base64.b64encode(open(a.plate, "rb").read()).decode()
    templates = ["bug_in", "bug_loop", "bug_out"] if a.template == "bug" else [a.template]
    srv = serve(); port = srv.server_address[1]
    with sync_playwright() as p:
        b = p.chromium.launch(args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"])
        pg = b.new_page(viewport={"width": w, "height": h}); pg.set_default_timeout(0)
        page_errors = []; pg.on("pageerror", lambda e: page_errors.append(str(e)))
        for tp in templates:
            pg.goto(f"http://127.0.0.1:{port}/motion.html")
            try:
                pg.wait_for_function("window.ready === true", timeout=60000)     # a script error would otherwise hang forever
            except PlaywrightError:
                b.close(); srv.shutdown()
                sys.exit(f"motion.py: motion.html did not load: {page_errors[0] if page_errors else 'timed out'}")
            try:
                info = pg.evaluate("c => setup(c)", {"svg": svg, "template": tp, "width": w, "height": h, "text1": a.text1,
                                                     "text2": a.text2, "text3": a.text3, "sponsor": sponsor, "plate": plate, "fps": a.fps, "accent": a.accent, "depth": a.depth, "dur": a.dur, "write": a.write,
                                                     "fonts": look["fonts"], "fontNames": look["fontNames"], "colors": look["colors"], "display": look["display"], "callSign": look.get("callSign"), "lockupTitle": look.get("lockupTitle"), "lockupLine": look.get("lockupLine"), "finish": finish,
                                                     "svg2": open(a.svg2, encoding="utf-8").read() if a.svg2 else None,
                                                     "place": dict(zip(("cx", "cy", "bw", "bh"), map(float, a.place.split(",")))) if a.place else None})
            except PlaywrightError as e:
                b.close(); srv.shutdown()
                msg = str(e).splitlines()[0] if str(e) else repr(e)
                sys.exit(f"motion.py: {tp}: page setup failed: {msg}")
            base = os.path.join(a.out, f"{a.name}_{tp}")
            if a.frames:
                for t in (float(v) for v in a.frames.split(",")):
                    save(pg.evaluate(f"frameAt({t})"), f"{base}_t{t:.2f}.png")
                continue
            n = int(round(info["duration"] * a.fps)); tmp = tempfile.mkdtemp()
            if a.png_seq: tmp = base + "_seq"; os.makedirs(tmp, exist_ok=True)
            for i in range(n):
                save(pg.evaluate(f"frameAt({i / a.fps})"), os.path.join(tmp, f"f{i:05d}.png"))
            if not a.png_seq: encode(tmp, a.fps, base, a.bg, (w, h)); shutil.rmtree(tmp)
            msg = f"{tp}: {info['duration']} s"
            if info.get("cut") is not None: msg += f", cut at {info['cut']} s (frame {int(info['cut'] * a.fps)})"
            if info.get("hit") is not None:
                msg += (f", hit at {info['hit']:.3f} s (frame {int(round(info['hit'] * a.fps))}; "
                        f"qa: --cuts {info['hit']:.3f})")
            print(msg, flush=True)
        b.close()
    srv.shutdown()


if __name__ == "__main__":
    main()
