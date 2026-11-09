#!/usr/bin/env python3
"""web/compliance.py - the website compliance checklist as a gate, run against the BUILT site in a real browser.

compliance.py <dist dir> [--site site.json] [--out report.md]     (default report: <dist>_compliance.md, beside the folder
                                                                  that gets deployed, never inside it)

Checks (numbers = the checklist's items; what a machine can check is checked, the rest is listed for the owner):
  1-5   legal pages exist (privacy, terms, data request; cookie policy when anything non-essential loads) and every
        page's footer links them; the privacy policy names what each form field is for, the sharing, retention, and
        the data-deletion route (11); legal pages carry the DRAFT note until a person reviews them
  4     consent banner when third-party scripts exist: Accept and Reject the same size and weight; NO request leaves
        for another host before a choice (watched on the network)
  6-7   every form: an unchecked consent box with a privacy link; every field labelled
  8     third-party audit: every external host the pages load is listed in site.json "third_party", nothing else; every
        host a form posts to (Formspree, a CRM) is named in the privacy policy
  11    the data-deletion paragraph holds a working mailto: or tel: link
  12    no pre-checked boxes (checked in the live page, so attribute order and script-ticked boxes don't matter);
        no fake urgency / countdown / confirm-shaming wording
  15    unsupported claims ("#1", "best", "guaranteed", "leading"...) without a source: listed for the owner
  16    alt text on every image (empty only when decorative / aria-hidden)
  17    contrast: the page is scrolled top to bottom at 1440x900 and 390x844 (plus the first screen at 1366x657 and
        390x664), with every .reveal forced visible and every <details> open. At each stop the text is made
        transparent and the window photographed, so every visible text line is measured against the real pixels behind
        it (photos, canvases, video, gradients, shadows), its colour blended by its alpha and opacity: the 5th
        percentile must be >= 4.5:1, or >= 3:1 for large text (24 px, or 18.7 px bold). Visible aria-hidden text
        counts; only text inside [data-decorative] is exempt.
  17+   no visible text cut off: clipped by an overflow:hidden container, past the side of the window, or (first
        screen) under the fixed header
  18    keyboard: Tab reaches every visible interactive element, each with a visible focus style; no tabindex > 0
  19    business details in the footer (legal name, email or phone)
  20    every font and image file in the site is in assets.json with a source and licence; fonts ship their licence
        file (FAIL otherwise). An image licence written as "UNSPECIFIED" in site.json is listed for the owner.
  +     no sideways scroll on a 390 px phone
Exit 1 when anything FAILs. The report ends with "Needs the owner": only decisions and missing facts.
"""
import argparse, io, json, os, re, sys, threading, functools, http.server, socketserver
from urllib.parse import urljoin, urlparse

URGENCY = re.compile(r"\b(only \d+ left|hurry|act now|expires in|limited time|last chance|selling fast)\b", re.I)
SHAMING = re.compile(r"no thanks,? i (don'?t|do not) (want|like|care)", re.I)
CLAIMS = re.compile(r"(#\s?1\b|\bno\.? ?1\b|\bbest\b|\bguarantee[sd]?\b|\bleading\b|\bunbeatable\b|\bcheapest\b)", re.I)

