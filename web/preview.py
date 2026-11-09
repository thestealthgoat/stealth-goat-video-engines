#!/usr/bin/env python3
"""web/preview.py - look at a built site: desktop + phone screenshots of every section and a scroll-through video.

preview.py <dist dir> --out DIR [--name N] [--seconds 14]
Writes <name>_desktop.jpg (a tall contact strip of the page at 1440 wide), <name>_phone.jpg (390 wide),
<name>_laptop.jpg (the first screen on a short 1366x657 laptop window, where a tall hero gets cut off first),
<name>_scroll.mp4 (1440x900, the page scrolled top to bottom on a smooth spring, recorded by the browser).
"""
import argparse, functools, http.server, os, shutil, socketserver, subprocess, sys, tempfile, threading


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass


def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument("dist"); ap.add_argument("--out", required=True); ap.add_argument("--name", default="site")
    ap.add_argument("--seconds", type=float, default=14.0)
    a = ap.parse_args(argv); os.makedirs(a.out, exist_ok=True)
    srv = socketserver.ThreadingTCPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=a.dist)); threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}/index.html"
    from playwright.sync_api import sync_playwright
    vid = tempfile.mkdtemp()
    with sync_playwright() as pw:
        br = pw.chromium.launch(args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"])
        for w, h, tag in ((1440, 900, "desktop"), (390, 844, "phone")):
            ctx = br.new_context(viewport={"width": w, "height": h}, device_scale_factor=1, is_mobile=tag == "phone"); pg = ctx.new_page()
            pg.goto(url, wait_until="networkidle"); total = pg.evaluate("document.documentElement.scrollHeight")
            shots = []
            for k in range(0, total, h):                         # scroll through so every reveal / scrub has run
                pg.evaluate(f"window.scrollTo({{top: {k}, behavior: 'instant'}})"); pg.wait_for_timeout(450)
                f = os.path.join(vid, f"{tag}_{k:06d}.png"); pg.screenshot(path=f); shots.append(f)
            from PIL import Image
            ims = [Image.open(f).convert("RGB") for f in shots]; cols = 4 if tag == "desktop" else 6
            tw = 480 if tag == "desktop" else 260; th = int(tw * h / w); rows = (len(ims) + cols - 1) // cols
            sheet = Image.new("RGB", (cols * tw, rows * th), (20, 20, 20))
            for i, im in enumerate(ims): sheet.paste(im.resize((tw, th)), ((i % cols) * tw, (i // cols) * th))
            sheet.save(os.path.join(a.out, f"{a.name}_{tag}.jpg"), quality=86); ctx.close()
        ctx = br.new_context(viewport={"width": 1366, "height": 657}, device_scale_factor=1); pg = ctx.new_page()
        pg.goto(url, wait_until="networkidle"); pg.wait_for_timeout(450); pg.screenshot(path=os.path.join(a.out, f"{a.name}_laptop.jpg"), quality=86, type="jpeg"); ctx.close()
        ctx = br.new_context(viewport={"width": 1440, "height": 900}, record_video_dir=vid, record_video_size={"width": 1440, "height": 900}); pg = ctx.new_page()
        pg.goto(url, wait_until="networkidle"); pg.wait_for_timeout(800)
        # one smooth scroll top to bottom: a critically damped spring on the scroll position, like a hand on a wheel
        pg.evaluate(f"""async () => {{ const S = window.Spring, end = document.documentElement.scrollHeight - innerHeight, T = {a.seconds};
          const t0 = performance.now(); await new Promise((res) => {{ const step = (now) => {{ const t = (now - t0) / 1000;
            const o = {{ zeta: 1, omega: 4.6 / T }}, p = S.clamp01(S.progress(Math.min(t, T), o) / S.progress(T, o)); window.scrollTo({{ top: p * end, behavior: 'instant' }}); if (t < T) requestAnimationFrame(step); else res(); }}; requestAnimationFrame(step); }}); }}""")
        pg.wait_for_timeout(600); path = pg.video.path(); ctx.close(); br.close()
    srv.shutdown()
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", path, "-c:v", "libx264", "-crf", "20", "-preset", "medium", "-pix_fmt", "yuv420p",
                    "-r", "30", "-movflags", "+faststart", os.path.join(a.out, f"{a.name}_scroll.mp4")], check=True)
    shutil.rmtree(vid, ignore_errors=True)
    print(f"preview: {a.out}/{a.name}_desktop.jpg, _phone.jpg, _scroll.mp4")


if __name__ == "__main__":
    sys.exit(main())
