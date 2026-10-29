"""Draw what the Wii Menu draws, frame by frame, from a channel's own archives.

A small brlyt/brlan interpreter: Benzin rips the layout and animations to XML,
the TPLs in the archive are decoded, and each frame composites the pane tree
with full transforms (translate, rotate, scale, size, origin), alpha inherited
down the tree, per-corner vertex colors, pane UV quads, texture SRT and wrap
modes, and the material's two TEV colors (a texel maps between them, black to
the first and white to the second). Animations drive every channel the Menu
animates here: RLPA, RLVC, RLVI, RLMC, RLTS and RLTP. Keyframes interpolate as
GX does (cubic Hermite with per-key tangents; flipbooks and visibility step).

Nothing about an animation is re-described: if a keyframe is wrong in the
archive, it is wrong in the render.
"""

import math
import os
import re
import struct
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(__file__))

import tpl as T
from wiilib import U8, unpack_lz77_imd5
from vbcgx import BENZIN, benzin

WIDE = 836 / 608                     # the Menu's 16:9 stretch of the 4:3 layout (Dolphin's 16:9 dumps are 836 wide)
TAGBLOCK = r'<tag type="(\w+)"((?:[^>]*[^/>])?)(?:>(.*?)</tag>|\s*/>)'
RLPA = {"X Translation": "tx", "Y Translation": "ty", "Z Translation": "tz", "X Rotate": "rx",
        "Y Rotate": "ry", "Z Rotate": "rz", "X Scale": "sx", "Y Scale": "sy", "Width": "w",
        "Height": "h"}
RLTS = {"XTrans": 0, "YTrans": 1, "Rotate": 2, "XScale": 3, "YScale": 4}
CORNERS = ("Top Left", "Top Right", "Bottom Left", "Bottom Right")
MATCOL = {f"{grp} {c}": (slot, i) for slot, grp in (("mat", "MatColor"), ("fore", "Forecolor"),
                                                     ("back", "Backcolor"), ("reg3", "TevReg3"))
          for i, c in enumerate(("Red", "Green", "Blue", "Alpha"))}


# ------------------------------------------------------------------ keyframes

def hermite(keys, t):
    if t <= keys[0][0]:
        return keys[0][1]
    if t >= keys[-1][0]:
        return keys[-1][1]
    for (f0, v0, m0), (f1, v1, m1) in zip(keys, keys[1:]):
        if f0 <= t <= f1:
            h = f1 - f0
            if h == 0:
                return v1
            s = (t - f0) / h
            return (v0 * (2 * s**3 - 3 * s**2 + 1) + v1 * (-2 * s**3 + 3 * s**2)
                    + h * m0 * (s**3 - 2 * s**2 + s) + h * m1 * (s**3 - s**2))
    return keys[-1][1]


def stepped(pairs, t):
    v = pairs[0][1]
    for f, x in pairs:
        if f <= t:
            v = x
    return v


# --------------------------------------------------------------------- parse

def _num(body, tag, default=0.0):
    m = re.search(rf"<{tag}>([^<]*)</{tag}>", body)
    return float(m.group(1)) if m else default


def _rgba(body, tag, hexa=True):
    m = re.search(rf'<{tag} r="(\w+)" g="(\w+)" b="(\w+)" a="(\w+)"', body)
    if not m:
        return [255.0] * 4
    return [float(int(v, 16) if hexa else int(v)) for v in m.groups()]


