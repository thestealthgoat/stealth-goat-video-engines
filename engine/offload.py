#!/usr/bin/env python3
"""Offload a camera card (or any folder) to a destination, safely and resumably.

    offload.py SRC DST [--files-from LIST] [--date YYYY-MM-DD] [--since "YYYY-MM-DD HH:MM"] [--until ...]
                       [--ext CR3,JPG,MP4,MOV] [--flat] [--verify cmp|md5|size] [--label REC] [--log FILE]
                       [--check-only [--sample N]] [--histogram] [--dry-run] [--conflict skip|rename]
                       [--no-caffeinate] [--profile NAME]

Rules it keeps:
  * SRC is strictly read-only: files are only opened for reading; DST and the log may not be inside SRC.
  * A different file already at the destination is never overwritten (CONFLICT, or --conflict rename).
  * A destination file of the same size is skipped (that is what makes a re-run resume where it stopped).
  * Every copy lands as <name>.part and is renamed only after a full byte verify (cmp, or md5 with --verify md5).
    Timestamps are preserved (like cp -p).
  * Everything goes to a log (default <DST>/_offload_<date>.log, appended) and to the terminal.
  * The last line is "<LABEL>_COMPLETE copied N skipped M ..." (LABEL defaults to ALL, so ALL_COMPLETE), or
    "<LABEL>_INCOMPLETE ..." with exit code 1 when anything failed. Other scripts can wait on that line.
  * On macOS the Mac is kept awake (caffeinate) while it runs.

SRC may be a profile card name (e.g. "ninja", "eos" -> profile cards.ninja / cards.eos).
--files-from: one path per line, relative to SRC (rsync style) or absolute (a `find` listing under SRC).
--date D[,D2]: files modified on those local calendar days. --since/--until: an explicit window
("2026-10-15 00:00" .. "2026-10-16 06:00" catches a game that runs past midnight). --flat puts every file
directly in DST (photo cards); the default keeps the folder structure under SRC.
--check-only: copy nothing; compare sizes of every listed file with DST and byte-compare all of them
(or every Nth with --sample N).
"""
import argparse, datetime as dt, hashlib, os, shutil, subprocess, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vprofile as prof  # noqa: E402

CHUNK = 8 * 1024 * 1024


class Log:
    def __init__(self, path):
        self.path = path
        self.f = open(path, "a") if path else None

    def __call__(self, *parts):
        line = " ".join(str(p) for p in parts)
        print(line, flush=True)
        if self.f:
            self.f.write(line + "\n"); self.f.flush()

    def close(self):
        if self.f:
            self.f.close()


def now():
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def hms():
    return dt.datetime.now().strftime("%H:%M:%S")


def inside(child, parent):
    child, parent = os.path.realpath(child), os.path.realpath(parent)
    return child == parent or child.startswith(parent.rstrip(os.sep) + os.sep)


def keep_awake(enabled):
    """caffeinate -i for as long as this process lives (macOS only)."""
    if not enabled or sys.platform != "darwin" or not shutil.which("caffeinate"):
        return None
    try:
        return subprocess.Popen(["caffeinate", "-i", "-w", str(os.getpid())],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        return None


def parse_when(s, end=False):
    s = s.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            t = dt.datetime.strptime(s, fmt)
            if fmt == "%Y-%m-%d" and end:
                t += dt.timedelta(days=1)
            return t.timestamp()
        except ValueError:
            pass
    raise SystemExit(f"bad date/time {s!r} (use YYYY-MM-DD or 'YYYY-MM-DD HH:MM')")


def windows(a):
    """List of [start, end) epoch windows from --date / --since / --until (empty = no filter)."""
    w = []
    for d in (a.date or "").split(","):
        if d.strip():
            w.append((parse_when(d), parse_when(d, end=True)))
    if a.since or a.until:
        w.append((parse_when(a.since) if a.since else float("-inf"),
                  parse_when(a.until, end=True) if a.until else float("inf")))
    return w


def wanted(name, exts):
    if name.startswith("._") or name.startswith(".") or name.endswith(".part"):
        return False
    return not exts or os.path.splitext(name)[1].lower().lstrip(".") in exts


def list_sources(src, a, exts):
    """(absolute source path, path relative to SRC) in a stable order."""
    out = []
    if a.files_from:
        with open(a.files_from) as f:
            for line in f:
                p = line.rstrip("\n").rstrip("\r")
                if not p.strip():
                    continue
                ap = p if os.path.isabs(p) else os.path.join(src, p)
                rel = os.path.relpath(ap, src) if inside(ap, src) else os.path.basename(ap)
                out.append((ap, rel))
    elif os.path.isfile(src):
        out.append((src, os.path.basename(src)))
    else:
        for root, dirs, files in os.walk(src):
            dirs[:] = sorted(d for d in dirs if not d.startswith("."))
            for n in sorted(files):
                if wanted(n, exts):
                    ap = os.path.join(root, n)
                    out.append((ap, os.path.relpath(ap, src)))
    if a.files_from and exts:
        out = [x for x in out if wanted(os.path.basename(x[0]), exts)]
    every = list(out)
    w = windows(a)
    if w:
        keep = []
        for ap, rel in out:
            try:
                m = os.stat(ap).st_mtime
            except OSError:
                keep.append((ap, rel)); continue   # missing: reported as FAIL later
            if any(s <= m < e for s, e in w):
                keep.append((ap, rel))
        out = keep
    return out, every


def same_bytes(p1, p2):
    with open(p1, "rb") as f1, open(p2, "rb") as f2:
        while True:
            b1 = f1.read(CHUNK); b2 = f2.read(CHUNK)
            if b1 != b2:
                return False
            if not b1:
                return True


def md5(p):
    h = hashlib.md5()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(CHUNK), b""):
            h.update(b)
    return h.hexdigest()


