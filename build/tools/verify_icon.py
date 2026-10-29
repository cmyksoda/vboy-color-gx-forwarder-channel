"""Check a built icon.bin against everything that has gone wrong on these channels before.

    verify_icon.py <look> [icon.bin]

Reads the archive back off disk and re-derives everything from it: the size cap, the U8 tree, texture and
name references, 16-byte pane names, texture dimensions, a Benzin round trip, and the animation itself:
every pane's tracks are evaluated frame by frame and compared with the story they were written from
(positions within a third of a pixel, the same cel, the same visibility, the logo swapping on Tantric's
frames), plus the loop seam and the 4:3 view.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))

import build_icon as B
import icon_scene as S
import tpl as T
from render import Archive, hermite, rip, stepped
from vbcgx import OUT
from wiilib import U8, unpack_lz77_imd5

CAP = 102_400
fails, warns = [], []


def check(ok, what, warn=False):
    (warns if warn else fails).append(what) if not ok else None
    print(("  ok   " if ok else ("  WARN " if warn else "  FAIL ")) + what)


def keys_run_forward(xml):
    """Every keyed track's frames never go backwards (NW4R searches keys assuming they are sorted)."""
    bad = 0
    for e in re.finditer(r"<entry [^>]*>(.*?)</entry>", xml, re.S):
        fr = [float(v) for v in re.findall(r"<frame>([-\d.e]+)</frame>", e.group(1))]
        fr += [float(v) for v in re.findall(r"<data1>([-\d.e]+)</data1>", e.group(1))]
        if any(b < a for a, b in zip(fr, fr[1:])):
            bad += 1
    return bad


def main(look, path=None):
    path = path or os.path.join(OUT, f"icon-{look}.bin")
    raw = unpack_lz77_imd5(open(path, "rb").read())
    print(f"{os.path.basename(path)}: {len(raw):,} bytes uncompressed")
    check(len(raw) < CAP, f"under the {CAP:,}-byte icon cap ({len(raw) / CAP:.0%})")
    check(len(raw) < 0.85 * CAP, "leaves 15% headroom under the cap", warn=True)

    arc = U8.load(raw)
    check(not arc.check_tree(), "U8 directory parents and ends are consistent")
    files = {os.path.basename(p): arc.nodes[i].data for i, p in arc.paths() if not arc.nodes[i].is_dir}
    lyt_bin, an_bin = files["icon.brlyt"], files["icon.brlan"]
    lyt, an = rip(lyt_bin, ".xmlyt"), rip(an_bin, ".xmlan")
    check(B.make(lyt, ".xmlyt") == lyt_bin and B.make(an, ".xmlan") == an_bin,
          "Benzin round-trips the layout and animation byte for byte")
    check(keys_run_forward(an) == 0, "every track's keys run forward in time")

    txl = re.findall(r"<name>([^<]+\.tpl)</name>", re.search(r'<tag type="txl1">(.*?)</tag>', lyt, re.S).group(1))
    timg = re.findall(r'<timg name="([^"]+)"', an)
    check(all(t in files for t in txl + timg), f"all {len(set(txl + timg))} referenced textures are in timg/")

    for name, data in files.items():
        if not name.endswith(".tpl"):
            continue
        t = T.parse(data)[0]
        step = 8 if t["fmt"] in (T.CI4, T.CI8) else 4
        check(t["w"] % step == 0 and t["h"] % 4 == 0, f"{name} {t['w']}x{t['h']} fits whole GX tiles", warn=True)

    panes = re.findall(r'<tag type="(?:pan1|pic1)" name="([^"]+)"', lyt)
    mats = re.findall(r'<entries name="([^"]+)">\s*<colors>', lyt)
    check(all(len(p.encode()) <= 16 for p in panes), "pane names fit their 16-byte field")
    check(len({p[:16] for p in panes}) == len(panes), "pane names are unique in their first 16 bytes")
    animated = re.findall(r'<pane name="([^"]+)" type="(\d)">', an)
    check(
        all((n in panes) if k == "0" else (n in mats) for n, k in animated),
        "every animated pane and material exists"
    )

    # the animation against the story it was written from
    a = Archive(open(path, "rb").read(), "icon")
    anim = a.anims["icon"]
    pane = {p["name"]: p for p in a.panes}
    _, _, variant = B.LOOKS[look]
    track = B.sample(variant)
    worst, cel_bad, vis_bad = 0.0, 0, 0
    for actor, (donor, prefix, _) in B.ACTORS.items():
        pt = anim["panes"].get(f"{donor}Pane", {})
        at = anim["panes"].get(f"{donor}Pic", {})
        mt = anim["mats"].get(f"{donor}Mat", {})
        used = []
        for s in track[actor]:
            if s and s[0] not in used:
                used.append(s[0])
        for f, s in enumerate(track[actor]):
            alpha = hermite(at["alpha"], f) if "alpha" in at else 255
            if (s is None) != (alpha < 1):
                vis_bad += 1
            if s is None:
                continue
            x = hermite(pt["tx"], f) + S.W / 2.0
            y = S.H / 2.0 - hermite(pt["ty"], f)
            worst = max(worst, abs(x - s[1]), abs(y - s[2]))
            tex = anim["timg"][stepped(mt[("tp", 0)], f)]
            if tex != f"{prefix}{used.index(s[0]):02d}.tpl":
                cel_bad += 1
    check(worst <= 0.35, f"every character within 0.35 px of the story on every frame (worst {worst:.2f})")
    check(cel_bad == 0, f"every frame shows the story's cel ({cel_bad} frames differ)")
    check(vis_bad <= 6, f"characters are visible exactly when the story has them ({vis_bad} edge frames differ)")

    swaps = anim["mats"]["Logo00Mat"][("tp", 0)]
    check([(int(f), anim["timg"][i]) for f, i in swaps] ==
          [(f, ["Logo00.tpl", "Logo01.tpl"][i]) for f, i in S.FLIP_SWAPS], "the logo swaps on Tantric's frames")

    fs = anim["framesize"]
    seam = 0.0
    for actor, (donor, _, _) in B.ACTORS.items():
        pt = anim["panes"].get(f"{donor}Pane", {})
        at = anim["panes"].get(f"{donor}Pic", {})
        if "alpha" in at and (hermite(at["alpha"], 0) < 1 or hermite(at["alpha"], fs - 1) < 1):
            continue                             # off screen across the wrap: it may move anywhere unseen
        for ch in ("tx", "ty"):
            if ch in pt:
                step = abs(hermite(pt[ch], fs - 1) - hermite(pt[ch], fs - 2))
                seam = max(seam, abs(hermite(pt[ch], 0) - hermite(pt[ch], fs - 1)) - step)
    check(seam <= 0.5, f"everything on screen at the wrap carries on smoothly (worst {seam:.2f} px)")

    lp = pane["Logo00Pic"]
    check(abs(lp["w"]) <= 128, "the logo fits the 4:3 view (128 px)")
    return not fails


if __name__ == "__main__":
    look = sys.argv[1]
    ok = main(look, sys.argv[2] if len(sys.argv) > 2 else None)
    print("PASS" if ok else f"FAIL ({len(fails)})", f"- {len(warns)} warnings" if warns else "")
    sys.exit(0 if ok else 1)
