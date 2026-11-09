"""W4 cinematic service-business hero: a pinned, scroll-scrubbed build sequence (real photos or frames of real
footage) with one editorial headline per stage, ending on the money shot with the call to action.

site.json "hero": {
  "eyebrow": "SPRINGFIELD · EST. 1998", "headline": ["BUILT FROM", "SOLID STEEL."], "text": "...",
  "cta": {"label": "Get a quote", "href": "#contact"},
  "sequence": {"frames": ["a.jpg", "b.jpg", ...]  |  "video": "build.mp4", "count": 72},   # real photos / footage only
  "alts": ["...", ...] (one per photo, or one "alt" for the video),
  "stages": [{"at": 0.0, "title": "The frame"}, {"at": 0.35, "title": "Walls go on"}, ...]  # at = share of the scroll
}
Photos are crossfaded by scroll position (a few stills read as a sequence); a video is cut into "count" frames.
Budgets (H9): the desktop frames stay under 32 MiB and the mobile set under 16 MiB, or the build stops. With
prefers-reduced-motion the sequence is never fetched: the money shot shows still.
"""
import html, os, subprocess, tempfile

E = html.escape


def frames_from_video(path, count, tmp):
    os.makedirs(tmp, exist_ok=True)
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path], capture_output=True, text=True).stdout)
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", path, "-vf", f"fps={count / dur:.4f},scale=1600:-2", "-q:v", "3",
                    os.path.join(tmp, "f%04d.jpg")], check=True)
    return sorted(os.path.join(tmp, f) for f in os.listdir(tmp) if f.endswith(".jpg"))[:count]


