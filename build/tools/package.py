"""The release: package.py <version number, e.g. 1>

Builds the Wii and vWii WADs, checks both, and zips each in Jaxi's layout: Wii-ONLY-<ID>-v<N>.zip and
vWii-ONLY-<ID>-v<N>.zip, each holding a <ID>-v<N>/ folder with README.md, LICENSE and that console's WAD.
"""

import os
import subprocess
import sys
import zipfile

sys.path.insert(0, os.path.dirname(__file__))
import build_wad as BW
from vbcgx import OUT, ROOT, TITLE, TITLE_ID, USERNAME


def main(n):
    for console, label in (("wii", "Wii"), ("vwii", "vWii")):
        wad = os.path.join(OUT, f"{TITLE} - {TITLE_ID} [{USERNAME}] ({label}).wad")
        BW.build("clash2", "paint", wad, console)
        r = subprocess.run(
            [sys.executable, os.path.join(os.path.dirname(__file__), "verify_wad.py"), wad, "clash2", "paint"],
            capture_output=True, text=True
        )
        assert r.returncode == 0, f"{os.path.basename(wad)} fails its checks:\n{r.stdout}"
        folder = f"{TITLE_ID}-v{n}"
        zpath = os.path.join(OUT, f"{label}-ONLY-{folder}.zip")
        with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
            d = zipfile.ZipInfo(folder + "/")
            d.external_attr = 0o40755 << 16 | 0x10          # a bare ZipInfo stores mode 000, which unzips unopenable
            z.writestr(d, b"")
            for src in (os.path.join(ROOT, "README.md"), os.path.join(ROOT, "LICENSE"), wad):
                z.write(src, f"{folder}/{os.path.basename(src)}")
        print(
            f"  {os.path.basename(zpath)}: {os.path.getsize(zpath):,} bytes ({os.path.basename(wad)} passes its checks)"
        )


if __name__ == "__main__":
    main(sys.argv[1])
