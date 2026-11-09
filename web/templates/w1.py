"""W1 scroll-built story: a pinned frame scrubbed by scroll through an image sequence (real photos or frames pulled
from real footage), one caption per stage, ending on the last stage's final frame, then the kit sections.

Desktop: the sequence plays in a tall portrait-or-landscape frame beside the caption column (a soft, dim copy of the
current frame fills the room behind). Phone: the frame fills the screen and the caption sits on a solid card at the
bottom. A numbered rail (real buttons) jumps to any stage on a 'smooth' spring scroll. Captions spring in ('ui') and
out ('uiExit'); opacity is clamped. Frames preload coarse-to-fine so the whole story scrubs early.
prefers-reduced-motion: nothing is pinned or fetched in bulk; the page shows every stage as text with one still each,
and the finished frame.

site.json "hero": {
  "label": "Walkthrough of ...",                   # aria-label of the section
  "eyebrow": "...", "headline": "..." | ["line", "line"], "text": "...", "hint": "Scroll to walk through",
  "credit": "Footage: ...", "licence": "...",      # logged for every frame (assets.json)
  "frame_ratio": "9/16",                           # the footage's shape (desktop frame box)
  "unit_vh": 75,                                   # scroll length of one stage (weight 1), in viewport heights %
  "hold": 0.25,                                    # share of the last stage that holds on the final frame
  "intro": {"frames": "img/seq/s0-*.jpg", "alt": "...", "weight": 0.6},
  "stages": [{"title": "...", "text": "...", "alt": "...", "frames": "img/seq/s1-*.jpg" | [..], "weight": 1}, ...]
}
Budgets: desktop frames under 32 MiB, phone set under 16 MiB, or the build stops.
"""
import glob, html, json, os

E = html.escape