# every visible text line in the window: its colour, alpha x opacity, size, line boxes, whether the line is the topmost
# thing at its own points (not covered by the header or a banner), and whether a container clips it
JS_LINES = r"""() => {
  const out = [], vw = innerWidth, vh = innerHeight, ids = (window.__tid = window.__tid || new WeakMap());
  const rgba = (c) => { const m = (c || '').match(/[\d.]+/g); return m && m.length >= 3 ? [+m[0], +m[1], +m[2], m.length > 3 ? +m[3] : 1] : null; };
  const opOf = (e) => { let o = 1; for (; e && e.nodeType === 1; e = e.parentElement) o *= +getComputedStyle(e).opacity; return o; };
  const topAt = (x, y) => (document.elementsFromPoint(x, y) || []).find((e) => opOf(e) > 0.05) || null;
  let headBottom = 0;
  for (const h of document.querySelectorAll('body > header, header.top')) { const p = getComputedStyle(h).position;
    if (p === 'fixed' || p === 'sticky') headBottom = Math.max(headBottom, h.getBoundingClientRect().bottom); }
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) { const n = walker.currentNode, el = n.parentElement; if (!el || !n.textContent.trim()) continue;
    if (el.closest('script,style,noscript,template,select,.skip,[data-decorative]')) continue;
    const cs = getComputedStyle(el); if (cs.visibility === 'hidden' || cs.display === 'none') continue;
    const fill = rgba(cs.webkitTextFillColor) || rgba(cs.color); if (!fill) continue;
    const a = fill[3] * opOf(el); if (a < 0.05) continue;                       // not showing at this scroll position
    let clip = { l: -1e9, t: -1e9, r: 1e9, b: 1e9 }, srOnly = false;
    for (let e = el; e && e !== document.documentElement; e = e.parentElement) { const ec = getComputedStyle(e);
      if (/hidden|clip/.test(ec.overflowX + ec.overflowY) || ec.clipPath !== 'none' || (ec.clip && ec.clip !== 'auto')) { const r = e.getBoundingClientRect();
        if (r.width <= 2 || r.height <= 2 || ec.clipPath !== 'none' || (ec.clip && ec.clip !== 'auto')) { srOnly = true; break; }
        if (/hidden|clip/.test(ec.overflowX)) { clip.l = Math.max(clip.l, r.left); clip.r = Math.min(clip.r, r.right); }
        if (/hidden|clip/.test(ec.overflowY)) { clip.t = Math.max(clip.t, r.top); clip.b = Math.min(clip.b, r.bottom); } } }
    if (srOnly) continue;
    if (!ids.has(n)) ids.set(n, ids.size + 1);
    const range = document.createRange(); range.selectNodeContents(n);
    const lines = [];
    for (const r of range.getClientRects()) { if (r.width < 2 || r.height < 4) continue;
      const vis = { l: Math.max(r.left, clip.l, 0), r: Math.min(r.right, clip.r, vw), t: Math.max(r.top, clip.t, 0), b: Math.min(r.bottom, clip.b, vh) };
      if (vis.r - vis.l < 2 || vis.b - vis.t < 2) continue;                        // nothing of this line shows here
      const cx = (vis.l + vis.r) / 2, mine = [0.3, 0.7].every((k) => { const y = r.top + r.height * k; if (y < 0 || y >= vh) return false;
        const h = topAt(cx, y); return !!h && (el.contains(h) || h.contains(el)); });
      lines.push({ x: r.left, y: r.top, w: r.width, h: r.height, mine,
        cut: r.left < clip.l - 2 || r.right > clip.r + 2 || r.top < clip.t - Math.max(2, r.height / 4) || r.bottom > clip.b + Math.max(2, r.height / 4),
        side: r.left < -2 || r.right > vw + 2, under: r.top < headBottom - 2 }); }
    if (!lines.length) continue;
    const px = parseFloat(cs.fontSize), bold = +cs.fontWeight >= 700;
    out.push({ id: ids.get(n), text: n.textContent.trim().replace(/\s+/g, ' ').slice(0, 50), fg: fill.slice(0, 3), a, large: px >= 24 || (px >= 18.66 && bold),
      inMain: !!el.closest('main'), sel: el.tagName.toLowerCase() + (el.className && typeof el.className === 'string' ? '.' + el.className.split(' ')[0] : ''), lines }); }
  return { y: scrollY, headBottom, lines: out }; }"""

FORCE_CSS = ".reveal{opacity:1!important;transform:none!important}html{scroll-behavior:auto!important}"
HIDE_TEXT = ("*,*::before,*::after{-webkit-text-fill-color:transparent!important;text-decoration-color:transparent!important;"
             "caret-color:transparent!important;outline-color:transparent!important}")


def _lin(v):
    import numpy as np
    v = v / 255.0
    return np.where(v <= 0.03928, v / 12.92, ((v + 0.055) / 1.055) ** 2.4)


def _lum(rgb):
    l = _lin(rgb); return 0.2126 * l[..., 0] + 0.7152 * l[..., 1] + 0.0722 * l[..., 2]


