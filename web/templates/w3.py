"""W3 drone flyover hero: scroll flies a tilted camera over a real orthomosaic (three.js plane, the map as the ground
texture), stopping on each place with an info card, then pulls back to the whole campus.

site.json "hero": {
  "label": "Campus flyover", "eyebrow": "Campus map", "headline": ["Find your way", "around campus."], "text": "...",
  "hint": "Scroll to fly", "still_text": "..." (shown with the still map: reduced motion or no WebGL),
  "map": {"src": "img/ortho.jpg", "alt": "...", "credit": "Aerial map: ...", "licence": "..."},   # a real orthomosaic only
  "places": [{"label": "Field 1", "x": 1077, "y": 1938, "r": 340, "heading": -8, "text": "..."}, ...],
       # x / y = pixel position on map.src; r = ground radius (px) the camera frames; heading = camera turn (degrees)
  "outro": {"title": "...", "text": "...", "cta": {"label": "...", "href": "#contact"}}
}
Scroll position sets the camera's target pose directly (overview -> each place, with a hold on each, lifting between
them like a drone); the camera follows that target on a 'gentle' spring, and cards / labels spring in on 'ui' and out
on 'uiExit' (opacity clamped). The map is shipped twice: the full web copy for desktop and a half-size copy for phones.
Without WebGL2, or with prefers-reduced-motion, three.js is never fetched: a still, numbered map and the list of
places show instead. Budget: the desktop map stays under 8 MiB, or the build stops.
"""
import html, json, os

E = html.escape


