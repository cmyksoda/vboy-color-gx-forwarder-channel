"""Icon A, second version: Mario Clash's real stage, layered the way the game draws it, with a view that
follows the action between the ledges.

The stage is the game's own (rebuilt from VBoy Color's frames) with the ledge middles squeezed out and each
diagonal pipe shortened by DIAG_CUT rows of straight sweep. Every stage pixel keeps the Virtual Boy world
that drew it (read from the core's tags), so the stage splits into the layers the actors pass between and
covers each actor exactly as the game does. Speeds and timings are the game's, converted to 60 Hz.
"""

import functools
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(__file__))
import icon_scene as S

W, H = S.W, S.H
VOID = S.VB_BLACK
STAGE_Y0, STAGE_Y1 = 94, 214         # stage rows kept: from the back tubes' tops to the front ledge's bricks
DIAG_CUT = 24                        # rows taken out of each diagonal pipe
# Each side: the stage columns it comes from, the first cut row, and where its front mouth's inner rim lands
SIDES = {
    "right": dict(x0=250, x1=384, cut=128, rim_stage=345, rim_icon=140),
    "left": dict(x0=0, x1=134, cut=128, rim_stage=34, rim_icon=36),
}
FRONT_FEET_STAGE, BACK_FEET_STAGE = 199, 122
BACK_LEDGE_END = 160                 # the back ledge's brick face fades out by this stage row
WORLDS = os.path.join(S.CAP, "stage-worlds-m0.npy")
# Stage layers by world, back to front ([lo, hi)); lower worlds draw in front. Front-plane sprites are
# world 8, back-plane 19, knocked enemies 28.
LAYERS = (("wall", 29, 31), ("far", 20, 28), ("back", 9, 19), ("front", 1, 8))
# each actor is drawn right after the layer named here, so every later layer covers it
ACTOR_LAYER = {"tumble": "wall", "koopa": "far", "shell_b": "far", "mario_b": "far",
               "fly": "back", "shell_f": "back", "mario_c": "back", "mario_f": "back"}
# mario_c plays the game's pickup and throw frames; mario_f walks (they hang from different anchors)
ACTORS = tuple(ACTOR_LAYER)

VB_HZ = 50.27
TO60 = 60 / VB_HZ                    # game frames -> Wii frames
V_FRONT = 2 / TO60                   # Mario's walk on the front ledge, 2 px a game frame
V_BACK = 0.75 / TO60                 # ... and on the back ledge
V_ENEMY = 0.32 / TO60                # a back-ledge enemy's walk
WALK_CEL = 4 * TO60                  # a walk cel lasts 4 game frames
ENEMY_CEL = 8 * TO60
TRANSIT = round(20 * TO60)           # inside a pipe for 20 game frames
SPAWN_SHOWN = 14 / 19                # the game puts a traveler back out with this much of him past the tube
ENTRY_SHOWN = {"walk": 10, "bwalk": 9}  # ... and takes him off once only this many columns still show going in


def stage(mode):
    return np.asarray(Image.open(os.path.join(S.CAP, f"stage-clean-m{mode}.png")).convert("RGBA")).copy()


def prepare(st, wm):
    """The spawn platform's last rows above the right back mouth go, and the back ledge's brown marks."""
    st, wm = st.copy(), wm.copy()
    st[90:96, 305:384, :3] = VOID
    wm[90:96, 305:384] = 0
    rows = st[116:141]
    warm = (rows[..., 0].astype(int) > rows[..., 2].astype(int) + 30) & (rows[..., 1] < 140)
    rows[warm] = st[122, 200]
    return st, wm


def diag_shift(st, side):
    """How far the upper part of a side moves sideways so its diagonal pipe stays continuous across the cut."""
    green = (st[..., 1].astype(int) > st[..., 0].astype(int) + 25) & (st[..., 1] > 60)
    cfg = SIDES[side]
    c0, c1 = cfg["cut"], cfg["cut"] + DIAG_CUT

    def edge(y):
        xs = np.nonzero(green[y, cfg["x0"]:cfg["x1"]])[0] + cfg["x0"]
        return int(xs[xs >= 300].min()) if side == "right" else int(xs[xs <= 80].max())

    return edge(c1) - edge(c0)