def parse_layout(xml):
    panes, stack = [], []
    for m in re.finditer(TAGBLOCK, xml, re.S):
        kind, attrs, body = m.group(1), m.group(2), m.group(3)
        if kind == "pas1":
            stack.append(len(panes) - 1)
            continue
        if kind == "pae1":
            stack.pop()
            continue
        if kind not in ("pan1", "pic1", "txt1", "wnd1", "bnd1") or body is None:
            continue
        tr = re.search(r"<translate>\s*<x>([-\d.e]+)</x>\s*<y>([-\d.e]+)</y>\s*<z>([-\d.e]+)</z>", body)
        ro = re.search(r"<rotate>\s*<x>([-\d.e]+)</x>\s*<y>([-\d.e]+)</y>\s*<z>([-\d.e]+)</z>", body)
        sc = re.search(r"<scale>\s*<x>([-\d.e]+)</x>\s*<y>([-\d.e]+)</y>", body)
        org = re.search(r'<origin x="(\w+)" y="(\w+)"', body)
        mat = re.search(r'<material name="([^"]+)"', body)

        p = dict(kind=kind, name=re.search(r'name="([^"]*)"', attrs).group(1),
                 parent=stack[-1] if stack else None,
                 visible=re.search(r"<visible>(\w+)</visible>", body).group(1) == "01",
                 flag=int(re.search(r"<flag>(\w+)</flag>", body).group(1), 16),
                 influence=int((re.search(r"<WidescreenAffected>(\w+)</WidescreenAffected>", body) or [0, "0"])[1], 16),
                 alpha=float(int(re.search(r"<alpha>(\w+)</alpha>", body).group(1), 16)),
                 tx=float(tr.group(1)), ty=float(tr.group(2)), tz=float(tr.group(3)),
                 rx=float(ro.group(1)), ry=float(ro.group(2)), rz=float(ro.group(3)),
                 sx=float(sc.group(1)), sy=float(sc.group(2)),
                 w=_num(body, "width"), h=_num(body, "height"),
                 ox=org.group(1) if org else "Center", oy=org.group(2) if org else "Center",
                 mat=mat.group(1) if mat else None)

        if kind == "txt1":
            hexs = re.search(r"<text>([0-9a-fA-F]*)</text>", body)
            p["text"] = bytes.fromhex(hexs.group(1)).decode("utf-16-be").split("\0")[0] if hexs else ""
            p["font_h"] = _num(body, "ysize", 18.0)
            p["text_color"] = _rgba(body, "topcolor")
        if kind == "pic1":
            p["vtx"] = [_rgba(body, f"vtxColor{c}") for c in ("TL", "TR", "BL", "BR")]
            uv = re.findall(r'<coord(TL|TR|BL|BR) s="([-\d.e]+)" t="([-\d.e]+)"', body)
            d = {k: (float(s), float(t)) for k, s, t in uv[:4]}
            p["uv"] = [d.get(k, dv) for k, dv in (("TL", (0, 0)), ("TR", (1, 0)),
                                                   ("BL", (0, 1)), ("BR", (1, 1)))]
        panes.append(p)
    return panes


def parse_materials(xml):
    mats = {}
    for m in re.finditer(r'<entries name="([^"]+)">(.*?)</entries>', xml, re.S):
        name, body = m.groups()
        if "<colors>" not in body:
            continue                                    # a txl1/fnl1 entry, not a material
        cols = re.search(r"<colors>(.*?)</colors>", body, re.S).group(1)
        texs = re.findall(r'<texture name="([^"]+)">\s*<wrap_s>(\w+)</wrap_s>\s*<wrap_t>(\w+)</wrap_t>', body)
        srt = re.search(r"<TextureSRT>(.*?)</TextureSRT>", body, re.S)
        mats[name] = dict(
            fore=_rgba(cols, "forecolor", hexa=False), back=_rgba(cols, "backcolor", hexa=False),
            mat=_rgba(body, "MaterialColor", hexa=False) if "<MaterialColor" in body else [255.0] * 4,
            tex=[t[0] for t in texs], wrap=[(t[1], t[2]) for t in texs],
            srt=[_num(srt.group(1), k) for k in ("XTrans", "YTrans", "Rotate", "XScale", "YScale")]
            if srt else [0.0, 0.0, 0.0, 1.0, 1.0])
    return mats


