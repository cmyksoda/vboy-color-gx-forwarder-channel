"""Build banner.bin: one of the banner proposals on the mGBA GX banner's layout.

    build_banner.py <design> [out.bin]        design: paint | dawn

Derived from the mGBA GX channel's released banner (Tantric's Snes9x GX banner underneath). Its panes keep
their names and roles: the background, the two-copy character conveyor (CharacterPaneA/B), the stripe band,
the bars, the controller, the logo and the title tab with its text. New panes are added for what Tantric's
banner doesn't have: the back row (its own two-copy conveyor, drawn behind the front row) and each design's
effect layers. Every moving part comes from banner_model.py, the same model the mockups draw.
"""

import colorsys
import functools
import math
import os
import re
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(__file__))

import banner_model as M
import banner_scene as BS
import build_splash as SP
import tpl as T
from build_icon import (ci_tpl, keys_linear, make, pairs, palette_of, pane as apane, pic_block, quant_tpl,
                        set_field, set_size, set_xy, tag, triplets, entry)
from render import rip, set_mag_nearest
from tex import ci8_sprite_tpl
from vbcgx import OUT, ROOT
from wiilib import U8, WAD, pack_lz77_imd5, u8_set_dir_files, unpack_lz77_imd5

DONOR = os.path.join(ROOT, "donor", "mGBA-GX - GBGX [cmyksoda].wad")
W, H = M.W, M.H
FRONT_SLOTS = [("Fawful01", 0), ("Samus01", 1), ("AWars01", 2), ("Lucas01", 3)]     # donor pane -> M.FRONT index
BLACK, GRID_RED, RED, DEEP_RED, LOWER_RED = BS.BLACK, BS.GRID_RED, BS.RED, BS.DEEP_RED, BS.LOWER_RED


def px(x, y):
    """Banner pixel (top-left origin) -> pane coordinates (center origin, +y up)."""
    return x - W / 2.0, H / 2.0 - y


def ceil(n, a):
    return (n + a - 1) // a * a


# ------------------------------------------------------------- xml blocks

def pic_xml(name, mat, size, tr, vtx=None, uv=None, alpha="ff", scale=(1.0, 1.0), rot=0.0):
    vtx = vtx or [(255, 255, 255, 255)] * 4
    uv = uv or [(0, 0), (1, 0), (0, 1), (1, 1)]
    c = "".join(f'\t\t\t\t\t<vtxColor{k} r="{r:02x}" g="{g:02x}" b="{b:02x}" a="{a:02x}" />\n'
                for k, (r, g, b, a) in zip(("TL", "TR", "BL", "BR"), vtx))
    u = "".join(
        f'\t\t\t\t\t\t<coord{k} s="{s:.6f}" t="{t:.6f}" />\n'
        for k, (s, t) in zip(("TL", "TR", "BL", "BR"), uv)
    )
    return (f'\t\t\t<tag type="pic1" name="{name}" userdata="">\n\t\t\t\t<visible>01</visible>\n'
            f'\t\t\t\t<WidescreenAffected>00</WidescreenAffected>\n\t\t\t\t<flag>00</flag>\n'
            f'\t\t\t\t<origin x="Center" y="Center" />\n\t\t\t\t<alpha>{alpha}</alpha>\n\t\t\t\t<padding>00</padding>\n'
            f'\t\t\t\t<translate>\n\t\t\t\t\t<x>{tr[0]:.10f}</x>\n\t\t\t\t\t<y>{tr[1]:.10f}</y>\n'
            f'\t\t\t\t\t<z>0.0000000000</z>\n\t\t\t\t</translate>\n'
            f'\t\t\t\t<rotate>\n\t\t\t\t\t<x>0.00000000000000000000</x>\n\t\t\t\t\t<y>0.00000000000000000000</y>\n'
            f'\t\t\t\t\t<z>{rot:.20f}</z>\n\t\t\t\t</rotate>\n'
            f'\t\t\t\t<scale>\n\t\t\t\t\t<x>{scale[0]:.10f}</x>\n\t\t\t\t\t<y>{scale[1]:.10f}</y>\n\t\t\t\t</scale>\n'
            f'\t\t\t\t<size>\n\t\t\t\t\t<width>{size[0]:f}</width>\n'
            f'\t\t\t\t\t<height>{size[1]:f}</height>\n\t\t\t\t</size>\n'
            f'\t\t\t\t<material name="{mat}" />\n\t\t\t\t<colors>\n{c}\t\t\t\t</colors>\n'
            f'\t\t\t\t<coordinates>\n\t\t\t\t\t<set>\n{u}\t\t\t\t\t</set>\n\t\t\t\t</coordinates>\n\t\t\t</tag>\n')


def pan_xml(name, tr=(0.0, 0.0)):
    """A group pane. Benzin's <flag> is the Wii's location-adjust bit and <WidescreenAffected> is alpha
    inheritance: our groups live under CharacterPaneBase (already adjusted) and pass their alpha down."""
    return (f'\t\t\t<tag type="pan1" name="{name}" userdata="">\n\t\t\t\t<visible>01</visible>\n'
            f'\t\t\t\t<WidescreenAffected>01</WidescreenAffected>\n\t\t\t\t<flag>00</flag>\n'
            f'\t\t\t\t<origin x="Center" y="Center" />\n\t\t\t\t<alpha>ff</alpha>\n\t\t\t\t<padding>00</padding>\n'
            f'\t\t\t\t<translate>\n\t\t\t\t\t<x>{tr[0]:.10f}</x>\n\t\t\t\t\t<y>{tr[1]:.10f}</y>\n'
            f'\t\t\t\t\t<z>0.0000000000</z>\n\t\t\t\t</translate>\n'
            f'\t\t\t\t<rotate>\n\t\t\t\t\t<x>0.00000000000000000000</x>\n\t\t\t\t\t<y>0.00000000000000000000</y>\n'
            f'\t\t\t\t\t<z>0.00000000000000000000</z>\n\t\t\t\t</rotate>\n'
            f'\t\t\t\t<scale>\n\t\t\t\t\t<x>1.0000000000</x>\n\t\t\t\t\t<y>1.0000000000</y>\n\t\t\t\t</scale>\n'
            f'\t\t\t\t<size>\n\t\t\t\t\t<width>30.000000</width>\n\t\t\t\t\t<height>40.000000</height>\n'
            f'\t\t\t\t</size>\n\t\t\t</tag>\n')


