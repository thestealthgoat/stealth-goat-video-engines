#!/usr/bin/env python3
"""Logo vectorizer: any raster logo (low-res PNG/JPG/screenshot) -> clean layered SVG + transparent hi-res PNG.

vectorize.py <input.png|jpg> <out_dir> <name> [--colors N] [--palette "#112233,#E04050,#FFFFFF"]
             [--bg auto|none|#hex] [--png-width 4000] [--detail 1.0]

Steps: key out a solid background (if any) -> AI-upscale small images x4 (EDSR) -> find the logo's real flat colours
(k-means, optionally snapped to a brand palette) -> clean each colour layer -> trace each layer to smooth curves
(vtracer, binary spline) -> stack the layers bottom-to-top with no seams -> render a transparent PNG and score the
result against the original.

Outputs: <name>.svg, <name>_Transparent_<W>px.png, <name>_vector_check.png (original | vector | difference), and
prints a fidelity score (silhouette IoU and mean color error). Score < 0.97 IoU means look closely before using it.
"""
import argparse, io, os, re, subprocess, sys, tempfile
import numpy as np
import cv2
from PIL import Image
# macOS + Homebrew: cairosvg's libcairo sits in /opt/homebrew/lib, which ctypes' find_library does not search by
# default; add it for the import only (nothing else, and no child process, sees the change)
_HB = sys.platform == 'darwin' and 'DYLD_FALLBACK_LIBRARY_PATH' not in os.environ and os.path.isdir('/opt/homebrew/lib')
if _HB: os.environ['DYLD_FALLBACK_LIBRARY_PATH'] = os.pathsep.join([os.path.expanduser('~/lib'), '/usr/local/lib', '/lib', '/usr/lib', '/opt/homebrew/lib'])
import vtracer, cairosvg
if _HB: del os.environ['DYLD_FALLBACK_LIBRARY_PATH']
from sklearn.cluster import KMeans

HERE = os.path.dirname(os.path.abspath(__file__))


def hex2rgb(h):
    h = h.strip().lstrip('#'); return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def load_rgba(path, bg):
    im = Image.open(path)
    im = im.convert('RGBA') if im.mode in ('RGBA', 'LA', 'P') else im.convert('RGB').convert('RGBA')
    a = np.array(im)
    if bg == 'none':
        return a
    has_alpha = (a[..., 3] < 250).mean() > 0.01
    if has_alpha and bg == 'auto':
        return a
    rgb = a[..., :3].astype(int)
    if bg == 'auto':
        border = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]])
        ref = np.median(border, axis=0)
        if np.abs(border - ref).sum(1).mean() > 40:          # busy border: no solid background to remove
            return a
    else:
        ref = np.array(hex2rgb(bg))
    d = np.sqrt(((rgb - ref) ** 2).sum(-1))
    alpha = np.clip((d - 18) * (255 / 30), 0, 255).astype(np.uint8)
    # only remove background connected to the edge (keeps same-coloured shapes inside the logo)
    mask = (alpha < 128).astype(np.uint8)
    n, lab = cv2.connectedComponents(mask, connectivity=4)
    edge = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))) - {0}
    keep_bg = np.isin(lab, list(edge))
    alpha = np.where(keep_bg, alpha, 255).astype(np.uint8)
    a[..., 3] = alpha
    return a


