#!/usr/bin/env python3
"""Build, rewrap, copy and verify delivery masters with ffmpeg, using an encode preset from the profile.

    encode.py master  INPUT... -o OUT.mp4 [--preset web] [--b-v 12M --maxrate 14M --bufsize 24M]
                      [--faststart|--no-faststart] [--full-verify] [--force] [--log FILE]
    encode.py rewrap  IN.ts [-o OUT.mp4]                      stream copy into MP4 (no quality loss)
    encode.py copy-verify FILE... --to DIR|<paths key>        copy (cp -p) then byte-compare (cmp)
    encode.py verify  FILE [--expect SECONDS | --like INPUT...] [--full-verify]

master: INPUT is one concat list (ffconcat .txt; inpoint/outpoint/duration lines are honoured for the duration
check) or one or more media files (several are joined with a concat list written next to OUT under .enc/).
The video is encoded with the preset (profile delivery.<preset>: vcodec, falling back to vcodec_fallback when
this ffmpeg lacks it, bitrate, maxrate, bufsize); audio is copied. +faststart is used only when the expected
output is under the preset's faststart_max_gb (rewriting a 10+ GB file at the end is the step that failed on a
long game); --faststart / --no-faststart override.
Every output is written as <name>.partial.mp4 and renamed when ffmpeg succeeds, so a crash never leaves a
broken file under the final name. An existing OUT is never replaced without --force, and an input is never
an output.

Verify (runs after master/rewrap, or on its own): decode errors in the first and last minute (--full-verify:
the whole file), and the duration against the inputs (tolerance --tol seconds). Prints VERIFY_OK / VERIFY_FAIL.
The Mac is kept awake (caffeinate) while it runs. ffmpeg is looked up in the usual install places, then PATH.

Log protocol (what a script or Claude can wait on): every run starts "=== START <mode>" and ends "=== DONE <mode>"
(exit 0) or "=== FAILED <mode>" (exit non-zero). Before a FAILED line there is always at least one failure line:
ENCODE_FAIL or VERIFY_FAIL (master), REWRAP_FAIL or VERIFY_FAIL (rewrap), COPY_FAIL (copy-verify), VERIFY_FAIL
(verify). A problem that stops the run before or instead of ffmpeg (output exists without --force, output is an
input, no encode preset in the profile, no ffmpeg, an unreadable concat list, ...) logs "FATAL: <reason>" and then
"<failure line> FATAL: <reason>"."""
import argparse, datetime as dt, os, shlex, shutil, subprocess, sys, traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import vprofile as prof  # noqa: E402
import offload  # noqa: E402

# An encode preset is the profile's delivery.<preset> (e.g. delivery.web). The profile must give the encoder and
# the bitrates; these generic settings fill in anything else it leaves out.
PRESET_REQUIRED = ("vcodec", "b_v", "maxrate", "bufsize")
PRESET_GENERIC = {"vcodec_fallback": "libx264", "fallback_args": ["-preset", "fast"], "acodec": "copy",
                  "faststart_max_gb": 10}
# usual ffmpeg install locations (Homebrew arm64/intel, Shutter Encoder's bundled copy), then PATH
FFMPEG_CANDIDATES = ["/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg", "~/Shutter Encoder/Library/ffmpeg",
                     "/Applications/Shutter Encoder.app/Contents/Resources/Library/ffmpeg"]


class Log(offload.Log):
    pass


# the line every failed run logs before "=== FAILED <mode>" (see the log protocol above)
FAIL_MARK = {"master": "ENCODE_FAIL", "rewrap": "REWRAP_FAIL", "copy-verify": "COPY_FAIL", "verify": "VERIFY_FAIL"}


def log_fatal(log, mode, why):
    """A problem that stops the run: 'FATAL: <why>' plus the mode's failure line, both in the log."""
    why = str(why)
    why = why[len("FATAL:"):].strip() if why.startswith("FATAL:") else why
    log(f"FATAL: {why}")
    log(f"{FAIL_MARK[mode]} FATAL: {why} {now()}")


def now():
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def find_ffmpeg():
    for c in FFMPEG_CANDIDATES + [shutil.which("ffmpeg") or ""]:
        c = os.path.expanduser(c)
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return None


