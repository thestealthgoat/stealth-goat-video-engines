#!/usr/bin/env python3
"""palette.py - brand colors -> UI color tokens with MEASURED contrast (WCAG 2 relative luminance), and a checker.

  palette.py make --primary "#0B3D2E" --accent "#F2B705" [--text "#FFFFFF"] [--write tokens.css]
  palette.py make --profile demo [--write tokens.css]      a brand profile in the engine folder ($VIDEO_ENGINE)
  palette.py make --profile-json path/to/profile.json [--write tokens.css]      (reads brand.colors)
  palette.py check tokens.css        measure every role pair in every theme block; exit 1 on any fail
  palette.py ratio "#767676" "#ffffff"

make prints a light theme (:root) and a dark theme (prefers-color-scheme: dark, unless data-theme="light"; and
data-theme="dark"). Each color is nudged until it passes, the same way the engine's website kit does it
(web/build.py palette()): text >= 7:1 on every ground, muted text, links and status text >= 4.5:1, labels on filled
buttons >= 4.5:1, control borders, focus ring and button fills >= 3:1 against the page. --write replaces the block
between "/* colours:start */" and "/* colours:end */" in a tokens.css and leaves everything else alone.
No dependencies beyond the Python standard library.
"""
import argparse, json, os, re, sys

WHITE, BLACK, INK = "#ffffff", "#000000", "#111111"
STATUS = {"danger": "#d92d20", "success": "#067647", "warning": "#b54708"}   # light-theme starting hues


def norm(c):
    c = c.strip().lstrip("#")
    if len(c) == 3: c = "".join(x * 2 for x in c)
    if not re.fullmatch(r"[0-9a-fA-F]{6}", c): raise ValueError(f"not a hex color: {c!r}")
    return "#" + c.lower()


