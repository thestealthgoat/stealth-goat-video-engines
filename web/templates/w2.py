"""W2 3D isometric scroll world: one small world built from simple shapes in the profile's colours (three.js,
standard/physical materials, a warm key light + a cool rim light, soft contact shadows). Scrolling moves the camera
from scene to scene (the scroll position drives a scene number; the camera follows it on a 'smooth' spring), with
the copy for each scene pinned beside it. A glowing cable carries the "signal" from scene to scene as you arrive.

site.json "hero": {
  "label": "How X works", "eyebrow": "ACME TV · FRIDAY NIGHT", "headline": ["From the field", "to your screen"],
  "text": "...", "cta": {"label": "Where to watch", "href": "#watch"},
  "scenes": [{"kind": "field", "short": "Cameras", "title": "Cameras around the field", "text": "...", "cta": {...}?}, ...]
}
Scene kinds: field (cameras round a pitch), switcher (production trailer cut away), encoder (equipment rack),
stream (servers + the internet cloud), home (living room + houses), blocks (a generic tile for anything else).
With prefers-reduced-motion (or no WebGL) three.js is never fetched: the copy shows as a still, numbered list.
"""
import html, json

E = html.escape


def mix(a, b, k):
    a, b = a.lstrip("#"), b.lstrip("#")
    return "#" + "".join(f"{int(round(int(a[i:i + 2], 16) + (int(b[i:i + 2], 16) - int(a[i:i + 2], 16)) * k)):02x}" for i in (0, 2, 4))


def rgb(h):
    h = h.lstrip("#"); return ",".join(str(int(h[i:i + 2], 16)) for i in (0, 2, 4))


# small flat icons for the still version and the cards (decorative: the copy says what each step is)
ICONS = {
    "field": '<rect x="6" y="20" width="30" height="20" rx="3"/><circle cx="21" cy="30" r="5"/><path d="M36 26l12-6v20l-12-6"/><path d="M14 40l-6 14M28 40l6 14M21 40v14"/>',
    "switcher": '<rect x="6" y="10" width="20" height="13" rx="2"/><rect x="30" y="10" width="20" height="13" rx="2"/><rect x="6" y="34" width="44" height="14" rx="3"/><path d="M13 41h3M21 41h3M29 41h3M37 41h3"/>',
    "encoder": '<rect x="10" y="6" width="36" height="44" rx="3"/><path d="M16 16h24M16 26h24M16 36h24"/><circle cx="38" cy="16" r="1.5"/><circle cx="38" cy="26" r="1.5"/>',
    "stream": '<path d="M16 34a9 9 0 0 1 2-17.8A12 12 0 0 1 41 18a8 8 0 0 1-1 16z"/><path d="M28 38v12M20 46l8 6 8-6"/>',
    "home": '<path d="M8 28L28 10l20 18"/><path d="M13 24v24h30V24"/><rect x="20" y="31" width="16" height="10" rx="1.5"/>',
    "blocks": '<rect x="8" y="26" width="18" height="22" rx="2"/><rect x="30" y="14" width="18" height="34" rx="2"/>',
}


def icon(kind):
    return (f'<svg class="w2-ico" viewBox="0 0 56 56" aria-hidden="true" focusable="false" fill="none" stroke="currentColor" '
            f'stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">{ICONS.get(kind, ICONS["blocks"])}</svg>')


