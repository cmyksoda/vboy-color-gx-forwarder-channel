"""Assemble the channel WAD: build_wad.py <icon look> <banner design> [out.wad] [--vwii]

Starts from Tantric's FCE Ultra GX channel: its ticket, TMD (IOS58) and certificate chain, its untouched NAND
loader (content 1), and its forwarder (content 2) with three data changes in place: the two splash PNGs (from
build_splash.py, zero-padded to their slots) and the app folder in its boot path, which is shorter than the
original. Content 0 is its banner archive with our icon.bin, banner.bin and sound.bin (Jaxi's song, from
build_sound.py); the IMET header gets the new sizes and the name.
"""

import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import build_splash as SP
from vbcgx import OUT, ROOT, TITLE, TITLE_ID
from wiilib import U8, WAD, imd5_unwrap, imet_set, imet_verify, unpack_lz77_imd5

DONORS = {
    "wii": os.path.join(ROOT, "donor", "FCE Ultra GX - FCEU [Tantric].wad"),
    # from his vWii installer
    "vwii": os.path.join(ROOT, "donor", "FCE Ultra GX vWii - FCEU [Tantric].wad"),
}
OLD_PATH = b"%s:/apps/fceugx/boot.dol"
NEW_PATH = b"%s:/apps/vbcgx/boot.dol"


def patch_forwarder(fw):
    """The splash PNGs and the boot path, in place; the rest of each slot is zeroed."""
    out = bytearray(fw)
    for tag, (at, room) in SP.slots(fw).items():
        assert fw[at:at + 8] == b"\x89PNG\r\n\x1a\n", f"no PNG at {at:#x}"
        png = open(SP.path(tag), "rb").read()
        assert png[25] == 2 and len(png) <= room
        out[at:at + room] = png.ljust(room, b"\0")
    i = fw.index(OLD_PATH)
    assert fw.count(OLD_PATH) == 1
    assert len(NEW_PATH) <= len(OLD_PATH)
    out[i:i + len(OLD_PATH)] = NEW_PATH.ljust(len(OLD_PATH), b"\0")
    return bytes(out), i


def build(icon_look, banner_design, out_path=None, console="wii"):
    w = WAD.load(DONORS[console])
    app = w.contents[0]
    cut = app.find(b"\x55\xAA\x38\x2D")
    prefix, meta = app[:cut], U8.load(app[cut:])

    icon = open(os.path.join(OUT, f"icon-{icon_look}.bin"), "rb").read()
    banner = open(os.path.join(OUT, f"banner-{banner_design}.bin"), "rb").read()
    meta.replace("meta/icon.bin", icon)
    meta.replace("meta/banner.bin", banner)
    meta.replace("meta/sound.bin", open(os.path.join(OUT, "sound.bin"), "rb").read())
    assert not meta.check_tree()

    sizes = (len(unpack_lz77_imd5(icon)), len(unpack_lz77_imd5(banner)), len(imd5_unwrap(meta.get("meta/sound.bin"))))
    app = imet_set(prefix + meta.to_bytes(), TITLE, sizes)
    assert imet_verify(app)
    w.contents[0] = app
    w.contents[2], at = patch_forwarder(w.contents[2])
    w.set_title_id(TITLE_ID)

    out = out_path or os.path.join(OUT, f"{TITLE} - {TITLE_ID} [{icon_look}+{banner_design}].wad")
    size = w.save(out)
    return out, size, sizes, at


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--vwii"]
    look, design = args[0], args[1]
    out, size, sizes, at = build(
        look, design, args[2] if len(args) > 2 else None, "vwii" if "--vwii" in sys.argv else "wii"
    )
    print(f"wrote {out}  {size:,} bytes")
    print(f"  IMET sizes icon={sizes[0]:,} banner={sizes[1]:,} sound={sizes[2]:,}")
    print(f"  boot path patched at {at:#x}")

    w = WAD.load(out)
    for i, c in enumerate(w.contents):
        print(f"  content{i}  {len(c):,} bytes  sha1 {hashlib.sha1(c).hexdigest()[:16]}")
