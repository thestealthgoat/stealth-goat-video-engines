"""W5 3D glass showcase hero: a dark pinned stage where one glass material (three.js MeshPhysicalMaterial: transmission,
thickness, low roughness, a RoomEnvironment through PMREM for reflections) sits on floating orbs and crystal shards
that refract thin studio light bars. The camera rides a path driven by scroll (smoothed by a 'smooth' spring follower),
the objects drift, and big editorial type changes chapter by chapter ('ui' in / 'uiExit' out, opacity clamped).

site.json "hero": {
  "label": "Jane Doe: video, broadcast and design",          # aria-label of the hero
  "eyebrow": "VIDEO · BROADCAST · DESIGN",
  "headline": ["Live events.", "Brand films.", "Tools I build."],
  "text": "...",
  "cta": {"label": "Get in touch", "href": "#contact"},  "cta2": {"label": "See the work", "href": "#work"},   # optional
  "chapters": [{"at": 0.22, "kicker": "01 · Broadcast", "title": "...", "text": "..."}, ...],  # at = share of the scroll
  "glass": {"seed": 7, "tint": 0.45}     # optional: layout seed; how much of the accent tints the glass (0 = clear)
}
No photos needed (the stage is generated), so nothing here can be stock or AI imagery. three.js ships with the site
(ctx["three"]), nothing loads from another host. With prefers-reduced-motion, no WebGL or no JS, three.js is never
fetched: the hero is a still, readable page (headline, then the chapters as a grid over a CSS glass still).
"""
import html, json

E = html.escape


