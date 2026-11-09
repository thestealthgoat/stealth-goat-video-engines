/*
 * spring.js — closed-form damped springs for frame-by-frame motion graphics.
 *
 * Every frame is drawn from a timestamp (renderFrame(t)), so motion must be a pure
 * function of t: no CSS transitions, no @keyframes, no ease-in-out curves, no
 * step-by-step simulation. This file solves the spring equation exactly, so any
 * frame can be drawn on its own and the same t always gives the same picture.
 *
 *   zeta  (ζ) damping ratio: <1 overshoots and settles, 1 = no overshoot (fastest), >1 = sluggish
 *   omega (ω) natural frequency in rad/s: higher = faster
 *
 * Use (browser): <script src="spring.js"></script>  →  Spring.at(t, {from:0, to:1, start:0.35, ...Spring.PRESETS.snappy})
 * Use (node):    const Spring = require('./spring.js')
 *
 * Camera and impact helpers (same names and math in spring.py):
 *   const [dx, dy] = Spring.handheld(t, 6, 0.6, 3);           // deterministic hand-held drift (amp, freq Hz, seed)
 *   y += Spring.shake(t, 2.40, 14, 9, 13);                     // impact shake from the hit frame (hit, amp, decay, freq)
 *   const cam = Spring.camera_at(t, [{ t: 0, x: 0, y: 0, zoom: 1 },
 *                                    { t: 1.2, zoom: 1.15, preset: 'smooth' },
 *                                    { t: 3.0, x: -120, preset: 'gentle' }]);   // -> {x, y, zoom}
 */
