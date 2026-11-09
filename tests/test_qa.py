#!/usr/bin/env python3
"""Self-test for engine/qa.py (the video-gates QA run). Renders short synthetic clips with planted faults and checks
that each one is caught, and that a clean clip passes.
Run:  python3 tests/test_qa.py
Needs: python3, numpy, pillow, ffmpeg (libx264, aac, scdet, ebur128). Writes into tests/out/gates/."""
import json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
QA = [sys.executable, os.path.join(REPO, "engine", "qa.py")]
os.dup2(os.open(os.devnull, os.O_RDONLY), 0)   # every child (ffmpeg, qa.py) reads /dev/null: no stdin stalls
OUT = os.path.join(HERE, "out", "gates"); os.makedirs(OUT, exist_ok=True)
GENERIC = os.path.join(REPO, "profiles", "_template", "profile.json")   # generic delivery spec, no org values
R = "30000/1001"
S = "1920x1080"
FIX = re.compile(r"^f\d+-f\d+ \(\d\d:\d\d\.\d\) - .+ - .+ - .+$")


def shot(d, look="", src="testsrc2"):
    return f"{src}=s={S}:r={R}:d={d}" + (f",{look}" if look else "")


def render(name, video, audio, extra_v="", extra_a=""):
    """video: list of lavfi sources concatenated, or a whole filtergraph string ending in [v]; audio: one source."""
    out = os.path.join(OUT, name + ".mp4")
    if isinstance(video, str):
        vchain = video
    else:
        parts = [f"{v}[v{i}]" for i, v in enumerate(video)]
        vchain = ";".join(parts) + ";" + "".join(f"[v{i}]" for i in range(len(video))) + \
            f"concat=n={len(video)}:v=1:a=0" + (f",{extra_v}" if extra_v else "") + "[v]"
    achain = audio + (f",{extra_a}" if extra_a else "") + "[a]"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-filter_complex", vchain + ";" + achain, "-map", "[v]",
                    "-map", "[a]", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "192k", "-shortest", out], check=True)
    return out


def tone(d, gain=-11):
    # lavfi sine is at 1/8 full scale (-18 dBFS); a 1 kHz sine at -11 dBFS peak measures -14 LUFS
    return f"sine=f=1000:r=48000:d={d},volume={gain + 18}dB"


def qa(path, *args, profile=GENERIC):
    name = os.path.splitext(os.path.basename(path))[0]
    out = os.path.join(OUT, "review_" + name)
    r = subprocess.run(QA + [path, "--profile", profile, "--out", out, *args], capture_output=True, text=True)
    j = None
    if os.path.isfile(os.path.join(out, "qa.json")):
        with open(os.path.join(out, "qa.json")) as fh:
            j = json.load(fh)
    return r.returncode, j, r.stdout + r.stderr, out


ok = True


def expect(label, cond, info=""):
    global ok
    print(("PASS " if cond else "FAIL ") + label + ("" if cond else f"\n     {info[-1500:]}"))
    ok &= bool(cond)


def flagged(j, kind, t0=None, t1=None, tol=0.15):
    for x in (j or {}).get("flags", []):
        if x["kind"] == kind and x["sev"] == "FAIL":
            if t0 is None or (x["t0"] <= t1 + tol and x["t1"] >= t0 - tol):
                return True
    return False


B = dict(src="testsrc")                                 # a different test pattern = a different shot
C = dict(look="crop=iw/3:ih/3:0:ih/2,scale=1920:1080")  # a zoomed-in part of the first pattern
BASE = [shot(1.5), shot(3.5, **B)]          # planned hard cut at 1.5 s, moving throughout
clean = render("clean", BASE, tone(5))
rc, j, log, out = qa(clean, "--cuts", "1.5")
expect("clean clip (moving, -14 LUFS, planned cut listed) passes", rc == 0, log)
expect("clean clip writes review.md, sheet.jpg, qa.json",
       all(os.path.isfile(os.path.join(out, f)) for f in ("review.md", "sheet.jpg", "qa.json")))
expect("clean clip loudness reads -14 +-1", j and abs(j["loudness"]["I"] + 14) <= 1, log)
expect("clean clip: the planned cut is found", j and any(c["planned"] for c in j["cuts"]), log)

