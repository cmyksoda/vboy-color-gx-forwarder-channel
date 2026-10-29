"""Build icon.bin: one of the Mario Clash icon proposals on the mGBA GX icon's layout.

    build_icon.py <look> [out.bin]        look: clash | red | grid

The layout is derived from the mGBA GX channel's released icon (Tantric's Snes9x GX icon underneath), never
written from scratch: its five picture panes keep their names and materials, the logo pane moves to just above
the background, and one pane is added on top for the pipe mouths that Mario walks behind. The story is the one
icon_scene.py renders for the mockups, sampled every frame and written as keyframes: pane translations, scales
and alpha, plus a flipbook (RLTP) per character over cels sharing one palette, the way Tantric's walk cycles work.
"""

import os
import re
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(__file__))

import icon_scene as S
import tpl as T
from render import rip
from vbcgx import BENZIN, OUT, ROOT, benzin
from wiilib import U8, WAD, pack_lz77_imd5, u8_set_dir_files, unpack_lz77_imd5

DONOR = os.path.join(ROOT, "donor", "mGBA-GX - GBGX [cmyksoda].wad")
LOOKS = {"clash": (0, "game", "a"), "red": (4, "red", "b"), "grid": (4, "red", "c")}
FRAMES = S.FRAMES

# Which donor pane carries which actor, and how its textures are named.
ACTORS = {
    "mario": ("Mario01", "Mario", ("walk", "bend", "lift", "hold", "wind", "throw", "back", "bwalk")),
    "koopa": ("Luigi01", "Koopa", ("koopa", "tumble")),
    "shell": ("Banana00", "Shell", ("shell", "fly", "land")),
}


def actor_of(cel):
    for actor, (_, _, prefixes) in ACTORS.items():
        if cel.startswith(prefixes):
            return actor
    raise KeyError(cel)


# ---------------------------------------------------------------- textures

def ceil(n, a):
    return (n + a - 1) // a * a


def palette_of(images):
    """One shared palette for a character's cels: every color they use, transparent first. None if > 15."""
    cols = set()
    for im in images:
        a = np.asarray(im)
        for px in a[a[..., 3] > 0][:, :3]:
            cols.add(tuple(int(v) for v in px))
    if len(cols) > 15:
        return None
    return [(0, 0, 0, 0)] + [c + (255,) for c in sorted(cols)]


def index_map(im, pal):
    lut = {c[:3]: i for i, c in enumerate(pal) if c[3]}
    a = np.asarray(im)
    idx = np.zeros(a.shape[:2], np.uint8)
    for y, x in zip(*np.nonzero(a[..., 3])):
        idx[y, x] = lut[tuple(int(v) for v in a[y, x, :3])]
    return idx.tolist()


def ci_tpl(im, pal):
    """CI4 with the given shared palette; the decode is checked against the source, cel by cel."""
    fmt = T.CI4 if len(pal) <= 16 else T.CI8
    data = T.build([(index_map(im, pal), fmt, pal, im.size)])
    info = T.parse(data)[0]
    back = np.asarray(T.decode(data[info["data_off"]:], info["w"], info["h"], fmt, info["pal"]))
    src = np.asarray(im)
    assert np.array_equal(back[..., 3] > 0, src[..., 3] > 0), "transparency changed"
    err = int(np.abs(back[..., :3].astype(int) - src[..., :3].astype(int))[src[..., 3] > 0].max(initial=0))
    assert err <= 8, f"palette error {err} beyond RGB5A3's 5 bits"
    return data


def quant_tpl(im, max_colors=256):
    """Background-like art: exact palette when it fits (CI4 up to 16 colors, else CI8)."""
    for maxc, fmt in ((16, T.CI4), (256, T.CI8)):
        q = T.quantize(im, maxc)
        if q:
            idx, pal = q
            return T.build([(idx, fmt, pal, im.size)])
    return T.build([(im, T.RGB5A3, None, im.size)])


# ------------------------------------------------------------- the story

def sample(variant):
    """Per actor, per frame: (cel, x, y, scale, alpha) or None, over the whole loop."""
    track = {a: [None] * FRAMES for a in ACTORS}
    for f in range(FRAMES):
        for name, x, y, clip, scale, alpha in S.story(f % S.PASSES[variant], variant):
            track[actor_of(name)][f] = (name, float(x), float(y), float(scale), float(alpha))
    return track


