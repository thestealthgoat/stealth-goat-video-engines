#!/usr/bin/env python3
"""routemap.py - O6 map route draw-on: a GPX route drawn on a map, the camera following the line.

routemap.py <route.gpx> --out DIR [--name N] [--dur 7] [--labels "Start|Finish"] [--fps 29.97] [--size 1920x1080]
            [--frames t1,t2] [--profile P]
routemap.py --gpx-from-videos "<folder or glob>" --gpx-out route.gpx          # a route from phone clips' GPS tags

The map (default --map naturalearth) is drawn offline from Natural Earth (public domain: coast, rivers, roads,
towns); --map osm draws roads from OpenStreetMap data via the Overpass API (cached, with the on-screen credit
"© OpenStreetMap contributors" its ODbL licence requires). Either is toned to the profile so the route reads. The route draws from start to finish on a spring (smooth, scaled to --dur)
with a glowing head; the camera frames the whole route, pushes toward the head while it travels and settles back
on the whole route at the end; the distance so far counts up (haversine, km and mi from the profile's units).
--gpx-from-videos reads each clip's QuickTime location tag (ISO 6709) and creation date and writes the points in time
order as a GPX track: a real route from the footage itself when nobody recorded a GPX file.
Outputs <name>_route.mp4.
"""
import argparse, glob, io, json, math, os, re, subprocess, sys, time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from xml.sax.saxutils import escape as xml_escape

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import vprofile as prof  # noqa: E402
from spring import clamp01, progress  # noqa: E402

TILE = 256
CACHE = os.path.join(REPO, "_cache", "osm")
UA = "VideoEngine-routemap/1.0 (offline video renders; tiles cached)"


# ---------------------------------------------------------------- GPX
def read_gpx(path):
    """-> (points, waypoints); a point is (lat, lon, name, gap) where gap is True when a new track segment / route
    starts at it (the straight jump to it is not part of the distance travelled). One kind only: the recorded track
    if there is one, else the planned route, else the waypoints (a GPX with both rte and trk must not draw twice)."""
    root = ET.parse(path).getroot()
    got = {"trkpt": [], "rtept": [], "wpt": []}
    new = {"trkpt": False, "rtept": False}
    for el in root.iter():                               # document order: a trk / trkseg / rte comes before its points
        tag = el.tag.split("}")[-1]
        if tag in ("trk", "trkseg"):
            new["trkpt"] = True
        elif tag == "rte":
            new["rtept"] = True
        elif tag in got:
            lat, lon = float(el.get("lat")), float(el.get("lon"))
            nm = next((c.text for c in el if c.tag.split("}")[-1] == "name"), None)
            L = got[tag]
            L.append((lat, lon, nm, bool(L) and new.get(tag, False)))
            if tag in new: new[tag] = False
    pts = got["trkpt"] or got["rtept"] or got["wpt"]
    if len(pts) < 2:
        raise SystemExit(f"routemap: {path} has fewer than 2 points")
    return pts, got["wpt"]


