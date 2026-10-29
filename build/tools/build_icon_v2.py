"""Build icon.bin for Icon A, second version (icon_v2.py): the real stage in the game's own layers, and a view
that follows the action.

    build_icon_v2.py [out.bin]

Derived from the mGBA GX channel's released icon. The pane tree becomes:

    RootPane
      BackgroundPic                      the void (keeps its proportions in 16:9)
      CamPane                            the view: its Y translation is the camera (keeps its proportions in 16:9)
        WallPic  TumblePane              the back wall, then the knocked Koopa in front of it
        FarPic   KoopaPane ShellBPane MarioBPane     the back ledge, then the back-plane actors
        BackPic  FlyPane ShellFPane MarioCPane MarioFPane    the pipes and front ledge, then the front plane
        FrontPic                         the front tubes, over everything
      StripesPic                         the red and black bands (fixed)
      Logo00Pane                         the coin-flipping logo, on top

Each picture has its own material: the Menu gives a material's animation to only one pane, so none is shared.
Benzin's <flag> is the Wii's location-adjust bit, so each picture has exactly one flagged pane on its path.
"""

import os
import re
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(__file__))

import icon_scene as S
import icon_v2 as V
import tpl as T
from build_icon import canvas, ci_tpl, entry, keys_linear, make, pairs, pane, pane_block, palette_of, set_field, \
    set_size, set_xy, tag, triplets
from render import rip
from vbcgx import OUT, ROOT
from wiilib import U8, WAD, pack_lz77_imd5, u8_set_dir_files, unpack_lz77_imd5

DONOR = os.path.join(ROOT, "donor", "mGBA-GX - GBGX [cmyksoda].wad")
NAMES = {"tumble": "Tumble", "koopa": "Koopa", "shell_b": "ShellB", "mario_b": "MarioB",
         "fly": "Fly", "shell_f": "ShellF", "mario_c": "MarioC", "mario_f": "MarioF"}
LAYER_NAMES = {"wall": "Wall", "far": "Far", "back": "Back", "front": "Front"}


def sample(L):
    track = {a: [None] * L for a in V.ACTORS}
    for f in range(L):
        for actor, cel, x, y in V.story(f):
            track[actor][f] = (cel, float(x), float(y))
    return track


def step_keys(values):
    """Keys for a value that only jumps: two keys half a frame before each change, so every whole frame
    reads exactly one value however a tie on the step frame would be resolved."""
    out = [(0, values[0], 0.0)]
    for f in range(1, len(values)):
        if values[f] != values[f - 1]:
            out += [(f - 0.5, values[f - 1], 0.0), (f - 0.5, values[f], 0.0)]
    out.append((len(values) - 1, values[-1], 0.0))
    return out


def held(trk, key, default):
    vals, last = [], default
    for s in trk:
        if s is not None:
            last = s[key]
        vals.append(last)
    return vals


def tex_exact_ci(im):
    """CI4 (or CI8) with the art's own colors, checked on decode; colors round to the palette's 5 bits."""
    q = T.quantize(im, 16) or T.quantize(im, 256)
    idx, pal = q
    fmt = T.CI4 if len(pal) <= 16 else T.CI8
    data = T.build([(idx, fmt, pal, im.size)])
    info = T.parse(data)[0]
    back = np.asarray(T.decode(data[info["data_off"]:], info["w"], info["h"], fmt, info["pal"]))
    src = np.asarray(im)
    assert np.array_equal(back[..., 3] > 0, src[..., 3] > 0)
    assert int(np.abs(back[..., :3].astype(int) - src[..., :3].astype(int))[src[..., 3] > 0].max(initial=0)) <= 8
    return data


