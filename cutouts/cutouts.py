#!/usr/bin/env python3
"""Player Cutouts - find, cut, check and file player cutouts from a culled game (runs after Photo Cull).
Every command takes --profile NAME (default: $VIDEO_PROFILE, then local.json): the team uniform colours
(team.uniform), the review-sheet background (brand colour primary), the label font (brand font body) and the
team abbreviation in library file names (team.home_abbr) come from it.

  cutouts.py candidates <cull dir> <Wk>                          cloud: needs the cull dir's rows.json, masks/ and prev960/
      Checks every kept frame for a cutout-able player and writes <dir>/cut_requests.json plus numbered sheets
      <dir>/cutcand_N.jpg. A frame passes if:
        - there is one dominant person (a second person > 15% of him is a reject);
        - nothing is cut off at the top or sides;
        - he is at least 35% of the frame height;
        - he wears the team uniform (team-colour share of his pixels, not the opponent's colours; profile team.uniform);
        - the subject passed the focus pass.
      One frame is kept per burst. Read the sheets and write the jersey numbers you can read into numbers.json:
      {"R5_12345": "12", "R5_23456": null, "R5_34567": "MASCOT"}. Use null for an unreadable number; a name not
      in numbers.json is skipped.
  (Mac)  fullcrop.py <Games dir> cut_requests.json <crops dir>      full-res JPEG crop of each requested player
  cutouts.py cut <crops dir> <numbers.json> <out dir>               cloud: cut + grade + review sheet
      Alpha = BiRefNet general (the most complete people: helmets, dark jerseys, hands, feet; MIT), checked against
      BiRefNet portrait (keeps every person), biggest person kept. (Before 2026-11-09: isnet gated by u2net_human_seg,
      which lost helmets and torsos.) Models: engine/models.py ($U2NET_HOME, local.json "rembg_models", resources/models/rembg).
      Grade A = full body; B = cut at the frame bottom (3/4); X = reject (mask disagreement IoU < 0.8, soft edge
      > 25%, more than one part, cut at the top or sides, or under 1,500 px tall). Writes <out>/png/, <out>/grades.json
      and <out>/review_N.jpg (on the primary colour). LOOK at the review sheets; --override name=A|B|X if a grade is wrong.
  cutouts.py library <out dir> <roster.csv> <library dir> --games-map cull/rows.json ...
      Builds/extends "<library>/#<n> <Name>/{Cutouts,Portraits,Action}", _Unidentified, _Mascot, _index.csv,
      _Overview.jpg, and lib_plan.json (Mac copies the full-res crops into Portraits/Action).
"""
import sys, os, json, csv, re, shutil, collections
import numpy as np, cv2
from PIL import Image, ImageDraw, ImageFont, ImageOps
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'engine'))
import vprofile as prof  # noqa: E402
def _pop_profile():
    """Take --profile NAME / --profile=NAME out of sys.argv (library reads every arg after --games-map)."""
    a = sys.argv
    for i, x in enumerate(a):
        if x == '--profile' and i + 1 < len(a): v = a[i + 1]; del a[i:i + 2]; return v
        if x.startswith('--profile='): del a[i]; return x.split('=', 1)[1]
    return None
P = prof.load(_pop_profile()); FONT = P.font('body'); BG = P.rgb('primary'); ABBR = P.get('team.home_abbr')
# team uniform in OpenCV HSV (H 0-180): share of the player's pixels inside "team" must be >= min, and each
# "reject" colour (opponents) must stay <= max. Bounds: h inclusive, s_gt / v_gt / v_lt strict.
def uniform():
    """team.uniform from the profile (only `candidates` needs it). No generic default: it is the team's own colours."""
    u = P.get('team.uniform', None)
    if not u:
        raise SystemExit(f"cutouts.py candidates: profile {P.name!r} has no team.uniform (OpenCV HSV bands of the team's "
                         "jersey colour and the opponents' colours to reject; see team.uniform in cutouts/README.md)")
    return u