def _when_utc(s):
    """a clip's creation date -> aware UTC datetime. QuickTime's creationdate is local time with an offset
    ('2026-03-14T10:22:31-0600'); creation_time is UTC ('2026-03-14T16:22:31.000000Z')."""
    s = s.strip().replace("Z", "+00:00").replace("z", "+00:00")
    s = re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2", s)                                   # -0600 -> -06:00
    s = re.sub(r"\.(\d+)", lambda m: "." + (m.group(1) + "000000")[:6], s)           # fraction -> 6 digits
    d = datetime.fromisoformat(s)
    return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def gpx_from_videos(pattern, out):
    files = sorted(glob.glob(os.path.join(pattern, "**", "*.*"), recursive=True) if os.path.isdir(pattern) else glob.glob(pattern))
    rows = []
    for p in files:
        if os.path.splitext(p)[1].lower() not in (".mov", ".mp4", ".m4v"):
            continue
        o = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format_tags", "-of", "json", p], capture_output=True, text=True).stdout
        tg = json.loads(o or "{}").get("format", {}).get("tags", {})
        loc = tg.get("com.apple.quicktime.location.ISO6709") or tg.get("location")
        when = tg.get("com.apple.quicktime.creationdate") or tg.get("creation_time")
        m = re.match(r"([+-]\d+\.\d+)([+-]\d+\.\d+)", loc or "")
        if m and when:
            try:
                w = _when_utc(when)
            except ValueError:
                print(f"routemap: skipping {os.path.basename(p)}: unreadable creation date {when!r}"); continue
            rows.append((w, float(m.group(1)), float(m.group(2)), os.path.basename(p)))
    rows.sort()                                           # on the UTC instant, so mixed phones and time zones order right
    if len(rows) < 2:
        raise SystemExit("routemap: fewer than 2 clips with a location tag")
    trk = "\n".join(f'   <trkpt lat="{la:.6f}" lon="{lo:.6f}"><time>{w.strftime("%Y-%m-%dT%H:%M:%SZ")}</time>'
                    f'<name>{xml_escape(n)}</name></trkpt>' for w, la, lo, n in rows)
    open(out, "w", encoding="utf-8").write(f'<?xml version="1.0" encoding="UTF-8"?>\n<gpx version="1.1" creator="routemap.py" xmlns="http://www.topografix.com/GPX/1/1">\n'
                         f' <trk><name>from clip locations</name><trkseg>\n{trk}\n </trkseg></trk>\n</gpx>\n')
    print(f"wrote {out}: {len(rows)} points from {len(files)} files")


# ---------------------------------------------------------------- maths
def merc(lat, lon, z):
    """world pixel x, y at zoom z (Web Mercator)"""
    n = TILE * 2 ** z
    x = (lon + 180) / 360 * n
    y = (1 - math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat))) / math.pi) / 2 * n
    return x, y


def hav(a, b):
    R = 6371.0088
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


NE = os.path.join(REPO, "_cache", "naturalearth")
NE_URL = "https://naciscdn.org/naturalearth/10m/"
NE_LAYERS = {"roads": "cultural/ne_10m_roads", "rivers": "physical/ne_10m_rivers_lake_centerlines",
             "places": "cultural/ne_10m_populated_places_simple", "border": "cultural/ne_10m_admin_0_boundary_lines_land",
             "states": "cultural/ne_10m_admin_1_states_provinces_lines", "lakes": "physical/ne_10m_lakes", "coast": "physical/ne_10m_coastline"}


def ne_layer(key, bbox):
    """Natural Earth 1:10m shapes (public domain) that touch bbox (s, w, n, e): [(kind, [[(lat, lon), ...]], attrs)]"""
    import shapefile, zipfile
    os.makedirs(NE, exist_ok=True)
    name = os.path.basename(NE_LAYERS[key]); zp = os.path.join(NE, name + ".zip")
    if not os.path.isfile(zp):
        r = subprocess.run(["curl", "-fsSL", "--max-time", "200", "-A", UA, "-o", zp + ".part", NE_URL + NE_LAYERS[key] + ".zip"], capture_output=True, text=True)
        if r.returncode: raise SystemExit(f"routemap: could not download Natural Earth {name}: {r.stderr.strip()[:200]}")
        os.replace(zp + ".part", zp)
    z = zipfile.ZipFile(zp)
    # Natural Earth DBFs are UTF-8 (each zip's .cpg says so): latin-1 would garble every accented place name
    rd = shapefile.Reader(shp=io.BytesIO(z.read(name + ".shp")), dbf=io.BytesIO(z.read(name + ".dbf")),
                          encoding="utf-8", encodingErrors="replace")
    S, Wl, N, E = bbox; out = []
    # a bbox past +-180 (a route across the antimeridian, longitudes unwrapped): also take the shapes one world over,
    # shifted by k degrees so they line up with the unwrapped route
    shifts = [k for k in range(-720, 721, 360) if Wl - k <= 180 and E - k >= -180]
    fields = [f[0] for f in rd.fields[1:]]
    for sr in rd.iterShapeRecords():
        sh = sr.shape
        if sh.shapeType == shapefile.NULL: continue
        for k in shifts:
            w_, e_ = Wl - k, E - k
            if sh.shapeType in (shapefile.POINT, shapefile.POINTZ):
                lon, lat = sh.points[0]
                if not (S <= lat <= N and w_ <= lon <= e_): continue
                out.append(("point", [[(lat, lon + k)]], dict(zip(fields, sr.record)))); continue
            b = sh.bbox
            if b[2] < w_ or b[0] > e_ or b[3] < S or b[1] > N: continue
            parts = list(sh.parts) + [len(sh.points)]
            rings = [[(y, x + k) for x, y in sh.points[i:j]] for i, j in zip(parts, parts[1:])]
            kind = "poly" if sh.shapeType in (shapefile.POLYGON, shapefile.POLYGONZ) else "line"
            out.append((kind, rings, dict(zip(fields, sr.record))))
    return out