def best_seam(st, rows, lo, hi, off):
    """The stage column in [lo, hi) where the left piece can hand over to the right piece (off columns
    further on in the stage) with the least visible step."""
    a = st[rows[0]:rows[1], :, :3].astype(int)
    cost = [np.abs(a[:, x] - a[:, x + off]).sum() for x in range(lo, hi)]
    return lo + int(np.argmin(cost))


@functools.lru_cache(maxsize=None)
def build(mode=0):
    """(layers, composite, geo): the strip's world layers (RGBA, strip-sized), all of them over the void,
    and where things are on the strip. Each side's pieces come from their own stage columns, so neither side
    ever draws over the other; the two meet at one seam per ledge, where the game's pixels match best."""
    st, wm = prepare(stage(mode), np.load(WORLDS))
    rows_upper = SIDES["right"]["cut"] - STAGE_Y0
    strip_h = (STAGE_Y1 - STAGE_Y0) - DIAG_CUT
    img = np.zeros((strip_h, W, 4), np.uint8)
    wld = np.zeros((strip_h, W), int)

    def paste(y0s, y1s, x0s, x1s, dx, dy, skip=()):
        """Stage rows [y0s, y1s) and columns [x0s, x1s) to the strip, at icon x = stage x + dx, row + dy."""
        for y in range(y0s, y1s):
            Y = y + dy
            if not 0 <= Y < strip_h:
                continue
            for x in range(x0s, x1s):
                X = x + dx
                if 0 <= X < W and wm[y, x] > 0 and wm[y, x] not in skip:
                    img[Y, X] = st[y, x]
                    wld[Y, X] = wm[y, x]

    shifts = {side: diag_shift(st, side) for side in SIDES}
    lo_dx = {side: cfg["rim_icon"] - cfg["rim_stage"] for side, cfg in SIDES.items()}
    up_dx = {side: lo_dx[side] + shifts[side] for side in SIDES}
    up_off, lo_off = up_dx["left"] - up_dx["right"], lo_dx["left"] - lo_dx["right"]
    cut = SIDES["right"]["cut"]

    seam_up = best_seam(st, (STAGE_Y0, BACK_LEDGE_END), 96, 124, up_off)
    seam_lo = best_seam(st, (cut + DIAG_CUT, STAGE_Y1), 96, 124, lo_off)
    dy_up, dy_lo = -STAGE_Y0, rows_upper - (cut + DIAG_CUT)

    # the back half: wall, back ledge, back mouths, the tops of the diagonals
    paste(STAGE_Y0, cut, 0, seam_up, up_dx["left"], dy_up)
    paste(STAGE_Y0, cut, seam_up + up_off, 384, up_dx["right"], dy_up)
    # between the diagonals the cut falls in the empty rows under the ledge instead, so its brick face stays whole
    paste(cut, BACK_LEDGE_END, 60, seam_up, up_dx["left"], dy_up)
    paste(cut, BACK_LEDGE_END, seam_up + up_off, 300, up_dx["right"], dy_up)
    # the front half: the rest of the diagonals, the front mouths and the front ledge
    paste(cut + DIAG_CUT, STAGE_Y1, 0, seam_lo, lo_dx["left"], dy_lo, skip=(22,))
    paste(cut + DIAG_CUT, STAGE_Y1, seam_lo + lo_off, 384, lo_dx["right"], dy_lo, skip=(22,))

    layers = {}
    for name, lo, hi in LAYERS:
        a = np.zeros_like(img)
        m = (wld >= lo) & (wld < hi)
        a[m] = img[m]
        a[m, 3] = 255
        layers[name] = Image.fromarray(a, "RGBA")

    comp = Image.new("RGBA", (W, strip_h), VOID + (255,))
    for name, _, _ in LAYERS:
        comp.alpha_composite(layers[name])

    geo = dict(front_feet=FRONT_FEET_STAGE - STAGE_Y0 - DIAG_CUT, back_feet=BACK_FEET_STAGE - STAGE_Y0,
               height=strip_h, back_l=72 + up_dx["left"], back_r=295 + up_dx["right"],
               seam_up=seam_up + up_dx["left"], seam_lo=seam_lo + lo_dx["left"])
    return layers, comp, geo


# ------------------------------------------------------------- what covers what

