#!/usr/bin/env python3
"""frames.py - the looking half of the video gate: contact sheets at 4 fps and every cut frame by frame.

The machine pass (engine/qa.py) measures motion, cuts, flashes and sound, but it cannot see what a frame shows:
text overlapping text, a label over a face, a graphic that explodes or smears for a few frames, a wrong frame
at a cut. Those are found only by looking at frames. This script lays them out for reading:

    python3 frames.py <video> --out <dir> [--qa <qa folder or qa.json>] [--fps 4] [--window 10] [--cols 8] [--w 320]
                      [--from S --to S]

A graphic that breaks for 2-3 frames can fall between 4 fps samples: for every element entrance, exit and
transition, run the range again at the full rate, e.g. --from 12.0 --to 13.5 --fps 29.97 --window 1.5 (no --qa).

Writes into <dir>:
  contact_<start>s.jpg   one sheet per --window seconds, --fps frames a second (default 4), each tile labeled with
                         its time and (approximate) frame number
  cut_f<N>.jpg           with --qa: every detected and every planned cut, 4 frames before and 4 after, each labeled
                         with its exact frame number; the first frame of the new shot is outlined
  flag_f<A>-f<B>.jpg     with --qa: every flag span up to 2 s long (whole-file flags such as loudness are skipped),
                         frame by frame with 2 frames of context each side, at most 24 frames a strip

Needs ffmpeg/ffprobe and Pillow (both already needed by engine/qa.py). Reads the video only; writes only into --out.
"""
import argparse, glob, json, os, shutil, subprocess, sys, tempfile

from PIL import Image, ImageDraw, ImageFont


def probe(video):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets", "-show_entries",
                        "stream=avg_frame_rate,r_frame_rate,nb_read_packets:format=duration", "-of", "json", video],
                       capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"frames: cannot read {video}: {r.stderr.strip()}")
    j = json.loads(r.stdout)
    s = j["streams"][0]
    num, den = (s.get("avg_frame_rate") or s["r_frame_rate"]).split("/")
    fps = float(num) / float(den) if float(den) else 0.0
    if not fps:
        num, den = s["r_frame_rate"].split("/")
        fps = float(num) / float(den)
    n = int(s.get("nb_read_packets") or 0)
    dur = float(j["format"].get("duration") or (n / fps))
    return fps, n or int(round(dur * fps)), dur


def font(size):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:            # Pillow < 10.1
        return ImageFont.load_default()


def label(im, text, size=16):
    d = ImageDraw.Draw(im)
    f = font(size)
    box = d.textbbox((0, 0), text, font=f)
    d.rectangle((0, 0, box[2] + 10, box[3] + 8), fill=(0, 0, 0))
    d.text((5, 3), text, font=f, fill=(255, 255, 255))
    return im


