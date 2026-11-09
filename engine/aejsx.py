#!/usr/bin/env python3
"""aejsx.py - editable After Effects handoff (X1): rebuild a template as a native AE comp from an ExtendScript .jsx.

A template describes its layers once (images, solids, native text) and samples its own spring motion per frame; this
module bakes those samples into keyframes (dropping the ones a straight line between neighbours already gives, to a
tolerance, so the curves stay editable) and writes a .jsx that, run in After Effects (File > Scripts > Run Script
File...), imports the image assets, builds the comp and sets every keyframe. Springs stay exactly as rendered.

    from aejsx import Comp
    c = Comp("Card", 1920, 1080, 30, 5.5)
    card = c.null("Card")                                      # parent for a group move
    pan = c.image("Panel", "panel.png", anchor=(0, 0), pos=(90, 700), parent=card)
    pan.track("position", [(t, (x, 700)) for t, x in samples])
    txt = c.text("Name", "#12 PLAYER", font_ps="Anton-Regular", size=64, color=(1, 1, 1), pos=(300, 760))
    txt.source_track([(0.0, "0"), (0.5, "54"), ...])           # counting text: hold keyframes
    c.write("out/Card.jsx", assets_dir="out/Card_ae")          # assets are copied next to the .jsx

Text layers need the font installed in the Mac/PC running AE (the font's PostScript name is used); the script reports
any font AE does not find and leaves that layer in AE's default font.
"""
import json, os, shutil

PROPS = {"position": "ADBE Position", "scale": "ADBE Scale", "opacity": "ADBE Opacity", "rotation": "ADBE Rotate Z",
         "anchor": "ADBE Anchor Point"}


def ps_name(ttf):
    """PostScript name of a font file (what AE's TextDocument.font wants)."""
    from fontTools.ttLib import TTFont
    f = TTFont(ttf, lazy=True)
    for rec in f["name"].names:
        if rec.nameID == 6:
            return rec.toUnicode()
    return os.path.splitext(os.path.basename(ttf))[0]


def _simplify(keys, tol):
    """keys [(t, value-or-tuple)] -> fewer keys: keep a key unless the line between the kept neighbours already gives
    it to within tol (Ramer-Douglas-Peucker on time). First and last always stay."""
    if len(keys) <= 2:
        return keys
    vec = lambda v: v if isinstance(v, (list, tuple)) else (v,)
    def err(i, a, b):
        ta, tb, t = keys[a][0], keys[b][0], keys[i][0]
        u = 0 if tb == ta else (t - ta) / (tb - ta)
        va, vb, vi = vec(keys[a][1]), vec(keys[b][1]), vec(keys[i][1])
        return max(abs(x + (y - x) * u - z) for x, y, z in zip(va, vb, vi))
    keep = {0, len(keys) - 1}
    stack = [(0, len(keys) - 1)]
    while stack:
        a, b = stack.pop()
        if b - a < 2:
            continue
        i, e = max(((i, err(i, a, b)) for i in range(a + 1, b)), key=lambda p: p[1])
        if e > tol:
            keep.add(i); stack += [(a, i), (i, b)]
    return [keys[i] for i in sorted(keep)]


class Layer:
    def __init__(self, comp, kind, name, **kw):
        self.comp, self.kind, self.name, self.kw = comp, kind, name, kw
        self.tracks, self.source = {}, None
        self.idx = None

    def track(self, prop, keys, tol=None):
        """keys [(t, value)]: position (x, y), scale (sx, sy) percent, opacity 0-100, rotation degrees."""
        if prop not in PROPS:
            raise ValueError(f"aejsx: unknown property {prop}")
        tol = tol if tol is not None else {"position": 0.25, "anchor": 0.25, "scale": 0.05, "opacity": 0.2, "rotation": 0.05}[prop]
        k = [(round(t, 6), tuple(round(x, 3) for x in v) if isinstance(v, (list, tuple)) else round(v, 3)) for t, v in keys]
        self.tracks[prop] = _simplify(k, tol)
        return self

    def source_track(self, keys):
        """text layers: [(t, string)] hold keyframes (only where the string changes)."""
        out, last = [], None
        for t, s in keys:
            if s != last:
                out.append((round(t, 6), s)); last = s
        self.source = out
        return self