clip = render("flash", BASE, tone(5), extra_v="drawbox=x=0:y=0:w=iw:h=ih:color=white:t=fill:enable='eq(n,100)'")
rc, j, log, out = qa(clip, "--cuts", "1.5")
expect("1-frame white flash is caught", rc == 1 and flagged(j, "flash", 100 / 29.97, 101 / 29.97), log)
with open(os.path.join(out, "review.md")) as fh:
    lines = [ln.split("** ", 1)[1] for ln in fh.read().splitlines() if ln.startswith("- **FAIL**")]
expect("fix lines use f<start>-f<end> (mm:ss.s) - what - why - fix", lines and all(FIX.match(x) for x in lines),
       "\n".join(lines))

clip = render("glitch", BASE, tone(5), extra_v="split[x][y];[y]hflip,vflip[z];[x][z]overlay=enable='eq(n,110)'")
rc, j, log, _ = qa(clip, "--cuts", "1.5")
expect("single foreign frame is caught", rc == 1 and (flagged(j, "glitch", 3.67, 3.7) or flagged(j, "flash", 3.67, 3.7))
       and not flagged(j, "unplanned_cut"), log)

clip = render("click", BASE, tone(5), extra_a="aeval='val(0)+if(eq(n\\,105600)\\,0.6\\,0)':c=same")
rc, j, log, _ = qa(clip, "--cuts", "1.5")
expect("audio click is caught", rc == 1 and flagged(j, "click", 2.2, 2.2), log)

clip = render("dropout", BASE, tone(5), extra_a="volume=volume=0:enable='between(t,3.0,3.6)'")
rc, j, log, _ = qa(clip, "--cuts", "1.5")
drop = [x for x in (j or {}).get("flags", []) if x["kind"] == "dropout"]
expect("0.6 s dropout is caught", rc == 1 and drop and abs(drop[0].get("dur", 0) - 0.6) < 0.08, log)

clip = render("quiet", BASE, tone(5, gain=-17))
rc, j, log, _ = qa(clip, "--cuts", "1.5")
expect("loudness 6 LU too low is caught", rc == 1 and flagged(j, "loudness") and j["loudness"]["I"] < -19, log)

clip = render("jump", [shot(1.5), shot(1.8, **B), shot(1.7, **C)], tone(5))
rc, j, log, _ = qa(clip, "--cuts", "1.5")
expect("unplanned hard cut is caught", rc == 1 and flagged(j, "unplanned_cut", 3.3, 3.3), log)
rc, j, log, _ = qa(clip, "--cuts", "1.5,3.3")
expect("the same cut passes once it is planned", rc == 0, log)
# --shotlist <_parts/list.txt>: cuts = running sum of the concat parts (as render_reel/vreel write them)
pdir = os.path.join(OUT, "jump_parts"); os.makedirs(pdir, exist_ok=True)
for n, (dur, kw) in enumerate([(1.5, {}), (1.8, B), (1.7, C)]):
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=s=320x180:r=30000/1001:d={dur}",
                    "-c:v", "libx264", os.path.join(pdir, f"p{n}.mp4")], check=True, stdin=subprocess.DEVNULL)
lst = os.path.join(pdir, "list.txt")
open(lst, "w").write("".join(f"file '{pdir}/p{n}.mp4'\n" for n in range(3)))
rc, j, log, _ = qa(clip, "--shotlist", lst)
expect("--shotlist <_parts/list.txt>: cuts read from the concat parts (1.5, 3.3) and the clip passes", rc == 0, log)
ej = os.path.join(pdir, "edit.json"); json.dump({"items": [{"in": 0, "out": 1}]}, open(ej, "w"))
rc, j, log, _ = qa(clip, "--shotlist", ej)
expect("--shotlist <edit list with items>: clear message pointing at _parts/list.txt", rc != 0 and "list.txt" in log, log)

clip = render("tail", [shot(1.5), shot(2.5, **B)], tone(7), extra_v="tpad=stop_mode=clone:stop_duration=3")
rc, j, log, _ = qa(clip, "--cuts", "1.5", "--holds", "end:3")
expect("3 s static end tail is caught (even when declared as a hold)", rc == 1 and flagged(j, "end_tail", 4.0, 7.0),
       log)