def find_ffprobe(ff):
    p = os.path.join(os.path.dirname(ff), "ffprobe")
    if os.path.isfile(p) and os.access(p, os.X_OK):
        return p
    return shutil.which("ffprobe")


def has_encoder(ff, name):
    try:
        out = subprocess.run([ff, "-hide_banner", "-nostdin", "-encoders"], capture_output=True, text=True,
                             stdin=subprocess.DEVNULL).stdout
    except OSError:
        return False
    return any(line.split()[1:2] == [name] for line in out.splitlines() if line.strip())


def load_preset(profile, name):
    try:
        P = prof.load(profile)
    except prof.ProfileError as e:
        raise SystemExit(f"FATAL: encode preset {name!r} comes from the profile: {e}")
    got = P.get(f"delivery.{name}", None)
    if not isinstance(got, dict):
        raise SystemExit(f"FATAL: no encode preset {name!r}: profile {P.name} has no delivery.{name} "
                         f"(needs {', '.join(PRESET_REQUIRED)})")
    missing = [k for k in PRESET_REQUIRED if not got.get(k)]
    if missing:
        raise SystemExit(f"FATAL: profile {P.name} delivery.{name} is missing {', '.join(missing)}")
    return dict(PRESET_GENERIC, **got)


def faststart_limit_gb(profile, name):
    """delivery.<name>.faststart_max_gb when the profile has it (a rewrap needs nothing else from the preset)"""
    try:
        got = prof.load(profile).get(f"delivery.{name}", None)
    except prof.ProfileError:
        got = None
    return float((got if isinstance(got, dict) else {}).get("faststart_max_gb", PRESET_GENERIC["faststart_max_gb"]))


def to_bits(s):
    s = str(s).strip().upper()
    mult = {"K": 1e3, "M": 1e6, "G": 1e9}.get(s[-1:], 1)
    return float(s[:-1] if s[-1:] in "KMG" else s) * mult


def probe_duration(fp, path):
    try:
        r = subprocess.run([fp, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                           capture_output=True, text=True, stdin=subprocess.DEVNULL)
        return float(r.stdout.strip())
    except (ValueError, OSError):
        return None


def probe_audio_bits(fp, path):
    try:
        r = subprocess.run([fp, "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=bit_rate",
                            "-of", "csv=p=0", path], capture_output=True, text=True, stdin=subprocess.DEVNULL)
        return float(r.stdout.strip())
    except (ValueError, OSError):
        return 320e3


def parse_concat(path):
    """[(file, inpoint, outpoint, duration)] from an ffconcat list (paths relative to the list resolved)."""
    items, base = [], os.path.dirname(os.path.abspath(path))
    with open(path) as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or line.lower().startswith("ffconcat"):
                continue
            key, _, rest = line.partition(" ")
            key = key.lower(); rest = rest.strip()
            if key == "file":
                p = shlex.split(rest)[0] if rest[:1] in "'\"" else rest
                if not os.path.isabs(p):
                    p = os.path.join(base, p)
                items.append([p, None, None, None])
            elif items and key in ("inpoint", "outpoint", "duration"):
                items[-1][{"inpoint": 1, "outpoint": 2, "duration": 3}[key]] = float(rest)
    return [tuple(i) for i in items]


def expected_duration(fp, inputs):
    """Sum of the inputs' playable durations (concat lists honour inpoint/outpoint/duration)."""
    total = 0.0
    for inp in inputs:
        if inp.lower().endswith((".txt", ".ffconcat")):
            for f, ip, op, du in parse_concat(inp):
                if du is not None:
                    total += du; continue
                d = probe_duration(fp, f)
                if d is None:
                    return None
                total += (op if op is not None else d) - (ip or 0.0)
        else:
            d = probe_duration(fp, inp)
            if d is None:
                return None
            total += d
    return total


def concat_inputs(inputs):
    return [f for inp in inputs for f in ([x[0] for x in parse_concat(inp)]
                                          if inp.lower().endswith((".txt", ".ffconcat")) else [inp])]


def decode_check(ff, path, full, minutes=1.0):
    """'' when clean, else the first error lines."""
    def run(extra_in):
        r = subprocess.run([ff, "-hide_banner", "-nostdin", "-v", "error"] + extra_in + ["-i", path, "-f", "null", "-"],
                           capture_output=True, text=True, stdin=subprocess.DEVNULL)
        err = (r.stderr or "").strip()
        if r.returncode != 0 and not err:
            err = f"ffmpeg exit {r.returncode}"
        return err
    if full:
        return run([])
    secs = f"{60 * minutes:g}"
    e1 = run(["-t", secs])               # first minute
    e2 = run(["-sseof", f"-{secs}"])     # last minute
    return "\n".join(x for x in (e1, e2) if x)


def verify(ff, fp, out, inputs, full, tol, log, expect=None):
    ok = True
    if not os.path.isfile(out) or os.path.getsize(out) == 0:
        log(f"VERIFY_FAIL missing or empty: {out}"); return False
    err = decode_check(ff, out, full)
    if err:
        ok = False
        log("DECODE_ERRORS " + " | ".join(err.splitlines()[:3]))
    else:
        log("DECODE_OK " + ("full file" if full else "first + last minute"))
    d = probe_duration(fp, out)
    want = expect if expect is not None else (expected_duration(fp, inputs) if inputs else None)
    if d is None:
        ok = False; log("DURATION unreadable (no moov atom?)")
    elif want is not None:
        good = abs(d - want) <= tol
        ok &= good
        log(f"DURATION {d:.2f} s expected {want:.2f} s (+-{tol:g}) {'OK' if good else 'MISMATCH'}")
    else:
        log(f"DURATION {d:.2f} s")
    log(f"{'VERIFY_OK' if ok else 'VERIFY_FAIL'} {os.path.basename(out)} {os.path.getsize(out) / 1e9:.2f} GB {now()}")
    return ok


def guard_output(out, inputs, force):
    o = os.path.realpath(out)
    for i in concat_inputs(inputs) + list(inputs):
        if os.path.realpath(i) == o:
            raise SystemExit(f"FATAL: output {out} is also an input")
    if os.path.exists(out) and not force:
        raise SystemExit(f"FATAL: {out} exists (pass --force to replace it)")


def partial_name(out):
    stem, ext = os.path.splitext(out)
    return f"{stem}.partial{ext or '.mp4'}"


def run_ffmpeg(cmd, log):
    log("CMD " + " ".join(shlex.quote(c) for c in cmd))
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
                         stdin=subprocess.DEVNULL)
    for line in p.stdout:
        line = line.rstrip()
        if line:
            log(line)
    return p.wait()


