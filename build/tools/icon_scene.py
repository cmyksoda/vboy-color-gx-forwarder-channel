"""Icon proposals: art from the captures, the choreography, and exact mock frames.

Every sprite pixel is a pixel VBoy Color drew (cut from harness-tags captures of
Mario Clash with its color pack); backgrounds are composed from the clean stage
rebuilt from those same frames. Frames here are composited 1:1 with no
filtering, which is what the icon shows for whole-pixel positions.
"""

import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(__file__))
from vbcgx import ROOT

CAP = os.path.join(ROOT, "icon")
REPO = os.path.dirname(ROOT)
W, H = 176, 96
FRAMES = 1200

# The app's own reds (source/menustyle.h, Brighter LED): accent and chrome edge, with near-black between,
# in the same band layout as Tantric's FCE Ultra GX icon and the mGBA GX icon.
RED, DEEP_RED, BLACK = (240, 40, 56), (176, 24, 38), (10, 2, 5)
LOWER_RED = (76, 8, 14)          # the lower red bar: the app menu's light chrome red (Jaxi's pick on her TV)
STRIPES = [(81, 86, RED), (86, 87, BLACK), (87, 92, LOWER_RED), (92, 96, BLACK)]
VB_BLACK = (6, 6, 14)            # Mario Clash's screen background in VBoy Color


def fig(run, h):
    return Image.open(os.path.join(CAP, run, "figs", f"{h}.png")).convert("RGBA")


def mirror(im):
    return im.transpose(Image.FLIP_LEFT_RIGHT)


# ------------------------------------------------------------------- cels

def cels():
    """name -> (RGBA, (dx, dy)): dx/dy place the cel's top-left relative to the actor's anchor (feet center)."""
    out = {}

    def foot(name, im, ox=None):
        # anchor at the bottom center of the cel, or at a fixed column for in-place sequences
        cx = im.width // 2 if ox is None else ox
        out[name] = (im, (-cx, -im.height))

    walk = ["1c2f03c23eb7", "f925f4e33d92", "d017d5a3dc01", "c09e6d6753ee"]
    for i, h in enumerate(walk):
        foot(f"walk{i}", fig("t2", h))

    # The pick-up and throw happened in place (game x 261..275), so their game positions align them; they face
    # left in the capture and are mirrored to face the way Mario walks here.
    seq = [
        ("bend0", "32ccf493c964", 261, 161),
        ("bend1", "a5ce33871c8b", 262, 161),
        ("lift", "384b32aa8d6a", 269, 162),
        ("hold0", "b09f142cb79d", 273, 162),
        ("hold1", "328dac68544b", 273, 162),
        ("wind0", "4c3a44e2b12e", 275, 161),
        ("wind1", "569242c8afba", 275, 161),
        ("throw", "8fd2d105babe", 267, 160),
        ("back", "26b5b8c0232e", 273, 162),
    ]
    ref_x, ref_y = 300, 199                      # a point at Mario's feet in that capture
    for name, h, x, y in seq:
        im = mirror(fig("w1h", h))
        # mirroring flips x about the cel: its left edge moves to (2*ref - x - w)
        mx = 2 * ref_x - x - im.width
        out[name] = (im, (mx - ref_x, y - ref_y))

    for name, h in [("fly0", "e4df87c15d0c"), ("fly1", "fb04d79792ae"), ("fly2", "77688df9b532"),
                    ("fly3", "02db47bbadd9"), ("fly4", "0d6fc5fa1a5f"), ("land", "47d5e4a94f96")]:
        foot(name, mirror(fig("w1h", h)))
    for name, h in [("shell", "5cdf423f8670"), ("shell1", "e51205c12cb0")]:
        foot(name, fig("v-UPA", h))
    for i, h in enumerate(["b8378be4136c", "440bba1377b4", "c6edcc12d816"]):
        k = fig("w1h" if h != "440bba1377b4" else "mc56h", h)
        foot(f"koopa{i}", mirror(k))
        foot(f"koopaL{i}", k)
    for i, h in enumerate(["e82169473438", "b471caea2610", "dd60202be1cb"]):
        foot(f"bwalk{i}", fig("t3", h))
    for i, h in enumerate(["c2e9c1357e97", "adf0cdf771ab", "dd4c62ac78b2", "16806eb82901"]):
        foot(f"tumble{i}", fig("w1h", h))
    return out


