# Fresh-eyes reviewer prompt

Whoever built the video never grades it. Spawn a sub-agent with no context from the build conversation. Give it only
files, never an explanation of what the video is meant to say:

- this version: `review.md`, `sheet.jpg`, the `frames.py` sheets (`contact_*.jpg`, `cut_f*.jpg`, `flag_f*.jpg`) and
  any crops you made;
- the previous version's `review.md` and sheets, when there is one;
- when there is no previous version: the brief's reference (a still or sheet of the look the user asked for).

Prompt (adapt the file paths, keep the rest):

```
You are reviewing a video you have never seen, only through these files:
<list the absolute paths>
Read review.md and look at every image. Do not assume anything about what the video is meant to say.

1. In one or two sentences, say what the video is about and where you got confused.
2. Score it out of 10, head to head against the previous version (<paths>, or "none: compare with the reference
   <path>"). Say which is better and why, by frame number.
3. Flag anything cheap or templated. Any yes is a fix: corner labels, counters, timecodes, corner brackets,
   "headline left / card right" deck layouts, typed-out headlines with a caret, fades everywhere, repeated identical
   transitions, things that grow from zero, decorative effects not born from the picture.
4. Step through the contact sheets and every cut strip frame by frame. Look for: text over text, text over a face,
   text closer than 24 px to the edge or outside the cyan safe box, a graphic that explodes, smears, flips or jumps
   for a few frames, an element that appears or vanishes in one frame, a wrong or black frame at a cut, anything cut
   by the frame edge, broken continuity across a cut.
5. List every defect in this exact format, most severe first:
   f<start>-f<end> (mm:ss.s) - what is wrong - why it matters - concrete fix (with a number when possible)
Answer with: about, score (this / previous), slop list hits, fix lines. Nothing else.
```

If the reviewer misreads the point of the video, that is a defect of the video, not of the reviewer: write it as a
fix line (which beat failed to carry the idea, and how to make it carry it).

Paste the answer under the "Fresh-eyes review" heading in `review.md`, replacing the placeholder lines.
