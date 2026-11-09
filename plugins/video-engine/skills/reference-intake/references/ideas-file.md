# The ideas file

Default path: `$VIDEO_ENGINE/REFERENCE_IDEAS.md`, unless the user names another file. The engine's `.gitignore`
ignores that default file, so creator handles and links stay on the machine; a file the user names inside a repo
they push gets committed with it, so say so once. Create it from the template below the first time; after that, only append rows and edit the Build order list. Never rewrite or reorder
existing rows.

## Template

```markdown
# Reference ideas

Videos and sites I like, what makes them work, and what to build from them with the video engine.
IDs: engine IDs (E1, O4, W2 ...) are tools that already exist; N1, N2 ... are new features.

## Build order

1. (empty)

## Reference log

| Date | Reference | Category | What makes it work | Ideas |
|---|---|---|---|---|

## Ideas

| ID | Idea | How to build | Size | Fits | Status | From |
|---|---|---|---|---|---|---|
```

## Row formats

**Reference log** (one row per reference):

| Field | What goes in it |
|---|---|
| Date | ISO date, `2026-11-09` |
| Reference | creator and a link or the local file name, e.g. `@janedoe (TikTok), glass-cards.mov` |
| Category | motion graphic, logo, explainer, talking head, product promo, website, method or tool |
| What makes it work | one or two sentences with at least one measured number (cuts per second, BPM, longest hold, palette) |
| Ideas | the IDs it matched or created, e.g. `O4, P2, N3 (new)` |

**Ideas** (one row per idea, new ones only):

| Field | What goes in it |
|---|---|
| ID | next free `N` number (read the table first) |
| Idea | what it does on screen, in plain words |
| How to build | the engine parts it uses (tool, scene, element, spring preset) and what is missing |
| Size | S (an hour or two), M (about a day), L (several days) |
| Fits | the one or two places in the user's own work it serves |
| Status | `idea`, `building`, `built` (with the tool or flag that now does it), `dropped` |
| From | the reference(s) it came from (dates are enough) |

When a later reference shows an existing idea again, append its date to that row's "From" cell and, if it adds
something, a short note in "How to build". Do not add a duplicate row.

## Example rows

```markdown
| 2026-11-09 | @janedoe (TikTok), glass-cards.mov | product promo | 14 cuts in 23 s, every cut on a beat at 120 BPM; the reveal lands on the drop at 12 s; glass cards pass behind the presenter | O4, P2, N3 (new) |
```

```markdown
| N3 | Frosted glass on the orbit cards: blur and refraction of the presenter through the card | stage3d.py orbit + a transmission / roughness material like the W5 glass; needs a card material option | M | ACME launch promo | idea | 2026-11-09 |
```

## Build order

A short numbered list, most valuable first, one line each: `N3 frosted orbit cards (M): launch promo next month`.
Move an item up when a new reference shows the same idea again or the user's next project needs it; say so in the
reply.
