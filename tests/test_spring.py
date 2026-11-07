#!/usr/bin/env python3
"""spring.py / spring.js self-test (no NAS needed; needs node).
  * the new helpers (handheld, shake, camera_at) and the existing ones give the same numbers in Python and JS
  * they are pure functions of t (same call -> same value; seeds reproduce; no hidden state)
  * logo/spring.js is a byte copy of engine/spring.js
Prints PASS/FAIL per case, exits 1 on any FAIL. (Unchanged preset numbers vs the last commit: tests/diff/test_beatspring.py.)
"""
import json, math, os, subprocess, sys
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "engine"))
import spring as S  # noqa: E402

ok = True
def expect(label, cond, detail=""):
    global ok
    print(("PASS " if cond else "FAIL ") + label + (f"  ({detail})" if detail and not cond else "")); ok &= bool(cond)

TS = [i / 29.97 for i in range(-6, 200)] + [0.0, 0.35, 0.42, 1.2, 2.4, 2.4000001, 3.0, 7.5]
CAM = [{"t": 0, "x": 10, "y": -5, "zoom": 1.0},
       {"t": 0.8, "zoom": 1.2, "preset": "smooth"},
       {"t": 1.0, "x": -120, "y": 30, "preset": "snappy"},
       {"t": 2.2, "x": 40, "rot": 3.5, "zeta": 0.5, "omega": 9},
       {"t": 2.5, "zoom": 1.05, "preset": "gentle", "v0": 0.4}]
CAM_SHUFFLED = [CAM[3], CAM[0], CAM[4], CAM[2], CAM[1]]
# explicit nulls (review 2026-11-07): "preset": None must mean the default "smooth" and "v0": None 0 in both languages
CAM_NULL = [{"t": 0, "x": 0}, {"t": 0.5, "x": 100, "preset": None}, {"t": 1.5, "y": 20, "v0": None}]
HH = [(4, 0.5, 0), (6, 0.6, 3), (2.5, 1.7, 12345), (10, 0.25, -7), (3, 0.9, 2 ** 33 + 5)]
SH = [(2.4, 14, 9, 13), (0.0, 12, 8, 14), (1.0, 3.5, 20, 6)]
HASH = [(0, 0), (1, 0), (3, 5), (-7, 2), (12345, 1), (2 ** 31, 3), (2 ** 33 + 5, 4), (-(2 ** 31) - 9, 5)]


def py_values():
    v = {"hash": [S._hash01(s, i) for s, i in HASH]}
    v["handheld"] = [[list(S.handheld(t, a, f, s)) for t in TS] for a, f, s in HH]
    v["shake"] = [[S.shake(t, h, a, d, f) for t in TS] for h, a, d, f in SH]
    cam = [S.camera_at(t, CAM) for t in TS]
    v["camera"] = [[c[k] for k in ("x", "y", "zoom", "rot")] for c in cam]
    v["camera_shuffled"] = [[c[k] for k in ("x", "y", "zoom", "rot")] for c in (S.camera_at(t, CAM_SHUFFLED) for t in TS)]
    v["camera_null"] = [[c[k] for k in ("x", "y", "zoom")] for c in (S.camera_at(t, CAM_NULL) for t in TS)]
    v["ring"] = [[S.ring(t, 0.42, 0.06, 6, 9) for t in TS], [S.ring(t) for t in TS]]
    v["at"] = [[S.spring_at(t, -400, 0, 0.35, p) for t in TS] for p in S.PRESETS]
    v["velocity"] = [[S.velocity(t, 0, 1, 0.2, p) for t in TS] for p in S.PRESETS]
    v["settle"] = [S.settle(p) for p in S.PRESETS]
    return v


JS = r"""
const S = require(process.argv[1]);
const I = JSON.parse(process.argv[2]);
const v = { hash: I.HASH.map(([s, i]) => S._hash01 ? S._hash01(s, i) : null) };
v.handheld = I.HH.map(([a, f, s]) => I.TS.map(t => S.handheld(t, a, f, s)));
v.shake = I.SH.map(([h, a, d, f]) => I.TS.map(t => S.shake(t, h, a, d, f)));
const cam = (keys) => I.TS.map(t => { const c = S.camera_at(t, keys); return ['x', 'y', 'zoom', 'rot'].map(k => c[k]); });
v.camera = cam(I.CAM); v.camera_shuffled = cam(I.CAM_SHUFFLED);
v.camera_null = I.TS.map(t => { const c = S.camera_at(t, I.CAM_NULL); return ['x', 'y', 'zoom'].map(k => c[k]); });
v.cameraAt_alias = S.cameraAt === S.camera_at;
v.ring = [I.TS.map(t => S.ring(t, { start: 0.42, amp: 0.06, freq: 6, decay: 9 })), I.TS.map(t => S.ring(t))];
const P = Object.keys(S.PRESETS);
v.at = P.map(p => I.TS.map(t => S.at(t, { from: -400, to: 0, start: 0.35, preset: p })));
v.velocity = P.map(p => I.TS.map(t => S.velocity(t, { from: 0, to: 1, start: 0.2, preset: p })));
v.settle = P.map(p => S.settle({ preset: p }));
v.presets = P;
v.pure = JSON.stringify(I.TS.map(t => S.handheld(t, 6, 0.6, 3))) === JSON.stringify(I.TS.map(t => S.handheld(t, 6, 0.6, 3)));
console.log(JSON.stringify(v));
"""


