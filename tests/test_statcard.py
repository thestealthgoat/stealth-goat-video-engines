#!/usr/bin/env python3
"""statcard.py self-test (no NAS needed; uses profiles/_template and a synthetic cutout).
  * the card loads from a file or inline, rejects fewer than 2 or more than 4 stats
  * count-up numbers never pass their value and land exactly on it; text keeps its final layout (no jitter)
  * frames are a pure function of t (same t -> same pixels), nothing is drawn before the start, the card is gone after
    its exit, and opacity never overshoots (no alpha above the settled card's)
  * the card stays inside the box it is given (also when the text is long and has to shrink)
  * write_mov writes a region-sized PNG .mov and a full-frame ProRes 4444 .mov with alpha
Prints PASS/FAIL per case, exits 1 on any FAIL. Output in tests/out/statcard/.
"""
import json, os, subprocess, sys
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "engine"))
import statcard as SC  # noqa: E402
import vprofile as prof  # noqa: E402
from PIL import Image, ImageChops, ImageDraw  # noqa: E402

ok = True
def expect(label, cond, detail=""):
    global ok
    print(("PASS " if cond else "FAIL ") + label + (f"  ({detail})" if detail and not cond else "")); ok &= bool(cond)

OUT = os.path.join(REPO, "tests", "out", "statcard"); os.makedirs(OUT, exist_ok=True)
P = prof.load(os.path.join(REPO, "profiles", "_template"))
cut = Image.new("RGBA", (300, 400), (0, 0, 0, 0)); d = ImageDraw.Draw(cut)
d.ellipse([90, 20, 210, 150], fill=(200, 160, 130, 255)); d.rectangle([40, 150, 260, 400], fill=(40, 60, 160, 255))
cut.save(os.path.join(OUT, "cutout.png"))
card = {"num": 7, "name": "Test Player", "photo": "cutout.png", "big": "3 TDS · 1,234 YDS",
        "stats": [["CAR", "21"], ["AVG", "6.5"], ["LONG", "54"]]}
json.dump(card, open(os.path.join(OUT, "card.json"), "w"))

c = SC.load_card(os.path.join(OUT, "card.json"), P=P)
expect("load from file: name upper-cased, photo resolved beside the file",
       c["name"] == "TEST PLAYER" and c["photo"] == os.path.join(OUT, "cutout.png"))
c2 = SC.load_card({"type": "stats", "file": "card.json", "big": "OVERRIDE"}, base_dir=OUT, P=P)
expect("inline keys override the file", c2["big"] == "OVERRIDE" and c2["stats"] == c["stats"])
for n in (1, 5):
    try:
        SC.load_card(dict(card, stats=[["A", "1"]] * n), base_dir=OUT); bad = False
    except ValueError:
        bad = True
    expect(f"{n} stats rejected (2-4 only)", bad)

segs = SC.count_segments("3 TDS · 1,234 YDS · 6.5 AVG")
expect("numbers split out (comma and decimal kept whole)", [s for s, n in segs if n] == ["3", "1,234", "6.5"])
vals = [SC.counted("1,234", p / 100) for p in range(-20, 140)]
expect("count-up never passes its value and lands on it",
       all(int(v.replace(",", "")) <= 1234 for v in vals) and vals[-1] == "1,234" and SC.counted("1,234", 1.0) == "1,234")
expect("decimal count keeps its places", SC.counted("6.5", 0.5) == "3.2" or SC.counted("6.5", 0.5) == "3.3")

sc = SC.StatCard(c, P, size=(1920, 1080), start=0.35, exit_at=4.0)
a, b = sc.frame(1.234), sc.frame(1.234)
expect("same t -> same pixels", ImageChops.difference(a, b).getbbox() is None)
expect("nothing drawn before the start", sc.frame(0.2).getchannel("A").getbbox() is None)
expect("gone after the exit", sc.frame(5.5).getchannel("A").getbbox() is None)
settled = sc.full_frame(sc.still_time(), sweep=False)
amax = settled.getchannel("A").getextrema()[1]
peak = max(sc.full_frame(sc.start + i / 30, sweep=False).getchannel("A").getextrema()[1] for i in range(0, 60, 3))
expect("opacity never overshoots the settled card", peak <= amax, f"{peak} > {amax}")
bb = settled.getchannel("A").getbbox(); safe = P.get("layout.safe_px", 90)
expect("default card inside the safe area", bb[0] >= safe and bb[2] <= 1920 - safe and bb[3] <= 1080 - safe, str(bb))

# the right edge of the big line does not move while its numbers count (layout fixed to the final string)
def right_edge(t):
    im = sc.frame(t, sweep=False).crop((0, 0, sc.region[2], sc.L["big_base"] - sc.region[1] + 4))
    return im.getchannel("A").point(lambda v: 255 if v > 200 else 0).getbbox()[2]
edges = {right_edge(sc.times()["big"] + k) for k in (0.5, 0.7, 0.9)}
expect("no layout jitter while counting", len(edges) == 1, str(edges))

long = dict(card, name="A Very Long Player Name For Testing Purposes", big="TWO HUNDRED AND FIFTY-FIVE YARDS RUSHING")
sv = SC.StatCard(SC.load_card(long, base_dir=OUT, P=P), P, size=(1080, 1920), box=(40, 1040, 1560), start=0.0)
bb = sv.full_frame(sv.still_time(), sweep=False).getchannel("A").getbbox()
expect("long text shrinks to fit a vertical box", bb[0] >= 40 and bb[2] <= 1040 and bb[3] <= 1560, str(bb))

m1 = sc.write_mov(os.path.join(OUT, "region.mov"), "60000/1001", 1.0, codec="png")
m2 = sc.write_mov(os.path.join(OUT, "full.mov"), 29.97, 1.0, codec="prores", full=True)
pr = lambda f: subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                               "stream=codec_name,width,height,pix_fmt,nb_frames", "-of", "csv=p=0", f],
                              capture_output=True, text=True).stdout.strip()
r1, r2 = pr(m1), pr(m2)
expect("region .mov: png with alpha, region size, 60 frames",
       r1 == f"png,{sc.region[2]},{sc.region[3]},rgba,60", r1)
expect("full .mov: ProRes 4444 with alpha, 1920x1080, 30 frames",
       r2.startswith("prores,1920,1080,yuva444p") and r2.endswith(",30"), r2)

print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
