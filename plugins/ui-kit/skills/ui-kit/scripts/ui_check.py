#!/usr/bin/env python3
"""ui_check.py - check a running app or page in a real browser (Playwright + Chromium), the ui-kit way.

  ui_check.py <url or .html file> [--out DIR] [--dark] [--max-tabs 250]

Checks (FAIL = exit 1; WARN = look at it; the report and screenshots go to --out, default ./ui-check):
  keyboard   Tab reaches every visible control; each shows a visible focus style (outline or box-shadow on the
             element or its ::before / ::after); no tabindex > 0. focus-NN.png shows the first stops.
  skip link  the first Tab stop is a link to an anchor on the page (WARN when missing)
  contrast   every visible text line measured against the real pixels behind it (text hidden, page photographed):
             5th percentile >= 4.5:1, or >= 3:1 for large text (24 px, or 18.66 px bold); at 1440x900 and 390x844
  phone      no sideways scroll at 390 px wide
  honest     no fake urgency ("only 3 left", "hurry", "expires in") or confirm-shaming ("No thanks, I don't want...")
  forms      every input / select / textarea has a label; no checkbox is ticked before the user ticks it;
             every button and link has a name
  images     every <img> has alt ("" only for decorative images)
  motion     with prefers-reduced-motion: reduce, no CSS transition or animation longer than 0.01 s is left
Screenshots: desktop.png, phone.png (full page), plus desktop-dark.png / phone-dark.png with --dark.
For an Electron or desktop web view: run its renderer in a browser (its dev-server URL, or the built index.html).
"""
import argparse, io, os, pathlib, re, sys

# honest design (the same wording rules as the engine's website gate, web/compliance.py)
URGENCY = re.compile(r"\b(only \d+ left|hurry|act now|expires in|limited time|last chance|selling fast)\b", re.I)
SHAMING = re.compile(r"no thanks,? i (don'?t|do not) (want|like|care)", re.I)

JS_FOCUSABLES = r"""() => [...document.querySelectorAll('a[href],button,input,select,textarea,summary,[tabindex],[contenteditable="true"]')]
  .filter((e) => { const r = e.getBoundingClientRect(), cs = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && !e.closest('[hidden],[inert]') && e.tabIndex >= 0 && !e.disabled
      && !(e.type === 'hidden'); })
  .map((e, i) => { e.dataset.uiKbd = i;
    const name = (e.getAttribute('aria-label') || (e.labels && e.labels[0] && e.labels[0].innerText) || e.innerText || e.name || e.id || '').trim().replace(/\s+/g, ' ').slice(0, 40);
    return { i, tag: e.tagName.toLowerCase(), name, tabindex: e.tabIndex }; })"""

JS_FOCUS_STYLE = r"""() => { const e = document.activeElement; if (!e || e === document.body) return null;
  const vis = (cs) => (cs.outlineStyle !== 'none' && parseFloat(cs.outlineWidth) > 0) || (cs.boxShadow && cs.boxShadow !== 'none');
  const ok = vis(getComputedStyle(e)) || vis(getComputedStyle(e, '::before')) || vis(getComputedStyle(e, '::after'));
  const r = e.getBoundingClientRect();
  return { kbd: e.dataset.uiKbd ?? null, ok, tag: e.tagName.toLowerCase(), href: e.getAttribute('href') || '',
           box: [r.left + scrollX, r.top + scrollY, r.width, r.height] }; }"""

