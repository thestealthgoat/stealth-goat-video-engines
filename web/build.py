#!/usr/bin/env python3
"""web/build.py - the website kit: one site.json + a profile -> a static site (no build step, no tracking by default).

build.py <site.json> --out DIR [--profile P]

A site is one template hero (W1-W5) plus the section kit, with the brand from the profile (colours, the profile's
OFL fonts copied in with their licences) and the website compliance checklist built in:
  - legal pages drafted from the site's real facts: privacy (what each form field is for, sharing, retention, the
    cookie note, the data-deletion request route), terms, and a cookie policy + consent banner only when the site loads
    something non-essential (analytics, embeds); all marked DRAFT for review and linked in every footer;
  - forms: every field needs a "why" (collect only what's needed), an unchecked consent box with the privacy link,
    labels, keyboard focus; no pre-checked boxes, no urgency, no countdowns;
  - every image needs alt text ("" only when marked decorative) and a source + licence line (assets.json is written);
  - UI motion is spring.js 'ui' / 'uiExit' (no bounce, opacity never overshoots); prefers-reduced-motion turns it off.
Templates (web/templates/): w4 cinematic service business (pinned scroll-scrubbed build sequence ending on the money
shot, then dark editorial sections) · w1 scroll-built story · w2 3D isometric scroll world · w3 drone flyover over an
orthomosaic · w5 3D glass showcase. Section types: stats, features, process, area, gallery, form, faq, cta, text.
Then run web/compliance.py on the output (the gate) and web/preview.py for screenshots + a scroll-through video.
"""
import argparse, hashlib, html, importlib, json, os, re, shutil, sys
from urllib.parse import urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "engine")); sys.path.insert(0, HERE)
import vprofile as prof  # noqa: E402

E = html.escape