def cover_mask(slot, mode=0):
    """Where the layers above an actor's slot cover it (strip-sized boolean)."""
    layers, _, geo = build(mode)
    order = [n for n, _, _ in LAYERS]
    m = np.zeros((geo["height"], W), bool)
    for n in order[order.index(slot) + 1:]:
        m |= np.asarray(layers[n])[..., 3] > 0
    return m


def shown_columns(cel, x, y, cover):
    """Columns of a cel left showing at feet (x, y) once the covering layers are over it (off-icon is hidden)."""
    im, (dx, dy) = cel
    a = np.asarray(im)[..., 3] > 0
    x0, y0 = int(round(x + dx)), int(round(y + dy))
    shown = 0
    for cx in range(a.shape[1]):
        X = x0 + cx
        if not 0 <= X < W:
            continue
        for cy in np.nonzero(a[:, cx])[0]:
            Y = y0 + cy
            if not 0 <= Y < cover.shape[0] or not cover[Y, X]:
                shown += 1
                break
    return shown


def spawn_x(cel, y, cover, mouth, into):
    """Where a traveler comes back out of a mouth: hidden just inside it, then out until enough shows."""
    inside = first_x(cel, y, cover, mouth, into, lambda shown, w: shown == 0)
    return first_x(cel, y, cover, inside, -into, lambda shown, w: shown >= SPAWN_SHOWN * w)


def entry_frames(celtab, prefix, n, x0, v, y, cover):
    """Frames of walking (from x0 at v px a frame) until the game takes the traveler off at the mouth."""
    u = 0
    while shown_columns(celtab[walk_cel(prefix, n, u)], x0 + v * u, y, cover) >= ENTRY_SHOWN[prefix]:
        u += 1
        assert u < 1000, "never reached the mouth"
    return u


def first_x(cel, y, cover, start, step, pred):
    x = start
    while not pred(shown_columns(cel, x, y, cover), cel[0].width):
        x += step
        assert abs(x - start) < 300, "never reached"
    return x


# ------------------------------------------------------------- the game's own clips

CLIPS = os.path.join(S.CAP, "w1-clips.json")
FIGS = [os.path.join(S.CAP, run, "figs") for run in ("w1x", "w1y")]
SHELL_CX = 269                       # the shell's center in the clip run; the icon mirrors the clip about it
MIRROR_TO = 86                       # ... onto the shell's spot in the icon (SHELL_X)
FRONT_DY = -(STAGE_Y0 + DIAG_CUT)    # stage rows -> strip rows on the front ledge
GAME_ROWS = {"pick": (1409, 1461), "flight": (1455, 1471), "knock": (1472, 1501), "wobble": (1354, 1371)}


@functools.lru_cache(maxsize=None)
def figure(h):
    for d in FIGS:
        for f in os.listdir(d):
            if f.startswith(h):
                return Image.open(os.path.join(d, f)).convert("RGBA").transpose(Image.FLIP_LEFT_RIGHT)
    raise KeyError(h)