# _index.csv columns (an existing index keeps its own header)
INDEX_FIELDS = ['player', 'number', 'grade', 'cutout', 'source_raw', 'game', 'size', 'full_body', 'mask_agreement']
def arg(k, d=None): return sys.argv[sys.argv.index(k) + 1] if k in sys.argv else d
def share(hh, ss, vv, r):
    m = (hh >= r['h'][0]) & (hh <= r['h'][1]) & (ss > r.get('s_gt', -1)) & (vv > r.get('v_gt', -1))
    if 'v_lt' in r: m &= vv < r['v_lt']
    return float(m.mean())
def rot(im, o): return im.transpose(Image.ROTATE_90) if o == 8 else im.transpose(Image.ROTATE_270) if o == 6 else im.transpose(Image.ROTATE_180) if o == 3 else im
def font(s): return ImageFont.truetype(FONT, s) if os.path.exists(FONT) else ImageFont.load_default()

def sheet(items, out, C=12, TW=166, TH=260, bg=(90, 90, 90)):
    R = (len(items) + C - 1) // C; sh = Image.new('RGB', (C * TW, max(1, R) * TH), bg); d = ImageDraw.Draw(sh); F = font(20)
    for k, (im, lab) in enumerate(items):
        im.thumbnail((TW - 6, TH - 28)); x, y = (k % C) * TW, (k // C) * TH
        sh.paste(im, (x + 3 + (TW - 6 - im.width) // 2, y + 3), im if im.mode == 'RGBA' else None); d.text((x + 4, y + TH - 24), lab, font=F, fill='yellow')
    sh.save(out, quality=85)

def candidates(d, wk):
    UNIFORM = uniform()
    R = json.load(open(f'{d}/rows.json')); rows = [r for r in R['rows'] if r['keep'] and os.path.exists(f"{d}/masks/{r['n']}.png")]
    out = {}; per = collections.defaultdict(list)
    for r in rows:
        m = np.asarray(Image.open(f"{d}/masks/{r['n']}.png")) > 128; H, W = m.shape
        k, lab, st, _ = cv2.connectedComponentsWithStats(m.astype(np.uint8), 8)
        if k < 2: continue
        comps = sorted([(st[i, 4], i) for i in range(1, k)], reverse=True); a0, i0 = comps[0]; x, y, w, h = st[i0, :4]
        if h < 0.35 * H or y <= 2 or x <= 2 or x + w >= W - 2 or (len(comps) > 1 and comps[1][0] > 0.15 * a0): continue
        im = rot(Image.open(f"{d}/prev960/{r['n']}.jpg").convert('RGB'), r['o']); hsv = cv2.cvtColor(np.asarray(im), cv2.COLOR_RGB2HSV); pm = lab == i0
        hh, ss, vv = hsv[..., 0][pm], hsv[..., 1][pm], hsv[..., 2][pm]
        team = share(hh, ss, vv, UNIFORM['team'])
        if team < UNIFORM['team']['min'] or any(share(hh, ss, vv, r) > r['max'] for r in UNIFORM.get('reject', [])): continue
        subj = (r.get('qa') or {}).get('subj') or 0
        c = dict(n=r['n'], o=r['o'], burst=r['burst'], score=subj * h / H, box=[x / W, y / H, (x + w) / W, (y + h) / H], folder=r['folder'], cat=r['cat'], wk=wk)
        per[r['burst']].append(c)
    best = sorted([max(v, key=lambda c: c['score']) for v in per.values()], key=lambda c: c['n'])
    json.dump({c['n']: c for c in best}, open(f'{d}/cut_requests.json', 'w'))
    for s in range(0, len(best), 96):
        items = []
        for k, c in enumerate(best[s:s + 96]):
            im = rot(Image.open(f"{d}/prev960/{c['n']}.jpg").convert('RGB'), c['o']).convert('RGBA'); im.putalpha(Image.open(f"{d}/masks/{c['n']}.png"))
            W, H = im.size; b = c['box']; items.append((im.crop((int(b[0] * W), int(b[1] * H), int(b[2] * W), int(b[3] * H))), f"{s + k} {c['n'][-5:]}"))
        sheet(items, f'{d}/cutcand_{s // 96}.jpg')
    print(f'{wk}: {len(best)} cutout candidates (one per burst) -> cut_requests.json, cutcand_*.jpg. Next: numbers.json')

def cut(crops, numbers, out):
    from rembg import new_session
    try:
        from rapidocr_onnxruntime import RapidOCR; ocr = RapidOCR()
    except Exception: ocr = None
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'engine'))
    import models; models.rembg_home()       # where the model files live (engine/models.py)
    N = json.load(open(numbers)); hs = new_session('birefnet-portrait'); isn = new_session('birefnet-general')
    os.makedirs(f'{out}/png', exist_ok=True); gp = f'{out}/grades.json'; G = json.load(open(gp)) if os.path.exists(gp) else {}
    for n, num in N.items():
        if n in G or not os.path.exists(f'{crops}/{n}.jpg'): continue
        im = ImageOps.exif_transpose(Image.open(f'{crops}/{n}.jpg')).convert('RGB'); im.thumbnail((3000, 3000))   # phone photos stored sideways come upright
        a1 = np.asarray(hs.predict(im)[0].resize(im.size)).astype(np.float32) / 255
        a2 = np.asarray(isn.predict(im)[0].resize(im.size)).astype(np.float32) / 255
        gate = cv2.GaussianBlur(cv2.dilate((a1 > 0.3).astype(np.uint8), np.ones((25, 25), np.uint8)).astype(np.float32), (0, 0), 6)
        a = np.clip(a2 * gate, 0, 1); k, lab, st, _ = cv2.connectedComponentsWithStats((a > 0.5).astype(np.uint8), 8)
        if k > 1:
            big = 1 + int(np.argmax(st[1:, 4])); keep = np.isin(lab, [i for i in range(1, k) if i == big or st[i, 4] > 0.25 * st[big, 4]])
            a = a * cv2.dilate(keep.astype(np.uint8), np.ones((15, 15), np.uint8))
        A = (a * 255).astype(np.uint8); rgba = im.convert('RGBA'); rgba.putalpha(Image.fromarray(A)); rgba = rgba.crop(rgba.getbbox()); rgba.save(f'{out}/png/{n}.png')
        # agreement measured around the kept player only (portrait also keeps bystanders, which aren't a disagreement)
        near = cv2.dilate((a > 0.5).astype(np.uint8), np.ones((61, 61), np.uint8)) > 0
        m1, m2 = (a1 > 0.5) & near, a > 0.5; iou = float((m1 & m2).sum() / max(1, (m1 | m2).sum()))
        e = dict(top=(A[:3] > 128).mean() > 0.01, left=(A[:, :3] > 128).mean() > 0.03, right=(A[:, -3:] > 128).mean() > 0.03, bottom=(A[-3:] > 128).mean() > 0.02)
        semi = float(((A > 25) & (A < 230)).sum() / max(1, (A > 128).sum()))
        k2, _, st2, _ = cv2.connectedComponentsWithStats((A > 128).astype(np.uint8), 8); parts = sum(1 for i in range(1, k2) if st2[i, 4] > 0.01 * (A > 128).sum())
        grade = 'X' if (iou < 0.8 or semi > 0.25 or parts > 1 or e['top'] or e['left'] or e['right'] or rgba.size[1] < 1500) else ('B' if e['bottom'] else 'A')
        digits = [x[1] for x in (ocr(np.asarray(im))[0] or []) if any(ch.isdigit() for ch in x[1]) and float(x[2]) > 0.6] if ocr else []   # (newer RapidOCR gives the score as text)
        G[n] = dict(number=num, grade=grade, iou=round(iou, 3), soft_edge=round(semi, 3), parts=parts, cut=[k for k, v in e.items() if v], size=list(rgba.size), ocr=digits)
        json.dump(G, open(gp, 'w')); print(n, num, grade, digits, flush=True)
    for o in [x for x in sys.argv if '=' in x and x.split('=')[0] in G]:
        nm, g = o.split('='); G[nm]['grade'] = g; G[nm]['override'] = True
    json.dump(G, open(gp, 'w')); ns = list(G)
    for s in range(0, len(ns), 40):
        sheet([(Image.open(f'{out}/png/{n}.png'), f"{s + k} {G[n]['grade']} #{G[n]['number'] or '?'} {n[-5:]}") for k, n in enumerate(ns[s:s + 40])], f'{out}/review_{s // 40}.jpg', C=10, TW=200, TH=330, bg=BG)
    print(collections.Counter(g['grade'] for g in G.values()), '-> look at review_*.jpg')

def library(out, roster, lib):
    G = json.load(open(f'{out}/grades.json')); R = {r['number']: r['name'] for r in csv.DictReader(open(roster))}
    meta = {}
    for p in sys.argv[sys.argv.index('--games-map') + 1:]:
        for c in json.load(open(os.path.join(os.path.dirname(p), 'cut_requests.json'))).values(): meta[c['n']] = c
    clean = lambda s: re.sub(r'\s+', ' ', re.sub(r'["\\/:*?<>|]', '', s)).strip()
    for num, name in R.items():
        for sub in ('Cutouts', 'Portraits', 'Action'): os.makedirs(f'{lib}/{clean(f"#{num} {name}")}/{sub}', exist_ok=True)
    for s in ('_Mascot/Cutouts', '_Unidentified/Cutouts', '_Unidentified/Photos'): os.makedirs(f'{lib}/{s}', exist_ok=True)
    ip = f'{lib}/_index.csv'; rows = list(csv.DictReader(open(ip))) if os.path.exists(ip) else []; have = {r['source_raw'] for r in rows}; plan = []
    for n, g in G.items():
        if g['grade'] == 'X' or n + '.CR3' in have: continue
        num = g['number'] if (g['number'] in R or g['number'] == 'MASCOT') else None
        f = '_Mascot' if num == 'MASCOT' else '_Unidentified' if num is None else clean(f'#{num} {R[num]}')
        c = meta.get(n, {}); wk = c.get('wk', '')
        label = clean(f"{ABBR} {'Mascot' if num == 'MASCOT' else '#' + num if num else 'unknown'} - {wk} - {n}")
        shutil.copy(f'{out}/png/{n}.png', f'{lib}/{f}/Cutouts/{label}.png')
        kind = ('Photos' if f == '_Unidentified' else None) if f.startswith('_') else ('Portraits' if c.get('folder') == '02 Pregame' and c.get('cat') in ('portrait', 'warmup', 'sideline') and c['box'][3] - c['box'][1] > 0.6 else 'Action')
        if kind: plan.append(dict(src=f'{n}.jpg', dst=f'{f}/{kind}/{label}.jpg'))
        rows.append(dict(player=f, number=num or '', grade=g['grade'], cutout=f'{f}/Cutouts/{label}.png', source_raw=n + '.CR3', game=wk,
                         size=f"{g['size'][0]}x{g['size'][1]}", full_body='yes' if g['grade'] == 'A' else 'no (cut at frame edge)', mask_agreement=g['iou']))
    with open(ip, 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]) if rows else INDEX_FIELDS); w.writeheader(); w.writerows(sorted(rows, key=lambda r: (r['player'], r['game'])))
    json.dump(plan, open(f'{lib}/../lib_plan.json', 'w'))
    sheet([(Image.open(f"{lib}/{r['cutout']}"), r['player'][:22] + ' ' + r['grade']) for r in rows], f'{lib}/_Overview.jpg', C=10, TW=190, TH=320, bg=BG)
    print(len(rows), 'cutouts in the library;', len({r['player'] for r in rows if not r['player'].startswith('_')}), 'players')

if __name__ == '__main__':
    c = sys.argv[1]
    if c == 'candidates': candidates(sys.argv[2], sys.argv[3])
    elif c == 'cut': cut(sys.argv[2], sys.argv[3], sys.argv[4])
    elif c == 'library': library(sys.argv[2], sys.argv[3], sys.argv[4])
