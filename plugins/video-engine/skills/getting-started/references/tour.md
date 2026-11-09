# The ten-minute tour (demo profile)

Four short pieces, each with a real command, on the neutral `demo` profile. Run them one at a time (one heavy render
at a time), show each result before the next, and say in one sentence which skill made it.

## Before you start

```bash
cd "$VIDEO_ENGINE"
T="$HOME/Movies/video-work/tour"; mkdir -p "$T"
python3 engine/vprofile.py list
python3 engine/vprofile.py show demo --check          # should end CHECK: OK
python3 engine/vprofile.py sample demo "$T/demo_card.png"
```

`show demo --check` ends `CHECK: OK` on a fresh machine too: the demo profile lists its working folders under
`~/Movies/video-work` as optional. Show `demo_card.png`: this is what a profile is (colours with
contrast, fonts, logo, a sample lower third).

`demo` ships with the engine (`profiles/demo/`: display name "Demo Sports", primary `#0B3D2E`, accent `#F2B705`,
Anton and Barlow Condensed Medium with their OFL licences, and `assets/demo_logo.png` as `brand.logo_png`). If it is
not in the list, the clone is incomplete or out of date: `git pull` in the engine folder. Only if that is not
possible, make a stand-in from the template:

```bash
python3 engine/vprofile.py new demo --display "Demo" --primary "#0B3D2E" --accent "#F2B705" --sample
```

Tell the user the stand-in differs from the shipped one: template fonts (Bebas Neue / Barlow Condensed) and no
`brand.logo_png`, so the stats card in section 2 has no logo.

## 1. Logo intro (logo-motion skill)

