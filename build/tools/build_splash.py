"""The forwarder's two splash screens: build_splash.py

4:3 and 16:9 loading screens in the channel's colors: the banner's red grid on black, the VBoy Color GX logo
rebuilt from the full-size master in the app icon's one-row layout, and "Loading..." in Fredoka SemiBold (Jaxi's
pick) beneath it, sized and placed like mGBA GX's splash. The 16:9 file is the wide picture squeezed to 640
pixels, because the Wii stretches its 640x480 picture to fill a widescreen set; the grid is drawn at the squeezed
pitch so its lines stay sharp. Both are RGB PNGs (Tantric's PNGU decoder rejects palette ones), and each must
fit the slot of the PNG it replaces in the forwarder.
"""

import os
import struct
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from scipy import ndimage

sys.path.insert(0, os.path.dirname(__file__))
import banner_scene as BS
from vbcgx import OUT, ROOT

SPLASH = os.path.join(ROOT, "splash")
ICON = os.path.join(ROOT, "banner", "vbcgx-logo.png")
MASTER = os.path.join(ROOT, "banner", "logo-master.png")
FONT, WEIGHT = os.path.join(os.path.dirname(OUT), "fonts", "Fredoka.ttf"), b"SemiBold"
ROOM = {"4-3": 165_683, "16-9": 157_270}         # the splash PNGs' lengths in Tantric's Wii and vWii forwarders
W, H = 640, 480
CELL, LINE = 32, 2                                # the banner's grid
LOGO_SCALE = 2.2                                  # the icon's logo at about mGBA GX's logo width
LOGO_MID, CAP, BASELINE = 165, 40, 340            # mGBA GX: logo centered on row 165, "Loading..." caps 40 px on 340
HALO = 7


def pieces(im, grow):
    """Boxes of the logo's three pieces: the red VBOY, the GX badge (white letters, right), the COLOR letters."""
    a = im[..., 3] > 40
    lab, _ = ndimage.label(ndimage.binary_dilation(a, iterations=grow))
    groups = {"VBOY": [], "COLOR": [], "GX": []}
    for i, sl in enumerate(ndimage.find_objects(lab), start=1):
        m = (lab[sl] == i) & a[sl]
        if m.sum() < 0.0005 * a.sum():
            continue
        px = im[sl][m][:, :3].astype(int)
        r, g, b = px.mean(axis=0)
        ys, xs = sl
        if (px.min(axis=1) > 200).mean() > 0.05 and (xs.start + xs.stop) / 2 > 0.6 * a.shape[1]:
            groups["GX"].append(sl)
        elif r > 170 and g < 70 and b < 70:
            groups["VBOY"].append(sl)
        else:
            groups["COLOR"].append(sl)
    return {
        k: (
            min(s[1].start for s in v),
            min(s[0].start for s in v),
            max(s[1].stop for s in v),
            max(s[0].stop for s in v),
        )
        for k, v in groups.items()
    }


def logo(scale=LOGO_SCALE):
    """The master's pieces, each fitted by height to where the app's logo puts them, at `scale` times its size."""
    icon = np.asarray(Image.open(ICON).convert("RGBA"))
    master = Image.open(MASTER).convert("RGBA")
    at, src = pieces(icon, 1), pieces(np.asarray(master), 12)
    x0 = min(b[0] for b in at.values())
    y0 = min(b[1] for b in at.values())
    x1 = max(b[2] for b in at.values())
    y1 = max(b[3] for b in at.values())
    out = Image.new("RGBA", (round((x1 - x0) * scale) + 24, round((y1 - y0) * scale) + 4), (0, 0, 0, 0))
    for k, (ix0, iy0, ix1, iy1) in at.items():
        h = round((iy1 - iy0) * scale)
        part = master.crop(src[k])
        part = part.resize((round(part.width * h / part.height), h), Image.LANCZOS)
        cx = ((ix0 + ix1) / 2 - x0) * scale + 12
        out.alpha_composite(part, (round(cx - part.width / 2), round((iy1 - y0) * scale) - h + 2))
    return out


def text_layer(width):
    probe = ImageFont.truetype(FONT, 100)
    probe.set_variation_by_name(WEIGHT)
    l, t, r, b = probe.getbbox("L")
    font = ImageFont.truetype(FONT, round(100 * CAP / (b - t)))
    font.set_variation_by_name(WEIGHT)
    layer = Image.new("RGBA", (width, H), (0, 0, 0, 0))
    ImageDraw.Draw(layer).text((width / 2, BASELINE), "Loading...", font=font, fill=(255, 255, 255, 255), anchor="ms")
    return layer


def overlay(width):
    """Logo and text over a soft black halo, so no grid line runs through them, on a `width`-wide canvas."""
    lg = logo()
    layer = Image.new("RGBA", (width, H), (0, 0, 0, 0))
    layer.alpha_composite(lg, (round(width / 2 - lg.width / 2), round(LOGO_MID - lg.height / 2)))
    layer.alpha_composite(text_layer(width))
    a = layer.getchannel("A").point(lambda v: 255 if v > 24 else 0)
    halo = a.filter(ImageFilter.MaxFilter(2 * HALO + 1)).filter(ImageFilter.GaussianBlur(2.5))
    out = Image.new("RGBA", (width, H), BS.BLACK + (0,))
    out.putalpha(halo)
    out.alpha_composite(layer)
    return out


def grid(pitch_x):
    im = Image.new("RGB", (W, H), BS.BLACK)
    d = ImageDraw.Draw(im)
    for x in np.arange(W / 2 % pitch_x, W, pitch_x):
        d.rectangle((round(x) - LINE // 2, 0, round(x) - LINE // 2 + LINE - 1, H - 1), fill=BS.GRID_RED)
    for y in range(H // 2 % CELL, H, CELL):
        d.rectangle((0, y - LINE // 2, W - 1, y - LINE // 2 + LINE - 1), fill=BS.GRID_RED)
    return im


def splash(wide):
    if wide:
        over = overlay(round(W * 4 / 3)).resize((W, H), Image.LANCZOS)
        base = grid(CELL * 3 / 4)
    else:
        over, base = overlay(W), grid(CELL)
    base = base.convert("RGBA")
    base.alpha_composite(over)
    return base.convert("RGB")


def slots(fw):
    """{tag: (offset, length)} of the forwarder's two splash PNGs: its first two 640x480 RGB PNGs, 4:3 first."""
    found, i = [], 0
    while len(found) < 2:
        i = fw.find(b"\x89PNG\r\n\x1a\n", i)
        assert i >= 0, "the forwarder has fewer than two splash PNGs"
        if fw[i + 16:i + 24] == struct.pack(">II", W, H) and fw[i + 25] == 2:
            found.append((i, fw.find(b"IEND", i) + 8 - i))
        i += 8
    out = dict(zip(ROOM, found))
    assert all(room == ROOM[tag] for tag, (_, room) in out.items()), "the splash slots aren't the expected sizes"
    return out


def path(tag):
    return os.path.join(SPLASH, f"splash-{tag}.png")


def main():
    os.makedirs(SPLASH, exist_ok=True)
    for tag, wide in (("4-3", False), ("16-9", True)):
        splash(wide).save(path(tag), optimize=True)
        png = open(path(tag), "rb").read()
        room = ROOM[tag]
        assert png[25] == 2 and len(png) <= room, f"splash-{tag}.png must be an RGB PNG of at most {room:,} bytes"
        print(f"  splash-{tag}.png: {len(png):,} bytes of the {room:,}-byte slot ({len(png) / room:.0%})")


if __name__ == "__main__":
    main()
