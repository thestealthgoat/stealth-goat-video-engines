#!/usr/bin/env python3
"""Self-test for spring.py + motion_check.py. Renders small clips with planted faults, then checks the gate.
Run:  python3 tests/test_motion_gate.py
Needs: python3, numpy, pillow, ffmpeg (prores_ks for the alpha test). Writes into tests/out/."""
import os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
FILES = os.path.join(HERE, "..", "engine")
sys.path.insert(0, FILES)
from spring import spring_at, progress, clamp01, settle  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

OUT = os.path.join(HERE, "out"); os.makedirs(OUT, exist_ok=True)
W, H, FPS, S = 960, 540, 60, 4
CHECK = [sys.executable, os.path.join(FILES, "motion_check.py")]
os.dup2(os.open(os.devnull, os.O_RDONLY), 0)   # every child (ffmpeg, the original scripts) reads /dev/null: no stdin stalls

def draw(t):
    im = Image.new("RGB", (W * S, H * S), (17, 34, 51)); d = ImageDraw.Draw(im)
    x = spring_at(t, frm=-200, to=380, start=0.2, preset="bouncy")
    d.rectangle([x * S, 200 * S, (x + 200) * S, 340 * S], fill=(224, 64, 80))
    y = spring_at(t, frm=600, to=380, start=2.0, preset="slam")
    d.rectangle([600 * S, y * S, 760 * S, (y + 60) * S], fill=(255, 255, 255))
    return im.resize((W, H), Image.LANCZOS)

def render(name, freeze=None, dup_at=None, drift=False):
    d = os.path.join(OUT, name); os.makedirs(d, exist_ok=True)
    for i in range(240):
        t = i / FPS
        if freeze and freeze[0] <= t < freeze[1]: t = freeze[0]
        if dup_at is not None and i == int(dup_at * FPS): t = (i - 1) / FPS
        im = draw(t)
        if drift: ImageDraw.Draw(im).ellipse([20 + i * 0.6, 40, 60 + i * 0.6, 80], fill=(40, 70, 120))
        im.save(os.path.join(d, f"f{i:04d}.png"))
    mp4 = os.path.join(OUT, name + ".mp4")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(FPS), "-i", os.path.join(d, "f%04d.png"),
                    "-c:v", "libx264", "-crf", "18", "-preset", "veryfast", "-pix_fmt", "yuv420p", mp4], check=True)
    return mp4

def alpha():
    d = os.path.join(OUT, "alpha"); os.makedirs(d, exist_ok=True)
    for i in range(180):
        t = i / 60
        a = clamp01(progress(t, preset="smooth")) if t < 2.4 else clamp01(1 - progress(t, start=2.4, preset="smooth"))
        im = Image.new("RGBA", (640, 360), (0, 0, 0, 0))
        ImageDraw.Draw(im).ellipse([220, 80, 420, 280], fill=(255, 25, 54, int(255 * a)))
        im.save(os.path.join(d, f"f{i:04d}.png"))
    mov = os.path.join(OUT, "alpha.mov")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", "60", "-i", os.path.join(d, "f%04d.png"),
                    "-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le", mov], check=True)
    return mov

def gate(path, *args):
    r = subprocess.run(CHECK + [path, *args], capture_output=True, text=True)
    return r.returncode, r.stdout

ok = True
def expect(label, cond):
    global ok
    print(("PASS " if cond else "FAIL ") + label); ok &= cond

expect("spring presets settle as documented", abs(settle("snappy") - 0.36) < 0.02 and abs(settle("ui") - 0.20) < 0.02)
bad, good, al = render("bad", freeze=(1.0, 2.0), dup_at=2.10), render("good", drift=True), alpha()
rc, out = gate(bad, "--holds", "end:1.0")
import re
spans = [(float(a), float(b)) for a, b in re.findall(r"FAIL dead\s+([\d.]+)-([\d.]+)", out)]
expect("planted 1 s freeze is caught", rc == 1 and any(a <= 1.05 and b >= 1.95 for a, b in spans))
expect("planted repeated frame is caught", "stutter" in out)
rc, out = gate(good, "--holds", "end:1.0"); expect("clean clip with drift passes", rc == 0)
rc, out = gate(good, "--holds", "end:1.0", "--strict"); expect("clean clip passes strict mode", rc == 0)
rc, out = gate(al); expect("alpha-only fade: unplanned still fails", rc == 1 and "alpha composited" in out)
rc, out = gate(al, "--holds", "0.6-2.4"); expect("alpha-only fade: planned hold passes", rc == 0)

