// Shared 3D logo builder (same rules as render.html): every fill keeps its colour, colour layers step up in z,
// neutral greys render as metal. Returns a Group centred at the origin, scaled so its width is 4 world units.
import * as THREE from 'three';
import { SVGLoader } from 'three/addons/loaders/SVGLoader.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';

export function makeRenderer(w, h) {
  const r = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true });
  r.setPixelRatio(1); r.setSize(w, h); r.setClearColor(0x000000, 0);
  r.outputColorSpace = THREE.SRGBColorSpace; r.toneMapping = THREE.NeutralToneMapping;
  return r;
}

export function makeScene(renderer) {
  const scene = new THREE.Scene();
  const pm = new THREE.PMREMGenerator(renderer);
  scene.environment = pm.fromScene(new RoomEnvironment(), 0.04).texture;
  scene.environmentIntensity = 0.55;
  const key = new THREE.DirectionalLight(0xffffff, 1.6); key.position.set(-4, 6, 8); scene.add(key);
  const rim = new THREE.DirectionalLight(0xffffff, 0.9); rim.position.set(6, 2, -6); scene.add(rim);
  scene.add(new THREE.AmbientLight(0xffffff, 0.35));
  return scene;
}

export function buildLogo(svgText, opt = {}) {
  const data = new SVGLoader().parse(svgText);
  const items = [];
  for (const p of data.paths) {
    const st = p.userData?.style || {};
    if (!st.fill || st.fill === 'none' || st.fill === 'transparent') continue;
    if (st.fillOpacity !== undefined && +st.fillOpacity === 0) continue;
    if (st.opacity !== undefined && +st.opacity === 0) continue;
    const shapes = SVGLoader.createShapes(p);
    if (shapes.length) items.push({ shapes, color: new THREE.Color().setStyle(st.fill) });
  }
  const bb = new THREE.Box2();
  for (const it of items) for (const s of it.shapes) for (const pt of s.getPoints(4)) bb.expandByPoint(pt);
  const size = new THREE.Vector2(); bb.getSize(size);
  const maxDim = Math.max(size.x, size.y);
  const depth = (opt.depth ?? 0.03) * maxDim, bevel = (opt.bevel ?? 0.0022) * maxDim;
  let L = 0; items.forEach((it, i) => { if (i && !it.color.equals(items[i - 1].color)) L++; it.layer = L; });
  const step = Math.min(0.004 * maxDim, (0.03 * maxDim) / Math.max(L, 1));
  const cache = new Map();
  const mats = (c) => {
    const k = c.getHexString(); if (cache.has(k)) return cache.get(k);
    const hsl = {}; c.getHSL(hsl);
    const metal = hsl.s < 0.08 && hsl.l > 0.25 && hsl.l < 0.85;
    const face = new THREE.MeshPhysicalMaterial({ color: c, roughness: metal ? 0.3 : 0.34, metalness: metal ? 0.45 : 0.05,
      clearcoat: metal ? 0.2 : 0.55, clearcoatRoughness: 0.2 });
    const side = face.clone(); side.color = c.clone().multiplyScalar(metal ? 0.8 : 0.62);
    const m = [face, side]; cache.set(k, m); return m;
  };
  const root = new THREE.Group();
  const heavy = items.length > 100;
  items.forEach((it) => {
    const geo = new THREE.ExtrudeGeometry(it.shapes, { depth, bevelEnabled: bevel > 0, bevelThickness: bevel, bevelSize: bevel,
      bevelOffset: -bevel, bevelSegments: heavy ? 2 : 4, curveSegments: heavy ? 3 : 16 });
    const m = new THREE.Mesh(geo, mats(it.color)); m.position.z = it.layer * step; root.add(m);
  });
  root.scale.set(1, -1, 1);
  const box = new THREE.Box3().setFromObject(root); const c = box.getCenter(new THREE.Vector3());
  root.position.sub(c);
  const s = 4 / Math.max(box.max.x - box.min.x, 1e-6);
  const g = new THREE.Group(); g.add(root); g.scale.setScalar(s);
  const b2 = new THREE.Box3().setFromObject(g); const sz = b2.getSize(new THREE.Vector3());
  const outer = new THREE.Group(); outer.add(g);
  outer.userData.size = { w: sz.x, h: sz.y };      // w is 4
  return outer;
}