# ------------------------------------------------------------- backgrounds

def stripes(img):
    d = np.asarray(img).copy()
    for y0, y1, c in STRIPES:
        d[y0:y1, :, :3] = c
        d[y0:y1, :, 3] = 255
    return Image.fromarray(d, "RGBA")


def stage_pieces(mode):
    """Pieces of the clean stage (mode 0: VBoy Color's colors, 4: Tint Red)."""
    st = Image.open(os.path.join(CAP, f"stage-clean-m{mode}.png")).convert("RGBA")
    return dict(
        front_ledge=st.crop((40, 191, 344, 213)),      # top edge, surface, light line, bricks
        back_ledge=st.crop((72, 116, 290, 140)),
        pipe_left=st.crop((0, 160, 40, 200)),
        pipe_right=st.crop((344, 160, 384, 200)),
        bg=tuple(np.asarray(st)[100, 200][:3]),
    )


def compose_stage(mode):
    p = stage_pieces(mode)
    img = Image.new("RGBA", (W, H), p["bg"] + (255,))

    # back ledge: its two ends with the middle squeezed out, top edge at y 47
    bl = p["back_ledge"]
    b = np.asarray(bl).copy()
    warm = (b[..., 0].astype(int) > b[..., 2].astype(int) + 30) & (b[..., 1] < 140)
    surface = b[6, 100].copy()
    b[warm] = surface
    bl = Image.fromarray(b, "RGBA")
    left, right = bl.crop((0, 0, 50, bl.height)), bl.crop((bl.width - 50, 0, bl.width, bl.height))
    back = Image.new("RGBA", (104, bl.height))
    back.alpha_composite(left, (0, 0))
    back.alpha_composite(right, (54, 0))
    back.alpha_composite(bl.crop((80, 0, 84, bl.height)), (50, 0))
    img.alpha_composite(back.crop((0, 0, 104, 16)), (36, 47))

    # front ledge across the whole icon, top edge at y 70, cut where the stripes start
    fl = p["front_ledge"]
    front = Image.new("RGBA", (W, fl.height))
    for x in range(0, W, 40):
        front.alpha_composite(fl.crop((100, 0, 140, fl.height)), (x, 0))
    front.alpha_composite(fl.crop((0, 0, 30, fl.height)), (0, 0))
    front.alpha_composite(fl.crop((fl.width - 30, 0, fl.width, fl.height)), (W - 30, 0))
    img.alpha_composite(front.crop((0, 0, W, 11)), (0, 70))
    return stripes(img)


PIPE_TOP = 40                    # the pipe mouths start just under the logo, so neither ever covers the other


def key_outside(im, bg):
    """The piece with the background around it made transparent (enclosed dark areas, like a pipe's opening, stay)."""
    from scipy import ndimage
    a = np.asarray(im).copy()
    lab, _ = ndimage.label(np.all(a[..., :3] == np.array(bg), axis=2))
    edge = (set(lab[0, :]) | set(lab[-1, :]) | set(lab[:, 0]) | set(lab[:, -1])) - {0}
    a[np.isin(lab, list(edge)), 3] = 0
    return Image.fromarray(a, "RGBA")


def pipes_overlay(mode):
    """The pipe mouths at the edges of the 4:3 view, drawn over the sprites: Mario walks into one and out of the
    other, and anything on the back ledge passes behind them."""
    p = stage_pieces(mode)
    lay = Image.new("RGBA", (W, H))
    for key, x in (("pipe_left", 4), ("pipe_right", W - 44)):
        lay.alpha_composite(key_outside(p[key], p["bg"]), (x, PIPE_TOP))
    return lay


