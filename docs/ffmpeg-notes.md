# ffmpeg notes: the audio-mix stall (2026-11-07)

## Short version

There are two different freezes. Only one of them is about stdin.

1. **The 100% CPU freeze is a bug in ffmpeg, not a stdin problem.** It happens when a filter graph has an
   unbounded `apad` (pads silence forever) followed by `atrim`. Sometimes ffmpeg spins forever making silence
   and throwing it away. `-nostdin` does **not** fix it. The fix is to give `apad` an end:
   `apad=whole_dur=<seconds>`. The output stays byte-identical.
2. **The 0% CPU freeze is the stdin/terminal problem.** When ffmpeg runs as a background job on a terminal
   (`ffmpeg ... &` in Terminal) without `-nostdin`, macOS stops it the moment it touches the terminal (state `T`,
   0% CPU). `-nostdin` fixes this one completely.

So use both: `-nostdin` on every ffmpeg call, **and** a bounded `apad` in every mix.

## What was tested

Standalone repro with synthetic inputs (testsrc2 + sine, 80 s source, 9.2 s reel, mp3 music bed), in a
`mkdtemp()` folder. It uses the same graph as `render_reel_dr` with `audio_xfade: 0.5`: two game-audio segments
`aresample,afade,afade,adelay` -> `amix duration=longest` -> `apad,atrim` -> music `amix duration=first` -> 2-pass
`loudnorm` (measure pass to `-f null`, final pass muxed with `-c:v copy`). Each pass had a 15 s timeout (a good run
takes under 1 s). ffmpeg: `/usr/local/bin/ffmpeg` N-125328-g8512161c812 (evermeet nightly).

| Condition (stdin of ffmpeg) | Runs (passes) | Hung |
|---|---|---|
| inherited (`/dev/null` here), 4 at a time | 120 | 36 (30%) |
| inherited, one at a time | 120 | 27 (23%) |
| `-nostdin`, 4 at a time | 120 | 18 (15%) |
| `-nostdin`, one at a time | 120 | 13 (11%) |
| `stdin=/dev/null` | 120 | 34 (28%) |
| stdin = open pipe nobody writes to | 120 | 29 (24%) |
| backgrounded job of a non-interactive shell | 120 | 23 (19%) |
| **`apad=whole_dur=<dur>,atrim=0:<dur>`** (inherited stdin, 4 at a time and one at a time, plus `-nostdin`) | **540** | **0** |
| `atrim` only, no `apad` (just to locate the bug) | 120 | 0 |

Both passes hang (measure and final), so it is not the muxer or `-c:v copy`.
Earlier tests (render_reel, 0 hangs in 12 with `-nostdin`) were just too few runs to see it.

**Evidence from the hung processes (all 181 hung runs were sampled):** `ps` shows `Rs ~100% CPU`. `sample <pid> 3` shows
the filter thread (`fc0`) always busy in `av_samples_set_silence` plus `av_malloc`/`free`. That is `apad` making
silent frames. Memory stays flat (about 65 MB), so the frames are made and thrown away without end. The other
threads are idle (`tq_receive`/`tq_send`). The encoder sits waiting for audio, and one decoder waits for the
filter thread to take its data. Stack frames above the leaf are lost under Rosetta, so the exact upstream function
is not shown.

**The 0% CPU case, reproduced:** inside a pty with job control (`script` + `set -m`), a background
`ffmpeg ... &` without `-nostdin` was in state `T` (stopped, 0.0% CPU) after 3 s and never finished. The same command
with `-nostdin` finished normally.

## Other ffmpeg builds on this Mac

- No Homebrew ffmpeg is installed (`/opt/homebrew/bin` has none). Homebrew is installed, and its stable formula is
  ffmpeg 9.0.2 (native Apple silicon).
- All ffmpeg binaries found on the test Mac were Intel builds running under Rosetta; only the evermeet
  nightly in `/usr/local/bin` was tested.
- Not checked: the ffmpeg-static inside Claude's app folder (excluded on purpose).

## Root cause

A livelock in this nightly's filter graph. An endless `apad` feeds `atrim`, and sometimes ffmpeg keeps pulling
silence from `apad` instead of the input it is actually waiting for. Whether this is a regression only in the
nightly, or also in released ffmpeg, is **not known**: no other build was tested.
stdin plays no part in the 100% CPU stall. It does cause the separate 0% CPU stop of background jobs on a terminal.

## Recommendation

1. **Bound every `apad`** (this is the real fix, output byte-identical):
   `apad,atrim=0:D` -> `apad=whole_dur=D,atrim=0:D` (or `whole_dur=D+1`, as render_reel now does).
   This was checked byte-for-byte here: same loudnorm measure JSON, same output file md5, same framemd5.
   - Check every filter graph that pads audio (`apad`) in your own render scripts; give each one `whole_dur`.
2. **Keep `-nostdin`** (and `stdin=subprocess.DEVNULL`) on every ffmpeg/ffprobe call. It stops the 0% CPU freeze
   for background and terminal jobs, and a stray `q` on stdin can no longer end an encode early.
3. **Add a watchdog** for long jobs: a subprocess timeout that is sized to the job, or killing ffmpeg when its
   `-progress` output stops moving for about 60 s. Then a future ffmpeg bug fails loudly instead of hanging overnight.
4. **Optional: switch to a stable, native build.** Run in Terminal:
   `brew install ffmpeg`
   Then make sure `/opt/homebrew/bin` comes before `/usr/local/bin` in PATH (`which ffmpeg` should print
   `/opt/homebrew/bin/ffmpeg`). Do not delete the evermeet copy until the diff tests pass on the new build: a new
   ffmpeg version can change encoder output bytes. Re-run the stall repro on it before relying on it. This step alone
   is not proven to fix the stall, so do steps 1-3 regardless.

The repro script used for this was `stall_repro.py`/`stall_variant.py` in the session scratchpad (not in the repo).
Usage: `stall_repro.py <dir> <runs> inherit|nostdin|devnull|pipe|bgshell [parallel] [meas|final|both]`.
