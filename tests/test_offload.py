#!/usr/bin/env python3
"""engine/offload.py self-test on tiny synthetic 'cards' under tests/out/production/ (never touches /Volumes)."""
import datetime as dt, os, shutil, stat, subprocess, sys, time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OFF = os.path.join(REPO, "engine", "offload.py")
OUT = os.path.join(REPO, "tests", "out", "production", "offload")
ok = True


def expect(label, cond):
    global ok
    print(("PASS " if cond else "FAIL ") + label, flush=True); ok &= bool(cond)


def run(*args):
    r = subprocess.run([sys.executable, OFF, *args, "--no-caffeinate", "--progress", "0"], capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def write(p, data, when=None):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "wb") as f:
        f.write(data)
    if when:
        t = time.mktime(time.strptime(when, "%Y-%m-%d %H:%M"))
        os.utime(p, (t, t))


def snapshot(d):
    out = {}
    for root, _, files in os.walk(d):
        for n in files:
            p = os.path.join(root, n); st = os.stat(p)
            out[os.path.relpath(p, d)] = (st.st_size, st.st_mtime, open(p, "rb").read())
    return out


shutil.rmtree(OUT, ignore_errors=True)
card = os.path.join(OUT, "card", "DCIM")
write(os.path.join(card, "100CANON", "0U0A0001.CR3"), b"a" * 5000, "2026-10-15 19:05")
write(os.path.join(card, "100CANON", "0U0A0002.JPG"), b"b" * 3000, "2026-10-15 23:59")
write(os.path.join(card, "100CANON", "0U0A0003.JPG"), b"c" * 3000, "2026-10-16 01:30")   # late game, after midnight
write(os.path.join(card, "100CANON", "0U0A0004.JPG"), b"d" * 3000, "2026-10-14 12:00")   # the day before
write(os.path.join(card, "100CANON", "._0U0A0001.CR3"), b"x" * 10, "2026-10-15 19:05")   # macOS junk
write(os.path.join(card, "101CANON", "0U0A0005.MP4"), os.urandom(70000), "2026-10-15 20:00")
write(os.path.join(card, "101CANON", "notes.txt"), b"hi", "2026-10-15 20:00")
for root, dirs, files in os.walk(os.path.join(OUT, "card")):          # make the card read-only, like a locked card
    for n in files:
        os.chmod(os.path.join(root, n), stat.S_IRUSR | stat.S_IRGRP)
before = snapshot(os.path.join(OUT, "card"))

# 1. structured copy of a whole card
dst = os.path.join(OUT, "dst1"); log = os.path.join(OUT, "dst1.log")
rc, o = run(card, dst, "--log", log)
expect("full copy exits 0", rc == 0)
expect("keeps folders", os.path.isfile(os.path.join(dst, "101CANON", "0U0A0005.MP4")))
expect("skips ._ files", not os.path.exists(os.path.join(dst, "100CANON", "._0U0A0001.CR3")))
expect("bytes identical", open(os.path.join(dst, "101CANON", "0U0A0005.MP4"), "rb").read()
       == open(os.path.join(card, "101CANON", "0U0A0005.MP4"), "rb").read())
expect("mtime preserved (cp -p)", abs(os.path.getmtime(os.path.join(dst, "100CANON", "0U0A0001.CR3"))
                                      - os.path.getmtime(os.path.join(card, "100CANON", "0U0A0001.CR3"))) < 1)
L = open(log).read()
expect("log has START and ALL_COMPLETE copied 6", "START" in L and "ALL_COMPLETE copied 6 skipped 0 failed 0" in L)
expect("no .part left", not any(n.endswith(".part") for _, _, fs in os.walk(dst) for n in fs))

# 2. resume: run again -> everything skipped
rc, o = run(card, dst, "--log", log)
expect("re-run skips everything", rc == 0 and "ALL_COMPLETE copied 0 skipped 6" in o)

# 3. never overwrite a different file
victim = os.path.join(dst, "100CANON", "0U0A0002.JPG")
os.chmod(victim, 0o644); open(victim, "wb").write(b"DIFFERENT")
rc, o = run(card, dst, "--log", log)
expect("different existing file -> CONFLICT, exit 1", rc == 1 and "CONFLICT 100CANON/0U0A0002.JPG" in o
       and "ALL_INCOMPLETE" in o)
expect("different file left alone", open(victim, "rb").read() == b"DIFFERENT")
rc, o = run(card, dst, "--log", log, "--conflict", "rename")
expect("--conflict rename copies beside it", rc == 0 and os.path.isfile(os.path.join(dst, "100CANON", "0U0A0002_1.JPG")))

# 4. date filter + flat + ext (photo-card style), game window past midnight
ph = os.path.join(OUT, "Photos")
rc, o = run(card, ph, "--flat", "--ext", "CR3,JPG,MP4,MOV", "--since", "2026-10-15 00:00", "--until",
            "2026-10-16 06:00", "--label", "PHOTOS", "--histogram", "--log", os.path.join(OUT, "ph.log"))
got = sorted(os.listdir(ph))
expect("window + ext + flat picks the 4 game files", rc == 0 and [g for g in got if not g.startswith("_")] ==
       ["0U0A0001.CR3", "0U0A0002.JPG", "0U0A0003.JPG", "0U0A0005.MP4"])
