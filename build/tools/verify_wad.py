"""Check a finished channel WAD before anything installs it: verify_wad.py <wad> <icon look> <banner design>

The container (contents hashed into the TMD, the TMD and ticket fakesigned with 0x19A left zero, IOS58,
the title ID clear of system channels and known homebrew), the IMET header (MD5, the three sizes, the name
in all ten slots), Tantric's NAND loader untouched, the forwarder changed only in its splash and boot path slots with its
code untouched, Jaxi's song looping from an ADPCM frame, and the icon and banner inside passing their own checks.
"""

import hashlib
import os
import struct
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(__file__))

import build_sound as BS
import build_splash as BS_SPLASH
import build_wad as BW
from vbcgx import OUT, TITLE, TITLE_ID
from wiilib import U8, WAD, imd5_unwrap, imet_titles, imet_verify, unpack_lz77_imd5

RESERVED = {b"HAEA", b"HABA", b"HACA", b"HAFA", b"HAAA", b"HABK", b"HCZA", b"HAYA", b"HAZA", b"HAXX", b"JODI",
            b"DUTB", b"LULZ", b"OHBC", b"1234", b"FCEU", b"9XGX", b"VBAG", b"VBGX", b"GBGX", b"WIIM", b"SNES",
            b"LSDE", b"ZGXA", b"PDWT", b"UHBC", b"ESLT"}

fails = []


def check(ok, what):
    if not ok:
        fails.append(what)
    print(("  ok   " if ok else "  FAIL ") + what)


def main(path, look, design):
    w = WAD.load(path)
    w1 = w.contents[1]
    console = next((c for c, p in BW.DONORS.items() if WAD.load(p).contents[1] == w1), None)
    check(console is not None, f"Tantric's {console or 'unknown'} NAND loader is untouched")
    donor = WAD.load(BW.DONORS[console or "wii"])

    tid = w.title_id
    print(f"{os.path.basename(path)}: title {tid.hex()} ({tid[4:].decode()})")
    check(tid[:4] == b"\x00\x01\x00\x01" and tid[4:] == TITLE_ID.encode(), f"title ID 00010001-{TITLE_ID}")
    check(tid[4:] not in RESERVED, "title ID clear of system channels and known homebrew channels")
    check(struct.unpack(">Q", w.tmd[0x184:0x18C])[0] == 0x000000010000003A, "boots IOS58, like Tantric's channels")

    n = struct.unpack(">H", w.tmd[0x1DE:0x1E0])[0]
    check(n == 3 and len(w.contents) == 3, "three contents: banner archive, NAND loader, forwarder")
    ok = all(
        w.tmd[0x1E4 + i * 36 + 16:0x1E4 + i * 36 + 36] == hashlib.sha1(c).digest()
        for i, c in enumerate(w.contents)
    )
    check(ok, "every content's SHA-1 matches the TMD")
    check(
        w.certs == WAD.load(BW.DONORS["wii"]).certs,
        "the certificate chain is Nintendo's standard CA, CP and XS (a WAD manager checks the ticket against it)"
    )
    check(hashlib.sha1(w.tmd[0x140:]).digest()[0] == 0, "TMD fakesigned")
    check(w.tmd[0x19A:0x19C] == bytes(2), "TMD 0x19A left zero (the Menu refuses some channels otherwise)")
    check(hashlib.sha1(w.tik[0x140:]).digest()[0] == 0, "ticket fakesigned")

    fw, dfw = w.contents[2], donor.contents[2]
    i = dfw.index(BW.OLD_PATH)
    splash = BS_SPLASH.slots(dfw)
    slots = [(at, at + room) for at, room in splash.values()] + [(i, i + len(BW.OLD_PATH))]
    diff = [k for k in range(len(fw)) if fw[k] != dfw[k]]
    check(len(fw) == len(dfw) and all(any(a <= k < b for a, b in slots) for k in diff),
          f"the forwarder differs from Tantric's only in its two splash slots and its boot path ({len(diff):,} bytes)")

    t0, tsz = struct.unpack(">I", dfw[0:4])[0], struct.unpack(">I", dfw[144:148])[0]
    check(fw[t0:t0 + tsz] == dfw[t0:t0 + tsz], f"its code (.text, {tsz:,} bytes) is byte-identical to Tantric's")
    for tag, (at, room) in splash.items():
        png = open(BS_SPLASH.path(tag), "rb").read()
        check(
            fw[at:at + room] == png.ljust(room, b"\0")
            and png[25] == 2
            and struct.unpack(">II", png[16:24]) == (640, 480),
            f"the {tag} splash slot holds splash-{tag}.png, a 640x480 RGB PNG "
            f"({len(png):,} of {room:,} bytes), then zeros"
        )

    check(fw[i:i + len(BW.NEW_PATH)] == BW.NEW_PATH and fw[i + len(BW.NEW_PATH)] == 0,
          f"it boots {BW.NEW_PATH.decode()} from SD or USB")

    app = w.contents[0]
    check(imet_verify(app), "IMET MD5 is right")
    _, names = imet_titles(app)
    check(len(names) == 10 and all(n == TITLE for n in names), f'the name "{TITLE}" fills all ten language slots')

    meta = U8.load(app[app.find(b"\x55\xAA\x38\x2D"):])
    off = app.find(b"IMET")
    sizes = struct.unpack(">III", app[off + 0x0C:off + 0x18])
    real = (len(unpack_lz77_imd5(meta.get("meta/icon.bin"))), len(unpack_lz77_imd5(meta.get("meta/banner.bin"))),
            len(imd5_unwrap(meta.get("meta/sound.bin"))))

    check(sizes == real, f"IMET records the icon, banner and sound sizes ({real[0]:,} / {real[1]:,} / {real[2]:,})")
    bns = imd5_unwrap(meta.get("meta/sound.bin"))
    check(bns == open(os.path.join(OUT, "sound.bns"), "rb").read(), "the sound is Jaxi's song from build_sound.py")
    rate, loop, ls, last, chans = BS.parse_bns(bns)
    check(
        loop == 1 and 0 < ls < last and ls % 14 == 0,
        f"it loops from sample {ls:,} (on an ADPCM frame) through {last:,}"
    )

    tmp = tempfile.mkdtemp(prefix=".verify-", dir=os.path.dirname(os.path.abspath(path)))
    icon_check = ["verify_icon_v2.py"] if look == "clash2" else ["verify_icon.py", look]
    for part, cmd in (("icon", icon_check), ("banner", ["verify_banner.py", design])):
        p = os.path.join(tmp, f"{part}.bin")
        open(p, "wb").write(meta.get(f"meta/{part}.bin"))
        r = subprocess.run(
            [sys.executable, os.path.join(os.path.dirname(__file__), cmd[0]), *cmd[1:], p],
            capture_output=True, text=True
        )
        check(r.returncode == 0, f"the {part} inside passes its own checks")
        os.remove(p)
    os.rmdir(tmp)

    return not fails


if __name__ == "__main__":
    ok = main(*sys.argv[1:4])
    print("PASS" if ok else f"FAIL ({len(fails)})")
    sys.exit(0 if ok else 1)
