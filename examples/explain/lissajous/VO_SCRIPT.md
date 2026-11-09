# Why some notes sound good together - voice-over script

Read it straight through in your normal voice, about as fast as you'd explain it to a friend.
Any quiet room and a phone or a USB mic is fine. One take; pauses are fine (the edit snaps to your words).
Read each line as its own sentence with a short pause after it: the transcript is matched to these words, and a rushed
line can lose words. Save it as `vo.wav` (or `vo.m4a`, then use that name below) in this folder, then run from the
engine folder:

```bash
python3 engine/storyboard.py retime examples/explain/lissajous/storyboard.json --vo examples/explain/lissajous/vo.wav   # transcribes locally: writes vo.words.json
python3 examples/explain/lissajous/make.py      # re-times the beats to your words and rebuilds the tones to match
python3 engine/storyboard.py check examples/explain/lissajous/storyboard.json   # should say CHECK: OK
python3 engine/explain.py examples/explain/lissajous/storyboard.json --out out/lissajous --profile demo --vo examples/explain/lissajous/vo.wav --music examples/explain/lissajous/_build/tones.wav --music-db -10
```

The first run of `retime` downloads the faster-whisper model. If `check` fails after it (a gap over 2.5 s with no new
visual, or a beat at an impossible words per second), the transcript dropped words: compare `vo.words.json` with the
lines below and re-record the rushed part. No recording yet? Skip `retime`: `make.py` paces the beats from the text,
and `explain.py` renders without `--vo` (then leave out `--music-db` too: with no voice the tones are the whole
soundtrack and are levelled to the delivery loudness).

With a voice-over, the two tones under it are what the scope draws, so keep them audible: `--music-db -10`. Every number in the script was
measured or computed by `make.py` (see "measured" in storyboard.json); if you change a line, keep the numbers.

Each line is one beat on screen; the **bold** word gets the highlight.

1. This is what a perfect **fifth** looks like.
2. One note moves the dot **sideways**,
3. the other moves it **up** and down.
4. Same note twice: a still **circle**.
5. An **octave**: twice as fast, a figure eight.
6. A fifth: **three** against two.
7. Small numbers, simple shapes, and they sound **smooth**.
8. A **tritone** is forty five against thirty two.
9. It never settles, and it sounds **tense**.
10. Here's the **twist**: a piano's fifth isn't three to two.
11. It's tuned a hair flat, so the shape slowly **turns**.
12. Which interval should we draw **next**?
