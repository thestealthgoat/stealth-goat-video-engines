#!/usr/bin/env python3
"""hopwords.py (C1) self-test, no NAS or audio needed: timing sources, alignment, spring kick, two stills."""
import json, os, subprocess, sys, tempfile
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "engine"))
import hopwords as hw  # noqa: E402

ok = True
def expect(label, cond):
    global ok
    print(("PASS " if cond else "FAIL ") + label); ok &= bool(cond)

text = "But the fruit of the Spirit is love, joy, peace".split()
timed = [{"w": w, "s": 1.0 + 0.5 * i, "e": 1.3 + 0.5 * i} for i, w in enumerate("but the fruit of the spirt is love joy peace".split())]
al = hw.align(text, timed)
expect("align keeps the --text spelling", [w["w"] for w in al] == text)
expect("align takes matched times", al[0]["s"] == 1.0 and al[-1]["s"] == timed[-1]["s"])
expect("an unmatched word is placed between its neighbours and marked",
       al[5].get("guessed") and al[4]["s"] < al[5]["s"] < al[6]["s"])
expect("landings strictly increase", all(b["s"] > a["s"] for a, b in zip(al, al[1:])))
tmp = tempfile.mkdtemp()
ch = os.path.join(tmp, "chart.txt")
open(ch, "w").write("# lyric chart\n0:01.0 Love joy\n2.0 peace\n")
c = hw.from_chart(ch)
expect("chart spreads a phrase to the next cue", [w["w"] for w in c] == ["Love", "joy", "peace"] and c[1]["s"] == 1.5)
p = hw.paced("a b, c.".split(), 60, 1.0)
expect("paced: comma and full stop hold longer", p[1]["s"] == 2.0 and abs(p[2]["s"] - 3.25) < 1e-6)
expect("kick is 0 before the hit and comes back to rest",
       hw.kick(0.9, 1.0, 5, "bouncy") == 0.0 and abs(hw.kick(4.0, 1.0, 5, "bouncy")) < 1e-3 and hw.kick(1.05, 1.0, 5, "bouncy") > 0)
out = os.path.join(tmp, "o")
r = subprocess.run([sys.executable, os.path.join(REPO, "engine", "hopwords.py"), "--text", "Love joy peace patience",
                    "--wpm", "90", "--out", out, "--name", "t", "--profile", "demo", "--frames", "0.5,2.0"],
                   capture_output=True, text=True, stdin=subprocess.DEVNULL)
expect("renders stills with the demo profile", r.returncode == 0 and os.path.isfile(os.path.join(out, "t_hop_t2.00.png")))
expect("writes the timing it used", len(json.load(open(os.path.join(out, "t.timing.json")))["words"]) == 4)
print("\nALL TESTS PASSED" if ok else "\nSOME TESTS FAILED")
sys.exit(0 if ok else 1)