def parse_anim(xml):
    head = re.search(r'<pai1 framesize="(\d+)" flags="(\w+)">', xml)
    timg = re.findall(r'<timg name="([^"]+)"', xml)
    panes, mats = {}, {}
    for m in re.finditer(r'<pane name="([^"]+)" type="(\d)">(.*?)</pane>', xml, re.S):
        name, kind, body = m.group(1), int(m.group(2)), m.group(3)
        dst = (panes if kind == 0 else mats).setdefault(name, {})
        for tag in re.finditer(r'<tag type="(\w+)">(.*?)</tag>', body, re.S):
            ttype, tbody = tag.groups()
            for e in re.finditer(r'<entry type1="(\d+)" type2="([^"]+)">(.*?)</entry>', tbody, re.S):
                t1, ch, eb = int(e.group(1)), e.group(2), e.group(3)
                trip = [(float(f), float(v), float(b)) for f, v, b in re.findall(
                    r"<frame>([-\d.e]+)</frame>\s*<value>([-\d.e]+)</value>\s*<blend>([-\d.e]+)</blend>", eb)]
                pairs = [(float(f), int(d, 16)) for f, d in re.findall(
                    r"<data1>([-\d.e]+)</data1>\s*<data2>(\w+)</data2>", eb)]

                if ttype == "RLPA" and ch in RLPA and trip:
                    dst[RLPA[ch]] = trip
                elif ttype == "RLVC" and trip:
                    if ch == "16":
                        dst["alpha"] = trip
                    else:
                        for ci, corner in enumerate(CORNERS):
                            for k, c in enumerate("RGBA"):
                                if ch in (f"{corner} {c}", str(ci * 4 + k)):
                                    dst[("vtx", ci, k)] = trip
                elif ttype == "RLVI" and pairs:
                    dst["visible"] = pairs
                elif ttype == "RLVI" and trip:
                    dst["visible"] = [(f, int(v)) for f, v, _ in trip]
                elif ttype == "RLMC" and ch in MATCOL and trip:
                    dst[("col",) + MATCOL[ch]] = trip
                elif ttype == "RLTS" and trip:
                    key = ch if ch in RLTS else None
                    if key is not None:
                        dst[("srt", t1, RLTS[key])] = trip
                elif ttype == "RLTP" and pairs:
                    dst[("tp", t1)] = pairs
    return dict(framesize=int(head.group(1)), loop=head.group(2) == "01", timg=timg,
                panes=panes, mats=mats)


# ----------------------------------------------------------------- archive

def texmap_filters(brlyt):
    """({material: mag filter is nearest}, the layout with every texture map's filter bits cleared).

    A texture map's two wrap bytes also carry its filters (nw4r: min filter in bits 2-4 of the S byte, mag
    filter in bit 2 of the T byte, stored so that zero means linear). Benzin reads those bytes as wrap modes
    only, so the bits are lifted off before Benzin sees the layout."""
    b = bytearray(brlyt)
    m = b.find(b"mat1")
    n = struct.unpack(">H", b[m + 8:m + 10])[0]
    offs = struct.unpack(f">{n}I", b[m + 12:m + 12 + 4 * n])
    nearest = {}
    for o in offs:
        base = m + o
        name = bytes(b[base:base + 20]).split(b"\0")[0].decode()
        flags = struct.unpack(">I", b[base + 60:base + 64])[0]
        for t in range(flags & 0xF):
            at = base + 64 + 4 * t
            if t == 0:
                nearest[name] = bool(b[at + 3] >> 2 & 1)
            b[at + 2] &= 0x03
            b[at + 3] &= 0x03
    return nearest, bytes(b)


def set_mag_nearest(brlyt, names):
    """The layout with the mag filter of each named material's first texture map set to nearest."""
    b = bytearray(brlyt)
    m = b.find(b"mat1")
    n = struct.unpack(">H", b[m + 8:m + 10])[0]
    offs = struct.unpack(f">{n}I", b[m + 12:m + 12 + 4 * n])
    done = set()
    for o in offs:
        base = m + o
        name = bytes(b[base:base + 20]).split(b"\0")[0].decode()
        if name in names:
            b[base + 64 + 3] |= 0x04
            done.add(name)
    assert done == set(names), set(names) - done
    return bytes(b)