def _rel(hex_):
    h = hex_.lstrip("#"); c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    c = [v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4 for v in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def _con(a, b):
    la, lb = sorted((_rel(a), _rel(b)), reverse=True); return (la + 0.05) / (lb + 0.05)


def _mix(a, b, k):
    a, b = a.lstrip("#"), b.lstrip("#")
    return "#" + "".join(f"{int(round(int(a[i:i + 2], 16) + (int(b[i:i + 2], 16) - int(a[i:i + 2], 16)) * k)):02x}" for i in (0, 2, 4))


def text_safe(pal):
    """the kit guarantees the accent 3:1 on the ground (enough for big type); small accent text (eyebrows, links) and
    button labels need 4.5:1, so W5 lifts the accent for text and deepens / lightens the button fill until both pass"""
    acc = pal["accent"]; k = 0.0
    while (_con(acc, pal["bg"]) < 4.6 or _con(acc, pal["bg2"]) < 4.6) and k < 1: k += 0.04; acc = _mix(pal["accent"], pal["text"], k)
    btn = pal["accent"]; toward = "#000000" if pal["on_accent"].lower() == "#ffffff" else "#ffffff"; k = 0.0
    while _con(pal["on_accent"], btn) < 4.6 and k < 1: k += 0.03; btn = _mix(pal["accent"], toward, k)
    return acc, btn


def build(ctx):
    site, pal = ctx["site"], ctx["pal"]; h = site["hero"]; g = h.get("glass", {})
    head = ctx["three"](("environments/RoomEnvironment.js",))
    acc_text, btn = text_safe(pal)
    chapters = h.get("chapters", [])
    lines = "".join(f"<span>{E(l)}</span>" for l in h["headline"])
    btns = "".join(f'<a class="btn{" ghost" if k == "cta2" else ""}" href="{E(h[k]["href"])}">{E(h[k]["label"])}</a>' for k in ("cta", "cta2") if h.get(k))
    chs = "".join(f'<article class="w5-ch w5-slot" data-at="{float(c["at"]):.3f}"><p class="w5-kick">{E(c.get("kicker", ""))}</p>'
                  f'<h2>{E(c["title"])}</h2>' + (f'<p class="w5-ch-text">{E(c["text"])}</p>' if c.get("text") else "") + "</article>" for c in chapters)
    ticks = "".join(f'<b style="top:{float(c["at"]) * 100:.1f}%"></b>' for c in chapters)
    cfg = {"bg": pal["bg"], "accent": pal["accent"], "text": pal["text"], "muted": pal["muted"],
           "tint": _mix("#ffffff", pal["accent"], float(g.get("tint", 0.45))), "seed": int(g.get("seed", 7))}
    cfg_js = json.dumps(cfg).replace("</", "<\\/")
    html_ = f"""<section class="w5" id="top" aria-label="{E(h.get('label', 'Introduction'))}">
<script>(function(){{var s=document.currentScript.parentNode;try{{if(!matchMedia('(prefers-reduced-motion: reduce)').matches&&window.WebGL2RenderingContext&&window.IntersectionObserver)s.classList.add('w5-live')}}catch(e){{}}}})()</script>
<div class="w5-pin">
<canvas class="w5-gl" aria-hidden="true"></canvas>
<div class="w5-still" aria-hidden="true"><i class="o1"></i><i class="o2"></i><i class="o3"></i><i class="o4"></i><u class="b1"></u><u class="b2"></u><u class="b3"></u></div>
<div class="w5-scrim" aria-hidden="true"></div>
<div class="w5-intro w5-slot" data-at="0"><p class="eyebrow">{E(h.get('eyebrow', ''))}</p><h1>{lines}</h1>
<p class="w5-text">{E(h.get('text', ''))}</p>{'<div class="w5-btns">' + btns + '</div>' if btns else ''}</div>
<div class="w5-chapters">{chs}</div>
<div class="w5-rail" aria-hidden="true"><i></i>{ticks}</div>
<p class="w5-hint" aria-hidden="true">Scroll</p>
</div></section>
<script>window.W5 = {cfg_js};</script>"""
    css = f"""
/* W5 3D glass showcase */
body.tpl-w5{{--accent:{acc_text};--w5-btn:{btn}}}
.tpl-w5 .btn:not(.ghost),.tpl-w5 .draft,.tpl-w5 .skip{{background:var(--w5-btn)}}
.tpl-w5 .btn.ghost{{box-shadow:inset 0 0 0 2px color-mix(in srgb,var(--text) 70%,transparent)}}
.w5{{position:relative;padding:0;max-width:none;margin:0}}
.w5-pin{{position:relative;min-height:100vh;overflow:hidden;background:var(--bg);padding:clamp(15rem,46vh,26rem) clamp(1rem,6vw,6rem) clamp(3rem,8vh,6rem)}}
.w5-gl{{position:absolute;inset:0;width:100%;height:100%;display:none;opacity:0}}
.w5-scrim{{display:none}}
.w5-intro{{position:relative;z-index:2;max-width:56rem}}
.w5-intro .eyebrow{{color:var(--text);display:flex;align-items:center;gap:.8em}}
.w5-intro .eyebrow::before{{content:'';width:1.8rem;height:2px;background:var(--accent);flex:none}}
.w5-intro h1{{font-size:clamp(2.7rem,7.4vw,7rem);line-height:.98;margin-bottom:.35em;text-wrap:balance}}
.w5-intro h1 span{{display:block}}
.w5-text{{font-size:clamp(1.05rem,1.3vw,1.25rem);max-width:36rem;color:var(--text);text-wrap:pretty}}
.w5-btns{{display:flex;flex-wrap:wrap;gap:.8rem;margin-top:1.6rem}}
.w5-chapters{{position:relative;z-index:2;display:grid;gap:2.2rem 3rem;margin-top:4.5rem;grid-template-columns:repeat(auto-fit,minmax(15rem,1fr))}}
.w5-ch h2{{font-size:clamp(1.6rem,2.6vw,2.3rem);line-height:1.08;text-wrap:balance}}
.w5-kick{{font-family:'BodySB';letter-spacing:.22em;text-transform:uppercase;font-size:.8rem;color:var(--muted);margin-bottom:.8em}}
.w5-ch-text{{color:var(--muted);max-width:34rem;text-wrap:pretty}}
.w5-rail,.w5-hint{{display:none}}
/* the still: CSS glass for reduced motion, no WebGL, and the moment before three.js arrives */
.w5-still{{position:absolute;inset:0 0 auto 0;height:clamp(15rem,46vh,26rem);pointer-events:none;z-index:0}}
.w5-still i{{position:absolute;border-radius:50%;
  background:radial-gradient(circle at 33% 27%,rgba(255,255,255,.62),rgba(255,255,255,.10) 18%,transparent 42%),
    radial-gradient(circle at 68% 80%,color-mix(in srgb,var(--accent) 50%,transparent),transparent 58%),
    radial-gradient(circle at 50% 50%,rgba(255,255,255,.03),rgba(255,255,255,.09) 70%,rgba(255,255,255,.22) 100%);
  box-shadow:inset 0 0 0 1px rgba(255,255,255,.2),inset -14px -22px 44px rgba(0,0,0,.35),0 40px 80px rgba(0,0,0,.35)}}
.w5-still .o1{{width:clamp(9rem,26vw,24rem);aspect-ratio:1;right:9%;top:16%}}
.w5-still .o2{{width:clamp(4.5rem,11vw,10rem);aspect-ratio:1;right:40%;top:40%}}
.w5-still .o3{{width:clamp(3rem,6vw,6rem);aspect-ratio:1;right:4%;top:62%}}
.w5-still .o4{{width:clamp(2.2rem,4vw,4rem);aspect-ratio:1;right:30%;top:14%}}
.w5-still u{{position:absolute;width:2px;background:linear-gradient(transparent,var(--accent),transparent);opacity:.7}}
.w5-still .b1{{height:62%;right:24%;top:6%}}.w5-still .b2{{height:46%;right:52%;top:22%;opacity:.35;background:linear-gradient(transparent,var(--text),transparent)}}
.w5-still .b3{{height:54%;right:6%;top:10%;opacity:.45}}
/* live: a pinned stage, the chapters take turns in one slot */
.w5-live{{height:430vh}}
.w5-live .w5-pin{{position:sticky;top:0;height:100vh;min-height:0;padding:0}}
.w5-live .w5-gl{{display:block}}
.w5-live .w5-still{{height:100%}}
.w5-live .w5-scrim{{display:block;position:absolute;inset:0;z-index:1;pointer-events:none;
  background:linear-gradient(90deg,color-mix(in srgb,var(--bg) 60%,transparent) 0%,transparent 55%),
    linear-gradient(0deg,color-mix(in srgb,var(--bg) 55%,transparent),transparent 30%)}}
/* a quiet panel behind whichever block of type is showing: --w5-top follows the block's top on a 'smooth' spring */
.w5-live .w5-scrim::before{{content:'';position:absolute;left:0;top:0;bottom:0;width:min(64rem,72vw);
  background:linear-gradient(180deg,transparent calc(var(--w5-top,40vh) - 18vh),color-mix(in srgb,var(--bg) 90%,transparent) calc(var(--w5-top,40vh) - 3vh));
  -webkit-mask-image:linear-gradient(90deg,#000 62%,transparent);mask-image:linear-gradient(90deg,#000 62%,transparent)}}
.w5-live .w5-intro h1{{font-size:clamp(2.4rem,min(7.4vw,10.5vh),7rem)}}
.w5-live .w5-intro,.w5-live .w5-ch{{position:absolute;z-index:2;left:clamp(1rem,6vw,6rem);bottom:clamp(2rem,9vh,7.5rem);width:min(52rem,calc(100vw - 2rem));margin:0;will-change:opacity,transform}}
.w5-live .w5-chapters{{position:static;margin:0;display:block}}
.w5-live .w5-ch{{opacity:0;pointer-events:none}}
.w5-live .w5-ch h2{{font-size:clamp(2.2rem,min(6.2vw,9.5vh),5.8rem);line-height:.98;margin-bottom:.3em}}
.w5-live .w5-ch-text{{color:var(--text);font-size:clamp(1.05rem,1.3vw,1.25rem)}}
.w5-live .w5-intro h1,.w5-live .w5-text,.w5-live .w5-ch h2,.w5-live .w5-ch-text{{text-shadow:0 2px 28px color-mix(in srgb,var(--bg) 80%,transparent)}}
.w5-live .w5-rail{{display:block;position:absolute;z-index:2;right:clamp(1rem,3vw,2.5rem);top:50%;height:38vh;width:2px;transform:translateY(-50%);
  background:color-mix(in srgb,var(--muted) 35%,transparent)}}
.w5-rail i{{position:absolute;inset:0;background:var(--accent);transform-origin:top;transform:scaleY(0)}}
.w5-rail b{{position:absolute;left:-4px;width:10px;height:2px;background:var(--muted)}}
.w5-live .w5-hint{{display:block;position:absolute;z-index:2;left:50%;bottom:1.1rem;transform:translateX(-50%);margin:0;color:var(--muted);
  letter-spacing:.3em;font-size:.75rem;text-transform:uppercase}}
@media (max-width:800px){{
  .w5-pin{{padding-top:clamp(13rem,52vh,22rem)}}
  .w5-still{{height:clamp(13rem,52vh,22rem)}}
  .w5-still .o1{{right:-6%;top:12%;width:58vw}}.w5-still .o2{{right:58%;top:30%;width:24vw}}.w5-still .o3{{right:8%;top:58%;width:13vw}}.w5-still .o4{{right:44%;top:10%}}
  .w5-live{{height:380vh}}
  .w5-live .w5-scrim{{background:none}}
  .w5-live .w5-scrim::before{{width:100%;-webkit-mask-image:none;mask-image:none}}
  .w5-live .w5-intro,.w5-live .w5-ch{{bottom:2.6rem}}
  .w5-live .w5-intro h1{{font-size:clamp(2.1rem,min(11vw,6.4vh),3.4rem)}}
  .w5-live .w5-ch h2{{font-size:clamp(2rem,min(10vw,6vh),3.2rem)}}
  .w5-live .w5-text,.w5-live .w5-ch-text{{font-size:1rem}}
  .w5-live .w5-hint,.w5-live .w5-rail{{display:none}}
}}
@media (prefers-reduced-motion:reduce){{
  .w5.w5-live{{height:auto}}.w5-live .w5-pin{{position:relative;height:auto;min-height:100vh;padding:clamp(15rem,46vh,26rem) clamp(1rem,6vw,6rem) 4rem}}
  .w5-live .w5-gl,.w5-live .w5-scrim,.w5-live .w5-rail,.w5-live .w5-hint{{display:none}}
  .w5-live .w5-intro,.w5-live .w5-ch{{position:relative;left:auto;bottom:auto;width:auto;opacity:1;pointer-events:auto}}
  .w5-live .w5-chapters{{display:grid;margin-top:4.5rem}}
}}
"""
    return html_, css, JS, {"head": head}


JS = r"""
// W5: glass orbs and shards in a dark stage. Scroll drives the camera path (followed by a 'smooth' spring), the pointer
// nudges it ('gentle'), chapter type springs in ('ui') and out ('uiExit'); opacity is always clamped.
const S = window.Spring, C = window.W5, sec = document.querySelector('.w5');
const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
const small = matchMedia('(max-width: 800px)').matches;
const goStatic = () => { sec.classList.remove('w5-live'); sec.querySelectorAll('.w5-slot').forEach((el) => { el.style.opacity = ''; el.style.transform = ''; el.style.pointerEvents = ''; }); };

// a spring that can be re-aimed mid-move: it keeps its position and velocity and heads for the new target
function follower(init, preset) {
  let from = init, to = init, v0 = 0, t0 = 0, pre = preset;
  const o = () => ({ from, to, preset: pre, v0 });
  return {
    get(now) { return to === from ? to : S.at((now - t0) / 1000, o()); },
    set(target, now, p) {
      if (target === to && (!p || p === pre)) return;
      const t = (now - t0) / 1000, cur = to === from ? to : S.at(t, o()), vel = to === from ? 0 : S.velocity(t, o());
      from = cur; to = target; t0 = now; pre = p || pre;
      v0 = Math.abs(to - from) > 1e-6 ? vel / (to - from) : 0; if (Math.abs(to - from) <= 1e-6) from = to;
    },
  };
}

function live() {
  const slots = [...sec.querySelectorAll('.w5-slot')].map((el) => ({ el, at: +el.dataset.at, f: follower(0, 'ui'), on: false }));
  const intro = slots[0], hint = sec.querySelector('.w5-hint'), fill = sec.querySelector('.w5-rail i');
  intro.on = true; intro.f = follower(1, 'ui');
  const prog = () => { const r = sec.getBoundingClientRect(); return Math.min(1, Math.max(0, -r.top / Math.max(1, r.height - innerHeight))); };
  // keyboard: tabbing into the intro while it is scrolled away brings the page back to it
  intro.el.addEventListener('focusin', () => { if (prog() > 0.02) window.scrollTo({ top: sec.offsetTop, behavior: 'instant' }); });
  const pin = sec.querySelector('.w5-pin'), topF = follower(intro.el.offsetTop, 'smooth');
  addEventListener('resize', () => topF.set(slots[active].el.offsetTop, performance.now()));
  const P = follower(prog(), 'smooth'), mx = follower(0, 'gentle'), my = follower(0, 'gentle');
  if (matchMedia('(pointer: fine)').matches) addEventListener('pointermove', (e) => { const n = performance.now();
    mx.set(e.clientX / innerWidth - 0.5, n); my.set(e.clientY / innerHeight - 0.5, n); }, { passive: true });
  let active = 0, gl = null;
  function frame(now) {
    const raw = prog(); P.set(raw, now);
    const ai = slots.reduce((b, s, i) => (raw >= s.at ? i : b), 0);
    if (ai !== active || !slots[ai].on) { slots.forEach((s, i) => { const on = i === ai; if (on !== s.on) { s.on = on; s.f.set(on ? 1 : 0, now, on ? 'ui' : 'uiExit'); } }); active = ai; topF.set(slots[ai].el.offsetTop, now); }
    pin.style.setProperty('--w5-top', topF.get(now).toFixed(1) + 'px');
    for (const s of slots) { const v = s.f.get(now), a = S.clamp01(v);
      s.el.style.opacity = a; s.el.style.transform = a > 0.999 ? 'none' : `translateY(${((1 - v) * (s.on ? 26 : -18)).toFixed(2)}px)`;
      s.el.style.pointerEvents = a > 0.5 ? 'auto' : 'none'; }
    if (hint) hint.style.opacity = S.clamp01(1 - raw * 30) * S.clamp01(intro.f.get(now));
    if (fill) fill.style.transform = `scaleY(${raw.toFixed(4)})`;
    if (gl) gl(now, Math.min(1, Math.max(0, P.get(now))), mx.get(now), my.get(now));
  }
  // one loop, live only while the hero is on screen
  let raf = 0, visible = true;
  const loop = (now) => { raf = 0; frame(now); if (visible) raf = requestAnimationFrame(loop); };
  const kick = () => { if (!raf && visible) raf = requestAnimationFrame(loop); };
  new IntersectionObserver((es) => { visible = es[0].isIntersecting; kick(); }).observe(sec);
  kick();
  // three.js is fetched only now (never under reduced motion), and only if WebGL2 really works here
  const probe = document.createElement('canvas').getContext('webgl2');
  if (!probe) { goStatic(); visible = false; return; }
  stage().then((fn) => { gl = fn; }).catch((e) => { console.warn('w5: showing the still', e); goStatic(); visible = false; });
}

async function stage() {
  const THREE = await import('three');
  const { RoomEnvironment } = await import('three/addons/environments/RoomEnvironment.js');
  const canvas = sec.querySelector('.w5-gl'), still = sec.querySelector('.w5-still');
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: !small && devicePixelRatio < 2, powerPreference: 'high-performance' });
  let dpr = Math.min(devicePixelRatio, small ? 1.5 : 1.75); renderer.setPixelRatio(dpr);
  renderer.toneMapping = THREE.NeutralToneMapping; renderer.toneMappingExposure = 1.05;
  const scene = new THREE.Scene(), bg = new THREE.Color(C.bg);
  scene.background = bg; scene.fog = new THREE.Fog(bg, 13, 34);
  const pmrem = new THREE.PMREMGenerator(renderer);
  scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture; scene.environmentIntensity = 1.0; pmrem.dispose();
  const camera = new THREE.PerspectiveCamera(small ? 52 : 40, 1, 0.1, 120); scene.add(camera);

  // the one material: clear glass with a breath of the brand accent in its body colour
  const glass = new THREE.MeshPhysicalMaterial({ color: 0xffffff, metalness: 0, roughness: 0.06, transmission: 1, thickness: 1.1, ior: 1.5,
    dispersion: small ? 0 : 0.8, attenuationColor: new THREE.Color(C.tint), attenuationDistance: 4, clearcoat: 1, clearcoatRoughness: 0.05,
    specularIntensity: 1 });
  let seed = C.seed >>> 0; const rnd = () => { seed = (seed + 0x6D2B79F5) >>> 0; let t = seed; t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
  const orbGeo = new THREE.SphereGeometry(1, small ? 40 : 56, small ? 28 : 40);
  const shardGeo = new THREE.LatheGeometry([0, 0.3, 0.36, 0.3, 0].map((x, i) => new THREE.Vector2(x, [-1.25, -0.72, 0.1, 0.75, 1.3][i])), 6).toNonIndexed();
  shardGeo.computeVertexNormals();
  const gemGeo = new THREE.IcosahedronGeometry(1, 0);
  const things = [], clusters = [3, -8, -19, -30];
  const sideX = (min, max) => small ? (rnd() < 0.5 ? 1 : -1) * (0.45 + rnd() * 1.9)      // phone: above the type, both sides
    : min + rnd() * (max - min);                                                         // desktop: right of the type
  for (const cz of clusters) {
    const n = small ? { orb: 2, shard: 2, gem: 1 } : { orb: 2, shard: 3, gem: 1 };
    for (const [kind, geo, count] of [['orb', orbGeo, n.orb], ['shard', shardGeo, n.shard], ['gem', gemGeo, n.gem]]) for (let i = 0; i < count; i++) {
      const m = new THREE.Mesh(geo, glass);
      const s = kind === 'orb' ? 0.55 + rnd() * 0.85 : kind === 'shard' ? 0.7 + rnd() * 0.6 : 0.45 + rnd() * 0.4;
      m.scale.setScalar(s); m.position.set(sideX(1.7, 4.6), small ? 0.5 + (rnd() - 0.5) * 2.6 : (rnd() - 0.5) * 3.4, cz + (rnd() - 0.5) * 6);
      m.rotation.set(rnd() * 6.28, rnd() * 6.28, rnd() * 6.28); scene.add(m);
      things.push({ m, y: m.position.y, x: m.position.x, rx: m.rotation.x, ry: m.rotation.y, sx: (rnd() - 0.5) * 0.3, sy: (rnd() - 0.5) * 0.4,
        f: 0.25 + rnd() * 0.35, ph: rnd() * 6.28, k: (rnd() - 0.5) * 3, dx: (rnd() - 0.5) * 1.6 });
    }
  }
  // a soft studio glow that travels with the camera: opaque (so the glass refracts it), fading to the page colour at its edges
  const gc = document.createElement('canvas'); gc.width = gc.height = 256; const g2 = gc.getContext('2d');
  const hex = (c) => '#' + c.getHexString(), glowCol = new THREE.Color(C.bg).lerp(new THREE.Color(C.accent), 0.24);
  const grad = g2.createRadialGradient(128, 128, 0, 128, 128, 128); grad.addColorStop(0, hex(glowCol));
  grad.addColorStop(0.45, hex(new THREE.Color(C.bg).lerp(new THREE.Color(C.accent), 0.08))); grad.addColorStop(0.92, hex(bg)); grad.addColorStop(1, hex(bg));
  g2.fillStyle = grad; g2.fillRect(0, 0, 256, 256);
  const glowTex = new THREE.CanvasTexture(gc); glowTex.colorSpace = THREE.SRGBColorSpace;
  const glow = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), new THREE.MeshBasicMaterial({ map: glowTex, toneMapped: false, fog: false, depthWrite: false }));
  glow.renderOrder = -1; glow.position.set(small ? 2 : 12, small ? 9 : 3, -70); glow.scale.set(small ? 64 : 70, small ? 64 : 70, 1); camera.add(glow);
  // thin studio light bars behind each cluster: what the glass bends, and a quiet graphic on their own
  const barGeo = new THREE.BoxGeometry(1, 1, 1);
  const accentBar = new THREE.MeshBasicMaterial({ color: new THREE.Color(C.accent), toneMapped: false });
  const paleBar = new THREE.MeshBasicMaterial({ color: new THREE.Color(C.muted).lerp(bg, 0.35), toneMapped: false });
  for (const cz of clusters) for (let i = 0; i < 3; i++) {
    const b = new THREE.Mesh(barGeo, i % 2 ? paleBar : accentBar), w = small ? 0.03 : 0.04, len = small ? 3 + rnd() * 3 : 5 + rnd() * 6;
    b.scale.set(w, len, w); b.position.set(small ? (rnd() - 0.5) * 7 : 1.5 + rnd() * 8, small ? 1.6 + rnd() : (rnd() - 0.5) * 2, cz - 6 - rnd() * 4); scene.add(b);
  }
  // a little dust for depth
  const dust = new THREE.BufferGeometry(), N = small ? 160 : 320, pos = new Float32Array(N * 3);
  for (let i = 0; i < N; i++) { pos[i * 3] = (rnd() - 0.5) * 22; pos[i * 3 + 1] = (rnd() - 0.5) * 12; pos[i * 3 + 2] = 8 - rnd() * 46; }
  dust.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  scene.add(new THREE.Points(dust, new THREE.PointsMaterial({ color: new THREE.Color(C.text), size: 0.035, transparent: true, opacity: 0.45, depthWrite: false })));

  const path = new THREE.CatmullRomCurve3([[-0.3, 0.2, 11], [0.5, -0.15, 2], [-0.4, 0.25, -8], [0.45, -0.2, -17], [0, 0.05, -24]].map((p) => new THREE.Vector3(...p)));
  const look = new THREE.Vector3();
  const size = () => { const w = canvas.clientWidth || innerWidth, h = canvas.clientHeight || innerHeight;
    renderer.setSize(w, h, false); camera.aspect = w / h;
    if (small) camera.setViewOffset(w, h, 0, h * 0.2, w, h); else camera.setViewOffset(w, h, -w * 0.15, 0, w, h); camera.updateProjectionMatrix(); };
  size(); addEventListener('resize', size);
  const pose = (p, px, py) => {
    camera.position.copy(path.getPointAt(p)); camera.position.x += px * 0.5; camera.position.y -= py * 0.35;
    look.copy(path.getPointAt(Math.min(1, p + 0.08))); look.z -= 6; look.x += px * 0.2; camera.lookAt(look);
  };
  pose(0, 0, 0); await renderer.compileAsync(scene, camera);       // shaders compile off the main thread where the browser can
  // quality that fits the device: if frames run slow, drop the glass dispersion, then the pixel ratio (never below 0.6)
  let n = 0, acc = 0, last = 0;
  const tune = (now) => { const dt = last ? now - last : 0; last = now; if (!dt || dt > 400) return; n++; acc += dt; if (n < 24) return;
    const avg = acc / n; n = 0; acc = 0; if (avg < 34) return;
    if (glass.dispersion > 0) { glass.dispersion = 0; glass.needsUpdate = true; } else if (dpr > 0.6) { dpr = Math.max(0.6, dpr * 0.75); renderer.setPixelRatio(dpr); size(); } };
  // the canvas takes over from the CSS still once the first frame is drawn (a 'smooth' spring, opacity clamped)
  const fade = follower(0, 'smooth'); let faded = false;
  return (now, p, px, py) => {
    const t = now / 1000; pose(p, px, py);
    for (const o of things) {
      o.m.rotation.x = o.rx + t * o.sx + p * o.k; o.m.rotation.y = o.ry + t * o.sy + p * o.k * 0.6;
      o.m.position.y = o.y + Math.sin(t * o.f + o.ph) * 0.14; o.m.position.x = o.x + p * o.dx;
    }
    renderer.render(scene, camera); tune(performance.now());
    if (!faded) { fade.set(1, now); const a = S.clamp01(fade.get(now)); canvas.style.opacity = a; still.style.opacity = 1 - a; if (a > 0.999) { faded = true; still.style.visibility = 'hidden'; } }
  };
}

if (reduce || !sec.classList.contains('w5-live')) goStatic(); else live();
"""
