"""Check Icon A v2's icon.bin: verify_icon_v2.py [icon.bin]

The size cap, the U8 tree, references, names, tiles, a Benzin round trip, keys running forward, the
16:9 flags (exactly one location-adjusted pane on every picture's path), no material shared between
pictures, no scale track, the layers in world order, and every frame's camera and every actor's place,
cel and visibility against the story, the waiting Koopa in full view once out of its pipe, and the logo's flip.
"""

import os
import re

import numpy as np
import sys

sys.path.insert(0, os.path.dirname(__file__))

import build_icon_v2 as B
import icon_scene as S
import icon_v2 as V
import tpl as T
from build_icon import make
from render import Archive, hermite, rip, stepped
from verify_icon import keys_run_forward
from vbcgx import OUT
from wiilib import U8, unpack_lz77_imd5

CAP = 102_400
fails = []


def check(ok, what):
    if not ok:
        fails.append(what)
    print(("  ok   " if ok else "  FAIL ") + what)


def main(path=None):
    path = path or os.path.join(OUT, "icon-clash2.bin")
    raw = unpack_lz77_imd5(open(path, "rb").read())
    print(f"{os.path.basename(path)}: {len(raw):,} bytes uncompressed")
    check(len(raw) < CAP, f"under the {CAP:,}-byte icon cap ({len(raw) / CAP:.0%})")
    if len(raw) >= 0.85 * CAP:
        print("  note less than 15% headroom left under the cap")

    arc = U8.load(raw)
    check(not arc.check_tree(), "U8 directory parents and ends are consistent")
    files = {os.path.basename(p): arc.nodes[i].data for i, p in arc.paths() if not arc.nodes[i].is_dir}
    lyt, an = rip(files["icon.brlyt"], ".xmlyt"), rip(files["icon.brlan"], ".xmlan")
    check(make(lyt, ".xmlyt") == files["icon.brlyt"] and make(an, ".xmlan") == files["icon.brlan"],
          "Benzin round-trips the layout and animation byte for byte")
    check(keys_run_forward(an) == 0, "every track's keys run forward in time")

    txl = re.findall(r"<name>([^<]+\.tpl)</name>", re.search(r'<tag type="txl1">(.*?)</tag>', lyt, re.S).group(1))
    timg = re.findall(r'<timg name="([^"]+)"', an)
    check(all(t in files for t in txl + timg), f"all {len(set(txl + timg))} referenced textures are in timg/")

    bad_tiles = [
        n
        for n, d in files.items()
        if n.endswith(".tpl")
        and (lambda t: t["w"] % (8 if t["fmt"] in (T.CI4, T.CI8) else 4) or t["h"] % 4)(T.parse(d)[0])
    ]
    check(not bad_tiles, f"every texture fits whole GX tiles {bad_tiles or ''}")

    panes = re.findall(r'<tag type="(?:pan1|pic1|txt1)" name="([^"]+)"', lyt)
    check(len({p[:16] for p in panes}) == len(panes), "pane names are unique in their first 16 bytes")
    mats = re.findall(r'<tag type="pic1" name="[^"]+".*?<material name="([^"]+)"', lyt, re.S)
    check(len(mats) == len(set(mats)), f"every picture has its own material ({len(mats)} pictures)")
    check("Scale" not in re.sub(r'<pane name="Logo00Pic".*?</pane>', "", an, flags=re.S),
          "nothing is scaled except the logo's coin flip")

    order = [m for m in re.findall(r'<tag type="pic1" name="([^"]+)"', lyt)]
    want = []
    for layer, _, _ in V.LAYERS:
        want.append(B.LAYER_NAMES[layer] + "Pic")
        want += [B.NAMES[a] + "Pic" for a in V.ACTORS if V.ACTOR_LAYER[a] == layer]
    check([o for o in order if o in want] == want, "layers and actors draw in the game's world order")

    a = Archive(open(path, "rb").read(), "icon")
    ok = True
    for i, p in enumerate(a.panes):
        if p["kind"] != "pic1":
            continue
        n, j = 0, i
        while j is not None:
            n += a.panes[j]["flag"] & 1
            j = a.panes[j]["parent"]
        ok &= n == 1
    check(ok, "every picture has exactly one location-adjusted pane on its path (true proportions in 16:9)")

    anim = a.anims["icon"]
    L = V.loop_len()
    _, _, geo = V.build(0)
    track = B.sample(L)
    cam_err = max(abs(hermite(anim["panes"]["CamPane"]["ty"], f) - round(V.cam(f))) for f in range(L))
    check(cam_err < 1e-3, f"the view is on a whole pixel of its path on every frame (worst {cam_err:.3f} px)")
    worst, cel_bad, vis_bad = 0.0, 0, 0
    for actor in V.ACTORS:
        n = B.NAMES[actor]
        pt, at, mt = anim["panes"][f"{n}Pane"], anim["panes"].get(f"{n}Pic", {}), anim["mats"][f"{n}Mat"]
        used = []
        for s_ in track[actor]:
            if s_ and s_[0] not in used:
                used.append(s_[0])
        for f, s_ in enumerate(track[actor]):
            alpha = hermite(at["alpha"], f) if "alpha" in at else 255
            vis_bad += (s_ is None) != (alpha < 1)
            if s_ is None:
                continue
            x = hermite(pt["tx"], f) + S.W / 2.0
            y = geo["height"] / 2.0 - hermite(pt["ty"], f)
            worst = max(worst, abs(x - round(s_[1])), abs(y - round(s_[2])))
            cel_bad += anim["timg"][stepped(mt[("tp", 0)], f)] != f"{n}{used.index(s_[0]):02d}.tpl"
    check(worst < 1e-3, f"every actor on the story's whole pixel on every frame (worst {worst:.3f} px)")
    check(cel_bad == 0, f"every frame shows the story's cel ({cel_bad} frames differ)")
    check(vis_bad == 0, f"actors are visible exactly when the story has them ({vis_bad} frames differ)")
    p, t, _, _ = V.plan(0)
    far, cels = V.cover_mask("far", 0), S.cels()
    out_at = int(np.ceil((p["koopa_br"] - V.KOOPA_RIGHT) / V.V_ENEMY))
    cut = sum(V.shown_columns(cels[cel], x, y, far) < cels[cel][0].width
              for f in range(L) if (f - t["koopa_out"]) % L >= out_at
              for actor, cel, x, y in V.story(f) if actor == "koopa")
    check(cut == 0, f"once out of its pipe, the waiting Koopa never goes behind a pipe ({cut} frames partly hidden)")

    swaps = anim["mats"]["Logo00Mat"][("tp", 0)]
    check(
        [(int(f), anim["timg"][i]) for f, i in swaps]
        == [(f, ["Logo00.tpl", "Logo01.tpl"][i]) for f, i in V.flip_keys(L)[1]],
        "the logo swaps on the flip's frames"
    )
    check(anim["framesize"] == L, f"the loop is {L} frames")

    st = T.parse(files["Stripes.tpl"])[0]
    band = np.asarray(
        T.decode(files["Stripes.tpl"][st["data_off"]:], st["w"], st["h"], st["fmt"], st["pal"])
    ).astype(int)
    lower = tuple(int(v) for v in band[8, 0, :3])                 # stripe rows 81-96: the lower bar is rows 87-91
    check(lower == S.LOWER_RED, f"the lower red bar is exactly the app menu's light chrome red {lower}")
    return not fails


if __name__ == "__main__":
    ok = main(sys.argv[1] if len(sys.argv) > 1 else None)
    print("PASS" if ok else f"FAIL ({len(fails)})")
    sys.exit(0 if ok else 1)
