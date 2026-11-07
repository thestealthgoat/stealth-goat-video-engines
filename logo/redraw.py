#!/usr/bin/env python3
"""Redraw toolkit: rebuild a logo as clean vector shapes when tracing can't (mockups, photos, embossed/3D logos).

Use it from a small per-logo script:
    from redraw import Doc
    d = Doc(752, 752)                                   # same pixel space as the reference image
    d.poly([(63,292),(63,283),...], '#9C928D')          # straight-edged shapes from measured points
    d.line((243,160),(243,268), 5, '#4E2E25')           # a stroke as a filled quad (extrudes in 3D)
    d.rect(309,168,364,268, '#4E2E25'); d.hole_rect(...) # rectangles, and cut-outs from the last shape
    d.text('ACME',     'TitilliumWeb-Black.ttf', (62,305,714,434), '#8B5444')   # real font, as outlines, fitted to box
    d.save('out.svg'); d.check('reference.jpg', 'check.png')                      # overlay check vs the original
Measure points off a gridded enlargement of the reference (see SKILL), and find the font with fontmatch.py.
"""
import math, os, sys
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.transformPen import TransformPen


def _pts(p):
    return ' '.join(f'{x:.2f},{y:.2f}' for x, y in p)


class Doc:
    def __init__(self, w, h):
        self.w, self.h, self.items = w, h, []

    def poly(self, pts, fill, holes=()):
        d = 'M' + ' L'.join(f'{x:.2f} {y:.2f}' for x, y in pts) + ' Z'
        for hp in holes:
            d += ' M' + ' L'.join(f'{x:.2f} {y:.2f}' for x, y in hp) + ' Z'
        self.items.append(f'<path d="{d}" fill="{fill}" fill-rule="evenodd"/>')

    def rect(self, x0, y0, x1, y1, fill, holes=()):
        self.poly([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], fill, holes)

    @staticmethod
    def rect_pts(x0, y0, x1, y1):
        return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]

    def line(self, a, b, width, fill):
        (x0, y0), (x1, y1) = a, b
        L = math.hypot(x1 - x0, y1 - y0) or 1
        nx, ny = -(y1 - y0) / L * width / 2, (x1 - x0) / L * width / 2
        self.poly([(x0 + nx, y0 + ny), (x1 + nx, y1 + ny), (x1 - nx, y1 - ny), (x0 - nx, y0 - ny)], fill)

    def polyline(self, pts, width, fill):
        for a, b in zip(pts, pts[1:]):
            self.line(a, b, width, fill)

    def text(self, s, font_path, box, fill, tracking=0.0):
        """Set s in font_path, convert to outlines, and stretch the ink box to exactly fill box=(x0,y0,x1,y1)."""
        f = TTFont(font_path)
        gs = f.getGlyphSet(); cmap = f.getBestCmap(); upm = f['head'].unitsPerEm
        hmtx = f['hmtx']
        x = 0; glyphs = []
        for ch in s:
            g = cmap.get(ord(ch))
            if g is None: x += upm * 0.3; continue
            glyphs.append((g, x)); x += hmtx[g][0] + tracking * upm
        bp = BoundsPen(gs)
        for g, gx in glyphs:
            gs[g].draw(TransformPen(bp, (1, 0, 0, 1, gx, 0)))
        xmin, ymin, xmax, ymax = bp.bounds
        x0, y0, x1, y1 = box
        sx, sy = (x1 - x0) / (xmax - xmin), (y1 - y0) / (ymax - ymin)
        pen = SVGPathPen(gs)
        for g, gx in glyphs:
            # font units (y up) -> box (y down)
            t = (sx, 0, 0, -sy, x0 + (gx - xmin) * sx, y1 + ymin * sy)
            gs[g].draw(TransformPen(pen, t))
        self.items.append(f'<path d="{pen.getCommands()}" fill="{fill}" fill-rule="nonzero"/>')

    def svg(self):
        return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.w} {self.h}" width="{self.w}" height="{self.h}">'
                + ''.join(self.items) + '</svg>')

    def save(self, path):
        open(path, 'w').write(self.svg())

    def check(self, ref_path, out_path, scale=2):
        """Side-by-side: reference | redraw | redraw outline over reference."""
        # macOS + Homebrew: libcairo (for cairosvg) is not on ctypes' default search path; add it for the import only
        hb = sys.platform == 'darwin' and 'DYLD_FALLBACK_LIBRARY_PATH' not in os.environ and os.path.isdir('/opt/homebrew/lib')
        if hb: os.environ['DYLD_FALLBACK_LIBRARY_PATH'] = os.pathsep.join([os.path.expanduser('~/lib'), '/usr/local/lib', '/lib', '/usr/lib', '/opt/homebrew/lib'])
        import io, cairosvg, numpy as np, cv2
        if hb: del os.environ['DYLD_FALLBACK_LIBRARY_PATH']
        from PIL import Image
        W, H = self.w * scale, self.h * scale
        ref = Image.open(ref_path).convert('RGB').resize((W, H), Image.LANCZOS)
        vec = Image.open(io.BytesIO(cairosvg.svg2png(bytestring=self.svg().encode(), output_width=W, output_height=H))).convert('RGBA')
        flat = Image.new('RGB', (W, H), (128, 128, 128)); flat.paste(vec, (0, 0), vec)
        a = (np.array(vec)[..., 3] > 128).astype(np.uint8)
        edge = cv2.morphologyEx(a, cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8)) > 0
        ov = np.array(ref).copy(); ov[edge] = (0, 200, 255)
        sheet = Image.new('RGB', (W * 3, H)); sheet.paste(ref, (0, 0)); sheet.paste(flat, (W, 0)); sheet.paste(Image.fromarray(ov), (2 * W, 0))
        sheet.save(out_path)