def luma(c):
    c = norm(c)[1:]; v = [int(c[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    v = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in v]
    return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2]


def ratio(a, b):
    la, lb = sorted((luma(a), luma(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def mix(a, b, k):
    a, b = norm(a)[1:], norm(b)[1:]
    return "#" + "".join(f"{round(int(a[i:i + 2], 16) + (int(b[i:i + 2], 16) - int(a[i:i + 2], 16)) * k):02x}" for i in (0, 2, 4))


def worst(c, grounds): return min(ratio(c, g) for g in grounds)


def push(c, toward, grounds, need, step=0.12):
    """move c toward `toward` in small steps until it reaches `need` on every ground (bounded)"""
    for _ in range(60):
        if worst(c, grounds) >= need: return c
        c = mix(c, toward, step)
    return toward


def on(fill):
    """the label color for a filled control: near-black or white, whichever reads better"""
    return INK if ratio(INK, fill) >= ratio(WHITE, fill) else WHITE


def fit_fill(fill, grounds, page_need=3.0):
    """a fill (button, badge) whose label passes 4.5:1 and whose edge stands out 3:1 from the page"""
    dark_page = luma(grounds[0]) < 0.2
    for _ in range(60):
        if ratio(on(fill), fill) >= 4.5 and worst(fill, grounds) >= page_need: return fill
        # on a light page darken the fill, on a dark page lighten it, until both hold
        fill = mix(fill, WHITE if dark_page else BLACK, 0.08)
    return fill


def light(prim, acc):
    bg, surface, surface2 = mix(WHITE, prim, 0.03), WHITE, mix(WHITE, prim, 0.07)
    G = (bg, surface, surface2)
    text = push(mix(prim, BLACK, 0.8), BLACK, G, 7.0)
    muted = push(mix(text, bg, 0.4), text, G, 4.5)
    # links: the accent if it gets there without losing its hue (mixed <= ~40% toward the text), else the primary
    link = None
    for base in (acc, prim):
        c = base
        for _ in range(4):
            if worst(c, G) >= 4.5: link = c; break
            c = mix(c, text, 0.12)
        if link: break
    link = link or push(prim, text, G, 4.5)
    t = {"bg": bg, "surface": surface, "surface-2": surface2, "text": text, "text-muted": muted, "link": link}
    t["action"] = fit_fill(prim, G); t["on-action"] = on(t["action"])
    t["highlight"] = fit_fill(acc, G, page_need=1.0); t["on-highlight"] = on(t["highlight"])
    t["border"] = push(mix(text, bg, 0.6), text, G, 3.0)
    t["divider"] = mix(text, bg, 0.86)                     # decorative lines only: no contrast requirement
    t["focus"] = push(link, text, G, 3.0)
    for k, v in STATUS.items():
        t[k] = push(v, BLACK, G, 4.5)
    t["on-danger"] = on(t["danger"])
    return t


def dark(prim, acc, text_in=None):
    # the website kit's dark ground (web/build.py palette()): primary deepened until body text is comfortably readable
    text = text_in or WHITE
    k = 0.62; bg = mix(prim, BLACK, k)
    while ratio(text, bg) < 7 and k < 0.95: k += 0.04; bg = mix(prim, BLACK, k)
    s = 0.12                                               # raised surfaces: a little lighter, text still >= 7:1
    while s > 0.02 and ratio(text, mix(bg, WHITE, s)) < 7: s -= 0.01
    surface, surface2 = mix(bg, WHITE, s * 0.5), mix(bg, WHITE, s)
    G = (bg, surface, surface2)
    if worst(text, G) < 7: text = WHITE if worst(WHITE, G) >= worst(INK, G) else INK
    t = {"bg": bg, "surface": surface, "surface-2": surface2, "text": text}
    t["text-muted"] = push(mix(text, bg, 0.28), text, G, 4.5, 0.2)
    t["link"] = push(acc, WHITE, G, 4.5, 0.15)
    t["action"] = fit_fill(acc, G); t["on-action"] = on(t["action"])
    t["highlight"] = fit_fill(acc, G, page_need=1.0); t["on-highlight"] = on(t["highlight"])
    t["border"] = push(mix(text, bg, 0.6), text, G, 3.0)
    t["divider"] = mix(text, bg, 0.8)
    t["focus"] = push(t["link"], WHITE, G, 3.0)
    for k2, v in STATUS.items():
        t[k2] = push(v, WHITE, G, 4.5)
    t["on-danger"] = on(t["danger"])
    return t


# role pairs every theme must pass: (foreground role, [ground roles], minimum ratio, what it is)
PAIRS = [
    ("text", ["bg", "surface", "surface-2"], 4.5, "body text"),
    ("text-muted", ["bg", "surface", "surface-2"], 4.5, "secondary text"),
    ("link", ["bg", "surface", "surface-2"], 4.5, "links / accent text"),
    ("danger", ["bg", "surface", "surface-2"], 4.5, "error text"),
    ("success", ["bg", "surface", "surface-2"], 4.5, "success text"),
    ("warning", ["bg", "surface", "surface-2"], 4.5, "warning text"),
    ("on-action", ["action"], 4.5, "label on a primary button"),
    ("on-highlight", ["highlight"], 4.5, "label on a highlight / badge"),
    ("on-danger", ["danger"], 4.5, "label on a danger button"),
    ("action", ["bg", "surface"], 3.0, "primary button edge vs page"),
    ("border", ["bg", "surface"], 3.0, "input / checkbox border vs page"),
    ("focus", ["bg", "surface", "surface-2"], 3.0, "focus ring vs page"),
]


def css_block(sel, t, indent="  "):
    return f"{sel} {{\n" + "".join(f"{indent}--color-{k}: {v};\n" for k, v in t.items()) + "}"


def make_css(prim, acc, text=None):
    L, D = light(prim, acc), dark(prim, acc, text)
    head = f"/* colours:start - made by scripts/palette.py from primary {prim}, accent {acc}; measured, see palette.py check */"
    dk = "".join(f"    --color-{k}: {v};\n" for k, v in D.items())
    return (f"{head}\n{css_block(':root', L)}\n"
            f"@media (prefers-color-scheme: dark) {{\n  :root:not([data-theme=\"light\"]) {{\n{dk}  }}\n}}\n"
            f"{css_block(':root[data-theme=\"dark\"]', D)}\n/* colours:end */"), L, D


def parse_blocks(css):
    """[(selector, {role: value})] for every innermost {...} block that sets --color-* tokens"""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    out = []
    for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        vals = dict(re.findall(r"--color-([\w-]+)\s*:\s*([^;]+);", body))
        if vals: out.append((" ".join(sel.split()), {k: v.strip() for k, v in vals.items()}))
    return out


def resolve(v, vals, seen=()):
    m = re.fullmatch(r"var\(--color-([\w-]+)\)", v)
    if m and m.group(1) in vals and m.group(1) not in seen: return resolve(vals[m.group(1)], vals, seen + (m.group(1),))
    m = re.fullmatch(r"rgba?\(\s*(\d+)[ ,]+(\d+)[ ,]+(\d+)\s*\)", v)
    if m: return "#" + "".join(f"{int(x):02x}" for x in m.groups())
    try: return norm(v)
    except ValueError: return None


def check(path):
    blocks = parse_blocks(open(path).read())
    if not blocks: print(f"check: no --color-* tokens in {path}"); return 1
    base = blocks[0][1]; fails = n = 0
    for sel, vals in blocks:
        merged = dict(base); merged.update(vals)            # a dark block overrides the :root values it names
        print(f"\n{sel}")
        for fg, grounds, need, what in PAIRS:
            if fg not in merged: continue
            f = resolve(merged[fg], merged)
            for g in grounds:
                if g not in merged: continue
                b = resolve(merged[g], merged)
                if not (f and b): print(f"  ?    {fg} on {g}: can't read {merged[fg]!r} / {merged[g]!r} (use hex)"); continue
                r = ratio(f, b); ok = r >= need; n += 1; fails += not ok
                print(f"  {'ok  ' if ok else 'FAIL'} {r:5.2f}:1 (need {need}) --color-{fg} {f} on --color-{g} {b}  [{what}]")
    print(f"\npalette check: {n - fails}/{n} pairs pass" + (f", {fails} FAIL" if fails else ""))
    return 1 if fails else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="brand colors -> measured UI color tokens")
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("make"); m.add_argument("--primary"); m.add_argument("--accent"); m.add_argument("--text")
    m.add_argument("--profile", help="engine brand profile name (needs $VIDEO_ENGINE; else $VIDEO_PROFILE / local.json is used "
                   "when you pass --profile ''): uses brand.colors primary / accent / text")
    m.add_argument("--profile-json", help="a brand profile.json file: uses brand.colors primary / accent / text")
    m.add_argument("--write", help="tokens.css to update between /* colours:start */ and /* colours:end */")
    c = sub.add_parser("check"); c.add_argument("css")
    r = sub.add_parser("ratio"); r.add_argument("a"); r.add_argument("b")
    a = ap.parse_args(argv)
    if a.cmd == "ratio":
        x = ratio(a.a, a.b); print(f"{x:.2f}:1  text {'pass' if x >= 4.5 else 'FAIL'} (4.5)  large text / controls {'pass' if x >= 3 else 'FAIL'} (3)"); return 0
    if a.cmd == "check": return check(a.css)
    prim, acc, text = a.primary, a.accent, a.text
    cols = None
    if a.profile is not None:
        eng = os.environ.get("VIDEO_ENGINE")
        if not eng or not os.path.isfile(os.path.join(eng, "engine", "vprofile.py")):
            print("make: --profile needs $VIDEO_ENGINE set to the engine folder (or pass --profile-json / --primary)"); return 1
        sys.path.insert(0, os.path.join(eng, "engine"))
        import vprofile                                            # the engine's profile loader: --profile, $VIDEO_PROFILE, local.json
        try:
            cols = vprofile.load(a.profile or None).get("brand.colors", {}) or {}
        except vprofile.ProfileError as e:
            print(f"make: {e}"); return 1
    elif a.profile_json:
        cols = json.load(open(a.profile_json)).get("brand", {}).get("colors", {})
    if cols is not None:
        prim, acc = prim or cols.get("primary"), acc or cols.get("accent") or cols.get("primary")
        text = text or cols.get("text")
    if not prim: ap.error("give --primary (and --accent), or --profile-json")
    prim = norm(prim); acc = norm(acc or prim)
    text = norm(text) if text and luma(norm(text)) > 0.5 else None     # a dark brand text color is for light themes; dark uses white
    css, L, D = make_css(prim, acc, text)
    if a.write:
        s = open(a.write).read()
        new, k = re.subn(r"/\* colours:start.*?/\* colours:end \*/", lambda _: css, s, flags=re.S)
        if not k: print(f"make: no /* colours:start */ ... /* colours:end */ block in {a.write}"); return 1
        open(a.write, "w").write(new); print(f"wrote color tokens into {a.write}")
    else:
        print(css)
    return 0


if __name__ == "__main__":
    sys.exit(main())
