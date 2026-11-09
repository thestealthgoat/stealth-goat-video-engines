## What and why

<!-- One or two sentences. Link the issue if there is one: Fixes #123 -->

## Checks

- [ ] Tests for what I touched pass (`python3 tests/test_<tool>.py`), and I added or updated a test on synthetic input
- [ ] Anything that renders went through the QA gate on the demo profile:
      `python3 engine/qa.py <video> --profile demo --kind <edit|motion|explainer|loop>` - result line pasted below
- [ ] `--help` works for any tool I added or changed
- [ ] No organization names, brand values or personal paths in `engine/`, `logo/`, `cutouts/` or `web/` (they belong in a profile)
- [ ] Motion uses `spring.py` / `spring.js`; audio fades at every cut, start and end
- [ ] Third-party code, models, fonts or data are credited in `NOTICE.md`; no AGPL, GPL or unlicensed code copied
- [ ] Docs updated (tool docstring, README tables, `CHANGELOG.md` under Unreleased); for a plugin skill, the plugin
      README table and `plugins/dist/` package

## Results

```text
<test PASS/FAIL lines and the qa.py RESULT line>
```