def upscale(a, target=2400):
    h, w = a.shape[:2]
    long = max(h, w)
    rgb, alpha = a[..., :3], a[..., 3]
    if long < 700:
        # small logo: AI super-resolution x4 (EDSR) in the helper venv; falls back to Lanczos if missing
        bgc = np.median(rgb[alpha > 200], axis=0) if (alpha > 200).any() else np.array([255, 255, 255])
        flat = (rgb * (alpha[..., None] / 255.0) + bgc * (1 - alpha[..., None] / 255.0)).astype(np.uint8)
        py = os.path.join(HERE, 'srenv', 'bin', 'python')
        rgb2 = None
        if os.path.exists(py):
            with tempfile.TemporaryDirectory() as td:
                i, o = os.path.join(td, 'i.png'), os.path.join(td, 'o.png')
                cv2.imwrite(i, cv2.cvtColor(flat, cv2.COLOR_RGB2BGR))
                if subprocess.run([py, os.path.join(HERE, 'sr.py'), i, o]).returncode == 0:
                    rgb2 = cv2.cvtColor(cv2.imread(o), cv2.COLOR_BGR2RGB)
        if rgb2 is None:
            rgb2 = cv2.resize(flat, (w * 4, h * 4), interpolation=cv2.INTER_LANCZOS4)
        al2 = cv2.resize(alpha, (rgb2.shape[1], rgb2.shape[0]), interpolation=cv2.INTER_CUBIC)
    else:
        rgb2, al2 = rgb, alpha
    s = target / max(rgb2.shape[:2])
    if abs(s - 1) > 0.05:
        size = (int(rgb2.shape[1] * s), int(rgb2.shape[0] * s))
        rgb2 = cv2.resize(rgb2, size, interpolation=cv2.INTER_LANCZOS4)
        al2 = cv2.resize(al2, size, interpolation=cv2.INTER_LANCZOS4)
    # edge-preserving smoothing: removes JPEG noise / gradients' banding before colour clustering
    rgb2 = cv2.bilateralFilter(rgb2, 9, 40, 9)
    return np.dstack([rgb2, al2])


def pick_colors(px, k, palette):
    sample = px[np.random.default_rng(0).choice(len(px), min(len(px), 150000), replace=False)].astype(float)
    if k is None:
        prev = None; best = 2
        for kk in range(2, 11):
            km = KMeans(kk, n_init=3, random_state=0).fit(sample)
            if prev is not None and (prev - km.inertia_) / prev < 0.25:
                break
            prev = km.inertia_; best = kk
        k = best
    km = KMeans(k, n_init=6, random_state=0).fit(sample)
    centers = km.cluster_centers_
    if palette:
        # brand palette entries are always candidates (keeps thin strokes in brand colours); auto colours far
        # from every palette entry are kept too (e.g. a grey the palette forgot)
        pal = np.array([hex2rgb(h) for h in palette], float)
        extra = [c for c in centers if np.sqrt(((pal - c) ** 2).sum(1)).min() >= 60]
        centers = np.vstack([pal] + ([np.array(extra)] if extra else []))
    # merge clusters that ended up identical after snapping
    uniq = []
    for c in centers:
        if not any(np.abs(c - u).sum() < 6 for u in uniq): uniq.append(c)
    return np.array(uniq)