def crop_tiles(im):
    """(cropped image, left, top): a layer cut to its opaque pixels, padded out to whole 8x8 tiles."""
    a = np.asarray(im)[..., 3] > 0
    ys, xs = np.nonzero(a)
    x0, y0 = int(xs.min()), int(ys.min())
    w = -(-(int(xs.max()) + 1 - x0) // 8) * 8
    h = -(-(int(ys.max()) + 1 - y0) // 8) * 8
    out = Image.new("RGBA", (w, h))
    out.alpha_composite(im.crop((x0, y0, min(im.width, x0 + w), min(im.height, y0 + h))), (0, 0))
    return out, x0, y0


# ------------------------------------------------------------------ layout

def block_of(xml, kind, name):
    m = re.search(rf'\n(\t*<tag type="{kind}" name="{name}".*?</tag>\n)', xml, re.S)
    return m.group(1)


def new_pic(template, name, mat, size, tr, flag="00"):
    b = template.replace(re.search(r'name="[^"]+"', template).group(0), f'name="{name}"', 1)
    b = re.sub(r'<material name="[^"]+"', f'<material name="{mat}"', b)
    b = set_field(set_field(set_field(b, "visible", "01"), "alpha", "ff"), "flag", flag)
    b = set_field(b, "WidescreenAffected", "00")
    b = set_size(set_xy(set_xy(b, "translate", *tr), "scale", 1.0, 1.0), *size)
    for k, (u, v) in zip(("TL", "TR", "BL", "BR"), ((0, 0), (1, 0), (0, 1), (1, 1))):
        b = re.sub(rf'<coord{k} s="[-\d.]+" t="[-\d.]+" />', f'<coord{k} s="{u:.6f}" t="{v:.6f}" />', b)
    return b


def new_group(head_tmpl, pic_tmpl, name, tr, pic):
    """An actor: a group pane at the actor's place, holding its picture (offset to the cels' canvas)."""
    head = head_tmpl.replace(re.search(r'name="[^"]+"', head_tmpl).group(0), f'name="{name}Pane"', 1)
    head = set_field(set_field(set_field(set_field(head, "visible", "01"), "alpha", "ff"), "flag", "00"),
                     "WidescreenAffected", "00")
    head = set_xy(set_xy(head, "translate", *tr), "scale", 1.0, 1.0)
    indent = re.match(r"\t*", head_tmpl).group(0)
    size, ptr = pic
    return (head + f'{indent}<tag type="pas1" />\n' + new_pic(pic_tmpl, f"{name}Pic", f"{name}Mat", size, ptr)
            + f'{indent}<tag type="pae1" />\n')


def retune_pane(block, tr, flag):
    head_end = block.index("</tag>") + len("</tag>")
    head = set_field(set_field(set_field(block[:head_end], "visible", "01"), "alpha", "ff"), "flag", flag)
    return set_xy(head, "translate", *tr) + block[head_end:]


def material(xml, name):
    m = re.search(rf'\n(\t*<entries name="{name}">.*?</entries>\n)', xml, re.S)
    return m.group(1)


def mat_texture(b, texture):
    b = re.sub(r'<texture name="[^"]+">', f'<texture name="{texture}">', b, count=1)
    b = re.sub(r"<wrap_s>\w+</wrap_s>", "<wrap_s>GX_CLAMP</wrap_s>", b)
    b = re.sub(r"<wrap_t>\w+</wrap_t>", "<wrap_t>GX_CLAMP</wrap_t>", b)
    for fld, v in (("XTrans", 0), ("YTrans", 0), ("Rotate", 0), ("XScale", 1), ("YScale", 1)):
        b = re.sub(rf"<{fld}>[^<]*</{fld}>", f"<{fld}>{v:.10f}</{fld}>", b)
    return b


def edit_layout(xml, geom, textures):
    pic_tmpl = block_of(xml, "pic1", "BackgroundPic")
    head_tmpl = block_of(xml, "pan1", "Luigi01Pane")

    s, e = pane_block(xml, "Logo00Pane")
    logo = retune_pane(xml[s:e], geom["Logo00Pane"], "01")
    lp = block_of(logo, "pic1", "Logo00Pic")
    logo = logo.replace(lp, set_size(set_xy(set_field(set_field(lp, "visible", "01"), "alpha", "ff"),
                                            "translate", 0.0, 0.0), 128, 48))

    cam = head_tmpl.replace('name="Luigi01Pane"', 'name="CamPane"')
    cam = set_field(set_field(set_field(set_field(cam, "visible", "01"), "alpha", "ff"), "flag", "01"),
                    "WidescreenAffected", "00")
    cam = set_xy(cam, "translate", 0.0, V.CAM_FRONT)

    indent = re.match(r"\t*", pic_tmpl).group(0)
    inner = ""
    for layer, _, _ in V.LAYERS:
        name = LAYER_NAMES[layer]
        inner += new_pic(pic_tmpl, f"{name}Pic", f"{name}Mat", *geom[f"{name}Pic"])
        for actor in V.ACTORS:
            if V.ACTOR_LAYER[actor] == layer:
                n = NAMES[actor]
                inner += new_group(head_tmpl, pic_tmpl, n, geom[f"{n}Pane"], geom[f"{n}Pic"])

    tree = (new_pic(pic_tmpl, "BackgroundPic", "BackgroundMat", (S.W, S.H), (0.0, 0.0), flag="01")
            + cam + f'{indent}<tag type="pas1" />\n' + inner + f'{indent}<tag type="pae1" />\n'
            + new_pic(pic_tmpl, "StripesPic", "StripesMat", *geom["StripesPic"], flag="01") + logo)
    root = xml.index('<tag type="pan1" name="RootPane"')
    start = xml.index("\n", xml.index('<tag type="pas1" />', root)) + 1
    end = xml.rindex("\n", 0, xml.rindex('<tag type="pae1" />')) + 1
    xml = xml[:start] + tree + xml[end:]

    for name, texname in textures.items():
        if f'<entries name="{name}">' in xml:
            m = material(xml, name)
            xml = xml.replace(m, mat_texture(m, texname))
        else:
            bg = material(xml, "BackgroundMat")
            new = bg.replace('<entries name="BackgroundMat">', f'<entries name="{name}">', 1)
            xml = xml.replace(bg, bg + mat_texture(new, texname))

    for gone in ("Luigi01Mat", "Mario01Mat", "Banana00Mat"):
        if f'<entries name="{gone}">' in xml:
            xml = xml.replace(material(xml, gone), "")

    names = list(dict.fromkeys(textures.values()))
    xml = re.sub(r"(<tag type=\"txl1\">\s*<entries>).*?(\s*</entries>)",
                 lambda mm: mm.group(1) + "".join(f"\n\t\t\t\t\t<name>{n}</name>" for n in names) + mm.group(2),
                 xml, count=1, flags=re.S)
    return xml


# ------------------------------------------------------------------- build

def build(out_path=None, mode=0, logo_mode="game"):
    layers, _, geo = V.build(mode)
    L = V.loop_len(mode)
    celtab = V.cels()
    track = sample(L)
    files, textures, geom, anim, timg = {}, {}, {}, [], []
    sh = geo["height"]
    to_pane_y = lambda y: sh / 2.0 - y          # strip row -> pane y inside CamPane (+y up)

    void = Image.new("RGBA", (8, 8), V.VOID + (255,))
    files["Void.tpl"] = T.build([(void, T.RGB5A3, None, void.size)])
    textures["BackgroundMat"] = "Void.tpl"

    for layer, _, _ in V.LAYERS:
        name = LAYER_NAMES[layer]
        im, x0, y0 = crop_tiles(layers[layer])
        files[f"{name}.tpl"] = tex_exact_ci(im)
        textures[f"{name}Mat"] = f"{name}.tpl"
        geom[f"{name}Pic"] = ((im.width, im.height), (x0 + im.width / 2.0 - S.W / 2.0, to_pane_y(y0 + im.height / 2.0)))

    band = V.stripes_layer().crop((0, 81, 8, 97))
    files["Stripes.tpl"] = T.build([(band, T.RGBA8, None, band.size)])     # the app's exact reds
    textures["StripesMat"] = "Stripes.tpl"
    geom["StripesPic"] = ((S.W, 16), (0.0, S.H / 2.0 - 89.0))

    logos = V.logo_canvases(logo_mode)
    files["Logo00.tpl"] = tex_exact_ci(logos[0])
    files["Logo01.tpl"] = T.build([(logos[1], T.RGB5A3, None, logos[1].size)])
    textures["Logo00Mat"] = "Logo00.tpl"
    geom["Logo00Pane"] = (0.0, S.H / 2.0 - V.LOGO_ROW)
    timg += ["Logo00.tpl", "Logo01.tpl"]
    scale, swaps = V.flip_keys(L, mode)
    anim.append(pane("Logo00Pic", 0, [tag("RLPA", [entry("X Scale", triplets([(f, v, 0.0) for f, v in scale]))])]))
    anim.append(pane("Logo00Mat", 1, [tag("RLTP", [entry("PaletteZero", pairs(swaps))])]))

    # every position steps from whole pixel to whole pixel, as the game moves things, so nothing is ever
    # drawn between pixels and smoothed
    cams = [round(V.cam(f, mode)) for f in range(L)]
    anim.append(pane("CamPane", 0, [tag("RLPA", [entry("Y Translation", triplets(step_keys(cams)))])]))

    for actor in V.ACTORS:
        n = NAMES[actor]
        trk = track[actor]
        used = []
        for s in trk:
            if s and s[0] not in used:
                used.append(s[0])
        x0, y0, cw, ch = canvas(celtab, used)
        cels = []
        for c in used:
            im, (dx, dy) = celtab[c]
            cv = Image.new("RGBA", (cw, ch))
            cv.alpha_composite(im, (dx - x0, dy - y0))
            cels.append(cv)
        pal = palette_of(cels)
        names = [f"{n}{i:02d}.tpl" for i in range(len(used))]
        for nm, cv in zip(names, cels):
            files[nm] = ci_tpl(cv, pal) if pal else tex_exact_ci(cv)
        base = len(timg)
        timg += names
        textures[f"{n}Mat"] = names[0]
        geom[f"{n}Pic"] = ((cw, ch), (x0 + cw / 2.0, -(y0 + ch / 2.0)))

        xs = [round(v) - S.W / 2.0 for v in held(trk, 1, 0.0)]
        ys = [to_pane_y(round(v)) for v in held(trk, 2, 0.0)]
        geom[f"{n}Pane"] = (xs[0], ys[0])
        anim.append(pane(f"{n}Pane", 0, [tag("RLPA", [
            entry("X Translation", triplets(step_keys(xs))), entry("Y Translation", triplets(step_keys(ys)))])]))
        al = [0.0 if s is None else 255.0 for s in trk]
        anim.append(pane(f"{n}Pic", 0, [tag("RLVC", [entry("16", triplets(step_keys(al)))])]))

        steps, last = [], None
        for f, s in enumerate(trk):
            c = used.index(s[0]) if s else None
            if c is not None and c != last:
                steps.append((f, base + c))
                last = c
        anim.append(pane(f"{n}Mat", 1, [tag("RLTP", [entry("PaletteZero", pairs(steps))])]))

    w = WAD.load(DONOR)
    app = w.contents[0]
    meta = U8.load(app[app.find(b"\x55\xAA\x38\x2D"):])
    arc = U8.load(unpack_lz77_imd5(meta.get("meta/icon.bin")))

    lyt_xml = edit_layout(rip(arc.get("arc/blyt/icon.brlyt"), ".xmlyt"), geom, textures)
    an_xml = ('<?xml version="1.0" encoding="utf-8"?>\n\t\t<xmlan version="2.1.12BETA" brlan_version="0008">\n'
              f'\t\t\t<pai1 framesize="{L}" flags="01">\n'
              + "".join(f'\t\t\t\t<timg name="{n}" />\n' for n in timg)
              + "".join(anim) + "\t\t\t</pai1>\n\t\t</xmlan>\n")

    arc.replace("arc/blyt/icon.brlyt", make(lyt_xml, ".xmlyt"))
    arc.replace("arc/anim/icon.brlan", make(an_xml, ".xmlan"))
    u8_set_dir_files(arc, "arc/timg", files)

    raw = arc.to_bytes()
    out = out_path or os.path.join(OUT, "icon-clash2.bin")
    open(out, "wb").write(pack_lz77_imd5(raw))
    return out, len(raw)


if __name__ == "__main__":
    path, size = build(sys.argv[1] if len(sys.argv) > 1 else None)
    print(f"  {os.path.basename(path)}  {size:,} bytes uncompressed ({size / 102400:.0%} of the cap)")