clip = render("deadhead", [shot(0.5) + ",tpad=start_mode=clone:start_duration=1", shot(3.5, **B)],
              tone(5))
rc, j, log, _ = qa(clip, "--cuts", "1.5")
expect("nothing moving in the first second is caught", rc == 1 and flagged(j, "hook_motion", 0, 1.0), log)

# explainer freshness (E6): a box drifting with nothing new for 5 s fails; new elements every second pass
bg = "color=c=0x303030:s=1280x720:r=30000/1001:d=5"
box = "color=c=0xE0E0E0:s=120x120:r=30000/1001:d=5"
drift = f"{bg}[bg];{box}[box];[bg][box]overlay=x='100+t*80':y=300:shortest=1"
news = ",".join(f"drawbox=x={200 + 220 * k}:y=520:w=160:h=100:color=0x{c}:t=fill:enable='gte(t,{0.8 + k:.1f})'"
                for k, c in enumerate(("C04040", "40C040", "4060D0", "D0A040")))
stale = render("explainer_stale", drift + "[v]", tone(5))
rc, j, log, _ = qa(stale, "--kind", "explainer", "--size", "1280x720", "--cuts", "none")
expect("explainer: 5 s with no new visual fails freshness", rc == 1 and flagged(j, "freshness"), log)
fresh = render("explainer_fresh", drift + "," + news + "[v]", tone(5))
rc, j, log, _ = qa(fresh, "--kind", "explainer", "--size", "1280x720", "--cuts", "none")
g = next((x for x in (j or {}).get("gates", []) if x["gate"].startswith("freshness")), {})
expect("explainer: a new element every second passes freshness", g.get("result") == "PASS", log)
expect("explainer: one-frame pop-ons are warned", any(x["kind"] == "pop" for x in (j or {}).get("flags", [])), log)
# a small state change (a readout-sized patch changing once a second, too small for the colour histogram) counts too
ticks = ",".join(f"drawbox=x=900:y=120:w=90:h=50:color=0x{c}:t=fill:enable='gte(t,{0.8 + k:.1f})'"
                 for k, c in enumerate(("E0E0E0", "40A040", "E0E0E0", "40A040")))
small = render("explainer_small", drift + "," + ticks + "[v]", tone(5))
rc, j, log, _ = qa(small, "--kind", "explainer", "--size", "1280x720", "--cuts", "none")
g = next((x for x in (j or {}).get("gates", []) if x["gate"].startswith("freshness")), {})
expect("explainer: a small readout changing every second passes freshness (local state change)",
       g.get("result") == "PASS", log)
blink = render("explainer_blink", drift + ",drawbox=x=900:y=120:w=90:h=50:color=0xE0E0E0:t=fill:enable='lt(mod(t,0.6),0.3)'[v]", tone(5))
rc, j, log, _ = qa(blink, "--kind", "explainer", "--size", "1280x720", "--cuts", "none")
g = next((x for x in (j or {}).get("gates", []) if x["gate"].startswith("freshness")), {})
expect("explainer: a blinking patch (no new state) still fails freshness", g.get("result") == "FAIL", log)

# 29.97 material in a 59.94 file repeats every other frame: one cadence note, not dozens of stutters
c60 = render("cadence_59", [f"testsrc2=s={S}:r={R}:d=4,fps=60000/1001"], tone(4))
rc, j, log, _ = qa(c60, "--cuts", "none", "--fps", "59.94")
g = next((x for x in (j or {}).get("gates", []) if x["gate"].startswith("motion")), {})
expect("29.97 material in 59.94: motion gate passes with a cadence note, no stutter flags",
       g.get("result") == "PASS" and "regular cadence" in g.get("measured", "") and not flagged(j, "stutter"), log)
expect("29.97 material in 59.94 (a multiple of the profile's 29.97 delivery): no cadence warning",
       g.get("result") == "PASS" and not any(x["kind"] == "cadence" for x in (j or {}).get("flags", [])), log)

# fix (2026-11-07): a cadence in a file AT the delivery rate is lower-rate material conformed by repeating frames
# (25p in a 29.97 file: a repeat about every 6 frames), which judders: WARN (not FAIL, not a silent PASS)
def cadence_warn(j):
    return [x for x in (j or {}).get("flags", []) if x["kind"] == "cadence" and x["sev"] == "WARN"]