def trace_mask(mask, detail):
    """mask: bool HxW -> list of (d, transform) path strings from vtracer"""
    img = np.where(mask, 0, 255).astype(np.uint8)
    with tempfile.TemporaryDirectory() as td:
        ip, op = os.path.join(td, 'm.png'), os.path.join(td, 'm.svg')
        Image.fromarray(img).save(ip)
        # positional on purpose: vtracer 0.6.15 under Python 3.14 segfaults on keyword arguments. Order: colormode,
        # hierarchical, mode, filter_speckle, color_precision, layer_difference, corner_threshold, length_threshold,
        # max_iterations, splice_threshold, path_precision (None = vtracer's default, same as leaving it out)
        vtracer.convert_image_to_svg_py(ip, op, 'binary', None, 'spline', max(2, int(10 / detail)), None, None, 60,
                                        4.0, None, 45, 2)
        svg = open(op).read()
    out = []
    for el in re.findall(r'<path\b[^>]*/>', svg):
        dm = re.search(r'\bd="([^"]+)"', el); tm = re.search(r'transform="([^"]*)"', el)
        if dm: out.append((dm.group(1), tm.group(1) if tm else ''))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('input'); ap.add_argument('out'); ap.add_argument('name')
    ap.add_argument('--colors', type=int); ap.add_argument('--palette')
    ap.add_argument('--bg', default='auto'); ap.add_argument('--png-width', type=int, default=4000)
    ap.add_argument('--detail', type=float, default=1.0, help='>1 keeps smaller details, <1 smooths more')
    ap.add_argument('--target', type=int, default=2400, help='working resolution (long side)')
    ap.add_argument('--flatten-shading', action='store_true',
                    help='for logos that are already "3D"/embossed/photographed: drop light neutral shadows as background '
                         'and group colors by hue/chroma instead of brightness')
    ap.add_argument('--bg-light', type=float, default=74, help='with --flatten-shading: L* above this AND near-neutral = background')
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    src = load_rgba(a.input, a.bg)
    work = upscale(src, a.target)
    H, W = work.shape[:2]
    if a.flatten_shading:
        labx = cv2.cvtColor(work[..., :3].astype(np.uint8), cv2.COLOR_RGB2LAB).astype(np.float32)
        Lx = labx[..., 0] * 100 / 255; Cx = np.hypot(labx[..., 1] - 128, labx[..., 2] - 128)
        bgm = (Lx > a.bg_light) & (Cx < 14)
        bgm = cv2.morphologyEx(bgm.astype(np.uint8), cv2.MORPH_OPEN, np.ones((5, 5), np.uint8)) > 0
        al = np.where(bgm, 0, work[..., 3]).astype(np.uint8)
        # keep only the main logo body (drop stray shadow blobs)
        n, cc, stats, _ = cv2.connectedComponentsWithStats((al > 128).astype(np.uint8), 8)
        if n > 1:
            keep = [i for i in range(1, n) if stats[i, cv2.CC_STAT_AREA] > stats[1:, cv2.CC_STAT_AREA].max() * 0.02]
            al = np.where(np.isin(cc, keep), al, 0).astype(np.uint8)
        work = np.dstack([work[..., :3], al])
        src = cv2.resize(work, (src.shape[1], src.shape[0]), interpolation=cv2.INTER_AREA)
    rgb, alpha = work[..., :3].astype(float), work[..., 3]
    solid = alpha > 128
    palette = [p for p in (a.palette or '').split(',') if p.strip()]
    lab_img = cv2.cvtColor(work[..., :3].astype(np.uint8), cv2.COLOR_RGB2LAB).astype(np.float32)
    gmag = sum(np.abs(cv2.Sobel(lab_img[..., c], cv2.CV_32F, 1, 0, ksize=3)) + np.abs(cv2.Sobel(lab_img[..., c], cv2.CV_32F, 0, 1, ksize=3)) for c in range(3))
    core = cv2.erode(solid.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
    flat = core & (gmag < np.percentile(gmag[core], 60))
    pick = flat if flat.sum() > 500 else solid
    if a.flatten_shading:
        # cluster on chroma with brightness down-weighted, then use each group's median colour
        feat = lab_img.copy(); feat[..., 0] *= 0.3
        c0 = pick_colors(feat[pick], a.colors, None)
        dd = ((feat[solid][:, None, :] - c0[None]) ** 2).sum(-1).argmin(1)
        centers = np.array([np.median(rgb[solid][dd == i], axis=0) for i in range(len(c0)) if (dd == i).any()])
        if palette:
            pal = np.array([hex2rgb(h) for h in palette], float)
            centers = np.array([pal[np.sqrt(((pal - c) ** 2).sum(1)).argmin()] for c in centers])
        rgb = rgb.copy()
        lab_all = cv2.cvtColor(work[..., :3].astype(np.uint8), cv2.COLOR_RGB2LAB).astype(np.float32); lab_all[..., 0] *= 0.3
        cf = cv2.cvtColor(np.uint8([centers]), cv2.COLOR_RGB2LAB)[0].astype(np.float32); cf[:, 0] *= 0.3
        lab_assign = ((lab_all[..., None, :] - cf[None, None]) ** 2).sum(-1).argmin(-1)
        rgb = centers[lab_assign]          # paint every pixel with its group colour so labelling ignores shading
    else:
        centers = pick_colors(rgb[pick], a.colors, palette)
    # label every solid pixel with its nearest colour, then clean with a mode filter
    d = ((rgb[..., None, :] - centers[None, None]) ** 2).sum(-1)
    lab = d.argmin(-1).astype(np.uint8) + 1
    lab[~solid] = 0
    k = max(3, int(round(W / 600)) | 1)
    lab = cv2.medianBlur(lab, k)
    solid = lab > 0
    tot = solid.sum()
    for _ in range(len(centers)):
        areas0 = np.array([(lab == i + 1).sum() for i in range(len(centers))])
        small = [i for i in range(len(centers)) if 0 < areas0[i] < tot * 0.012]
        if not small: break
        i = min(small, key=lambda j: areas0[j])
        big = [j for j in range(len(centers)) if j != i and areas0[j] >= tot * 0.012]
        if not big: break
        j = min(big, key=lambda j: ((centers[i] - centers[j]) ** 2).sum())
        lab[lab == i + 1] = j + 1
    # bottom-to-top order: outermost colour first (mean distance from the logo's edge), so outlines sit under fills;
    # each layer is filled under everything above it, so there are no seams
    areas = [(lab == i + 1).sum() for i in range(len(centers))]
    dist = cv2.distanceTransform(np.pad(solid.astype(np.uint8), 1), cv2.DIST_L2, 5)[1:-1, 1:-1]
    depth_in = [dist[lab == i + 1].mean() if areas[i] else 1e9 for i in range(len(centers))]
    order = sorted(range(len(centers)), key=lambda i: depth_in[i])
    parts = []
    for pos, i in enumerate(order):
        if areas[i] < solid.sum() * 0.0005: continue
        above = np.isin(lab, [j + 1 for j in order[pos:]])
        m = cv2.morphologyEx(above.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8)) > 0
        col = '#%02x%02x%02x' % tuple(int(round(v)) for v in centers[i])
        paths = trace_mask(m, a.detail)
        g = ''.join(f'<path d="{dd}"' + (f' transform="{tr}"' if tr else '') + '/>' for dd, tr in paths)
        parts.append(f'<g fill="{col}" fill-rule="evenodd">{g}</g>')
        print(f'layer {col}  area {areas[i] / solid.sum():.1%}  paths {len(paths)}')
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">'
           + ''.join(parts) + '</svg>')
    svg_path = os.path.join(a.out, f'{a.name}.svg'); open(svg_path, 'w').write(svg)
    pw = a.png_width; ph = int(round(H * pw / W))
    png = cairosvg.svg2png(bytestring=svg.encode(), output_width=pw, output_height=ph)
    open(os.path.join(a.out, f'{a.name}_Transparent_{pw}px.png'), 'wb').write(png)
    # fidelity check against the original at the working size
    vec = np.array(Image.open(io.BytesIO(cairosvg.svg2png(bytestring=svg.encode(), output_width=W, output_height=H))).convert('RGBA'))
    ref = np.array(Image.fromarray(src).resize((W, H), Image.LANCZOS))
    a1, a2 = ref[..., 3] > 128, vec[..., 3] > 128
    iou = (a1 & a2).sum() / max((a1 | a2).sum(), 1)
    both = a1 & a2
    cerr = np.abs(ref[..., :3].astype(int) - vec[..., :3].astype(int))[both].mean() if both.any() else 0
    print(f'FIDELITY silhouette IoU {iou:.3f}  mean color error {cerr:.1f}/255  colors {len(parts)}')
    # side-by-side check image on grey
    def on_grey(x):
        bgim = Image.new('RGBA', (W, H), (128, 128, 128, 255)); bgim.alpha_composite(Image.fromarray(x)); return bgim.convert('RGB')
    diff = np.zeros((H, W, 3), np.uint8); diff[a1 & ~a2] = (255, 0, 0); diff[a2 & ~a1] = (0, 160, 255)
    diff[both] = np.clip(np.abs(ref[..., :3].astype(int) - vec[..., :3].astype(int)) * 3, 0, 255)[both]
    sheet = Image.new('RGB', (W * 3, H)); sheet.paste(on_grey(ref), (0, 0)); sheet.paste(on_grey(vec), (W, 0)); sheet.paste(Image.fromarray(diff), (2 * W, 0))
    sheet.thumbnail((2400, 1200)); sheet.save(os.path.join(a.out, f'{a.name}_vector_check.png'))


if __name__ == '__main__':
    main()
