#!/usr/bin/env python3
"""3D logo renderer.

render3d.py <logo.svg> <out_dir> <name> [--depth 0.03] [--still-only] [--anim swing|spin] [--spin-seconds 4] [--fps 60]
           [--bg 112233 | --bg '#112233'] [--fill 0.78] [--drop-bg] [--profile NAME]

Outputs in <out_dir>:
  <name>_3D_Hero_4K.png    3840x2160, transparent, angled
  <name>_3D_Front_4K.png   3840x2160, transparent, straight on (slight tilt)
  <name>_3D_Swing_Alpha.mov 1920x1080 60fps ProRes 4444 with alpha, seamless loop (vMix / Premiere / Resolve)
  <name>_3D_Swing.mp4       same loop, H.264 on the --bg colour (social / web; default: the profile's primary colour)
                            [--anim spin for a full turn]
  <name>_3D.glb            3D model (Blender, After Effects, web)
--drop-bg leaves out a filled rectangle that covers the whole SVG canvas (an export background); off by default, because
a full-bleed plate can be part of the logo (e.g. a square badge traced by vectorize.py).
Serves render.html from this folder on a local port and drives it in headless Chromium.
"""
import argparse, base64, http.server, os, shutil, socketserver, subprocess, sys, tempfile, threading, math
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
UPLOAD_TO = ['']
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "engine"))
import vprofile as prof  # noqa: E402


def serve():
    class Q(http.server.SimpleHTTPRequestHandler):
        def __init__(s, *a, **k): super().__init__(*a, directory=HERE, **k)
        def log_message(s, *a): pass
        def do_POST(s):
            n = int(s.headers['Content-Length']); data = s.rfile.read(n)
            part = int(s.path.split('part=')[1]) if 'part=' in s.path else 0
            open(UPLOAD_TO[0], 'wb' if part == 0 else 'ab').write(data); s.send_response(200); s.end_headers()
    srv = socketserver.TCPServer(("127.0.0.1", 0), Q)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def ffmpeg_color(v):
    """--bg as an ffmpeg colour: '112233', '#112233' and '0x112233' (6 or 8 hex digits) all give 0x112233;
    anything else (an ffmpeg colour name such as black) is passed through."""
    s = str(v).strip()
    h = s[1:] if s.startswith("#") else (s[2:] if s[:2].lower() == "0x" else s)
    if len(h) in (6, 8) and all(c in "0123456789abcdefABCDEF" for c in h):
        return "0x" + h
    return s


def save(data_url, path):
    with open(path, "wb") as f:
        f.write(base64.b64decode(data_url.split(",", 1)[1]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("svg"); ap.add_argument("out"); ap.add_argument("name")
    ap.add_argument("--depth", type=float, default=0.03)
    ap.add_argument("--fill", type=float, default=0.78)
    ap.add_argument("--still-only", action="store_true")
    ap.add_argument("--spin-seconds", type=float, default=4)
    ap.add_argument("--fps", type=int, default=60)
    ap.add_argument("--bg", help="background hex for the .mp4, 112233 or '#112233' (default: profile primary colour)")
    ap.add_argument("--anim", default="swing", choices=["swing", "spin"], help="swing = seamless +/-25 deg sway (always readable); spin = full turn")
    ap.add_argument("--hero", default="0.10,-0.30", help="rotX,rotY radians for the hero still")
    ap.add_argument("--drop-bg", action="store_true", help="leave out a filled rectangle covering the whole canvas "
                    "(export background); off by default: a full-bleed plate may be part of the logo")
    prof.add_arg(ap)
    a = ap.parse_args()
    if a.bg is None and not a.still_only:          # only the .mp4 uses it; stills-only runs need no profile
        a.bg = prof.load(a.profile).color("primary").lstrip("#")
    os.makedirs(a.out, exist_ok=True)
    svg = open(a.svg, encoding="utf-8").read()
    srv = serve(); port = srv.server_address[1]
    hx, hy = (float(v) for v in a.hero.split(","))
    with sync_playwright() as p:
        b = p.chromium.launch(args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"])
        pg = b.new_page(viewport={"width": 3840, "height": 2160})
        pg.set_default_timeout(0); pg.goto(f"http://127.0.0.1:{port}/render.html"); pg.wait_for_function("window.ready === true")
        info = pg.evaluate("([s,o]) => build(s,o)", [svg, {"depth": a.depth, "width": 3840, "height": 2160, "fill": a.fill, "dropBackground": a.drop_bg}])
        print("paths", info["paths"], flush=True)
        if info.get("dropped"): print("dropped full-canvas background rectangle(s):", info["dropped"], flush=True)
        save(pg.evaluate(f"renderAt({hx},{hy})"), os.path.join(a.out, f"{a.name}_3D_Hero_4K.png")); print("hero", flush=True)
        save(pg.evaluate("renderAt(0.06,0)"), os.path.join(a.out, f"{a.name}_3D_Front_4K.png"))
        UPLOAD_TO[0] = os.path.join(a.out, f"{a.name}_3D.glb")
        print("glb", pg.evaluate("exportGLB()"), flush=True)
        raw = UPLOAD_TO[0]; tmpg = raw + ".raw.glb"; os.replace(raw, tmpg)
        r = subprocess.run([os.path.join(HERE, "node_modules", ".bin", "gltf-transform"), "optimize", tmpg, raw,
                            "--compress", "draco", "--texture-compress", "false", "--simplify", "false"],
                           capture_output=True, text=True, stdin=subprocess.DEVNULL)
        if r.returncode == 0: os.remove(tmpg)
        else: os.replace(tmpg, raw); print("glb optimize failed, kept raw:", r.stderr[-300:])
        if not a.still_only:
            pg.set_viewport_size({"width": 1920, "height": 1080})
            pg.evaluate("([s,o]) => build(s,o)", [svg, {"depth": a.depth, "width": 1920, "height": 1080, "fill": a.fill, "dropBackground": a.drop_bg}])
            tmp = tempfile.mkdtemp()
            n = int(a.spin_seconds * a.fps)
            for i in range(n):
                t = i / n
                if a.anim == "spin":
                    ry = t * 2 * math.pi; rx = 0.08 * math.sin(t * 2 * math.pi)
                else:
                    ry = 0.44 * math.sin(t * 2 * math.pi); rx = 0.07 * math.sin(t * 4 * math.pi + 0.6)
                save(pg.evaluate(f"renderAt({rx},{ry})"), os.path.join(tmp, f"f{i:04d}.png"))
                if i % 60 == 0: print("frame", i, "/", n, flush=True)
            fr = str(a.fps)
            subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-framerate", fr, "-i", os.path.join(tmp, "f%04d.png"),
                            "-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le", "-alpha_bits", "16",
                            os.path.join(a.out, f"{a.name}_3D_{a.anim.title()}_Alpha.mov")], check=True, stdin=subprocess.DEVNULL)
            subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c={ffmpeg_color(a.bg)}:s=1920x1080:r={fr}",
                            "-framerate", fr, "-i", os.path.join(tmp, "f%04d.png"),
                            "-filter_complex", "[0][1]overlay=shortest=1,format=yuv420p",
                            "-c:v", "libx264", "-crf", "16", "-preset", "slow", "-movflags", "+faststart",
                            os.path.join(a.out, f"{a.name}_3D_{a.anim.title()}.mp4")], check=True, stdin=subprocess.DEVNULL)
            shutil.rmtree(tmp)
        b.close()
    srv.shutdown()


if __name__ == "__main__":
    main()