# repeat cadence: lower-rate material conformed up repeats frames on a regular beat (not stutters); a repeat that
# breaks the beat is still a stutter
def conform(name, src_fps, out_fps, secs=4.0, extra_at=None):
    """Draw a steadily moving scene at src_fps and lay it into out_fps (rates as "num/den" strings) by repeating frames (what a frame-rate
    conform does). extra_at: seconds at which one picture is shown one extra frame (a real hitch)."""
    d = os.path.join(OUT, name); os.makedirs(d, exist_ok=True)
    from fractions import Fraction
    ratio = Fraction(src_fps) / Fraction(out_fps)            # source pictures per output frame (exact)
    n_out = int(secs * Fraction(out_fps))
    srcs = [int(k * ratio) for k in range(n_out)]
    for at in sorted([extra_at] if isinstance(extra_at, (int, float)) else (extra_at or []), reverse=True):
        k = int(at * Fraction(out_fps)); srcs.insert(k, srcs[k])
    cache = {}
    for k, si in enumerate(srcs):
        if si not in cache:
            t = si / float(Fraction(src_fps)); im = Image.new("RGB", (480, 270), (17, 34, 51)); dr = ImageDraw.Draw(im)
            for x in range(-40, 520, 40):   # stripes panning across the whole frame = motion on every picture
                xx = x + (120 * t) % 40; dr.rectangle([xx, 0, xx + 14, 270], fill=(40, 70, 120))
            dr.rectangle([20 + 90 * t, 90, 80 + 90 * t, 170], fill=(224, 64, 80))
            dr.ellipse([300 - 30 * t, 30, 340 - 30 * t, 70], fill=(220, 220, 220)); cache[si] = im
        cache[si].save(os.path.join(d, f"f{k:04d}.png"))
    mp4 = os.path.join(OUT, name + ".mp4")
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-framerate", out_fps, "-i", os.path.join(d, "f%04d.png"),
                    # lossless, so a repeated picture stays an exact repeat (ffmpeg 9's x264 at crf 18 can re-code one
                    # with small noise, which motion_check deliberately does not treat as a repeat)
                    "-c:v", "libx264", "-qp", "0", "-preset", "veryfast", "-pix_fmt", "yuv420p", mp4], check=True,
                   stdin=subprocess.DEVNULL)
    return mp4

def stutters(out):
    return [float(a) for a in re.findall(r"FAIL stutter\s+([\d.]+)-", out)]

c60 = conform("cadence_30in60", "30000/1001", "60000/1001")
rc, out = gate(c60)
expect("29.97 material in a 59.94 file: regular repeats are one cadence note, not stutters",
       rc == 0 and not stutters(out) and "note cadence" in out)
c60x = conform("cadence_30in60_hitch", "30000/1001", "60000/1001", extra_at=2.0)
rc, out = gate(c60x); st = stutters(out)
expect("an extra repeat that breaks the 2-frame cadence is still a stutter (and only that one)",
       rc == 1 and len(st) == 1 and abs(st[0] - 2.0) < 0.1 and "note cadence" in out)
c32 = conform("cadence_24in30", "24000/1001", "30000/1001")
rc, out = gate(c32)
expect("3:2 pulldown (23.976 in 29.97, a repeat every 5th frame) passes with a cadence note",
       rc == 0 and not stutters(out) and "note cadence" in out)
c32x = conform("cadence_24in30_hitch", "24000/1001", "30000/1001", extra_at=2.0)
rc, out = gate(c32x); st = stutters(out)
expect("an extra repeat inside 3:2 pulldown is still a stutter (and only that one)",
       rc == 1 and len(st) == 1 and abs(st[0] - 2.0) < 0.15)
rc, out = gate(c60, "--allow-stutter"); expect("--allow-stutter still skips the repeat check", rc == 0)
# review cases: real hitches must never be absorbed into a "cadence"
hits = [0.5, 0.83, 1.4, 1.62, 2.3, 2.55, 3.1, 3.6]                    # 8 one-off repeats, irregular spacing
cl = conform("hitches_30", "30000/1001", "30000/1001", extra_at=hits)
rc, out = gate(cl); st = stutters(out)
expect("8 irregular one-off repeats in clean 29.97 motion are 8 stutters (no cadence note)",
       rc == 1 and len(st) == 8 and "note cadence" not in out and
       all(any(abs(s - (h + k / 29.97)) < 0.1 for k, h in enumerate(sorted(hits))) for s in st))
c60h = conform("cadence_30in60_3hitches", "30000/1001", "60000/1001", extra_at=[0.9, 2.0, 3.3])
rc, out = gate(c60h); st = stutters(out)
expect("3 extra repeats inside a 2-frame cadence are 3 stutters",
       rc == 1 and len(st) == 3 and "note cadence" in out)
print("\nALL TESTS PASSED" if ok else "\nSOME TESTS FAILED"); sys.exit(0 if ok else 1)