JS_FORMS = r"""() => {
  const named = (e) => (e.getAttribute('aria-label') || e.getAttribute('aria-labelledby') || e.innerText || e.title || e.value || '').trim()
    || [...e.querySelectorAll('img[alt],svg[aria-label]')].some((i) => (i.alt || i.getAttribute('aria-label') || '').trim());
  const shown = (e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  return {
    unlabelled: [...document.querySelectorAll('input:not([type=hidden]):not([type=submit]):not([type=button]):not([type=reset]),select,textarea')]
      .filter((i) => shown(i) && !(i.labels && i.labels.length) && !i.getAttribute('aria-label') && !i.getAttribute('aria-labelledby'))
      .map((i) => i.name || i.id || i.type),
    prechecked: [...document.querySelectorAll('input[type=checkbox]')].filter((i) => i.checked || i.defaultChecked).map((i) => i.name || i.id || '?'),
    nameless: [...document.querySelectorAll('button,a[href],[role=button]')].filter((e) => shown(e) && !named(e))
      .map((e) => e.tagName.toLowerCase() + (e.className && typeof e.className === 'string' ? '.' + e.className.split(' ')[0] : '')),
    noalt: [...document.images].filter((i) => !i.hasAttribute('alt')).map((i) => (i.currentSrc || i.src).split('/').pop()),
    overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,   // innerWidth grows with the page on a phone
  }; }"""

# every visible text line on the page, in page coordinates: colour (alpha x opacity), size, rects
JS_TEXT = r"""() => {
  const out = [], rgba = (c) => { const m = (c || '').match(/[\d.]+/g); return m && m.length >= 3 ? [+m[0], +m[1], +m[2], m.length > 3 ? +m[3] : 1] : null; };
  const opOf = (e) => { let o = 1; for (; e && e.nodeType === 1; e = e.parentElement) o *= +getComputedStyle(e).opacity; return o; };
  const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  while (w.nextNode()) { const n = w.currentNode, el = n.parentElement; if (!el || !n.textContent.trim()) continue;
    if (el.closest('script,style,noscript,template,option,[data-decorative],.ui-visually-hidden')) continue;
    const cs = getComputedStyle(el); if (cs.visibility === 'hidden' || cs.display === 'none') continue;
    const fill = rgba(cs.webkitTextFillColor) || rgba(cs.color); if (!fill) continue;
    const a = fill[3] * opOf(el); if (a < 0.05) continue;
    const range = document.createRange(); range.selectNodeContents(n); const lines = [];
    for (const r of range.getClientRects()) if (r.width >= 2 && r.height >= 4) lines.push([r.left + scrollX, r.top + scrollY, r.width, r.height]);
    if (!lines.length) continue;
    const px = parseFloat(cs.fontSize), bold = +cs.fontWeight >= 700;
    out.push({ text: n.textContent.trim().replace(/\s+/g, ' ').slice(0, 50), fg: fill.slice(0, 3), a, large: px >= 24 || (px >= 18.66 && bold),
      sel: el.tagName.toLowerCase() + (el.className && typeof el.className === 'string' && el.className ? '.' + el.className.split(' ')[0] : ''), lines }); }
  return out; }"""

HIDE_TEXT = ("*,*::before,*::after{-webkit-text-fill-color:transparent!important;text-decoration-color:transparent!important;"
             "caret-color:transparent!important;outline-color:transparent!important}")
STILL = "*,*::before,*::after{transition:none!important;animation:none!important}"

JS_MOTION = r"""() => { const long = [];
  for (const e of document.querySelectorAll('*')) { const cs = getComputedStyle(e);
    const t = Math.max(...cs.transitionDuration.split(',').map(parseFloat)), a = Math.max(...cs.animationDuration.split(',').map(parseFloat));
    if ((t > 0.01 && cs.transitionProperty !== 'none') || (a > 0.01 && cs.animationName !== 'none'))
      long.push(e.tagName.toLowerCase() + (e.className && typeof e.className === 'string' && e.className ? '.' + e.className.split(' ')[0] : '')); }
  return [...new Set(long)].slice(0, 8); }"""


def lum(rgb):
    import numpy as np
    v = rgb / 255.0
    v = np.where(v <= 0.03928, v / 12.92, ((v + 0.055) / 1.055) ** 2.4)
    return 0.2126 * v[..., 0] + 0.7152 * v[..., 1] + 0.0722 * v[..., 2]


