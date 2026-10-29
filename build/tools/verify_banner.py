"""Check a built banner.bin: verify_banner.py <design> [banner.bin]

The share of system-wide banner memory, the U8 tree, references, names, one animation block per pane, a
Benzin round trip, the title text, no material shared between pictures (the Menu animates a material on
one pane only), no fractional scale at rest, and the walkers: every third frame of both animations compared
with banner_model (positions within half a pixel, the right cel, the hidden copy hidden).
"""

import os
import re

import numpy as np
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(__file__))

import banner_model as M
import build_banner as BB
import tpl as T
from build_icon import make
from render import Archive, hermite, rip, stepped, texmap_filters
from vbcgx import OUT
from wiilib import U8, unpack_lz77_imd5

SHARE = 600_000
fails = []


def check(ok, what):
    if not ok:
        fails.append(what)
    print(("  ok   " if ok else "  FAIL ") + what)


def keys_run_forward(xml):
    """Every keyed track's frames never go backwards (NW4R searches keys assuming they are sorted)."""
    bad = 0
    for e in re.finditer(r"<entry [^>]*>(.*?)</entry>", xml, re.S):
        fr = [float(v) for v in re.findall(r"<frame>([-\d.e]+)</frame>", e.group(1))]
        fr += [float(v) for v in re.findall(r"<data1>([-\d.e]+)</data1>", e.group(1))]
        if any(b < a for a, b in zip(fr, fr[1:])):
            bad += 1
    return bad


