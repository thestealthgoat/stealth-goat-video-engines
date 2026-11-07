"""spring.py — closed-form damped springs for anything drawn frame by frame in Python
(render_reel.py / vreel.py cards, PIL overlays). Same maths and presets as spring.js.

Motion must be a pure function of t: never a fixed-duration ease or a step-by-step simulation.

    from spring import spring_at, settle, PRESETS
    x = spring_at(t, frm=-400, to=0, start=0.35, preset="snappy")   # card slides in at 0.35 s

Camera and impact helpers (same names and maths in spring.js):
    dx, dy = handheld(t, amp=6, freq=0.6, seed=3)                  # deterministic hand-held drift, px
    y += shake(t, hit=2.40, amp=14, decay=9, freq=13)              # impact shake from the hit frame on
    cam = camera_at(t, [{"t": 0, "x": 0, "y": 0, "zoom": 1.0},
                        {"t": 1.2, "zoom": 1.15, "preset": "smooth"},
                        {"t": 3.0, "x": -120, "preset": "gentle"}])  # -> {"x", "y", "zoom"}

Run `python3 spring.py` to print each preset's settle time and overshoot.
"""
import math

# Settle times are to within 0.5% of the move.
PRESETS = {
    "snappy": (0.75, 20.0),  # UI panels, lower thirds, cards: tiny overshoot, ~0.36 s
    "bouncy": (0.42, 17.0),  # playful entrances, logo lands: clear overshoot, ~0.70 s
    "slam":   (0.30, 26.0),  # hard hits (logo slam, score pop): fast, visible bounce, ~0.67 s
    "smooth": (1.00, 12.0),  # no overshoot: fades, camera pushes, text that must not wobble, ~0.62 s
    "gentle": (0.90, 8.0),   # slow drifts and background moves, ~0.69 s
    "ui":     (1.00, 37.0),  # website/app UI: never bounces, ~0.20 s
    "uiExit": (1.00, 46.0),  # UI exits ~20% faster, ~0.16 s
}


def solve(t, zeta, omega, v0=0.0):
    """Offset from target (starts at -1) and velocity, t seconds after the spring starts."""
    y0 = -1.0
    if t <= 0:
        return y0, v0
    if zeta < 1:
        wd = omega * math.sqrt(1 - zeta * zeta)
        a, b = y0, (v0 + zeta * omega * y0) / wd
        e, c, s = math.exp(-zeta * omega * t), math.cos(wd * t), math.sin(wd * t)
        y = e * (a * c + b * s)
        v = e * ((-zeta * omega) * (a * c + b * s) + (-a * wd * s + b * wd * c))
        return y, v
    if zeta == 1:
        a, b, e = y0, v0 + omega * y0, math.exp(-omega * t)
        return e * (a + b * t), e * (b - omega * (a + b * t))
    r = omega * math.sqrt(zeta * zeta - 1)
    r1, r2 = -zeta * omega + r, -zeta * omega - r
    c2 = (v0 - r1 * y0) / (r2 - r1)
    c1 = y0 - c2
    e1, e2 = math.exp(r1 * t), math.exp(r2 * t)
    return c1 * e1 + c2 * e2, c1 * r1 * e1 + c2 * r2 * e2


def _params(preset, zeta, omega):
    if preset is not None:
        if preset not in PRESETS:
            raise ValueError(f"unknown preset {preset!r}")
        pz, po = PRESETS[preset]
        zeta = pz if zeta is None else zeta
        omega = po if omega is None else omega
    return (0.75 if zeta is None else zeta), (20.0 if omega is None else omega)


def progress(t, start=0.0, preset=None, zeta=None, omega=None, v0=0.0):
    """0 -> 1 (overshoots past 1 when zeta < 1). 0 before `start`."""
    z, w = _params(preset, zeta, omega)
    return 1 + solve(t - start, z, w, v0)[0]


def spring_at(t, frm=0.0, to=1.0, start=0.0, preset=None, zeta=None, omega=None, v0=0.0):
    """Value at time t moving frm -> to, beginning at `start` seconds."""
    return frm + (to - frm) * progress(t, start, preset, zeta, omega, v0)


def velocity(t, frm=0.0, to=1.0, start=0.0, preset=None, zeta=None, omega=None, v0=0.0):
    """Units per second at time t (for motion blur / squash and stretch)."""
    if t < start:
        return 0.0
    z, w = _params(preset, zeta, omega)
    return (to - frm) * solve(t - start, z, w, v0)[1]


def settle(preset=None, zeta=None, omega=None, v0=0.0, tol=0.005):
    """Seconds after start until the motion stays within `tol` (fraction of the move) of the target."""
    z, w = _params(preset, zeta, omega)
    dt, last, t = 0.001, 0.0, 0.0
    while t < 20:
        if abs(solve(t, z, w, v0)[0]) > tol:
            last = t
        elif t - last > 2 * math.pi / w:
            break
        t += dt
    return round(last + dt, 3)