c25 = render("cadence_25in2997", [f"testsrc2=s={S}:r=25:d=1.5,fps={R}", f"testsrc=s={S}:r=25:d=3.5,fps={R}"], tone(5))
rc, j, log, _ = qa(c25, "--cuts", "1.5")
g = next((x for x in (j or {}).get("gates", []) if x["gate"].startswith("motion")), {})
cw = cadence_warn(j)
expect("25p material in a 29.97 file (delivery 29.97): motion gate WARN, one cadence WARN flag, no FAIL, exit 0",
       rc == 0 and g.get("result") == "WARN" and len(cw) == 1 and not flagged(j, "stutter")
       and not any(x["sev"] == "FAIL" for x in j["flags"]), log)
expect("25p in 29.97: the cadence warning is a fix line naming the material rate and the conform",
       bool(cw) and FIX.match(j["fix_lines"][[x["kind"] for x in j["flags"]].index("cadence")]) is not None
       and "24.98 fps material" in cw[0]["what"] and "conform" in cw[0]["fix"], log)
# a multiple of the delivery rate that is NOT delivery-rate material (25p in a 59.94 file) still judders: WARN
c25x = render("cadence_25in5994", [f"testsrc2=s={S}:r=25:d=1.5,fps=60000/1001", f"testsrc=s={S}:r=25:d=3.5,fps=60000/1001"],
              tone(5))
rc, j, log, _ = qa(c25x, "--cuts", "1.5", "--fps", "59.94")
g = next((x for x in (j or {}).get("gates", []) if x["gate"].startswith("motion")), {})
expect("25p material in a 59.94 file (delivery 29.97): motion gate WARN with a cadence WARN flag, exit 0",
       rc == 0 and g.get("result") == "WARN" and len(cadence_warn(j)) == 1, log)

# a quick fade into digital silence (and back) at a planned cut is a fade, not a hard audio cut
fade = render("fade_silence", BASE, "sine=f=1000:r=48000:d=5,volume=12dB,aeval='val(0)*if(lt(t\\,1.46)\\,1\\,"
              "if(lt(t\\,1.5)\\,(1.5-t)/0.04\\,if(lt(t\\,2)\\,0\\,if(lt(t\\,2.04)\\,(t-2)/0.04\\,1))))':c=same")
rc, j, log, _ = qa(fade, "--cuts", "1.5", "--silences", "1.5-2.04")
g = next((x for x in (j or {}).get("gates", []) if x["gate"].startswith("hard audio")), {})
expect("40 ms fade into digital silence at a cut passes the hard-audio-cut gate", g.get("result") == "PASS"
       and not flagged(j, "audio_hard"), log)

# review case: a hard cut from REAL music into silence (and back) at a planned cut is a hard audio cut, however
# much the music's own level moves around; the same edit with 40 ms fades passes. (any real music track, set
# QA_TEST_MUSIC=<file>)
music = os.environ.get("QA_TEST_MUSIC", "")
if music and os.path.isfile(music):
    import numpy as np, wave
    raw = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-ss", "30", "-t", "60", "-i", music, "-ac", "1", "-ar",
                          "48000", "-f", "s16le", "-"], capture_output=True).stdout
    x = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    st = int(np.random.default_rng(16).integers(0, len(x) - 96000))
    for name, L in (("music_hardcut", 0), ("music_fade40", 1920)):
        a, b = x[st:st + 72000].copy(), x[st + 96000:st + 144000].copy()
        if L:
            a[-L:] *= np.linspace(1, 0, L); b[:L] *= np.linspace(0, 1, L)
        y = np.concatenate([a, np.zeros(24000, np.float32), b])
        wav = os.path.join(OUT, name + ".wav")
        with wave.open(wav, "w") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(48000)
            w.writeframes((np.clip(y, -1, 1) * 32767).astype(np.int16).tobytes())
        clip = render(name, [shot(1.5), shot(1.5, src="testsrc")], "amovie=filename='" + wav.replace("'", "\\'") + "'")
        rc, j, log, _ = qa(clip, "--cuts", "1.5,2.0", "--silences", "1.5-2.0")
        g = next((x_ for x_ in (j or {}).get("gates", []) if x_["gate"].startswith("hard audio")), {})
        if L:
            expect("40 ms fades from real music into silence and back pass the hard-audio-cut gate",
                   g.get("result") == "PASS" and not flagged(j, "audio_hard"), log)
        else:
            expect("hard cut from real music into silence (and a hard cut-in) fails the hard-audio-cut gate",
                   g.get("result") == "FAIL" and flagged(j, "audio_hard"), log)