def want_faststart(a, preset, est_bytes):
    if a.faststart is not None:
        return a.faststart
    lim = float(preset.get("faststart_max_gb", 10)) * 1e9
    return est_bytes is not None and est_bytes < lim


def do_master(a, ff, fp, log):
    if not a.preset:
        try:
            a.preset = prof.load(a.profile).get("delivery.default_preset", "web")
        except Exception:
            a.preset = "web"
    preset = load_preset(a.profile, a.preset)
    for k in ("b_v", "maxrate", "bufsize"):
        if getattr(a, k):
            preset[k] = getattr(a, k)
    inputs = [os.path.abspath(os.path.expanduser(i)) for i in a.inputs]
    out = os.path.abspath(os.path.expanduser(a.out))
    guard_output(out, inputs, a.force)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    if len(inputs) == 1 and inputs[0].lower().endswith((".txt", ".ffconcat")):
        src = ["-f", "concat", "-safe", "0", "-i", inputs[0]]
    elif len(inputs) == 1:
        src = ["-i", inputs[0]]
    else:
        enc = os.path.join(os.path.dirname(out), ".enc"); os.makedirs(enc, exist_ok=True)
        lst = os.path.join(enc, os.path.splitext(os.path.basename(out))[0] + "_concat.txt")
        with open(lst, "w") as f:
            f.write("ffconcat version 1.0\n")
            for i in inputs:
                f.write("file '" + i.replace("'", "'\\''") + "'\n")
        log(f"CONCAT {lst} ({len(inputs)} files)")
        src = ["-f", "concat", "-safe", "0", "-i", lst]
    vc = preset["vcodec"]; extra = []
    if not has_encoder(ff, vc):
        vc = preset.get("vcodec_fallback", "libx264"); extra = list(preset.get("fallback_args", []))
        log(f"encoder: {vc} (software fallback; {preset['vcodec']} not in this ffmpeg)")
    else:
        log(f"encoder: {vc}")
    venc = ["-c:v", vc] + extra + (["-profile:v", preset["profile"]] if preset.get("profile") else []) + \
           ["-b:v", str(preset["b_v"]), "-maxrate", str(preset["maxrate"]), "-bufsize", str(preset["bufsize"])]
    dur = expected_duration(fp, inputs)
    est = None
    if dur is not None:
        abits = probe_audio_bits(fp, concat_inputs(inputs)[0]) if preset.get("acodec", "copy") == "copy" else 160e3
        est = dur * (to_bits(preset["b_v"]) + abits) / 8
        log(f"EXPECTED {dur:.1f} s, about {est / 1e9:.1f} GB")
    fs = want_faststart(a, preset, est)
    log(f"faststart: {'on' if fs else 'off'}")
    part = partial_name(out)
    cmd = [ff, "-y", "-hide_banner", "-nostdin"] + src + ["-map", "0:v:0", "-map", "0:a:0"] + venc + \
          ["-c:a", preset.get("acodec", "copy")] + (["-movflags", "+faststart"] if fs else []) + ["-f", "mp4", part]
    rc = run_ffmpeg(cmd, log)
    log(f"EXIT {rc} {now()}")
    if rc != 0:
        log(f"ENCODE_FAIL (partial left at {part})"); return 1
    os.replace(part, out)
    log(f"WROTE {out} {os.path.getsize(out) / 1e9:.2f} GB")
    if a.no_verify:
        return 0
    return 0 if verify(ff, fp, out, inputs, a.full_verify, a.tol, log) else 1