def overpass_complete(body):
    """the parsed Overpass reply, or (None, why) when it is not a complete result. Overpass answers a query that hit its
    own timeout or memory limit with HTTP 200 and a JSON 'remark' ("runtime error: Query timed out ..."), holding no
    or only some elements: that must never be cached as the map."""
    try:
        d = json.loads(body)
    except ValueError:
        return None, "the reply was not complete JSON"
    if not isinstance(d, dict) or not isinstance(d.get("elements"), list):
        return None, "the reply had no element list"
    rem = str(d.get("remark") or "")
    if re.search(r"error|timed out|out of memory", rem, re.I):
        return None, rem.strip()[:160]
    return d, ""


def _overpass(S, Wl, N, E):
    f = os.path.join(REPO, "_cache", "osm", f"{S:.3f}_{Wl:.3f}_{N:.3f}_{E:.3f}.json")
    if os.path.isfile(f):
        d, why = overpass_complete(open(f, encoding="utf-8").read())
        if d is not None:
            return d
        print(f"routemap: ignoring an incomplete cached Overpass result ({why})")
    q = (f'[out:json][timeout:90];(way["highway"~"^(motorway|trunk|primary|secondary)$"]({S},{Wl},{N},{E});'
         f'way["waterway"="river"]({S},{Wl},{N},{E});way["natural"="water"]({S},{Wl},{N},{E});'
         f'node["place"~"^(city|town)$"]({S},{Wl},{N},{E}););out geom;')
    why = "busy or unreachable"
    for wait in (0, 15, 45, 120):
        time.sleep(wait)
        r = subprocess.run(["curl", "-fsS", "--max-time", "120", "-A", UA, "--data-urlencode", "data=" + q,
                            "https://overpass-api.de/api/interpreter"], capture_output=True, text=True)
        if r.returncode != 0:
            why = "busy or unreachable"; continue
        d, why_ = overpass_complete(r.stdout)
        if d is None:
            why = f"returned an incomplete result: {why_}"; continue
        with open(f + ".part", "w", encoding="utf-8") as fh:
            fh.write(r.stdout)
        os.replace(f + ".part", f)                        # only a complete reply ever becomes the cache file
        return d
    raise SystemExit(f"routemap: the Overpass API (OpenStreetMap data) {why}; try again later, a smaller area, or --map naturalearth")