def group_xml(name, children, tr=(0.0, 0.0)):
    return pan_xml(name, tr) + '\t\t\t<tag type="pas1" />\n' + "".join(children) + '\t\t\t<tag type="pae1" />\n'


def mat_xml(template, name, texture, wrap=("GX_CLAMP", "GX_CLAMP"), fore=(0, 0, 0, 0), back=(255, 255, 255, 255)):
    blk = template.replace(re.search(r'<entries name="([^"]+)">', template).group(0), f'<entries name="{name}">')
    blk = re.sub(
        r'<forecolor r="\d+" g="\d+" b="\d+" a="\d+" />', '<forecolor r="%d" g="%d" b="%d" a="%d" />' % fore, blk
    )
    blk = re.sub(
        r'<backcolor r="\d+" g="\d+" b="\d+" a="\d+" />', '<backcolor r="%d" g="%d" b="%d" a="%d" />' % back, blk
    )
    blk = re.sub(r'<texture name="[^"]+">', f'<texture name="{texture}">', blk)
    blk = re.sub(r"<wrap_s>\w+</wrap_s>", f"<wrap_s>{wrap[0]}</wrap_s>", blk)
    blk = re.sub(r"<wrap_t>\w+</wrap_t>", f"<wrap_t>{wrap[1]}</wrap_t>", blk)
    for fld, v in (("XTrans", 0), ("YTrans", 0), ("Rotate", 0), ("XScale", 1), ("YScale", 1)):
        blk = re.sub(rf"<{fld}>[^<]*</{fld}>", f"<{fld}>{v:.10f}</{fld}>", blk)
    return blk


def material_block(xml, name):
    m = re.search(rf'\n\t*<entries name="{name}">.*?</entries>\n', xml, re.S)
    return m.group(0)[1:]


def edit_material(xml, name, **kw):
    blk = material_block(xml, name)
    return xml.replace(blk, mat_xml(blk, name, kw.pop("texture"), **kw))


def edit_pic(xml, name, size=None, tr=None, rot=None, uv=None, alpha="ff"):
    s, e = pic_block(xml, name)
    blk = set_field(set_field(xml[s:e], "visible", "01"), "alpha", alpha)
    if size:
        blk = set_size(blk, *size)
    if tr is not None:
        blk = set_xy(blk, "translate", *tr)
    if rot is not None:
        blk = re.sub(r"(<rotate>.*?<z>)[^<]*(</z>)", rf"\g<1>{rot:.20f}\g<2>", blk, flags=re.S)
    uv = uv or [(0, 0), (1, 0), (0, 1), (1, 1)]
    for k, (u, v) in zip(("TL", "TR", "BL", "BR"), uv):
        blk = re.sub(rf'<coord{k} s="[-\d.]+" t="[-\d.]+" />', f'<coord{k} s="{u:.6f}" t="{v:.6f}" />', blk)
    return xml[:s] + blk + xml[e:]


def edit_pan(xml, name, tr=None, rot=None, flag=None):
    m = re.search(rf'\n\t*<tag type="pan1" name="{name}".*?</tag>\n', xml, re.S)
    blk = set_field(set_field(m.group(0), "visible", "01"), "alpha", "ff")
    if tr is not None:
        blk = set_xy(blk, "translate", *tr)
    if rot is not None:
        blk = re.sub(r"(<rotate>.*?<z>)[^<]*(</z>)", rf"\g<1>{rot:.20f}\g<2>", blk, flags=re.S)
    if flag is not None:
        blk = set_field(blk, "flag", flag)
    return xml[:m.start()] + blk + xml[m.end():]


def insert_into(xml, parent, block):
    """Insert panes as the first children of a group pane (right after its pas1)."""
    i = xml.index(f'<tag type="pan1" name="{parent}"')
    j = xml.index('<tag type="pas1" />', i)
    j = xml.index("\n", j) + 1
    return xml[:j] + block + xml[j:]


def insert_materials(xml, blocks):
    i = xml.index("</tag>", xml.index('<tag type="mat1">'))
    i = xml.rindex("\n", 0, i) + 1
    return xml[:i] + "".join(blocks) + xml[i:]


def set_txl(xml, names):
    return re.sub(r"(<tag type=\"txl1\">\s*<entries>).*?(\s*</entries>)",
                  lambda mm: mm.group(1) + "".join(f"\n\t\t\t\t\t<name>{n}</name>" for n in names) + mm.group(2),
                  xml, count=1, flags=re.S)


# --------------------------------------------------------------- textures

def grid_texture(cell, width, name):
    """One grid cell: line texels white and opaque, the rest transparent (the material tints it)."""
    im = Image.new("RGBA", (cell, cell), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, width - 1, cell - 1), fill=(255, 255, 255, 255))
    d.rectangle((0, 0, cell - 1, width - 1), fill=(255, 255, 255, 255))
    return name, T.build([(im, T.RGB5A3, None, im.size)])


