#!/usr/bin/env python3
"""engine/encode.py self-test with tiny synthetic clips under tests/out/production/ (never touches /Volumes)."""
import json, os, shutil, subprocess, sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENC = os.path.join(REPO, "engine", "encode.py")
OUT = os.path.join(REPO, "tests", "out", "production", "encode")
ok = True


def expect(label, cond, extra=""):
    global ok
    print(("PASS " if cond else "FAIL ") + label + ("" if cond or not extra else f"\n     {extra[-600:]}"), flush=True)
    ok &= bool(cond)


def run(*args, caffeinate=False):
    r = subprocess.run([sys.executable, ENC, *args] + ([] if caffeinate else ["--no-caffeinate"]),
                       capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def ff(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


def probe(path, entries, stream=None):
    cmd = ["ffprobe", "-v", "error"] + (["-select_streams", stream] if stream else []) + \
          ["-show_entries", entries, "-of", "csv=p=0", path]
    return subprocess.run(cmd, capture_output=True, text=True).stdout.strip()


def atoms(path):
    """Top-level MP4 atom names in order."""
    names = []
    with open(path, "rb") as f:
        while True:
            h = f.read(8)
            if len(h) < 8:
                break
            size = int.from_bytes(h[:4], "big"); name = h[4:].decode("latin1")
            if size == 1:
                size = int.from_bytes(f.read(8), "big"); f.seek(size - 16, 1)
            elif size == 0:
                names.append(name); break
            else:
                f.seek(size - 8, 1)
            names.append(name)
    return names


def framemd5(path, sel="v"):
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-map", f"0:{sel}", "-f", "framemd5", "-"],
                       capture_output=True, text=True)
    return [l.split(",")[-1].strip() for l in r.stdout.splitlines() if l and not l.startswith("#")]


shutil.rmtree(OUT, ignore_errors=True); os.makedirs(OUT)
# a synthetic default profile, so the test never depends on this machine's default profile
ENC_PROFILE = os.path.join(OUT, "prof_enc"); os.makedirs(ENC_PROFILE)
json.dump({"name": "enc", "brand": {"colors": {"primary": "#000000", "accent": "#ffffff"}, "fonts": {}}, "paths": {},
           "delivery": {"web": {"vcodec": "h264_videotoolbox", "vcodec_fallback": "libx264",
                                      "fallback_args": ["-preset", "fast"], "profile": "high", "b_v": "12M",
                                      "maxrate": "14M", "bufsize": "24M", "acodec": "copy", "faststart_max_gb": 10}}},
          open(os.path.join(ENC_PROFILE, "profile.json"), "w"))
os.environ["VIDEO_PROFILE"] = ENC_PROFILE
a = os.path.join(OUT, "HyperDeck_0001.mp4"); b = os.path.join(OUT, "HyperDeck_0002.mp4")
for p, sec, f in ((a, 3, 440), (b, 4, 660)):
    ff("-f", "lavfi", "-i", f"testsrc2=size=320x180:rate=60000/1001:duration={sec}", "-f", "lavfi",
       "-i", f"sine=frequency={f}:sample_rate=48000:duration={sec}", "-c:v", "libx264", "-preset", "ultrafast",
       "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-shortest", p)
final = os.path.join(OUT, "03 Final"); enc = os.path.join(final, ".enc"); os.makedirs(enc)
lst = os.path.join(enc, "concat.txt")
open(lst, "w").write(f"ffconcat version 1.0\nfile '{a}'\nfile '{b}'\ninpoint 1.0\n")
master = os.path.join(final, "2026 Week 7 - Test.mp4")

# 1. master from a concat list (inpoint honored), web preset, verify
rc, o = run("master", lst, "-o", master, caffeinate=True)
expect("master exits 0 (caffeinate on)", rc == 0, o)
expect("master written, no .partial left", os.path.isfile(master) and not os.path.exists(master.replace(".mp4", ".partial.mp4")))
expect("preset bitrate on the command line", "-b:v 12M -maxrate 14M -bufsize 24M" in o and "-profile:v high" in o)
expect("audio copied (aac kept)", probe(master, "stream=codec_name", "a:0") == "aac")
expect("verify step ran and passed", "DECODE_OK" in o and "VERIFY_OK" in o and "MISMATCH" not in o, o)
d = float(probe(master, "format=duration"))
expect(f"duration = 3 + (4 - 1) s (got {d:.2f})", abs(d - 6.0) < 0.2)
expect("small file -> +faststart (moov before mdat)", atoms(master).index("moov") < atoms(master).index("mdat"))
expect("log in 03 Final/.enc/encode.log", "=== START master" in open(os.path.join(enc, "encode.log")).read())

# 2. existing output is never replaced without --force; output may not be an input
rc, o = run("master", lst, "-o", master)
expect("existing output refused", rc != 0 and "exists" in o)
rc, o = run("master", a, "-o", a, "--force")
expect("output == input refused", rc != 0 and "also an input" in o)

# 3. --no-faststart (the >10 GB rule's outcome) and the size rule itself
m2 = os.path.join(final, "nofs.mp4")
rc, o = run("master", a, b, "-o", m2, "--no-faststart", "--no-verify")
expect("several inputs -> concat list written under .enc", rc == 0 and os.path.isfile(os.path.join(enc, "nofs_concat.txt")), o)
expect("--no-faststart -> moov after mdat", atoms(m2).index("moov") > atoms(m2).index("mdat"))
sys.path.insert(0, os.path.join(REPO, "engine")); import encode  # noqa: E402


class A: faststart = None


expect("faststart auto: off above faststart_max_gb", encode.want_faststart(A, {"faststart_max_gb": 10}, 12e9) is False
       and encode.want_faststart(A, {"faststart_max_gb": 10}, 2e9) is True)
expect("3 h at 12M lands over 10 GB (so a real game gets no faststart)", 3 * 3600 * (12e6 + 320e3) / 8 > 10e9)

# 4. preset from a profile + encoder fallback + bitrate overrides
pdir = os.path.join(OUT, "prof"); os.makedirs(pdir)
json.dump({"name": "t", "brand": {"colors": {"primary": "#000000", "accent": "#ffffff"}, "fonts": {}}, "paths": {},
           "delivery": {"web": {"vcodec": "no_such_encoder", "b_v": "2M", "maxrate": "3M", "bufsize": "4M"}}},
          open(os.path.join(pdir, "profile.json"), "w"))
m3 = os.path.join(final, "fallback.mp4")
rc, o = run("master", a, "-o", m3, "--profile", pdir, "--no-verify")
expect("profile preset + software fallback", rc == 0 and "libx264 (software fallback" in o and "-preset fast" in o
       and "-b:v 2M -maxrate 3M -bufsize 4M" in o, o)
m4 = os.path.join(final, "override.mp4")
rc, o = run("master", a, "-o", m4, "--b-v", "14M", "--maxrate", "16M", "--bufsize", "28M", "--no-verify")
expect("--b-v/--maxrate/--bufsize override (14M copy)", rc == 0 and "-b:v 14M -maxrate 16M -bufsize 28M" in o)

# 5. rewrap ts -> mp4 is a pure stream copy
ts = os.path.join(OUT, "game.ts")
ff("-i", a, "-c", "copy", "-f", "mpegts", ts)
rc, o = run("rewrap", ts)
rw = os.path.join(OUT, "game.mp4")
expect("rewrap exits 0 + verifies", rc == 0 and "VERIFY_OK" in o, o)
expect("rewrap: identical decoded video + audio", framemd5(rw, "v") == framemd5(ts, "v") and framemd5(rw, "a") == framemd5(ts, "a"))

# 6. verify catches a broken master (truncated, like a run that died before the moov atom)
broken = os.path.join(OUT, "broken.mp4")
shutil.copy(m2, broken)
with open(broken, "r+b") as f:
    f.truncate(os.path.getsize(broken) // 2)
rc, o = run("verify", broken, "--like", lst)
expect("truncated file -> VERIFY_FAIL", rc == 1 and "VERIFY_FAIL" in o, o)
rc, o = run("verify", master, "--expect", "9.0")
expect("duration mismatch -> VERIFY_FAIL", rc == 1 and "MISMATCH" in o)
rc, o = run("verify", master, "--like", lst, "--full-verify")
expect("--full-verify on a good file", rc == 0 and "full file" in o)

# 7. copy-verify into a 'Dropbox' folder
box = os.path.join(OUT, "web"); os.makedirs(box)
log = os.path.join(OUT, "dropbox_copy.log")
rc, o = run("copy-verify", master, "--to", box, "--log", log)
expect("copy-verify OK + byte identical", rc == 0 and "COPY_OK" in o and
       open(master, "rb").read() == open(os.path.join(box, os.path.basename(master)), "rb").read(), o)
rc, o = run("copy-verify", master, "--to", box, "--log", log)
expect("second copy: already there (byte-identical)", rc == 0 and "ALREADY_THERE" in o)
open(os.path.join(box, "nofs.mp4"), "wb").write(b"other")
rc, o = run("copy-verify", m2, "--to", box, "--log", log)
expect("different file at destination is left alone", rc == 1 and "left alone" in o
       and open(os.path.join(box, "nofs.mp4"), "rb").read() == b"other")
rc, o = run("copy-verify", master, "--to", "no_such_paths_key")
expect("unknown --to key refused", rc != 0)

# 8. help + ffmpeg lookup
r = subprocess.run([sys.executable, ENC, "--help"], capture_output=True, text=True)
expect("--help", r.returncode == 0 and "copy-verify" in r.stdout)
expect("finds ffmpeg", encode.find_ffmpeg() is not None)

# 9. the preset comes from the profile only (no built-in bitrates): missing preset / keys fail clearly
for k, (dl, want) in enumerate([({}, "has no delivery.web"),
                                ({"web": {"vcodec": "libx264", "maxrate": "3M", "bufsize": "4M"}}, "missing b_v")]):
    pd = os.path.join(OUT, f"prof_nopreset{k}"); os.makedirs(pd)
    json.dump({"name": f"np{k}", "brand": {"colors": {"primary": "#000000", "accent": "#ffffff"}, "fonts": {}}, "paths": {},
               "delivery": dl}, open(os.path.join(pd, "profile.json"), "w"))
    rc, o = run("master", a, "-o", os.path.join(final, f"np{k}.mp4"), "--profile", pd, "--no-verify")
    expect(f"profile without a full delivery.web -> clear FATAL ({want}), nothing written",
           rc != 0 and want in o and not os.path.exists(os.path.join(final, f"np{k}.mp4")), o)
ts2 = os.path.join(OUT, "np.ts")
ff("-i", a, "-c", "copy", "-f", "mpegts", ts2)
rc, o = run("rewrap", ts2, "--profile", os.path.join(OUT, "prof_nopreset0"), "--no-verify")
expect("rewrap needs no encode preset (profile without delivery.web)", rc == 0 and os.path.isfile(ts2[:-3] + ".mp4"), o)

# 10. ffmpeg never reads stdin: run with a terminal holding 'q' keystrokes as stdin (an ffmpeg that reads it quits early)
import pty
mq, sq = pty.openpty(); os.write(mq, b"q" * 512)
mq_out = os.path.join(final, "qtty.mp4")
r = subprocess.run([sys.executable, ENC, "master", lst, "-o", mq_out, "--no-caffeinate"], stdin=sq, capture_output=True, text=True)
os.close(mq); os.close(sq)
expect("master with a 'q' terminal as stdin: same frames as the normal master + VERIFY_OK",
       r.returncode == 0 and "VERIFY_OK" in r.stdout + r.stderr and framemd5(mq_out) == framemd5(master), r.stdout + r.stderr)

# 11. every failure is in the log: FATAL <reason>, the failure line, then '=== FAILED <mode>' (a watcher never waits for ever)
def tail_run(logf):
    t = open(logf).read() if os.path.isfile(logf) else ""
    return t.rsplit("=== START", 1)[-1]


rc, o = run("master", lst, "-o", master)                                  # exists, no --force
L = tail_run(os.path.join(enc, "encode.log"))
expect("existing output: FATAL ... exists + ENCODE_FAIL + '=== FAILED master' in encode.log", rc == 1
       and "FATAL: " in L and "exists (pass --force" in L and "ENCODE_FAIL FATAL" in L and "=== FAILED master" in L, L)
rc, o = run("master", a, "-o", a, "--force")
L = tail_run(os.path.join(OUT, ".enc", "encode.log"))
expect("output == input: FATAL + ENCODE_FAIL + FAILED in the log", rc == 1 and "also an input" in L
       and "ENCODE_FAIL" in L and "=== FAILED master" in L, L)
rc, o = run("master", a, "-o", os.path.join(final, "np_log.mp4"), "--profile", os.path.join(OUT, "prof_nopreset0"))
L = tail_run(os.path.join(enc, "encode.log"))
expect("no encode preset in the profile: FATAL + ENCODE_FAIL + FAILED in the log", rc == 1
       and "has no delivery.web" in L and "ENCODE_FAIL" in L and "=== FAILED master" in L, L)
badl = os.path.join(enc, "bad_concat.txt"); open(badl, "w").write(f"ffconcat version 1.0\nfile '{a}'\ninpoint soon\n")
rc, o = run("master", badl, "-o", os.path.join(final, "bad.mp4"))
L = tail_run(os.path.join(enc, "encode.log"))
expect("unreadable concat list: FATAL ValueError + ENCODE_FAIL + FAILED in the log, exit 1, nothing written", rc == 1
       and "FATAL: ValueError" in L and "ENCODE_FAIL" in L and "=== FAILED master" in L
       and not os.path.exists(os.path.join(final, "bad.mp4")), L)
cl = os.path.join(OUT, "copy_fail.log")
rc, o = run("copy-verify", master, "--to", "no_such_paths_key", "--log", cl)
L = tail_run(cl)
expect("copy-verify to an unknown --to key: FATAL + COPY_FAIL + '=== FAILED copy-verify'", rc == 1
       and "FATAL: --to" in L and "COPY_FAIL" in L and "=== FAILED copy-verify" in L, L)

print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