def osm_layers(bbox):
    """OpenStreetMap ways from the Overpass API (cached; retried with backoff when the public servers are busy).
    A bbox past +-180 (unwrapped longitudes) is fetched as one query per world copy and shifted to line up."""
    S, Wl, N, E = bbox; os.makedirs(os.path.join(REPO, "_cache", "osm"), exist_ok=True)
    out = []
    for k in [k for k in range(-720, 721, 360) if Wl - k <= 180 and E - k >= -180]:
        d = _overpass(S, max(-180.0, Wl - k), N, min(180.0, E - k))
        for el in d.get("elements", []):
            tg = el.get("tags", {})
            if el["type"] == "node":
                out.append(("place", [[(el["lat"], el["lon"] + k)]], {"NAME": tg.get("name", ""), "POP_MAX": int(re.sub(r"\D", "", tg.get("population", "0")) or 0)}))
            elif "geometry" in el:
                ring = [(g["lat"], g["lon"] + k) for g in el["geometry"]]
                kind = "road" if "highway" in tg else ("lake" if tg.get("natural") == "water" else "river")
                out.append((kind, [ring], {"type": tg.get("highway", "")}))
    return out


def draw_base(bbox, z, ox, oy, size, P, source, s):
    """the map as a picture in world pixels (zoom z, origin ox, oy), drawn from vector data in the profile's colours"""
    from PIL import Image, ImageDraw
    Wb, Hb = size
    ground = tuple(int(v * 0.42) for v in P.rgb("primary"))
    txt = P.rgb("text") if "text" in P.get("brand.colors") else (235, 235, 235)
    mixc = lambda a, b, k: tuple(int(x + (y - x) * k) for x, y in zip(a, b))
    water = mixc(ground, (90, 140, 190), 0.35)
    im = Image.new("RGB", (Wb, Hb), ground); d = ImageDraw.Draw(im, "RGBA")
    to = lambda lat, lon: (merc(lat, lon, z)[0] - ox, merc(lat, lon, z)[1] - oy)
    places = []
    if source == "osm":
        L = osm_layers(bbox)
        for kind, rings, at in L:
            pts = [to(*p) for p in rings[0]]
            if kind == "lake" and len(pts) > 2: d.polygon(pts, fill=water + (255,))
        for kind, rings, at in L:
            pts = [to(*p) for p in rings[0]]
            if kind == "river" and len(pts) > 1: d.line(pts, fill=water + (255,), width=max(1, int(3 * s)))
            if kind == "road" and len(pts) > 1:
                major = at["type"] in ("motorway", "trunk")
                d.line(pts, fill=txt + (150 if major else 90,), width=max(1, int((4 if major else 2) * s)))
            if kind == "place": places.append((at["NAME"], at["POP_MAX"], pts[0]))
    else:
        # lakes: every ring after a lake's outer one is a hole (an island). Fill each lake even-odd on a mask, so islands
        # stay land (Isle Royale, Manitoulin), and a separate lake that sits on an island is never painted over.
        lake_mask = Image.new("1", (Wb, Hb), 0)
        for kind, rings, at in ne_layer("lakes", bbox):
            rs = [[to(*p) for p in r] for r in rings if len(r) > 2]
            if not rs: continue
            x0 = max(0, int(math.floor(min(x for r in rs for x, _ in r)))); x1 = min(Wb, int(math.ceil(max(x for r in rs for x, _ in r))) + 1)
            y0 = max(0, int(math.floor(min(y for r in rs for _, y in r)))); y1 = min(Hb, int(math.ceil(max(y for r in rs for _, y in r))) + 1)
            if x1 <= x0 or y1 <= y0: continue
            m = Image.new("1", (x1 - x0, y1 - y0), 0)
            for r in rs:
                rm = Image.new("1", m.size, 0)
                ImageDraw.Draw(rm).polygon([(x - x0, y - y0) for x, y in r], fill=1)
                m = ImageChops.logical_xor(m, rm)
            lake_mask.paste(ImageChops.logical_or(lake_mask.crop((x0, y0, x1, y1)), m), (x0, y0))
        im.paste(water, (0, 0, Wb, Hb), lake_mask)
        for key, col, w in (("coast", water, 3), ("rivers", water, 3), ("states", txt + (60,), 1)):
            for kind, rings, at in ne_layer(key, bbox):
                for r in rings:
                    if len(r) > 1: d.line([to(*p) for p in r], fill=col if len(col) == 4 else col + (255,), width=max(1, int(w * s)))
        for kind, rings, at in ne_layer("roads", bbox):
            major = "Major" in str(at.get("type", "")) or int(at.get("scalerank", 9) or 9) <= 5
            for r in rings:
                if len(r) > 1: d.line([to(*p) for p in r], fill=txt + (150 if major else 85,), width=max(1, int((4 if major else 2) * s)))
        for kind, rings, at in ne_layer("border", bbox):          # the national border, dashed
            for r in rings:
                pts = [to(*p) for p in r]
                for a_, b_ in zip(pts, pts[1:]):
                    L_ = math.hypot(b_[0] - a_[0], b_[1] - a_[1]); n_ = max(1, int(L_ / (14 * s)))
                    for k in range(0, n_, 2):
                        d.line([(a_[0] + (b_[0] - a_[0]) * k / n_, a_[1] + (b_[1] - a_[1]) * k / n_),
                                (a_[0] + (b_[0] - a_[0]) * min(1, (k + 1) / n_), a_[1] + (b_[1] - a_[1]) * min(1, (k + 1) / n_))],
                               fill=txt + (170,), width=max(1, int(3 * s)))
        for kind, rings, at in ne_layer("places", bbox):
            places.append((at.get("name") or at.get("NAME") or "", int(at.get("pop_max") or at.get("POP_MAX") or 0), to(*rings[0][0])))
    return im, sorted(places, key=lambda p: -p[1])