def single_color(canv):
    """The one exact color of a walker drawn in a single color (an invader row), else None."""
    cols = set()
    for c in canv:
        a = np.asarray(c)
        cols |= {tuple(int(v) for v in p) for p in a[a[..., 3] > 0][:, :3]}
    return cols.pop() if len(cols) == 1 else None


def mask_tpl(c):
    """A white mask of a single-color sprite; its material's back color paints it in the exact 8-bit color."""
    a = np.asarray(c).copy()
    on = a[..., 3] > 0
    a[on] = (255, 255, 255, 255)
    a[~on] = 0
    return T.build([(Image.fromarray(a, "RGBA"), T.RGB5A3, None, c.size)])


def replace_children(xml, parent, block):
    """Replace a group pane's children (everything between its pas1 and the matching pae1)."""
    i = xml.index(f'<tag type="pan1" name="{parent}"')
    j = xml.index("\n", xml.index('<tag type="pas1" />', i)) + 1
    depth, k = 1, j
    for m in re.finditer(r'<tag type="(pas1|pae1)" />', xml[j:]):
        depth += 1 if m.group(1) == "pas1" else -1
        if depth == 0:
            k = xml.rindex("\n", 0, j + m.start()) + 1
            break
    return xml[:j] + block + xml[k:]


# ------------------------------------------------------------- animation

def per_frame(fn, start):
    """fn(f) over the Start (frames 0..999) or the Loop (timeline frames 1000..2999, keyed 0..1999)."""
    rng = range(0, M.START) if start else range(M.START, M.START + M.LOOP)
    return [fn(f) for f in rng]


def rlpa(name, chans, start):
    entries = [entry(ch, triplets(keys_linear(per_frame(fn, start), **kw))) for ch, fn, kw in chans]
    return apane(name, 0, [tag("RLPA", entries)])


def rlvc_alpha(name, fn, start):
    return apane(name, 0, [tag("RLVC", [entry("16", triplets(keys_linear(per_frame(fn, start), tol=2, corner=4)))])])


def rltp(mat, fn, start):
    vals = per_frame(fn, start)
    steps, last = [], None
    for f, v in enumerate(vals):
        if v != last:
            steps.append((f, v))
            last = v
    return apane(mat, 1, [tag("RLTP", [entry("PaletteZero", pairs(steps))])])


def rlts_x(mat, fn, start):
    return apane(mat, 1, [
        tag("RLTS", [entry("XTrans", triplets(keys_linear(per_frame(fn, start), tol=0.002, corner=0.01)))])
    ])


def merge_panes(blocks):
    """One animation block per pane: tags written separately for the same pane are gathered into it, since
    the Menu binds a block per name and a second block of the same name may not apply."""
    order, tags = [], {}
    for blk in blocks:
        m = re.match(r'\t*<pane name="([^"]+)" type="(\d)">\n(.*)\t*</pane>\n', blk, re.S)
        key = (m.group(1), m.group(2))
        if key not in tags:
            order.append(key)
            tags[key] = []
        tags[key].append(m.group(3))
    return [f'\t\t\t\t<pane name="{n}" type="{k}">\n' + "".join(tags[(n, k)]) + '\t\t\t\t</pane>\n' for n, k in order]


def brlan_xml(timg, panes, frames):
    panes = merge_panes(panes)
    return ('<?xml version="1.0" encoding="utf-8"?>\n\t\t<xmlan version="2.1.12BETA" brlan_version="0008">\n'
            f'\t\t\t<pai1 framesize="{frames}" flags="01">\n'
            + "".join(f'\t\t\t\t<timg name="{n}" />\n' for n in timg) + "".join(panes)
            + "\t\t\t</pai1>\n\t\t</xmlan>\n")


# ------------------------------------------------------------------ build