Write a sample mark (a made-up "ACME" hexagon; the user's own SVG works the same way):

```bash
cat > "$T/acme.svg" <<'EOF'
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 400">
  <polygon points="200,20 356,110 356,290 200,380 44,290 44,110" fill="#F2B705"/>
  <path d="M200 90 L310 310 H252 L230 262 H170 L148 310 H90 Z M200 160 L182 215 H218 Z" fill="#0B3D2E"/>
</svg>
EOF
python3 logo/motion.py "$T/acme.svg" "$T" ACME intro --profile demo --frames 0.3,2.0,3.9
```

`--frames` renders only stills (`ACME_intro_t0.30.png`, ...), transparent PNGs, in a few seconds. Look at them
first; this is how every motion piece starts. Then the full 4-second render:

```bash
python3 logo/motion.py "$T/acme.svg" "$T" ACME intro --profile demo
```

Outputs: `$T/ACME_intro_Alpha.mov` (ProRes 4444 with alpha: drop it over footage in any editor) and
`$T/ACME_intro.mp4` (a preview on the profile's primary colour). The default is 60 fps (`--fps` to change).
Point out: the same command with `outro --text1 "THANKS FOR WATCHING" --text2 "SEE YOU NEXT WEEK"` gives an end card,
`bug` gives a corner bug (in, loop, out), `stinger` a 1.2 s wipe, `writeon` a pen tracing the logo.

## 2. Stats lower third (motion-graphics skill)

```bash
python3 engine/statcard.py docs/stats_card_example.json "$T" --profile demo --name demo_card --frames 1.0,3.0
python3 engine/statcard.py docs/stats_card_example.json "$T" --profile demo --name demo_card
```

The first line writes two stills, `$T/demo_card_stats_t1.00.png` and `$T/demo_card_stats_t3.00.png`; the second writes `$T/demo_card_stats_Alpha.mov` (alpha, full frame),
`$T/demo_card_stats.mp4` (preview) and `$T/demo_card_stats.png` (the settled card, transparent).
Point out: the stats file is plain JSON (`num`, `name`, `big`, 2-4 `stats` pairs, optional `photo` cutout); copy it
and fill in your own. The panel slides in on springs and the numbers count up. Colours, fonts and the logo (from
`brand.logo_png`) come from the profile, so `--profile <theirs>` re-brands it with no other change.

## 3. QA run (video-gates skill)

A lower third is an overlay: it has no opening or ending of its own, so it is checked as `--kind loop` (the same
gates as `motion`, with the hook and end-tail gates listed as SKIP):

```bash
python3 engine/qa.py "$T/demo_card_stats.mp4" --profile demo --kind loop --cuts none --out "$T/qa_card"
echo "exit $?"        # 0 = PASS, 1 = FAIL, 2 = could not read the file
```

Expect `RESULT: PASS (0 warnings)` and exit 0. Open `$T/qa_card/review.md` and `$T/qa_card/sheet.jpg` with the
user. Walk through:

- the verdict line and the gate table (spec against the profile's size and frame rate, motion: dead stretches and
  stutters, flashes, one-frame pops, the hook in the first 0.5 s, holds, the end tail);
- each fix line, `f<start>-f<end> (mm:ss.s) - what - why - fix`, which names the exact frames;
- the sheet: one frame per shot with the safe area drawn, plus evidence strips for the worst flags.

Then show a real fix line by checking the same card as a stand-alone motion piece:

```bash
python3 engine/qa.py "$T/demo_card_stats.mp4" --profile demo --kind motion --cuts none --out "$T/qa_card_motion"
```

This FAILS, exit 1, on one gate: `hook: strong moment by 2 s` (the card's biggest move is about 8% of the frame;
the gate wants 20% in 0.2 s), with the fix line `f0-f59 (00:00.0) - no strong moment by 2 s ... - put a cut, a hit
or a big move ... by 1-2 s`. Say plainly that this is a real FAIL, and why it does not apply to an overlay: the
footage under the card carries the opening. That is what `--kind` is for.

Explain the rule: nothing is shown or delivered until this passes, or a failure is fixed. A gate that fails on
purpose is declared, and still shows in the review; it is never silently passed. The logo intro from section 1 is
the example: it settles at about 1.9 s and holds the finished logo to the end, by design. Checked plainly (`--kind
motion --cuts none --fps 60`; `--fps 60` because motion.py renders 60 fps and the demo profile delivers 29.97) it
FAILS with four dead stretches from about 1.9 s and a 1.8 s static tail. Declared:

```bash
python3 engine/qa.py "$T/ACME_intro.mp4" --profile demo --kind motion --cuts none --fps 60 \
    --intended end_tail --holds end:2.2 --out "$T/qa_intro"
```

`--holds end:2.2` marks the last 2.2 s as an intentional still, and `--intended end_tail` turns the static-tail
failure into an INFO line: expect `RESULT: PASS (0 warnings, 1 declared intended)`. If the dead stretches start
earlier than 1.9 s on this machine, read the first `f<start>` in the plain run's fix lines and widen `end:N` to cover
it; never declare more than the designed hold.

## 4. Explainer (explain skill)

The example in `examples/explain/lissajous/` explains why some notes sound good together: two tones, one on each
axis of a scope, draw a still shape when their frequencies make a small whole-number ratio. Every figure is computed
from the real waveforms, and the soundtrack is those same tones. Files: `make.py` (builds the data, the tones and
the storyboard), `storyboard.json` (the beats: what is said, what is on screen), `VO_SCRIPT.md` (the voice-over
script). Read the docstring at the top of `make.py` first. Its example adds `--music-db -10`; that flag only sets
the bed against a voice-over, so without one it has no effect (the bed is levelled to the profile loudness) and the
commands below leave it out. Follow the docstring for anything else that differs.

```bash
python3 examples/explain/lissajous/make.py
python3 engine/storyboard.py check examples/explain/lissajous/storyboard.json
python3 engine/explain.py examples/explain/lissajous/storyboard.json --out "$T/liss" --name lissajous \
    --profile demo --board
```

`storyboard.py check` prints the beat count, length and longest gap without a new visual, then `CHECK: OK`.
`--board` writes `$T/liss/lissajous_board.jpg`: one still per beat with its text. This is the approval step: show
it and ask for changes before the full render. Then:

```bash
python3 engine/explain.py examples/explain/lissajous/storyboard.json --out "$T/liss" --name lissajous \
    --profile demo --music examples/explain/lissajous/_build/tones.wav
python3 engine/qa.py "$T/liss/lissajous.mp4" --profile demo --kind explainer --out "$T/qa_liss"
```

The render takes about three minutes (1186 frames). Expect the QA to end `RESULT: PASS (0 warnings)`, with loudness
at the profile's -14 LUFS and the freshness gate well inside 2.5 s. If `explain.py` stops before rendering with
`--music ...: no such file (for a topic pack, run its make.py first)`, run `make.py` again.

Outputs: `$T/liss/lissajous.mp4` (1080p at the profile's frame rate, mix levelled to the profile loudness) and
`$T/liss/lissajous.xml` (a Premiere timeline, one clip a beat with a marker on each). `--kind explainer` adds the
freshness gate: a new visual at least every 2.5 s.
Point out: captions are paced by line length until a voice-over is recorded. With a recording (the user's own voice,
or a synthetic voice they choose, never a fake of a real person), `--vo voice.wav` adds it and
`engine/storyboard.py retime` lines the words up to it.

## Wrap up

- Re-run piece 1 or 2 with `--profile <their name>` so they see their own brand.
- Everything lives in `~/Movies/video-work/tour`; nothing was uploaded.
- Show the skill map (skill-map.md) and ask what they want to make first.