def tile(images, cols, out, title=None):
    w, h = images[0].size
    rows = (len(images) + cols - 1) // cols
    top = 30 if title else 0
    sheet = Image.new("RGB", (w * min(cols, len(images)), h * rows + top), (24, 24, 24))
    for i, im in enumerate(images):
        sheet.paste(im.resize((w, h)), ((i % cols) * w, top + (i // cols) * h))
    if title:
        ImageDraw.Draw(sheet).text((8, 6), title, font=font(18), fill=(255, 255, 255))
    sheet.save(out, quality=85)
    return out


def contact_sheets(video, out, fps, dur, rate, window, cols, w, t_from=0.0, t_to=None):
    written = []
    with tempfile.TemporaryDirectory() as tmp:
        rng = ["-ss", f"{t_from:.4f}"] + (["-to", f"{t_to:.4f}"] if t_to is not None else [])
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", video] + rng +
                       ["-vf", f"fps={rate},scale={w}:-2", "-q:v", "3", os.path.join(tmp, "c_%06d.jpg")], check=True)
        paths = sorted(glob.glob(os.path.join(tmp, "c_*.jpg")))
        if not paths:
            sys.exit(f"frames: no frames decoded from {video} in that range")
        dur = t_to if t_to is not None else dur
        per = max(1, int(round(window * rate)))
        for k in range(0, len(paths), per):
            ims = []
            for i, p in enumerate(paths[k:k + per]):
                t = t_from + (k + i) / rate
                ims.append(label(Image.open(p).convert("RGB"), f"{t:.2f}s ~f{int(round(t * fps))}", 14))
            t0 = t_from + k / rate
            name = os.path.join(out, f"contact_{t0:07.2f}s.jpg")
            written.append(tile(ims, cols, name, f"{os.path.basename(video)}  {t0:.2f}-{min(dur, t0 + window):.2f} s"
                                                 f"  at {rate:g} fps"))
    return written


def exact_frames(video, wanted, w, tmp):
    """Decode once and keep exactly the frame numbers in `wanted` (sorted); returns {n: path}."""
    wanted = sorted(set(wanted))
    if not wanted:
        return {}
    spans, a = [], wanted[0]
    for p, q in zip(wanted, wanted[1:] + [None]):
        if q != p + 1:
            spans.append((a, p))
            a = q
    expr = "+".join(f"between(n\\,{x}\\,{y})" for x, y in spans)
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", video, "-vf", f"select={expr},scale={w}:-2",
                    "-fps_mode", "passthrough", "-q:v", "3", os.path.join(tmp, "x_%06d.jpg")], check=True)
    paths = sorted(glob.glob(os.path.join(tmp, "x_*.jpg")))
    return dict(zip(wanted, paths))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video")
    ap.add_argument("--out", required=True, help="folder for the sheets (created)")
    ap.add_argument("--qa", help="qa.py review folder or its qa.json: adds cut and flag strips")
    ap.add_argument("--fps", type=float, default=4.0, help="contact sheet rate, frames a second (default 4)")
    ap.add_argument("--window", type=float, default=10.0, help="seconds per contact sheet (default 10)")
    ap.add_argument("--cols", type=int, default=8, help="tiles per row (default 8)")
    ap.add_argument("--w", type=int, default=320, help="contact tile width in px (default 320)")
    ap.add_argument("--from", dest="t_from", type=float, default=0.0, help="contact sheets start here, seconds")
    ap.add_argument("--to", dest="t_to", type=float, help="contact sheets end here, seconds (default: the end)")
    ap.add_argument("--no-qa-strips", action="store_true", help="with --qa: contact sheets only, no cut/flag strips")
    ap.add_argument("--around", type=int, default=4, help="frames shown each side of a cut (default 4)")
    a = ap.parse_args()

    os.makedirs(a.out, exist_ok=True)
    fps, nframes, dur = probe(a.video)
    written = contact_sheets(a.video, a.out, fps, dur, a.fps, a.window, a.cols, a.w, a.t_from, a.t_to)

    if a.qa and not a.no_qa_strips:
        qj = a.qa if a.qa.endswith(".json") else os.path.join(a.qa, "qa.json")
        J = json.load(open(qj))
        fps = float(J.get("spec", {}).get("fps") or fps)
        nframes = int(J.get("spec", {}).get("frames") or nframes)
        cuts = {int(c["frame"]) for c in J.get("cuts") or []}
        for t in J.get("planned_cuts") or []:
            f = int(round(float(t) * fps))
            if not any(abs(f - c) <= 3 for c in cuts):
                cuts.add(f)                      # planned but not detected: look at it too
        jobs = []
        for f in sorted(cuts):
            fr = [x for x in range(f - a.around, f + a.around) if 0 <= x < nframes]
            jobs.append((f"cut_f{f:05d}.jpg", fr, f, f"cut at f{f} ({f / fps:.3f} s): f{fr[0]}-f{fr[-1]}"))
        for x in J.get("flags") or []:
            f0, f1 = int(x["f0"]), int(x["f1"])
            if f1 - f0 > 2 * fps:
                continue
            fr = [y for y in range(f0 - 2, f1 + 3) if 0 <= y < nframes]
            if len(fr) > 24:
                step = len(fr) / 24
                fr = sorted({fr[int(i * step)] for i in range(24)})
            jobs.append((f"flag_f{f0:05d}-f{f1:05d}.jpg", fr, f0,
                         f"{x['sev']} {x['kind']} f{f0}-f{f1}: {x['what']}"[:150]))
        if jobs:
            with tempfile.TemporaryDirectory() as tmp:
                got = exact_frames(a.video, [y for _, fr, _, _ in jobs for y in fr], 480, tmp)
                for name, fr, mark, title in jobs:
                    ims = []
                    for y in fr:
                        if y not in got:
                            continue
                        im = label(Image.open(got[y]).convert("RGB"), f"f{y}  {y / fps:.3f}s", 16)
                        if y == mark:
                            ImageDraw.Draw(im).rectangle((0, 0, im.width - 1, im.height - 1), outline=(255, 60, 60),
                                                         width=4)
                        ims.append(im)
                    if ims:
                        written.append(tile(ims, min(len(ims), 8), os.path.join(a.out, name), title))

    for p in written:
        print(p)
    print(f"frames: {len(written)} sheet(s) in {a.out}")


if __name__ == "__main__":
    main()