else:
    print("SKIP real-music audio cases (set QA_TEST_MUSIC to a music file)")

# no audio stream: the audio gate is skipped cleanly (audio_check would report NO AUDIO)
mute = os.path.join(OUT, "no_audio.mp4")
subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i", shot(3), "-c:v", "libx264", "-preset",
                "ultrafast", "-pix_fmt", "yuv420p", mute], check=True, stdin=subprocess.DEVNULL)
rc, j, log, _ = qa(mute, "--cuts", "none")
expect("file with no audio: runs, audio gate SKIP, no crash", rc in (0, 1) and j and any(
    x["gate"] == "audio" and x["result"] == "SKIP" for x in j["gates"]), log)

bad = os.path.join(OUT, "not_a_video.mp4")
with open(bad, "w") as fh:
    fh.write("this is not a video\n")
rc, j, log, _ = qa(bad)
expect("unreadable file exits 2", rc == 2, log)

# ---- fixes 2026-11-07 (gaps found while updating the skills) ---------------------------------------------------
import tempfile


def gate_row(j, prefix):
    return next((x for x in (j or {}).get("gates", []) if x["gate"].startswith(prefix)), {})


def sev_of(j, kind):
    return [x["sev"] for x in (j or {}).get("flags", []) if x["kind"] == kind]


# 1. a concat list written by another shell (absolute /sessions/<id>/mnt/... paths): parts are found next to the list
jump = render("jump_stale", [shot(1.5), shot(1.8, **B), shot(1.7, **C)], tone(5))
sdir = os.path.join(OUT, "stale_parts"); os.makedirs(sdir, exist_ok=True)
for n, dur in enumerate((1.5, 1.8, 1.7)):
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=s=320x180:r={R}:d={dur}",
                    "-c:v", "libx264", os.path.join(sdir, f"p{n}.mp4")], check=True, stdin=subprocess.DEVNULL)
stale = os.path.join(sdir, "list.txt")
other = "/sessions/zz-no-such-session/mnt/ORG/02 Clips/Highlights/_parts"
open(stale, "w").write("".join(f"file '{other}/p{n}.mp4'\n" for n in range(3)))
rc, j, log, out = qa(jump, "--shotlist", stale)
expect("--shotlist list.txt from another shell: parts found next to the list, cuts 1.5/3.3, clip passes, said once",
       rc == 0 and j and len(j.get("planned_cuts") or []) == 2
       and all(abs(x - y) < 0.02 for x, y in zip(j["planned_cuts"], (1.5, 3.3))) and log.count("next to the list") == 1
       and "next to the list" in open(os.path.join(out, "review.md")).read(), log)
gone = os.path.join(sdir, "list_gone.txt")
open(gone, "w").write(f"file '{other}/p9.mp4'\nfile '{other}/p1.mp4'\n")
rc, j, log, _ = qa(jump, "--shotlist", gone)
expect("--shotlist: a part missing both as listed and next to the list stops and names both paths",
       rc != 0 and f"{other}/p9.mp4" in log and os.path.join(sdir, "p9.mp4") in log, log)

# 2. delivery.fps_allowed: a profile that also delivers 59.94 (29.97 material shown at 2x) passes 59.94 files
ptmp = tempfile.mkdtemp(prefix="qa_prof_")
gen = json.load(open(GENERIC)); gen["name"] = "allow5994"; gen["delivery"]["fps_allowed"] = [59.94005994]
json.dump(gen, open(os.path.join(ptmp, "profile.json"), "w"))
c60b = render("cadence_59b", [f"testsrc2=s={S}:r={R}:d=4,fps=60000/1001"], tone(4))
rc, j, log, _ = qa(c60b, "--cuts", "none", profile=ptmp)
expect("delivery.fps_allowed [59.94]: a 59.94 file passes spec without --fps",
       gate_row(j, "integrity").get("result") == "PASS" and not sev_of(j, "spec_fps"), log)
