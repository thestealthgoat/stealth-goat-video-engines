---
name: video
description: Front door for any video request on the local open-source video engine. Routes the job to the right engine tool or skill - talking-head edits that cut pauses and fillers (talkedit.py), kinetic captions (captions.py), cuts snapped to the beat (beatsnap.py, beatmap.py), hype edits with flash cuts, whips, speed ramps and zoom punches (fxpack.py), bouncing-word verse or lyric videos (hopwords.py), After Effects handoffs (statcard.py --ae), delivery masters (encode.py), 9:16 versions (vertical.py), contact sheets (sheet.py), Premiere XML (fcp7xml.py) - or to the explain, matte, motion-graphics, logo, cutout and QA skills. Use when the user says "edit this video", "cut the pauses", "tighten this talk", "caption this", "add subtitles", "cut this to the beat", "make a hype edit", "bouncing words lyric video", "make a vertical for Reels", "export for Premiere", "After Effects version", "encode the master", "contact sheet", or gives any video job without naming a tool.
---

# Video front door

Take any video request, pick the tool or skill that does it, run it on the user's engine and brand profile, check the
result, deliver. Tool details and file formats are in [references/tools.md](references/tools.md) and
[references/formats.md](references/formats.md); read the section for a tool before changing its defaults.

## 0. Find the engine and the profile