def js_values(path):
    # hash01 is internal in JS; expose it for the test by evaluating the file with a shim
    shim = os.path.join(REPO, "tests", "out", "spring_test")
    os.makedirs(shim, exist_ok=True)
    src = open(path).read().replace("const Spring = { PRESETS,", "const Spring = { _hash01: hash01, PRESETS,")
    sp = os.path.join(shim, "spring_shim.js")
    open(sp, "w").write(src)
    inp = dict(TS=TS, HH=HH, SH=SH, CAM=CAM, CAM_SHUFFLED=CAM_SHUFFLED, CAM_NULL=CAM_NULL, HASH=HASH)
    r = subprocess.run(["node", "-e", JS, sp, json.dumps(inp)], capture_output=True, text=True)
    if r.returncode:
        print(r.stderr); return None
    return json.loads(r.stdout)


def maxdiff(a, b):
    if isinstance(a, (list, tuple)):
        if not isinstance(b, (list, tuple)) or len(a) != len(b):
            return math.inf
        return max([maxdiff(x, y) for x, y in zip(a, b)] or [0.0])
    if a is None or b is None:
        return 0.0 if a is b else math.inf
    return abs(a - b) / max(1.0, abs(a))


py = py_values()
js = js_values(os.path.join(REPO, "engine", "spring.js"))
expect("node runs spring.js", js is not None)
if js:
    expect("JS preset order = Python", js["presets"] == list(S.PRESETS))
    expect("hash01 bit-identical in Py and JS (incl. negative / >32-bit seeds)", py["hash"] == js["hash"],
           f"{py['hash']} vs {js['hash']}")
    for k in ("handheld", "shake", "camera", "camera_shuffled", "camera_null", "ring", "at", "velocity", "settle"):
        d = maxdiff(py[k], js[k])
        expect(f"Py == JS: {k} (max rel diff {d:.1e} <= 1e-9)", d <= 1e-9)
    expect("JS cameraAt is an alias of camera_at", js["cameraAt_alias"])
    expect("JS handheld is a pure function of t", js["pure"])

# determinism / purity in Python
expect("handheld: same call, same value", all(S.handheld(t, 6, 0.6, 3) == S.handheld(t, 6, 0.6, 3) for t in TS))
order_a = [S.handheld(t, 6, 0.6, 3) for t in TS]
order_b = [S.handheld(t, 6, 0.6, 3) for t in reversed(TS)][::-1]
expect("handheld: no hidden state (evaluation order does not matter)", order_a == order_b)
expect("handheld: seeds give different paths", S.handheld(1.3, 6, 0.6, 3) != S.handheld(1.3, 6, 0.6, 4))
dense = [S.handheld(i / 240, 5, 0.7, 9) for i in range(240 * 20)]
expect("handheld: |dx|, |dy| <= amp", max(max(abs(x), abs(y)) for x, y in dense) <= 5 + 1e-12)
expect("handheld: x and y differ (2D, not one sine copied)", any(abs(x - y) > 0.5 for x, y in dense))
step = max(math.hypot(dense[i + 1][0] - dense[i][0], dense[i + 1][1] - dense[i][1]) for i in range(len(dense) - 1))
expect("handheld: smooth (no jumps between 240 fps samples)", step < 0.5, f"max step {step:.3f}")
expect("shake: 0 before the hit", all(S.shake(t, 2.4, 14, 9, 13) == 0.0 for t in TS if t < 2.4))
expect("shake: full amp on the hit frame", S.shake(2.4, 2.4, 14, 9, 13) == 14.0)
expect("shake: dies out", abs(S.shake(2.4 + 1.0, 2.4, 14, 9, 13)) < 14 * math.exp(-9) + 1e-12)
expect("shake: defaults", S.shake(0, 0) == 12.0)
c0 = S.camera_at(-1.0, CAM)
expect("camera_at: starts at the first key", (c0["x"], c0["y"], c0["zoom"], c0["rot"]) == (10.0, -5.0, 1.0, 0.0))
c9 = S.camera_at(40.0, CAM)
expect("camera_at: ends on the last targets",
       all(abs(c9[k] - v) < 1e-6 for k, v in (("x", 40), ("y", 30), ("zoom", 1.05), ("rot", 3.5))), str(c9))
jump = max(abs(S.camera_at(k["t"] + 1e-7, CAM)[f] - S.camera_at(k["t"] - 1e-7, CAM)[f]) for k in CAM for f in ("x", "y", "zoom"))
expect("camera_at: no jump at key times", jump < 1e-4, f"{jump}")
expect("camera_at: key order in the list does not matter", py["camera"] == py["camera_shuffled"])
expect("camera_at: no keys = rest pose", S.camera_at(1.0, []) == {"x": 0.0, "y": 0.0, "zoom": 1.0})
mid = S.camera_at(1.1, CAM)
expect("camera_at: overlapping moves blend (zoom still moving while x moves)", 1.0 < mid["zoom"] < 1.2 and mid["x"] < 10)
expect("camera_at: pure (same t, same pose)", S.camera_at(2.31, CAM) == S.camera_at(2.31, CAM))

a = open(os.path.join(REPO, "engine", "spring.js"), "rb").read()
b = open(os.path.join(REPO, "logo", "spring.js"), "rb").read()
expect("logo/spring.js is a byte copy of engine/spring.js", a == b)
r = subprocess.run(["node", "--check", os.path.join(REPO, "engine", "spring.js")], capture_output=True)
expect("node --check engine/spring.js", r.returncode == 0)

print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