(function (root) {
  'use strict';

  const PRESETS = {
    // Settle times are to within 0.5% of the move (Spring.settle).
    snappy: { zeta: 0.75, omega: 20 }, // UI panels, lower thirds, cards: tiny overshoot, ~0.36 s
    bouncy: { zeta: 0.42, omega: 17 }, // playful entrances, logo lands: clear overshoot, ~0.70 s
    slam:   { zeta: 0.30, omega: 26 }, // hard hits (logo slam, score pop): fast, visible bounce, ~0.67 s
    smooth: { zeta: 1.00, omega: 12 }, // no overshoot: fades, camera pushes, text that must not wobble, ~0.62 s
    gentle: { zeta: 0.90, omega: 8 },  // slow drifts and background moves, ~0.69 s
    ui:     { zeta: 1.00, omega: 37 }, // website/app UI: never bounces, ~0.20 s (menus, popovers, toggles)
    uiExit: { zeta: 1.00, omega: 46 }, // UI exits ~20% faster, ~0.16 s
  };

  // Offset from target y(t) (starts at y0 = -1, i.e. full distance away) and its velocity.
  // v0 is the starting velocity in "moves per second" (0 = starts at rest).
  function solve(t, zeta, omega, v0) {
    const y0 = -1;
    if (t <= 0) return { y: y0, v: v0 };
    if (zeta < 1) {
      const wd = omega * Math.sqrt(1 - zeta * zeta);
      const a = y0, b = (v0 + zeta * omega * y0) / wd;
      const e = Math.exp(-zeta * omega * t), c = Math.cos(wd * t), s = Math.sin(wd * t);
      const y = e * (a * c + b * s);
      const v = e * ((-zeta * omega) * (a * c + b * s) + (-a * wd * s + b * wd * c));
      return { y, v };
    }
    if (zeta === 1) {
      const a = y0, b = v0 + omega * y0, e = Math.exp(-omega * t);
      return { y: e * (a + b * t), v: e * (b - omega * (a + b * t)) };
    }
    const r = omega * Math.sqrt(zeta * zeta - 1);
    const r1 = -zeta * omega + r, r2 = -zeta * omega - r;
    const c2 = (v0 - r1 * y0) / (r2 - r1), c1 = y0 - c2;
    const e1 = Math.exp(r1 * t), e2 = Math.exp(r2 * t);
    return { y: c1 * e1 + c2 * e2, v: c1 * r1 * e1 + c2 * r2 * e2 };
  }

  function opts(o) {
    o = o || {};
    const p = o.preset ? PRESETS[o.preset] : null;
    if (o.preset && !p) throw new Error('spring.js: unknown preset ' + o.preset);
    return {
      zeta: o.zeta != null ? o.zeta : (p ? p.zeta : 0.75),
      omega: o.omega != null ? o.omega : (p ? p.omega : 20),
      v0: o.v0 || 0,
      start: o.start || 0,
      from: o.from != null ? o.from : 0,
      to: o.to != null ? o.to : 1,
    };
  }

  /** Progress 0→1 (overshoots past 1 when zeta < 1). Before `start` it is 0. */
  function progress(t, o) {
    const k = opts(o);
    return 1 + solve(t - k.start, k.zeta, k.omega, k.v0).y;
  }

  /** Value at time t, moving from `from` to `to` starting at `start` seconds. */
  function at(t, o) {
    const k = opts(o);
    return k.from + (k.to - k.from) * (1 + solve(t - k.start, k.zeta, k.omega, k.v0).y);
  }

  /** Velocity (units per second) at time t — use for motion blur or squash/stretch. */
  function velocity(t, o) {
    const k = opts(o);
    if (t < k.start) return 0;
    return (k.to - k.from) * solve(t - k.start, k.zeta, k.omega, k.v0).v;
  }

  /**
   * Seconds after start until the motion stays within `tol` of the target (fraction of the move).
   * Plan holds and the next beat from this, not from a guessed duration.
   */
  function settle(o, tol) {
    const k = opts(o);
    tol = tol || 0.005;
    const dt = 1 / 1000, max = 20;
    let last = 0;
    for (let t = 0; t < max; t += dt) {
      if (Math.abs(solve(t, k.zeta, k.omega, k.v0).y) > tol) last = t;
      else if (t - last > 2 * Math.PI / k.omega) break; // stayed inside for a full period
    }
    return Math.round((last + dt) * 1000) / 1000;
  }

  /** Overshoot past the target as a fraction of the move (0 when zeta >= 1 and v0 = 0). */
  function overshoot(o) {
    const k = opts(o);
    let peak = 0;
    for (let t = 0; t < 3; t += 1 / 2000) peak = Math.max(peak, solve(t, k.zeta, k.omega, k.v0).y);
    return peak;
  }

  /** Start times for a staggered group: n items, `gap` seconds apart, beginning at `start`. */
  function stagger(n, start, gap) {
    const out = [];
    for (let i = 0; i < n; i++) out.push(start + i * gap);
    return out;
  }

  /** Mix two numbers, or two [r,g,b(,a)] arrays, by p (p may overshoot; colors are clamped). */
  function mix(a, b, p) {
    if (Array.isArray(a)) return a.map((x, i) => Math.max(0, Math.min(255, x + (b[i] - x) * p)));
    return a + (b - a) * p;
  }

  /**
   * Follow-through after an impact: a damped wobble that starts at `start` and dies out.
   * ring(t, {start, amp, freq, decay}) -> offset to ADD to a resting value (e.g. scale 1 + ring).
   * amp in the value's units, freq in Hz, decay per second (higher = shorter ring).
   */
  function ring(t, o) {
    o = o || {};
    const dt = t - (o.start || 0);
    if (dt < 0) return 0;
    const amp = o.amp != null ? o.amp : 0.06, f = o.freq != null ? o.freq : 6, k = o.decay != null ? o.decay : 9;
    return amp * Math.exp(-k * dt) * Math.sin(2 * Math.PI * f * dt);
  }

  // handheld(): three sines per axis, not harmonics of each other
  const HH_RATIOS = [1.0, 2.17, 4.31], HH_WEIGHTS = [1.0, 0.45, 0.2];

  /** Deterministic 0..1 from integers (32-bit integer hash; spring.py computes the same bits). */
  function hash01(seed, i) {
    let h = (Math.imul(seed | 0, 374761393) + Math.imul(i | 0, 668265263)) >>> 0;
    h = Math.imul(h ^ (h >>> 13), 1274126177) >>> 0;
    h = (h ^ (h >>> 16)) >>> 0;
    return h / 4294967296;
  }

  /**
   * Hand-held camera drift: [dx, dy] in the units of amp, a deterministic sum of sines (same seed -> same path).
   * freq is the slowest sway in Hz; two faster, smaller sines ride on it. |dx|, |dy| stay within amp.
   */
  function handheld(t, amp, freq, seed) {
    amp = amp != null ? amp : 4; freq = freq != null ? freq : 0.5; seed = seed != null ? seed : 0;
    const tot = HH_WEIGHTS[0] + HH_WEIGHTS[1] + HH_WEIGHTS[2];
    const out = [];
    for (let axis = 0; axis < 2; axis++) {
      let v = 0;
      for (let k = 0; k < 3; k++) {
        const ph = 2 * Math.PI * hash01(seed, axis * 3 + k);
        v += HH_WEIGHTS[k] * Math.sin(2 * Math.PI * freq * HH_RATIOS[k] * t + ph);
      }
      out.push(amp * v / tot);
    }
    return out;
  }

  /**
   * Impact shake: a damped oscillation that starts at full amp on the hit frame (cosine) and dies out.
   * 0 before `hit`. ADD it to a position; for 2D use a second call with another freq (e.g. freq * 1.37).
   */
  function shake(t, hit, amp, decay, freq) {
    const dt = t - hit;
    if (dt < 0) return 0;
    amp = amp != null ? amp : 12; decay = decay != null ? decay : 8; freq = freq != null ? freq : 14;
    return amp * Math.exp(-decay * dt) * Math.cos(2 * Math.PI * freq * dt);
  }

  const CAM_SKIP = { t: 1, preset: 1, zeta: 1, omega: 1, v0: 1 };
  const CAM_DEFAULT = { x: 0, y: 0, zoom: 1 };

  /**
   * Camera {x, y, zoom, ...} at time t from keys [{t, x?, y?, zoom?, preset?, zeta?, omega?}, ...].
   * The first key is the starting pose. Each later key starts a spring (preset default 'smooth') at its t from
   * the previous target of every field it names to its new value; fields it leaves out hold. Moves add up, so
   * overlapping keys blend without a jump. Any other numeric field (e.g. rot) works the same way.
   */
  function camera_at(t, keys) {
    keys = (keys || []).slice().sort((a, b) => (a.t || 0) - (b.t || 0));
    const cur = Object.assign({}, CAM_DEFAULT);
    if (keys.length) for (const f in keys[0]) if (!CAM_SKIP[f]) cur[f] = +keys[0][f];
    const out = Object.assign({}, cur);
    for (const k of keys.slice(1)) {
      const preset = k.preset != null ? k.preset : (k.zeta == null && k.omega == null ? 'smooth' : null);
      let p = null;
      for (const f in k) {
        if (CAM_SKIP[f]) continue;
        if (!(f in cur)) { cur[f] = out[f] = (f in CAM_DEFAULT) ? CAM_DEFAULT[f] : 0; }
        if (p === null) p = progress(t, { start: k.t || 0, preset, zeta: k.zeta, omega: k.omega, v0: k.v0 || 0 });
        out[f] += (+k[f] - cur[f]) * p;
        cur[f] = +k[f];
      }
    }
    return out;
  }

  /** Clamp to 0..1 — for opacity, which must never overshoot. */
  function clamp01(x) { return Math.max(0, Math.min(1, x)); }

  const Spring = { PRESETS, at, progress, velocity, settle, overshoot, stagger, mix, clamp01, ring, solve,
                   handheld, shake, camera_at, cameraAt: camera_at };
  if (typeof module !== 'undefined' && module.exports) module.exports = Spring;
  else root.Spring = Spring;
})(typeof self !== 'undefined' ? self : this);