def canvas(celtab, names):
    """A common canvas holding every cel of a character at its offset from the actor's anchor."""
    x0 = min(celtab[n][1][0] for n in names)
    y0 = min(celtab[n][1][1] for n in names)
    x1 = max(celtab[n][1][0] + celtab[n][0].width for n in names)
    y1 = max(celtab[n][1][1] + celtab[n][0].height for n in names)
    w, h = ceil(x1 - x0, 8), ceil(y1 - y0, 8)
    return x0, y0, w, h


def hermite_at(f0, v0, m0, f1, v1, m1, f):
    h = f1 - f0
    t = (f - f0) / h
    return (v0 * (2 * t**3 - 3 * t**2 + 1) + v1 * (-2 * t**3 + 3 * t**2)
            + h * m0 * (t**3 - 2 * t**2 + t) + h * m1 * (t**3 - t**2))


def keys_linear(values, tol=0.3, corner=0.5):
    """Keyframes reproducing a per-frame value list within `tol`.

    A key's tangent shapes both segments that meet at it, so a corner (the slope changing by more than
    `corner` per frame, or a jump) is written the way Tantric's own files write one: two keys on the same
    frame, carrying the incoming and the outgoing slope. Between corners the curve is smooth, and keys are
    placed greedily as far apart as a cubic Hermite with the curve's own slopes still lands within `tol` of
    every frame, so a straight walk is two keys and an arc a handful.
    """
    n = len(values)
    v = values
    breaks = [0]
    for f in range(1, n - 1):
        if abs((v[f + 1] - v[f]) - (v[f] - v[f - 1])) > corner:
            breaks.append(f)
    breaks.append(n - 1)
    out = []
    for bi in range(len(breaks) - 1):
        a, b = breaks[bi], breaks[bi + 1]

        def slope(f):
            if f <= a:
                return v[a + 1] - v[a] if a + 1 <= b else 0.0
            if f >= b:
                return v[b] - v[b - 1] if b - 1 >= a else 0.0
            return (v[f + 1] - v[f - 1]) / 2.0

        f0 = a
        seg = [(a, v[a], slope(a))]
        while f0 < b:
            best = f0 + 1
            for f1 in range(f0 + 1, b + 1):
                m0, m1 = slope(f0), slope(f1)
                if all(abs(hermite_at(f0, v[f0], m0, f1, v[f1], m1, g) - v[g]) <= tol for g in range(f0 + 1, f1)):
                    best = f1
                else:
                    break
            seg.append((best, v[best], slope(best)))
            f0 = best
        if out and out[-1][0] == seg[0][0] and abs(out[-1][2] - seg[0][2]) < 1e-9:
            seg = seg[1:]
        out += seg
    return out


def anchor_values(trk, key, default):
    """A channel per frame, holding the last known value while the actor is off screen."""
    vals, last = [], default
    for s in trk:
        if s is not None:
            last = s[key]
        vals.append(last)
    return vals


# ------------------------------------------------------------- xml helpers

def triplets(keys):
    return "".join(
        f"\t\t\t\t\t\t\t<triplet>\n\t\t\t\t\t\t\t\t<frame>{f:.15f}</frame>\n"
        f"\t\t\t\t\t\t\t\t<value>{v:.15f}</value>\n\t\t\t\t\t\t\t\t<blend>{t:.15f}</blend>\n"
        f"\t\t\t\t\t\t\t</triplet>\n" for f, v, t in keys)


def entry(channel, body):
    return f'\t\t\t\t\t\t<entry type1="0" type2="{channel}">\n{body}\t\t\t\t\t\t</entry>\n'


def tag(kind, entries):
    return f'\t\t\t\t\t<tag type="{kind}">\n{"".join(entries)}\t\t\t\t\t</tag>\n'


def pane(name, kind, tags):
    return f'\t\t\t\t<pane name="{name}" type="{kind}">\n{"".join(tags)}\t\t\t\t</pane>\n'


def pairs(steps):
    return "".join(
        f"\t\t\t\t\t\t\t<pair>\n\t\t\t\t\t\t\t\t<data1>{f:.15f}</data1>\n"
        f"\t\t\t\t\t\t\t\t<data2>{i:04x}</data2>\n\t\t\t\t\t\t\t\t<padding>0000</padding>\n"
        f"\t\t\t\t\t\t\t</pair>\n" for f, i in steps)


