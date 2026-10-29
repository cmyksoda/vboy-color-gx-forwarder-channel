"""Texture packing choices for this channel's art.

Format picking is not cosmetic here -- the icon has a hard 102,400-byte cap and
the banner a soft memory budget, and a rotating background is a big texture.

* **spiral -> CI4.** The spiral is two colors plus antialiasing, and
  `spiral.render(levels=15)` caps it at exactly 16 distinct colors, so a
  16-entry palette holds every one of them with **no colors merged** at 4 bits
  per pixel. 960x960 costs 460,800 bytes instead of 1,843,200 as RGBA8, which is
  what makes a full-coverage spinning background affordable. If the color count
  ever exceeds 16 this falls back to CI8 rather than silently degrading.

  It is not bit-exact, and the check below does not claim it is: TPL palette
  entries are themselves stored as RGB5A3, so each entry lands within 5-bit
  precision of the original (max error 6/255 measured here, against 7/255 for
  RGB565 -- the format the previous project's background shipped in). What CI4
  *does* guarantee exactly is the index structure: no two distinct source
  colors collapse into one, so no banding is introduced on top of that.

* **sprites -> RGB5A3.** The console photo and the logo need alpha, and RGB5A3
  is what Tantric's own `Logo.tpl` and `Controller.tpl` use, so the System Menu
  demonstrably renders it. Its alpha is 3-bit, which is coarse in principle but
  is exactly what ships in every stock channel banner.

* **unused donor textures -> 4x4 stubs that keep their names.** Every entry in
  the layout's texture list and every RLTP reference in a brlan must still
  resolve, so the files stay; only their contents shrink. A flat 4x4 stretched
  over a pane is also how the donor's own solid-color fills work, so this is
  not a hack.
"""

import numpy as np
from PIL import Image

import tpl as T

STUB = (4, 4)


RGB5A3_MAX_ERR = 8              # 5 bits per channel: worst case 255/31/2 rounded up


CI8_MAX_MEAN_ERR = 6.0          # per channel, alpha-weighted


def ci8_sprite_tpl(img, colors=256):
    """Halve a sprite's cost by palettising it: 1 byte/px + 512 vs 2 bytes/px.

    Banner memory is shared across *every installed channel*, so a sprite that
    survives palettisation should be palettised. Measured on this art the cost is
    negligible -- mean error 2.5/255 for the console photo and 1.7/255 for the
    logo -- because both are a narrow palette to begin with (a grey console, and
    black text with a white outline over one red sphere).

    Alpha comes along: TPL palette entries are RGB5A3, so partially transparent
    antialiased edges survive. Pillow's FASTOCTREE is used because it is the one
    Pillow quantiser that considers the alpha channel.
    """
    assert img.size[0] % 4 == 0 and img.size[1] % 4 == 0, \
        f"{img.size} is not 4-aligned; GX tiles are 4x4"
    im = img.convert("RGBA")
    q = im.quantize(colors=colors, method=Image.Quantize.FASTOCTREE)
    raw = q.getpalette("RGBA")
    pal = [tuple(raw[i * 4:i * 4 + 4]) for i in range(colors)]
    idx = np.asarray(q, dtype=np.uint8)

    # error on premultiplied color, so transparent padding cannot flatter it
    a = np.asarray(im, np.int16)
    p = np.asarray(pal, np.int16)[idx]
    err = np.abs(a[:, :, :3] * (a[:, :, 3:4] / 255.0)
                 - p[:, :, :3] * (p[:, :, 3:4] / 255.0))
    mean = float(err.mean())
    assert mean <= CI8_MAX_MEAN_ERR, (
        f"CI8 mean error {mean:.2f} exceeds {CI8_MAX_MEAN_ERR}; this sprite needs "
        f"RGB5A3")
    return T.build([(idx.tolist(), T.CI8, pal, im.size)]), mean


# Bayer 8x8 ordered-dither matrix. Ordered rather than error-diffusing on
# purpose: a serpentine Floyd-Steinberg over a pure vertical gradient makes
# directional worm artifacts, while the Bayer pattern is stationary, survives
# GX's bilinear stretch, and reads as clean film grain at TV distance.
_BAYER8 = [
    [0, 32, 8, 40, 2, 34, 10, 42],
    [48, 16, 56, 24, 50, 18, 58, 26],
    [12, 44, 4, 36, 14, 46, 6, 38],
    [60, 28, 52, 20, 62, 30, 54, 22],
    [3, 35, 11, 43, 1, 33, 9, 41],
    [51, 19, 59, 27, 49, 17, 57, 25],
    [15, 47, 7, 39, 13, 45, 5, 37],
    [63, 31, 55, 23, 61, 29, 53, 21],
]