def build(ctx):
    site, pal = ctx["site"], ctx["pal"]; h = site["hero"]; scenes = h["scenes"]
    head = ctx["three"](("environments/RoomEnvironment.js", "geometries/RoundedBoxGeometry.js"))
    bg, text, prim, acc = pal["bg"], pal["text"], pal["primary"], pal["accent"]
    cols = {"bg": bg, "text": text, "accent": acc, "primary": prim,
            "ground": mix(bg, prim, 0.55), "grid": mix(mix(bg, prim, 0.55), text, 0.10),
            "tile": mix(prim, text, 0.10), "tileEdge": mix(prim, bg, 0.45),
            "field": mix(prim, text, 0.20), "line": mix(text, prim, 0.12),
            "light": mix(text, prim, 0.10), "mid": mix(prim, text, 0.35), "dark": mix(bg, "#000000", 0.2),
            "accentDim": mix(acc, prim, 0.35), "floor": mix(text, prim, 0.32), "wall": mix(text, prim, 0.22),
            "skin": mix(text, acc, 0.18), "key": "#ffd8a8", "rim": "#8fb2ff"}
    # fit the headline to the card: measure its longest line in the profile's head font (wide fonts get a smaller size)
    try:
        from PIL import ImageFont
        f = ImageFont.truetype(ctx["P"].font("head"), 100)
        em = max(f.getlength(l) for l in h["headline"]) / 100
    except Exception:
        em = 7.0
    big, phone_sz = min(4.4, 24.5 / em), min(2.6, 19.5 / em)
    cfg = {"c": cols, "scenes": [{"kind": s.get("kind", "blocks")} for s in scenes]}
    def cta(c):
        return f'<a class="btn w2-cta" href="{E(c["href"])}">{E(c["label"])}</a>' if c else ""
    intro = (f'<div class="w2-card w2-intro" data-i="0"><p class="eyebrow">{E(h.get("eyebrow", ""))}</p>'
             f'<h1>{"".join(f"<span>{E(l)}</span>" for l in h["headline"])}</h1>'
             f'<p class="w2-text">{E(h.get("text", ""))}</p>{cta(h.get("cta"))}</div>')
    steps = "".join(f'<li class="w2-card w2-step" data-i="{n + 1}"><div class="w2-tag"><span class="w2-n">{n + 1:02d}</span>{icon(s.get("kind"))}</div>'
                    f'<h2>{E(s["title"])}</h2><p class="w2-text">{E(s["text"])}</p>{cta(s.get("cta"))}</li>' for n, s in enumerate(scenes))
    rail = "".join(f'<button type="button" data-go="{n}" aria-label="{E(lab)}"><span class="lbl">{E(short)}</span><span class="w2-dot" aria-hidden="true"></span></button>'
                   for n, (short, lab) in enumerate([(h.get("short", "Start"), "Back to the start")] +
                                                    [(s.get("short", s["title"]), f'Go to step {n + 1}: {s["title"]}') for n, s in enumerate(scenes)]))
    html_ = f"""<section class="w2" id="{E(h.get('id', 'how'))}" aria-label="{E(h.get('label', 'How it works'))}" style="--n:{len(scenes) + 1}">
<div class="w2-pin"><canvas class="w2-canvas" aria-hidden="true"></canvas>
<div class="w2-cards">{intro}<ol class="w2-steps">{steps}</ol></div>
<nav class="w2-rail" aria-label="Steps">{rail}</nav>
<p class="w2-hint" aria-hidden="true">Scroll</p></div></section>
<script>window.W2 = {json.dumps(cfg)};</script>"""
    css = f"""
.w2{{position:relative;padding:0;max-width:none}}
.w2-pin{{padding:7rem clamp(1rem,6vw,6rem) 2rem;max-width:1280px;margin:0 auto}}
.w2-canvas,.w2-rail,.w2-hint{{display:none}}
.w2-cards{{display:grid;gap:1.2rem}}
.w2-intro h1{{font-size:clamp(2.4rem,6vw,5.2rem)}}.w2-intro h1 span{{display:block}}
.w2-intro .w2-text{{max-width:36rem;font-size:1.15rem}}
.w2-steps{{list-style:none;margin:0;padding:0;display:grid;gap:1rem;grid-template-columns:repeat(auto-fit,minmax(12rem,1fr))}}
.w2-step{{background:var(--bg2);border-radius:12px;padding:1.4rem 1.4rem 1.2rem}}
.w2-step h2{{font-size:clamp(1.6rem,2.6vw,2.3rem);margin-bottom:.35em}}
.w2-step .w2-text{{margin:0 0 .8rem}}
.w2-tag{{display:flex;align-items:center;gap:.7rem;margin-bottom:.6rem;color:var(--accent)}}
.w2-n{{font-family:'Head';font-size:1.5rem;line-height:1}}.w2-ico{{width:2.2rem;height:2.2rem}}
.w2-cta{{margin-top:.4rem}}
.w2.live{{height:calc((var(--n) + .6) * 100vh)}}
.w2.live .w2-pin{{position:sticky;top:0;height:100vh;height:100svh;overflow:hidden;padding:0;max-width:none}}
.w2.live .w2-canvas{{display:block;position:absolute;inset:0;width:100%;height:100%}}
.w2.live .w2-cards{{position:absolute;left:clamp(1rem,5vw,5rem);top:5rem;bottom:2rem;width:min(29rem,38vw);gap:0;align-items:center}}
.w2.live .w2-steps{{display:contents}}
.w2.live .w2-card{{grid-area:1/1;opacity:0;pointer-events:none;background:var(--bg);border:1px solid rgba({rgb(text)},.14);
  border-radius:14px;padding:clamp(1.2rem,2.2vw,2rem);box-shadow:0 18px 50px rgba(0,0,0,.35)}}
.w2.live .w2-card.on{{pointer-events:auto}}
.w2.live .w2-intro h1{{font-size:min({big:.2f}rem,{big / 29 * 38:.2f}vw)}}
.w2.live .w2-rail{{display:flex;flex-direction:column;gap:.15rem;position:absolute;right:clamp(.75rem,2.5vw,2.5rem);top:50%;transform:translateY(-50%);
  background:var(--bg);border:1px solid rgba({rgb(text)},.14);border-radius:14px;padding:.4rem}}
.w2-rail button{{display:flex;align-items:center;justify-content:flex-end;gap:.7rem;background:none;border:0;border-radius:9px;color:var(--muted);
  font:600 .9rem 'BodySB',system-ui,sans-serif;letter-spacing:.08em;text-transform:uppercase;padding:.35rem .6rem;min-height:44px;min-width:44px;cursor:pointer}}
.w2-rail button[aria-current="step"]{{color:var(--text)}}
.w2-dot{{width:10px;height:10px;border-radius:50%;background:var(--muted);flex:none}}
.w2-rail button[aria-current="step"] .w2-dot{{background:var(--accent)}}
.w2.live .w2-hint{{display:block;position:absolute;left:50%;bottom:1.1rem;transform:translateX(-50%);margin:0;color:var(--muted);letter-spacing:.3em;font-size:.8rem;text-transform:uppercase;
  background:var(--bg);border-radius:99px;padding:.35rem .5rem .35rem .8rem}}
.tpl-w2 .top{{background:var(--bg)}}
@media (max-width:760px){{
  .w2.live .w2-cards{{left:.75rem;right:.75rem;width:auto;top:auto;bottom:.75rem;align-items:end}}
  .w2.live .w2-card{{padding:1.1rem 1.2rem}}
  .w2.live .w2-step h2{{font-size:1.7rem}}.w2.live .w2-card .w2-text{{font-size:1rem;margin-bottom:.5rem}}
  .w2.live .w2-intro h1{{font-size:{phone_sz:.2f}rem}}
  .w2.live .w2-tag{{margin-bottom:.3rem}}.w2.live .w2-ico{{width:1.8rem;height:1.8rem}}
  .w2.live .w2-rail{{flex-direction:row;top:calc(var(--w2-head,4.5rem) + .4rem);right:auto;left:50%;transform:translateX(-50%);padding:.2rem}}
  .w2-rail .lbl{{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}}
  .w2-rail button{{justify-content:center;padding:0}}
  .w2.live .w2-hint{{display:none}}
}}
"""
    return html_, css, JS, {"head": head}