def step_keys(values):
    """Keys for a value that only jumps (alpha on/off): two keys on the frame it changes."""
    out = [(0, values[0], 0.0)]
    for f in range(1, len(values)):
        if values[f] != values[f - 1]:
            out += [(f, values[f - 1], 0.0), (f, values[f], 0.0)]
    out.append((len(values) - 1, values[-1], 0.0))
    return out


# --------------------------------------------------------------- layout

TAGBLOCK = r'<tag type="(\w+)"((?:[^>]*[^/>])?)(?:>(.*?)</tag>|\s*/>)'


def pane_block(xml, name):
    """The text of a pane and its children (its pan1, the pas1..pae1 that follows)."""
    start = xml.index(f'<tag type="pan1" name="{name}"')
    start = xml.rindex("\n", 0, start) + 1
    i = xml.index('<tag type="pas1" />', start)
    depth, pos = 0, i
    for m in re.finditer(r'<tag type="(pas1|pae1)" />', xml[i:]):
        depth += 1 if m.group(1) == "pas1" else -1
        if depth == 0:
            end = i + m.end()
            end = xml.index("\n", end) + 1
            return start, end
    raise ValueError(name)


def set_field(block, field, value):
    return re.sub(rf"<{field}>[^<]*</{field}>", f"<{field}>{value}</{field}>", block, count=1)


def set_xy(block, group, x, y):
    return re.sub(
        rf"(<{group}>\s*<x>)[^<]*(</x>\s*<y>)[^<]*(</y>)",
        rf"\g<1>{x:.10f}\g<2>{y:.10f}\g<3>",
        block,
        count=1,
    )


def set_size(block, w, h):
    return re.sub(r"(<size>\s*<width>)[^<]*(</width>\s*<height>)[^<]*(</height>)",
                  rf"\g<1>{w:f}\g<2>{h:f}\g<3>", block, count=1)


def pic_block(xml, name):
    m = re.search(rf'\n\t*<tag type="pic1" name="{name}".*?</tag>\n', xml, re.S)
    return m.start() + 1, m.end()


def edit_layout(xml, geom, textures):
    """geom: {pic name: (size, translate)} and {pane name: translate}; textures: {material: texture}."""

    # move the logo right above the background, so the cast passes in front of it
    s, e = pane_block(xml, "Logo00Pane")
    logo = xml[s:e]
    xml = xml[:s] + xml[e:]
    bs, be = pic_block(xml, "BackgroundPic")
    xml = xml[:be] + logo + xml[be:]

    # a pane for the pipe mouths, on top of everything: a copy of the background picture with its own material
    bs, be = pic_block(xml, "BackgroundPic")
    pipes = xml[bs:be].replace('name="BackgroundPic"', 'name="PipesPic"').replace(
        '<material name="BackgroundMat"', '<material name="PipesMat"')
    root_end = xml.rindex('<tag type="pae1" />')
    root_end = xml.rindex("\n", 0, root_end) + 1
    xml = xml[:root_end] + pipes + xml[root_end:]
    m = re.search(r'\n\t*<entries name="BackgroundMat">.*?</entries>\n', xml, re.S)
    mat = m.group(0).replace('name="BackgroundMat"', 'name="PipesMat"')
    xml = xml[:m.end()] + mat[1:] + xml[m.end():]

    for name, (size, tr) in geom.items():
        if name.endswith("Pic"):
            s, e = pic_block(xml, name)
            blk = xml[s:e]
            blk = set_field(blk, "visible", "01")
            blk = set_field(blk, "alpha", "ff")
            if size:
                blk = set_size(blk, *size)
            blk = set_xy(blk, "translate", *tr)
            blk = set_xy(blk, "scale", 1.0, 1.0)
            blk = re.sub(
                r'<coord(TL|TR|BL|BR) s="[-\d.]+" t="[-\d.]+" />',
                lambda mm: '<coord%s s="%s" t="%s" />' % (
                    mm.group(1),
                    {"TL": "0.000000", "TR": "1.000000", "BL": "0.000000", "BR": "1.000000"}[mm.group(1)],
                    {"TL": "0.000000", "TR": "0.000000", "BL": "1.000000", "BR": "1.000000"}[mm.group(1)],
                ),
                blk,
            )
            xml = xml[:s] + blk + xml[e:]
        else:
            m = re.search(rf'\n\t*<tag type="pan1" name="{name}".*?</tag>\n', xml, re.S)
            blk = m.group(0)
            blk = set_field(blk, "visible", "01")
            blk = set_field(blk, "alpha", "ff")
            blk = set_xy(blk, "translate", *tr)
            xml = xml[:m.start()] + blk + xml[m.end():]

    # materials: our textures, clamped, identity texture matrix
    for matname, tex in textures.items():
        m = re.search(rf'<entries name="{matname}">(.*?)</entries>', xml, re.S)
        body = re.sub(r'<texture name="[^"]+">', f'<texture name="{tex}">', m.group(1), count=1)
        body = re.sub(r"<wrap_s>\w+</wrap_s>", "<wrap_s>GX_CLAMP</wrap_s>", body)
        body = re.sub(r"<wrap_t>\w+</wrap_t>", "<wrap_t>GX_CLAMP</wrap_t>", body)
        for fld, v in (("XTrans", 0), ("YTrans", 0), ("Rotate", 0), ("XScale", 1), ("YScale", 1)):
            body = re.sub(rf"<{fld}>[^<]*</{fld}>", f"<{fld}>{v:.10f}</{fld}>", body)
        xml = xml[:m.start(1)] + body + xml[m.end(1):]

    # the texture list names exactly what the materials rest on
    names = list(dict.fromkeys(textures.values()))
    xml = re.sub(r"(<tag type=\"txl1\">\s*<entries>).*?(\s*</entries>)",
                 lambda mm: mm.group(1) + "".join(f"\n\t\t\t\t\t<name>{n}</name>" for n in names) + mm.group(2),
                 xml, count=1, flags=re.S)
    return xml