def verify(src, dst, how):
    if os.path.getsize(src) != os.path.getsize(dst):
        return False
    if how == "size":
        return True
    if how == "md5":
        return md5(src) == md5(dst)
    return same_bytes(src, dst)


def copy_one(src, dst, how="cmp", conflict="skip"):
    """Copy src -> dst. Returns (status, final_dst): status OK | SKIP | CONFLICT | FAIL:<why>.
    Never overwrites a different existing file; never writes to src."""
    size = os.path.getsize(src)
    if os.path.exists(dst):
        if os.path.getsize(dst) == size:
            return "SKIP", dst
        if conflict != "rename":
            return "CONFLICT", dst
        stem, ext = os.path.splitext(dst); k = 1
        while os.path.exists(f"{stem}_{k}{ext}"):
            if os.path.getsize(f"{stem}_{k}{ext}") == size:
                return "SKIP", f"{stem}_{k}{ext}"
            k += 1
        dst = f"{stem}_{k}{ext}"
    os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
    part = dst + ".part"
    try:
        with open(src, "rb") as fi, open(part, "wb") as fo:
            shutil.copyfileobj(fi, fo, CHUNK)
            fo.flush(); os.fsync(fo.fileno())
        shutil.copystat(src, part)
        if not verify(src, part, how):
            os.remove(part)
            return "FAIL:verify", dst
        os.replace(part, dst)
        return "OK", dst
    except OSError as e:
        try:
            os.remove(part)
        except OSError:
            pass
        return f"FAIL:{e.strerror or e}", dst


def resolve_src(s, profile):
    if os.path.exists(s) or os.sep in s:
        return s
    try:
        P = prof.load(profile)
        if P.get(f"cards.{s}", None):
            return P.asset(f"cards.{s}")
    except prof.ProfileError:
        pass
    return s


