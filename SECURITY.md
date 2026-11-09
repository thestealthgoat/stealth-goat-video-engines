# Security policy

## Reporting a vulnerability

Please report security problems privately, not in a public issue. On GitHub, open the repository's **Security**
tab and choose **Report a vulnerability**. Include the tool, the command you ran, what happens and, if you can, a
small input that shows it.

You will get a reply once the report has been read. A fix, if one is needed, is noted in
[`CHANGELOG.md`](CHANGELOG.md).

## Scope

The engine runs locally on your own machine; there is no hosted service, account or server to attack. Reports
that are in scope include:

- a tool that writes outside the output folder you gave it, or over your source footage,
- a crafted input file (a `site.json`, storyboard, edit list, profile or media file) that makes a tool run a shell
  command or code it should not,
- a site built with `web/build.py` that loads code from another host, sets tracking cookies by default, or has an
  injection problem in the pages it generates,
- a network request that a tool does not document (see "Local only" in [`docs/TOOLS.md`](docs/TOOLS.md)).

Out of scope: problems in third-party packages (ffmpeg, Python packages, npm packages, Playwright Chromium) that
are not caused by how the engine uses them. Report those to their own projects.
