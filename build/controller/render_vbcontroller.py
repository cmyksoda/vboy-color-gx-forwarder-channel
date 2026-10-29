#!/usr/bin/env python3
"""Renders banner/vbcontroller.svg to the PNG the banner uses, with Inkscape (never by resizing a raster).

  render_vbcontroller.py [svg-name ...]     default: vbcontroller

The PNG is named by the controller's own width (sticker rim included) and gets a transparent
margin of at least 4 px, rounded up to whole GX tiles (width to 8, height to 4).
"""
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
BANNER = HERE.parents[1] / "banner"
WIDTHS = (148,)
MARGIN = 4


def inkscape_png(svg_text, out, width, height):
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "in.svg"
        src.write_text(svg_text)
        subprocess.run(["nice", "-n", "15", "inkscape", str(src), "--export-type=png",
                        f"--export-filename={out}", "--export-area-page",
                        f"--export-width={width}", f"--export-height={height}"],
                       check=True, capture_output=True)


def with_view(svg_text, width, height, view):
    return re.sub(r'width="[^"]*"\s+height="[^"]*"\s+viewBox="[^"]*"',
                  f'width="{width}" height="{height}" viewBox="{" ".join(f"{v:.4f}" for v in view)}"',
                  svg_text, count=1)


def drawing_box(svg_text):
    """The drawing's bounds in SVG units, measured from a 16x render's alpha."""
    vx, vy, vw, vh = map(float, re.search(r'viewBox="([^"]*)"', svg_text).group(1).split())
    k = 16
    with tempfile.TemporaryDirectory() as tmp:
        png = Path(tmp) / "probe.png"
        inkscape_png(with_view(svg_text, int(vw * k), int(vh * k), (vx, vy, vw, vh)), png, int(vw * k), int(vh * k))
        a = np.asarray(Image.open(png))[:, :, 3]
    ys, xs = np.nonzero(a > 0)
    return vx + xs.min() / k, vy + ys.min() / k, vx + (xs.max() + 1) / k, vy + (ys.max() + 1) / k


def bleed(png, rgb):
    """Gives (nearly) transparent pixels the rim's color, so filtered edges never pick up black."""
    im = np.asarray(Image.open(png).convert("RGBA")).copy()
    im[im[:, :, 3] < 16, :3] = rgb
    Image.fromarray(im, "RGBA").save(png, optimize=True)


def render_sizes(name):
    svg_text = (BANNER / f"{name}.svg").read_text()
    x0, y0, x1, y1 = drawing_box(svg_text)
    outline = re.search(r'<use xlink:href="#silhouette" fill="#(\w{6})"', svg_text).group(1)
    rim = tuple(int(outline[i:i + 2], 16) for i in (0, 2, 4))
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    made = []
    for w in WIDTHS:
        s = w / (x1 - x0)
        cw = -(-(w + 2 * MARGIN) // 8) * 8
        ch = -(-(round((y1 - y0) * s) + 2 * MARGIN) // 4) * 4
        view = (cx - cw / s / 2, cy - ch / s / 2, cw / s, ch / s)
        out = BANNER / f"{name}-{w}.png"
        inkscape_png(with_view(svg_text, cw, ch, view), out, cw, ch)
        bleed(out, rim)
        made.append((out, cw, ch))
        print(f"  {out.name}: {cw}x{ch}, controller {w}x{round((y1 - y0) * s)}")
    return made


if __name__ == "__main__":
    for name in sys.argv[1:] or ["vbcontroller"]:
        render_sizes(name)