def build(ctx):
    site, out = ctx["site"], ctx["out"]; h = site["hero"]; seq = h["sequence"]
    base = os.path.dirname(os.path.abspath(site["_path"]))
    if seq.get("video"):
        v = seq["video"] if os.path.isabs(seq["video"]) else os.path.join(base, seq["video"])
        srcs = frames_from_video(v, int(seq.get("count", 72)), tempfile.mkdtemp())
        alts = [h.get("alt", "")] * len(srcs)
    else:
        srcs = seq["frames"]; alts = h.get("alts") or [h.get("alt", "")] * len(srcs)
    if not srcs:
        raise SystemExit("w4: hero.sequence has no frames (give 'frames' or a 'video')")
    if len(alts) != len(srcs):   # zip() would silently drop the last frames, and the last one is the money shot
        raise SystemExit(f"w4: hero.sequence has {len(srcs)} frames but hero.alts has {len(alts)} (need one alt per photo)")
    desk = [ctx["img"](s, a, width=1600) for s, a in zip(srcs, alts)]
    mob = [ctx["img"](s, a, width=800) for s, a in zip(srcs, alts)]
    size = lambda L: sum(os.path.getsize(os.path.join(out, p)) for p in set(L))
    if size(desk) > 32 * 2 ** 20 or size(mob) > 16 * 2 ** 20:
        raise SystemExit(f"w4: the sequence is {size(desk) / 2 ** 20:.1f} MiB desktop / {size(mob) / 2 ** 20:.1f} MiB mobile (budgets 32 / 16): use fewer frames")
    stages = h.get("stages", [])
    caps = "".join(f'<p class="w4-stage" data-at="{s["at"]}" aria-hidden="true">{E(s["title"])}</p>' for s in stages)
    head = "".join(f"<span>{E(l)}</span>" for l in h["headline"])
    money_alt = alts[-1] if alts else ""
    html_ = f"""<section class="w4" aria-label="{E(h.get('label', 'Build sequence'))}">
<div class="w4-pin"><canvas class="w4-canvas" aria-hidden="true"></canvas>
<img class="w4-still" src="{desk[-1]}" alt="{E(money_alt)}">
<div class="w4-shade"></div>
<div class="w4-copy"><p class="eyebrow">{E(h.get('eyebrow', ''))}</p><h1>{head}</h1>
<p class="w4-text">{E(h.get('text', ''))}</p>{'<a class="btn" href="' + E(h['cta']['href']) + '">' + E(h['cta']['label']) + '</a>' if h.get('cta') else ''}</div>
<div class="w4-stages">{caps}</div>
<p class="w4-hint" aria-hidden="true">Scroll</p></div></section>
<script>window.W4 = {{ desk: {desk!r}, mob: {mob!r} }};</script>"""
    css = """
.w4{position:relative;height:420vh;padding:0;max-width:none}
.w4-pin{position:sticky;top:0;height:100vh;overflow:hidden}
.w4-canvas,.w4-still{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}
.w4-still{opacity:0}
.w4-shade{position:absolute;inset:0;background:linear-gradient(90deg,rgba(0,0,0,.5),rgba(0,0,0,0) 65%),linear-gradient(180deg,rgba(0,0,0,.45),rgba(0,0,0,.05) 35%,rgba(0,0,0,.7))}
/* text over a photo: a soft dark pool behind the copy and behind each stage title (the contrast gate measures the real
   pixels), and the eyebrow in the text colour, since the accent can land on rust-red steel */
.w4-copy{z-index:1;text-shadow:0 1px 14px rgba(0,0,0,.55)}.w4-copy .eyebrow{color:var(--text)}.w4-copy .btn{text-shadow:none}
.w4-copy::before{content:"";position:absolute;inset:-7rem -9rem -5rem -9rem;z-index:-1;pointer-events:none;
  background:radial-gradient(closest-side,rgba(0,0,0,.62),rgba(0,0,0,.5) 55%,rgba(0,0,0,0))}
.w4-stage::before{content:"";position:absolute;inset:-1.2em -1.5em;z-index:-1;pointer-events:none;
  background:radial-gradient(closest-side,rgba(0,0,0,.6),rgba(0,0,0,.45) 60%,rgba(0,0,0,0))}
.w4-copy{position:absolute;left:clamp(1rem,6vw,6rem);right:clamp(1rem,6vw,6rem);bottom:clamp(2.5rem,8vh,7rem);max-width:46rem}
.w4-copy h1{font-size:clamp(2.2rem,min(7vw,10vh),6.5rem)}.w4-copy h1 span{display:block}.w4-text{color:var(--text);max-width:34rem;font-size:1.15rem}
.w4-stages{position:absolute;right:clamp(1rem,6vw,6rem);top:22vh;text-align:right}
.w4-stage{font-family:'Head';font-size:clamp(1.6rem,3.6vw,3rem);opacity:0;margin:0;position:absolute;right:0;z-index:1;width:max-content;max-width:calc(100vw - 2 * clamp(1rem,6vw,6rem));text-shadow:0 2px 18px rgba(0,0,0,.6)}
.w4-hint{position:absolute;left:50%;bottom:1.2rem;transform:translateX(-50%);color:var(--muted);letter-spacing:.3em;font-size:.8rem;text-transform:uppercase}
@media (prefers-reduced-motion:reduce){.w4{height:auto}.w4-pin{position:relative}.w4-canvas,.w4-hint,.w4-stages{display:none}.w4-still{opacity:1}}
"""
    js = """
// W4: draw the build sequence by scroll position (photos crossfade, frames index); stage headlines spring in (ui)
const S = window.Spring, reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
const sec = document.querySelector('.w4'), cv = document.querySelector('.w4-canvas'), cx = cv.getContext('2d');
if (!reduce) {
  const list = matchMedia('(max-width: 800px)').matches ? W4.mob : W4.desk;
  const imgs = list.map((s) => { const i = new Image(); i.decoding = 'async'; i.src = s; return i; });
  const fit = () => { cv.width = innerWidth * Math.min(2, devicePixelRatio); cv.height = innerHeight * Math.min(2, devicePixelRatio); };
  fit(); addEventListener('resize', () => { fit(); draw(); });
  const cover = (im, a) => { if (!im.complete || !im.naturalWidth) return; const k = Math.max(cv.width / im.naturalWidth, cv.height / im.naturalHeight);
    const w = im.naturalWidth * k, h = im.naturalHeight * k; cx.globalAlpha = a; cx.drawImage(im, (cv.width - w) / 2, (cv.height - h) / 2, w, h); };
  const stages = [...document.querySelectorAll('.w4-stage')]; let cur = -1;
  const showStage = (i) => { stages.forEach((el, k) => { const t0 = performance.now(), on = k === i;
    const run = (now) => { const t = (now - t0) / 1000, p = S.clamp01(S.progress(t, { preset: on ? 'ui' : 'uiExit' }));
      el.style.opacity = on ? p : Math.min(+el.style.opacity || 0, 1 - p); el.style.transform = `translateY(${on ? (1 - p) * 20 : -p * 14}px)`; if (t < 0.5) requestAnimationFrame(run); };
    requestAnimationFrame(run); }); };
  const prog = () => { const r = sec.getBoundingClientRect(); return Math.min(1, Math.max(0, -r.top / (r.height - innerHeight))); };
  function draw() {
    const p = prog(), f = p * (imgs.length - 1), i = Math.floor(f), k = f - i;
    cx.clearRect(0, 0, cv.width, cv.height); cover(imgs[i], 1); if (k > 0.001 && imgs[i + 1]) cover(imgs[i + 1], k);
    const si = stages.reduce((b, el, n) => (p >= +el.dataset.at ? n : b), -1); if (si !== cur) { cur = si; showStage(si); }
  }
  imgs.forEach((im) => im.addEventListener('load', draw)); addEventListener('scroll', () => requestAnimationFrame(draw), { passive: true }); draw();
}
"""
    return html_, css, js, {}