def _luma(h):
    h = h.lstrip("#"); c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    c = [v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4 for v in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def _contrast(a, b):
    x, y = sorted((_luma(a), _luma(b)), reverse=True)
    return (x + 0.05) / (y + 0.05)


def _mix(a, b, k):
    a, b = a.lstrip("#"), b.lstrip("#")
    return "#" + "".join(f"{int(round(int(a[i:i + 2], 16) + (int(b[i:i + 2], 16) - int(a[i:i + 2], 16)) * k)):02x}" for i in (0, 2, 4))


def text_safe(pal):
    """the palette guarantees the accent at 3:1 (large text); small text and buttons need 4.5:1"""
    acc = pal["accent"]
    # the pinned stage sits over a blurred copy of the frame at 12% opacity: the worst ground behind the copy is the
    # background moved 12% toward white (or black, on a light ground), so the accent is checked against both
    grounds = [pal["bg"], pal["bg2"], _mix(pal["bg"], "#ffffff", 0.12), _mix(pal["bg"], "#000000", 0.12)]
    while min(_contrast(acc, g) for g in grounds) < 4.6:
        acc = _mix(acc, pal["text"], 0.12)
    btn, on = pal["accent"], pal["on_accent"]
    toward = "#000000" if _luma(on) > 0.5 else "#ffffff"
    while _contrast(btn, on) < 4.6:
        btn = _mix(btn, toward, 0.08)
    return acc, btn


def frames_of(base, spec):
    if isinstance(spec, list):
        return spec
    hits = sorted(glob.glob(os.path.join(base, spec)))
    if not hits:
        raise SystemExit(f"w1: no frames match {spec!r}")
    return [os.path.relpath(h, base) for h in hits]


def build(ctx):
    site, out, pal = ctx["site"], ctx["out"], ctx["pal"]; h = site["hero"]
    base = os.path.dirname(os.path.abspath(site["_path"]))
    credit, licence = h.get("credit"), h.get("licence")
    chapters = [dict(h["intro"], intro=True)] + [dict(s) for s in h["stages"]]
    desk, mob = [], []
    for ch in chapters:
        fs = frames_of(base, ch["frames"])
        desk.append([ctx["img"](f, ch["alt"], width=720, credit=credit, licence=licence) for f in fs])
        mob.append([ctx["img"](f, ch["alt"], width=480, credit=credit, licence=licence) for f in fs])
    size = lambda L: sum(os.path.getsize(os.path.join(out, p)) for p in {x for c in L for x in c})
    if size(desk) > 32 * 2 ** 20 or size(mob) > 16 * 2 ** 20:
        raise SystemExit(f"w1: the sequence is {size(desk) / 2 ** 20:.1f} MiB desktop / {size(mob) / 2 ** 20:.1f} MiB phone (budgets 32 / 16): use fewer frames")
    weights = [float(c.get("weight", 0.6 if c.get("intro") else 1.0)) for c in chapters]
    unit = float(h.get("unit_vh", 75)); length = round(sum(weights) * unit)
    n = len(chapters) - 1
    head = h["headline"] if isinstance(h["headline"], str) else " ".join(f"<span>{E(l)}</span>" for l in h["headline"])
    head = E(head) if isinstance(h["headline"], str) else head
    caps = [f'<div class="w1-cap w1-intro" data-i="0"><p class="eyebrow">{E(h.get("eyebrow", ""))}</p><h1>{head}</h1>'
            f'<p class="w1-t">{E(h.get("text", ""))}</p><p class="w1-hint">{E(h.get("hint", "Scroll to walk through"))}</p></div>']
    for i, s in enumerate(chapters[1:], 1):
        thumb = desk[i][len(desk[i]) // 2]
        caps.append(f'<div class="w1-cap" data-i="{i}"><img class="w1-thumb" src="{thumb}" alt="{E(s["alt"])}" loading="lazy">'
                    f'<div><p class="w1-n">{i:02d} / {n:02d}</p><h2>{E(s["title"])}</h2><p class="w1-t">{E(s["text"])}</p></div></div>')
    rail = "".join(f'<li><button type="button" data-i="{i}" aria-label="{i:02d} {E(s["title"])}">{i:02d}</button></li>'
                   for i, s in enumerate(chapters[1:], 1))
    still_alt = chapters[-1]["alt"]
    ratio = h.get("frame_ratio", "9/16")
    data = {"desk": desk, "mob": mob, "weights": weights, "hold": float(h.get("hold", 0.25))}
    html_ = f"""<section class="w1" aria-label="{E(h.get('label', 'Build sequence'))}" style="--w1-len:{length}">
<div class="w1-pin"><canvas class="w1-back" width="18" height="32" aria-hidden="true"></canvas>
<div class="w1-copy"><div class="w1-caps">{''.join(caps)}</div>
<div class="w1-nav"><div class="w1-bar" aria-hidden="true"><span></span></div><ol class="w1-rail" aria-label="Jump to a stage">{rail}</ol></div></div>
<figure class="w1-frame"><canvas class="w1-canvas" aria-hidden="true"></canvas><img class="w1-still" src="{desk[-1][-1]}" alt="{E(still_alt)}"></figure>
</div></section>
<script>window.W1 = {json.dumps(data)};</script>"""
    acc_text, btn = text_safe(pal)
    css = f"""
:root{{--w1-acc:{acc_text};--w1-btn:{btn}}}
.tpl-w1 .eyebrow,.tpl-w1 .step-n,.tpl-w1 .stat-v{{color:var(--w1-acc)}}
.tpl-w1 main a:not(.btn),.tpl-w1 .foot div a{{color:var(--w1-acc)}}
@media (max-width:800px){{.tpl-w1 .top{{padding:.8rem 1rem}}.tpl-w1 .brand{{font-size:.9rem;letter-spacing:.03em;white-space:nowrap}}
  .tpl-w1 .top nav a{{margin-left:.7rem;font-size:.8rem;white-space:nowrap}}.w1 h1 span{{display:inline}}}}
.tpl-w1 section>p.reveal{{max-width:44rem}}.tpl-w1 .cta .lede{{margin-left:auto;margin-right:auto}}
.tpl-w1 .btn,.tpl-w1 .draft{{background:var(--w1-btn)}}
.w1{{position:relative;max-width:none;padding:0;height:calc(var(--w1-len) * 1vh + 100vh)}}
.w1-pin{{position:sticky;top:0;height:100vh;overflow:hidden;display:grid;grid-template-columns:minmax(0,36rem) auto;justify-content:center;
  align-items:center;gap:clamp(2rem,6vw,6rem);padding:5.5rem clamp(1rem,6vw,6rem) 2.5rem}}
.w1-back{{position:absolute;inset:0;width:100%;height:100%;opacity:.12;filter:blur(30px);transform:scale(1.2);pointer-events:none}}
.w1-copy{{position:relative;display:flex;flex-direction:column;gap:2.2rem;min-width:0}}
.w1-caps{{display:grid}}.w1-cap{{grid-area:1/1;align-self:end;will-change:opacity,transform}}
.w1-cap:not(.w1-intro){{opacity:0}}
.w1 h1{{font-size:clamp(2.4rem,5.2vw,5rem);margin-bottom:.35em}}.w1 h1 span{{display:block}}
.w1-cap h2{{font-size:clamp(1.9rem,3.3vw,3rem);margin-bottom:.4em}}
.w1-t{{font-size:1.12rem;color:var(--text);max-width:33rem;margin:0}}
.w1-n{{font-family:'BodySB';letter-spacing:.22em;font-size:.8rem;color:var(--w1-acc);margin:0 0 .9rem}}
.w1-hint{{margin:1.4rem 0 0;font-family:'BodySB';font-size:.8rem;letter-spacing:.24em;text-transform:uppercase;color:var(--text)}}
.w1-thumb{{display:none}}
.w1-bar{{height:2px;background:var(--bg2);margin-bottom:.2rem;overflow:hidden}}
.w1-bar span{{display:block;height:100%;background:var(--w1-acc);transform-origin:0 50%;transform:scaleX(0)}}
.w1-rail{{display:flex;flex-wrap:wrap;gap:.3rem;list-style:none;padding:0;margin:0}}
.w1-rail button{{font:600 .85rem 'BodySB',system-ui,sans-serif;color:var(--text);background:none;border:0;border-bottom:2px solid transparent;
  padding:.5rem .35rem;min-width:2.6rem;min-height:2.6rem;cursor:pointer;letter-spacing:.06em}}
.w1-rail button[aria-current]{{border-bottom-color:var(--w1-acc);color:var(--w1-acc)}}
.w1-frame{{position:relative;margin:0;height:min(78vh,780px);aspect-ratio:{ratio};border-radius:10px;overflow:hidden;background:var(--bg2);
  box-shadow:0 30px 90px rgba(0,0,0,.5)}}
.w1-canvas,.w1-still{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}}
.w1-live .w1-still{{opacity:0}}
@media (max-width:800px){{
  .w1-pin{{display:block;padding:0;height:100vh;height:100svh}}
  .w1-back{{display:none}}
  .w1-frame{{position:absolute;inset:0;height:auto;aspect-ratio:auto;border-radius:0;box-shadow:none}}
  .w1-copy{{position:absolute;left:0;right:0;bottom:0;z-index:2;background:var(--bg);padding:1.1rem 1rem 1rem;gap:.9rem;border-radius:14px 14px 0 0}}
  .w1 h1{{font-size:2.3rem}}.w1-cap h2{{font-size:1.55rem}}.w1-t{{font-size:1rem;line-height:1.5}}
  .w1-n{{margin-bottom:.4rem}}.w1-hint{{margin-top:.7rem}}
  .w1-rail{{gap:.1rem;justify-content:space-between}}.w1-rail button{{min-width:2.4rem;padding:.4rem .2rem}}
}}
@media (prefers-reduced-motion:reduce){{
  .w1{{height:auto}}
  .w1-pin{{position:relative;height:auto;overflow:visible;align-items:start;padding-top:7rem}}
  .w1-back,.w1-canvas,.w1-nav,.w1-hint{{display:none}}
  .w1-caps{{gap:2.6rem}}.w1-cap{{grid-area:auto;opacity:1!important;transform:none!important;display:grid;grid-template-columns:7rem 1fr;gap:1.2rem;align-items:start}}
  .w1-intro{{display:block}}
  .w1-thumb{{display:block;width:7rem;aspect-ratio:{ratio};object-fit:cover;border-radius:6px}}
  .w1-frame{{position:sticky;top:6rem}}
  .w1-still{{opacity:1}}
}}
@media (prefers-reduced-motion:reduce) and (max-width:800px){{
  .w1-pin{{display:flex;flex-direction:column;gap:2rem;padding:6rem 1rem 3rem}}
  .w1-copy{{position:static;padding:0;background:none}}
  .w1-frame{{position:relative;inset:auto;width:100%;height:auto;aspect-ratio:{ratio};border-radius:10px}}
}}
"""
    js = r"""
// W1 scroll-built story: scroll position scrubs the frame sequence directly; captions and rail jumps run on springs.
const S = window.Spring, reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
const sec = document.querySelector('.w1'), D = window.W1;
if (sec && D && !reduce) {
  sec.classList.add('w1-live');
  const phone = matchMedia('(max-width: 800px)').matches, lists = phone ? D.mob : D.desk;
  const flat = [], offs = [];
  lists.forEach((L) => { offs.push(flat.length); flat.push(...L); });
  const imgs = new Array(flat.length).fill(null);
  // preload coarse to fine (each stage's first frame, then every 16th, 8th ... frame) so the whole walk scrubs early
  const order = [], seen = new Set(), add = (i) => { if (i < flat.length && !seen.has(i)) { seen.add(i); order.push(i); } };
  offs.forEach(add); for (const st of [16, 8, 4, 2, 1]) for (let i = 0; i < flat.length; i += st) add(i);
  let busy = 0;
  const pump = () => { while (busy < 6 && order.length) { const i = order.shift(), im = new Image(); busy++; im.decoding = 'async';
    im.onload = () => { imgs[i] = im; busy--; pump(); queue(); }; im.onerror = () => { busy--; pump(); }; im.src = flat[i]; } };
  pump();
  const near = (i) => { for (let d = 0; d < flat.length; d++) { if (imgs[i - d]) return imgs[i - d]; if (imgs[i + d]) return imgs[i + d]; } return null; };
  const cv = sec.querySelector('.w1-canvas'), cx = cv.getContext('2d'), bk = sec.querySelector('.w1-back'), bx = bk.getContext('2d');
  const fit = () => { const r = cv.getBoundingClientRect(), k = Math.min(2, devicePixelRatio || 1); cv.width = Math.round(r.width * k); cv.height = Math.round(r.height * k); };
  const cover = (c, w, h, im, a) => { if (!im) return; const k = Math.max(w / im.naturalWidth, h / im.naturalHeight), iw = im.naturalWidth * k, ih = im.naturalHeight * k;
    c.globalAlpha = a; c.drawImage(im, (w - iw) / 2, (h - ih) / 2, iw, ih); };
  // chapter spans along the scroll (intro + stages), from their weights
  const tot = D.weights.reduce((a, b) => a + b, 0), starts = []; let acc = 0;
  D.weights.forEach((w) => { starts.push(acc / tot); acc += w; });
  const last = lists.length - 1;
  const prog = () => { const r = sec.getBoundingClientRect(); return Math.min(1, Math.max(0, -r.top / (r.height - innerHeight))); };
  const caps = [...sec.querySelectorAll('.w1-cap')], btns = [...sec.querySelectorAll('.w1-rail button')], bar = sec.querySelector('.w1-bar span');
  caps.forEach((el, i) => { el._o = i === 0 ? 1 : 0; });
  const fade = (el, on) => { const tok = (el._tok || 0) + 1, from = el._o, t0 = performance.now(); el._tok = tok;
    const run = (now) => { if (el._tok !== tok) return; const t = (now - t0) / 1000, p = S.clamp01(S.progress(t, { preset: on ? 'ui' : 'uiExit' }));
      el._o = from + ((on ? 1 : 0) - from) * p; el.style.opacity = el._o; el.style.transform = `translateY(${on ? (1 - p) * 18 : -p * 12}px)`;
      if (t < 0.45) requestAnimationFrame(run); };
    requestAnimationFrame(run); };
  let cur = 0;
  const setChapter = (c) => { if (c === cur) return; fade(caps[cur], false); fade(caps[c], true); cur = c;
    btns.forEach((b) => (+b.dataset.i === c ? b.setAttribute('aria-current', 'step') : b.removeAttribute('aria-current'))); };
  function draw() {
    const p = prog(); let c = 0; starts.forEach((s, i) => { if (p >= s) c = i; });
    const len = (c < last ? starts[c + 1] : 1) - starts[c], q = len > 0 ? (p - starts[c]) / len : 0, n = lists[c].length;
    const G = c < last ? offs[c] + q * n : offs[c] + Math.min(1, q / (1 - D.hold)) * (n - 1);
    const i = Math.min(flat.length - 1, Math.floor(G)), k = S.clamp01((G - i - 0.65) / 0.35),  // hold each frame, dissolve only at the end
      a = near(i), b = imgs[i + 1];
    cx.clearRect(0, 0, cv.width, cv.height); cover(cx, cv.width, cv.height, a, 1); if (b && k > 0.01) cover(cx, cv.width, cv.height, b, k);
    if (!phone && a) { bx.clearRect(0, 0, bk.width, bk.height); cover(bx, bk.width, bk.height, a, 1); }
    bar.style.transform = `scaleX(${p})`; setChapter(c);
  }
  let pend = false; const queue = () => { if (!pend) { pend = true; requestAnimationFrame(() => { pend = false; draw(); }); } };
  fit(); addEventListener('resize', () => { fit(); queue(); }); addEventListener('scroll', queue, { passive: true }); draw();
  // rail: jump to a stage on a 'smooth' spring (a camera move); any wheel / touch / key takes the scroll back
  let jump = 0; const stop = () => { jump++; };
  ['wheel', 'touchstart', 'keydown'].forEach((e) => addEventListener(e, stop, { passive: true }));
  btns.forEach((b) => b.addEventListener('click', () => { const c = +b.dataset.i, top = sec.offsetTop + starts[c] * (sec.offsetHeight - innerHeight) + 2;
    const from = scrollY, tok = ++jump, t0 = performance.now();
    const run = (now) => { if (jump !== tok) return; const t = (now - t0) / 1000;
      window.scrollTo({ top: S.at(t, { from, to: top, preset: 'smooth' }), behavior: 'instant' }); if (t < 0.9) requestAnimationFrame(run); };
    requestAnimationFrame(run); }));
}
"""
    return html_, css, js, {}
