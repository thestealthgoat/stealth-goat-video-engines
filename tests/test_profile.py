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
# ---- fixes 2026-11-07 -------------------------------------------------------------------------------------------
# optional_paths: a machine-only folder (e.g. Dropbox under one person's home) missing here is listed, not a failure
opt = json.loads(json.dumps(data)); opt["name"] = "opt"; opt["paths"].pop("loop", None)
opt["paths"]["dropbox"] = "{home}/zz-no-such-dropbox-folder/apps"
opt["optional_paths"] = ["dropbox"]
odir = os.path.join(tmp, "opt"); os.makedirs(odir)
json.dump(opt, open(os.path.join(odir, "profile.json"), "w"))
O = vprofile.load(odir)
expect("optional path missing here: check() has no problems", O.check() == [])
expect("optional path missing here: check_optional() lists it", len(O.check_optional()) == 1
       and "dropbox" in O.check_optional()[0])
r = subprocess.run([sys.executable, os.path.join(REPO, "engine", "vprofile.py"), "show", odir, "--check"],
                   capture_output=True, text=True, stdin=subprocess.DEVNULL)
expect("show --check: CHECK: OK, exit 0, and the optional path listed as 'optional, missing here'",
       r.returncode == 0 and "CHECK: OK" in r.stdout and "optional, missing here" in r.stdout
       and "zz-no-such-dropbox-folder" in r.stdout)
opt["optional_paths"] = []; json.dump(opt, open(os.path.join(odir, "profile.json"), "w"))
expect("the same path not marked optional is still a problem", any("dropbox" in x for x in vprofile.load(odir).check()))
opt["optional_paths"] = ["dropbx"]; json.dump(opt, open(os.path.join(odir, "profile.json"), "w"))
expect("optional_paths naming a key that isn't in paths is reported",
       any("dropbx" in x and "not a paths key" in x for x in vprofile.load(odir).check()))
# review 2026-11-07: one key written without the list brackets still counts; any other shape is reported
opt["optional_paths"] = "dropbox"; json.dump(opt, open(os.path.join(odir, "profile.json"), "w"))
expect("optional_paths as a bare string (one key) is honoured: check() has no problems",
       vprofile.load(odir).check() == [] and len(vprofile.load(odir).check_optional()) == 1)
opt["optional_paths"] = {"dropbox": True}; json.dump(opt, open(os.path.join(odir, "profile.json"), "w"))
expect("optional_paths that is not a list is reported (not silently ignored)",
       any("should be a list" in x for x in vprofile.load(odir).check()))
# a folder in the current directory with a profile's name must not hide profiles/<name>
cwd = os.getcwd(); os.chdir(tmp); os.makedirs("_template", exist_ok=True)
try:
    expect("bare profile name loads profiles/<name> even when ./<name>/ exists without a profile.json",
           vprofile.load("_template").color("primary") == "#1A1A1A")
finally:
    os.chdir(cwd)
# This file's own profile name (+ this run's process id): this test and the private profile test used to
# share profiles/zz_selftest, so running them back to back or side by side could delete each other's folder.
name = f"zz_selftest_core_{os.getpid()}"
# Stand-in for another self-test run still in progress, under the old shared name: this run must not need that name
# and must not delete it.
other = os.path.join(REPO, "profiles", "zz_selftest")
try:
    os.makedirs(other); made_other = True    # only one run owns the stand-in when two start at once
    open(os.path.join(other, "in_use_by_another_run"), "w").close()
except FileExistsError:
    made_other = False
try:
    r = subprocess.run([sys.executable, os.path.join(REPO, "engine", "vprofile.py"), "new", name,
                        "--primary", "#224466", "--accent", "#FFAA00", "--sample"], capture_output=True, text=True,
                       stdin=subprocess.DEVNULL)
    card = os.path.join(REPO, "profiles", name, "sample_card.png")
    expect("`new` creates a profile and sample card", r.returncode == 0 and os.path.isfile(card))
    expect("new profile loads", vprofile.load(name).color("accent") == "#FFAA00")
finally:
    shutil.rmtree(os.path.join(REPO, "profiles", name), ignore_errors=True)
    # the stand-in goes even when a check above raised (e.g. `new` failed and load() found no profile): left behind,
    # every later run would find the name taken, skip this check and never remove it
    if made_other:
        expect("another self-test run's profile folder (profiles/zz_selftest) is left alone",
               os.path.isfile(os.path.join(other, "in_use_by_another_run")))
        shutil.rmtree(other, ignore_errors=True)
shutil.rmtree(tmp, ignore_errors=True)
print("\nALL TESTS PASSED" if ok else "\nSOME TESTS FAILED"); sys.exit(0 if ok else 1)
