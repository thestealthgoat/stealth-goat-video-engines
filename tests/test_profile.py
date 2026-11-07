#!/usr/bin/env python3
"""Profile loader self-test (no NAS needed): token expansion, path map, errors, `new` + sample card."""
import json, os, shutil, subprocess, sys, tempfile
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "engine"))
import vprofile  # noqa: E402

ok = True
def expect(label, cond):
    global ok
    print(("PASS " if cond else "FAIL ") + label); ok &= bool(cond)

tmp = tempfile.mkdtemp()
real = os.path.join(tmp, "real"); os.makedirs(os.path.join(real, "ORG", "Assets", "Music"))
data = {"name": "t", "brand": {"colors": {"primary": "112233", "accent": "#E04050"},
                                "fonts": {"head": "{repo}/resources/fonts/BebasNeue-Regular.ttf"}},
        "team": {"foot": "WATCH {root}"},
        "paths": {"music": "{assets}/Music", "assets": "{root}/Assets", "root": "/nonexistent-vol/ORG"},
        "path_map": [["/nonexistent-vol", real]]}
pdir = os.path.join(tmp, "t"); os.makedirs(pdir)
json.dump(data, open(os.path.join(pdir, "profile.json"), "w"))
P = vprofile.load(pdir)
expect("tokens resolve in any order", P.path("music") == os.path.join(real, "ORG", "Assets", "Music"))
expect("path map rewrites a missing mount", P.map_path("/nonexistent-vol/ORG/x.mp4") == os.path.join(real, "ORG", "x.mp4"))
expect("path map leaves unrelated paths", P.map_path("/tmp/x") == "/tmp/x")
expect("color adds #", P.color("primary") == "#112233" and P.rgb("accent") == (224, 64, 80))
expect("font resolves {repo}", os.path.isfile(P.font("head")))
expect("text() expands tokens", P.text("team.foot").startswith("WATCH ") and "{" not in P.text("team.foot"))
expect("get default", P.get("nope.x", 7) == 7)
try:
    P.get("nope.x"); expect("missing key raises", False)
except vprofile.ProfileError:
    expect("missing key raises", True)
data["paths"]["loop"] = "{loop}/x"; json.dump(data, open(os.path.join(pdir, "profile.json"), "w"))
try:
    vprofile.load(pdir); expect("self-reference raises", False)
except vprofile.ProfileError:
    expect("self-reference raises", True)
del data["paths"]["loop"]; json.dump(data, open(os.path.join(pdir, "profile.json"), "w"))
old = os.environ.pop("VIDEO_PROFILE", None)
os.environ["VIDEO_PROFILE"] = pdir
expect("VIDEO_PROFILE picks the profile", vprofile.load().name == "t")
if old is None: os.environ.pop("VIDEO_PROFILE")
else: os.environ["VIDEO_PROFILE"] = old
K = vprofile.load(os.path.join(REPO, "profiles", "_template"))
expect("template profile loads", K.color("primary") == "#1A1A1A")
name = "zz_selftest"
try:
    r = subprocess.run([sys.executable, os.path.join(REPO, "engine", "vprofile.py"), "new", name,
                        "--primary", "#224466", "--accent", "#FFAA00", "--sample"], capture_output=True, text=True)
    card = os.path.join(REPO, "profiles", name, "sample_card.png")
    expect("`new` creates a profile and sample card", r.returncode == 0 and os.path.isfile(card))
    expect("new profile loads", vprofile.load(name).color("accent") == "#FFAA00")
finally:
    shutil.rmtree(os.path.join(REPO, "profiles", name), ignore_errors=True)
shutil.rmtree(tmp, ignore_errors=True)
print("\nALL TESTS PASSED" if ok else "\nSOME TESTS FAILED"); sys.exit(0 if ok else 1)