class Archive:
    """One icon.bin / banner.bin (or its U8 bytes), ready to render."""

    def __init__(self, data, kind):
        if data[:4] == b"IMD5":
            data = unpack_lz77_imd5(data)
        arc = U8.load(data)
        self.files = {os.path.basename(p): arc.nodes[i].data
                      for i, p in arc.paths() if not arc.nodes[i].is_dir}
        lyt = [n for n in self.files if n.endswith(".brlyt")][0]
        self.nearest, plain = texmap_filters(self.files[lyt])
        self.layout_xml = rip(plain, ".xmlyt")
        self.panes = parse_layout(self.layout_xml)
        self.materials = parse_materials(self.layout_xml)
        for name, m in self.materials.items():
            tex = self.files.get(m["tex"][0]) if m["tex"] else None
            in_tpl = tex is not None and T.parse(tex)[0]["mag_filter"] == 0
            m["nearest"] = self.nearest.get(name, False) or in_tpl
        self.anims = {n[:-6]: parse_anim(rip(self.files[n], ".xmlan"))
                      for n in self.files if n.endswith(".brlan")}
        self._tex = {}
        self.kind = kind

    def texture(self, name):
        if name not in self._tex:
            data = self.files.get(name)
            if data is None:
                self._tex[name] = None
            else:
                info = T.parse(data)[0]
                img = T.decode(data[info["data_off"]:], info["w"], info["h"], info["fmt"], info["pal"])
                self._tex[name] = np.asarray(img.convert("RGBA"), np.float32) / 255.0
        return self._tex[name]

    # ----------------------------------------------------------- one frame
    def render(self, anim_name, frame, canvas, background=(0, 0, 0), widescreen=False):
        """widescreen: the Menu's 16:9 framing. The 4:3 layout is stretched 4/3 to the screen (positions
        spread out), and every location-adjusted pane (Benzin's <flag>) has its own subtree squeezed back by
        3/4, so a pane under one adjusted ancestor keeps its proportions. In 4:3 neither applies."""
        an = self.anims[anim_name] if anim_name else dict(panes={}, mats={}, timg=[])
        stretch = WIDE if widescreen else 1.0
        W, H = canvas
        out = np.zeros((H, W, 3), np.float32)
        out[:] = np.array(background, np.float32) / 255.0

        mats = {k: _animated_material(v, an["mats"].get(k, {}), an["timg"], frame)
                for k, v in self.materials.items()}
        world = [None] * len(self.panes)
        alpha = [1.0] * len(self.panes)
        shown = [True] * len(self.panes)

        for i, p in enumerate(self.panes):
            tr = an["panes"].get(p["name"], {})
            v = lambda k: hermite(tr[k], frame) if k in tr else p[k]
            vis = p["visible"]
            if "visible" in tr:
                vis = stepped(tr["visible"], frame) != 0
            a = max(0.0, min(255.0, v("alpha"))) / 255.0
            adjust = (1.0 / stretch) if (p["flag"] & 1) else 1.0
            local = _matrix(v("tx"), v("ty"), v("tz"), v("rx"), v("ry"), v("rz"), v("sx") * adjust, v("sy"))

            par = p["parent"]
            if par is None:
                world[i], alpha[i], shown[i] = np.diag([stretch, 1.0, 1.0, 1.0]) @ local, a, vis
            else:
                world[i] = world[par] @ local
                inherit = alpha[par] if self.panes[par]["influence"] & 1 else 1.0
                alpha[i], shown[i] = a * inherit, vis and shown[par]

            if p["kind"] == "txt1" and shown[i] and alpha[i] > 0.002 and p.get("text"):
                _draw_text(out, world[i], p, alpha[i])
                continue
            if p["kind"] != "pic1" or not shown[i] or alpha[i] <= 0.002:
                continue

            m = mats.get(p["mat"])
            if m is None:
                continue

            vtx = [[hermite(tr[("vtx", c, k)], frame) if ("vtx", c, k) in tr else p["vtx"][c][k]
                    for k in range(4)] for c in range(4)]
            _draw_quad(out, world[i], v("w"), v("h"), p["ox"], p["oy"], p["uv"], vtx,
                       alpha[i], m, self.texture(m["tex"][0]) if m["tex"] else None)

        return Image.fromarray((np.clip(out, 0, 1) * 255 + 0.5).astype(np.uint8), "RGB")


def rip(binary, ext):
    """Benzin XML text for one .brlyt/.brlan's bytes."""
    tag = f"_r{os.getpid()}"                 # per process: two builds sharing Benzin's folder must not collide
    src = tag + (".brlyt" if ext == ".xmlyt" else ".brlan")
    open(os.path.join(BENZIN, src), "wb").write(binary)
    benzin("r", src, tag + ext)
    xml = open(os.path.join(BENZIN, tag + ext)).read()
    os.remove(os.path.join(BENZIN, src))
    os.remove(os.path.join(BENZIN, tag + ext))
    return xml


