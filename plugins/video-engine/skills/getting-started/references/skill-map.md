# Which skill does what

Show this to the user at the end of the tour. They never need to name a skill: they say what they want, and the
right skill picks it up. The engine tools named here are in the engine folder (`$VIDEO_ENGINE`).

## video-engine plugin

| Skill | What it makes | Say things like | Main tools |
|---|---|---|---|
| getting-started | engine setup, brand profile, this tour | "set up the video engine", "make a brand profile", "show me what this can do" | `setup.sh`, `engine/vprofile.py` |
| video | the front door for any edit: talking-head edits (pauses and fillers cut, punch-ins), kinetic captions, beat-synced cuts, clips from a list, Premiere XML, 9:16 versions | "cut the pauses out of this talk and caption it", "beat-sync these clips to this song", "make a vertical version" | `engine/talkedit.py`, `captions.py`, `beatmap.py`, `beatsnap.py`, `clip_plays.py`, `fcp7xml.py`, `vertical.py` |
| video-gates | the QA review every render gets: spec, motion, audio, loudness, cuts, flashes, hook and holds | "QA this render", "check this video before I post it", "why did it fail?" | `engine/qa.py` (with `motion_check.py`, `audio_check.py`) |
| explain | explainers whose numbers and pictures are computed, not guessed: storyboard, approval board, render, voice-over timing | "make an explainer on why a room echoes", "explain compound interest in 60 seconds" | `engine/storyboard.py`, `explain.py`, `musicbed.py`, `sourcecard.py` |
| matte | a person cut out of moving video (alpha), text behind the speaker | "cut the speaker out of this clip", "put the title behind me" | `engine/matte.py`, `behind.py` |
| motion-graphics | stats lower thirds, quote cards, progress bars, before/after, route maps, 3D card scenes, bouncing-word verses | "stats lower third for our top scorer", "quote card from this clip at 5:00", "route map of our trip" | `engine/statcard.py`, `quote.py`, `progressbar.py`, `beforeafter.py`, `routemap.py`, `stage3d.py`, `hopwords.py` |
| logo-motion | animated logos with transparent backgrounds: intro, end card, corner bug, stinger, "presented by" lower third, write-on, word swaps, shatter | "make a logo intro", "end card that says thanks for watching", "corner bug for the stream" | `logo/motion.py` |
| logo-3d | the logo extruded in 3D: stills, a swing loop, a GLB model | "3D version of our logo", "spinning logo loop" | `logo/render3d.py` |
| logo-vectorize | a clean SVG and transparent PNGs from a JPG, PNG, screenshot or photo of a logo | "turn this JPG logo into an SVG", "clean up this blurry logo" | `logo/vectorize.py`, `logo/redraw.py` |
| player-cutouts | transparent person cutouts from photos (BiRefNet), graded and filed one folder per person | "cut out our players from these photos", "headshot cutouts for the roster" | `cutouts/cutouts.py`, `engine/cutout.py` |
| action-pack | a fast stop-motion video from burst photos, 16:9 or vertical | "stop-motion pack from these bursts", "make an action pack" | `engine/flipbook.py` |
| reference-intake | a breakdown of a video or site the user likes: what makes it work, ideas to borrow | "here's a video I like, break it down", "what makes this intro feel good?" | ffmpeg contact sheet and cut count, a local faster-whisper transcript (nothing sent out) |

## ui-kit plugin (separate install)

| Skill | What it makes | Say things like |
|---|---|---|
| ui-kit | brand color tokens with measured contrast, type scale, spring UI motion, accessible components and focus states | "apply the UI kit to this app", "make our app's colors accessible" |
| website | one-page sites from a short `site.json`, with draft legal pages and a compliance gate | "build a website for my studio" |

Install it with `/plugin install ui-kit@stealth-goat` (same marketplace). The website skill uses the same engine
folder; its demo sites are `examples/sites/demo-world/site.json` (an isometric world) and
`examples/sites/demo-studio/site.json` (a glass showcase), both on the demo profile.

## How to ask

- Plain words are enough. Say what it is, what it is for, and roughly how long: "a 20-second intro for our YouTube
  channel", "a 9:16 reel for social", "a lower third for the live stream".
- Hand over the files: drag them in, or say the folder. Footage is read, never overwritten; outputs go to a new
  folder.
- Name the brand once ("use the acme profile"), or set the default with `vprofile.py default` and forget about it.
- Ask for a look first on anything long: "show me stills", "show me the board".
- Every render comes back with its QA review. Say "fix the QA notes" or "why did it fail?".
- Say which services are OK. By default everything is free, open-source and local; a voice service or a stock
  library is used only when the user asks for it, and never to fake a real person.
