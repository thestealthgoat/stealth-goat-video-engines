---
name: Bug report
about: A tool crashes, gives a wrong result, or a render fails the QA gate
title: "[bug] <tool>: <what goes wrong>"
labels: bug
---

**What happened**
<!-- One or two sentences. What did you expect instead? -->

**Command**
<!-- The exact command you ran, from the engine folder. -->

```bash
python3 engine/<tool>.py ...
```

**Output**
<!-- The error or the last 20 lines of output. For a render problem, also attach review.md and sheet.jpg from
     python3 engine/qa.py <video> --profile demo --out <folder> -->

```text

```

**Can you reproduce it on the demo profile?**
<!-- Yes / No. If it only happens with your own profile, paste the relevant part of profile.json
     (no private paths or names needed). -->

**Setup**
<!-- Paste the output of ./setup.sh --check (the Result line is enough if everything is ok). -->

- OS and chip:
- Python version (`python3 --version`):
- ffmpeg version (`ffmpeg -version | head -1`):
- Commit (`git rev-parse --short HEAD`):

**Input**
<!-- What kind of file went in (codec, size, fps, length). Attach a short sample only if you own it and it shows
     no one who hasn't agreed to be shared. -->