def overshoot(preset=None, zeta=None, omega=None, v0=0.0):
    """Peak overshoot past the target as a fraction of the move."""
    z, w = _params(preset, zeta, omega)
    return max(0.0, max(solve(i / 2000, z, w, v0)[0] for i in range(6000)))


def ring(t, start=0.0, amp=0.06, freq=6.0, decay=9.0):
    """Follow-through after an impact: damped wobble to ADD to a resting value (e.g. scale = 1 + ring(t, 0.42))."""
    dt = t - start
    if dt < 0:
        return 0.0
    return amp * math.exp(-decay * dt) * math.sin(2 * math.pi * freq * dt)


_HH_RATIOS = (1.0, 2.17, 4.31)      # handheld(): three sines per axis, not harmonics of each other
_HH_WEIGHTS = (1.0, 0.45, 0.2)


def _hash01(seed, i):
    """Deterministic 0..1 from integers (32-bit integer hash; spring.js computes the same bits)."""
    h = (int(seed) * 374761393 + int(i) * 668265263) & 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    h = h ^ (h >> 16)
    return h / 4294967296.0


def handheld(t, amp=4.0, freq=0.5, seed=0):
    """Hand-held camera drift: (dx, dy) in the units of amp, a deterministic sum of sines (same seed -> same path).
    freq is the slowest sway in Hz; two faster, smaller sines ride on it. |dx|, |dy| stay within amp."""
    tot = sum(_HH_WEIGHTS)
    out = []
    for axis in (0, 1):
        v = 0.0
        for k in range(3):
            ph = 2 * math.pi * _hash01(seed, axis * 3 + k)
            v += _HH_WEIGHTS[k] * math.sin(2 * math.pi * freq * _HH_RATIOS[k] * t + ph)
        out.append(amp * v / tot)
    return out[0], out[1]


def shake(t, hit, amp=12.0, decay=8.0, freq=14.0):
    """Impact shake: a damped oscillation that starts at full amp on the hit frame (cosine) and dies out.
    0 before `hit`. ADD it to a position; for 2D use a second call with another freq (e.g. freq * 1.37)."""
    dt = t - hit
    if dt < 0:
        return 0.0
    return amp * math.exp(-decay * dt) * math.cos(2 * math.pi * freq * dt)


_CAM_SKIP = ("t", "preset", "zeta", "omega", "v0")
_CAM_DEFAULT = {"x": 0.0, "y": 0.0, "zoom": 1.0}


def camera_at(t, keys):
    """Camera {x, y, zoom, ...} at time t from keys [{t, x?, y?, zoom?, preset?, zeta?, omega?}, ...].
    The first key is the starting pose. Each later key starts a spring (preset default "smooth") at its t from
    the previous target of every field it names to its new value; fields it leaves out hold. Moves add up, so
    overlapping keys blend without a jump. Any other numeric field (e.g. "rot") works the same way."""
    keys = sorted(keys, key=lambda k: k.get("t", 0.0))
    cur = dict(_CAM_DEFAULT)
    if keys:
        for f, v in keys[0].items():
            if f not in _CAM_SKIP:
                cur[f] = float(v)
    out = dict(cur)
    for k in keys[1:]:
        preset = k.get("preset")                    # None / missing -> "smooth" unless zeta/omega given (as spring.js)
        if preset is None and k.get("zeta") is None and k.get("omega") is None:
            preset = "smooth"
        p = None
        for f, v in k.items():
            if f in _CAM_SKIP:
                continue
            if f not in cur:
                cur[f] = out[f] = _CAM_DEFAULT.get(f, 0.0)
            if p is None:
                p = progress(t, k.get("t", 0.0), preset, k.get("zeta"), k.get("omega"), k.get("v0") or 0.0)
            out[f] += (float(v) - cur[f]) * p
            cur[f] = float(v)
    return out


def stagger(n, start, gap):
    return [start + i * gap for i in range(n)]


def mix(a, b, p):
    """Mix numbers or colour tuples by p (colours clamped to 0..255)."""
    if isinstance(a, (tuple, list)):
        return tuple(max(0, min(255, round(x + (y - x) * p))) for x, y in zip(a, b))
    return a + (b - a) * p


def clamp01(x):
    """For opacity, which must never overshoot."""
    return max(0.0, min(1.0, x))


if __name__ == "__main__":
    for name in PRESETS:
        print(f"{name:7s} zeta={PRESETS[name][0]:.2f} omega={PRESETS[name][1]:>4.1f}  "
              f"settles {settle(name):.2f} s  overshoot {overshoot(name) * 100:4.1f}%")