- Use `$VIDEO_ENGINE` as the engine folder (a clone of https://github.com/thestealthgoat/stealth-goat-video-engines)
  and run every command from it: `cd "$VIDEO_ENGINE" && python3 engine/<tool>.py ...`. If `$VIDEO_ENGINE` is unset or
  the folder has no `engine/vprofile.py`, ask the user where the engine is, or run the **getting-started** skill to
  clone and set it up (`./setup.sh` targets macOS with Homebrew). `./setup.sh --check` reports any missing tool or
  package (installs nothing).
- Pick the profile: `--profile <name>`, else `$VIDEO_PROFILE`, else the machine default in `local.json`. Use
  `--profile demo` to try things (the engine ships `profiles/demo`: OFL fonts and a placeholder logo). If an older
  clone has no `profiles/demo`, make it: `python3 engine/vprofile.py new demo --display "Demo" --primary "#0B3D2E"
  --accent "#F2B705" --logo <a PNG> --sample` (without a logo PNG, `vertical.py` cannot run on it). If the user has no profile, offer to make one from `profiles/_template`
  (`python3 engine/vprofile.py new <name> --primary "#112233" --accent "#E04050" --logo logo.png --sample`; keys in
  `docs/LAYOUT.md`) or hand over to **getting-started**. Give `--logo` a PNG: an `.svg` is stored as
  `brand.logo_svg`, but `vertical.py` and `statcard.py` read only `brand.logo_png` (vertical stops without it, the
  stats card drops the logo). With only an SVG, make a transparent PNG of it (the **logo-vectorize** skill writes
  one) and set `brand.logo_png` to it in the profile.
- Check the profile once per session: `python3 engine/vprofile.py show <name> --check` must end `CHECK: OK`. The
  demo profile passes on a fresh clone (its working folders are listed as optional). A profile the user made from
  `profiles/_template` may report `CHECK: missing` for folders that don't exist yet: `mkdir -p` them or edit its
  `paths`.
- Ask which file(s) to work on when it isn't clear. Work on the user's files where they are, write into a new output
  folder (`--out out/<job>` or a folder the user names).

## 1. Standing rules (every video)

- **Free and open-source tools by default.** AI tools are fine when the user wants them (an ElevenLabs voice, for
  example), but never make a fake of a real person: no cloned voice or face of someone who has not agreed to it.
- **Nothing leaves the machine** unless the user chooses a service. Transcription is local faster-whisper; person
  cutouts are local BiRefNet through rembg (model folder: `engine/models.py`, `$U2NET_HOME` or `rembg_models` in
  `local.json`, else `resources/models/rembg`, else rembg's own cache). Transcription runs offline; on a machine
  that has never fetched the whisper model, run the first command with `HF_HUB_OFFLINE=0` in front (model only).
- **Source footage is read-only.** Never write over, move or delete a source file. Tools write into `--out`; old
  outputs go to `_old/`, never deleted. Ask before any `rm`.
- **Audio fades everywhere.** Every cut, start, end and silence change fades (40 ms or more); music runs continuous
  under cuts and fades at the end. `engine/audio_check.py <video> --cuts <times>` must PASS.
- **Motion is springs.** Anything animated moves on `engine/spring.py` / `engine/spring.js` presets (`snappy`,
  `bouncy`, `slam`, `smooth`, `gentle`); opacity never overshoots. Details: `engine/README_motion.md`.
- **Look before you call it done.** Take stills first where the tool has `--frames`, and read a contact sheet
  (`engine/sheet.py`) of every cut before showing it.
- **QA every render before anyone sees it:** run the **video-gates** skill (`engine/qa.py`). Fix every real FAIL.
- **One heavy render at a time.** Never run two renders, transcriptions or mattes in parallel; don't run dependent
  commands in parallel either.
- **Deliver both** the ready-to-post file and the Premiere XML when the tool writes one, so the user can polish it.
- ffmpeg: pass `-nostdin` to every call, bound every `apad` (`apad=whole_dur=<s>`), use `-fps_mode` (not `-vsync`).
  Why `-nostdin` and a bounded `apad`: `docs/ffmpeg-notes.md`. Some ffmpeg builds lack `drawtext`/`subtitles`, so
  the tools draw text with PIL; do the same in any hand-made step.

## 2. Route the request

| The user says / gives | Do |
|---|---|
| Talking head, talk, sermon, podcast segment, interview: "cut the pauses", "tighten this", "edit this in my style" | `engine/talkedit.py` (§3.1) |
| "Caption this", "subtitles", "burned-in captions", "an .srt" | `engine/captions.py` (§3.2). Already editing with talkedit? It captions for you |
| Clips + a song: "cut this to the beat", "beat-sync" | Finished render with effects: `engine/fxpack.py` (§3.3). Premiere edit list only: `engine/beatsnap.py` then `engine/fcp7xml.py` (§3.4) |
| "Hype edit", "cinematic cut", flash cuts, whip pans, speed ramps, zoom punches, RGB split, black and white with a colour pop, kinetic text | `engine/fxpack.py` (§3.3) |
| "Where are the beats / the drop in this song?", "best 15 s of this track" | `engine/beatmap.py` (§3.4) |
| Memory verse, lyric, read-along with a character hopping word to word | `engine/hopwords.py` (§3.5) |
| "Give me an After Effects version", "editable in AE" | `engine/statcard.py ... --ae` (§3.6) for stats lower thirds; other templates have no AE export yet |
| "Encode the master", "rewrap this .ts", "copy and verify to the delivery drive" | `engine/encode.py` (§3.7) |
| "Vertical", "9:16", "Reels / TikTok / Shorts version" of a finished 16:9 | `engine/vertical.py` (§3.8). A talking head: talkedit already writes a face-cropped 9:16. Captions in 9:16: `captions.py --aspect 9:16` |
| "Show me what's in this clip", "contact sheet", before choosing in-points | `engine/sheet.py` (§3.9) |
| "Pull these moments out" from a long recording | `engine/clip_plays.py` (stream copy, no re-encode; [formats](references/formats.md#moments-list)) |
| "Premiere XML" for a finished MP4 or an edit list | `engine/fcp7xml.py` (§3.4, `--single` for one render) |
| "Copy my camera card", "offload the card safely" | `engine/offload.py <card> <dest> --profile <name>` (resumable, byte-verified; `--dry-run` first) |
| "QA this", "check before I post" | **video-gates** skill |
| Explainer: "explain how X works" | **explain** skill (worked example: `examples/explain/lissajous/`) |
| Cut a person out of a shot, text behind the speaker, new background | **matte** skill |
| Stats lower third, quote callout, progress bar, before/after, sketch-to-shot, route map, 3D card scenes | **motion-graphics** skill |
| Logo intro, end card, corner bug, stinger, word-swap lower third | **logo-motion** skill |
| 3D logo, spinning logo, GLB | **logo-3d** skill. Raster logo to clean SVG: **logo-vectorize** |
| Cut people out of photos, headshot cutouts for cards | **player-cutouts** skill (single image: `engine/cutout.py in.jpg out.png`) |
| Burst photos to a stop-motion "action pack" | **action-pack** skill if installed, else the docstring at the top of `engine/flipbook.py` |
| "Here's a video I like, break it down" | **reference-intake** skill |
| A website or app UI | the **ui-kit** plugin (**website** skill; examples `examples/sites/demo-world/site.json`, `examples/sites/demo-studio/site.json`) |
| New engine, no profile, "show me what this can do" | **getting-started** skill |
| Anything else | Build it from the shared tools here (sheet, clip_plays, fcp7xml, beatsnap, encode, qa), then propose a skill once the pattern repeats. Don't promise features the tools lack: check `--help` |

## 3. Worked examples (fresh clone, demo profile)

Replace `talk.mp4`, `song.mp3` and friends with the user's files. Every one ends with the QA step in §4.

### 3.1 Talking-head edit (talkedit)

```bash
python3 engine/talkedit.py talk.mp4 --out out/talk --profile demo --start 0 --end 90 --plan-only   # plan, fast
python3 engine/talkedit.py talk.mp4 --out out/talk --profile demo --start 0 --end 90 --qa --preview
```

Local words, then every pause over 0.40 s and every filler cut in measured quiet with a voice fade, punch-ins at the
jump cuts, spring push-ins on emphasis words, cutaway title cards, pop-up cards, captions, 16:9 + face-cropped 9:16
at the profile's loudness. Read both `qa_16x9/review.md` and `qa_9x16/review.md`, send the `preview/` files.
Re-running with the same `--out` keeps the user's edits to `talk.talkedit.json` (`"on": false` puts a pause back);
`--fresh` plans again. Fix spelling in `talk.words.json`. Style numbers: the profile's `talkedit` block, merged
over the `RECIPE` defaults near the top of `engine/talkedit.py` (every key is there; the demo profile has no
`talkedit` block and runs on them). `profiles/_template/profile.json` shows `cut`, `zoom`, `captions`, `cards` and
`music` only: to change pop-up cards add a `pops` block yourself, e.g.
`"pops": {"per_min": 3.0, "triggers": {"deadline": "DEADLINE"}}`. Outputs and gotchas:
[tools.md § talkedit](references/tools.md#talkeditpy).

`--qa` runs qa.py on both cuts with the planned cuts and holds filled in (the exact command is at the top of each
`review.md`). Judge each flag before fixing: a "hard audio cut-off" away from talkedit's cut points that is also
in the source (`python3 engine/audio_check.py talk.mp4` reports it there too) is in the recording, not the edit;
"planned cut not detected" on a small punch-in is common and is a WARN to check by eye. A FAIL at a cut point is
real: fix it.

### 3.2 Captions

```bash
python3 engine/captions.py talk.mp4 --out out/caps --profile demo                       # 16:9, transcribes
python3 engine/captions.py talk.mp4 --out out/caps --profile demo --aspect 9:16 --words-file out/caps/talk.words.json
```

Writes `talk.words.json` (fix spelling, `"key": true` picks the boxed word, `"break": true` starts a caption),
`talk.srt`, a ProRes 4444 caption layer `.mov` for Premiere and a burned-in `.mp4` (audio copied untouched). Re-run
with `--words-file` after fixing words: no new transcription. Test a range with `--start/--end`. Read the `"dropped"`
list (whisper's invented "thanks for watching" and low-confidence words). Look: the profile's `captions` block.

### 3.3 Cinematic edit to music (fxpack)

Write `out/hype/plan.json` (paths are relative to the plan file; format in
[formats.md](references/formats.md#fxpack-plan)):

```json
{"music": "../../song.mp3", "music_in": 0.0,
 "shots": [{"src": "../../clip1.mp4", "in": 3.0, "beats": 3},
           {"src": "../../clip2.mp4", "in": 1.5, "beats": 4},
           {"src": "../../clip3.mp4", "in": 0.5, "beats": 8, "hero": true}],
 "text": ["GAME", "DAY"], "fx": "auto"}
```

```bash
python3 engine/fxpack.py out/hype/plan.json --out out/hype --name hype --profile demo --plan-only    # effects list
python3 engine/fxpack.py out/hype/plan.json --out out/hype --name hype --profile demo --frames 2.0,6.1
python3 engine/fxpack.py out/hype/plan.json --out out/hype --name hype --profile demo                # vertical: --size 1080x1920
```

Look at the stills first and pick in-points on live action. Every effect needs a music event within one frame and a
measured picture reason (the H3 gate), else the render stops with exit 3 and lists it in `hype_fx.json`: fix the
plan, don't force it. Outputs `hype_fx.mp4`, `hype_fx.xml` (Premiere, a marker per effect), `hype_fx.json`,
`hype_fx_music.wav` (the levelled music the XML uses), and it prints the qa arguments
(`qa: --kind edit --cuts 1.498,3.500`): pass exactly those to qa.py (§4). qa's hook gate wants a cut or a big move
by 2.0 s (the frame nearest 2 s still counts), so keep the first shot to 2 s or less (3 beats at 120 BPM is 1.5 s;
4 beats is 2.0 s, the longest that passes) or open on a shot with a big move. Add `"bpm"` to the plan when the tempo is known: beatmap can halve a tempo it is not
sure of (it prints `LOW-CONF`), which doubles every shot's length.

### 3.4 Beat map, beat snap and Premiere XML

```bash
python3 engine/beatmap.py song.mp3 --out out/beat/beatmap.json --profile demo       # bpm, downbeats, drop, stops
python3 engine/beatmap.py song.mp3 --choose-window 15 --profile demo                # best 15 s windows
cp edit.json out/beat/edit.json                                                     # beatsnap writes in place
python3 engine/beatsnap.py out/beat/edit.json song.mp3 --open 0 --profile demo      # snaps every cut to a beat
python3 engine/fcp7xml.py out/beat/edit.json out/beat/edit.xml                      # Premiere: File > Import
```

beatsnap moves only out points: an ordinary cut by at most `--max-shift` (0.25 s), a cut into a `"big": true` item
onto a downbeat within `--down-shift` (1.0 s), the cut into the `"payoff": true` item onto the drop within
`--drop-shift` (1.5 s; else it prints the music in point that would line them up). A cut that would land inside a
music stop moves out of it even past those limits, and the printout says so (`moved out of a stop`): read it. `--open` is the length of any opener before
the first item (default 1.6 s; `0` for none). Edit list format: [formats.md](references/formats.md#edit-list).
Premiere paths are data: write the paths the editing machine sees. Any MP4 a tool made:
`python3 engine/fcp7xml.py --single out/x/render.mp4`.

### 3.5 Bouncing-word verse or lyric (hopwords)

```bash
python3 engine/hopwords.py --text "Practice makes progress, one small step at a time." --wpm 95 \
  --out out/hop --name step --profile demo --frames 1.0,2.5                         # stills first
python3 engine/hopwords.py --text "Practice makes progress, one small step at a time." --wpm 95 \
  --out out/hop --name step --profile demo                                          # -> step_hop.mp4
python3 engine/hopwords.py --text "<lyric>" --audio voice.wav --out out/hop --name lyric --profile demo --aspect 9:16
```

Word times: `--words` (a words.json), `--audio` (local faster-whisper; saved as `<name>.words.json`), `--chart`
(lyric chart), or `--wpm` (even pace). `--text` keeps the words spelled right. `--character art.png|svg` must be art
the user owns; without it a placeholder bean is drawn. `--bg none` adds an alpha `.mov`. Only put text on screen the
user may show (their own words, public-domain translations, licensed lyrics). QA with `--kind motion --cuts none`.

### 3.6 After Effects handoff (statcard --ae)

```bash
python3 engine/statcard.py docs/stats_card_example.json out/card --name card --profile demo --frames 1.5   # still
python3 engine/statcard.py docs/stats_card_example.json out/card --name card --profile demo --ae
```

Writes `card_stats_Alpha.mov` (ProRes 4444), `card_stats.mp4`, `card_stats.png` and, with `--ae`, `card_stats.jsx`
+ `card_stats_ae/`. In After Effects: File > Scripts > Run Script File, pick the `.jsx`: native text layers in the
profile fonts, every spring baked to editable keyframes. The fonts must be installed on the AE machine (the script
reports any it can't find). `engine/aejsx.py` is the library behind it (no command line): new templates use its
`Comp` class to get the same export.

### 3.7 Delivery masters (encode)

```bash
python3 engine/encode.py rewrap stream.ts --profile demo                       # stream copy into MP4, verified
python3 engine/encode.py verify out/final.mp4 --like part1.mp4 part2.mp4 --profile demo
python3 engine/encode.py master part1.mp4 part2.mp4 -o out/master.mp4 --profile demo
```

All three work on the demo profile as it is. `master` encodes with an encode preset from the profile: `--preset
<name>` reads `delivery.<name>`; without `--preset` it uses the profile's `delivery.default_preset`, else `web`. The
demo and `_template` profiles ship `delivery.web` (libx264, 12M / 14M / 24M). A profile without that preset stops
with `FATAL: no encode preset 'web': profile <p> has no delivery.web`: add one
([formats.md](references/formats.md#encode-preset)). Outputs
are written as `.partial.mp4` and renamed on success; an existing output is never replaced without `--force`. Wait
on the log lines `=== DONE` / `=== FAILED`.

### 3.8 Vertical version of a finished 16:9

```bash
python3 engine/vertical.py out/promo.mp4 out/promo_9x16.mp4 --profile demo --kicker "SPRING SHOWCASE" --head "HIGHLIGHTS"
```

The full 16:9 frame as a band over a blurred copy, the profile logo (`brand.logo_png`) above, `team.foot` below
(`--foot` overrides), `--sponsor` line optional. Audio is copied untouched (the input must have an audio track), so
the vertical's loudness and audio gates match the 16:9's: QA it with the 16:9's `--cuts` list.

### 3.9 Contact sheet

```bash
python3 engine/sheet.py talk.mp4 out/sheet.jpg 0 60 --n 12 --w 300 --label "talk 0-60 s"
```

Read the image. Use it to pick in-points, check a cut, or show the user a clip without sending the clip.

## 4. Check and deliver

1. Run **video-gates** on every output, for example
   `python3 engine/qa.py out/hype/hype_fx.mp4 --profile demo --kind edit --cuts <printed list> --out out/hype/qa`
   (`--kind motion` for graphics, `explainer` for explainers, `loop` for loops and overlays; `--cuts none` when
   nothing is cut). Read `review.md` and `sheet.jpg`, judge every FAIL and WARN, fix every real FAIL, re-run.
2. Send small previews (720p or 540-wide, under ~30 MB) rather than masters when the user is on a phone.
3. Report compactly: what was made, where the files are (absolute paths), what the user must decide or check.
