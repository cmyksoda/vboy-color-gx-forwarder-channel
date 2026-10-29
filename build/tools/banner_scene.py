"""The banner's shared pieces: the parade's cels at whole-number scales, and the colors the designs use."""

import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, os.path.dirname(__file__))
import icon_scene as I
from vbcgx import ROOT

W, H = 832, 456
X43 = (112, 720)                 # what a 4:3 TV shows
START, LOOP = 1000, 2000
RED, DEEP_RED, LOWER_RED, BLACK = I.RED, I.DEEP_RED, I.LOWER_RED, (6, 4, 8)
GRID_RED = (150, 18, 30)
# Hues from the VBoy Color logo's "COLOR" letters, the colors the grid comes alive in.
LOGO_HUES = [(204, 44, 66), (96, 84, 172), (160, 196, 40), (226, 182, 24), (20, 158, 170)]
REPO = I.REPO


def up(im, k):
    return im.resize((round(im.width * k), round(im.height * k)), Image.NEAREST)


# ------------------------------------------------------------------ walkers

CAST = os.path.join(ROOT, "banner", "cast")


def _cast(name, i):
    return Image.open(os.path.join(CAST, name, f"{name}-{i}.png")).convert("RGBA")


def walker_cels(scaled=True):
    """Every cel of the parade at its walker's whole-number scale (nearest neighbor), or at 1x, cut from the
    games. A walker's cels share one canvas with the game's own bob built in: the canvas bottom is the lowest step."""
    c = {}
    for w in M.FRONT:
        names = list(dict.fromkeys(w.cycle))
        ims = {n: Image.open(os.path.join(CAST, w.name, f"{n}.png")).convert("RGBA") for n in names}
        drop = max(w.dy.values())
        for n, im in ims.items():
            cv = Image.new("RGBA", (im.width, im.height + drop))
            cv.alpha_composite(im, (0, w.dy[n]))
            c[n] = cv if not scaled else (up(cv, w.scale) if w.scale == int(w.scale) else ballom_15(cv))
    for kind in dict.fromkeys(i.kind for i in M.INVADERS):
        for k in (0, 1):
            c[f"{kind}{k}"] = up(_cast(kind, k + 1), M.FORM_SCALE)
    return c


import banner_model as M

FRONT_FEET = M.FRONT_FEET
RIPPLE_LIFE = 48

HORIZON = 112                     # the Dawn floor's horizon row (build_banner's Dawn layers)


# Ballom at 1.5x is drawn ahead of time, so both eyes can be the same true shape (Jaxi's request): the game's
# 3x10 eye (rounded ends, one light and one orange pixel down the middle) at 15 rows tall, centered where 1.5x
# puts each eye, at EYE_WIDTH pixels wide
EYE_DARK, EYE_LIGHT, EYE_GLINT = (110, 40, 20), (255, 232, 150), (240, 150, 50)
EYE_WIDTH = 4                    # Jaxi's pick


def eye_stamp(width=EYE_WIDTH):
    """The 1.5x eye as rows of (color or None): rounded top and bottom, the light and orange pixels in the middle."""
    edge = (width - (1 if width % 2 else 2)) // 2
    mid = width - 2 * edge
    row = lambda c: [EYE_DARK] * edge + [c] * mid + [EYE_DARK] * edge
    cap = [EYE_GLINT] + [EYE_DARK] * (width - 2) + [EYE_GLINT]
    return [cap, row(EYE_LIGHT), row(EYE_LIGHT), row(EYE_GLINT)] + [[EYE_DARK] * width] * 10 + [cap]


def ballom_15(im, width=EYE_WIDTH):
    """One Ballom cel (1x, RGBA) at 1.5x by nearest neighbour, with both eyes redrawn as eye_stamp."""
    from scipy import ndimage
    a = np.asarray(im)
    big = np.asarray(im.resize((round(im.width * 1.5), round(im.height * 1.5)), Image.NEAREST)).copy()
    dark = (a[..., 3] > 0) & np.all(a[..., :3] == EYE_DARK, axis=2)
    lab, _ = ndimage.label(dark)
    eyes = [sl for sl in ndimage.find_objects(lab) if sl[1].stop - sl[1].start == 3 and 8 <= sl[0].stop - sl[0].start <= 12]
    assert len(eyes) == 2, f"found {len(eyes)} eyes"
    stamp = eye_stamp(width)
    for sl in eyes:
        top, x0 = sl[0].start - 1, sl[1].start                      # the cap row sits just above the solid column
        cx = (x0 + 1.5) * 1.5                                       # the eye's center at 1.5x
        left, y0 = int(round(cx - width / 2)), int(round(top * 1.5))
        big[y0 - 1:y0 + len(stamp) + 1, left - 1:left + width + 1, :3] = EYE_LIGHT
        big[y0 - 1:y0 + len(stamp) + 1, left - 1:left + width + 1, 3] = 255
        for dy, r in enumerate(stamp):
            for dx, c in enumerate(r):
                big[y0 + dy, left + dx] = (*c, 255)
    return Image.fromarray(big)