rc, j, log, _ = qa(c60b, "--cuts", "none")
expect("profile without fps_allowed: a 59.94 file still FAILs spec_fps (default unchanged)",
       rc == 1 and flagged(j, "spec_fps"), log)
rc, j, log, _ = qa(c60b, "--cuts", "none", "--fps", "29.97", profile=ptmp)
expect("--fps overrides fps_allowed: --fps 29.97 on a 59.94 file FAILs spec_fps", rc == 1 and flagged(j, "spec_fps"), log)

# 3. avg_frame_rate a hair under a declared constant r_frame_rate (timestamp gaps): spec on r_frame_rate + WARN
def dropped(name, k):
    out = os.path.join(OUT, name + ".mp4")
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=s={S}:r=60000/1001:d=4",
                    "-f", "lavfi", "-i", tone(4), "-vf", f"select='not(between(n\\,120\\,{119 + k}))'",
                    "-fps_mode", "passthrough", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-shortest", out], check=True, stdin=subprocess.DEVNULL)
    return out


d1 = dropped("gap_1frame", 1)    # 239 frames in 4 s: avg 59.69 (-0.4%), r 60000/1001
rc, j, log, _ = qa(d1, "--cuts", "none", "--fps", "59.94")
w = [x for x in (j or {}).get("flags", []) if x["kind"] == "spec_fps"]
expect("avg 59.69 in a file flagged 60000/1001: spec judged on r_frame_rate, the average shown as a WARN",
       j and not flagged(j, "spec_fps") and [x["sev"] for x in w] == ["WARN"] and "average frame rate 59.6" in w[0]["what"]
       and gate_row(j, "integrity").get("result") == "WARN", log)
d3 = dropped("gap_3frames", 3)   # 237 frames: avg 59.19 (-1.25%): a real rate problem, still a FAIL
rc, j, log, _ = qa(d3, "--cuts", "none", "--fps", "59.94")
expect("avg 1.25% under r_frame_rate: still a spec_fps FAIL", rc == 1 and flagged(j, "spec_fps"), log)

# 4. --kind loop: a gentle loop (no strong moment) is not hook-gated; the motion gates still run
drift_only = render("loop_drift", f"{bg}[bg];{box}[box];[bg][box]overlay=x='100+t*80':y=300:shortest=1[v]", tone(5))
rc, j, log, _ = qa(drift_only, "--kind", "motion", "--size", "1280x720", "--cuts", "none")
expect("--kind motion on a gentle loop: hook 'strong moment' FAILs (default unchanged)",
       rc == 1 and flagged(j, "hook_strong"), log)
rc, j, log, _ = qa(drift_only, "--kind", "loop", "--size", "1280x720", "--cuts", "none")
expect("--kind loop: hook and end-tail gates listed as SKIP (with their measurement), no FAIL, exit 0",
       rc == 0 and gate_row(j, "hook: strong").get("result") == "SKIP"
       and gate_row(j, "hook: motion").get("result") == "SKIP" and gate_row(j, "end card").get("result") == "SKIP"
       and "biggest move" in gate_row(j, "hook: strong").get("measured", "")
       and gate_row(j, "motion (motion_check --strict").get("result") == "PASS", log)
frozen = render("loop_frozen", [shot(1.0) + ",tpad=stop_mode=clone:stop_duration=2", shot(2.0, **B)], tone(5))
rc, j, log, _ = qa(frozen, "--kind", "loop", "--cuts", "1.0")
expect("--kind loop still FAILs a 2 s freeze mid-loop (motion gates still apply)", rc == 1 and
       (flagged(j, "dead") or flagged(j, "hold_life")), log)

# 5. --intended end_tail,hook: a designed hold or weak hook becomes an INFO line, never a silent PASS
tailc = render("tail_intended", [shot(1.5), shot(2.5, **B)], tone(7), extra_v="tpad=stop_mode=clone:stop_duration=3")
rc, j, log, out = qa(tailc, "--cuts", "1.5", "--holds", "end:3", "--intended", "end_tail")
g = gate_row(j, "end card")
expect("--intended end_tail: the 3 s tail is an INFO line 'declared intended', gate INFO (not PASS), exit 0",
       rc == 0 and sev_of(j, "end_tail") == ["INFO"] and g.get("result") == "INFO"
       and "declared intended" in g.get("target", "") and "declared intended" in j["verdict"]
       and "**INFO**" in open(os.path.join(out, "review.md")).read(), log)