def compose_grid():
    """Black with the Virtual Boy's red grid, two depth planes drawn as perspective floors."""
    img = Image.new("RGBA", (W, H), VB_BLACK + (255,))
    a = np.asarray(img).copy()
    red, dim = np.array(RED), np.array((96, 10, 20))
    horizon, cx = 30, W / 2.0

    for y in range(horizon, 81):
        t = (y - horizon) / (81 - horizon)
        for k in range(-14, 15):
            # converging verticals
            x = int(round(cx + k * (6 + 34 * t)))
            if 0 <= x < W:
                a[y, x, :3] = dim if y < 47 else red

    for y in (47, 49, 52, 56, 61, 67, 74, 80):
        a[y, :, :3] = red if y >= 70 else (dim if y < 60 else red)
    return stripes(Image.fromarray(a, "RGBA"))


# ------------------------------------------------------------- choreography

FRONT_Y, BACK_Y = 77, 52         # feet lines of the front and back ledges
SHELL_X, KOOPA_X = 86, 106       # where the shell rests and where the back Koopa stops
PIPE_L, PIPE_R = 38, 138         # pipe rims: Mario shows right of PIPE_L and left of PIPE_R


def lerp_keys(keys, f):
    """Piecewise-linear value of [(frame, value), ...] at frame f (held outside)."""
    if f <= keys[0][0]:
        return keys[0][1]
    for (f0, v0), (f1, v1) in zip(keys, keys[1:]):
        if f0 <= f <= f1:
            return v0 + (v1 - v0) * (f - f0) / (f1 - f0) if f1 > f0 else v1
    return keys[-1][1]


PASSES = {"a": 400, "b": 400, "c": 600}


