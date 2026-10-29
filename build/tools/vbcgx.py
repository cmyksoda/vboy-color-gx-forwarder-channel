"""Shared configuration: paths, donor, channel identity and viewports.

Coordinates follow the toolkit's convention (see to_pane): art is authored at
832x456 (banner) and 176x96 (icon), center-aligned to the viewport, and brlyt
panes are center-origin with +y up.
"""

import os
import subprocess

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
BUILD = os.path.join(ROOT, "build")
OUT = os.path.join(BUILD, "out")
EXTRACTED = os.path.join(BUILD, "extracted")
BENZIN = os.path.join(BUILD, "tools", "benzin")
DONOR = os.path.join(ROOT, "donor", "FCE Ultra GX - FCEU [Tantric].wad")

# ----------------------------------------------------------------- the channel

TITLE = "VBoy Color GX"
TITLE_ID = "VBCG"                # 00010001 56424347; VBGX is Tantric's Visual Boy Advance GX channel
# The app's SD folder is vbcgx (sd:/apps/vbcgx/boot.dol), the same on every card it ships to.
BOOT_PATH = "%s:/apps/vbcgx/boot.dol"
USERNAME = "cmyksoda"
WAD_NAME = f"{TITLE} - {TITLE_ID} [{USERNAME}].wad"

# ------------------------------------------------------------------- viewports

FPS = 60
BANNER_ART = (832, 456)          # authored size, incl. 112 px widescreen bleed each side
BANNER_43 = (608, 456)           # what a 4:3 TV shows
ICON_ART = (176, 96)             # incl. 24 px bleed each side
ICON_43 = (128, 96)

# The Wii Menu's "Wii Menu" / "Start" strip covers the banner below about pane y -118 (measured on PDWT).
MENU_CUT_Y = -118.0


def benzin(*args):
    """Run Benzin under wine. 'r' rips a binary to XML, 'm' makes it back."""
    r = subprocess.run(["wine", "BENZIN.EXE", *args], cwd=BENZIN,
                       capture_output=True, env={**os.environ, "WINEDEBUG": "-all"})
    out = (r.stdout + r.stderr).decode(errors="replace")
    if "Couldn't" in out or r.returncode != 0:
        raise RuntimeError(f"benzin {args}: {out}")
    return out


def to_pane(px, py, art=BANNER_ART):
    """Authored top-left-origin pixel -> center-origin pane coords (+y up)."""
    w, h = art
    return px - w / 2.0, h / 2.0 - py


def ceil4(n):
    return (n + 3) // 4 * 4