def rel_luma(hex_):
    h = hex_.lstrip("#"); c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    c = [v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4 for v in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def contrast(a, b):
    la, lb = sorted((rel_luma(a), rel_luma(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def mix(a, b, k):
    a, b = a.lstrip("#"), b.lstrip("#")
    return "#" + "".join(f"{int(round(int(a[i:i + 2], 16) + (int(b[i:i + 2], 16) - int(a[i:i + 2], 16)) * k)):02x}" for i in (0, 2, 4))


def palette(P):
    """site colours from the profile, adjusted until body text, muted text and the accent (eyebrows and links are small
    text) all pass 4.5:1 on both grounds (bg and the band colour bg2). The ground is always dark, so a dark profile text
    colour is replaced by white."""
    cols = P.get("brand.colors") or {}
    prim, acc = P.color("primary"), P.color("accent")
    text = P.color("text") if "text" in cols else "#ffffff"
    bg = P.color("primary_deep") if "primary_deep" in cols else mix(prim, "#000000", 0.62)
    k = 0.62
    while contrast(text, bg) < 7 and k < 0.95:              # deepen the ground until body text is comfortably readable
        k += 0.04; bg = mix(prim, "#000000", k)
    bg2 = mix(bg, prim, 0.35)
    worst = lambda c: min(contrast(c, bg), contrast(c, bg2))
    if worst(text) < 4.5:                                   # profile text is dark: the ground is always dark, use light text
        text = "#ffffff" if worst("#ffffff") >= worst("#111111") else "#111111"
    muted = mix(text, bg, 0.28)
    for _ in range(40):                                     # bounded: mixing toward text always gets there (text passes)
        if worst(muted) >= 4.5: break
        muted = mix(muted, text, 0.2)
    else:
        muted = text
    accent = acc
    for _ in range(40):
        if worst(accent) >= 4.5: break
        accent = mix(accent, "#ffffff", 0.15)
    else:
        accent = text
    on_accent = "#111111" if contrast("#111111", accent) >= contrast("#ffffff", accent) else "#ffffff"
    return {"bg": bg, "bg2": bg2, "text": text, "muted": muted, "accent": accent, "on_accent": on_accent, "primary": prim}


def fonts(P, out):
    """the profile's head / body fonts copied in with their licence files (the site only ships licensed fonts)"""
    os.makedirs(os.path.join(out, "fonts"), exist_ok=True)
    have = P.get("brand.fonts") or {}; faces, log = [], []
    for fam, role in (("Head", "head"), ("Body", "body"), ("BodySB", "body_semibold")):
        src = P.font(role if role in have else "body"); name = os.path.basename(src)
        shutil.copy2(src, os.path.join(out, "fonts", name))
        lic = font_licence(src)
        if lic:
            ofl = os.path.basename(lic).lower().startswith("ofl")
            dst = os.path.basename(lic) if re.sub(r"^(ofl|license|licence)[-_ ]?", "", os.path.splitext(os.path.basename(lic).lower())[0]) \
                else f"{'OFL' if ofl else 'LICENSE'}-{os.path.splitext(name)[0]}.txt"          # a bare OFL.txt gets the font's name
            shutil.copy2(lic, os.path.join(out, "fonts", dst))
            licence = f"SIL OFL 1.1 (fonts/{dst})" if ofl else f"see fonts/{dst}"
        else:
            licence = "UNSPECIFIED (no licence file next to the font: add OFL-<Family>.txt)"
        faces.append(f"@font-face{{font-family:'{fam}';src:url('../fonts/{name}');font-display:swap}}")   # site.css lives in assets/
        log.append({"file": f"fonts/{name}", "kind": "font", "source": "resources/fonts (bundled)" if os.path.dirname(src) == os.path.join(REPO, "resources", "fonts")
                    else os.path.relpath(src, REPO), "licence": licence})
    return "\n".join(faces), log


def font_licence(src):
    """the licence file for a font: OFL-<Family>.txt / LICENSE-<Family>.txt beside it whose family is the longest prefix
    of the font's file stem (BarlowCondensed-Bold.ttf -> OFL-Barlow.txt), else a bare OFL.txt / LICENSE.txt (a
    Google-Fonts-style folder for one family); None when there is none"""
    d = os.path.dirname(src); stem = re.sub(r"[^a-z0-9]", "", os.path.splitext(os.path.basename(src))[0].split("-")[0].lower())
    best, bare = None, None
    for f in sorted(os.listdir(d)):
        fl = f.lower()
        if not fl.startswith(("ofl", "license", "licence")) or os.path.isdir(os.path.join(d, f)): continue
        key = re.sub(r"[^a-z0-9]", "", re.sub(r"^(ofl|license|licence)", "", os.path.splitext(fl)[0]))
        if not key: bare = bare or f
        elif stem.startswith(key) and (best is None or len(key) > len(best[0])): best = (key, f)
    f = best[1] if best else bare
    return os.path.join(d, f) if f else None


def img(site, out, src, alt, log, width=1600, decorative=False, credit=None, licence=None):
    """copy + resize an image into the site; refuse missing alt text; log its source and licence"""
    from PIL import Image
    base = os.path.dirname(os.path.abspath(site["_path"]))
    path = src if os.path.isabs(src) else os.path.join(base, src)
    if not decorative and not (alt or "").strip():
        raise SystemExit(f"build: image {src} has no alt text (give 'alt', or 'decorative': true)")
    os.makedirs(os.path.join(out, "img"), exist_ok=True)
    with open(path, "rb") as fh: key = hashlib.sha1(fh.read()).hexdigest()[:8]     # same stem from two folders, or a replaced photo: new name
    name = re.sub(r"[^a-z0-9]+", "-", os.path.splitext(os.path.basename(path))[0].lower()).strip("-") + f"-{key}-{width}.jpg"
    dst = os.path.join(out, "img", name)
    if not os.path.isfile(dst):
        im = Image.open(path).convert("RGB")
        if im.width > width: im = im.resize((width, int(im.height * width / im.width)), Image.LANCZOS)
        im.save(dst, quality=82, optimize=True, progressive=True)
    # MISSING = site.json says nothing (the gate FAILs); "UNSPECIFIED" written in site.json = an open question for the owner
    log.append({"file": f"img/{name}", "kind": "image", "source": credit or site.get("images_owner") or "MISSING",
                "licence": licence or site.get("images_licence") or "MISSING", "alt": alt or ""})
    return f"img/{name}"


def vendor_three(out, log, addons=()):
    """three.js shipped with the site (MIT, from logo/node_modules; no CDN request, so nothing third-party loads).
    addons: e.g. ("controls/OrbitControls.js", "environments/RoomEnvironment.js"). Returns the <script type=importmap>
    for <head>, so a template's module can `import * as THREE from 'three'` and `import ... from 'three/addons/...'`."""
    src = os.path.join(REPO, "logo", "node_modules", "three")
    dst = os.path.join(out, "assets", "vendor", "three"); os.makedirs(os.path.join(dst, "addons"), exist_ok=True)
    shutil.copy2(os.path.join(src, "build", "three.module.min.js"), os.path.join(dst, "three.module.min.js"))
    shutil.copy2(os.path.join(src, "LICENSE"), os.path.join(dst, "LICENSE"))
    if not any(x.get("file") == "assets/vendor/three/three.module.min.js" for x in log):
        log.append({"file": "assets/vendor/three/three.module.min.js", "kind": "library", "source": "three.js (npm three)", "licence": "MIT"})
    for ad in addons:
        os.makedirs(os.path.dirname(os.path.join(dst, "addons", ad)), exist_ok=True)
        shutil.copy2(os.path.join(src, "examples", "jsm", ad), os.path.join(dst, "addons", ad))
    return '<script type="importmap">{"imports":{"three":"./assets/vendor/three/three.module.min.js","three/addons/":"./assets/vendor/three/addons/"}}</script>'


# ---------------------------------------------------------------- section kit
def sec_head(s):
    eb = f'<p class="eyebrow">{E(s["eyebrow"])}</p>' if s.get("eyebrow") else ""
    return f'{eb}<h2 class="reveal">{E(s["title"])}</h2>' + (f'<p class="lede reveal">{E(s["lede"])}</p>' if s.get("lede") else "") if s.get("title") else eb


def section(site, s, out, log):
    t = s["type"]; sid = s.get("id", t)
    if t == "stats":
        items = "".join(f'<div class="stat reveal"><div class="stat-v" data-count="{E(str(i["value"]))}">{E(str(i["value"]))}</div>'
                        f'<div class="stat-l">{E(i["label"])}</div>' + (f'<div class="stat-src">{E(i["source"])}</div>' if i.get("source") else "") + '</div>'
                        for i in s["items"])
        return f'<section class="band" id="{sid}">{sec_head(s)}<div class="stats">{items}</div></section>'
    if t == "features":
        items = "".join(f'<div class="feat reveal"><h3>{E(i["title"])}</h3><p>{E(i["text"])}</p>'
                        + (f'<p><a href="{E(i["href"])}" rel="noopener">{E(i.get("link", i["href"]))}</a></p>' if i.get("href") else "")
                        + '</div>' for i in s["items"])
        media = ""
        if s.get("image"):
            im = s["image"]; media = f'<img class="reveal" src="{img(site, out, im["src"], im.get("alt"), log, credit=im.get("credit"), licence=im.get("licence"))}" alt="{E(im.get("alt", ""))}" loading="lazy">'
        if not media:                                            # no picture: the text runs full width, the items in columns
            return f'<section id="{sid}">{sec_head(s)}<div class="feats feats-wide">{items}</div></section>'
        return f'<section id="{sid}"><div class="split">{media}<div>{sec_head(s)}<div class="feats">{items}</div></div></div></section>'
    if t == "process":
        items = "".join(f'<li class="reveal"><span class="step-n">{n + 1:02d}</span><div><h3>{E(i["title"])}</h3><p>{E(i["text"])}</p></div></li>' for n, i in enumerate(s["steps"]))
        return f'<section id="{sid}">{sec_head(s)}<ol class="process">{items}</ol></section>'
    if t == "area":
        places = "".join(f"<li>{E(p)}</li>" for p in s.get("places", []))
        return f'<section class="band" id="{sid}">{sec_head(s)}<ul class="places reveal">{places}</ul>' + (f'<p class="note">{E(s["note"])}</p>' if s.get("note") else "") + "</section>"
    if t == "gallery":
        items = "".join(f'<figure class="reveal"><img src="{img(site, out, i["src"], i.get("alt"), log, 1200, credit=i.get("credit"), licence=i.get("licence"))}" alt="{E(i.get("alt", ""))}" loading="lazy">'
                        + (f'<figcaption>{E(i["caption"])}</figcaption>' if i.get("caption") else "") + "</figure>" for i in s["images"])
        return f'<section id="{sid}">{sec_head(s)}<div class="gallery">{items}</div></section>'
    if t == "faq":
        items = "".join(f'<details class="reveal"><summary>{E(i["q"])}</summary><p>{E(i["a"])}</p></details>' for i in s["items"])
        return f'<section id="{sid}">{sec_head(s)}<div class="faq">{items}</div></section>'
    if t == "cta":
        return (f'<section class="cta band" id="{sid}">{sec_head(s)}<a class="btn" href="{E(s.get("href", "#contact"))}">{E(s.get("button", "Get in touch"))}</a></section>')
    if t == "text":
        return f'<section id="{sid}">{sec_head(s)}' + "".join(f'<p class="reveal">{E(p)}</p>' for p in s.get("paragraphs", [])) + "</section>"
    if t == "form":
        fields = []
        for f in s["fields"]:
            if not f.get("why"):
                raise SystemExit(f"build: form field {f['name']!r} has no 'why' (collect only what's needed: say what it's for)")
            req = " required" if f.get("required") else ""
            lab = f'<label for="f-{f["name"]}">{E(f["label"])}{"" if f.get("required") else " <span class=opt>(optional)</span>"}</label>'
            if f.get("type") == "textarea":
                ctl = f'<textarea id="f-{f["name"]}" name="{f["name"]}" rows="4"{req}></textarea>'
            elif f.get("type") == "select":
                ctl = f'<select id="f-{f["name"]}" name="{f["name"]}"{req}><option value="">Choose…</option>' + "".join(f"<option>{E(o)}</option>" for o in f["options"]) + "</select>"
            else:
                ctl = f'<input id="f-{f["name"]}" name="{f["name"]}" type="{f.get("type", "text")}" autocomplete="{f.get("autocomplete", "on")}"{req}>'
            fields.append(f'<div class="field">{lab}{ctl}</div>')
        action = s.get("action") or ""
        consent = (f'<div class="field consent"><input id="f-consent" name="consent" type="checkbox" required>'
                   f'<label for="f-consent">{E(s.get("consent_text", "I agree that you may use these details to answer my request."))} '
                   f'<a href="privacy.html">Privacy policy</a></label></div>')
        note = "" if action else '<p class="note" data-needs-owner="form endpoint">Form endpoint not set yet: this form does not send anywhere.</p>'
        return (f'<section class="band" id="{sid}">{sec_head(s)}<form class="form reveal" method="post" action="{E(action)}" novalidate>{"".join(fields)}{consent}'
                f'<button class="btn" type="submit">{E(s.get("button", "Send"))}</button><p class="form-msg" role="status" aria-live="polite"></p>{note}</form></section>')
    raise SystemExit(f"build: unknown section type {t!r}")


# ---------------------------------------------------------------- legal pages (drafts, from the site's own facts)
def legal_pages(site, forms, third, cookies_needed):
    b = site["business"]; name = b["legal_name"]; email = b.get("email", ""); phone = b.get("phone", ""); eff = site.get("legal", {}).get("effective", "")
    tel = re.sub(r"[^0-9+]", "", phone)
    if email:      # the data-deletion route (11) is always a working link: email, or the phone when there is no email
        route = f'email <a href="mailto:{E(email)}?subject=Data%20request">{E(email)}</a> with the subject "Data request"'
        contact_link = f'<a href="mailto:{E(email)}">{E(email)}</a>'
    elif tel:
        route = f'call or text <a href="tel:{E(tel)}">{E(phone)}</a> and say it is a data request'
        contact_link = f'<a href="tel:{E(tel)}">{E(phone)}</a>'
    else:
        raise SystemExit("build: business needs an email or a phone (the data-deletion route and the footer contact)")
    retention = site.get("legal", {}).get("retention", "as long as needed to answer your request and keep a record of the work, and no longer than 2 years")
    approved = site.get("legal", {}).get("approved")     # "2026-11-09 by <name>": the owner accepted the wording as written
    draft = "" if approved else '<p class="draft">DRAFT: plain-language template written for this site. Review it (ideally with a lawyer) before launch.</p>'
    fields = "".join(f"<li><strong>{E(f['label'])}</strong>: {E(f['why'])}</li>" for form in forms for f in form["fields"])
    procs = {}                                   # form processors (Formspree, a CRM...): every form submission goes to them
    for form in forms:
        host = urlparse(form.get("action") or "").netloc
        if host: procs.setdefault(host, form.get("processor", host))
    sharing = ("".join(f"<li><strong>{E(nm)}</strong> ({E(host)}): the form details above, to deliver your message to us (form processor)</li>" for host, nm in procs.items())
               + "".join(f"<li><strong>{E(t['name'])}</strong>: {E(t['collects'])} ({E(t['why'])})</li>" for t in third)
               or "<li>None. This site loads no analytics, ad pixels, chat widgets or embeds.</li>")
    cookie_note = ("This site uses the cookies listed in the <a href=\"cookies.html\">cookie policy</a>; non-essential ones load only after you accept them in the banner."
                   if cookies_needed else "This site sets no tracking cookies. It remembers nothing about you between visits except your cookie choice, if a banner was shown.")
    privacy = f"""{draft}<h1>Privacy policy</h1><p class="eff">Effective {E(eff)}</p>
<p>This policy explains what {E(name)} collects through this website, why, and what you can ask us to do with it.</p>
<h2>What we collect and why</h2><ul>{fields or '<li>Nothing: the site has no forms.</li>'}</ul>
<p>We only use these details to answer your request. We do not sell them.</p>
<h2>Who it is shared with</h2><ul>{sharing}</ul>
<h2>How long we keep it</h2><p>We keep form messages {E(retention)}.</p>
<h2>Cookies</h2><p>{cookie_note}</p>
<h2>Your choices: see, correct or delete your data</h2><p id="data-deletion">To see, correct or delete what we hold about you,
{route}, or use the <a href="data-request.html">data request page</a>.
We answer within 30 days.</p>
<h2>Children</h2><p>This site is not meant for children under 13 and we do not knowingly collect their information.</p>
<h2>Contact</h2><p>{E(name)} · {contact_link}{(' · ' + E(phone)) if email and phone else ''}{(' · ' + E(b['address'])) if b.get('address') else ''}</p>"""
    terms = f"""{draft}<h1>Terms of use</h1><p class="eff">Effective {E(eff)}</p>
<p>By using this website you agree to these terms. If you don't agree, please don't use the site.</p>
<h2>The content</h2><p>The text, photos and graphics belong to {E(name)} or are used with permission. Please don't copy them without asking.</p>
<h2>Quotes and prices</h2><p>Anything on this site is general information, not a binding offer. A written quote from us is what counts.</p>
<h2>Liability</h2><p>We work to keep the site accurate and available but can't promise it is free of errors or always online.</p>
<h2>Changes</h2><p>We may update these terms; the effective date above shows the latest version.</p>
<h2>Contact</h2><p>{contact_link}</p>"""
    request = f"""{draft}<h1>Data request</h1><p>Ask to see, correct or delete the information you sent us through this website.</p>
<p id="data-deletion">To make a request, {route}. Give the name and contact details you used and what you want us to do.
We confirm within 30 days and never ask for more than we need to find your message.</p>"""
    cookies = None
    if cookies_needed:
        rows = "".join(f"<tr><td>{E(t['name'])}</td><td>{E(t['collects'])}</td><td>{E(t.get('cookie', 'see provider'))}</td><td>Only after you accept</td></tr>" for t in third)
        cookies = f"""{draft}<h1>Cookie policy</h1><p class="eff">Effective {E(eff)}</p><p>Essential: one entry that remembers your cookie choice. Non-essential (below) load only after you choose Accept; Reject keeps them off.</p>
<table><thead><tr><th>Service</th><th>What it collects</th><th>Cookie</th><th>When</th></tr></thead><tbody>{rows}</tbody></table>
<p><button class="btn ghost" type="button" data-cookie-reset>Change my choice</button></p>"""
    return privacy, terms, request, cookies


PAGE = """<!doctype html><html lang="{lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><meta name="description" content="{desc}"><link rel="stylesheet" href="assets/site.css">{head}</head>
<body class="tpl-{tpl}"><a class="skip" href="#main">Skip to content</a>
<header class="top"><a class="brand" href="index.html">{brand}</a><nav aria-label="Main">{nav}</nav></header>
<main id="main">{main}</main>
<footer class="foot"><div><strong>{name}</strong><br>{contact}</div><nav aria-label="Legal"><a href="privacy.html">Privacy</a><a href="terms.html">Terms</a>{cookie_link}<a href="data-request.html">Data request</a></nav>
<p class="credits">{credits}</p></footer>
{banner}<script src="assets/spring.js"></script><script src="assets/site.js"></script>{scripts}</body></html>"""


def clean(out, site):
    """clear what an earlier build into the same --out generated (img/, fonts/, legal pages, an old gate report), so a
    replaced photo or a dropped cookie policy never ships stale. Refuses an --out that holds the site's own sources."""
    o, sd = os.path.realpath(out), os.path.realpath(os.path.dirname(os.path.abspath(site["_path"])))
    if o in (REPO, os.path.expanduser("~"), "/") or sd == o or sd.startswith(o + os.sep):
        raise SystemExit(f"build: --out {out} holds the site's sources (or is the repo); build into a separate folder")
    for d in ("img", "fonts"):
        shutil.rmtree(os.path.join(out, d), ignore_errors=True)
    for f in ("index.html", "privacy.html", "terms.html", "data-request.html", "cookies.html", "assets.json", "compliance.md", "assets/hero.js"):
        if os.path.isfile(os.path.join(out, f)): os.remove(os.path.join(out, f))


def main(argv=None):
    ap = argparse.ArgumentParser(description="the website kit")
    ap.add_argument("site"); ap.add_argument("--out", required=True); prof.add_arg(ap)
    a = ap.parse_args(argv)
    site = json.load(open(a.site)); site["_path"] = a.site
    P = prof.load(a.profile or site.get("profile"))
    out = a.out; clean(out, site); os.makedirs(os.path.join(out, "assets"), exist_ok=True)
    pal = palette(P); faces, log = fonts(P, out)
    tpl = importlib.import_module("templates." + site["template"])
    ctx = {"site": site, "P": P, "pal": pal, "out": out, "log": log, "img": lambda *x, **k: img(site, out, *x, log=log, **k),
           "three": lambda addons=(): vendor_three(out, log, addons)}
    hero_html, hero_css, hero_js, head_extra = tpl.build(ctx)
    secs = "".join(section(site, s, out, log) for s in site.get("sections", []))
    forms = [s for s in site.get("sections", []) if s["type"] == "form"]
    third = site.get("third_party", [])                                      # [{name, collects, why, src, cookie}]
    cookies_needed = bool(third)
    b = site["business"]
    contact = " · ".join(x for x in (f'<a href="mailto:{E(b["email"])}">{E(b["email"])}</a>' if b.get("email") else "",
                                      f'<a href="tel:{E(re.sub(r"[^0-9+]", "", b["phone"]))}">{E(b["phone"])}</a>' if b.get("phone") else "",
                                      E(b.get("city", ""))) if x)
    nav = "".join(f'<a href="index.html#{E(n["id"])}">{E(n["label"])}</a>' for n in site.get("nav", []))
    banner = ""
    if cookies_needed:
        banner = ('<div class="cookie" role="dialog" aria-live="polite" aria-label="Cookie choice" hidden><p>We\'d like to use '
                  + ", ".join(E(t["name"]) for t in third) + ' (see the <a href="cookies.html">cookie policy</a>). Nothing loads until you choose.</p>'
                  '<div class="cookie-btns"><button class="btn" type="button" data-cookie="reject">Reject</button>'
                  '<button class="btn" type="button" data-cookie="accept">Accept</button></div></div>')
    gated = "".join(f'<script type="text/plain" data-consent src="{E(t["src"])}"></script>' for t in third if t.get("src"))
    fl = [x["licence"] for x in log if x["kind"] == "font"]
    credits = E(site.get("credits", "")) + (" · " if site.get("credits") else "") + (
        "Fonts: SIL Open Font License." if fl and all(x.startswith("SIL OFL") for x in fl) else "Fonts: see the licence files in fonts/.")
    common = dict(lang=site.get("lang", "en"), brand=E(site.get("brand_text", b["legal_name"])), nav=nav, name=E(b["legal_name"]), contact=contact,
                  cookie_link='<a href="cookies.html">Cookies</a>' if cookies_needed else "", credits=credits, banner=banner, tpl=site["template"])
    css = open(os.path.join(HERE, "kit", "site.css")).read()
    vars_ = ":root{" + "".join(f"--{k.replace('_', '-')}:{v};" for k, v in pal.items()) + "}"
    open(os.path.join(out, "assets", "site.css"), "w").write(faces + "\n" + vars_ + "\n" + css + "\n" + hero_css)
    shutil.copy2(os.path.join(REPO, "engine", "spring.js"), os.path.join(out, "assets", "spring.js"))
    open(os.path.join(out, "assets", "site.js"), "w").write(open(os.path.join(HERE, "kit", "site.js")).read())
    if hero_js:
        open(os.path.join(out, "assets", "hero.js"), "w").write(hero_js)
    scripts = (head_extra.get("scripts", "") if isinstance(head_extra, dict) else "") + ('<script src="assets/hero.js" type="module"></script>' if hero_js else "") + gated
    head = head_extra.get("head", "") if isinstance(head_extra, dict) else ""
    page = lambda title, main, scripts_="", head_="": PAGE.format(title=E(title), desc=E(site.get("description", "")), head=head_, main=main, scripts=scripts_, **common)
    open(os.path.join(out, "index.html"), "w").write(page(site.get("title", b["legal_name"]), hero_html + secs, scripts, head))
    privacy, terms, request, cookies = legal_pages(site, forms, third, cookies_needed)
    for nm, body in (("privacy", privacy), ("terms", terms), ("data-request", request), ("cookies", cookies)):
        if body: open(os.path.join(out, f"{nm}.html"), "w").write(page(f"{nm.replace('-', ' ').title()} · {b['legal_name']}", f'<article class="legal">{body}</article>'))
    json.dump({"assets": log, "third_party": third}, open(os.path.join(out, "assets.json"), "w"), indent=1)
    size = sum(os.path.getsize(os.path.join(dp, f)) for dp, _, fs in os.walk(out) for f in fs)
    print(f"built {out}: template {site['template']}, {len(site.get('sections', []))} sections, {len(log)} logged assets, {size / 1e6:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