JS = r"""
// W2: one isometric 3D world; the scroll position drives a scene number, the camera follows it on a 'smooth' spring,
// the copy for each scene is pinned beside it and springs in ('ui') / out ('uiExit'). Reduced motion: never runs.
const S = window.Spring, reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
const sec = document.querySelector('.w2');
if (sec && !reduce && webgl()) start().catch((e) => { console.warn('w2: showing the still version', e); sec.classList.remove('live'); });

function webgl() { try { const c = document.createElement('canvas'); return !!(c.getContext('webgl2') || c.getContext('webgl')); } catch (e) { return false; } }

async function start() {
  const THREE = await import('three');
  const { RoomEnvironment } = await import('three/addons/environments/RoomEnvironment.js');
  const { RoundedBoxGeometry } = await import('three/addons/geometries/RoundedBoxGeometry.js');
  const C = W2.c, V = THREE.Vector3, pin = sec.querySelector('.w2-pin'), cv = sec.querySelector('.w2-canvas');
  const phone = () => pin.clientWidth < 760;
  const renderer = new THREE.WebGLRenderer({ canvas: cv, antialias: true, powerPreference: 'high-performance' });
  sec.classList.add('live');
  renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 2));
  renderer.toneMapping = THREE.NeutralToneMapping; renderer.toneMappingExposure = 1.05;
  renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap; renderer.shadowMap.autoUpdate = false;
  const scene = new THREE.Scene(); scene.background = new THREE.Color(C.bg);
  const pm = new THREE.PMREMGenerator(renderer); scene.environment = pm.fromScene(new RoomEnvironment(), 0.04).texture; scene.environmentIntensity = 0.35;

  // ---------- materials + helpers
  const std = (c, o = {}) => new THREE.MeshStandardMaterial({ color: c, roughness: 0.78, metalness: 0, ...o });
  const gloss = (c, o = {}) => new THREE.MeshPhysicalMaterial({ color: c, roughness: 0.32, metalness: 0.05, clearcoat: 0.8, clearcoatRoughness: 0.22, ...o });
  const glow = (c, k = 1.4) => new THREE.MeshStandardMaterial({ color: c, emissive: c, emissiveIntensity: k, roughness: 0.4 });
  const M = { tile: std(C.tile), edge: std(C.tileEdge), field: std(C.field), line: std(C.line), light: std(C.light), lightG: gloss(C.light),
    mid: std(C.mid), dark: gloss(C.dark), darkM: std(C.dark), acc: gloss(C.accent), accDim: std(C.accentDim), floor: std(C.floor), wall: std(C.wall),
    skin: std(C.skin), accGlow: glow(C.accent, 1.6), lightGlow: glow(C.light, 0.9), warmGlow: glow('#ffcf8a', 1.2) };
  const B = (w, h, d) => new THREE.BoxGeometry(w, h, d);
  const RB = (w, h, d, r = 0.12) => new RoundedBoxGeometry(w, h, d, 2, Math.min(r, w / 2, h / 2, d / 2) * 0.98);
  const CY = (r, h, n = 16) => new THREE.CylinderGeometry(r, r, h, n);
  function add(p, geo, mat, x, y, z, o = {}) {
    const m = new THREE.Mesh(geo, mat); m.position.set(x, y, z);
    if (o.rx) m.rotation.x = o.rx; if (o.ry) m.rotation.y = o.ry; if (o.rz) m.rotation.z = o.rz;
    m.castShadow = o.cast !== false; m.receiveShadow = true; p.add(m); return m;
  }
  const box = (p, w, h, d, mat, x, y, z, o) => add(p, o && o.r ? RB(w, h, d, o.r) : B(w, h, d), mat, x, y + h / 2, z, o);   // sits on y
  // soft contact shadow: a blurred dark disc under things (the shadow map does the long shadows)
  const blobTex = (() => { const c = document.createElement('canvas'); c.width = c.height = 128; const g = c.getContext('2d');
    const r = g.createRadialGradient(64, 64, 4, 64, 64, 62); r.addColorStop(0, 'rgba(0,0,0,0.55)'); r.addColorStop(0.55, 'rgba(0,0,0,0.22)'); r.addColorStop(1, 'rgba(0,0,0,0)');
    g.fillStyle = r; g.fillRect(0, 0, 128, 128); return new THREE.CanvasTexture(c); })();
  const blobMat = new THREE.MeshBasicMaterial({ map: blobTex, transparent: true, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -2 });
  function blob(p, x, z, w, d, y = 0.02) { const m = new THREE.Mesh(new THREE.PlaneGeometry(w, d), blobMat); m.rotation.x = -Math.PI / 2; m.position.set(x, y, z); m.renderOrder = 1; p.add(m); return m; }
  // the picture on every screen: a small drawn broadcast frame (field, players, score bar, LIVE tag)
  const screenTex = (() => { const c = document.createElement('canvas'); c.width = 320; c.height = 180; const g = c.getContext('2d');
    g.fillStyle = C.bg; g.fillRect(0, 0, 320, 180); g.fillStyle = C.mid; g.fillRect(0, 0, 320, 34);          // stands
    g.fillStyle = C.field; g.beginPath(); g.moveTo(40, 40); g.lineTo(280, 40); g.lineTo(340, 180); g.lineTo(-20, 180); g.closePath(); g.fill();   // field in perspective
    g.strokeStyle = C.line; g.lineWidth = 2; for (let i = 0; i <= 8; i++) { const u = i / 8; g.beginPath(); g.moveTo(40 + 240 * u, 40); g.lineTo(-20 + 360 * u, 180); g.stroke(); }
    for (let i = 0; i < 6; i++) { g.fillStyle = C.light; g.beginPath(); g.arc(128 + (i % 3) * 16, 92 + (i > 2 ? 18 : 0), 5, 0, 7); g.fill();
      g.fillStyle = C.accent; g.beginPath(); g.arc(186 + (i % 3) * 16, 92 + (i > 2 ? 18 : 0), 5, 0, 7); g.fill(); }
    g.fillStyle = C.bg; g.fillRect(16, 146, 170, 22); g.fillStyle = C.accent; g.fillRect(16, 146, 40, 22); g.fillStyle = C.light; g.fillRect(64, 153, 50, 8); g.fillRect(124, 153, 50, 8);
    g.fillStyle = C.accent; g.fillRect(262, 12, 46, 18); g.fillStyle = '#ffffff'; g.font = 'bold 13px sans-serif'; g.fillText('LIVE', 270, 26);
    const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t; })();
  const screen = (crop) => { const t = screenTex.clone(); if (crop) { t.repeat.set(crop[0], crop[0]); t.offset.set(crop[1], crop[2]); t.wrapS = t.wrapT = THREE.ClampToEdgeWrapping; } t.needsUpdate = true;
    return new THREE.MeshBasicMaterial({ map: t, toneMapped: false }); };
  function tile(g, w, d) { box(g, w, 1.2, d, M.tile, 0, -1.2, 0, { r: 0.35 }); box(g, w + 0.9, 0.7, d + 0.9, M.edge, 0, -1.95, 0, { r: 0.3 }); return { hw: w / 2, hd: d / 2 }; }
  function person(p, x, y, z, mat, ry = 0) { const g = new THREE.Group(); g.position.set(x, y, z); g.rotation.y = ry; add(g, new THREE.CapsuleGeometry(0.26, 0.42, 4, 10), mat, 0, 0.47, 0); add(g, new THREE.SphereGeometry(0.2, 16, 12), M.skin, 0, 1.08, 0); p.add(g); return g; }
  function chair(p, x, z, ry = 0) { const g = new THREE.Group(); g.position.set(x, 0, z); g.rotation.y = ry; add(g, CY(0.05, 0.5, 8), M.darkM, 0, 0.25, 0); box(g, 0.75, 0.12, 0.75, M.darkM, 0, 0.5, 0); box(g, 0.75, 0.75, 0.1, M.darkM, 0, 0.6, 0.35); p.add(g); return g; }
  function tree(p, x, z, s = 1) { add(p, CY(0.12 * s, 0.8 * s, 8), M.darkM, x, 0.4 * s, z); add(p, new THREE.ConeGeometry(0.75 * s, 1.9 * s, 10), M.mid, x, 1.7 * s, z); blob(p, x, z, 2 * s, 2 * s); }

  // ---------- scene kinds: each builds on a tile and returns its cable anchors (local), in = where the signal arrives, out = where it leaves
  const KINDS = {
    field(g) {
      const t = tile(g, 25, 18);
      box(g, 21, 0.06, 11.6, M.field, 0, 0, 0, { cast: false });
      for (const s of [-1, 1]) box(g, 1.9, 0.07, 11.6, M.accDim, s * 9.55, 0, 0, { cast: false });
      for (let i = 0; i <= 10; i++) box(g, 0.08, 0.08, 11.6, M.line, -8.6 + i * 1.72, 0, 0, { cast: false });
      for (const s of [-1, 1]) { const x = s * 10.9; add(g, CY(0.07, 1.5, 8), M.light, x, 0.75, 0); box(g, 0.1, 0.1, 2.1, M.light, x, 1.45, 0);
        for (const z of [-1, 1]) add(g, CY(0.05, 1.8, 8), M.light, x, 2.4, z * 1.02); }
      const lineup = [[-0.5, -2.4], [-0.5, -1.2], [-0.5, 0], [-0.5, 1.2], [-0.5, 2.4], [-1.9, 0], [-1.6, 3.6]];
      lineup.forEach(([x, z]) => { person(g, x, 0.05, z, M.light, Math.PI / 2); blob(g, x, z, 1, 1, 0.07); });
      lineup.forEach(([x, z], i) => { const xx = 0.6 + (i > 4 ? 1.5 : 0), zz = z + (i === 6 ? -1 : 0.3); person(g, xx, 0.05, zz, M.acc, -Math.PI / 2); blob(g, xx, zz, 1, 1, 0.07); });
      const cams = [[-4, 7.6, 0], [4, 7.6, 0], [-11.6, -1.5, 0], [5.5, -7.6, 3.2]];
      const junction = new V(11.4, 0.25, 7.6); box(g, 0.9, 0.7, 0.6, M.dark, junction.x, 0, junction.z); box(g, 0.2, 0.12, 0.05, M.accGlow, junction.x + 0.2, 0.45, junction.z + 0.31, { cast: false });
      const links = [];
      cams.forEach(([x, z, hgt], i) => {
        if (hgt) { for (const [dx, dz] of [[-0.9, -0.9], [0.9, -0.9], [-0.9, 0.9], [0.9, 0.9]]) add(g, CY(0.07, hgt, 6), M.mid, x + dx, hgt / 2, z + dz);
          box(g, 2.3, 0.15, 2.3, M.mid, x, hgt, z); }
        const cam = new THREE.Group(); cam.position.set(x, hgt ? hgt + 0.15 : 0, z); cam.rotation.y = Math.atan2(-x, -z); g.add(cam);
        for (let k = 0; k < 3; k++) { const a = k * 2.094; const leg = add(cam, CY(0.04, 1.5, 6), M.darkM, Math.sin(a) * 0.35, 0.7, Math.cos(a) * 0.35); leg.rotation.set(Math.cos(a) * 0.25, 0, -Math.sin(a) * 0.25); }
        box(cam, 0.55, 0.5, 0.95, M.dark, 0, 1.4, 0, { r: 0.08 }); add(cam, CY(0.17, 0.5, 16), M.dark, 0, 1.65, 0.68, { rx: Math.PI / 2 });
        add(cam, new THREE.CircleGeometry(0.13, 16), M.lightGlow, 0, 1.65, 0.935, { cast: false }); box(cam, 0.3, 0.22, 0.3, M.dark, 0.3, 1.9, -0.2);
        add(cam, new THREE.SphereGeometry(0.07, 10, 8), M.accGlow, 0, 1.95, 0.25, { cast: false });
        person(cam, -0.25, 0, -0.95, M.mid); blob(g, x, z, 2.4, 2.4, hgt + 0.03);
        const lane = 6.4 + i * 0.2, end = [new V(junction.x - 1.2, 0.07, lane), new V(junction.x - 0.45, 0.2, junction.z)];
        const route = { 0: [[x, lane]], 1: [[x, lane]], 2: [[x, lane]], 3: [[11.9, z], [11.9, 5.4]] }[i] || [[x, lane]];
        links.push({ pts: [new V(x, 0.07, z), ...route.map(([a, b]) => new V(a, 0.07, b)), ...(i === 3 ? [end[1]] : end)], r: 0.06 });
      });
      return { t, out: junction, links };
    },
    switcher(g) {
      const t = tile(g, 19, 17), T = new THREE.Group(); T.position.set(0.5, 0, -1); g.add(T);
      box(T, 13, 0.4, 5.6, M.darkM, 0, 0.4, 0);
      for (const x of [-4.2, -3, 3, 4.2]) for (const z of [-2.75, 2.75]) add(T, CY(0.55, 0.42, 20), M.dark, x, 0.55, z, { rx: Math.PI / 2 });
      blob(g, 0.5, -1, 15, 8.5);
      box(T, 13, 0.25, 6, M.floor, 0, 0.8, 0);
      box(T, 13, 3.3, 0.25, M.wall, 0, 1.05, -2.88); box(T, 0.25, 3.3, 6, M.wall, -6.38, 1.05, 0);
      box(T, 13, 0.75, 0.25, M.light, 0, 1.05, 2.88); box(T, 13.02, 0.16, 0.27, M.acc, 0, 1.45, 2.88, { cast: false }); box(T, 0.25, 0.75, 6, M.light, 6.38, 1.05, 0);
      for (let i = 0; i < 3; i++) box(T, 0.55, 0.95 - i * 0.3, 1.4, M.mid, 6.8 + i * 0.55, 0, 1.2);
      box(T, 10.5, 0.95, 1.4, M.mid, -0.3, 1.05, -2.0);
      const scr = [[0.45, 0.05, 0.4], [0.45, 0.5, 0.45], [0.5, 0.25, 0.1], [0.4, 0.6, 0.1], [0.5, 0, 0], [0.42, 0.3, 0.5], [0.45, 0.55, 0.3], [0.5, 0.1, 0.25]];
      for (let r = 0; r < 2; r++) for (let k = 0; k < 4; k++) { const x = -4.2 + k * 2.55, y = 2.35 + r * 1.35, prog = r === 1 && k === 1;
        box(T, 2.3, 1.2, 0.12, prog ? M.accGlow : M.dark, x, y, -2.68, { cast: false });
        add(T, new THREE.PlaneGeometry(2.08, 1.0), screen(scr[r * 4 + k]), x, y + 0.6, -2.61, { cast: false }); }
      const P = new THREE.Group(); P.position.set(0.4, 2.12, -1.7); P.rotation.x = 0.28; T.add(P);
      box(P, 4.2, 0.18, 1.0, M.dark, 0, 0, 0, { r: 0.05 });
      for (let r = 0; r < 3; r++) for (let k = 0; k < 10; k++) { const on = (r === 0 && k === 3) ? M.accGlow : (r === 1 && k === 6) ? M.lightGlow : M.mid;
        box(P, 0.24, 0.08, 0.2, on, -1.75 + k * 0.33, 0.18, -0.3 + r * 0.3, { cast: false }); }
      box(P, 0.12, 0.45, 0.12, M.light, 1.85, 0.18, 0.1);
      box(T, 1.1, 0.06, 0.45, M.dark, -3.4, 2.0, -1.75); box(T, 1.1, 0.7, 0.06, M.dark, -3.4, 2.06, -2.05, { rx: -0.2 });
      chair(T, 0.4, -0.3, Math.PI); chair(T, -3.4, -0.3, Math.PI); person(T, 0.4, 1.35, -0.5, M.mid, Math.PI); person(T, -3.4, 1.35, -0.5, M.accDim, Math.PI);
      tree(g, 7.2, -6.2, 1.1); tree(g, -8.2, 5.6, 0.9);
      const inn = new V(-7.4, 0.1, 5.4), out = new V(8.2, 0.1, -4.8);
      return { t, ins: [inn], out, links: [
        { pts: [inn, new V(-6.6, 0.1, 3.0), new V(-6.0, 1.95, 2.0), new V(-5.0, 1.12, 1.2), new V(-1.5, 1.12, -1.9), new V(0.2, 1.12, -2.15)], r: 0.08 },
        { pts: [new V(2.5, 1.12, -2.15), new V(6.0, 1.12, -2.2), new V(6.95, 1.95, -2.6), new V(7.6, 0.1, -3.4), out], r: 0.08 }] };
    },
    encoder(g) {
      const t = tile(g, 16, 16);
      box(g, 2.8, 5.4, 2.3, M.dark, -1.8, 0, -2.6, { r: 0.12 }); blob(g, -1.8, -2.6, 4.4, 4);
      for (let i = 0; i < 9; i++) { const enc = i === 5, y = 0.45 + i * 0.52;
        box(g, 2.3, 0.4, 0.12, enc ? M.acc : M.mid, -1.8, y, -1.42, { cast: false });
        for (let k = 0; k < 3; k++) box(g, 0.09, 0.09, 0.05, (k + i) % 3 ? M.lightGlow : M.accGlow, -0.95 + k * 0.17, y + 0.15, -1.34, { cast: false });
        if (enc) box(g, 0.9, 0.16, 0.05, M.lightGlow, -2.3, y + 0.12, -1.34, { cast: false }); }
      box(g, 3.4, 0.12, 1.7, M.mid, 3, 1.55, 0.6); for (const [x, z] of [[1.5, -0.1], [4.5, -0.1], [1.5, 1.3], [4.5, 1.3]]) add(g, CY(0.06, 1.55, 8), M.darkM, x, 0.78, z);
      blob(g, 3, 0.6, 4.6, 3);
      box(g, 1.2, 0.06, 0.8, M.dark, 2.6, 1.67, 0.7); const lid = add(g, new THREE.PlaneGeometry(1.1, 0.68), screen([0.8, 0.1, 0.1]), 2.6, 2.05, 0.3, { rx: -0.25, cast: false });
      box(g, 1.2, 0.74, 0.04, M.dark, 2.6, 1.68, 0.27, { rx: -0.25 }); lid.position.z = 0.3;
      box(g, 0.9, 0.22, 0.6, M.dark, 4.1, 1.61, 0.5); for (let k = 0; k < 4; k++) box(g, 0.07, 0.07, 0.04, M.accGlow, 3.8 + k * 0.17, 1.75, 0.81, { cast: false });
      chair(g, 2.8, 2.2, Math.PI); person(g, 2.8, 0.55, 2.2, M.light, Math.PI);
      tree(g, 5.5, -5.2, 1); tree(g, -5.8, 4.8, 0.8);
      const inn = new V(-3.2, 0.1, 6.8), out = new V(6.8, 0.1, -3.4);
      return { t, ins: [inn], out, links: [{ pts: [inn, new V(-3.2, 0.1, 1.2), new V(-2.6, 0.1, -1.0), new V(-2.4, 0.5, -1.38)], r: 0.08 }, { pts: [new V(-1.2, 0.5, -1.38), new V(-0.6, 0.1, -1.1), new V(3, 0.1, -3.3), out], r: 0.08 }] };
    },
    stream(g) {
      const t = tile(g, 18, 16);
      for (let k = 0; k < 5; k++) { const x = -4 + k * 2; box(g, 1.6, 3.6, 1.4, M.dark, x, 0, -3, { r: 0.08 });
        for (let s = 0; s < 3; s++) box(g, 0.06, 2.9, 0.04, s === 1 ? M.accGlow : M.lightGlow, x - 0.45 + s * 0.45, 0.35, -2.28, { cast: false }); }
      for (let k = 0; k < 4; k++) { const x = -3 + k * 2; box(g, 1.6, 2.4, 1.4, M.dark, x, 0, 1.2, { r: 0.08 });
        for (let s = 0; s < 3; s++) box(g, 0.06, 1.8, 0.04, s === 1 ? M.lightGlow : M.accGlow, x - 0.45 + s * 0.45, 0.3, 1.92, { cast: false }); }
      blob(g, 0, -3, 11.5, 3.2); blob(g, 0, 1.2, 9.5, 3.2);
      const cl = new THREE.Group(); cl.position.set(0, 9.6, -1); g.add(cl);
      const cm = new THREE.MeshPhysicalMaterial({ color: C.light, roughness: 0.55, sheen: 1, sheenColor: new THREE.Color(C.rim), sheenRoughness: 0.6 });
      for (const [x, y, z, r] of [[0, 0, 0, 2.3], [-2.3, -0.5, 0.4, 1.7], [2.2, -0.4, -0.2, 1.8], [-1, 0.9, -1, 1.6], [1.2, 0.8, 0.9, 1.5], [3.6, -0.9, 0.5, 1.1], [-3.8, -1, -0.5, 1.1]])
        add(cl, new THREE.SphereGeometry(r, 28, 20), cm, x, y, z);
      blob(g, 0, -1, 10, 6, 0.03);
      const out = new V(0, 8.6, -1), inn = new V(-7.6, 0.1, 6.4);
      const links = [{ pts: [inn, new V(-6.2, 0.1, 3.4), new V(-5.4, 0.1, -1.4), new V(-4, 0.25, -2.26)], r: 0.08 }];
      for (const x of [-4, 0, 4]) links.push({ air: true, a: new V(x, 3.65, -3), b: new V(x * 0.5, 7.9, -1), r: 0.05 });
      return { t, ins: [inn], out, air: true, links };
    },
    home(g) {
      const t = tile(g, 23, 19), R = new THREE.Group(); R.position.set(-3, 0, -0.5); g.add(R);
      box(R, 10, 0.25, 8, M.floor, 0, 0, 0); box(R, 10, 4.2, 0.3, M.wall, 0, 0.25, -3.85); box(R, 0.3, 4.2, 8, M.wall, -4.85, 0.25, 0);
      add(R, new THREE.PlaneGeometry(2.4, 1.6), new THREE.MeshBasicMaterial({ color: C.bg }), -4.69, 2.7, 0.8, { ry: Math.PI / 2, cast: false });
      box(R, 0.12, 0.12, 2.6, M.light, -4.66, 1.82, 0.8); box(R, 3.6, 0.06, 2.6, M.accDim, 0.4, 0.25, 0.9, { cast: false });
      box(R, 3.6, 0.7, 0.9, M.dark, 0.4, 0.25, -3.1);
      box(R, 4.0, 2.3, 0.16, M.dark, 0.4, 1.15, -3.1, { r: 0.05 }); add(R, new THREE.PlaneGeometry(3.75, 2.05), screen(), 0.4, 2.3, -3.01, { cast: false });
      const sofa = std(C.mid); box(R, 4.4, 0.6, 1.5, sofa, 0.4, 0.25, 2.3, { r: 0.15 }); box(R, 4.4, 1.2, 0.45, sofa, 0.4, 0.25, 3.05, { r: 0.15 });
      for (const s of [-1, 1]) box(R, 0.45, 0.95, 1.5, sofa, 0.4 + s * 2.2, 0.25, 2.3, { r: 0.15 });
      person(R, -0.6, 0.75, 2.35, M.light, Math.PI); person(R, 1.4, 0.75, 2.35, M.accDim, Math.PI);
      box(R, 2.2, 0.1, 1, M.mid, 0.4, 0.75, 0.4); for (const [x, z] of [[-0.55, 0], [1.35, 0], [-0.55, 0.8], [1.35, 0.8]]) box(R, 0.08, 0.5, 0.08, M.darkM, x, 0.25, z);
      box(R, 0.35, 0.03, 0.62, M.dark, 0.9, 0.85, 0.4); add(R, new THREE.PlaneGeometry(0.3, 0.55), screen([0.6, 0.2, 0.2]), 0.9, 0.875, 0.4, { rx: -Math.PI / 2, cast: false });
      add(R, CY(0.05, 1.8, 8), M.darkM, -3.9, 1.15, -2.9); add(R, new THREE.ConeGeometry(0.5, 0.6, 16, 1, true), M.warmGlow, -3.9, 2.2, -2.9, { cast: false });
      blob(g, -3, -0.5, 12, 10, 0.03);
      const houses = [[7.2, -5.2], [7.6, 3.6]], ins = [new V(-7.85, 4.5, -4.35)];
      for (const [x, z] of houses) { box(g, 3.6, 2.6, 3.2, M.light, x, 0, z); add(g, new THREE.ConeGeometry(2.75, 1.6, 4), M.accDim, x, 3.4, z, { ry: Math.PI / 4 });
        for (const dx of [-0.85, 0.85]) box(g, 0.8, 0.7, 0.05, dx < 0 ? M.warmGlow : M.lightGlow, x + dx, 1.3, z + 1.62, { cast: false });
        box(g, 0.05, 0.7, 0.8, M.warmGlow, x + 1.82, 1.3, z, { cast: false }); box(g, 0.8, 1.4, 0.05, M.dark, x + 0.4, 0, z + 1.62, { cast: false });
        blob(g, x, z, 5.6, 5.2); ins.push(new V(x, 4.15, z)); }
      tree(g, 4.6, -1, 1); tree(g, 10, 0, 0.8); tree(g, 3.8, 7.6, 0.9);
      return { t, ins, links: [{ pts: [new V(-7.85, 4.5, -4.35), new V(-6, 4.5, -4.35), new V(-4, 4.5, -4.35), new V(-2.9, 4.2, -4.1), new V(-2.6, 3.5, -3.75)], r: 0.05 }] };
    },
    blocks(g) {
      const t = tile(g, 16, 16);
      box(g, 3, 3, 3, M.light, -2, 0, -2, { r: 0.2 }); box(g, 2.2, 5, 2.2, M.acc, 2.2, 0, -1, { r: 0.2 }); box(g, 3.5, 1.4, 2.5, M.mid, 0.5, 0, 3, { r: 0.2 });
      blob(g, -2, -2, 5, 5); blob(g, 2.2, -1, 4, 4); blob(g, 0.5, 3, 5.5, 4.5);
      return { t, ins: [new V(-7.2, 0.1, 0)], out: new V(7.2, 0.1, 0), links: [] };
    },
  };

  // ---------- lay the scenes out along the screen's right-hand direction (isometric: camera on the (1,1,1) diagonal)
  const BACK = new V(1, 1, 1).normalize(), RIGHT = new V(1, 0, -1).normalize(), DOWN = new V(1, 0, 1).normalize();
  const UP = new V().crossVectors(BACK, RIGHT).normalize();   // screen up
  const world = new THREE.Group(); scene.add(world);
  const zig = [0, 6, -4, 5, -3, 4, -2], gap = 30;
  const built = W2.scenes.map((s, k) => {
    const g = new THREE.Group(); g.position.copy(RIGHT.clone().multiplyScalar(k * gap).addScaledVector(DOWN, zig[k % zig.length]));
    g.position.x = Math.round(g.position.x * 2) / 2; g.position.z = Math.round(g.position.z * 2) / 2; world.add(g);
    const r = (KINDS[s.kind] || KINDS.blocks)(g); r.g = g; return r;
  });
  const ground = new THREE.Mesh(new THREE.PlaneGeometry(900, 900), std(C.ground, { roughness: 0.95 })); ground.rotation.x = -Math.PI / 2; ground.position.y = -2.3; ground.receiveShadow = true; scene.add(ground);
  const grid = new THREE.GridHelper(900, 300, C.grid, C.grid); grid.position.y = -2.28; grid.material.transparent = true; grid.material.opacity = 0.5; scene.add(grid);
  world.updateMatrixWorld(true);

  // ---------- cables: inside each scene, and from each scene's out to the next scene's ins. Each lights up as the camera arrives.
  const cables = [];
  const L = (g, v) => g.localToWorld(v.clone());
  const exitDist = (a, d, t) => { let m = 1e9; if (d.x) m = Math.min(m, ((d.x > 0 ? t.hw : -t.hw) - a.x) / d.x); if (d.z) m = Math.min(m, ((d.z > 0 ? t.hd : -t.hd) - a.z) / d.z); return Math.max(0, m); };
  function drape(ga, a, ta, gb, b, tb) {          // a ground cable: off the edge of one tile, along the ground, up onto the next
    const A = L(ga, a), Bw = L(gb, b), d = Bw.clone().sub(A).setY(0).normalize(), nd = d.clone().negate();
    const ea = A.clone().addScaledVector(d, exitDist(a, d, ta) + 0.55), eb = Bw.clone().addScaledVector(nd, exitDist(b, nd, tb) + 0.55);
    const pts = [A, ea.clone().setY(0.05), ea.clone().addScaledVector(d, 0.5).setY(-1.2), ea.clone().addScaledVector(d, 1.4).setY(-2.2),
      eb.clone().addScaledVector(nd, 1.4).setY(-2.2), eb.clone().addScaledVector(nd, 0.5).setY(-1.2), eb.clone().setY(0.05), Bw];
    return new THREE.CatmullRomCurve3(pts, false, 'centripetal');
  }
  function arc(A, Bw, lift) { const m = A.clone().lerp(Bw, 0.5); m.y = Math.max(A.y, Bw.y) + lift; return new THREE.QuadraticBezierCurve3(A, m, Bw); }
  function cable(curve, r, at, air) {
    const mat = new THREE.MeshStandardMaterial({ color: C.mid, emissive: C.accent, emissiveIntensity: 0, roughness: 0.45, transparent: !!air, opacity: air ? 0.35 : 1 });
    const n = Math.max(24, Math.round(curve.getLength() * 3));
    const m = new THREE.Mesh(new THREE.TubeGeometry(curve, n, r, 8, false), mat); m.castShadow = !air; m.receiveShadow = true; scene.add(m);
    cables.push({ curve, mat, at, air, len: curve.getLength(), lvl: 0, on: false, t0: 0, from: 0, pulses: Math.max(2, Math.round(curve.getLength() / 3.2)) });
  }
  built.forEach((b, k) => {
    for (const l of b.links || []) {
      if (l.air) cable(arc(L(b.g, l.a), L(b.g, l.b), 1.2), l.r, k + 1 - 0.45, true);
      else cable(new THREE.CatmullRomCurve3(l.pts.map((p) => L(b.g, p)), false, 'centripetal'), l.r, k + 1 - 0.45, false);
    }
    const nx = built[k + 1]; if (!nx || !b.out) return;
    for (const inn of nx.ins || []) {
      if (b.air) { const A = L(b.g, b.out), Bw = L(nx.g, inn); cable(arc(A, Bw, 1 + A.distanceTo(Bw) * 0.07), 0.06, k + 1.5, true); }
      else cable(drape(b.g, b.out, b.t, nx.g, inn, nx.t), 0.12, k + 1.5, false);
    }
  });
  const nP = cables.reduce((s, c) => s + c.pulses, 0);
  const pulses = new THREE.InstancedMesh(new THREE.SphereGeometry(0.2, 12, 8), new THREE.MeshBasicMaterial({ color: new THREE.Color(C.accent).lerp(new THREE.Color('#ffffff'), 0.45), toneMapped: false }), nP);
  pulses.frustumCulled = false; scene.add(pulses);

  // ---------- lights: warm key (with the one long shadow pass), cool rim from behind, soft sky fill
  const wb = new THREE.Box3().setFromObject(world), wc = wb.getCenter(new V()), wr = wb.getSize(new V()).length() / 2;
  scene.add(new THREE.HemisphereLight(new THREE.Color(C.light).lerp(new THREE.Color(C.rim), 0.4), C.ground, 0.9));
  const key = new THREE.DirectionalLight(C.key, 2.6); key.position.copy(wc).add(new V(-0.55, 1, 0.75).normalize().multiplyScalar(wr + 40)); key.target.position.copy(wc);
  key.castShadow = true; const sc = key.shadow.camera; sc.left = sc.bottom = -wr; sc.right = sc.top = wr; sc.near = 1; sc.far = 2 * wr + 90;
  const maxT = renderer.capabilities.maxTextureSize; key.shadow.mapSize.set(Math.min(4096, maxT), Math.min(4096, maxT)); key.shadow.bias = -0.0004; key.shadow.normalBias = 0.03;
  scene.add(key, key.target);
  const rim = new THREE.DirectionalLight(C.rim, 1.9); rim.position.copy(wc).add(new V(-1, 0.55, -1).multiplyScalar(60)); rim.target.position.copy(wc); scene.add(rim, rim.target);

  // ---------- camera keyframes: frame 0 = the whole world, then one per scene (its box projected on the screen axes)
  const frame = (bx) => { const ctr = bx.getCenter(new V()); let w = 0, h = 0;
    for (let i = 0; i < 8; i++) { const p = new V(i & 1 ? bx.max.x : bx.min.x, i & 2 ? bx.max.y : bx.min.y, i & 4 ? bx.max.z : bx.min.z).sub(ctr);
      w = Math.max(w, Math.abs(p.dot(RIGHT))); h = Math.max(h, Math.abs(p.dot(UP))); } return { ctr, w: 2 * w, h: 2 * h }; };
  const keys = [frame(wb), ...built.map((b) => frame(new THREE.Box3().setFromObject(b.g)))];
  const N = keys.length, D = 220;
  const cam = new THREE.OrthographicCamera(-1, 1, 1, -1, 1, 600);
  scene.fog = new THREE.Fog(C.bg, D + 25, D + 150);
  function aimAt(c) {      // c: scene number (float)
    const i = Math.max(0, Math.min(N - 2, Math.floor(c))), f = Math.max(0, Math.min(1, c - i)), a = keys[i], b = keys[i + 1];
    const ctr = a.ctr.clone().lerp(b.ctr, f), w = a.w + (b.w - a.w) * f, h = a.h + (b.h - a.h) * f;
    const W = pin.clientWidth, H = pin.clientHeight, asp = W / H, ph = phone(), R = free;
    const aw = R.aw + (ph ? 0 : 0.06 * (1 - Math.min(1, c))), ah = R.ah, fx = R.fx, fy = R.fy;   // the free area beside / above the copy
    const wk = 1 - 0.12 * (1 - Math.min(1, c));                                     // the overview may tuck its ends under the card
    let size = Math.max((h * 1.06) / ah, (w * wk * 1.06) / (asp * aw));
    if (ph) size = Math.min(size, 150);
    size *= zoomK.x;
    const sw = size * asp;
    cam.left = -fx * sw; cam.right = (1 - fx) * sw; cam.top = fy * size; cam.bottom = -(1 - fy) * size;
    cam.position.copy(ctr).addScaledVector(BACK, D); cam.up.set(0, 1, 0); cam.lookAt(ctr); cam.updateProjectionMatrix();
  }

  // ---------- springs (Spring.at / velocity, re-solved each frame so a moving target stays smooth)
  class Follow { constructor(x, preset) { this.x = x; this.v = 0; this.p = preset; }
    step(to, dt) { const d = to - this.x; if (Math.abs(d) < 1e-4 && Math.abs(this.v) < 1e-3) { this.x = to; this.v = 0; return to; }
      if (Math.abs(d) < 1e-4) { this.x = to; this.v = 0; return to; }
      const o = { from: this.x, to, preset: this.p, v0: this.v / d }; this.x = S.at(dt, o); this.v = S.velocity(dt, o); return this.x; } }
  const fc = new Follow(0, 'smooth'), zoomK = new Follow(1.22, 'gentle');
  const tween = (el, preset, fn) => { const t0 = performance.now(), id = (el._w2 = (el._w2 || 0) + 1);
    const run = (now) => { if (el._w2 !== id) return; const t = (now - t0) / 1000, p = S.progress(t, { preset }); fn(p); if (t < 0.6) requestAnimationFrame(run); else fn(1); };
    requestAnimationFrame(run); };

  // ---------- copy: one card per scene, pinned; 'ui' in, 'uiExit' out, opacity clamped
  const cards = [...sec.querySelectorAll('.w2-card')], dots = [...sec.querySelectorAll('.w2-rail button')], hint = sec.querySelector('.w2-hint');
  let cur = -1;
  function setCard(i) {
    if (i === cur) return; const prev = cur, first = cur < 0; cur = i;
    if (first) { cards.forEach((el, k) => { el.classList.toggle('on', k === i); el.style.opacity = k === i ? 1 : 0; }); }
    cards.forEach((el, k) => { el.classList.toggle('on', k === i);
      const o0 = +(el.style.opacity || 0);
      if (first) return;
      if (k === i) tween(el, 'ui', (p) => { el.style.opacity = S.clamp01(o0 + (1 - o0) * p); el.style.transform = `translateY(${(1 - p) * 18}px)`; });
      else if (k === prev || o0 > 0) tween(el, 'uiExit', (p) => { el.style.opacity = S.clamp01(o0 * (1 - p)); el.style.transform = `translateY(${-p * 12}px)`; }); });
    dots.forEach((d, k) => { d.setAttribute('aria-current', k === i ? 'step' : 'false'); const dot = d.querySelector('.w2-dot'), on = k === i;
      tween(dot, on ? 'ui' : 'uiExit', (p) => { dot.style.transform = `scale(${on ? 1 + 0.5 * p : 1.5 - 0.5 * p})`; }); });
  }
  // scroll -> scene number: each scene holds, then the camera travels in the back half of its slot
  const prog = () => { const r = sec.getBoundingClientRect(), span = r.height - innerHeight; return span > 0 ? Math.min(1, Math.max(0, -r.top / span)) : 0; };
  const sceneAt = (p) => { const x = Math.min(N - 1, Math.max(0, p * (N - 1 + 0.6) - 0.3)), k = Math.floor(x); return Math.min(N - 1, k + Math.min(1, Math.max(0, (x - k - 0.3) / 0.5))); };
  const scrollFor = (k) => { const p = (k + (k ? 0.05 : -0.3) + 0.3) / (N - 1 + 0.6); return sec.offsetTop + Math.max(0, p) * (sec.offsetHeight - innerHeight); };
  let jumpId = 0;
  function jump(k) { const from = scrollY, to = scrollFor(k), t0 = performance.now(), id = ++jumpId;
    const run = (now) => { if (id !== jumpId) return; const t = (now - t0) / 1000; window.scrollTo({ top: S.at(t, { from, to, preset: 'smooth' }), behavior: 'instant' }); if (t < 0.9) requestAnimationFrame(run); };
    requestAnimationFrame(run); }
  addEventListener('wheel', () => { jumpId++; }, { passive: true }); addEventListener('touchstart', () => { jumpId++; }, { passive: true });
  dots.forEach((d) => d.addEventListener('click', () => jump(+d.dataset.go)));
  cards.forEach((el, k) => el.addEventListener('focusin', () => { if (k !== cur) jump(k); }));
  let hintOn = true;

  // ---------- size, first frame, loop
  // the free area of the screen the scene is framed into: between the copy and the step rail (desktop), or between
  // the rail and the tallest card (phone); measured from the layout, so any font or copy length frames correctly
  let free = { fx: 0.6, fy: 0.5, aw: 0.5, ah: 0.8 };
  function measure() {
    const head = document.querySelector('.top'), hb = head ? head.getBoundingClientRect().bottom : 0;
    pin.style.setProperty('--w2-head', hb + 'px');
    const P = pin.getBoundingClientRect(), W = P.width, H = P.height, rl = sec.querySelector('.w2-rail').getBoundingClientRect();
    const tops = cards.map((el) => el.getBoundingClientRect()), pad = 14;
    let l, r, t, b;
    if (phone()) { l = 0; r = W; t = rl.bottom - P.top + pad; b = Math.min(...tops.map((x) => x.top)) - P.top - pad; }
    else { l = Math.max(...tops.map((x) => x.right)) - P.left + pad; r = rl.left - P.left - pad; t = hb; b = H - pad; }
    if (r - l < W * 0.3) { l = 0; r = W; } if (b - t < H * 0.25) { t = 0; b = H; }
    free = { fx: (l + r) / 2 / W, fy: (t + b) / 2 / H, aw: (r - l) / W, ah: (b - t) / H };
  }
  function fit() { renderer.setSize(pin.clientWidth, pin.clientHeight, false); measure(); }
  fit(); addEventListener('resize', fit); document.fonts && document.fonts.ready.then(fit);
  let visible = true; new IntersectionObserver((es) => { visible = es[0].isIntersecting; }).observe(pin);
  fc.x = sceneAt(prog()); setCard(Math.round(fc.x));
  scene.traverse((o) => { if (o.isMesh && o !== pulses) { o.matrixAutoUpdate = false; o.updateMatrix(); } });
  renderer.shadowMap.needsUpdate = true;
  const colMid = new THREE.Color(C.mid), colAcc = new THREE.Color(C.accent), M4 = new THREE.Matrix4(), PV = new V(), Q = new THREE.Quaternion(), SV = new V();
  let last = performance.now();
  function loop(now) {
    requestAnimationFrame(loop);
    const dt = Math.min(0.25, (now - last) / 1000); last = now;
    if (!visible) return;
    const goal = sceneAt(prog()), c = fc.step(goal, dt); zoomK.step(1, dt);
    setCard(Math.round(goal));                     // the copy answers the scroll at once; the camera follows on its spring
    if (hintOn && scrollY > 40) { hintOn = false; tween(hint, 'uiExit', (p) => { hint.style.opacity = S.clamp01(1 - p); }); }
    aimAt(c);
    const T = now / 1000; let n = 0;
    for (const cb of cables) {
      const on = c >= cb.at; if (on !== cb.on) { cb.on = on; cb.t0 = now; cb.from = cb.lvl; }
      const p = S.clamp01(S.progress((now - cb.t0) / 1000, { preset: 'smooth' })); cb.lvl = cb.from + ((on ? 1 : 0) - cb.from) * p;
      cb.mat.emissiveIntensity = cb.lvl * (cb.air ? 1.6 : 0.9); cb.mat.color.copy(colMid).lerp(colAcc, cb.lvl); if (cb.air) cb.mat.opacity = 0.18 + 0.5 * cb.lvl;
      for (let i = 0; i < cb.pulses; i++) {
        const u = ((T * 5.5) / cb.len + i / cb.pulses) % 1; cb.curve.getPointAt(u, PV);
        SV.setScalar(cb.lvl * (cb.air ? 0.8 : 1)); M4.compose(PV, Q, SV); pulses.setMatrixAt(n++, M4);
      }
    }
    pulses.instanceMatrix.needsUpdate = true;
    renderer.render(scene, cam);
  }
  requestAnimationFrame(loop);
}
"""