def do_rewrap(a, ff, fp, log):
    inp = os.path.abspath(os.path.expanduser(a.inputs[0]))
    out = os.path.abspath(os.path.expanduser(a.out or os.path.splitext(inp)[0] + ".mp4"))
    guard_output(out, [inp], a.force)
    fs = a.faststart if a.faststart is not None else os.path.getsize(inp) < faststart_limit_gb(a.profile, a.preset) * 1e9
    part = partial_name(out)
    cmd = [ff, "-y", "-hide_banner", "-nostdin", "-i", inp, "-map", "0:v:0", "-map", "0:a:0", "-c", "copy"] + \
          (["-movflags", "+faststart"] if fs else []) + ["-f", "mp4", part]
    rc = run_ffmpeg(cmd, log)
    log(f"EXIT {rc} {now()}")
    if rc != 0:
        log(f"REWRAP_FAIL (partial left at {part})"); return 1
    os.replace(part, out)
    log(f"WROTE {out}")
    if a.no_verify:
        return 0
    return 0 if verify(ff, fp, out, [inp], a.full_verify, a.tol, log) else 1


def resolve_dest(to, profile):
    if os.sep in to or to.startswith("~") or os.path.isdir(to):
        return os.path.abspath(os.path.expanduser(to))
    P = prof.load(profile)
    if P.has_path(to):
        return P.path(to)
    raise SystemExit(f"--to {to!r}: not a folder and not a paths key in profile {P.name}")


def do_copy_verify(a, log):
    dest = resolve_dest(a.to, a.profile)
    if not os.path.isdir(dest):
        log(f"COPY_FAIL destination folder missing: {dest}"); return 1
    bad = 0
    for inp in a.inputs:
        src = os.path.abspath(os.path.expanduser(inp))
        if os.path.realpath(dest) == os.path.realpath(os.path.dirname(src)):
            log(f"COPY_FAIL {src} is already in {dest}"); bad += 1; continue
        dst = os.path.join(dest, os.path.basename(src))
        log(f"COPY {src} -> {dst} {now()}")
        status, final = offload.copy_one(src, dst, "cmp", "skip")
        if status == "SKIP":
            status = "OK" if offload.same_bytes(src, final) else "FAIL:existing same-size file differs"
            if status == "OK":
                log(f"ALREADY_THERE {os.path.basename(src)} (byte-identical)")
        if status == "OK":
            log(f"COPY_OK {os.path.basename(src)} {now()}")
        elif status == "CONFLICT":
            bad += 1; log(f"COPY_FAIL {os.path.basename(src)}: a different file is already at {dst} (left alone)")
        else:
            bad += 1; log(f"COPY_FAIL {os.path.basename(src)} {status[5:]} {now()}")
    return 1 if bad else 0