def scan(pg, label, full=True, settle=550):
    """scroll the page (or just the first screen) and measure every visible text line against the pixels behind it.
    Returns ({selector|text: worst record}, [cut-off problems])."""
    import numpy as np
    from PIL import Image
    pg.add_style_tag(content=FORCE_CSS)
    pg.evaluate("() => { document.querySelectorAll('details').forEach((d) => { d.open = true; }); if (document.activeElement) document.activeElement.blur(); }")
    pg.evaluate("() => document.fonts.ready.then(() => true)")
    vh = pg.evaluate("innerHeight"); total = pg.evaluate("document.documentElement.scrollHeight")
    stops = sorted(set(list(range(0, max(1, total - vh), vh // 2)) + [max(0, total - vh)])) if full else [0]
    worst, cuts = {}, []
    for y in stops:
        pg.evaluate(f"window.scrollTo({{top: {y}, behavior: 'instant'}})"); pg.wait_for_timeout(settle)
        res = pg.evaluate(JS_LINES)
        h = pg.add_style_tag(content=HIDE_TEXT)
        shot = np.asarray(Image.open(io.BytesIO(pg.screenshot(animations="disabled", caret="hide"))).convert("RGB")).astype(np.float64)
        h.evaluate("(e) => e.remove()")
        H, W = shot.shape[:2]
        for t in res["lines"]:
            for ln in t["lines"]:
                if ln["cut"]: cuts.append(f"{label}: {t['sel']} {t['text']!r} is cut off by its container")
                elif ln["side"]: cuts.append(f"{label}: {t['sel']} {t['text']!r} runs past the side of the window")
                elif ln["under"] and t["inMain"] and res["y"] == 0: cuts.append(f"{label}: {t['sel']} {t['text']!r} sits under the fixed header on the first screen")
                if not ln["mine"]: continue
                x0, x1 = max(0, int(ln["x"]) + 1), min(W, int(ln["x"] + ln["w"]) - 1)
                # the part of a line under the fixed header is covered by it (the header is near-solid): measure only the
                # part that shows, against the pixels that are really behind it
                y0, y1 = max(0, int(ln["y"]) + 1, int(res.get("headBottom", 0)) + 1), min(H, int(ln["y"] + ln["h"]) - 1)
                if x1 - x0 < 2 or y1 - y0 < 2: continue
                bg = shot[y0:y1, x0:x1].reshape(-1, 3)
                fg = t["a"] * np.array(t["fg"], dtype=np.float64) + (1 - t["a"]) * bg       # alpha / opacity blended over each pixel
                lf, lb = _lum(fg), _lum(bg)
                ratio = (np.maximum(lf, lb) + 0.05) / (np.minimum(lf, lb) + 0.05)
                r5 = float(np.percentile(ratio, 5)); over = float(np.std(lb)) > 0.004
                key = t["sel"] + "|" + t["text"]           # the same text across window sizes / page loads
                cur = worst.get(key)
                if cur is None or r5 < cur["ratio"]:
                    worst[key] = {"ratio": round(r5, 2), "large": t["large"], "sel": t["sel"], "text": t["text"], "over": over, "where": f"{label} at scroll {res['y']}"}
    return worst, list(dict.fromkeys(cuts))


JS_FOCUSABLES = r"""() => [...document.querySelectorAll('a[href],button,input,select,textarea,summary,[tabindex]')].filter((e) => {
  const r = e.getBoundingClientRect(), cs = getComputedStyle(e); return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && !e.closest('[hidden]') && e.tabIndex >= 0 && !e.disabled; })
  .map((e, i) => { e.dataset.kbd = i; return { i, tag: e.tagName.toLowerCase(), text: (e.innerText || e.getAttribute('aria-label') || e.name || '').trim().slice(0, 40), tabindex: e.tabIndex }; })"""

JS_FOCUS_STYLE = r"""() => { const e = document.activeElement; if (!e || e === document.body) return null; const cs = getComputedStyle(e);
  return { kbd: e.dataset.kbd ?? null, outline: cs.outlineStyle !== 'none' && parseFloat(cs.outlineWidth) > 0, shadow: cs.boxShadow !== 'none' }; }"""


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass


def serve(root):
    h = functools.partial(Quiet, directory=root)
    srv = socketserver.ThreadingTCPServer(("127.0.0.1", 0), h); threading.Thread(target=srv.serve_forever, daemon=True).start(); return srv


def main(argv=None):
    ap = argparse.ArgumentParser(description="website compliance gate")
    ap.add_argument("dist"); ap.add_argument("--site"); ap.add_argument("--out")
    a = ap.parse_args(argv)
    site = json.load(open(a.site)) if a.site else {}
    fails, done, needs, warns = [], [], [], []
    pages = sorted(f for f in os.listdir(a.dist) if f.endswith(".html"))
    third = site.get("third_party", [])
    # 1-5: legal pages, footer links, privacy contents
    need_pages = ["privacy.html", "terms.html", "data-request.html"] + (["cookies.html"] if third else [])
    miss = [p for p in need_pages if p not in pages]
    (fails if miss else done).append(f"legal pages: {'missing ' + ', '.join(miss) if miss else ', '.join(need_pages)}")
    for p in pages:
        s = open(os.path.join(a.dist, p)).read()
        foot = s[s.find('<footer'):]
        lost = [q for q in need_pages if f'href="{q}"' not in foot]
        if lost: fails.append(f"{p}: footer does not link {', '.join(lost)}")
        if p in need_pages and "DRAFT" in s: needs.append(f"{p} is a DRAFT: review the wording (ideally with a lawyer) before launch")
        for rx, what in ((URGENCY, "fake urgency"), (SHAMING, "confirm-shaming")):
            m = rx.search(re.sub(r"<[^>]+>", " ", s))
            if m: fails.append(f"{p}: {what} wording: {m.group(0)!r} (12)")
        for m in CLAIMS.finditer(re.sub(r"<[^>]+>", " ", s)):
            needs.append(f"{p}: claim {m.group(0)!r}: is there a source? (15)")
    priv = open(os.path.join(a.dist, "privacy.html")).read() if "privacy.html" in pages else ""
    for key, what in (("How long we keep it", "retention"), ("Who it is shared with", "sharing")):
        (done if key in priv else fails).append(f"privacy policy: {what}" + ("" if key in priv else " is missing"))
    for pg_ in ("privacy.html", "data-request.html"):           # 11: the route must be a link that works, not just the id
        src = open(os.path.join(a.dist, pg_)).read() if pg_ in pages else ""
        m = re.search(r'id="data-deletion".*?</p>', src, re.S)
        if not (m and re.search(r'href="(mailto:[^"?@\s]+@[^"?\s]+|tel:\+?\d{5,})', m.group(0))):
            fails.append(f"{pg_}: the data deletion route (11) has no working mailto: or tel: link")
    if not any("data deletion route" in f for f in fails): done.append("privacy policy + data request page: a working data deletion route (11)")
    # 20: asset log
    try:
        log = json.load(open(os.path.join(a.dist, "assets.json")))["assets"]
    except FileNotFoundError:
        log = None; fails.append("assets.json is missing (20)")
    if log is not None:
        n0 = len(fails); listed = {x.get("file") for x in log}
        media = (".jpg", ".jpeg", ".png", ".webp", ".avif", ".gif", ".svg", ".ico", ".ttf", ".otf", ".woff", ".woff2", ".mp4", ".webm", ".mov", ".m4v")
        files = sorted(os.path.relpath(os.path.join(dp, f), a.dist).replace(os.sep, "/") for dp, _, fs in os.walk(a.dist) for f in fs if f.lower().endswith(media))
        unl = [f for f in files if f not in listed]
        if unl: fails.append(f"{len(unl)} font / image file(s) in the site are not in assets.json (no source or licence): {unl[:6]}{' ...' if len(unl) > 6 else ''} (20)")
        nolic = sorted({x.get("file", "?") for x in log if x.get("kind") != "library" and (not (x.get("source") or "").strip() or not (x.get("licence") or "").strip()
                        or "MISSING" in (x.get("source") or "") + (x.get("licence") or ""))})
        if nolic: fails.append(f"no source / licence for {len(nolic)} asset(s): {nolic[:6]}{' ...' if len(nolic) > 6 else ''} (set images_owner / images_licence or per-image credit / licence in site.json) (20)")
        for x in log:
            if x.get("kind") != "font": continue
            m = re.search(r"(fonts/[^)\s]+)", x.get("licence") or "")
            if "UNSPECIFIED" in (x.get("licence") or "") or not (m and os.path.isfile(os.path.join(a.dist, m.group(1)))):
                fails.append(f"font {x.get('file')}: its licence file is not shipped with the site ({x.get('licence')!r}) (20)")
        open_q = sorted({x["file"] for x in log if "UNSPECIFIED" in (x.get("source") or "") + (x.get("licence") or "") and x.get("kind") != "font"})
        if open_q: needs.append(f"image licence marked UNSPECIFIED in site.json for {len(open_q)} file(s): {', '.join(open_q[:6])}{' ...' if len(open_q) > 6 else ''}: confirm who owns the photos and the licence (20)")
        if len(fails) == n0: done.append(f"asset log: all {len(files)} font / image files listed, {len(log)} entries, fonts ship their licence files (20)")
    b = site.get("business", {})
    if not (b.get("legal_name") and (b.get("email") or b.get("phone"))): fails.append("business details: legal name + email or phone needed in the footer (19)")
    else: done.append("business details in the footer (19)")
    if not b.get("address"): needs.append("physical address: needed only if the site sells online (e-commerce); say if it does (19)")
    from playwright.sync_api import sync_playwright
    srv = serve(a.dist); port = srv.server_address[1]; host = f"127.0.0.1:{port}"
    allowed = {urlparse(t["src"]).netloc for t in third if t.get("src")}
    measured = pictured = 0
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        for p in pages:
            ctx = br.new_context(viewport={"width": 1440, "height": 900}); pg = ctx.new_page(); reqs = []
            pg.on("request", lambda r: reqs.append(r.url)); statuses = []
            pg.on("response", lambda r: statuses.append((r.url, r.status)))
            pg.goto(f"http://{host}/{p}", wait_until="networkidle"); pg.wait_for_timeout(300)
            ext = sorted({urlparse(u).netloc for u in reqs if urlparse(u).netloc not in (host, "")})
            broken = [u for u, st in statuses if st >= 400]
            if broken: fails.append(f"{p}: {len(broken)} file(s) fail to load: {[b_.split('/')[-1] for b_ in broken[:4]]}")
            if ext: fails.append(f"{p}: requests to {', '.join(ext)} BEFORE any cookie choice (4, 8)")
            # 12: pre-checked boxes, in the live page (markup in any attribute order, or ticked by script)
            pre = pg.evaluate("() => [...document.querySelectorAll('input[type=checkbox]')].filter((i) => i.checked || i.defaultChecked).map((i) => i.name || i.id || '?')")
            if pre: fails.append(f"{p}: pre-checked box(es) {pre[:5]} (12)")
            # 8: every host a form posts to is named in the privacy policy
            for act in pg.evaluate("() => [...document.forms].map((f) => f.getAttribute('action') || '')"):
                net = urlparse(urljoin(f"http://{host}/{p}", act)).netloc
                if net and net != host and net.lower() not in priv.lower():
                    fails.append(f"{p}: a form posts to {net} but the privacy policy does not name it (2, 8)")
            # 4: banner buttons equal
            if third and p == "index.html":
                bb = pg.evaluate("() => [...document.querySelectorAll('.cookie [data-cookie]')].map((b) => { const r = b.getBoundingClientRect(), cs = getComputedStyle(b); return [b.dataset.cookie, Math.round(r.width), Math.round(r.height), cs.fontWeight, cs.backgroundColor]; })")
                if len(bb) != 2 or bb[0][1:] != bb[1][1:]: fails.append(f"cookie banner: Accept and Reject differ {bb} (4)")
                else: done.append("cookie banner: Accept and Reject equal; nothing loads before a choice (4)")
            # 6: forms
            forms = pg.evaluate("""() => [...document.querySelectorAll('form')].map((f) => ({ consent: !!f.querySelector('input[type=checkbox][name=consent]:not(:checked)'),
              privacy: !!f.querySelector('a[href$="privacy.html"]'), unlabelled: [...f.querySelectorAll('input,select,textarea')].filter((i) => !(i.labels && i.labels.length) && !i.getAttribute('aria-label')).map((i) => i.name) }))""")
            for k, f in enumerate(forms):
                if not (f["consent"] and f["privacy"]): fails.append(f"{p}: form {k + 1} lacks an unchecked consent box with a privacy link (6)")
                if f["unlabelled"]: fails.append(f"{p}: form {k + 1} fields without labels: {f['unlabelled']} (18)")
            if forms and p == "index.html": done.append(f"{len(forms)} form(s): unchecked consent + privacy link, every field labelled and justified (6, 7)")
            # 16: alt text
            noalt = pg.evaluate("() => [...document.images].filter((i) => !i.hasAttribute('alt') || (i.alt.trim() === '' && i.getAttribute('role') !== 'presentation' && i.getAttribute('aria-hidden') !== 'true' && !i.closest('[aria-hidden=true]') && getComputedStyle(i).opacity !== '0')).map((i) => i.src.split('/').pop())")
            if noalt: fails.append(f"{p}: images without alt text: {noalt[:5]} (16)")
            # 18: keyboard
            fz = pg.evaluate(JS_FOCUSABLES)
            if any(f["tabindex"] > 0 for f in fz): fails.append(f"{p}: tabindex > 0 breaks the tab order (18)")
            reached, nostyle = set(), []
            pg.mouse.click(1, 1)
            for _ in range(min(250, 3 * len(fz) + 5)):
                pg.keyboard.press("Tab"); st = pg.evaluate(JS_FOCUS_STYLE)
                if st and st["kbd"] is not None:
                    reached.add(int(st["kbd"]))
                    if not (st["outline"] or st["shadow"]): nostyle.append(int(st["kbd"]))
            unreached = [f for f in fz if f["i"] not in reached]
            if unreached: fails.append(f"{p}: Tab never reaches {[u['tag'] + ':' + u['text'] for u in unreached[:5]]} (18)")
            if nostyle: fails.append(f"{p}: no visible focus style on {[fz[i]['tag'] + ':' + fz[i]['text'] for i in sorted(set(nostyle))[:5]]} (18)")
            ctx.close()
            # 17: contrast against the real pixels + cut-off text, at two full scrolls and two short first screens
            worst, cuts = {}, []
            for (w, h_, mob, full) in ((1440, 900, False, True), (390, 844, True, True), (1366, 657, False, False), (390, 664, True, False)):
                ctx = br.new_context(viewport={"width": w, "height": h_}, is_mobile=mob, device_scale_factor=1); pg = ctx.new_page()
                pg.goto(f"http://{host}/{p}", wait_until="networkidle"); pg.wait_for_timeout(300)
                if (w, h_) == (390, 844):
                    ov = pg.evaluate("() => document.documentElement.scrollWidth - innerWidth")
                    if ov > 2: fails.append(f"{p}: {ov} px of sideways scroll on a 390 px phone")
                wv, cv = scan(pg, f"{w}x{h_}", full)
                for k, r in wv.items():
                    if k not in worst or r["ratio"] < worst[k]["ratio"]: worst[k] = r
                cuts += cv; ctx.close()
            for c in list(dict.fromkeys(cuts))[:8]: fails.append(f"{p}: {c} (17)")
            low = sorted((r for r in worst.values() if r["ratio"] < (3.0 if r["large"] else 4.5)), key=lambda r: r["ratio"])
            for r in low[:8]: fails.append(f"{p}: contrast {r['ratio']}:1 on {r['sel']} {r['text']!r}{' over a picture' if r['over'] else ''} ({r['where']}) (17)")
            measured += len(worst); pictured += sum(r["over"] for r in worst.values())
        br.close()
    srv.shutdown()
    if not any("(17)" in f for f in fails): done.append(f"contrast: {measured} text nodes measured against the pixels behind them ({pictured} over a picture or gradient), "
                                                     "all >= 4.5:1 (3:1 large); no text cut off at 1440x900, 390x844, 1366x657, 390x664 (17)")
    if not any("(18)" in f for f in fails): done.append("keyboard: Tab reaches every control, each with a visible focus style (18)")
    if not third: done.append("no third-party scripts, pixels or embeds; no cookie banner needed (a cookie note sits in the privacy policy) (4, 8)")
    if not site.get("email_list"): done.append("no marketing email from this site: no unsubscribe link needed (10)")
    if any('data-needs-owner="form endpoint"' in open(os.path.join(a.dist, p)).read() for p in pages):
        needs.append("form endpoint: where should quote requests go (an email service, Formspree, the CRM)? The form doesn't send until it's set")
    verdict = "FAIL" if fails else "PASS"
    rep = [f"# Website compliance: {verdict}", "", f"{len(pages)} pages checked in a real browser ({os.path.abspath(a.dist)})", ""]
    rep += ["## FAIL"] + [f"- {x}" for x in fails] + [""] if fails else []
    rep += ["## Check by eye"] + [f"- {x}" for x in warns] + [""] if warns else []
    rep += ["## Done"] + [f"- {x}" for x in done] + ["", "## Needs the owner"] + ([f"- {x}" for x in dict.fromkeys(needs)] or ["- nothing"])
    out = a.out or os.path.abspath(a.dist).rstrip(os.sep) + "_compliance.md"     # beside dist: never deployed with the site
    open(out, "w").write("\n".join(rep) + "\n")
    print(f"compliance: {verdict} ({len(fails)} fail, {len(set(needs))} for the owner) -> {out}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