class Comp:
    def __init__(self, name, w, h, fps, dur, bg=(0, 0, 0)):
        self.name, self.w, self.h, self.fps, self.dur, self.bg = name, int(w), int(h), float(fps), float(dur), bg
        self.layers = []
        self.group_op = None

    def group_opacity(self, keys, tol=0.2):
        """fade the whole comp as one (the layers go into a precomp '<name> (layers)' and this opacity track goes on
        it), so overlapping layers fade like the render's group fade instead of showing through each other."""
        self.group_op = _simplify([(round(t, 6), round(v, 3)) for t, v in keys], tol)
        return self

    def _add(self, L):
        self.layers.append(L); return L

    def null(self, name, pos=(0, 0), parent=None):
        """a null at the comp origin with its anchor at (0, 0): a child's position is then an offset from it"""
        return self._add(Layer(self, "null", name, pos=pos, anchor=(0, 0), parent=parent))

    def image(self, name, path, pos, anchor=(0, 0), parent=None, matte_of=None, start=0.0):
        """an image layer; anchor in layer pixels (0,0 = its top-left), pos in comp pixels."""
        return self._add(Layer(self, "image", name, path=path, pos=pos, anchor=anchor, parent=parent, start=start))

    def solid(self, name, size, color, pos, anchor=(0, 0), parent=None):
        return self._add(Layer(self, "solid", name, size=size, color=color, pos=pos, anchor=anchor, parent=parent))

    def text(self, name, s, font_ps, size, color, pos, justify="left", tracking=0, parent=None, start=0.0):
        """native point text; pos = the baseline start (left justify) or centre (center); colour 0-1 floats."""
        return self._add(Layer(self, "text", name, s=s, font=font_ps, size=size, color=color, pos=pos,
                               justify=justify, tracking=tracking, parent=parent, start=start))

    def matte(self, layer, matte_layer):
        """use matte_layer's alpha as the track matte of layer (matte_layer is placed directly above it)."""
        layer.kw["matte"] = matte_layer
        return layer

    # ------------------------------------------------------------------ output
    def spec(self, assets_rel):
        order = self.layers
        for i, L in enumerate(order):
            L.idx = i
        out = []
        for L in order:
            d = {"kind": L.kind, "name": L.name}
            for k, v in L.kw.items():
                if k == "parent":
                    d["parent"] = v.idx if v is not None else None
                elif k == "matte":
                    d["matte"] = v.idx
                elif k == "path":
                    d["file"] = assets_rel + "/" + os.path.basename(v)
                else:
                    d[k] = list(v) if isinstance(v, tuple) else v
            d["tracks"] = {PROPS[p]: [[t, list(v) if isinstance(v, tuple) else v] for t, v in keys]
                           for p, keys in L.tracks.items()}
            if L.source:
                d["source"] = L.source
            out.append(d)
        return {"name": self.name, "w": self.w, "h": self.h, "fps": self.fps, "dur": self.dur,
                "bg": list(self.bg), "layers": out, "groupOpacity": self.group_op}

    def write(self, jsx_path, assets_dir):
        os.makedirs(assets_dir, exist_ok=True)
        for L in self.layers:
            if L.kind == "image" and os.path.abspath(os.path.dirname(L.kw["path"])) != os.path.abspath(assets_dir):
                shutil.copy2(L.kw["path"], os.path.join(assets_dir, os.path.basename(L.kw["path"])))
        rel = os.path.relpath(assets_dir, os.path.dirname(os.path.abspath(jsx_path)))
        spec = self.spec(rel.replace(os.sep, "/"))
        with open(jsx_path, "w", encoding="utf-8") as f:
            f.write(JSX_HEAD + "var SPEC = " + json.dumps(spec, ensure_ascii=True, indent=1) + ";\n" + JSX_BODY)
        return jsx_path


JSX_HEAD = """// Built by the Video Engine (engine/aejsx.py). In After Effects: File > Scripts > Run Script File... and pick this
// file. It imports the images next to it, builds the comp and bakes every spring as keyframes. Safe to run twice
// (it makes a new comp each time). Text layers use the profile fonts: install them first (resources/fonts).
"""