# ---------------------------------------------------------------- build

def build(look, out_path=None):
    pipe_mode, logo_mode, variant = LOOKS[look]
    celtab = S.cels()
    track = sample(variant)
    files = {}
    textures = {}
    geom = {}
    anim_panes = []
    timg = []

    # background and pipes (static)
    bg = S.compose_stage(pipe_mode) if look != "grid" else S.compose_grid()
    files["Background.tpl"] = quant_tpl(bg.convert("RGBA"))
    textures["BackgroundMat"] = "Background.tpl"
    geom["BackgroundPic"] = ((S.W, S.H), (0.0, 0.0))
    pipes = S.pipes_overlay(pipe_mode).crop((0, S.PIPE_TOP, S.W, S.PIPE_TOP + 40))
    files["Pipes.tpl"] = quant_tpl(pipes)
    textures["PipesMat"] = "Pipes.tpl"
    geom["PipesPic"] = ((S.W, 40), (0.0, S.H / 2.0 - (S.PIPE_TOP + 20)))

    # logos: both in one 128x48 canvas size, since the flip swaps textures on one pane
    logos = []
    for im in (S.vb_logo(logo_mode), S.app_logo()):
        c = Image.new("RGBA", (128, 48))
        c.alpha_composite(im, ((128 - im.width) // 2, (48 - im.height) // 2))
        logos.append(c)
    files["Logo00.tpl"] = T.build([(logos[0], T.RGB5A3, None, logos[0].size)])
    files["Logo01.tpl"] = T.build([(logos[1], T.RGB5A3, None, logos[1].size)])
    textures["Logo00Mat"] = "Logo00.tpl"
    # low enough that the Menu tile's rounded frame keeps its top edge
    geom["Logo00Pane"] = (None, (0.0, S.H / 2.0 - 22))
    geom["Logo00Pic"] = ((128, 48), (0.0, 0.0))
    timg += ["Logo00.tpl", "Logo01.tpl"]
    flip = [(f, v, 0.0) for f, v in S.FLIP_SCALE]
    anim_panes.append(pane("Logo00Pic", 0, [tag("RLPA", [entry("X Scale", triplets(flip))])]))
    anim_panes.append(pane("Logo00Mat", 1, [tag("RLTP", [entry("PaletteZero", pairs(S.FLIP_SWAPS))])]))

    for actor, (donor, prefix, _) in ACTORS.items():
        trk = track[actor]
        used = sorted({s[0] for s in trk if s}, key=lambda n: [s[0] for s in trk if s].index(n))
        x0, y0, cw, ch = canvas(celtab, used)
        cels = []
        for n in used:
            im, (dx, dy) = celtab[n]
            c = Image.new("RGBA", (cw, ch))
            c.alpha_composite(im, (dx - x0, dy - y0))
            cels.append(c)
        pal = palette_of(cels)
        assert pal, f"{actor}: more than 15 colors"
        names = [f"{prefix}{i:02d}.tpl" for i in range(len(used))]
        for nm, c in zip(names, cels):
            files[nm] = ci_tpl(c, pal)
        base = len(timg)
        timg += names
        textures[f"{donor}Mat"] = names[0]

        # the picture sits where the canvas center is relative to the anchor (feet), the pane moves the anchor
        geom[f"{donor}Pic"] = ((cw, ch), (x0 + cw / 2.0, -(y0 + ch / 2.0)))

        xs = [v - S.W / 2.0 for v in anchor_values(trk, 1, 0.0)]
        ys = [S.H / 2.0 - v for v in anchor_values(trk, 2, 0.0)]
        sc = anchor_values(trk, 3, 1.0)
        al = [0.0 if s is None else round(255 * max(0.0, min(1.0, s[4]))) for s in trk]
        geom[f"{donor}Pane"] = (None, (xs[0], ys[0]))

        tags = [tag("RLPA", [entry("X Translation", triplets(keys_linear(xs))),
                             entry("Y Translation", triplets(keys_linear(ys))),
                             entry("X Scale", triplets(keys_linear(sc, tol=0.01, corner=0.02))),
                             entry("Y Scale", triplets(keys_linear(sc, tol=0.01, corner=0.02)))])]
        anim_panes.append(pane(f"{donor}Pane", 0, tags))
        anim_panes.append(
            pane(f"{donor}Pic", 0, [tag("RLVC", [entry("16", triplets(keys_linear(al, tol=2, corner=4)))])])
        )

        cel_at = [used.index(s[0]) if s else None for s in trk]
        steps, last = [], None
        for f, c in enumerate(cel_at):
            if c is not None and c != last:
                steps.append((f, base + c))
                last = c
        anim_panes.append(pane(f"{donor}Mat", 1, [tag("RLTP", [entry("PaletteZero", pairs(steps))])]))

    # layout and animation, from the donor
    w = WAD.load(DONOR)
    app = w.contents[0]
    meta = U8.load(app[app.find(b"\x55\xAA\x38\x2D"):])
    arc = U8.load(unpack_lz77_imd5(meta.get("meta/icon.bin")))

    lyt_xml = edit_layout(rip(arc.get("arc/blyt/icon.brlyt"), ".xmlyt"), geom, textures)
    an_xml = ('<?xml version="1.0" encoding="utf-8"?>\n\t\t<xmlan version="2.1.12BETA" brlan_version="0008">\n'
              f'\t\t\t<pai1 framesize="{FRAMES}" flags="01">\n'
              + "".join(f'\t\t\t\t<timg name="{n}" />\n' for n in timg)
              + "".join(anim_panes) + "\t\t\t</pai1>\n\t\t</xmlan>\n")

    lyt = make(lyt_xml, ".xmlyt")
    an = make(an_xml, ".xmlan")
    arc.replace("arc/blyt/icon.brlyt", lyt)
    arc.replace("arc/anim/icon.brlan", an)
    u8_set_dir_files(arc, "arc/timg", files)

    raw = arc.to_bytes()
    out = out_path or os.path.join(OUT, f"icon-{look}.bin")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    open(out, "wb").write(pack_lz77_imd5(raw))
    return out, len(raw), lyt_xml, an_xml


def make(xml, ext):
    src = f"_m{os.getpid()}" + ext
    dst = f"_m{os.getpid()}" + (".brlyt" if ext == ".xmlyt" else ".brlan")
    open(os.path.join(BENZIN, src), "w").write(xml)
    benzin("m", src, dst)
    data = open(os.path.join(BENZIN, dst), "rb").read()
    os.remove(os.path.join(BENZIN, src))
    os.remove(os.path.join(BENZIN, dst))
    return data


if __name__ == "__main__":
    for look in (sys.argv[1:] or LOOKS):
        path, size, _, _ = build(look)
        print(f"  {look}: {os.path.basename(path)}  {size:,} bytes uncompressed ({size / 102400:.0%} of the cap)")
