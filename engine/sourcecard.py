#!/usr/bin/env python3
"""sourcecard.py - E3 real-source card: screenshot a real page and find the exact phrase on it, so an explainer can
slide the page in and land a highlight box on the words (engine/explain.html, element type "image").

sourcecard.py <url or file.html> "<exact phrase>" <out.png> [--width 1280] [--height 760] [--context 0.55]
              [--wait 1.0] [--dark]

Opens the page in headless Chromium (Playwright), finds the first visible text match of the phrase (case-insensitive,
whitespace-insensitive, across inline tags; block boundaries, cells and <br> count as a space; hidden copies are
skipped) with a DOM text walk, scrolls it into view, measures it again after the last scroll, and writes:
  <out.png>    the screenshot, cropped so the phrase sits about --context of the way down
  <out.json>   {"url", "phrase", "box": [x0, y0, x1, y1] as fractions of the PNG (the whole phrase), "rects": one
               box per line of text (a phrase that wraps gets two), "taken": date, "credit"}
Use box and rects as the image element's "box" / "rects" in storyboard.json (the highlight is drawn per line);
--also "<phrase>" boxes more phrases on the same screenshot ("groups": one entry per phrase, each with its rects; an
image element's "groups" with an "at" each lands them one after another); "credit" (the page's host and title) goes under the card.
The page is only read; nothing is posted. Pages with cookie banners: pass --dark to hide fixed overlays.
Exit 1 when the phrase is not on the page (the error lists the closest text found).
"""
import argparse, datetime, json, os, sys
from urllib.parse import urlparse

FIND_JS = r"""
({ phrase, scroll }) => {
  const norm = (s) => s.replace(/\s+/g, ' ').toLowerCase();
  const want = norm(phrase).trim();
  if (!want) return { found: false, hint: '' };
  const blockOf = (el) => { while (el && el !== document.body) { const d = getComputedStyle(el).display;
    if (d !== 'inline' && d !== 'inline-block' && d !== 'contents') return el; el = el.parentElement; } return document.body; };
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT);
  const nodes = []; let text = '', lastBlock = null;
  while (walker.nextNode()) {
    const n = walker.currentNode;
    if (n.nodeType === 1) { if (n.tagName === 'BR') text += ' '; continue; }
    const pe = n.parentElement;
    if (!pe || (pe.checkVisibility && !pe.checkVisibility({ checkVisibilityCSS: true, checkOpacity: true }))) continue;
    const blk = blockOf(pe);
    if (lastBlock && blk !== lastBlock) text += ' ';        // a virtual space between blocks / cells / items
    lastBlock = blk;
    nodes.push({ n, at: text.length }); text += n.nodeValue;
  }
  const raw2 = []; let normText = ''; let prevSpace = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i], sp = /\s/.test(c);
    if (sp && prevSpace) continue;
    const lc = sp ? ' ' : c.toLowerCase();
    for (let u = 0; u < lc.length; u++) raw2.push(i);       // one entry per output code unit
    normText += lc; prevSpace = sp;
  }
  const locate = (pos) => { let lo = 0; for (let i = 0; i < nodes.length; i++) if (nodes[i].at <= pos) lo = i; return [nodes[lo].n, pos - nodes[lo].at]; };
  for (let k = normText.indexOf(want); k >= 0; k = normText.indexOf(want, k + 1)) {   // first visible occurrence
    const a = raw2[k], b = raw2[k + want.length - 1] + 1;
    const [sn, so] = locate(a), [en, eo] = locate(b - 1);
    const r = document.createRange();
    try { r.setStart(sn, Math.min(so, sn.nodeValue.length)); r.setEnd(en, Math.min(eo + 1, en.nodeValue.length)); } catch (e) { continue; }
    if (scroll) sn.parentElement.scrollIntoView({ block: 'center' });
    const rects = [...r.getClientRects()].filter((q) => q.width > 1 && q.height > 1);
    if (!rects.length) continue;
    const lines = [];
    rects.sort((p, q) => p.top - q.top || p.left - q.left).forEach((q) => {
      const L = lines.find((l) => Math.abs(l.top - q.top) < q.height * 0.5);
      if (L) { L.left = Math.min(L.left, q.left); L.right = Math.max(L.right, q.right); L.bottom = Math.max(L.bottom, q.bottom); }
      else lines.push({ left: q.left, right: q.right, top: q.top, bottom: q.bottom });
    });
    // viewport coordinates (the caller measures again after its last scroll)
    return { found: true, title: document.title, vw: innerWidth, vh: innerHeight, docTop: Math.min(...lines.map((l) => l.top)) + scrollY,
             lines: lines.map((l) => [l.left, l.top, l.right, l.bottom]) };
  }
  const words = want.split(' ').filter((w) => w.length > 3);
  return { found: false, hint: words.filter((w) => normText.includes(w)).join(', ') };
}
"""