def main(design, path=None):
    path = path or os.path.join(OUT, f"banner-{design}.bin")
    raw = unpack_lz77_imd5(open(path, "rb").read())
    print(f"{os.path.basename(path)}: {len(raw):,} bytes uncompressed")
    check(len(raw) <= SHARE, f"inside the {SHARE:,}-byte share ({len(raw) / SHARE:.0%})")
    arc = U8.load(raw)
    check(not arc.check_tree(), "U8 directory parents and ends are consistent")
    files = {os.path.basename(p): arc.nodes[i].data for i, p in arc.paths() if not arc.nodes[i].is_dir}
    nearest, plain = texmap_filters(files["banner.brlyt"])
    lyt = rip(plain, ".xmlyt")
    check(make(lyt, ".xmlyt") == plain, "Benzin round-trips the layout byte for byte (filter bits lifted off)")

    want = {f"Walk{i}Mat{k}" for i, w_ in enumerate(M.FRONT) if w_.scale > 1 for k in "AB"}
    check(
        {n for n, v in nearest.items() if v} == want,
        f"the layout asks for nearest-neighbor on exactly the walkers drawn bigger than 1x ({len(want)})"
    )
    big = [w_ for w_ in M.FRONT if w_.scale > 1]
    tpls = [f"{n.replace('-', '').capitalize()}.tpl" for w_ in big for n in dict.fromkeys(w_.cycle)]
    check(all(T.parse(files[t])[0]["mag_filter"] == 0 and T.parse(files[t])[0]["min_filter"] == 0 for t in tpls),
          f"their {len(tpls)} textures ask for nearest-neighbor in their own headers too")

    txl = re.findall(r"<name>([^<]+\.tpl)</name>", re.search(r'<tag type="txl1">(.*?)</tag>', lyt, re.S).group(1))
    panes = re.findall(r'<tag type="(?:pan1|pic1|txt1)" name="([^"]+)"', lyt)
    mats = re.findall(r'<entries name="([^"]+)">\s*<colors>', lyt)
    long_names = [p for p in panes if len(p.encode()) > 16]

    check(all(sum(1 for q in panes if q[:16] == p[:16]) == 1 for p in long_names),
          f"names past the 16-byte field still bind to one pane each ({', '.join(long_names) or 'none'})")
    check(len({p[:16] for p in panes}) == len(panes), "pane names are unique in their first 16 bytes")
    check(all(len(m.encode()) <= 20 for m in mats), "material names fit their 20-byte field")

    for an in ("banner_Start", "banner_Loop"):
        x = rip(files[f"{an}.brlan"], ".xmlan")
        check(make(x, ".xmlan") == files[f"{an}.brlan"], f"Benzin round-trips {an} byte for byte")
        timg = re.findall(r'<timg name="([^"]+)"', x)
        check(all(t in files for t in txl + timg), f"{an}: every texture it names is in timg/")
        check(keys_run_forward(x) == 0, f"{an}: every track's keys run forward in time")
        blocks = Counter(re.findall(r'<pane name="([^"]+)" type="(\d)">', x))
        check(all(v == 1 for v in blocks.values()), f"{an}: one animation block per pane ({len(blocks)})")
        check(all((n in panes) if k == "0" else (n in mats) for n, k in blocks), f"{an}: every animated name exists")

    used = re.findall(r'<tag type="pic1" name="[^"]+".*?<material name="([^"]+)"', lyt, re.S)
    shared = [m for m, n in Counter(used).items() if n > 1]
    check(
        not shared,
        f"every picture has its own material ({len(used)} pictures{', shared: ' + ', '.join(shared) if shared else ''})"
    )

    scales = [(float(x), float(y)) for x, y in re.findall(r"<scale>\s*<x>([-\d.]+)</x>\s*<y>([-\d.]+)</y>", lyt)]
    check(all(v == int(v) for xy in scales for v in xy), "every pane rests at a whole-number scale")

    tab = lyt[lyt.index('<entries name="TitleBarMaterial">'):]
    tab = tab[:tab.index("</entries>")]
    fore = tuple(int(v) for v in re.search(r'<forecolor r="(\d+)" g="(\d+)" b="(\d+)" a="(\d+)"', tab).groups())
    back = tuple(int(v) for v in re.search(r'<backcolor r="(\d+)" g="(\d+)" b="(\d+)" a="(\d+)"', tab).groups())
    check(back == BB.DEEP_RED + (255,) and fore == BB.BLACK + (0,),
          f"the title tab is VBoy Color red {back[:3]} with a black edge {fore[:3]}")

    st = T.parse(files["Stripe.tpl"])[0]
    band = np.asarray(
        T.decode(files["Stripe.tpl"][st["data_off"]:], st["w"], st["h"], st["fmt"], st["pal"])
    ).astype(int)
    lower = tuple(int(v) for v in band[18, 0, :3])
    check(lower == BB.LOWER_RED, f"the stripe band's lower bar is exactly the app menu's light chrome red {lower}")
    check(panes.index("ControllerPicture") > max(panes.index("StripePicture"), panes.index("BarsPicture")),
          "the controller is drawn over the stripe band and the red bars")
    text = re.search(r"<text>([0-9a-f]*)</text>", lyt).group(1)
    check(bytes.fromhex(text).decode("utf-16-be").split("\0")[0] == "VBoy Color GX", "the title tab says VBoy Color GX")

    a = Archive(open(path, "rb").read(), "banner")
    worst, cel_bad, hide_bad, step_bad = 0.0, 0, 0, []
    for an, offset, n in (("banner_Start", 0, M.START), ("banner_Loop", M.START, M.LOOP)):
        anim = a.anims[an]
        for f in range(0, n, 3):
            tf = offset + f
            for c, k in ((0, "A"), (1, "B")):
                for grp, xf, vf in ((f"CharacterPane{k}", M.copy_x, M.copy_visible),
                                    (f"RainbowPane{k}", M.copy_x, BB.rainbow_group_visible)):
                    tr = anim["panes"][grp]
                    worst = max(worst, abs(hermite(tr["tx"], f) - xf(tf, c)))
                    if "alpha" in tr and (hermite(tr["alpha"], f) > 1) != vf(tf, c):
                        hide_bad += 1
                for i, w_ in enumerate(M.FRONT):
                    tex = anim["timg"][stepped(anim["mats"][f"Walk{i}Mat{k}"][("tp", 0)], f)]
                    cel_bad += tex != f"{w_.cel(tf).replace('-', '').capitalize()}.tpl"
                    if w_.moves:
                        pt = anim["panes"][f"Walk{i}Pic{k}"]
                        ox, oy = w_.offset(tf)
                        step_bad.append(max(
                            abs(hermite(pt["tx"], f) - hermite(pt["tx"], 0) - (ox - w_.offset(offset)[0])),
                            abs(hermite(pt["ty"], f) - hermite(pt["ty"], 0) + (oy - w_.offset(offset)[1])),
                        ))
                for inv in M.INVADERS:
                    tex = anim["timg"][stepped(anim["mats"][f"Inv{inv.k:02d}Mat{k}"][("tp", 0)], f)]
                    cel_bad += tex != f"{inv.kind.replace('-', '').capitalize()}{inv.cel(tf)}.tpl"

    check(
        worst <= 0.5,
        f"walkers and the rainbow follow Tantric's conveyor on every third frame (worst {worst:.2f} px)"
    )
    check(cel_bad == 0, f"every walker and invader shows the model's cel ({cel_bad} frames differ)")
    check(hide_bad <= 4, f"each copy fades in on Tantric's frames ({hide_bad} frames differ)")
    check(
        max(step_bad, default=0) <= 0.05,
        f"a walker the game moves per step follows its steps (worst {max(step_bad, default=0):.2f} px)"
    )

    lead = BB.lead_x()
    visible = lead - BB.LEAD_ALPHA * BB.FRONT_FADE - BB.LEAD_AHEAD
    for mode, edge in (("4:3", BB.EDGE_43), ("16:9", BB.EDGE_169)):
        fw = BB.first_frame(BB.wario_front, edge)
        fr = BB.first_frame(lambda f: visible, edge)
        check(fw == fr, f"{mode}: the rainbow's first visible color (10%) comes {BB.LEAD_AHEAD} px ahead of "
                        f"Wario's first pixel (frame {fr}, with the cel showing on each frame)")
    return not fails


if __name__ == "__main__":
    ok = main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
    print("PASS" if ok else f"FAIL ({len(fails)})")
    sys.exit(0 if ok else 1)
