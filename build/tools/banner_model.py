"""The banner's moving parts, shared by the mockups and the real build so both draw the same thing.

The parade rides Tantric's own conveyor, read from the FCE Ultra GX and mGBA GX banners: four slots 256 px
apart in each of two copies 1024 px apart, moving right at 2.048 px a frame, with the copies jumping back
only while they are off screen, and the same fade-ins at the start. Every walker plays its game's own cels for
the game's own time (converted to 60 Hz and rounded so each cycle divides the 1000-frame Start and Loop), with
the game's own little bob in each step.
"""

import json
import os

W, H = 832, 456
START, LOOP = 1000, 1000
SLOTS = [384, 128, -128, -384]             # Tantric's slots, leader first (the parade walks right)
FRONT_FEET = 192
TO60 = 60 / 50.27                          # game frames -> Wii frames
CAST = os.path.join(os.path.dirname(__file__), "..", "..", "banner", "cast")
# Tantric's conveyor keys: (frame, x) per copy, a repeated frame is a jump
CONVEYOR = {0: [(0, 0.0), (500, 1024.0), (500, -1024.0), (1000, 0.0)], 1: [(0, -1024.0), (1000, 1024.0)]}
SHOW_FROM = {0: 450, 1: 100}               # in the Start, each copy fades in at this frame


def _keyed(keys, t):
    for (f0, v0), (f1, v1) in zip(keys, keys[1:]):
        if f0 <= t < f1:
            return v0 + (v1 - v0) * (t - f0) / (f1 - f0)
    return keys[-1][1]


def local(f):
    """(in the Start, frame within it) for timeline frame f (the Loop repeats after the Start)."""
    return (True, f) if f < START else (False, (f - START) % LOOP)


def copy_x(f, c):
    return _keyed(CONVEYOR[c], local(f)[1])


def copy_visible(f, c):
    start, t = local(f)
    return not start or t >= SHOW_FROM[c]


def per(game_frames, slots):
    """Wii frames per slot of a cycle of `slots` slots of game_frames each, rounded to divide the Loop."""
    cycles = max(1, round(LOOP / (game_frames * TO60 * slots)))
    return LOOP / (cycles * slots)


def _info(name):
    return json.load(open(os.path.join(CAST, name, "cels.json")))


class Walker:
    """One character: its game's cycle of cels, each held the game's time, at a slot of the conveyor. A walker
    whose game also moves it per step (Ballom drifts and bobs) gets those offsets as pane motion; a walker whose
    bob belongs to each cel (Wario, Jack Frost) has it built into the cel's canvas."""

    def __init__(self, name, slot, scale, float_up=0):
        self.name, self.slot, self.scale, self.float_up = name, slot, scale, float_up
        info = _info(name)
        if "cels" in info:
            steps = [(c["file"][:-4], c.get("game_dx", 0), c.get("game_dy", 0)) for c in info["cels"]]
            hold = info["cels"][0]["hold_frames"]
        else:
            steps = [(n, 0, 0) for n in info["cycle"]]
            hold = info["hold_frames"]
        self.cycle = [n for n, _, _ in steps]
        self.offsets = [(dx, dy) for _, dx, dy in steps]
        by_cel = {}
        for n, dx, dy in steps:
            by_cel.setdefault(n, set()).add((dx, dy))
        self.moves = any(len(v) > 1 for v in by_cel.values()) or any(dx for _, dx, _ in steps)
        self.dy = {n: 0 for n in by_cel} if self.moves else {n: next(iter(v))[1] for n, v in by_cel.items()}
        self.per = per(hold, len(self.cycle))

    def step(self, f):
        return int(f // self.per) % len(self.cycle)

    def cel(self, f):
        return self.cycle[self.step(f)]

    def offset(self, f):
        """(right, down) in banner pixels for a walker the game moves per step, centered on its slot."""
        if not self.moves:
            return 0.0, 0.0
        dxs = [dx for dx, _ in self.offsets]
        dx, dy = self.offsets[self.step(f)]
        x, y = (dx - (min(dxs) + max(dxs)) / 2) * self.scale, dy * self.scale
        return (x, y) if self.scale == int(self.scale) else (round(x), round(y))      # drawn ahead: whole pixels


class Invader:
    """One invader of the formation: it toggles its two cels in the game's ripple, one invader a frame from
    the bottom left, so with N in the formation each one toggles every N game frames."""

    def __init__(self, kind, col, row, k, n):
        self.kind, self.col, self.row, self.k = kind, col, row, k
        self.per = per(n, 2)
        self.phase = k * self.per / n

    def cel(self, f):
        return int((f - self.phase) // self.per) % 2


FORM_ROWS = ["invader-squid", "invader", "invader", "invader-octopus"]   # top to bottom, as in the arcade
FORM_COLS = 6
FORM_PITCH = 16
FORM_SCALE = 2


def formation():
    n = FORM_COLS * len(FORM_ROWS)
    out, k = [], 0
    for row in reversed(range(len(FORM_ROWS))):          # the ripple starts on the bottom row, left to right
        for col in range(FORM_COLS):
            out.append(Invader(FORM_ROWS[row], col, row, k, n))
            k += 1
    return out


# Ballom floats, so his lowest step leaves his tail a little above the stripe
FRONT = [Walker("wario", SLOTS[0], 2), Walker("ballom", SLOTS[1], 1.5, float_up=9), Walker("jack", SLOTS[2], 2)]
INVADERS = formation()
INVADER_SLOT = SLOTS[3]


def walkers(f):
    """[(walker, cel, x of the slot, copy)] for every character drawn at frame f (the formation is listed by
    its invaders: (invader, cel index, x of the slot, copy))."""
    out = []
    for c in (0, 1):
        if not copy_visible(f, c):
            continue
        x = copy_x(f, c)
        for w in FRONT:
            out.append((w, w.cel(f), x + w.slot, c))
        for inv in INVADERS:
            out.append((inv, inv.cel(f), x + INVADER_SLOT, c))
    return out