HIDE_OVERLAYS_JS = r"""
() => { for (const el of document.querySelectorAll('body *')) { const s = getComputedStyle(el);
  if ((s.position === 'fixed' || s.position === 'sticky') && el.offsetHeight < innerHeight * 0.9) el.style.display = 'none'; } }
"""


def main(argv=None):
    ap = argparse.ArgumentParser(description="E3 real-source card: screenshot + exact-phrase box")
    ap.add_argument("src"); ap.add_argument("phrase"); ap.add_argument("out")
    ap.add_argument("--width", type=int, default=1280); ap.add_argument("--height", type=int, default=760)
    ap.add_argument("--context", type=float, default=0.55, help="where the phrase sits vertically in the crop (0-1)")
    ap.add_argument("--wait", type=float, default=1.0, help="seconds to let the page settle")
    ap.add_argument("--dark", action="store_true", help="hide fixed/sticky overlays (cookie banners, headers)")
    ap.add_argument("--also", action="append", default=[],
                    help="another exact phrase to box on the same screenshot (repeatable); written to \"groups\"")
    a = ap.parse_args(argv)
    if a.src.lower().endswith(".pdf"):
        sys.exit("sourcecard: PDFs aren't supported (headless Chromium downloads them); open the PDF, save the page as "
                 "an image or HTML, or point at the web page it came from")
    url = a.src if "://" in a.src else "file://" + os.path.abspath(a.src)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        try:
            pg = b.new_page(viewport={"width": a.width, "height": a.height}, device_scale_factor=1.5)
            pg.goto(url, wait_until="networkidle", timeout=60000)
            pg.wait_for_timeout(int(a.wait * 1000))
            if a.dark:
                pg.evaluate(HIDE_OVERLAYS_JS)
            r = pg.evaluate(FIND_JS, {"phrase": a.phrase, "scroll": True})
            if not r.get("found"):
                sys.exit(f"sourcecard: phrase not found (visible) on the page: {a.phrase!r}" +
                         (f" (words that are there: {r['hint']})" if r.get("hint") else ""))
            full_h = pg.evaluate("() => document.documentElement.scrollHeight")
            top = max(0, min(full_h - a.height, r["docTop"] - a.context * a.height))
            pg.evaluate(f"() => window.scrollTo(0, {top})")
            pg.wait_for_timeout(400)
            if a.dark:
                pg.evaluate(HIDE_OVERLAYS_JS)
            r2 = pg.evaluate(FIND_JS, {"phrase": a.phrase, "scroll": False})   # measured where the screenshot is
            if r2.get("found"):
                r = r2
            extra = []
            for ph in a.also:
                rx = pg.evaluate(FIND_JS, {"phrase": ph, "scroll": False})
                if not rx.get("found"):
                    sys.exit(f"sourcecard: --also phrase not found on the page: {ph!r}")
                extra.append((ph, rx))
            pg.screenshot(path=a.out)
        finally:
            b.close()
    vw, vh = r["vw"], r["vh"]
    rects = [[round(l[0] / vw, 4), round(l[1] / vh, 4), round(l[2] / vw, 4), round(l[3] / vh, 4)] for l in r["lines"]]
    box = [min(x[0] for x in rects), min(x[1] for x in rects), max(x[2] for x in rects), max(x[3] for x in rects)]
    host = urlparse(url).netloc or os.path.basename(a.src)
    to_rects = lambda rr: [[round(l[0] / rr["vw"], 4), round(l[1] / rr["vh"], 4), round(l[2] / rr["vw"], 4),
                            round(l[3] / rr["vh"], 4)] for l in rr["lines"]]
    groups = [{"phrase": a.phrase, "rects": rects}] + [{"phrase": ph, "rects": to_rects(rx)} for ph, rx in extra]
    meta = {"url": url, "phrase": a.phrase, "box": [round(v, 4) for v in box], "rects": rects, "groups": groups,
            "taken": datetime.date.today().isoformat(), "title": r.get("title", ""),
            "credit": f"{host} · {r.get('title', '')}".strip(" ·")}
    json.dump(meta, open(os.path.splitext(a.out)[0] + ".json", "w"), indent=1)
    print(f"source card: {a.out}  box {meta['box']}  ({meta['credit']})")


if __name__ == "__main__":
    main()