def main(argv=None):
    ap = argparse.ArgumentParser(description="O6 map route draw-on (OpenStreetMap)")
    ap.add_argument("gpx", nargs="?"); ap.add_argument("--out"); ap.add_argument("--name", default="route")
    ap.add_argument("--dur", type=float, default=7.0); ap.add_argument("--labels", help="'Start|Finish' names for the ends")
    ap.add_argument("--fps", type=float, default=29.97); ap.add_argument("--size", default="1920x1080"); ap.add_argument("--frames")
    ap.add_argument("--gpx-from-videos"); ap.add_argument("--gpx-out")
    ap.add_argument("--map", choices=["naturalearth", "osm"], default="naturalearth",
                    help="naturalearth: public-domain 1:10m layers, offline after one download (regional routes); osm: OpenStreetMap "
                         "roads / water / towns from the Overpass API (city-scale routes; credited on screen)")
    prof.add_arg(ap)
    a = ap.parse_args(argv)
    if a.gpx_from_videos:
        gpx_from_videos(a.gpx_from_videos, a.gpx_out or "route.gpx"); return 0
    if not (a.gpx and a.out):
        ap.error("give a GPX file and --out")
    P = prof.load(a.profile); W, H = (int(v) for v in a.size.split("x")); s = min(W, H) / 1080
    pts, wpts = read_gpx(a.gpx)
    # unwrap longitudes so no step jumps more than 180 deg (a route across the antimeridian stays one short line;
    # merc() is linear in lon and hav() is unchanged by a 360 deg shift), then centre the route on [-180, 180]
    un = [pts[0]]
    for la, lo, nm, gap in pts[1:]:
        prev = un[-1][1]
        while lo - prev > 180: lo -= 360
        while lo - prev < -180: lo += 360
        un.append((la, lo, nm, gap))
    kw = 360 * round((min(p[1] for p in un) + max(p[1] for p in un)) / 2 / 360)
    pts = [(la, lo - kw, nm, gap) for la, lo, nm, gap in un]
    # drop repeats (a phone parked in one place gives dozens of the same point): a repeat is a point closer to the
    # last kept one than 0.2% of the route's size (well under 2 px on screen; 3 m at the least), so a 1 Hz track keeps
    # its corners, while clips shot around one base camp do not scribble. The real last point is always the finish.
    la_, lo_ = [p[0] for p in pts], [p[1] for p in pts]
    rep = max(0.003, 0.002 * hav((min(la_), min(lo_)), (max(la_), max(lo_))))
    clean, carry = [pts[0]], False
    for p in pts[1:]:
        if hav(clean[-1], p) > rep:
            clean.append(p[:3] + (p[3] or carry,)); carry = False
        else:
            carry = carry or p[3]                         # a dropped point that opened a segment: the next kept one does
    if clean[-1] is not pts[-1] and hav(clean[-1], pts[-1]) > 0:
        if len(clean) > 1: clean[-1] = pts[-1][:3] + (clean[-1][3] or carry,)
        else: clean.append(pts[-1])
    pts = clean if len(clean) >= 2 else pts
    # the head travels every leg, but the jump between two track segments (or routes) is not distance travelled
    seg = [hav(p, q) for p, q in zip(pts, pts[1:])]; cum = np.concatenate([[0], np.cumsum(seg)]); total = float(cum[-1])
    cum_rec = np.concatenate([[0], np.cumsum([0.0 if q[3] else s_ for s_, q in zip(seg, pts[1:])])]); total_rec = float(cum_rec[-1])
    # zoom: the largest z where the route's box fits 62% of the frame
    lats, lons = [p[0] for p in pts], [p[1] for p in pts]
    xa0, ya0 = merc(max(lats), min(lons), 0); xb0, yb0 = merc(min(lats), max(lons), 0)
    z = math.log2(min(0.62 * W / max(1e-9, xb0 - xa0), 0.62 * H / max(1e-9, yb0 - ya0)))   # a vector map: any zoom
    z = min(z, 16.0)
    xa, ya = merc(max(lats), min(lons), z); xb, yb = merc(min(lats), max(lons), z)
    cxw, cyw = (xa + xb) / 2, (ya + yb) / 2
    PUSH = 1.35                                         # the camera pushes in up to 35% while the head travels
    m0x, m0y, m1x, m1y = cxw - W * 0.56, cyw - H * 0.56, cxw + W * 0.56, cyw + H * 0.56   # the full view plus a little drift room
    ox, oy = int(m0x), int(m0y)
    lat_n = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * m0y / (TILE * 2 ** z)))))
    lat_s = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * m1y / (TILE * 2 ** z)))))
    lon_w = m0x / (TILE * 2 ** z) * 360 - 180; lon_e = m1x / (TILE * 2 ** z) * 360 - 180
    base, places = draw_base((lat_s, lon_w, lat_n, lon_e), z, ox, oy, (int(m1x - m0x), int(m1y - m0y)), P, a.map, s)
    dark = tuple(int(v * 0.42) for v in P.rgb("primary"))
    XY = [((merc(p[0], p[1], z)[0] - ox), (merc(p[0], p[1], z)[1] - oy)) for p in pts]
    acc = P.rgb("accent"); txt = P.rgb("text") if "text" in P.get("brand.colors") else (255, 255, 255)
    fonts = P.get("brand.fonts")
    fh = ImageFont.truetype(P.font("head"), int(64 * s)); fb = ImageFont.truetype(P.font("body_semibold" if "body_semibold" in fonts else "body"), int(26 * s))
    fc = ImageFont.truetype(P.font("body"), int(18 * s))
    metric = str(P.get("units", "metric")).lower() != "imperial"
    labels = (a.labels or "|").split("|") + [""]
    safe = int(P.get("layout.safe_px", 90) * s)
    T0, TD = 0.35, a.dur * 0.62                          # the line draws from T0 over about TD seconds
    def head(d_km):
        i = int(np.clip(np.searchsorted(cum, d_km) - 1, 0, len(XY) - 2)); f = 0 if seg[i] == 0 else (d_km - cum[i]) / seg[i]
        return XY[i][0] + (XY[i + 1][0] - XY[i][0]) * f, XY[i][1] + (XY[i + 1][1] - XY[i][1]) * f, i
    # The draw spring only approaches 1, so on its own the head stops short of the finish and the counter short of the
    # total. A second closed-form spring, starting from rest as the finish marker lands, takes up the remainder by the
    # end hold (velocity stays continuous); dividing by the value on the last frame makes that frame exactly 1.
    QS = T0 + TD * 0.85; QW = 7.0 / max(0.3, a.dur - 1.0 - QS)
    def draw_p(t):
        r = progress(t, start=T0, zeta=1.0, omega=4.6 / TD, v0=0.6)
        return r + (1 - r) * progress(t, start=QS, zeta=1.0, omega=QW)
    p_end = draw_p((int(round(a.dur * a.fps)) - 1) / a.fps) or 1.0  # (0 only for a --dur too short to draw at all)
    # town labels: chosen once in base pixels (the k=1 full view). The camera only pushes in (k >= 1), which spreads
    # labels apart, so a set that does not collide at k=1 never collides later: no label pops in or out mid-move
    sel, used = [], []
    for nm, pop, (px_, py_) in places[:12]:
        if nm and not any(abs(px_ - u) < 170 * s and abs(py_ - v) < 40 * s for u, v in used):
            used.append((px_, py_)); sel.append((nm.upper(), px_, py_))
    def frame(t):
        p = clamp01(draw_p(t) / p_end)
        dk = p * total; hx, hy, hi = head(dk)
        dk_rec = float(np.interp(dk, cum, cum_rec))       # the counter leaves out jumps between track segments
        # camera: centre eases from the route's middle toward the head while drawing, back at the end; zoom pushes in
        cx0, cy0 = cxw - ox, cyw - oy
        go = clamp01(progress(t, start=T0, preset="smooth")) * (1 - clamp01(progress(t, start=a.dur - 1.6, preset="smooth")))
        drop = 1 - clamp01(progress(t, start=0.0, preset="snappy"))       # the opening: the camera drops in from 1.6x
        k = 1 + (PUSH - 1) * go + 0.6 * drop
        cx, cy = cx0 + (hx - cx0) * 0.55 * go, cy0 + (hy - cy0) * 0.55 * go
        cw, ch = W / k, H / k
        # sample the base with the same float transform as the overlay (an integer crop makes the map step 1 px at a time
        # under the smoothly moving line)
        x0v, y0v = cx - cw / 2, cy - ch / 2
        view = base.resize((W, H), Image.BILINEAR, box=(x0v, y0v, x0v + cw, y0v + ch))
        to = lambda x, y: ((x - x0v) * k, (y - y0v) * k)
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(lay)
        line = [to(*XY[j]) for j in range(hi + 1)] + [to(hx, hy)]
        if len(line) >= 2:
            glow = Image.new("RGBA", (W, H), (0, 0, 0, 0)); ImageDraw.Draw(glow).line(line, fill=acc + (150,), width=int(16 * s), joint="curve")
            lay.alpha_composite(glow.filter(ImageFilter.GaussianBlur(8 * s)))
            d.line(line, fill=acc + (255,), width=int(6 * s), joint="curve")
        for (x, y), lab, at in ((to(*XY[0]), labels[0], T0 - 0.2), (to(*XY[-1]), labels[1], T0 + TD * 0.85)):
            if t < at: continue
            pa = clamp01(progress(t, start=at, preset="smooth")); r = 12 * s * (1.3 - 0.3 * progress(t, start=at, preset="snappy"))
            d.ellipse((x - r, y - r, x + r, y + r), fill=txt + (int(255 * pa),), outline=acc + (int(255 * pa),), width=int(4 * s))
            if lab: d.text((x + 20 * s, y - 18 * s), lab, font=fb, fill=txt + (int(255 * pa),), anchor="ls", stroke_width=int(3 * s), stroke_fill=dark)
        if p > 0.001:
            hxp, hyp = to(hx, hy); R = 16 * s
            hg = Image.new("RGBA", (W, H), (0, 0, 0, 0)); ImageDraw.Draw(hg).ellipse((hxp - 3 * R, hyp - 3 * R, hxp + 3 * R, hyp + 3 * R), fill=acc + (110,))
            lay.alpha_composite(hg.filter(ImageFilter.GaussianBlur(10 * s)))
            d.ellipse((hxp - R * 0.6, hyp - R * 0.6, hxp + R * 0.6, hyp + R * 0.6), fill=(255, 255, 255, 255))
        for nm, px_, py_ in sel:                                    # the biggest towns, quiet labels, never stacked
            X_, Y_ = to(px_, py_)
            if X_ + 10 * s + fc.getlength(nm) < 0 or X_ - 4 * s > W or Y_ + 4 * s < 0 or Y_ - 30 * s > H:
                continue                                            # culled on the whole label: it slides off the edge
            d.ellipse((X_ - 4 * s, Y_ - 4 * s, X_ + 4 * s, Y_ + 4 * s), fill=txt + (200,))
            d.text((X_ + 10 * s, Y_ - 6 * s), nm, font=fc, fill=txt + (190,), anchor="ls")
        # distance counter (top left) and the map credit (bottom right, always)
        val = dk_rec if metric else dk_rec * 0.621371; unit = "km" if metric else "mi"
        ra = clamp01(progress(t, start=0.1, preset="smooth"))
        d.text((safe, safe + 60 * s), f"{val:,.1f} {unit}", font=fh, fill=txt + (int(255 * ra),), anchor="ls", stroke_width=int(3 * s), stroke_fill=dark)
        d.text((safe, safe + 96 * s), "DISTANCE", font=fb, fill=acc + (int(255 * ra),), anchor="ls")
        cr = "© OpenStreetMap contributors" if a.map == "osm" else "Map data: Natural Earth"; tw = fc.getlength(cr)
        d.rectangle((W - safe - tw - 16 * s, H - safe - 30 * s, W - safe + 4 * s, H - safe + 2 * s), fill=(0, 0, 0, 140))
        d.text((W - safe - 6 * s, H - safe - 6 * s), cr, font=fc, fill=(255, 255, 255, 230), anchor="rs")
        out = view.convert("RGBA"); out.alpha_composite(lay)
        fl = 0.55 * (1 - clamp01(progress(t, start=0.0, zeta=1.0, omega=12.0)))   # and develops from a light flash (the hit)
        if fl > 0.004: out = Image.blend(out, Image.new("RGBA", (W, H), txt + (255,)), fl)
        return out.convert("RGB")
    os.makedirs(a.out, exist_ok=True); bp = os.path.join(a.out, f"{a.name}_route")
    if a.frames:
        for t in (float(v) for v in a.frames.split(",")):
            frame(t).save(f"{bp}_t{t:.2f}.jpg", quality=92); print("still", f"{bp}_t{t:.2f}.jpg")
        print(f"route {total_rec:.1f} km, {len(pts)} points, zoom {z:.2f}")
        return 0
    fr = "30000/1001" if abs(a.fps - 30000 / 1001) < 0.01 else f"{a.fps:g}"
    enc = subprocess.Popen(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-framerate", fr,
                            "-i", "pipe:0", "-c:v", "libx264", "-crf", "17", "-preset", "medium", "-pix_fmt", "yuv420p", "-threads", "4",
                            "-movflags", "+faststart", bp + ".mp4"], stdin=subprocess.PIPE)
    for i in range(int(round(a.dur * a.fps))):
        enc.stdin.write(frame(i / a.fps).tobytes())
    enc.stdin.close()
    if enc.wait(): raise SystemExit("routemap: encode failed")
    print(f"route {total_rec:.1f} km, {len(pts)} points, zoom {z:.2f} -> {bp}.mp4 (qa: --kind motion --cuts none --holds end:1.0)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
