#!/usr/bin/env python3
"""Writes vbcontroller.svg: the Virtual Boy controller traced from the app's
data/images/icon_settings_vbcontroller.png, mirrored about its center line.

Units are source pixels with u = x - 82.2 (the source's measured axis) and v = y,
so every coordinate below can be checked against the source picture directly.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BANNER = HERE.parents[1] / "banner"

PALETTES = {
    # cool slate, as the source photo has it, lifted a little so it reads on the banner's black
    "slate": dict(
        outline="#f4f4f6", base="#0b0d10",
        face="#2b3338", face_hi="#5f6c75", bevel="#1b2126", groove="#101418",
        rim="#6e7a83", center_lo="#242a2f",
        grip="#1c2125", grip_edge="#2a3238", grip_hi="#3a444b", grip_core="#0f1215",
        grip_spec="#aab4bb", shadow="#040506",
        dpad="#1c2226", dpad_top="#3c464d", dpad_well="#101417",
        btn_ring="#0d1013", grey_hi="#c6cbcf", grey_lo="#6f757b",
        red_hi="#f2525d", red_lo="#a1111e", spec="#ffffff",
        label="#8e979e", logo="#bcc4ca",
        slot="#0b0e10", slider_hi="#d8dcdf", slider_lo="#899095",
        pack_seam="#15181b", pack_lip="#787d80", pack_hi="#676c6f", pack_lo="#54585b",
        pack_band="#54585b", pack_band_lo="#3a3e41",
    ),
    # neutral black plastic, closer to the real controller than the photo's blue cast
    "neutral": dict(
        outline="#f4f4f6", base="#0b0b0c",
        face="#2d2d2f", face_hi="#646468", bevel="#1d1d1f", groove="#111112",
        rim="#77777b", center_lo="#252527",
        grip="#1e1e20", grip_edge="#2c2c2f", grip_hi="#3e3e41", grip_core="#101011",
        grip_spec="#b2b2b6", shadow="#040404",
        dpad="#1e1e20", dpad_top="#434346", dpad_well="#121213",
        btn_ring="#0e0e0f", grey_hi="#cacacd", grey_lo="#747478",
        red_hi="#f24c55", red_lo="#a6101b", spec="#ffffff",
        label="#959599", logo="#c2c2c5",
        slot="#0c0c0d", slider_hi="#dcdcde", slider_lo="#8e8e92",
        pack_seam="#171719", pack_lip="#7b7b7e", pack_hi="#6b6b6e", pack_lo="#58585b",
        pack_band="#58585b", pack_band_lo="#3d3d3f",
    ),
}

OUTLINE_R = 1.25            # sticker rim outside the body, like the mGBA GX banner's console

# Bebas Neue "VIRTUAL BOY", turned into a path by Inkscape; LOGO_BOX is its cap box
LOGO_D = (HERE / "vbcontroller-logo.d").read_text().strip()
LOGO_BOX = (0.336, 8.4, 116.82, 28.0)
LOGO_CENTER, LOGO_SIZE = (0, 44.45), (24.2, 4.5)


def fmt(x):
    s = f"{x:.2f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def pt(p):
    return f"{fmt(p[0])},{fmt(p[1])}"


def mirror(points):
    return [(-p[0], p[1]) + tuple(p[2:]) for p in points]


def spline(points, closed=False):
    """Catmull-Rom through the points as cubic Beziers; a point tagged "c" is a sharp corner."""
    n = len(points)
    get = (lambda i: points[i % n]) if closed else (lambda i: points[max(0, min(n - 1, i))])
    d = [f"M{pt(points[0])}"]
    for i in range(n if closed else n - 1):
        p0, p1, p2, p3 = get(i - 1), get(i), get(i + 1), get(i + 2)
        c1 = p1[:2] if "c" in p1[2:] else (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = p2[:2] if "c" in p2[2:] else (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        d.append(f"C{pt(c1)} {pt(c2)} {pt(p2)}")
    if closed:
        d.append("Z")
    return " ".join(d)


def symmetric(left_half):
    """Closes a left half that runs from the axis round to the axis into a mirrored outline."""
    return spline(left_half + mirror(left_half[1:-1])[::-1], closed=True)


def offset(points, dist, towards):
    """Moves each point dist along its normal, to the side facing the point `towards`."""
    out = []
    for i, p in enumerate(points):
        a, b = points[max(0, i - 1)], points[min(len(points) - 1, i + 1)]
        dx, dy = b[0] - a[0], b[1] - a[1]
        n = (dx * dx + dy * dy) ** 0.5 or 1
        nx, ny = -dy / n, dx / n
        if nx * (towards[0] - p[0]) + ny * (towards[1] - p[1]) < 0:
            nx, ny = -nx, -ny
        out.append((p[0] + nx * dist, p[1] + ny * dist))
    return out


def ribbon(center, widths):
    """A tapered stroke as a filled shape."""
    sides = []
    for sign in (1, -1):
        side = []
        for i, (p, w) in enumerate(zip(center, widths)):
            a, b = center[max(0, i - 1)], center[min(len(center) - 1, i + 1)]
            dx, dy = b[0] - a[0], b[1] - a[1]
            n = (dx * dx + dy * dy) ** 0.5 or 1
            side.append((p[0] - dy / n * w / 2 * sign, p[1] + dx / n * w / 2 * sign))
        sides.append(side)
    return spline(sides[0] + sides[1][::-1], closed=True)


# ---- traced geometry, left half: the source's alpha contour at 80 %, pushed out 0.3 ----

SILHOUETTE = [
    (0, 14.6),      (-6, 14.6),     (-11.8, 14.6),  (-13.5, 14.3),  (-14.9, 13.7),  (-16.7, 12.6),
    (-18.7, 11.35), (-20.7, 10.0),  (-22.7, 8.75),  (-24.7, 7.6),   (-26.7, 6.55),  (-28.7, 5.7),
    (-30.7, 5.2),   (-32.8, 4.95),  (-34.8, 5.0),   (-36.8, 5.4),   (-38.8, 5.95),  (-40.8, 6.75),
    (-42.8, 7.85),  (-44.6, 9.4),   (-46.3, 11.3),  (-47.7, 13.3),  (-48.7, 15.5),  (-49.35, 17.6),
    (-49.55, 19.6), (-49.3, 21.6),  (-48.75, 23.6), (-48.0, 25.6),  (-47.25, 27.6), (-46.55, 29.6),
    (-45.85, 31.6), (-45.2, 33.6),  (-44.9, 35.6),  (-45.05, 37.6), (-45.6, 39.6),  (-46.4, 41.6),
    (-47.3, 43.8),  (-48.3, 46.6),  (-49.4, 50.0),  (-50.5, 54.0),  (-51.4, 58.0),  (-52.1, 62.5),
    (-52.6, 67.0),  (-52.85, 71.5), (-52.75, 76.0), (-52.4, 80.5),  (-51.95, 84.3), (-51.15, 86.8),
    (-49.85, 88.7), (-47.6, 90.15), (-44.7, 90.6),  (-41.9, 90.25), (-39.6, 89.1),  (-37.9, 87.0),
    (-36.9, 84.0),  (-36.25, 79.5), (-35.45, 74.0), (-34.7, 68.5),  (-33.9, 63.0),  (-33.1, 57.0),
    (-32.35, 51.0), (-31.75, 46.5), (-31.1, 44.4),  (-30.0, 43.45), (-28.0, 43.3),  (-21.4, 43.3),
    (-20.1, 43.6),  (-19.6, 44.6),  (-19.55, 48.0), (-19.55, 54.0), (-19.5, 57.2),  (-19.1, 58.4),
    (-18.85, 59.7), (-18.6, 61.0),  (-17.9, 61.95), (-16.8, 62.3),  (-8.0, 62.3),   (0, 62.3),
]

# the shell's lower edge: under the lobes, then round the logo plate to the axis
BODY_BOTTOM = [
    (-56, 29.6, "c"), (-45.6, 31.7), (-43.6, 34.0), (-41.2, 35.9), (-38.0, 37.1), (-34.0, 37.8),
    (-29.0, 38.25), (-24.0, 38.35), (-20.6, 38.2), (-19.55, 38.7, "c"), (-19.55, 48.6, "c"),
    (0, 48.6),
]
BODY = [(0, -2), (-56, -2, "c")] + BODY_BOTTOM

# the groove round each lobe: outer-lower edge, then the inner edge rising toward the axis
GROOVE_OUTER = [
    (-46.6, 26.4), (-44.6, 29.0), (-42.5, 30.9), (-39.4, 32.5), (-35.0, 33.85), (-30.0, 35.0),
    (-25.0, 36.1), (-21.2, 37.1), (-18.0, 37.75), (-13.0, 37.85),
]
GROOVE_INNER = [
    (-13.0, 37.85), (-10.0, 36.8), (-7.4, 35.25), (-5.25, 33.5), (-3.75, 31.4), (-3.0, 29.0),
    (-2.8, 26.0), (-2.85, 22.6),
]
LOBE = GROOVE_OUTER[:-1] + GROOVE_INNER + [
    (-4.5, 18.0), (-9.0, 12.0, "c"), (-9.0, -2.0, "c"), (-60.0, -2.0, "c"), (-60.0, 24.0, "c"),
]
# the lobe's darker underside band, between the groove and the shell's lower edge
BEVEL = GROOVE_OUTER[:-1] + [
    (-18.0, 38.45), (-24.0, 38.65), (-29.0, 38.55), (-34.0, 38.1), (-38.0, 37.4), (-41.2, 36.2),
    (-43.6, 34.3), (-45.6, 32.0), (-56, 29.9, "c"), (-56, 24.0, "c"),
]

# the grip's inner edge is real; its outside runs past the silhouette and gets clipped
GRIP = [
    (-29.4, 28.0, "c"), (-29.9, 36.5), (-30.4, 40.5), (-30.8, 42.9), (-29.6, 44.6), (-30.3, 51.0),
    (-31.9, 63.0), (-33.6, 74.0), (-34.9, 82.0), (-35.2, 95.0, "c"), (-62, 95.0, "c"),
    (-62, 28.0, "c"),
]
GRIP_SPEC_LOW = [(-45.0, 59.5), (-45.4, 66.0), (-45.5, 72.0), (-45.3, 77.5), (-44.7, 82.8)]
GRIP_SPEC_TOP = [(-43.9, 34.5), (-43.6, 39.0), (-43.6, 44.0), (-44.1, 49.0), (-44.6, 54.0)]

TOP_RIM = offset(SILHOUETTE[:24], 0.62, (0, 30))

DPAD = (-34.5, 18.6)         # left pad's center; the right pad is its mirror
DPAD_ARM, DPAD_HALF = 2.35, 6.75
SELECT, START = (-21.3, 23.9), (-13.2, 27.05)
BUTTON_R = 2.7
LABEL_OFFSET = (2.25, -4.25)  # labels sit up and toward the axis from their buttons
TILT = 22.6                   # slope of the button row, which the word labels follow


def stops(*items):
    return "".join(f'<stop offset="{fmt(o)}" stop-color="{c}"' +
                   (f' stop-opacity="{fmt(a)}"' if a != 1 else "") + "/>" for o, c, a in items)


def cross(cx, cy, arm, half, r, fill):
    return (f'<rect x="{fmt(cx - half)}" y="{fmt(cy - arm)}" width="{fmt(2 * half)}" height="{fmt(2 * arm)}" '
            f'rx="{fmt(r)}" fill="{fill}"/>'
            f'<rect x="{fmt(cx - arm)}" y="{fmt(cy - half)}" width="{fmt(2 * arm)}" height="{fmt(2 * half)}" '
            f'rx="{fmt(r)}" fill="{fill}"/>')


def button(p, center, gradient):
    x, y = center
    sx, sy = x - 0.85, y - 1.05
    return (f'<circle cx="{fmt(x)}" cy="{fmt(y + 0.25)}" r="{fmt(BUTTON_R + 0.7)}" fill="{p["btn_ring"]}"/>'
            f'<circle cx="{fmt(x)}" cy="{fmt(y)}" r="{fmt(BUTTON_R)}" fill="url(#{gradient})"/>'
            f'<ellipse cx="{fmt(sx)}" cy="{fmt(sy)}" rx="1.05" ry="0.7" transform="rotate(-28 {fmt(sx)} {fmt(sy)})" '
            f'fill="{p["spec"]}" fill-opacity="0.75"/>')


def word_label(p, center, length):
    x, y = center[0] + LABEL_OFFSET[0], center[1] + LABEL_OFFSET[1]
    return (f'<rect x="{fmt(x - length / 2)}" y="{fmt(y - 0.5)}" width="{fmt(length)}" height="1" rx="0.5" '
            f'transform="rotate({fmt(TILT)} {fmt(x)} {fmt(y)})" fill="{p["label"]}"/>')


def letter_label(p, center):
    x, y = -center[0] - LABEL_OFFSET[0], center[1] + LABEL_OFFSET[1] + 0.35
    return (f'<rect x="{fmt(x - 0.7)}" y="{fmt(y - 0.75)}" width="1.4" height="1.5" rx="0.35" '
            f'fill="{p["label"]}"/>')


def build(p):
    du, dv = DPAD
    grip = spline(GRIP, closed=True)
    lobe = spline(LOBE, closed=True)
    rim = spline(TOP_RIM[::-1] + mirror(TOP_RIM[1:]))
    lx0, ly0, lx1, ly1 = LOGO_BOX
    sx, sy = LOGO_SIZE[0] / (lx1 - lx0), LOGO_SIZE[1] / (ly1 - ly0)
    logo_tf = (f"translate({fmt(LOGO_CENTER[0] - (lx0 + lx1) / 2 * sx)},"
               f"{fmt(LOGO_CENTER[1] - (ly0 + ly1) / 2 * sy)}) scale({sx:.5f},{sy:.5f})")

    return f'''<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"
     width="448" height="360" viewBox="-56 3 112 90">
  <title>Virtual Boy controller</title>
  <defs>
    <path id="silhouette" d="{symmetric(SILHOUETTE)}"/>
    <clipPath id="inside"><use xlink:href="#silhouette"/></clipPath>
    <clipPath id="grip-area"><path d="{grip}"/></clipPath>
    <clipPath id="lobe-area"><path d="{lobe}"/></clipPath>

    <radialGradient id="lobe-light" gradientUnits="userSpaceOnUse" cx="-35" cy="12" r="20"
                    gradientTransform="translate(-35 12) scale(1.25 1) translate(35 -12)">
      {stops((0, p["face_hi"], 0.75), (0.55, p["face_hi"], 0.25), (1, p["face_hi"], 0))}
    </radialGradient>
    <linearGradient id="shell" gradientUnits="userSpaceOnUse" x1="0" y1="20" x2="0" y2="48.6">
      {stops((0, p["face"], 1), (1, p["center_lo"], 1))}
    </linearGradient>
    <linearGradient id="grip-shade" gradientUnits="userSpaceOnUse" x1="-53.5" y1="62" x2="-33" y2="59.5">
      {stops((0, p["grip_edge"], 1), (0.1, p["grip"], 1), (0.33, p["grip_hi"], 1),
             (0.55, p["grip"], 1), (0.8, p["grip_core"], 1), (1, p["grip"], 1))}
    </linearGradient>
    <radialGradient id="grip-tuck">
      {stops((0, p["shadow"], 0.95), (0.6, p["shadow"], 0.7), (1, p["shadow"], 0))}
    </radialGradient>
    <linearGradient id="spec-low" gradientUnits="userSpaceOnUse" x1="0" y1="59.5" x2="0" y2="83">
      {stops((0, p["grip_spec"], 0), (0.35, p["grip_spec"], 0.8), (0.8, p["grip_spec"], 0.9),
             (1, p["grip_spec"], 0))}
    </linearGradient>
    <linearGradient id="spec-top" gradientUnits="userSpaceOnUse" x1="0" y1="34" x2="0" y2="54">
      {stops((0, p["grip_spec"], 0), (0.4, p["grip_spec"], 0.8), (1, p["grip_spec"], 0))}
    </linearGradient>
    <linearGradient id="rim-fade" gradientUnits="userSpaceOnUse" x1="-50" y1="0" x2="50" y2="0">
      {stops((0, p["rim"], 0), (0.08, p["rim"], 0.9), (0.92, p["rim"], 0.9), (1, p["rim"], 0))}
    </linearGradient>
    <linearGradient id="groove-fade" gradientUnits="userSpaceOnUse" x1="0" y1="22.4" x2="0" y2="28">
      {stops((0, p["groove"], 0), (1, p["groove"], 1))}
    </linearGradient>
    <linearGradient id="dpad-face" gradientUnits="userSpaceOnUse" x1="0" y1="{fmt(dv - DPAD_HALF)}"
                    x2="0" y2="{fmt(dv + DPAD_HALF)}">
      {stops((0, p["dpad_top"], 1), (0.45, p["dpad"], 1), (1, p["dpad"], 1))}
    </linearGradient>
    <linearGradient id="grey" x1="0" y1="0" x2="0" y2="1">{stops((0, p["grey_hi"], 1), (1, p["grey_lo"], 1))}</linearGradient>
    <linearGradient id="red" x1="0" y1="0" x2="0" y2="1">{stops((0, p["red_hi"], 1), (1, p["red_lo"], 1))}</linearGradient>
    <linearGradient id="slider" x1="0" y1="0" x2="0" y2="1">{stops((0, p["slider_hi"], 1), (1, p["slider_lo"], 1))}</linearGradient>
    <linearGradient id="pack" gradientUnits="userSpaceOnUse" x1="0" y1="50.4" x2="0" y2="57.85">
      {stops((0, p["pack_lo"], 1), (1, p["pack_hi"], 1))}
    </linearGradient>

    <g id="grip">
      <path d="{grip}" fill="url(#grip-shade)"/>
      <g clip-path="url(#grip-area)">
        <ellipse cx="-33.5" cy="37.5" rx="11" ry="8.5" fill="url(#grip-tuck)"/>
        <path d="{ribbon(GRIP_SPEC_LOW, [0.2, 1.0, 1.35, 1.2, 0.3])}" fill="url(#spec-low)"/>
        <path d="{ribbon(GRIP_SPEC_TOP, [0.3, 1.0, 1.1, 0.8, 0.2])}" fill="url(#spec-top)"/>
      </g>
    </g>

    <g id="lobe">
      <path d="{lobe}" clip-path="url(#lobe-area)" fill="url(#lobe-light)"/>
      <path d="{spline(BEVEL, closed=True)}" fill="{p["bevel"]}"/>
      <path d="{spline(GROOVE_OUTER)}" fill="none" stroke="{p["groove"]}" stroke-width="0.65" stroke-linecap="round"/>
      <path d="{spline(GROOVE_INNER)}" fill="none" stroke="url(#groove-fade)" stroke-width="0.6" stroke-linecap="round"/>
      {cross(du, dv + 0.2, DPAD_ARM + 0.7, DPAD_HALF + 0.7, 1.1, p["dpad_well"])}
      {cross(du, dv, DPAD_ARM, DPAD_HALF, 0.7, "url(#dpad-face)")}
      <circle cx="{fmt(du)}" cy="{fmt(dv)}" r="1.15" fill="{p["dpad"]}" stroke="{p["dpad_well"]}" stroke-width="0.35"/>
    </g>
  </defs>

  <use xlink:href="#silhouette" fill="{p["outline"]}" stroke="{p["outline"]}"
       stroke-width="{fmt(2 * OUTLINE_R)}" stroke-linejoin="round"/>
  <use xlink:href="#silhouette" fill="{p["base"]}"/>

  <g clip-path="url(#inside)">
    <use xlink:href="#grip"/>
    <use xlink:href="#grip" transform="scale(-1 1)"/>

    <path d="{symmetric(BODY)}" fill="url(#shell)"/>
    <use xlink:href="#lobe"/>
    <use xlink:href="#lobe" transform="scale(-1 1)"/>
    <path d="{rim}" fill="none" stroke="url(#rim-fade)" stroke-width="0.7" stroke-linecap="round"/>
    <path d="M-12.6,15.75 H12.6" stroke="{p["groove"]}" stroke-width="0.5" stroke-linecap="round" stroke-opacity="0.85"/>

    <rect x="-21" y="48.4" width="42" height="0.85" fill="{p["pack_seam"]}"/>
    <rect x="-21" y="49.25" width="42" height="1.15" fill="{p["pack_lip"]}"/>
    <rect x="-21" y="50.4" width="42" height="7.45" fill="url(#pack)"/>
    <rect x="-21" y="57.85" width="42" height="0.6" fill="{p["pack_band_lo"]}"/>
    <rect x="-21" y="58.45" width="42" height="5" fill="{p["pack_band"]}"/>
    <path d="M-19.05,38.6 V57.85 M19.05,38.6 V57.85" stroke="{p["groove"]}" stroke-width="0.9"/>

    <rect x="-6.45" y="16.55" width="12.9" height="3.6" rx="1.6" fill="{p["slot"]}"/>
    <rect x="-4.6" y="17.1" width="9.2" height="2.5" rx="1.1" fill="url(#slider)"/>

    {button(p, SELECT, "grey")}
    {button(p, START, "grey")}
    {button(p, mirror([SELECT])[0], "red")}
    {button(p, mirror([START])[0], "red")}
    {word_label(p, SELECT, 6.4)}
    {word_label(p, START, 5.4)}
    {letter_label(p, SELECT)}
    {letter_label(p, START)}

    <path transform="{logo_tf}" fill="{p["logo"]}" d="{LOGO_D}"/>
  </g>
</svg>
'''


if __name__ == "__main__":
    for name in sys.argv[1:] or ["slate"]:
        target = BANNER / ("vbcontroller.svg" if name == "slate" else f"vbcontroller-{name}.svg")
        target.write_text(build(PALETTES[name]))
        print("wrote", target)