JSX_BODY = r"""
(function () {
  var here = File($.fileName).parent;
  app.beginUndoGroup("Video Engine: " + SPEC.name);
  var proj = app.project || app.newProject();
  var folder = proj.items.addFolder(SPEC.name + " (Video Engine)");
  var outer = proj.items.addComp(SPEC.name, SPEC.w, SPEC.h, 1, SPEC.dur, SPEC.fps);
  outer.parentFolder = folder; outer.bgColor = SPEC.bg;
  var comp = outer;
  if (SPEC.groupOpacity) {                 // layers in a precomp; the group fade goes on the precomp layer
    comp = proj.items.addComp(SPEC.name + " (layers)", SPEC.w, SPEC.h, 1, SPEC.dur, SPEC.fps);
    comp.parentFolder = folder; comp.bgColor = SPEC.bg;
  }
  var made = [], missingFonts = [];
  function setTrack(layer, matchName, keys) {
    var p = layer.property("ADBE Transform Group").property(matchName);
    if (!keys || !keys.length) return;
    if (keys.length === 1) { p.setValue(keys[0][1]); return; }
    var ts = [], vs = [];
    for (var i = 0; i < keys.length; i++) { ts.push(keys[i][0]); vs.push(keys[i][1]); }
    p.setValuesAtTimes(ts, vs);
    for (var k = 1; k <= p.numKeys; k++) p.setInterpolationTypeAtKey(k, KeyframeInterpolationType.LINEAR, KeyframeInterpolationType.LINEAR);
  }
  // build bottom-up so the first spec layer ends up on top (AE adds new layers at index 1)
  for (var i = SPEC.layers.length - 1; i >= 0; i--) {
    var L = SPEC.layers[i], lay = null;
    if (L.kind === "null") { lay = comp.layers.addNull(SPEC.dur); }
    else if (L.kind === "solid") { lay = comp.layers.addSolid(L.color, L.name, L.size[0], L.size[1], 1, SPEC.dur); }
    else if (L.kind === "image") {
      var f = new File(here.fsName + "/" + L.file);
      if (!f.exists) { alert("Video Engine: missing asset " + f.fsName); continue; }
      var item = proj.importFile(new ImportOptions(f)); item.parentFolder = folder;
      lay = comp.layers.add(item, SPEC.dur);
    } else if (L.kind === "text") {
      lay = comp.layers.addText(L.s);
      var st = lay.property("ADBE Text Properties").property("ADBE Text Document");
      var doc = st.value;
      doc.resetCharStyle(); doc.fontSize = L.size; doc.fillColor = L.color; doc.applyFill = true; doc.applyStroke = false;
      doc.tracking = L.tracking || 0;
      doc.justification = L.justify === "center" ? ParagraphJustification.CENTER_JUSTIFY :
                          (L.justify === "right" ? ParagraphJustification.RIGHT_JUSTIFY : ParagraphJustification.LEFT_JUSTIFY);
      try { doc.font = L.font; } catch (e) { missingFonts.push(L.font); }
      st.setValue(doc);
      if (doc.font !== L.font) missingFonts.push(L.font);
      if (L.source && L.source.length) {
        for (var k = 0; k < L.source.length; k++) {
          var d2 = st.value; d2.text = L.source[k][1]; st.setValueAtTime(L.source[k][0], d2);
        }
        for (var k = 1; k <= st.numKeys; k++) st.setInterpolationTypeAtKey(k, KeyframeInterpolationType.HOLD, KeyframeInterpolationType.HOLD);
      }
    }
    if (!lay) continue;
    lay.name = L.name;
    if (L.start) lay.inPoint = L.start;
    var tg = lay.property("ADBE Transform Group");
    if (L.anchor) tg.property("ADBE Anchor Point").setValue(L.anchor);
    if (L.pos) tg.property("ADBE Position").setValue(L.pos);
    for (var m in L.tracks) if (L.tracks.hasOwnProperty(m)) setTrack(lay, m, L.tracks[m]);
    made[i] = lay;
  }
  for (var i = 0; i < SPEC.layers.length; i++) {
    var L = SPEC.layers[i];
    // setParentWithJump: parent without AE re-computing the child's transform (our positions are already relative)
    if (made[i] && L.parent !== undefined && L.parent !== null && made[L.parent]) {
      if (typeof made[i].setParentWithJump === "function") made[i].setParentWithJump(made[L.parent]); else made[i].parent = made[L.parent];
    }
  }
  for (var i = 0; i < SPEC.layers.length; i++) {
    var L = SPEC.layers[i];
    if (made[i] && L.matte !== undefined && made[L.matte]) {
      made[L.matte].moveBefore(made[i]);
      made[i].trackMatteType = TrackMatteType.ALPHA;
    }
  }
  if (SPEC.groupOpacity) {
    var pl = outer.layers.add(comp, SPEC.dur); pl.name = SPEC.name + " (layers)";
    setTrack(pl, "ADBE Opacity", SPEC.groupOpacity);
  }
  outer.openInViewer();
  app.endUndoGroup();
  if (missingFonts.length) alert("Video Engine: install these fonts, then re-run (layers use AE's default font for now):\n" + missingFonts.join("\n"));
})();
"""