def histogram(items, log):
    n, sz = {}, {}
    for ap, _ in items:
        try:
            st = os.stat(ap)
        except OSError:
            continue
        d = dt.datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d")
        n[d] = n.get(d, 0) + 1; sz[d] = sz.get(d, 0) + st.st_size
    log("== date histogram (local) ==")
    for d in sorted(n):
        log(f"{d} {n[d]} files {sz[d] / 1e9:.1f} GB")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("src", help="card or folder to copy from (read-only), or a profile card name")
    ap.add_argument("dst", help="destination folder")
    ap.add_argument("--files-from", help="list of files to copy (relative to SRC or absolute)")
    ap.add_argument("--date", help="only files modified on these local days: YYYY-MM-DD[,YYYY-MM-DD]")
    ap.add_argument("--since", help="only files modified at/after this local time")
    ap.add_argument("--until", help="only files modified before this local time")
    ap.add_argument("--ext", help="comma list of extensions to include, e.g. CR3,JPG,MP4,MOV (default: all)")
    ap.add_argument("--flat", action="store_true", help="put every file directly in DST (default keeps sub-folders)")
    ap.add_argument("--verify", choices=["cmp", "md5", "size"], default="cmp",
                    help="check after each copy: full byte compare (default), md5 of both, or size only")
    ap.add_argument("--verify-existing", action="store_true",
                    help="also byte-compare same-size files that are already there (default: skip them)")
    ap.add_argument("--conflict", choices=["skip", "rename"], default="skip",
                    help="a different file with the same name at DST: report and leave it (default) or copy as name_1")
    ap.add_argument("--label", default="ALL", help="word for the summary line: <LABEL>_COMPLETE (default ALL)")
    ap.add_argument("--log", help="log file (appended). Default: <DST>/_offload_<YYYY-MM-DD>.log")
    ap.add_argument("--check-only", action="store_true", help="copy nothing; verify DST against SRC")
    ap.add_argument("--sample", type=int, default=1, help="with --check-only: byte-compare every Nth file (default 1 = all)")
    ap.add_argument("--histogram", action="store_true", help="log a per-day count/size of the source files first")
    ap.add_argument("--dry-run", action="store_true", help="list what would be copied, change nothing")
    ap.add_argument("--progress", type=int, default=250, help="progress line every N files (default 250)")
    ap.add_argument("--no-caffeinate", action="store_true")
    prof.add_arg(ap)
    a = ap.parse_args(argv)

    src = os.path.abspath(os.path.expanduser(resolve_src(a.src, a.profile)))
    dst = os.path.abspath(os.path.expanduser(a.dst))
    if not os.path.exists(src):
        print(f"FATAL: source not found: {src}", file=sys.stderr); return 2
    src_dir = src if os.path.isdir(src) else os.path.dirname(src)
    if inside(dst, src_dir):
        print(f"FATAL: destination {dst} is inside the source {src_dir} (the source is read-only)", file=sys.stderr)
        return 2
    log_path = None if a.dry_run else (a.log or os.path.join(dst, f"_offload_{dt.date.today().isoformat()}.log"))
    if log_path and inside(log_path, src_dir):
        print("FATAL: the log may not be written inside the source", file=sys.stderr); return 2
    if not a.dry_run:
        os.makedirs(dst, exist_ok=True)
        if log_path:
            os.makedirs(os.path.dirname(os.path.abspath(log_path)), exist_ok=True)
    log = Log(log_path)
    awake = keep_awake(not a.no_caffeinate and not a.dry_run)
    exts = {e.strip().lower().lstrip(".") for e in (a.ext or "").split(",") if e.strip()}

    log(f"START {now()} {a.label} {src} -> {dst}" + (" (check only)" if a.check_only else "")
        + (" (dry run)" if a.dry_run else ""))
    items, every = list_sources(src, a, exts)
    if a.histogram:
        histogram(every, log)            # the whole card (before the date filter), to see which days are on it
    log(f"LIST {len(items)}")

    copied = skipped = failed = conflicts = 0; nbytes = 0; t0 = time.time()
    for k, (sp, rel) in enumerate(items, 1):
        dp = os.path.join(dst, os.path.basename(rel) if a.flat else rel)
        if not os.path.isfile(sp):
            failed += 1; log(f"FAIL {rel} (missing at source)"); continue
        if a.check_only:
            ok = os.path.isfile(dp) and os.path.getsize(dp) == os.path.getsize(sp)
            if not ok:
                failed += 1; log(f"SIZEBAD {rel}"); continue
            if (k % max(1, a.sample)) == 0 and a.verify != "size" and not verify(sp, dp, a.verify):
                failed += 1; log(f"CMPBAD {rel}"); continue
            skipped += 1
            continue
        if a.dry_run:
            st = "SKIP" if os.path.isfile(dp) and os.path.getsize(dp) == os.path.getsize(sp) else \
                 ("CONFLICT" if os.path.exists(dp) else "WOULD_COPY")
            log(f"{st} {rel}")
            continue
        status, final = copy_one(sp, dp, a.verify, a.conflict)
        if status == "SKIP" and a.verify_existing and a.verify != "size" and not verify(sp, final, a.verify):
            status = "FAIL:existing file differs"
        if status == "OK":
            copied += 1; nbytes += os.path.getsize(final)
            log(f"OK {rel}" + ("" if final == dp else f" -> {os.path.basename(final)}"))
        elif status == "SKIP":
            skipped += 1
        elif status == "CONFLICT":
            conflicts += 1; log(f"CONFLICT {rel} (a different file is already at {dp}; left alone)")
        else:
            failed += 1; log(f"FAIL {rel} {status[5:]}")
        if a.progress and k % a.progress == 0:
            log(f"{a.label} {k}/{len(items)} {hms()}")

    secs = time.time() - t0
    bad = failed + conflicts
    if a.check_only:
        log(f"VERIFY {len(items)} files, bad {failed}" + (f" (byte-compared every {a.sample})" if a.sample > 1 else ""))
    summary = (f"copied {copied} skipped {skipped} failed {failed} conflicts {conflicts} "
               f"{nbytes / 1e9:.2f} GB {secs:.0f}s {now()}")
    log(f"{a.label}_{'INCOMPLETE' if bad else 'COMPLETE'} {summary}")
    log.close()
    if awake:
        awake.terminate()
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