def build(ctx):
    site, out, pal = ctx["site"], ctx["out"], ctx["pal"]; h = site["hero"]; m = h["map"]
    from PIL import Image
    base = os.path.dirname(os.path.abspath(site["_path"]))
    src = m["src"] if os.path.isabs(m["src"]) else os.path.join(base, m["src"])
    W, H = Image.open(src).size
    dw = min(W, 4096 if H <= 4096 else int(W * 4096 / H))           # keep the texture within 4096 px on its long side
    desk = ctx["img"](m["src"], m["alt"], width=dw, credit=m.get("credit"), licence=m.get("licence"))
    mob = ctx["img"](m["src"], m["alt"], width=max(800, dw // 2), credit=m.get("credit"), licence=m.get("licence"))
    if os.path.getsize(os.path.join(out, desk)) > 8 * 2 ** 20:
        raise SystemExit(f"w3: the map is {os.path.getsize(os.path.join(out, desk)) / 2 ** 20:.1f} MiB (budget 8): use a smaller copy")
    places = h["places"]; n = len(places)
    if not 2 <= n <= 8:
        raise SystemExit(f"w3: {n} places (use 2 to 8)")
    data = {"desk": desk, "mob": mob, "aspect": W / H,
            "places": [{"x": p["x"] / W, "y": p["y"] / H, "r": p.get("r", 380) / H, "heading": p.get("heading", 0)} for p in places],
            "bg": pal["bg"]}
    head = "".join(f"<span>{E(l)}</span>" for l in h["headline"])
    cta = h.get("outro", {}).get("cta")
    pins = "".join(f'<div class="w3-dot" data-i="{i}"><span class="w3-num">{i + 1}</span><span class="w3-tag">{E(p["label"])}</span></div>'
                   for i, p in enumerate(places))
    cards = "".join(f'<article class="w3-card" data-i="{i}"><p class="w3-step">Stop {i + 1} of {n}</p><h2>{E(p["label"])}</h2>'
                    f'<p>{E(p.get("text", ""))}</p></article>' for i, p in enumerate(places))
    o = h.get("outro", {})
    outro = (f'<div class="w3-card w3-outro" data-i="{n}"><h2>{E(o.get("title", ""))}</h2><p>{E(o.get("text", ""))}</p>'
             + (f'<a class="btn" href="{E(cta["href"])}">{E(cta["label"])}</a>' if cta else "") + "</div>") if o else ""
    nav = "".join(f'<li><button type="button" data-go="{i}" aria-label="Fly to {E(p["label"])}"><span class="w3-n" aria-hidden="true">{i + 1}</span>'
                  f'<span class="w3-l" aria-hidden="true">{E(p["label"])}</span></button></li>' for i, p in enumerate(places))
    marks = "".join(f'<span class="w3-mk" style="left:{p["x"] / W * 100:.2f}%;top:{p["y"] / H * 100:.2f}%" aria-hidden="true">{i + 1}</span>'
                    for i, p in enumerate(places))
    items = "".join(f'<li><span class="w3-n" aria-hidden="true">{i + 1}</span><div><h3>{E(p["label"])}</h3><p>{E(p.get("text", ""))}</p></div></li>'
                    for i, p in enumerate(places))
    credit = E(m.get("credit", ""))
    intro = lambda text: f'<p class="eyebrow">{E(h.get("eyebrow", ""))}</p><h1>{head}</h1><p class="w3-text">{E(text)}</p>'

    html_ = f"""<script>try{{if(!matchMedia('(prefers-reduced-motion: reduce)').matches)document.documentElement.classList.add('w3-js')}}catch(e){{}}</script>
<section class="w3" id="map" aria-label="{E(h.get('label', 'Map'))}">
<div class="w3-pin">
<canvas class="w3-canvas" aria-hidden="true"></canvas><div class="w3-shade" aria-hidden="true"></div>
<div class="w3-pins" aria-hidden="true">{pins}</div>
<div class="w3-panel">
<div class="w3-card w3-intro is-on" data-i="-1">{intro(h.get("text", ""))}<p class="w3-hint" aria-hidden="true">{E(h.get('hint', 'Scroll'))}</p></div>
{cards}{outro}</div>
<nav class="w3-nav" aria-label="Places on the map"><ol>{nav}</ol></nav>
<p class="w3-credit">{credit}</p>
</div>
<div class="w3-still">
<div class="w3-still-copy">{intro(h.get("still_text") or h.get("text", ""))}</div>
<div class="w3-still-grid"><figure class="w3-map"><div class="w3-map-img"><img src="{mob}" alt="{E(m['alt'])}" loading="lazy" width="{max(800, dw // 2)}" height="{round(max(800, dw // 2) * H / W)}">{marks}</div>
<figcaption>{credit}</figcaption></figure>
<ol class="w3-list">{items}</ol></div>
</div>
</section>
<script>window.W3 = {json.dumps(data)};</script>"""
    css = """
.w3{position:relative;padding:0;max-width:none}
.w3-pin{display:none}
.w3-js .w3-pin{display:block;position:sticky;top:0;height:100vh;height:100svh;overflow:hidden}
.w3-js .w3-still{display:none}
.w3-canvas{position:absolute;inset:0;width:100%;height:100%;display:block}
.w3-shade{position:absolute;inset:0;pointer-events:none;
  background:linear-gradient(90deg,color-mix(in srgb,var(--bg) 82%,transparent) 0%,color-mix(in srgb,var(--bg) 30%,transparent) 34%,transparent 52%),
             linear-gradient(180deg,color-mix(in srgb,var(--bg) 70%,transparent) 0%,transparent 16%)}
.w3-pins{position:absolute;inset:0;pointer-events:none}
.w3-dot{position:absolute;left:0;top:0;display:flex;align-items:center;gap:.5rem;will-change:transform}
.w3-num,.w3 .w3-n{flex:none;display:grid;place-items:center;width:1.9rem;height:1.9rem;border-radius:50%;font:700 .9rem/1 'BodySB',system-ui,sans-serif;
  background:var(--bg);color:var(--text);box-shadow:0 0 0 2px var(--accent),0 4px 14px rgba(0,0,0,.45)}
.w3-dot.is-on .w3-num{background:var(--accent);color:var(--on-accent)}
.w3-tag{background:var(--bg);color:var(--text);font:600 .9rem/1 'BodySB',system-ui,sans-serif;padding:.45rem .7rem;border-radius:4px;
  white-space:nowrap;opacity:0;box-shadow:0 4px 14px rgba(0,0,0,.4)}
.w3-panel{position:absolute;left:clamp(1rem,6vw,6rem);bottom:clamp(2.5rem,11vh,7rem);width:min(31rem,40vw);height:min(70vh,36rem)}
.w3-card{position:absolute;left:0;right:0;bottom:0;visibility:hidden;opacity:0}
.w3-card.is-on{visibility:visible;opacity:1}
.w3-card:not(.w3-intro){background:var(--bg);border-radius:10px;padding:1.5rem 1.6rem 1.3rem;border-left:4px solid var(--accent);
  box-shadow:0 18px 50px rgba(0,0,0,.45)}
.w3-card h2{font-size:clamp(1.7rem,2.8vw,2.5rem);margin:0 0 .4em}
.w3-card p{color:var(--text);margin:0 0 .6em}.w3-card .btn{margin-top:.6rem}
.w3-step{font-family:'BodySB';letter-spacing:.22em;text-transform:uppercase;font-size:.78rem;color:var(--accent)!important}
.w3-intro{width:min(36rem,40vw)}.w3-intro h1,.w3-still-copy h1{font-size:clamp(2.4rem,3.8vw,3.6rem)}.w3 h1 span{display:block}
.w3-text{font-size:1.15rem;max-width:30rem;text-shadow:0 1px 12px rgba(0,0,0,.5)}
.w3-hint{color:var(--text);letter-spacing:.3em;font-size:.78rem;text-transform:uppercase;margin-top:1.2rem}
.w3-hint::after{content:'';display:block;width:2px;height:2.2rem;margin:.7rem 0 0 .4rem;background:var(--accent)}
.w3-nav{position:absolute;right:clamp(1rem,2.5vw,2.5rem);top:50%;transform:translateY(-50%)}
.w3-nav ol{list-style:none;margin:0;padding:0;display:grid;gap:.55rem;justify-items:end}
.w3-nav button{display:flex;align-items:center;gap:.65rem;border:0;cursor:pointer;background:color-mix(in srgb,var(--bg) 86%,transparent);color:var(--text);
  padding:.35rem .9rem .35rem .35rem;border-radius:999px;font:600 .9rem/1 'BodySB',system-ui,sans-serif}
.w3-nav button[aria-current] .w3-n{background:var(--accent);color:var(--on-accent)}
.w3-nav button:hover .w3-l{color:var(--accent)}
.w3-credit{position:absolute;right:clamp(1rem,2.5vw,2.5rem);bottom:.9rem;margin:0;font-size:.78rem;background:var(--bg);color:var(--text);
  padding:.3rem .6rem;border-radius:4px}
.w3-still{padding:clamp(6rem,12vw,9rem) clamp(1rem,6vw,6rem) clamp(3rem,8vw,6rem);max-width:1280px;margin:0 auto}
.w3-still-grid{display:grid;gap:2.5rem;align-items:start;margin-top:1rem}
@media(min-width:900px){.w3-still-grid{grid-template-columns:minmax(0,1fr) minmax(0,1fr)}}
.w3-map{margin:0}.w3-map-img{position:relative}.w3-map-img img{width:100%;height:auto;border-radius:8px}
.w3-map figcaption{margin-top:.6rem;font-size:.9rem;color:var(--text)}
.w3-mk{position:absolute;transform:translate(-50%,-50%);display:grid;place-items:center;width:1.8rem;height:1.8rem;border-radius:50%;
  background:var(--accent);color:var(--on-accent);font:700 .85rem/1 'BodySB',system-ui,sans-serif;box-shadow:0 0 0 2px var(--bg)}
.w3-list{list-style:none;padding:0;margin:0;display:grid;gap:1.4rem}
.w3-list li{display:flex;gap:1rem;align-items:flex-start}.w3-list h3{margin:.15rem 0 .3rem}.w3-list p{color:var(--muted);margin:0}
@media (max-width:800px){
  .tpl-w3 .top{background:var(--bg)}.tpl-w3 .top::after{content:'';position:absolute;left:0;right:0;top:100%;height:.9rem;
    background:linear-gradient(var(--bg),color-mix(in srgb,var(--bg) 0%,transparent))}  /* solid bar: nothing bright behind the header text */
.tpl-w3 .top .brand{font-size:1rem}.tpl-w3 .top nav a{margin-left:.9rem;font-size:.85rem}
  .w3-intro{background:var(--bg);border-radius:10px;padding:1.1rem 1.2rem .9rem;border-left:4px solid var(--accent);box-shadow:0 18px 50px rgba(0,0,0,.45)}
  .w3-intro .w3-hint{margin:0}.w3-hint::after{display:none}
  .w3-shade{background:linear-gradient(0deg,color-mix(in srgb,var(--bg) 92%,transparent) 0%,color-mix(in srgb,var(--bg) 55%,transparent) 30%,transparent 50%),
                       linear-gradient(180deg,color-mix(in srgb,var(--bg) 80%,transparent) 0%,transparent 22%)}
  .w3-panel{left:1rem;right:1rem;width:auto;bottom:3.1rem;height:auto;top:8.5rem}
  .w3-card:not(.w3-intro){padding:1.1rem 1.2rem 1rem}
  .w3-card h2{font-size:1.6rem}.w3-card p{font-size:1rem}
  .w3-intro h1{font-size:2.1rem}.w3-text{font-size:1rem;text-shadow:none}
  .w3-intro{width:auto}
  .w3-nav{top:5.4rem;right:auto;left:1rem;transform:none}
  .w3-nav ol{display:flex;gap:.5rem;justify-items:start}
  .w3-nav button{padding:.2rem;background:transparent}
  .w3-nav .w3-l{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
  .w3-credit{right:1rem;left:1rem;bottom:.5rem;text-align:center;font-size:.72rem;background:transparent}
  .w3-tag{font-size:.82rem;white-space:normal;max-width:9.5rem;line-height:1.15}   /* long names wrap on a phone */
}
@media (prefers-reduced-motion:reduce){.w3-pin{display:none!important}.w3-still{display:block!important}}
"""
    js = r"""
// W3: scroll sets the camera's target pose over the orthomosaic; the camera follows on a 'gentle' spring (Spring.solve
// stepped from its own position and velocity); cards, pin labels and the nav state spring in on 'ui', out on 'uiExit'.
const S = window.Spring, D = window.W3, root = document.documentElement, sec = document.querySelector('.w3');
const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
const toStill = (e) => { if (e) console.warn('w3: showing the still map:', e.message || e); root.classList.remove('w3-js'); sec.style.height = ''; };
if (!reduce && root.classList.contains('w3-js')) start().catch(toStill); else toStill();

// a spring that follows a moving target: closed-form step from the current offset and velocity (spring.js maths)
function follower(preset) {
  const P = S.PRESETS[preset];
  return (st, target, dt) => {
    const x0 = st.x - target, v0 = st.v;
    if (Math.abs(x0) < 1e-6 && Math.abs(v0) < 1e-6) { st.x = target; st.v = 0; return false; }
    const a = S.solve(dt, P.zeta, P.omega, 0), b = S.solve(dt, P.zeta, P.omega, 1);
    st.x = target - x0 * a.y + v0 * (b.y - a.y); st.v = -x0 * a.v + v0 * (b.v - a.v); return true;
  };
}

// one element springs in ('ui') or out ('uiExit') from wherever it is now; opacity never overshoots
function toggle(el, on, dy = 18) {
  if (!el || el._on === on) return; el._on = on;
  const from = +getComputedStyle(el).opacity || 0, t0 = performance.now(), tok = (el._tok = (el._tok || 0) + 1);
  if (on) { el.style.visibility = 'visible'; el.classList.add('is-on'); }
  const run = (now) => { if (el._tok !== tok) return; const t = (now - t0) / 1000;
    const p = S.progress(t, { preset: on ? 'ui' : 'uiExit' });
    el.style.opacity = S.clamp01(on ? from + (1 - from) * p : from * (1 - p));
    el.style.transform = on ? `translateY(${(1 - p) * dy}px)` : `translateY(${-p * dy * 0.6}px)`;
    if (t < 0.45) requestAnimationFrame(run);
    else if (!on) { el.style.visibility = 'hidden'; el.classList.remove('is-on'); } };
  requestAnimationFrame(run);
}

async function start() {
  // scroll timeline in units: hold on the overview, then (travel, hold) per place, then travel back out and hold.
  // The section gets its full height first, so the page is its final length before three.js and the map arrive.
  const HOLD0 = 0.5, TRAVEL = 0.9, HOLD = 0.9, HOLDN = 0.8, N = D.places.length;
  const keys = []; let u = 0; keys.push({ a: 0, b: HOLD0 }); u = HOLD0;
  for (let i = 0; i <= N; i++) { u += TRAVEL; keys.push({ a: u, b: u + (i < N ? HOLD : HOLDN) }); u += i < N ? HOLD : HOLDN; }
  const U = u, VH_PER_UNIT = 75;
  sec.style.height = `calc(${(U * VH_PER_UNIT).toFixed(1)}vh + 100vh)`;
  const probe = document.createElement('canvas').getContext('webgl2');
  if (!probe) throw new Error('no WebGL2');
  probe.getExtension('WEBGL_lose_context')?.loseContext();
  const THREE = await import('three');
  const phone = () => innerWidth <= 800;
  const cv = sec.querySelector('.w3-canvas');
  const renderer = new THREE.WebGLRenderer({ canvas: cv, antialias: true, powerPreference: 'high-performance' });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 1.5));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  const bg = new THREE.Color(D.bg), scene = new THREE.Scene(); scene.background = bg;
  const camera = new THREE.PerspectiveCamera(38, 1, 0.05, 200);

  // the ground: the orthomosaic on a plane, 10 units tall; its no-data border melts into the page colour, far ground fades
  const MH = 10, MW = MH * D.aspect;
  const tex = await new THREE.TextureLoader().loadAsync(phone() || renderer.capabilities.maxTextureSize < 4096 ? D.mob : D.desk);
  tex.colorSpace = THREE.SRGBColorSpace; tex.anisotropy = renderer.capabilities.getMaxAnisotropy(); tex.generateMipmaps = true;
  tex.minFilter = THREE.LinearMipmapLinearFilter;
  const mat = new THREE.ShaderMaterial({
    uniforms: { map: { value: tex }, bg: { value: bg }, fogNear: { value: 14 }, fogFar: { value: 34 } },
    vertexShader: `varying vec2 vUv; varying vec3 vView;
      void main(){ vUv = uv; vec4 mv = modelViewMatrix * vec4(position, 1.0); vView = mv.xyz; gl_Position = projectionMatrix * mv; }`,
    fragmentShader: `uniform sampler2D map; uniform vec3 bg; uniform float fogNear, fogFar; varying vec2 vUv; varying vec3 vView;
      void main(){ vec3 t = texture2D(map, vUv).rgb; float m = pow(max(t.r, max(t.g, t.b)), 1.0 / 2.2);
        vec3 c = mix(bg, t, smoothstep(0.03, 0.08, m));
        vec2 e = min(vUv, 1.0 - vUv); c = mix(bg, c, smoothstep(0.0, 0.012, min(e.x, e.y)));
        c = mix(c, bg, 0.85 * smoothstep(fogNear, fogFar, length(vView)));   // distance per pixel, not per vertex
        gl_FragColor = linearToOutputTexel(vec4(c, 1.0)); }`,
  });
  const ground = new THREE.Mesh(new THREE.PlaneGeometry(MW, MH), mat); ground.rotation.x = -Math.PI / 2; scene.add(ground);
  const world = (u, v) => new THREE.Vector3((u - 0.5) * MW, 0, (v - 0.5) * MH);

  // poses: overview, each place, overview again. A pose = target on the ground, ground radius to frame, tilt, heading
  const R = (deg) => (deg * Math.PI) / 180;
  const over = (tilt) => ({ x: 0, z: phone() ? 0.2 : 0.35, rad: MH * (phone() ? 0.36 : 0.44), tilt: R(tilt), yaw: 0 });
  const poses = () => [over(30), ...D.places.map((p) => { const w = world(p.x, p.y); return { x: w.x, z: w.z, rad: p.r * MH, tilt: R(52), yaw: R(p.heading) }; }), over(38)];

  const distFor = (rad) => { const vf = R(camera.fov) / 2, hf = Math.atan(Math.tan(vf) * camera.aspect); return rad / Math.tan(Math.min(vf, hf)) * 1.08; };
  const lerp = (a, b, k) => a + (b - a) * k;
  const progress = () => { const r = sec.getBoundingClientRect(); return Math.min(1, Math.max(0, -r.top / Math.max(1, r.height - innerHeight))) * U; };
  // target pose for a scroll position: hold = the pose; travel = straight across, lifting like a drone between stops
  function target(uu) {
    const P = poses();
    for (let k = 0; k < keys.length; k++) {
      if (uu <= keys[k].b) {
        if (uu >= keys[k].a || k === 0) return { ...P[k], d: distFor(P[k].rad), stop: k };
        const s = (uu - keys[k - 1].b) / (keys[k].a - keys[k - 1].b), A = P[k - 1], B = P[k];
        const hop = Math.hypot(B.x - A.x, B.z - A.z);
        return { x: lerp(A.x, B.x, s), z: lerp(A.z, B.z, s), tilt: lerp(A.tilt, B.tilt, s) - Math.sin(Math.PI * s) * R(10), yaw: lerp(A.yaw, B.yaw, s),
                 d: lerp(distFor(A.rad), distFor(B.rad), s) + Math.sin(Math.PI * s) * hop * 0.55, stop: s < 0.3 ? k - 1 : s > 0.7 ? k : -1 };
      }
    }
    const L = P[P.length - 1]; return { ...L, d: distFor(L.rad), stop: P.length - 1 };
  }

  // camera state (each field a follower on the 'gentle' spring), placed by the pose
  const follow = follower('gentle'), F = ['x', 'z', 'd', 'tilt', 'yaw'], cam = {};
  const size = () => {
    const w = sec.querySelector('.w3-pin').clientWidth, h = sec.querySelector('.w3-pin').clientHeight;
    renderer.setSize(w, h, false); camera.aspect = w / h;
    // shift the focal point away from the cards: right of centre on desktop, up on phones
    if (phone()) camera.setViewOffset(w, h, 0, h * 0.1, w, h); else camera.setViewOffset(w, h, -w * 0.15, 0, w, h);
    camera.updateProjectionMatrix();
  };
  size();
  { const t0 = target(progress()); F.forEach((f) => (cam[f] = { x: t0[f], v: 0 })); }
  const place = () => {
    const T = new THREE.Vector3(cam.x.x, 0, cam.z.x), th = cam.tilt.x, ps = cam.yaw.x, d = cam.d.x;
    camera.position.set(T.x + d * Math.sin(th) * Math.sin(ps), d * Math.cos(th), T.z + d * Math.sin(th) * Math.cos(ps));
    camera.lookAt(T);
  };

  // overlays: the card for the current stop, its pin label, the nav state
  const cards = [...sec.querySelectorAll('.w3-card')], dots = [...sec.querySelectorAll('.w3-dot')], btns = [...sec.querySelectorAll('.w3-nav button')];
  const cardFor = (stop) => cards.find((c) => +c.dataset.i === (stop === 0 ? -1 : stop - 1));
  cards.forEach((c) => { c._on = c.classList.contains('is-on'); if (!c._on) c.style.visibility = 'hidden'; });
  let cur = 0;
  const setStop = (stop) => {
    if (stop === cur) return; const prev = cur; cur = stop;
    toggle(cardFor(prev), false); toggle(cardFor(stop), true);
    dots.forEach((d, i) => { const on = i === stop - 1; d.classList.toggle('is-on', on); toggle(d.querySelector('.w3-tag'), on, 8); });
    btns.forEach((b, i) => (i === stop - 1 ? b.setAttribute('aria-current', 'step') : b.removeAttribute('aria-current')));
  };
  const pinPos = D.places.map((p) => world(p.x, p.y)), v = new THREE.Vector3();
  const placePins = () => {
    const w = renderer.domElement.clientWidth, h = renderer.domElement.clientHeight;
    dots.forEach((el, i) => { v.copy(pinPos[i]).project(camera);
      const x = ((v.x + 1) / 2) * w, y = ((1 - v.y) / 2) * h;
      const off = v.z > 1 || x < -40 || x > w + 40 || y < (phone() ? 150 : 76) || y > h - (phone() ? 60 : 40);          // keep clear of the header bar
      el.style.visibility = off ? 'hidden' : 'visible';
      el.style.transform = `translate(${x - 15}px, ${y - 15}px)`; });
  };

  // the loop runs while the camera is still moving, then sleeps until the next scroll or resize
  let last = 0, running = false;
  const frame = (now) => {
    const dt = Math.min(0.1, (now - last) / 1000 || 1 / 60); last = now;
    const t = target(progress()); let moving = false;
    F.forEach((f) => { if (follow(cam[f], t[f], dt)) moving = true; });
    // a card shows once the camera has arrived over its place, and leaves as the camera lifts off
    const arrived = t.rad == null || (Math.hypot(cam.x.x - t.x, cam.z.x - t.z) < t.rad * 0.5 && Math.abs(cam.d.x - t.d) < t.d * 0.3);
    setStop(arrived ? t.stop : -1);
    mat.uniforms.fogNear.value = cam.d.x * 1.15; mat.uniforms.fogFar.value = cam.d.x * 2.8;
    place(); renderer.render(scene, camera); placePins();
    if (moving) requestAnimationFrame(frame); else running = false;
  };
  const wake = () => { if (!running) { running = true; last = performance.now(); requestAnimationFrame(frame); } };
  addEventListener('scroll', wake, { passive: true });
  addEventListener('resize', () => { size(); wake(); });

  // nav: fly to a place (the page scroll moves on a 'gentle' spring; a wheel or touch takes over)
  let flyTok = 0;
  const stopFly = () => flyTok++;
  ['wheel', 'touchstart', 'keydown'].forEach((e) => addEventListener(e, (ev) => { if (ev.type !== 'keydown' || !ev.target.closest?.('.w3-nav')) stopFly(); }, { passive: true }));
  btns.forEach((b) => b.addEventListener('click', () => {
    const k = keys[+b.dataset.go + 1], uu = (k.a + k.b) / 2;
    const top = sec.getBoundingClientRect().top + scrollY, y1 = top + (uu / U) * (sec.offsetHeight - innerHeight), y0 = scrollY;
    const tok = ++flyTok, t0 = performance.now();
    const run = (now) => { if (tok !== flyTok) return; const t = (now - t0) / 1000;
      const y = S.at(t, { from: y0, to: y1, preset: 'gentle' }); scrollTo({ top: y, behavior: 'instant' });
      if (t < 1.2) requestAnimationFrame(run); };
    requestAnimationFrame(run);
  }));
  root.classList.add('w3-live');
  mat.uniforms.fogNear.value = cam.d.x * 1.15; mat.uniforms.fogFar.value = cam.d.x * 2.8;
  place(); renderer.render(scene, camera); placePins(); wake();
}
"""
    return html_, css, js, {"head": ctx["three"]()}