def _animated_material(m, tracks, timg, frame):
    m = dict(m, fore=list(m["fore"]), back=list(m["back"]), mat=list(m["mat"]),
             tex=list(m["tex"]), srt=list(m["srt"]))
    for key, keys in tracks.items():
        if key[0] == "col":
            slot, i = key[1], key[2]
            m[slot][i] = max(0.0, min(255.0, hermite(keys, frame)))
        elif key[0] == "srt" and key[1] == 0:
            m["srt"][key[2]] = hermite(keys, frame)
        elif key[0] == "tp" and key[1] < len(m["tex"]):
            idx = stepped(keys, frame)
            if idx < len(timg):
                m["tex"][key[1]] = timg[idx]
    return m


def _matrix(tx, ty, tz, rx, ry, rz, sx, sy):
    """Pane-local -> parent, as NW4R composes it: T * Rz * Ry * Rx * S (degrees)."""
    def rot(axis, deg):
        c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
        r = np.eye(4)
        i, j = {"x": (1, 2), "y": (2, 0), "z": (0, 1)}[axis]
        r[i, i], r[i, j], r[j, i], r[j, j] = c, -s, s, c
        return r

    t = np.eye(4)
    t[:3, 3] = (tx, ty, tz)
    s = np.diag([sx, sy, 1.0, 1.0])
    return t @ rot("z", rz) @ rot("y", ry) @ rot("x", rx) @ s


def _draw_quad(out, M, w, h, ox, oy, uv, vtx, alpha, m, tex):
    H, W = out.shape[:2]
    x0 = {"Left": 0.0, "Center": -w / 2.0, "Right": -w}[ox]
    y0 = {"Top": 0.0, "Center": h / 2.0, "Bottom": h}[oy]       # +y up: the top edge

    # local quad corners (TL, TR, BL, BR) -> screen (y down, origin at the canvas center)
    loc = np.array([[x0, y0, 0, 1], [x0 + w, y0, 0, 1], [x0, y0 - h, 0, 1], [x0 + w, y0 - h, 0, 1]]).T
    scr = (M @ loc)[:2].T
    scr[:, 0] += W / 2.0
    scr[:, 1] = H / 2.0 - scr[:, 1]
    xs, ys = scr[:, 0], scr[:, 1]
    bx0, bx1 = int(max(0, math.floor(xs.min()))), int(min(W, math.ceil(xs.max())))
    by0, by1 = int(max(0, math.floor(ys.min()))), int(min(H, math.ceil(ys.max())))
    if bx1 <= bx0 or by1 <= by0:
        return

    # the quad is a parallelogram (affine): solve pixel center -> (u, v) in [0, 1]^2
    o, ex, ey = scr[0], scr[1] - scr[0], scr[2] - scr[0]
    det = ex[0] * ey[1] - ex[1] * ey[0]
    if abs(det) < 1e-9:
        return

    gx, gy = np.meshgrid(np.arange(bx0, bx1) + 0.5, np.arange(by0, by1) + 0.5)
    dx, dy = gx - o[0], gy - o[1]
    u = (dx * ey[1] - dy * ey[0]) / det
    v = (ex[0] * dy - ex[1] * dx) / det
    inside = (u >= 0) & (u < 1) & (v >= 0) & (v < 1)
    if not inside.any():
        return
    u, v = u[inside], v[inside]

    # UV quad, then the material's texture SRT (about the texture center)
    (s0, t0), (s1, t1), (s2, t2), (s3, t3) = uv
    s = (1 - u) * (1 - v) * s0 + u * (1 - v) * s1 + (1 - u) * v * s2 + u * v * s3
    t = (1 - u) * (1 - v) * t0 + u * (1 - v) * t1 + (1 - u) * v * t2 + u * v * t3
    xt, yt, rot, xsc, ysc = m["srt"]
    if (xt, yt, rot, xsc, ysc) != (0.0, 0.0, 0.0, 1.0, 1.0):
        c, sn = math.cos(math.radians(rot)), math.sin(math.radians(rot))
        ps, pt = (s - 0.5) * xsc, (t - 0.5) * ysc
        s, t = c * ps - sn * pt + 0.5 + xt, sn * ps + c * pt + 0.5 + yt

    if tex is not None:
        texel = _sample(tex, s, t, m["wrap"][0], m.get("nearest", False))
    else:
        texel = np.ones((len(u), 4), np.float32)

    fore, back = np.array(m["fore"]) / 255.0, np.array(m["back"]) / 255.0
    col = fore + (back - fore) * texel
    vc = np.array(vtx, np.float32) / 255.0
    vcol = ((1 - u) * (1 - v))[:, None] * vc[0] + (u * (1 - v))[:, None] * vc[1] \
        + ((1 - u) * v)[:, None] * vc[2] + (u * v)[:, None] * vc[3]
    col = np.clip(col, 0, 1) * vcol
    a = col[:, 3] * alpha

    region = out[by0:by1, bx0:bx1]
    dst = region[inside]
    region[inside] = dst * (1 - a[:, None]) + col[:, :3] * a[:, None]