@functools.lru_cache(maxsize=None)
def clips():
    """Per game frame: (figure hash, mirrored left, top) for Mario's pickup and throw, the flight, the knock and
    the resting shell's wobble, in strip coordinates (the flight and knock still need their end points)."""
    raw = __import__("json").load(open(CLIPS))
    out = {}
    for key, name in (("pick", "mario"), ("flight", "flight"), ("knock", "knock"), ("wobble", "shell")):
        g0, g1 = GAME_ROWS[key]
        seq = {}
        for f, h, x, y, w, hh, run in raw[name]:
            if g0 <= f <= g1 and f not in seq:
                seq[f] = (h[:4], x, y, w, hh)
        out[key] = seq
    # the first flight frames are partly behind Mario (world 11 is behind his world 8): the whole first cel,
    # on the line the later frames fly
    fl = out["flight"]
    for g in (1455, 1456, 1457):
        x, y = fl[1458][1] + 2 * (1458 - g), fl[1458][2] + 3 * (1458 - g)
        fl[g] = ("e4df", x, y, 12, 12)
    kn = out["knock"]                # 1475 was not drawn whole that frame; the last three are cut by the ledge
    kn[1475] = ("dd4c", (kn[1474][1] + kn[1476][1]) // 2, (kn[1474][2] + kn[1476][2]) // 2, 11, 8)
    for g, dy in ((1499, 4), (1500, 9), (1501, 14)):
        kn[g] = ("d5d0", kn[1498][1], kn[1498][2] + dy, 7, 8)
    return out


def clips_walk_end():
    """Mario's last walking frame before he bends for the shell (game frame 1408)."""
    for f, h, x, y, w, hh, run in __import__("json").load(open(CLIPS))["mario"]:
        if f == 1408:
            return (h[:4], x, y, w, hh)
    raise KeyError(1408)


def mirror_x(x, w):
    return SHELL_CX - x - w + MIRROR_TO


def clip_frame(key, u):
    """The clip frame showing u Wii frames after the clip starts, or None once it is over."""
    seq = clips()[key]
    g0, g1 = min(seq), max(seq)
    g = g0 + int(u / TO60)
    return seq.get(g) if g <= g1 else None


def clip_len(key):
    seq = clips()[key]
    return int(np.ceil((max(seq) - min(seq) + 1) * TO60))


def cels():
    """The icon's cel table: the captured cels plus every clip figure (anchored at its top-left)."""
    c = dict(S.cels())
    for seq in clips().values():
        for h, *_ in seq.values():
            c.setdefault("g" + h, (figure(h), (0, 0)))
    return c


# ------------------------------------------------------------- the story

SHELL_X = 86                         # the shell's spot on the front ledge
CAM_FRONT, CAM_BACK = 4, -38         # strip row at the icon's top: front feet at 77, back feet at 66
KOOPA_LEFT, KOOPA_RIGHT = 65, 103    # the waiting Koopa turns round before the back pipes would hide any of it
TANTRIC = True                       # Tantric's 20-second loop and flips (Jaxi approved the mock-up, 28 Oct)
LOOP_FRAMES = 1200                   # Tantric's icon loop (FCE Ultra GX and mGBA GX)
HOLD_BACK = 20                       # calm time: the view stays on the back ledge after the knock
HOLD_POSE = 40                       # ... Mario stands in his throwing pose before he walks off
FRONT_TIME = 490                     # ... and the view comes back to the front this long before the loop ends
SHELL_BACK = 420                     # the next shell slides out of the right pipe this long before the end


def ease(t):
    t = min(1.0, max(0.0, t))
    return t * t * (3 - 2 * t)


def walk_cel(prefix, n, t, every=WALK_CEL):
    return f"{prefix}{int(t // every) % n}"


def plan(mode=0):
    return _plan(mode, TANTRIC)


@functools.lru_cache(maxsize=None)
def _plan(mode, tantric):
    """Every event's frame and every traveler's spawn and hide positions, worked out from the layers."""
    _, _, geo = build(mode)
    c = S.cels()
    FY, BY = geo["front_feet"], geo["back_feet"]
    front, back = cover_mask("back", mode), cover_mask("far", mode)
    hidden = lambda shown, w: shown == 0
    p = {}

    # front-left mouth: Mario steps out walking right; front-right mouth: he walks in until hidden
    p["mario_fl"] = spawn_x(c["walk0"], FY, front, SIDES["left"]["rim_icon"], -1)
    p["mario_fr"] = max(first_x(c[f"walk{i}"], FY, front, SHELL_X, 1, hidden) for i in range(4))
    # back-right mouth: Mario and the new Koopa step out walking left; back-left: Mario walks in
    p["mario_br"] = spawn_x(c["bwalk0"], BY, back, geo["back_r"], 1)
    p["mario_bl"] = min(first_x(c[f"bwalk{i}"], BY, back, p["mario_br"], -1, hidden) for i in range(3))
    p["koopa_br"] = spawn_x(c["koopaL0"], BY, back, geo["back_r"], 1)
    p["shell_fr"] = spawn_x(c["shell"], FY, front, SIDES["right"]["rim_icon"], 1)

    t = {}
    pick = clips()["pick"]
    first = pick[min(pick)]
    last = clips_walk_end()
    p["stop"] = mirror_x(last[1], last[3]) + last[3] / 2           # the game's last walk frame before the pickup
    t["at_shell"] = int(np.ceil((p["stop"] - p["mario_fl"]) / V_FRONT))
    g = lambda frame: t["at_shell"] + int((frame - 1409) * TO60)
    t["fly"] = g(1455)
    t["hit"] = g(1472)
    t["back_pose"] = g(1461)
    t["cam_up1"] = g(1440)

    t["cam_down1"] = t["hit"] + clip_len("knock") + 20 + (HOLD_BACK if tantric else 0)
    t["walk2"] = t["cam_down1"] + 70 + (HOLD_POSE if tantric else 0)
    pose = pick[1461]
    p["back_x"] = mirror_x(pose[1], pose[3]) + pose[3] / 2
    t["in1"] = t["walk2"] + entry_frames(c, "walk", 4, p["back_x"], V_FRONT, FY, front)
    t["out1"] = t["in1"] + TRANSIT
    t["in2"] = t["out1"] + entry_frames(c, "bwalk", 3, p["mario_br"], -V_BACK, BY, back)

    if tantric:
        t["loop"] = LOOP_FRAMES                          # Mario stays in the back pipe till the loop ends
        assert t["in2"] + TRANSIT + FRONT_TIME < LOOP_FRAMES, "the story no longer fits Tantric's loop"
    else:
        t["loop"] = t["in2"] + TRANSIT

    t["koopa_out"] = t["out1"] + 46
    t["shell_out"] = t["loop"] - (SHELL_BACK if tantric else 26)
    t["shell_rest"] = t["shell_out"] + int(np.ceil((p["shell_fr"] - SHELL_X) / V_FRONT))
    p["koopa_hit"] = koopa_walk((t["hit"] - t["koopa_out"]) % t["loop"], p["koopa_br"])[0]

    pans = [(t["cam_up1"], t["hit"] + 2, CAM_FRONT, CAM_BACK),
            (t["cam_down1"], t["cam_down1"] + 55, CAM_BACK, CAM_FRONT),
            (t["in1"] - 6, t["out1"], CAM_FRONT, CAM_BACK),
            (t["loop"] - FRONT_TIME, t["loop"] - FRONT_TIME + 55, CAM_BACK, CAM_FRONT) if tantric
            else (t["in2"] - 6, t["loop"], CAM_BACK, CAM_FRONT)]
    return p, t, pans, geo


def loop_len(mode=0):
    return plan(mode)[1]["loop"]


def cam(f, mode=0):
    _, t, pans, _ = plan(mode)
    f %= t["loop"]
    v = CAM_FRONT
    for a, b, c0, c1 in pans:
        if f >= a:
            v = c0 + (c1 - c0) * ease((f - a) / (b - a))
    return v


def koopa_walk(since, start):
    """(x, facing right) of a Koopa that stepped out of the right pipe at x `start` heading left `since` frames
    ago, walking at the game's speed and turning round at the ends of its stretch of ledge."""
    x = start - V_ENEMY * since
    if x >= KOOPA_LEFT:
        return x, False
    span = KOOPA_RIGHT - KOOPA_LEFT
    d = (KOOPA_LEFT - x) % (2 * span)
    return (KOOPA_LEFT + d, True) if d < span else (KOOPA_RIGHT - (d - span), False)


def koopa_at(f, mode=0):
    """(x, facing right) of the waiting Koopa, from when it stepped out after Mario."""
    p, t, _, _ = plan(mode)
    return koopa_walk((f - t["koopa_out"]) % t["loop"], p["koopa_br"])


def story(f, mode=0):
    """[(actor, cel, x, y)] in strip coordinates at frame f of the loop."""
    p, t, _, geo = plan(mode)
    L = t["loop"]
    f %= L
    FY, BY = geo["front_feet"], geo["back_feet"]
    out = []
    # the Koopa: waits on the back ledge, is knocked off behind it, and a new one follows Mario out of the pipe
    if not t["hit"] <= f < t["koopa_out"]:
        x, right = koopa_at(f, mode)
        since = (f - t["koopa_out"]) % L
        out.append(("koopa", f"{'koopa' if right else 'koopaL'}{int(since // ENEMY_CEL) % 3}", x, BY))
    kx = p["koopa_hit"]
    if t["hit"] <= f < t["hit"] + clip_len("knock"):
        h, x, y, w, hh = clip_frame("knock", f - t["hit"])
        h0, x0, y0, w0, _ = clips()["knock"][1472]
        cx = kx - ((x + w / 2) - (x0 + w0 / 2))         # mirrored drift about where it was hit
        out.append(("tumble", "g" + h, cx - w / 2, BY - 13 + (y - y0)))

    # the shell: rests (wobbling), goes up in Mario's hands, flies to the Koopa; one comes back out of the pipe
    if f < t["at_shell"] or f >= t["shell_out"]:
        since = (f - t["shell_out"]) % L
        x = max(SHELL_X, p["shell_fr"] - V_FRONT * since)
        if x > SHELL_X:
            out.append(("shell_f", "g5cdf", x - 8, FY - 15))
        else:
            h, gx, gy, w, hh = clip_frame("wobble", (since - (t["shell_rest"] - t["shell_out"])) % clip_len("wobble"))
            out.append(("shell_f", "g" + h, mirror_x(gx, w), gy + FRONT_DY))

    if t["fly"] <= f < t["hit"]:
        h, x, y, w, hh = clip_frame("flight", f - t["fly"])
        fl = clips()["flight"]
        a, b = fl[1455], fl[1471]
        u = (y - a[2]) / (b[2] - a[2])                    # the game's own progress along the throw
        x0, y0 = mirror_x(a[1], a[3]), a[2] + FRONT_DY
        x1, y1 = kx - b[3] / 2, BY - b[4]
        out.append(("fly" if h != "47d5" else "shell_b", "g" + h, x0 + (x1 - x0) * u, y0 + (y1 - y0) * u))

    if f < t["at_shell"]:
        out.append(("mario_f", walk_cel("walk", 4, f), p["mario_fl"] + V_FRONT * f, FY))
    elif f < t["back_pose"]:
        h, x, y, w, hh = clip_frame("pick", f - t["at_shell"])
        out.append(("mario_c", "g" + h, mirror_x(x, w), y + FRONT_DY))
    elif f < t["walk2"]:
        h, x, y, w, hh = clips()["pick"][1461]
        out.append(("mario_c", "g" + h, mirror_x(x, w), y + FRONT_DY))
    elif f < t["in1"]:
        u = f - t["walk2"]
        out.append(("mario_f", walk_cel("walk", 4, u), p["back_x"] + V_FRONT * u, FY))
    elif t["out1"] <= f < t["in2"]:
        u = f - t["out1"]
        out.append(("mario_b", walk_cel("bwalk", 3, u), p["mario_br"] - V_BACK * u, BY))
    return sorted(out, key=lambda it: ACTORS.index(it[0]))


# ------------------------------------------------------------- logos

LOGO_ROW = 25                        # both logos' center row: their tops land on row 8 or lower, as the donors' do
LOGO_W, LOGO_H = 128, 48


LOGO_TARGET = 105                    # the 4:3 tile shows about 117 px; this leaves a clear margin each side


def tighten(a, keep=1, word_gap=3):
    """The lettering with every blank column run between letters trimmed to `keep` columns (the gap between
    the two words to `word_gap`): every letter keeps its exact pixels, only the spacing shrinks."""
    blank = ~a[..., 3].any(axis=0)
    runs, x = [], 0
    while x < len(blank):
        if blank[x]:
            x0 = x
            while x < len(blank) and blank[x]:
                x += 1
            runs.append((x0, x))
        else:
            x += 1
    widest = max(runs, key=lambda r: r[1] - r[0])
    cols = []
    for x in range(a.shape[1]):
        run = next((r for r in runs if r[0] <= x < r[1]), None)
        if run is None or x - run[0] < (word_gap if run == widest else keep):
            cols.append(x)
    return a[:, cols]


def carve(im, width, height=None, reach=4, protect=None):
    """A crisp, even reduction. The cuts sit where a nearest-neighbor shrink would put them, spread evenly so
    the proportions hold, but each one takes the column (then row) within `reach` pixels that most nearly
    repeats its neighbour, so curves stay whole. No color is invented and edges stay hard. No cut crosses the
    `protect` box (x0, y0, x1, y1): small lettering there, like the GX badge, has strokes only a pixel wide."""
    a = np.asarray(im.convert("RGBA")).astype(int)
    height = height or round(im.height * width / im.width)

    def cut(a, keep, axis, lo, hi):
        a = np.moveaxis(a, axis, 0)
        n = a.shape[0] - keep
        diff = np.abs(a[1:] - a[:-1]).sum(axis=tuple(range(1, a.ndim))).astype(float)
        # a column is cheap to drop when it nearly repeats the one before or after it
        cost = {k: min(diff[k - 1], diff[k] if k < len(diff) else diff[k - 1]) for k in range(1, a.shape[0])}
        allowed = [k for k in range(1, a.shape[0]) if not lo <= k <= hi]
        drop = set()
        for i in range(n):
            center = allowed[min(len(allowed) - 1, int((i + 0.5) * len(allowed) / n))]
            r = reach
            while True:
                window = [k for k in allowed if abs(k - center) <= r and not {k - 1, k, k + 1} & drop]
                if window:
                    break
                r += 1
            drop.add(min(window, key=lambda k: cost[k]))
        kept = [k for k in range(a.shape[0]) if k not in drop]
        return np.moveaxis(a[kept], 0, axis)

    x0, y0, x1, y1 = protect or (-1, -1, -2, -2)
    a = cut(a, width, 1, x0, x1)
    a = cut(a, height, 0, y0, y1)
    return Image.fromarray(a.astype(np.uint8), "RGBA")


def smooth_down(im, width):
    """A clean downscale of an RGBA image to `width` px wide: area averaging on premultiplied alpha."""
    h = round(im.height * width / im.width)
    return im.convert("RGBa").resize((width, h), Image.BOX).convert("RGBA")


def vb_logo(mode="game", variant="current"):
    """The Virtual Boy lettering as the boot screen draws it, without its trademark mark (Jaxi's choice, so it
    fits the 4:3 tile at its own size), on the boot screen's black, with one of its dotted rows above and below."""
    a = np.asarray(Image.open(os.path.join(S.CAP, f"vblogo-{mode}.png")).convert("RGBA"))
    top, bot = 16, 54                                   # the capture's box outline rows
    inner = a[top + 1:bot, 1:-1]
    cols = np.nonzero(inner[..., 3].any(axis=0))[0]
    rows = np.nonzero(inner[..., 3].any(axis=1))[0]
    text = inner[rows.min():rows.max() + 1, cols.min():cols.max() + 1].copy()
    text = text[:, :TM_FROM]                            # the ™ sits right of this column, under the Y's arm
    if variant == "tight":
        text = tighten(text)

    th, tw = text.shape[:2]
    pw, ph = tw + 2, th + 2
    dots = np.nonzero(a[0, :, 3])[0]
    block = min(dots.max() + 1 - dots.min(), (pw * 2 // 3) // 2 * 2)
    sx0 = dots.min() + (dots.max() + 1 - dots.min() - block) // 2

    out = np.zeros((ph + 4, pw, 4), np.uint8)
    out[2:2 + ph] = VOID + (255,)
    panel = out[3:3 + th, 1:1 + tw]
    panel[text[..., 3] > 0] = text[text[..., 3] > 0]
    bx0 = (pw - block) // 2
    out[0, bx0:bx0 + block] = a[top - 2, sx0:sx0 + block]
    out[ph + 3, bx0:bx0 + block] = a[bot + 2, sx0:sx0 + block]
    img = Image.fromarray(out, "RGBA")

    if variant == "smooth":
        return smooth_down(img, LOGO_TARGET)
    if variant == "nearest":
        return img.resize((LOGO_TARGET, round(img.height * LOGO_TARGET / img.width)), Image.NEAREST)
    if variant == "carve":
        return carve(img, LOGO_TARGET)
    return img


def app_logo(variant="current", tip=True):
    im = S.app_logo()
    a = np.asarray(im)[..., 3] > 0
    xs = np.nonzero(a.any(axis=0))[0]
    content = im.crop((int(xs.min()), 0, int(xs.max()) + 1, im.height))
    if variant == "smooth":
        return smooth_down(content, LOGO_TARGET)
    if variant == "nearest":
        return content.resize((LOGO_TARGET, round(content.height * LOGO_TARGET / content.width)), Image.NEAREST)
    if variant == "carve":
        c = np.asarray(content)
        top = c[:22, int(0.75 * content.width):, 3] > 0               # the GX badge, top right
        ys, xs = np.nonzero(top)
        ox = int(0.75 * content.width)
        badge = (ox + int(xs.min()) - 1, int(ys.min()) - 1, ox + int(xs.max()) + 1, int(ys.max()) + 1)
        logo = carve(content, LOGO_TARGET, protect=badge)
        return solid_v_tip(logo) if tip else logo
    return im


STEM_EDGE = [72, 64, 58, 52, 47, 42, 38]   # the stem's soft outside edge, rows 29-35, easing on from the V's


def solid_v_tip(im):
    """The V narrows to a one-pixel point that a CRT's softening erases: give it a solid 3-pixel stem with soft
    edges, a notch 2 pixels deeper so it still reads as a V, and a point narrowing to one pixel (Jaxi's pick)."""
    a = np.asarray(im).copy()
    col = a[29:38, :12, 3].astype(int).sum(axis=0)
    x = int(np.argmax(col))
    red = a[25, x - 1, :3]                  # a solid pixel of the V's arm
    notch = a[18:31, x, 3].copy()
    a[20:31, x, 3] = notch[:11]
    a[18:20, x, 3] = 0
    for y, e in zip(range(29, 36), STEM_EDGE):
        a[y, x - 2:x + 3] = (*red, 0)
        a[y, x - 1:x + 2] = (*red, 255)
        a[y, [x - 2, x + 2]] = (*red, e)
    a[36:38, x - 2:x + 3] = (*red, 0)
    a[36:38, x] = (*red, 255)
    a[36, [x - 1, x + 1]] = (*red, 128)
    return Image.fromarray(a)


# lettering columns 0-111 are VIRTUAL BOY (the Y's arm reaches 111); the ™ starts at 112
TM_FROM = 112


def logo_canvases(logo_mode="game", vb_variant="tight", app_variant="carve"):
    """Both logos on the 128x48 canvas the logo pane shows, each centered the way the archive draws them."""
    out = []
    for im in (vb_logo(logo_mode, vb_variant), app_logo(app_variant)):
        c = Image.new("RGBA", (LOGO_W, LOGO_H))
        c.alpha_composite(im, ((LOGO_W - im.width) // 2, (LOGO_H - im.height) // 2))
        out.append(c)
    return out


# ------------------------------------------------------------- flip and mock

def flip_keys(L, mode=0):
    """The coin flip. With TANTRIC, key for key from the FCE Ultra GX and mGBA GX icons: a double flip, eight
    seconds of the first logo, a triple flip, six seconds of the second, and a single flip back. Without it,
    the current build's: 24 frames to edge-on, to our logo at the top of the knock, and back at the end."""
    if TANTRIC:
        assert L == LOOP_FRAMES
        return S.FLIP_SCALE, S.FLIP_SWAPS
    T = plan(mode)[1]["hit"] + 18
    scale = [(0, 1), (T - 24, 1), (T, .01), (T + 24, 1), (L - 48, 1), (L - 24, .01), (L, 1)]
    swaps = [(0, 0), (T, 1), (L - 24, 0)]
    return scale, swaps


def logo_scale(f, L):
    return S.smooth_keys(flip_keys(L)[0], f % L)


def logo_index(f, L):
    return [v for k, v in flip_keys(L)[1] if k <= f % L][-1]


def stripes_layer():
    return S.stripes(Image.new("RGBA", (W, H)))


def render(f, mode=0, logo_mode="game", celtab=None, logos=None):
    logos = logos or logo_canvases(logo_mode)
    """One mock frame, composited the way the archive draws it (whole pixels, layers in world order)."""
    layers, _, geo = build(mode)
    celtab = celtab or cels()
    L = loop_len(mode)
    c = int(round(cam(f, mode)))
    img = Image.new("RGBA", (W, H), VOID + (255,))
    items = story(f, mode)

    for name, _, _ in LAYERS:
        img.alpha_composite(layers[name], (0, -c))
        for actor, cel, x, y in items:
            if ACTOR_LAYER[actor] == name:
                im, (dx, dy) = celtab[cel]
                img.alpha_composite(im, (round(x) + dx, round(y) - c + dy))

    img.alpha_composite(stripes_layer(), (0, 0))
    logo = logos[logo_index(f, L)]
    w = max(1, round(logo.width * logo_scale(f, L)))
    img.alpha_composite(
        logo.resize((w, logo.height), Image.BILINEAR),
        (int(round(W / 2 - w / 2)), LOGO_ROW - LOGO_H // 2),
    )
    return img