def contrast(pg, label):
    """[(ratio, need, sel, text)] below the line, and how many text nodes were measured"""
    import numpy as np
    from PIL import Image
    pg.add_style_tag(content=STILL)
    pg.evaluate("() => document.fonts.ready.then(() => true)")
    pg.wait_for_timeout(150)
    texts = pg.evaluate(JS_TEXT)
    h = pg.add_style_tag(content=HIDE_TEXT)
    shot = np.asarray(Image.open(io.BytesIO(pg.screenshot(full_page=True, animations="disabled", caret="hide"))).convert("RGB")).astype(np.float64)
    h.evaluate("(e) => e.remove()")
    H, W = shot.shape[:2]; low = {}
    for t in texts:
        for (x, y, w, hh) in t["lines"]:
            x0, x1, y0, y1 = max(0, int(x) + 1), min(W, int(x + w) - 1), max(0, int(y) + 1), min(H, int(y + hh) - 1)
            if x1 - x0 < 2 or y1 - y0 < 2: continue
            bg = shot[y0:y1, x0:x1].reshape(-1, 3)
            fg = t["a"] * np.array(t["fg"], dtype=np.float64) + (1 - t["a"]) * bg
            lf, lb = lum(fg), lum(bg)
            r5 = float(np.percentile((np.maximum(lf, lb) + 0.05) / (np.minimum(lf, lb) + 0.05), 5))
            need = 3.0 if t["large"] else 4.5
            key = t["sel"] + "|" + t["text"]
            if r5 < need and (key not in low or r5 < low[key][0]): low[key] = (round(r5, 2), need, t["sel"], t["text"], label)
    return sorted(low.values()), len(texts)