expect("PHOTOS_COMPLETE line + histogram", "PHOTOS_COMPLETE copied 4" in o and "2026-10-14 1 files" in o)
ph2 = os.path.join(OUT, "Photos2")
rc, o = run(card, ph2, "--flat", "--date", "2026-10-15", "--log", os.path.join(OUT, "ph2.log"))
expect("--date = that calendar day only", sorted(os.listdir(ph2)) == ["0U0A0001.CR3", "0U0A0002.JPG", "0U0A0005.MP4", "notes.txt"])

# 5. files-from (relative and absolute lines) + md5 verify
lst = os.path.join(OUT, "list.txt")
open(lst, "w").write("100CANON/0U0A0004.JPG\n" + os.path.join(card, "101CANON", "0U0A0005.MP4") + "\n\n")
ff = os.path.join(OUT, "ff")
rc, o = run(card, ff, "--files-from", lst, "--verify", "md5", "--log", os.path.join(OUT, "ff.log"))
expect("--files-from relative + absolute", rc == 0 and os.path.isfile(os.path.join(ff, "100CANON", "0U0A0004.JPG"))
       and os.path.isfile(os.path.join(ff, "101CANON", "0U0A0005.MP4")))

# 6. check-only (verify photos): good, then a corrupted byte with the same size
lst2 = os.path.join(OUT, "list2.txt")
open(lst2, "w").write("\n".join(os.path.join(card, x) for x in ("100CANON/0U0A0001.CR3", "101CANON/0U0A0005.MP4")) + "\n")
lst = lst2
rc, o = run(card, ph, "--flat", "--files-from", lst, "--check-only", "--log", os.path.join(OUT, "chk.log"))
expect("--check-only clean", rc == 0 and "VERIFY 2 files, bad 0" in o)
bad = os.path.join(ph, "0U0A0005.MP4"); os.chmod(bad, 0o644); b = bytearray(open(bad, "rb").read()); b[100] ^= 1; open(bad, "wb").write(b)
rc, o = run(card, ph, "--flat", "--files-from", lst, "--check-only", "--log", os.path.join(OUT, "chk.log"))
expect("--check-only finds a flipped byte", rc == 1 and "CMPBAD" in o)
rc, o = run(card, ph, "--flat", "--files-from", lst, "--verify-existing", "--log", os.path.join(OUT, "chk.log"))
expect("--verify-existing catches it on a copy run", rc == 1 and "existing file differs" in o)

# 7. safety: destination or log inside the source is refused; dry run writes nothing
rc, o = run(card, os.path.join(card, "copy"))
expect("dst inside src refused", rc == 2 and "read-only" in o)
rc, o = run(card, os.path.join(OUT, "dry"), "--dry-run")
expect("dry run writes nothing", rc == 0 and not os.path.exists(os.path.join(OUT, "dry")) and "WOULD_COPY" in o)
expect("source untouched (bytes, sizes, mtimes)", snapshot(os.path.join(OUT, "card")) == before)

# 8. profile card names resolve (cards.<name>); unknown names are taken as paths
sys.path.insert(0, os.path.join(REPO, "engine")); import offload  # noqa: E402
expect("unknown card name stays a path", offload.resolve_src("nosuchcard_xyz", os.path.join(REPO, "profiles", "_template")) == "nosuchcard_xyz")

# 9. help
r = subprocess.run([sys.executable, OFF, "--help"], capture_output=True, text=True)
expect("--help", r.returncode == 0 and "--files-from" in r.stdout)

# 10. a problem that stops the run is in the log too: FATAL <reason> + <LABEL>_INCOMPLETE (exit 2)
fl = os.path.join(OUT, "fatal.log")
rc, o = run(os.path.join(OUT, "NO_CARD"), os.path.join(OUT, "fatal_dst"), "--label", "REC", "--log", fl)
L = open(fl).read() if os.path.isfile(fl) else ""
expect("card not mounted: FATAL source not found + REC_INCOMPLETE FATAL in the log, exit 2, DST not created",
       rc == 2 and "FATAL: source not found" in L and "REC_INCOMPLETE FATAL" in L
       and not os.path.exists(os.path.join(OUT, "fatal_dst")))
rc, o = run(os.path.join(OUT, "NO_CARD"), os.path.join(OUT, "fatal_dst2"))
expect("card not mounted, default log: DST is not created just for the log", rc == 2
       and not os.path.exists(os.path.join(OUT, "fatal_dst2")))
rc, o = run(card, os.path.join(OUT, "fatal_dst3"), "--since", "yesterday", "--label", "PHOTOS", "--log", fl)
L = open(fl).read()
expect("bad --since: FATAL bad date/time + PHOTOS_INCOMPLETE FATAL in the log, exit 2",
       rc == 2 and "FATAL: bad date/time 'yesterday'" in L and "PHOTOS_INCOMPLETE FATAL" in L)
rc, o = run(card, os.path.join(OUT, "fatal_dst4"), "--files-from", os.path.join(OUT, "no_list.txt"), "--log", fl)
L = open(fl).read()
expect("missing --files-from list: FATAL FileNotFoundError + ALL_INCOMPLETE FATAL in the log, exit 2",
       rc == 2 and "FATAL: FileNotFoundError" in L and "ALL_INCOMPLETE FATAL" in L)
rc, o = run(card, os.path.join(card, "copy"), "--log", os.path.join(card, "x.log"))
expect("log inside the source is still never written", rc == 2 and not os.path.exists(os.path.join(card, "x.log")))
expect("source still untouched", snapshot(os.path.join(OUT, "card")) == before)

for root, dirs, files in os.walk(OUT):
    for n in files:
        os.chmod(os.path.join(root, n), 0o644)
print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