def story(f, variant="a"):
    """What's on screen at frame f of a pass: [(cel name, x, y, clip, scale, alpha)], back to front.

    a: the shell knocks the Koopa off the back ledge and slides away.
    b: after the knock it ricochets out of the screen, straight at you.
    c: Mario takes the pipes through both planes before coming back round.
    """
    out = []
    P = PASSES[variant]
    seq_x = SHELL_X - 31                         # the pick-up cels' anchor, lining their shell up with the resting one
    stop_x = seq_x + 11                          # Mario's walk ends with his body where the bend cel has it

    # back Koopa: waits, is knocked away by the shell, and a new one walks in
    if f < 206:
        out.append((f"koopa{(f // 9) % 3}", KOOPA_X, BACK_Y, None, 1.0, 1.0))
    elif f < 258:
        t = f - 206
        y = BACK_Y - 28 * np.sin(np.pi * min(t, 34) / 34) + (0 if t < 34 else (t - 34) * 2.6)
        out.append((f"tumble{(t // 4) % 4}", KOOPA_X + t * 1.1, y, None, 1.0, 1.0))
    elif variant != "c" and f >= 270:
        kx = lerp_keys([(270, 18), (390, KOOPA_X)], f)
        out.append((f"koopa{(f // 9) % 3}", kx, BACK_Y, ("left", 44), 1.0, 1.0))
    elif variant == "c" and f >= 470:
        kx = lerp_keys([(470, 150), (560, KOOPA_X)], f)
        out.append((
            f"koopaL{(f // 9) % 3}" if f < 560 else f"koopa{(f // 9) % 3}",
            kx, BACK_Y, ("right", 132), 1.0, 1.0,
        ))

    # the shell
    if f < 70:
        out.append(("shell", SHELL_X, FRONT_Y, None, 1.0, 1.0))
    elif 174 <= f < 206:
        t = (f - 174) / 32.0
        x0, y0, x1, y1 = stop_x + 2, 42, KOOPA_X - 2, BACK_Y
        x = x0 + (x1 - x0) * t
        y = y0 + (y1 - y0) * t - 16 * np.sin(np.pi * t)
        out.append((f"fly{(f // 3) % 5}", x, y, None, 1.0 - 0.18 * t, 1.0))
    elif variant == "b" and 206 <= f < 246:
        t = (f - 206) / 40.0                     # toward the viewer: it grows, drops toward the middle and fades
        x = KOOPA_X - 4 + (88 - KOOPA_X) * t
        y = BACK_Y + (70 - BACK_Y) * t * t
        out.append((f"fly{(f // 2) % 5}", x, y, None, 0.82 + 4.2 * t * t, 1.0 if t < 0.6 else (1 - t) / 0.4))
    elif variant != "b" and 206 <= f < 251:
        out.append(("land", KOOPA_X + (f - 206) * 0.9, BACK_Y, ("right", PIPE_R + 2), 0.82, 1.0))
    elif f >= P - 60:
        out.append(("shell", lerp_keys([(P - 60, 20), (P - 20, SHELL_X)], f), FRONT_Y, ("left", PIPE_L), 1.0, 1.0))

    # Mario
    walk = lambda x0, x1, f0, f1: (f"walk{(f // 8) % 4}", lerp_keys([(f0, x0), (f1, x1)], f))
    if f < 70:
        cel, x = walk(22, stop_x, 0, 70)
        out.append((cel, x, FRONT_Y, ("left", PIPE_L), 1.0, 1.0))
    elif f < 174:
        t = f - 70
        name = (
            "bend0" if t < 10
            else "bend1" if t < 22
            else "lift" if t < 40
            else ("hold0" if (t // 12) % 2 == 0 else "hold1") if t < 80
            else ("wind0" if t < 92 else "wind1")
        )
        out.append((name, seq_x, FRONT_Y, None, 1.0, 1.0))
    elif f < 206:
        out.append(("throw", seq_x, FRONT_Y, None, 1.0, 1.0))
    elif f < 236:
        out.append(("back", seq_x, FRONT_Y, None, 1.0, 1.0))
    elif f < 326:
        cel, x = walk(stop_x, PIPE_R + 16, 236, 326)
        out.append((cel, x, FRONT_Y, ("right", PIPE_R), 1.0, 1.0))
    elif variant == "c" and 350 <= f < 566:
        # out of the pipe on the back plane, along the back ledge, and into the far pipe
        x = lerp_keys([(350, 148), (566, 26)], f)
        clip = ("right", 132) if x > 120 else ("left", 44)
        out.append((f"bwalk{(f // 9) % 3}", x, BACK_Y, clip, 1.0, 1.0))
    return out


def render(bg, logo_frame, f, celtab, variant="a", pipes=None):
    """Background, then the logo, then the cast, then the pipe mouths over everything they hide."""
    img = bg.copy()
    if logo_frame is not None:
        img.alpha_composite(logo_frame, (0, 0))
    _draw(img, story(f % PASSES[variant], variant), celtab)
    if pipes is not None:
        img.alpha_composite(pipes)
    return img


def _draw(img, items, celtab):
    for name, x, y, clip, scale, alpha in items:
        im, (dx, dy) = celtab[name]
        if scale != 1.0:
            w, h = max(1, round(im.width * scale)), max(1, round(im.height * scale))
            im = im.resize((w, h), Image.NEAREST)
            dx, dy = round(dx * scale), round(dy * scale)
        px, py = int(round(x + dx)), int(round(y + dy))
        if alpha < 1.0:
            a = np.asarray(im).copy()
            a[..., 3] = (a[..., 3] * max(0.0, alpha)).astype(np.uint8)
            im = Image.fromarray(a, "RGBA")
        img.alpha_composite(im, (px, py))


# ------------------------------------------------------------------- logos

def vb_logo(mode="game", pad=2, vpad=4, dot_rows=1):
    """The Virtual Boy logo as every VB game draws it at boot, re-boxed to fit the icon.

    The lettering, the dotted rows and both colors are the capture's own pixels; only the box outline is
    redrawn closer around the lettering and the dotted block keeps its rows nearest the box, centered.
    """
    a = np.asarray(Image.open(os.path.join(CAP, f"vblogo-{mode}.png")).convert("RGBA"))
    top, bot = 16, 54                                   # the box's outline rows in the capture
    line = a[top, a.shape[1] // 2]
    inner = a[top + 1:bot, 1:-1]
    cols = np.nonzero(inner[..., 3].any(axis=0))[0]
    rows = np.nonzero(inner[..., 3].any(axis=1))[0]
    text = inner[rows.min():rows.max() + 1, cols.min():cols.max() + 1]

    th, tw = text.shape[:2]
    bw, bh = tw + 2 * pad + 2, th + 2 * vpad + 2
    dots = np.nonzero(a[0, :, 3])[0]
    src_w = dots.max() + 1 - dots.min()
    block_w = min(src_w, (bw * 2 // 3) // 2 * 2)
    sx0 = dots.min() + (src_w - block_w) // 2

    out = np.zeros((bh + 4 * dot_rows, bw, 4), np.uint8)
    y0 = 2 * dot_rows
    out[y0, :] = line
    out[y0 + bh - 1, :] = line
    out[y0:y0 + bh, 0] = line
    out[y0:y0 + bh, bw - 1] = line
    out[y0 + 1:y0 + bh - 1, 1:bw - 1] = VB_BLACK + (255,)   # the panel is black on the boot screen too

    panel = out[y0 + 1 + vpad:y0 + 1 + vpad + th, 1 + pad:1 + pad + tw]
    panel[text[..., 3] > 0] = text[text[..., 3] > 0]

    bx0 = (bw - block_w) // 2
    for r in range(dot_rows):
        out[y0 - 2 - 2 * r, bx0:bx0 + block_w] = a[top - 2 - 2 * r, sx0:sx0 + block_w]
        out[y0 + bh + 1 + 2 * r, bx0:bx0 + block_w] = a[bot + 2 + 2 * r, sx0:sx0 + block_w]
    return Image.fromarray(out, "RGBA")


def app_logo():
    return Image.open(os.path.join(CAP, "vbcgx-logo.png")).convert("RGBA")


# Tantric's coin flip, frame for frame from the FCE Ultra GX / mGBA GX icons: X scale keys, and the frames the
# texture swaps at (each swap lands when the logo is edge-on).
FLIP_SCALE = [(0, 1), (30, .01), (60, 1), (90, .01), (120, 1), (600, 1), (630, .01), (660, 1), (690, .01),
              (720, 1), (750, .01), (780, 1), (1140, 1), (1170, .01), (1200, 1)]
FLIP_SWAPS = [(0, 0), (30, 1), (90, 0), (630, 1), (690, 0), (750, 1), (1170, 0)]


def smooth_keys(keys, f):
    """Hermite with zero tangents, as the donor's keys are written (each segment eases in and out)."""
    if f <= keys[0][0]:
        return keys[0][1]
    for (f0, v0), (f1, v1) in zip(keys, keys[1:]):
        if f0 <= f <= f1:
            s = (f - f0) / (f1 - f0) if f1 > f0 else 1
            return v0 + (v1 - v0) * (3 * s * s - 2 * s * s * s)
    return keys[-1][1]


def logo_layer(logos, f, center=(88, 22)):
    """The logo pane at frame f: logos[0] is the console logo (Logo00), logos[1] ours (Logo01)."""
    idx = [v for k, v in FLIP_SWAPS if k <= f][-1]
    im = logos[idx]
    sx = smooth_keys(FLIP_SCALE, f % FRAMES)
    w = max(1, round(im.width * sx))
    lay = Image.new("RGBA", (W, H))
    sq = im.resize((w, im.height), Image.BILINEAR)
    lay.alpha_composite(sq, (int(round(center[0] - w / 2)), int(round(center[1] - im.height / 2))))
    return lay