def run_mode(a, log):
    if a.mode == "copy-verify":
        return do_copy_verify(a, log)
    ff = find_ffmpeg()
    if not ff:
        raise SystemExit("no ffmpeg found (install it with Homebrew, or Shutter Encoder)")
    fp = find_ffprobe(ff)
    if not fp:
        raise SystemExit("no ffprobe next to ffmpeg or on PATH")
    log(f"ffmpeg: {ff}")
    if a.mode == "master":
        return do_master(a, ff, fp, log)
    if a.mode == "rewrap":
        return do_rewrap(a, ff, fp, log)
    rc = 0
    for f in a.inputs:
        if not verify(ff, fp, os.path.abspath(os.path.expanduser(f)),
                      [os.path.abspath(os.path.expanduser(x)) for x in (a.like or [])],
                      a.full_verify, a.tol, log, a.expect):
            rc = 1
    return rc


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("mode", choices=["master", "rewrap", "copy-verify", "verify"])
    ap.add_argument("inputs", nargs="+", help="concat list / media files (master), .ts (rewrap), files (copy-verify, verify)")
    ap.add_argument("-o", "--out", help="output file (master: required; rewrap: default IN with .mp4)")
    ap.add_argument("--preset", default=None, help="profile delivery.<preset> (default: the profile's delivery.default_preset, else web)")
    ap.add_argument("--b-v", dest="b_v", help="override video bitrate, e.g. 14M")
    ap.add_argument("--maxrate", help="override maxrate, e.g. 16M")
    ap.add_argument("--bufsize", help="override bufsize, e.g. 28M")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--faststart", dest="faststart", action="store_true", default=None, help="force +faststart")
    g.add_argument("--no-faststart", dest="faststart", action="store_false", help="never +faststart")
    ap.add_argument("--to", help="copy-verify: destination folder or a profile paths key (e.g. delivery_inbox)")
    ap.add_argument("--full-verify", action="store_true", help="decode the whole output (default: first + last minute)")
    ap.add_argument("--no-verify", action="store_true", help="skip the verify step after master/rewrap")
    ap.add_argument("--expect", type=float, help="verify: expected duration in seconds")
    ap.add_argument("--like", nargs="+", help="verify: inputs whose total duration the file should match")
    ap.add_argument("--tol", type=float, default=2.0, help="duration tolerance in seconds (default 2)")
    ap.add_argument("--force", action="store_true", help="replace an existing output")
    ap.add_argument("--log", help="log file (appended). Default: <output folder>/.enc/encode.log")
    ap.add_argument("--no-caffeinate", action="store_true")
    prof.add_arg(ap)
    a = ap.parse_args(argv)

    if a.mode == "master" and not a.out:
        ap.error("master needs -o OUT")
    if a.mode == "copy-verify" and not a.to:
        ap.error("copy-verify needs --to DIR")
    if a.log:
        log_path = a.log
    elif a.mode in ("master", "rewrap"):
        o = a.out or os.path.splitext(a.inputs[0])[0] + ".mp4"
        log_path = os.path.join(os.path.dirname(os.path.abspath(os.path.expanduser(o))), ".enc", "encode.log")
    else:
        log_path = None
    if log_path:
        os.makedirs(os.path.dirname(os.path.abspath(log_path)), exist_ok=True)
    log = Log(log_path)
    awake = offload.keep_awake(not a.no_caffeinate)
    log(f"=== START {a.mode} {now()} ===")
    rc = 1
    try:
        rc = run_mode(a, log)
    except SystemExit as e:              # guard_output, load_preset, resolve_dest, ...: a clear reason, no traceback
        log_fatal(log, a.mode, e.code if isinstance(e.code, str) else f"stopped (exit {e.code})")
        rc = 1
    except KeyboardInterrupt:
        log_fatal(log, a.mode, "interrupted (Ctrl-C)")
        rc = 130
    except Exception as e:               # anything unexpected: the reason in the log, the traceback in the Terminal
        traceback.print_exc()
        log_fatal(log, a.mode, f"{type(e).__name__}: {e}")
        rc = 1
    try:
        log(f"=== {'DONE' if rc == 0 else 'FAILED'} {a.mode} {now()} ===")
        return rc
    finally:
        log.close()
        if awake:
            awake.terminate()


if __name__ == "__main__":
    sys.exit(main())