def _draw_text(out, M, p, alpha):
    """A stand-in for the Menu's own font (Rodin): good enough to place the title, not to judge its letters."""
    from PIL import ImageDraw, ImageFont
    H, W = out.shape[:2]
    try:
        font = ImageFont.truetype("/usr/share/fonts/google-noto/NotoSans-Medium.ttf", int(p["font_h"] * 0.9))
    except OSError:
        font = ImageFont.load_default()

    w, h = p["w"], p["h"]
    x0 = {"Left": 0.0, "Center": -w / 2.0, "Right": -w}[p["ox"]]
    y0 = {"Top": 0.0, "Center": h / 2.0, "Bottom": h}[p["oy"]]
    cx, cy = (M @ np.array([x0 + w / 2.0, y0 - h / 2.0, 0, 1]))[:2]
    layer = Image.new("RGBA", (W, H))
    d = ImageDraw.Draw(layer)
    r, g, b, a = p["text_color"]
    d.text(
        (W / 2.0 + cx, H / 2.0 - cy),
        p["text"],
        font=font,
        anchor="mm",
        fill=(int(r), int(g), int(b), int(a * alpha)),
    )
    la = np.asarray(layer, np.float32) / 255.0
    out[:] = out * (1 - la[..., 3:4]) + la[..., :3] * la[..., 3:4]


def _wrap(c, mode):
    if mode == "GX_REPEAT":
        return c - np.floor(c)
    if mode == "GX_MIRROR":
        f = np.mod(c, 2.0)
        return np.where(f > 1, 2 - f, f)
    return np.clip(c, 0, 1)


def _sample(tex, s, t, wrap, nearest=False):
    """Bilinear, as GX filters layout textures by default, with texel centers at (i + 0.5) / size; or the
    nearest texel when the material asks for it."""
    th, tw = tex.shape[:2]
    s, t = _wrap(s, wrap[0]), _wrap(t, wrap[1])

    if nearest:
        x = np.clip(np.floor(s * tw).astype(int), 0, tw - 1)
        y = np.clip(np.floor(t * th).astype(int), 0, th - 1)
        return tex[y, x]

    fx, fy = s * tw - 0.5, t * th - 0.5
    x0, y0 = np.floor(fx).astype(int), np.floor(fy).astype(int)
    ax, ay = (fx - x0)[:, None], (fy - y0)[:, None]

    def fetch(x, y):
        if wrap[0] == "GX_REPEAT":
            x = np.mod(x, tw)
        else:
            x = np.clip(x, 0, tw - 1)
        if wrap[1] == "GX_REPEAT":
            y = np.mod(y, th)
        else:
            y = np.clip(y, 0, th - 1)
        return tex[y, x]

    return ((1 - ax) * (1 - ay) * fetch(x0, y0) + ax * (1 - ay) * fetch(x0 + 1, y0)
            + (1 - ax) * ay * fetch(x0, y0 + 1) + ax * ay * fetch(x0 + 1, y0 + 1))


# ---------------------------------------------------------------- outputs

def frames(archive, anim_name, start, stop, step, canvas, background=(0, 0, 0)):
    return [archive.render(anim_name, f, canvas, background) for f in range(start, stop, step)]


def save_gif(imgs, path, step, scale=1):
    if scale != 1:
        imgs = [im.resize((im.width * scale, im.height * scale), Image.NEAREST) for im in imgs]
    imgs[0].save(path, save_all=True, append_images=imgs[1:], duration=round(1000 * step / 60),
                 loop=0, optimize=False)


def load_wad_parts(wad_path):
    """(icon.bin, banner.bin) bytes from a channel WAD."""
    from wiilib import WAD
    app = WAD.load(wad_path).contents[0]
    u8 = U8.load(app[app.find(b"\x55\xAA\x38\x2D"):])
    return u8.get("meta/icon.bin"), u8.get("meta/banner.bin")