def build(design, out_path=None):
    cels = BS.walker_cels()
    files, timg, mats_new = {}, [], []
    w = WAD.load(DONOR)
    app = w.contents[0]
    meta = U8.load(app[app.find(b"\x55\xAA\x38\x2D"):])
    arc = U8.load(unpack_lz77_imd5(meta.get("meta/banner.bin")))
    xml = rip(arc.get("arc/blyt/banner.brlyt"), ".xmlyt")
    tmpl_mat = material_block(xml, "Fawful01MaterialA")
    anim = {True: [], False: []}                  # Start, Loop

    # ---- the parade on Tantric's own conveyor and slots. Every walker and every invader has its own picture
    # and material in each copy, since the Menu gives a material's animation to only one pane.
    # walkers keep their exact 8-bit colors at 1x; a walker drawn bigger gets a picture exactly its scale times
    # the texture and asks for nearest-neighbor filtering, in the layout and in the texture's own header
    tex_of, cels1, nearest = {}, BS.walker_cels(scaled=False), []
    for w_ in M.FRONT:
        for n in dict.fromkeys(w_.cycle):
            im = cels1[n]
            cv = Image.new("RGBA", (ceil(im.width, 4), ceil(im.height, 4)))
            cv.alpha_composite(im, ((cv.width - im.width) // 2, cv.height - im.height))
            tn = f"{n.replace('-', '').capitalize()}.tpl"
            filt = (0, 0) if w_.scale > 1 else (1, 1)       # nearest in the texture's own header too
            if w_.scale == int(w_.scale):
                files[tn] = T.build([(cv, T.RGBA8, None, cv.size, filt)])
                tex_of[n] = (tn, (cv.width * w_.scale, cv.height * w_.scale))
            else:
                # drawn at its scale ahead of time (Ballom's hand-drawn eyes), shown 1:1 in its own few colors
                big = BS.ballom_15(im)
                cvb = Image.new("RGBA", (ceil(big.width, 8), ceil(big.height, 8)))
                cvb.alpha_composite(big, ((cvb.width - big.width) // 2, cvb.height - big.height))
                idx, pal = T.quantize(cvb, 16)
                files[tn] = T.build([(idx, T.CI4, pal, cvb.size, filt)])
                tex_of[n] = (tn, cvb.size)
            timg.append(tn)
    inv_tex, inv_color = {}, {}
    for kind in dict.fromkeys(i.kind for i in M.INVADERS):
        for k in (0, 1):
            im = cels[f"{kind}{k}"]
            hop = INVADER_HOP if INVADER_STEPS else 0       # the option: the second frame stands a step forward
            cv = Image.new("RGBA", (ceil(im.width + hop, 4), ceil(im.height, 4)))
            cv.alpha_composite(im, (hop * k, 0))
            inv_color[kind] = single_color([cv])
            tn = f"{kind.replace('-', '').capitalize()}{k}.tpl"
            files[tn] = mask_tpl(cv)
            inv_tex[(kind, k)] = (tn, cv.size)
            timg.append(tn)

    form_w = (M.FORM_COLS - 1) * M.FORM_PITCH + 12
    form_h = (len(M.FORM_ROWS) - 1) * M.FORM_PITCH + 8

    xml = edit_pan(xml, "CharacterPaneBase", tr=(0.0, 0.0), flag="01")
    for c, grp in ((0, "CharacterPaneA"), (1, "CharacterPaneB")):
        xml = edit_pan(xml, grp, tr=(M.copy_x(0, c), 0.0), flag="00")
        kids = []
        for i, w_ in enumerate(M.FRONT):
            matn, picn = f"Walk{i}Mat{'AB'[c]}", f"Walk{i}Pic{'AB'[c]}"
            tn, size = tex_of[w_.cycle[0]]
            if w_.scale > 1:
                nearest.append(matn)
            mats_new.append(mat_xml(tmpl_mat, matn, tn))
            if w_.moves:
                low = round(max(dy for _, dy in w_.offsets) * w_.scale)
                base = (w_.slot, H / 2.0 - (M.FRONT_FEET - w_.float_up - low) + size[1] / 2.0)
            else:
                base = (w_.slot, H / 2.0 - M.FRONT_FEET + size[1] / 2.0)
            kids.append(pic_xml(picn, matn, size, base))
            for start in (True, False):
                anim[start].append(rltp(matn, lambda f, w_=w_: timg.index(tex_of[w_.cel(f)][0]), start))
                if w_.moves:
                    anim[start].append(rlpa(picn, [
                        ("X Translation", lambda f, w_=w_, b=base: b[0] + w_.offset(f)[0],
                         dict(tol=0.01, corner=0.5)),
                        ("Y Translation", lambda f, w_=w_, b=base: b[1] - w_.offset(f)[1],
                         dict(tol=0.01, corner=0.5)),
                    ], start))
        left, top = M.INVADER_SLOT - form_w, M.FRONT_FEET - 2 * form_h
        for inv in M.INVADERS:
            matn, picn = f"Inv{inv.k:02d}Mat{'AB'[c]}", f"Inv{inv.k:02d}Pic{'AB'[c]}"
            tn, size = inv_tex[(inv.kind, 0)]
            mats_new.append(mat_xml(tmpl_mat, matn, tn, back=inv_color[inv.kind] + (255,)))
            x0 = left + M.FORM_SCALE * M.FORM_PITCH * inv.col
            y0 = top + M.FORM_SCALE * M.FORM_PITCH * inv.row
            base = (x0 + size[0] / 2.0, H / 2.0 - y0 - size[1] / 2.0)
            kids.append(pic_xml(picn, matn, size, base))
            for start in (True, False):
                anim[start].append(rltp(matn, lambda f, inv=inv: timg.index(inv_tex[(inv.kind, inv.cel(f))][0]), start))
        xml = replace_children(xml, grp, "".join(kids))
        for start in (True, False):
            anim[start].append(rlpa(grp, [("X Translation", lambda f, c=c: M.copy_x(f, c), {})], start))
            anim[start].append(rlvc_alpha(grp, lambda f, c=c: 255 if M.copy_visible(f, c) else 0, start))

    for donor, _ in FRONT_SLOTS:
        for k in "AB":
            xml = xml.replace(material_block(xml, f"{donor}Material{k}"), "")
    under_base = ""

    # ---- background and the design's own layers
    effect_blocks = design_layers(design, xml, tmpl_mat, files, timg, mats_new, anim)
    xml = edit_pic(xml, "BackgroundPicture", size=(W, H), tr=(0.0, 0.0), uv=effect_blocks.get("bg_uv"))
    xml = edit_material(xml, "BackgroundMaterial", texture=effect_blocks["bg_tex"], wrap=effect_blocks["bg_wrap"],
                        fore=effect_blocks["bg_fore"], back=effect_blocks["bg_back"])

    # everything that moves with the parade sits under CharacterPaneBase, so it shares the walkers' 16:9
    # treatment and stays on the background grid in both modes
    xml = insert_into(xml, "CharacterPaneBase", "".join(effect_blocks["blocks"]) + under_base)

    # ---- chrome: stripe band, bars, controller, logo, title tab
    band = Image.new("RGBA", (8, 28))
    bd = ImageDraw.Draw(band)
    for y0, y1, col in [(0, 10, RED), (10, 12, BLACK), (12, 24, LOWER_RED), (24, 28, BLACK)]:
        bd.rectangle((0, y0, 7, y1 - 1), fill=col + (255,))
    files["Stripe.tpl"] = T.build([(band, T.RGBA8, None, band.size)])      # the app's exact reds
    xml = edit_pic(xml, "StripePicture", size=(W, 28), tr=px(W / 2.0, 194 + 14))
    xml = edit_material(xml, "StripeMaterial", texture="Stripe.tpl")

    bars = Image.new("RGBA", (8, 12))
    ImageDraw.Draw(bars).rectangle((0, 0, 7, 2), fill=(255, 255, 255, 255))
    ImageDraw.Draw(bars).rectangle((0, 7, 7, 9), fill=(255, 255, 255, 255))
    files["Bars.tpl"] = T.build([(bars, T.RGB5A3, None, bars.size)])
    xml = edit_pic(xml, "BarsPicture", size=(8, 12), tr=px(W / 2.0, 330 + 5))
    xml = edit_material(xml, "BarsMaterial", texture="Bars.tpl", fore=(0, 0, 0, 0), back=RED + (255 if BARS else 0,))

    cc = Image.open(CONTROLLER).convert("RGBA")
    files["Controller.tpl"], _ = ci8_sprite_tpl(cc)
    xml = edit_pan(xml, "ControllerPane", tr=px(*CONTROLLER_AT), rot=8.0, flag="01")
    xml = edit_pic(xml, "ControllerPicture", size=cc.size, tr=(0.0, 0.0))
    xml = edit_material(xml, "ControllerMaterial", texture="Controller.tpl")

    logo = SP.logo(LOGO_SCALE)
    lc = Image.new("RGBA", (ceil(logo.width, 8), ceil(logo.height, 4)))
    lc.alpha_composite(logo, ((lc.width - logo.width) // 2, (lc.height - logo.height) // 2))
    files["Logo.tpl"], _ = ci8_sprite_tpl(lc)
    xml = edit_pan(xml, "LogoPane", tr=px(*LOGO_AT), flag="01")
    xml = edit_pic(xml, "LogoPicture", size=lc.size, tr=(0.0, 0.0))
    xml = edit_material(xml, "LogoMaterial", texture="Logo.tpl")
    files["TitleBar.tpl"] = arc.get("arc/timg/TitleBar.tpl")
    blk = material_block(xml, "TitleBarMaterial")
    tab = re.sub(
        r'<backcolor r="\d+" g="\d+" b="\d+" a="\d+" />', '<backcolor r="%d" g="%d" b="%d" a="255" />' % DEEP_RED, blk
    )
    tab = re.sub(
        r'<forecolor r="\d+" g="\d+" b="\d+" a="(\d+)" />',
        lambda m: '<forecolor r="%d" g="%d" b="%d" a="%s" />' % (BLACK + (m.group(1),)),
        tab,
    )
    xml = xml.replace(blk, tab)
    text = "VBoy Color GX".encode("utf-16-be").hex().ljust(96, "0")
    xml = re.sub(r"<text>[0-9a-f]*</text>", f"<text>{text}</text>", xml, count=1)

    # ---- Tantric's own entrances, as the mGBA GX banner keeps them: the title tab drops in, the controller
    # pops up and then rocks, the logo flies in from the right, squashes as it lands and bobs from then on
    def keys(pts):
        return triplets([(f, v, t) for f, v, t in pts])
    rock = [(-125, 10, 0), (125, -10, 0), (375, 10, 0), (625, -10, 0), (875, 10, 0), (1125, -10, 0)]
    rock_loop = [(f, v, t) for f, v, t in rock] + [(1375, 10, 0), (1625, -10, 0), (1875, 10, 0), (2125, -10, 0)]
    bob = [(f, 15 if (f // 125) % 2 else 0, 0) for f in range(0, 1001, 125)]
    bob_loop = [(f, 15 if (f // 125) % 2 else 0, 0) for f in range(0, 2001, 125)]

    anim[True] += [
        apane("TitlePane", 0, [tag("RLPA", [entry("Y Translation", keys([(0, 100, 0), (40, 0, 0)]))])]),
        apane("ControllerPicture", 0, [tag("RLPA", [
            entry("X Scale", keys([(0, 0, 0), (30, 1.2, 0), (35, 1, 0)])),
            entry("Y Scale", keys([(0, 0, 0), (30, 1.2, 0), (35, 1, 0)])),
            entry("Z Rotate", keys(rock)),
        ])]),
        apane("LogoPicture", 0, [tag("RLPA", [
            entry("X Translation", keys([(0, 1024, 0), (60, 0, 0)])),
            entry("X Scale", keys([(0, 1, 0), (59, 1, 0), (66, 0.7, 0), (69, 1, 0)])),
            entry("Y Scale", keys([(0, 1, 0), (59, 1, 0), (66, 1.2, 0), (69, 1, 0)])),
            entry("Y Translation", keys(bob)),
        ])]),
    ]
    anim[False] += [
        apane("ControllerPicture", 0, [tag("RLPA", [entry("Z Rotate", keys(rock_loop))])]),
        apane("LogoPicture", 0, [tag("RLPA", [entry("Y Translation", keys(bob_loop))])]),
    ]

    # ---- finish
    xml = insert_materials(xml, mats_new)
    txl = [effect_blocks["bg_tex"]]
    for tn in [
        re.search(r'<texture name="([^"]+)"', b).group(1)
        for b in re.findall(r'<entries name="[^"]+">.*?</entries>', xml, re.S)
        if "<texture" in b
    ]:
        if tn not in txl:
            txl.append(tn)
    xml = set_txl(xml, txl)
    for t in txl:
        if t not in timg:
            timg.append(t)
    assert all(t in files for t in timg), [t for t in timg if t not in files]

    lyt = set_mag_nearest(make(xml, ".xmlyt"), nearest)
    start = make(brlan_xml(timg, anim[True], M.START), ".xmlan")
    loop = make(brlan_xml(timg, anim[False], M.LOOP), ".xmlan")
    arc.replace("arc/blyt/banner.brlyt", lyt)
    arc.replace("arc/anim/banner_Start.brlan", start)
    arc.replace("arc/anim/banner_Loop.brlan", loop)
    u8_set_dir_files(arc, "arc/timg", files)

    raw = arc.to_bytes()
    out = out_path or os.path.join(OUT, f"banner-{design}.bin")
    open(out, "wb").write(pack_lz77_imd5(raw))
    return out, len(raw)


# -------------------------------------------------------- design layers

def design_layers(design, xml, tmpl_mat, files, timg, mats_new, anim):
    if design == "paint":
        return paint_layers(tmpl_mat, files, mats_new, anim)
    return dawn_layers(tmpl_mat, files, mats_new, anim)


def grid_background(cell, width, files):
    name, data = grid_texture(cell, width, "Grid.tpl")
    files[name] = data
    return dict(bg_tex=name, bg_wrap=("GX_REPEAT", "GX_REPEAT"), bg_fore=BLACK + (255,), bg_back=GRID_RED + (255,),
                bg_uv=[(0, 0), (W / cell, 0), (0, H / cell), (W / cell, H / cell)])


def glow_grid_texture(cell, name):
    """A grid cell for the wake: the 2-px line fully lit and a 1-px glow either side, so the colored lines read
    wider than the red ones they cover."""
    a = np.zeros((cell, cell, 4), np.uint8)
    a[..., :3] = 255
    for k, alpha in ((0, 255), (1, 255), (2, 130), (cell - 1, 130)):
        a[:, k, 3] = np.maximum(a[:, k, 3], alpha)
        a[k, :, 3] = np.maximum(a[k, :, 3], alpha)
    return name, T.build([(Image.fromarray(a, "RGBA"), T.RGB5A3, None, (cell, cell))])


# the game's march step, as a hop and back with each frame switch (Jaxi, 28 Oct)
INVADER_STEPS = True
INVADER_HOP = 2 * M.FORM_SCALE                      # the game's 2-pixel step, at the block's 2x
CONTROLLER = os.path.join(ROOT, "banner", "vbcontroller-148.png")   # the vector controller, 148 px wide (Jaxi's pick)
BARS = False                                        # the two red lines under the controller and logo (off: her pick)
CONTROLLER_AT = (230, 248)                          # where the mGBA GX banner keeps its picture (Jaxi's pick)
LOGO_SCALE, LOGO_AT = 1.5, (500, 270)               # the logo rebuilt from the master at 1.5x the app's (her pick)


RAINBOW_PERIOD, RAINBOW_STRIPS = 1024, 32          # one full spectrum per copy, one grid cell per strip
LEAD_HUE = 5 / 6                                   # magenta, right behind the leader
# in the opening, the rainbow fades to clear over this many px up to Wario's front
FRONT_FADE = 96
RAINBOW_A_FROM = 500                               # copy A's rainbow shows once it has jumped in behind copy B


LEAD_ALPHA = 0.1                                   # the rainbow counts as visible from this strength
LEAD_AHEAD = 40                                    # pixels the rainbow's front runs ahead of Wario (her pick)
EDGE_43, EDGE_169 = -304, -418                     # the screen's left edge in the parade's own pixels


@functools.lru_cache(maxsize=None)
def _wario_fronts():
    """Wario's frontmost pixel per cel, relative to his slot center, as the archive draws him."""
    w = M.FRONT[0]
    cels1 = BS.walker_cels(scaled=False)
    out = {}
    for n in dict.fromkeys(w.cycle):
        im = cels1[n]
        cw = ceil(im.width, 4)
        cols = np.nonzero((np.asarray(im)[..., 3] > 0).any(axis=0))[0]
        out[n] = ((cw - im.width) // 2 + int(cols.max()) + 1 - cw / 2.0) * w.scale
    return out


def wario_front(f):
    """The leader's frontmost pixel at Start frame f, with the cel showing then, relative to his copy's x."""
    w = M.FRONT[0]
    return w.slot + _wario_fronts()[w.cel(f)]


def first_frame(offset, edge):
    """The first Start frame copy B is visible with a point `offset(f)` ahead of its x past the screen edge."""
    return next(f for f in range(M.START) if M.copy_visible(f, 1) and M.copy_x(f, 1) + offset(f) > edge)


def lead_x():
    """The rainbow's clear point, the front of its fade: placed so its first visible color crosses the 4:3 screen
    edge on the very frame Wario's first pixel does (in 16:9 both appear with copy B itself), plus LEAD_AHEAD."""
    f = first_frame(wario_front, EDGE_43)
    lo, hi = EDGE_43 - M.copy_x(f, 1), EDGE_43 - M.copy_x(f - 1, 1)
    return (lo + hi) / 2 + LEAD_ALPHA * FRONT_FADE + LEAD_AHEAD


def rainbow_hue(t):
    """The spectrum evenly, as an RGB color for t in [0, 1)."""
    r, g, b = colorsys.hsv_to_rgb(t % 1.0, 0.8, 0.92)
    return (round(r * 255), round(g * 255), round(b * 255))


def rainbow_group_visible(f, c):
    """Copy B's rainbow appears with copy B's walkers; copy A's once it has jumped in behind copy B."""
    start, t = M.local(f)
    return not start or t >= (M.SHOW_FROM[1] if c == 1 else RAINBOW_A_FROM)


def rainbow_strip_visible(f, c, ahead):
    """In the Start, the grid ahead of the leading Wario (copy B's) stays red; after that, everything is behind
    a Wario, so every strip shows."""
    start, t = M.local(f)
    return rainbow_group_visible(f, c) and not (start and c == 1 and ahead)


def paint_layers(tmpl_mat, files, mats_new, anim):
    """The grid lights up in a rainbow that starts at Wario: its front edge rides at his frontmost pixel with
    magenta right behind him, and the spectrum trails back through the parade, so the first colored pixel shows
    on the frame his first pixel does. Once he has crossed, the whole grid stays rainbow. Each copy of the
    conveyor carries one full spectrum, so it loops seamlessly; each strip's texture scrolls against the
    conveyor so its lines sit on the background grid's, and each strip has its own material, since the Menu
    animates a material on one pane only."""
    out = grid_background(32, 2, files)
    name, data = glow_grid_texture(32, "GridGlow.tpl")
    files[name] = data
    blocks = []
    lead = lead_x()
    half = RAINBOW_PERIOD // 2
    edges = sorted(set(range(-half, half + 1, RAINBOW_PERIOD // RAINBOW_STRIPS)) | {lead, lead - FRONT_FADE})
    hue_at = lambda x: rainbow_hue(LEAD_HUE + (x - lead) / RAINBOW_PERIOD)
    for c in (0, 1):
        kids = []
        for i, (x0, x1) in enumerate(zip(edges, edges[1:])):
            c0, c1 = hue_at(x0), hue_at(x1)
            matn, picn = f"Rbw{i:02d}Mat{'AB'[c]}", f"Rbw{i:02d}Pic{'AB'[c]}"
            mats_new.append(mat_xml(tmpl_mat, matn, name, wrap=("GX_REPEAT", "GX_REPEAT")))
            vtx = [c0 + (255,), c1 + (255,), c0 + (255,), c1 + (255,)]
            uv = [(x0 / 32.0, 0), (x1 / 32.0, 0), (x0 / 32.0, H / 32.0), (x1 / 32.0, H / 32.0)]
            kids.append(pic_xml(picn, matn, (x1 - x0, H), ((x0 + x1) / 2.0, 0.0), vtx, uv))
            fading = c == 1 and lead - FRONT_FADE <= x0 < lead
            for start in (True, False):
                anim[start].append(rlts_x(matn, lambda f, c=c: (M.copy_x(f, c) + W / 2.0) / 32.0, start))
                if c == 1 and x0 >= lead:
                    anim[start].append(
                        rlvc_alpha(picn, lambda f: 255 if rainbow_strip_visible(f, 1, True) else 0, start)
                    )
                if fading:                               # in the opening its fading twin shows instead
                    anim[start].append(rlvc_alpha(picn, lambda f: 0 if M.local(f)[0] else 255, start))
            if fading:
                # the fading twin: full color FRONT_FADE px behind Wario's front, clear at his front, so the
                # rainbow blends into the red grid ahead of him and still starts with his first pixel
                fade = lambda x: round(255 * (lead - x) / FRONT_FADE)
                matn, picn = f"Rbw{i:02d}FMat", f"Rbw{i:02d}FPic"
                mats_new.append(mat_xml(tmpl_mat, matn, name, wrap=("GX_REPEAT", "GX_REPEAT")))
                vtx = [c0 + (fade(x0),), c1 + (fade(x1),), c0 + (fade(x0),), c1 + (fade(x1),)]
                kids.append(pic_xml(picn, matn, (x1 - x0, H), ((x0 + x1) / 2.0, 0.0), vtx, uv))
                for start in (True, False):
                    anim[start].append(rlts_x(matn, lambda f: (M.copy_x(f, 1) + W / 2.0) / 32.0, start))
                    anim[start].append(rlvc_alpha(picn, lambda f: 255 if M.local(f)[0] else 0, start))
        blocks.append(group_xml(f"RainbowPane{'AB'[c]}", kids, (M.copy_x(0, c), 0.0)))
        for start in (True, False):
            anim[start].append(
                rlpa(f"RainbowPane{'AB'[c]}", [("X Translation", lambda f, c=c: M.copy_x(f, c), {})], start)
            )
            anim[start].append(rlvc_alpha(
                f"RainbowPane{'AB'[c]}", lambda f, c=c: 255 if rainbow_group_visible(f, c) else 0, start
            ))
    out["blocks"] = blocks
    return out


HORIZON = BS.HORIZON
FLOOR_BOTTOM = 348                # the floor texture stops where the Menu's buttons start covering the banner


def dawn_life(f):
    """0 -> 1 as the cast walks in (frames 60..460 of Start), smoothstepped; awake for the whole Loop."""
    t = min(1.0, max(0.0, (f - 60) / 400.0)) if f < M.START else 1.0
    return t * t * (3 - 2 * t)


def dawn_layers(tmpl_mat, files, mats_new, anim):
    """A wireframe floor under a dark sky. Its converging lines are one texture, mirrored about the middle;
    the cross lines are thin panes riding perspective keys toward the viewer, speeding up as the cast arrives;
    a red glow and a gold horizon line fade in, and stars twinkle."""
    blank = Image.new("RGBA", (8, 8), BLACK + (255,))
    files["Black.tpl"] = T.build([(blank, T.RGB5A3, None, blank.size)])
    out = dict(bg_tex="Black.tpl", bg_wrap=("GX_CLAMP", "GX_CLAMP"), bg_fore=BLACK + (255,), bg_back=BLACK + (255,),
               bg_uv=None, blocks=[])
    white = Image.new("RGBA", (8, 4), (255, 255, 255, 255))
    files["White.tpl"] = T.build([(white, T.RGB5A3, None, white.size)])
    mats_new.append(mat_xml(tmpl_mat, "WhiteMat", "White.tpl"))
    blocks = out["blocks"]

    # sky glow: deep red rising off the horizon, its own alpha ramp baked into the texture
    glow = np.zeros((64, 8, 4), np.uint8)
    glow[..., :3] = 255
    glow[..., 3] = (255 * (np.linspace(0, 1, 64) ** 1.6))[:, None].astype(np.uint8)
    files["Glow.tpl"] = T.build([(Image.fromarray(glow, "RGBA"), T.RGB5A3, None, (8, 64))])
    mats_new.append(mat_xml(tmpl_mat, "GlowMat", "Glow.tpl", back=DEEP_RED + (255,)))
    blocks.append(pic_xml("SkyGlowPic", "GlowMat", (W, 44), px(W / 2.0, HORIZON - 22), alpha="00"))
    for start in (True, False):
        anim[start].append(rlvc_alpha("SkyGlowPic", lambda f: 255 * dawn_life(f), start))

    # stars: the mockup's own positions and phases
    rng = np.random.RandomState(7)
    stars = [(rng.randint(0, W), rng.randint(4, HORIZON - 10), rng.randint(0, 120)) for _ in range(70)][:28]
    for i, (sx, sy, ph) in enumerate(stars):
        pn = f"Star{i:02d}Pic"
        blocks.append(pic_xml(pn, "WhiteMat", (2, 2), px(sx + 1, sy + 1), [(255, 120, 120, 255)] * 4, alpha="00"))
        tw = lambda f, ph=ph: (
            255 * (0.5 + 0.5 * math.sin((f + ph) * 2 * math.pi * 29 / 2000)) * (0.35 + 0.4 * dawn_life(f))
        )
        for start in (True, False):
            anim[start].append(apane(pn, 0, [
                tag("RLVC", [entry("16", triplets(keys_linear(per_frame(tw, start), tol=3, corner=40)))])
            ]))

    # converging floor lines: the right half drawn exactly, mirrored for the left
    fh = FLOOR_BOTTOM - HORIZON
    half = np.zeros((fh, W // 2), np.uint8)
    cx = W / 2
    for k in range(0, 25):
        for y in range(HORIZON, FLOOR_BOTTOM):
            t = (y - HORIZON) / (H - HORIZON)
            x = int(round(cx + k * (8 + 120 * t))) - W // 2
            if 0 <= x < W // 2:
                half[y - HORIZON, x] = 255
    floor = Image.fromarray(np.dstack([half, half, half, half]), "RGBA")
    files["Floor.tpl"] = quant_tpl(floor)
    mats_new.append(mat_xml(tmpl_mat, "FloorMat", "Floor.tpl", wrap=("GX_MIRROR", "GX_CLAMP")))
    depth_top = GRID_RED + (255,)
    depth_low = tuple(int(GRID_RED[i] + (RED[i] - GRID_RED[i]) * fh / (H - HORIZON)) for i in range(3)) + (255,)
    blocks.append(pic_xml("FloorPic", "FloorMat", (W, fh), px(W / 2.0, HORIZON + fh / 2.0),
                          [depth_top, depth_top, depth_low, depth_low], uv=[(-1, 0), (1, 0), (-1, 1), (1, 1)]))

    # cross lines rolling toward the viewer
    def phase(f):
        if f < M.START:
            # the mockup's scroll speed grows with life; integrate it so the lines never jump
            return sum(dawn_life(g) for g in range(f)) * 0.012
        return sum(dawn_life(g) for g in range(M.START)) * 0.012 + (f - M.START) * 0.012

    phase_at = [phase(f) for f in range(M.START + M.LOOP)]
    for k in range(14):
        pn = f"Cross{k:02d}Pic"
        blocks.append(pic_xml(pn, "WhiteMat", (W, 1), (0.0, 0.0), [RED + (255,)] * 4, alpha="00"))

        def y_of(f, k=k):
            z = k + 1 - (phase_at[f] % 1.0)
            return HORIZON + (H - HORIZON) * (1.0 / z) * 0.9 if z > 0.2 else H + 10

        def ty(f, y_of=y_of):
            return H / 2.0 - min(y_of(f), H + 10)

        def al(f, y_of=y_of):
            y = y_of(f)
            if y >= FLOOR_BOTTOM:
                return 0.0
            depth = (y - HORIZON) / (H - HORIZON)
            return (110 + 145 * depth) * (0.35 + 0.65 * dawn_life(f))

        for start in (True, False):
            anim[start].append(rlpa(pn, [("Y Translation", ty, dict(tol=0.3, corner=6))], start))
            anim[start].append(apane(pn, 0, [
                tag("RLVC", [entry("16", triplets(keys_linear(per_frame(al, start), tol=3, corner=30)))])
            ]))

    blocks.append(
        pic_xml("HorizonPic", "WhiteMat", (W, 2), px(W / 2.0, HORIZON), [(255, 196, 96, 255)] * 4, alpha="00")
    )
    for start in (True, False):
        anim[start].append(rlvc_alpha("HorizonPic", lambda f: 60 + 195 * dawn_life(f), start))
    return out


if __name__ == "__main__":
    for d in (sys.argv[1:] or ["paint", "dawn"]):
        path, size = build(d)
        print(
            f"  {d}: {os.path.basename(path)}  {size:,} bytes uncompressed ({size / 600000:.0%} of the 600,000 share)"
        )