def main(argv=None):
    ap = argparse.ArgumentParser(description="ui-kit browser check: keyboard, focus, contrast, phone width, forms, motion")
    ap.add_argument("target", help="http(s) URL, or a local .html file")
    ap.add_argument("--out", default="ui-check", help="folder for the report and screenshots (default ./ui-check)")
    ap.add_argument("--dark", action="store_true", help="also check and photograph the dark theme (prefers-color-scheme: dark)")
    ap.add_argument("--max-tabs", type=int, default=250, help="Tab presses at most (default 250)")
    ap.add_argument("--focus-shots", type=int, default=12, help="screenshots of the first N focus stops (default 12)")
    a = ap.parse_args(argv)
    url = a.target if "://" in a.target else pathlib.Path(a.target).resolve().as_uri()
    os.makedirs(a.out, exist_ok=True)
    from playwright.sync_api import sync_playwright
    fails, warns, done = [], [], []
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        schemes = ["light", "dark"] if a.dark else ["light"]
        for scheme in schemes:
            sfx = "" if scheme == "light" else "-dark"
            for (w, h, mob, name) in ((1440, 900, False, "desktop"), (390, 844, True, "phone")):
                ctx = br.new_context(viewport={"width": w, "height": h}, is_mobile=mob, color_scheme=scheme, device_scale_factor=1)
                pg = ctx.new_page(); errs = []
                pg.on("pageerror", lambda e: errs.append(str(e)))
                pg.goto(url, wait_until="networkidle"); pg.wait_for_timeout(400)
                for e in errs[:3]: fails.append(f"{name}{sfx}: script error: {e}")
                f = pg.evaluate(JS_FORMS)
                if mob and f["overflow"] > 2: fails.append(f"phone{sfx}: {f['overflow']} px of sideways scroll at 390 px wide")
                if not sfx and not mob:
                    if f["unlabelled"]: fails.append(f"fields without a label: {f['unlabelled'][:6]}")
                    if f["prechecked"]: fails.append(f"checkbox ticked before the user chose: {f['prechecked'][:6]}")
                    if f["nameless"]: fails.append(f"buttons / links with no name (add text or aria-label): {f['nameless'][:6]}")
                    if f["noalt"]: fails.append(f"images without alt: {f['noalt'][:6]}")
                    body = pg.evaluate("document.body.innerText")
                    for rx, what in ((URGENCY, "fake urgency"), (SHAMING, "confirm-shaming")):
                        m = rx.search(body)
                        if m: fails.append(f"{what} wording: {m.group(0)!r}")
                pg.screenshot(path=os.path.join(a.out, f"{name}{sfx}.png"), full_page=True)
                low, n = contrast(pg, f"{name}{sfx}")
                for r in low[:10]: fails.append(f"contrast {r[0]}:1 (need {r[1]}) on {r[2]} {r[3]!r} ({r[4]})")
                if not low: done.append(f"contrast {name}{sfx}: {n} text nodes measured against the pixels behind them, all pass")
                ctx.close()
        # keyboard: a fresh desktop page in the light theme
        ctx = br.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=1); pg = ctx.new_page()
        pg.goto(url, wait_until="networkidle"); pg.wait_for_timeout(300)
        fz = pg.evaluate(JS_FOCUSABLES)
        if any(x["tabindex"] > 0 for x in fz): fails.append("tabindex > 0 reorders the Tab sequence: use 0 or -1")
        reached, nostyle, first, shots = set(), set(), None, 0
        pg.mouse.click(1, 1)
        for _ in range(min(a.max_tabs, 3 * len(fz) + 5)):
            pg.keyboard.press("Tab"); st = pg.evaluate(JS_FOCUS_STYLE)
            if not st or st["kbd"] is None: continue
            k = int(st["kbd"])
            if first is None: first = st
            if k in reached: continue
            reached.add(k)
            if not st["ok"]: nostyle.add(k)
            if shots < a.focus_shots:
                x, y, w, h = st["box"]; pad = 24
                pg.screenshot(path=os.path.join(a.out, f"focus-{shots + 1:02d}.png"), full_page=True,
                              clip={"x": max(0, x - pad), "y": max(0, y - pad), "width": w + 2 * pad, "height": h + 2 * pad})
                shots += 1
        miss = [x for x in fz if x["i"] not in reached]
        if miss: fails.append(f"Tab never reaches: {[m['tag'] + ':' + m['name'] for m in miss[:6]]}")
        if nostyle: fails.append(f"no visible focus style on: {[fz[i]['tag'] + ':' + fz[i]['name'] for i in sorted(nostyle)[:6]]}")
        if fz and not miss and not nostyle: done.append(f"keyboard: Tab reaches all {len(fz)} controls, each with a visible focus style")
        if first and first["tag"] == "a" and first["href"].startswith("#") and len(first["href"]) > 1 \
                and pg.evaluate("(h) => !!document.getElementById(decodeURIComponent(h.slice(1)))", first["href"]):
            done.append(f"skip link: the first Tab stop jumps to {first['href']}")
        elif fz:
            warns.append("no skip link: make the first Tab stop <a class=\"ui-skip\" href=\"#main\">Skip to content</a>")
        ctx.close()
        # reduced motion
        ctx = br.new_context(viewport={"width": 1440, "height": 900}, reduced_motion="reduce"); pg = ctx.new_page()
        pg.goto(url, wait_until="networkidle"); pg.wait_for_timeout(300)
        long = pg.evaluate(JS_MOTION)
        if long: fails.append(f"with reduced motion on, these still transition or animate: {long}")
        else: done.append("reduced motion: no CSS transition or animation left (check JS-driven motion by eye)")
        ctx.close(); br.close()
    verdict = "FAIL" if fails else "PASS"
    rep = [f"# UI check: {verdict}", "", f"Target: {url}", ""]
    if fails: rep += ["## FAIL"] + [f"- {x}" for x in fails] + [""]
    if warns: rep += ["## Look at"] + [f"- {x}" for x in warns] + [""]
    rep += ["## Passed"] + [f"- {x}" for x in done] + ["", f"Screenshots in {os.path.abspath(a.out)}"]
    open(os.path.join(a.out, "report.md"), "w").write("\n".join(rep) + "\n")
    print("\n".join(rep))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