rc, j, log, _ = qa(drift_only, "--kind", "motion", "--size", "1280x720", "--cuts", "none", "--intended", "hook")
expect("--intended hook: the weak-hook FAIL becomes INFO, exit 0", rc == 0 and sev_of(j, "hook_strong") == ["INFO"]
       and gate_row(j, "hook: strong").get("result") == "INFO", log)
rc, j, log, _ = qa(tailc, "--cuts", "1.5", "--intended", "hook")
expect("--intended hook does not cover the end tail: still a FAIL", rc == 1 and flagged(j, "end_tail"), log)
rc, j, log, _ = qa(tailc, "--cuts", "1.5", "--intended", "stutter")
expect("--intended with a gate that has its own flag (stutter) stops with a clear message",
       rc != 0 and "choose from" in log, log)
expect("--intended with an unknown name is a usage error: exit 2 (not 1, which means a QA FAIL)", rc == 2, log)
# review 2026-11-07: delivery.fps_allowed written as one number (no list) still works; garbage is a clear exit 2
gen["name"] = "allow5994_scalar"; gen["delivery"]["fps_allowed"] = 59.94005994
json.dump(gen, open(os.path.join(ptmp, "profile.json"), "w"))
rc, j, log, _ = qa(c60b, "--cuts", "none", profile=ptmp)
expect("delivery.fps_allowed as a bare number (59.94): a 59.94 file passes spec, no crash",
       gate_row(j, "integrity").get("result") == "PASS" and not sev_of(j, "spec_fps") and "Traceback" not in log, log)
gen["delivery"]["fps_allowed"] = ["fast"]; json.dump(gen, open(os.path.join(ptmp, "profile.json"), "w"))
rc, j, log, _ = qa(c60b, "--cuts", "none", profile=ptmp)
expect("delivery.fps_allowed not a list of rates: exit 2 with a message naming the key, no traceback",
       rc == 2 and "delivery.fps_allowed should be a list" in log and "Traceback" not in log, log)

# concat lists whose folder has a ' in it (e.g. "Al's Shop").
# Render scripts that build concat lists write the ' as '\'' (the concat demuxer's quoting); lists written before that
# have it unescaped. qa's --shotlist reader takes both, and finds the parts next to the list when the listed folder
# (with its ') is gone.
sys.path.insert(0, os.path.join(REPO, "engine"))
import qa as _qa  # noqa: E402
import shutil as _sh2, tempfile as _tf2  # noqa: E402
aq = os.path.join(_tf2.mkdtemp(prefix="qa_apos_"), "Al's Shop", "_parts")
os.makedirs(aq)
for n in range(3):
    _sh2.copy(os.path.join(pdir, f"p{n}.mp4"), os.path.join(aq, f"p{n}.mp4"))
want = _qa.concat_list_cuts(lst)   # the plain list of the same parts (pdir, no ')
for tag, body in [("escaped '\\''", "".join("file '" + f"{aq}/p{n}.mp4".replace("'", "'\\''") + "'\n" for n in range(3))),
                  ("older unescaped", "".join(f"file '{aq}/p{n}.mp4'\n" for n in range(3))),
                  ("escaped, listed folder gone (parts next to the list)",
                   "".join("file '" + f"/sessions/zz/Al's Shop/p{n}.mp4".replace("'", "'\\''") + "'\n" for n in range(3)))]:
    lp_ = os.path.join(aq, "list.txt"); open(lp_, "w").write(body)
    try:
        got = _qa.concat_list_cuts(lp_)
    except SystemExit as e:
        got = f"SystemExit: {e}"
    expect(f"concat list in a folder with a ' ({tag}): same cuts as the plain list {want}", got == want and len(want) == 2,
           f"got {got}")

print("\nALL TESTS PASSED" if ok else "\nSOME TESTS FAILED")
sys.exit(0 if ok else 1)
