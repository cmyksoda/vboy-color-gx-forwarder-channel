# VBoy Color GX — Wii forwarder channel

Builds two channels that boot `sd:/apps/vbcgx/boot.dol` (or the same path on USB):

- `VBoy Color GX - VBCG [cmyksoda] (Wii).wad`, for an original Wii
- `VBoy Color GX - VBCG [cmyksoda] (vWii).wad`, for a Wii U's vWii

and the release zips `Wii-ONLY-VBCG-v<N>.zip` / `vWii-ONLY-VBCG-v<N>.zip`, each a `VBCG-v<N>/` folder with
README.md, LICENSE and that console's WAD. The names come from `TITLE`/`TITLE_ID`/`USERNAME` in
`build/tools/vbcgx.py`.

```
build/.venv/bin/python build/tools/build_icon_v2.py
build/.venv/bin/python build/tools/build_banner.py paint
build/.venv/bin/python build/tools/build_sound.py
build/.venv/bin/python build/tools/build_splash.py
build/.venv/bin/python build/tools/package.py 1
```

The first four write `build/out/icon-clash2.bin`, `banner-paint.bin`, `sound.bin` and the two splash PNGs in
`splash/`. `package.py` builds both WADs, runs `verify_wad.py` on each (it refuses to zip a WAD that fails), and
writes the zips to `build/out/`. Needs `wine` (for Benzin), Inkscape (only to re-render the controller), and a
Python venv:

```
python3 -m venv build/.venv
build/.venv/bin/pip install Pillow pycryptodome numpy scipy
```

> **The build will not run as-is from a fresh clone.** Three third-party inputs are deliberately not
> redistributed here. All have fixed homes inside the project, so nothing needs repointing:
>
> - `donor/FCE Ultra GX - FCEU [Tantric].wad`, the Wii channel this one is derived from, from the
>   [FCE Ultra GX](https://github.com/dborth/fceugx) channel installer.
> - `donor/FCE Ultra GX vWii - FCEU [Tantric].wad`, the vWii channel. Tantric ships it only inside his vWii
>   channel installer (`FCEUltraGX-vWii-Channel-Installer.zip`, FCE Ultra GX 4.0.3).
>   `build/tools/extract_installer.py` pulls it out (see below).
> - `build/tools/benzin/BENZIN.EXE` and its `CYGWIN1.DLL`, for the `brlyt`/`brlan` XML round-trips. A Windows
>   binary that runs under plain `wine`.
>
> The donor WADs stay out because a fakesigned channel carries Nintendo's certificate chain and a ticket, which
> is a different matter from shipping GPL'd source.

## What goes on the SD card

```
sd:/apps/vbcgx/boot.dol    <- VBoy Color GX itself
sd:/vbcgx/                 <- its games, saves and settings
```

Exactly what VBoy Color GX's own [release zip](https://github.com/cmyksoda/vbcgx#installing) puts there. The
channel passes no arguments, so the app starts as it would from the Homebrew Channel.

## Channel properties

```
Title ID     00010001-VBCG
Name         VBoy Color GX (all ten languages)
Boot IOS     58
Region       Free
NAND blocks  14 (Wii), 12 (vWii)
Looks for    apps/vbcgx/boot.dol   on SD or USB
```

NAND blocks are the decrypted contents' total size over 128 KiB, rounded up. The vWii build is two blocks
smaller because Tantric's vWii NAND loader and forwarder are smaller.

## Wii and vWii

**Tantric's Wii forwarder cannot boot on a Wii U's vWii**: the channel installs and its banner plays, but
pressing Start gives a black screen. His vWii channel is a separate build, and a channel built on its NAND
loader and forwarder starts fine on the vWii. So the two WADs share content 0 (the banner archive: icon,
banner, sound) and the title ID, and differ in contents 1 and 2, which come from the matching donor.
`build_wad.py --vwii` picks the vWii donor; `package.py` builds both.

### Getting the vWii donor

```
build/.venv/bin/python build/tools/extract_installer.py \
    <vWii installer>/apps/fceugx-channel-installer/boot.dol \
    "donor/FCE Ultra GX vWii - FCEU [Tantric].wad" \
    "donor/FCE Ultra GX - FCEU [Tantric].wad"
```

The installer carries the CP and XS certificates, the ticket, the TMD and the encrypted contents back to back.
Every content is decrypted with the ticket's title key and must match its SHA-1 in the TMD before anything is
written. The installer leaves out the root CA certificate (the console already has it), but a WAD manager
checks the ticket against the WAD's own chain: a vWii WAD with a broken chain fails in YAWMM at the ticket with
`ret = -4100`. So the extractor takes Nintendo's standard 2,560-byte chain from the Wii donor, after checking that
its CP and XS certificates are the installer's own, byte for byte.

## Changes made to the forwarder

The forwarder is Tantric's DOL with **three in-place data edits and no code touched**. `verify_wad.py` checks
that the whole `.text` section is byte-identical to his.

| what | Wii forwarder | vWii forwarder |
|---|---|---|
| 4:3 splash PNG | `0x081700`, 165,683 bytes of room | `0x056C00`, 165,683 bytes of room |
| 16:9 splash PNG | `0x0A9E40`, 157,270 bytes of room | `0x07F340`, 157,270 bytes of room |
| app path string | `0x0D3694` | `0x0A849C` |
| `.text` (untouched) | 529,888 bytes | 355,072 bytes |

`build_splash.slots()` finds the two splash PNGs (the first two 640×480 RGB PNGs in the forwarder) and
`build_wad.py` finds the path string by searching for `%s:/apps/fceugx/boot.dol`, so neither offset is
hardcoded. `%s:/apps/vbcgx/boot.dol` is shorter than the original and overwrites it in place; the rest of its
slot is zeroed.

### Splashes

`build_splash.py` draws both: the banner's red grid on black, the VBoy Color GX logo (rebuilt from the
full-size logo in the app icon's one-row layout), and "Loading..." in Fredoka SemiBold, placed like the
mGBA GX channel's splash. They must stay **colortype 2 RGB** (Tantric's PNGU decoder rejects palette PNGs) and
fit their slot, which is zero-padded after `IEND`. Both use about a third of their room.

The **16:9 splash** is the wide picture squeezed to 640 pixels, because the Wii stretches its 640×480 picture to
fill a widescreen set. Its grid is drawn at the squeezed spacing (24-pixel columns), so the cells come out
square and the lines stay sharp after the stretch.

## Banner sound

`sound.bin` is a looping **stereo BNS at 32 kHz**, built by `build_sound.py` from `audio/audio.wav` (44.1 kHz,
130 bpm). The first four bars play once, then bars five to eight loop.

- **The loop point is the bar line**, worked out from the tempo (frame 325,662 at 44.1 kHz). The song is
  resampled with an exact rational filter (`scipy.signal.resample_poly`, no delay), with the loop's opening
  appended after the end so the filter sees the real continuation at the seam.
- **Twelve samples of silence go in front**, so the loop starts on a 14-sample ADPCM frame.
- **INFO stores the loop's predictor and history** (the decoded samples just before the loop start), so the DSP
  resumes each pass exactly as the first pass decoded it. libWiiSharp and both donors leave these zero.
- **The loop end is the last sample played, not a count.** In a recording of the real Wii Menu (Dolphin's audio
  dump), a BNS whose loop-end field held the sample count played one sample too many on every pass. With the
  last sample's index there, every seam matches with no drift.
- **The last ADPCM frame is padded with the loop's opening**, not zeros, so a player that reads one sample past
  the end still plays the song.

32 kHz is the rate the Wii mixes all its sound at. The song stays stereo because it uses stereo (the side
signal is 8.6 dB under the middle). No banner sound size limit is documented; at 540,360 bytes it is twice the
mGBA GX channel's mono jingle.

## The animations

Both layouts are Tantric's, edited rather than rebuilt: his pane and material names, his section list.

- **Icon:** Tantric's 1200-frame (20-second) loop with his logo flips key for key: a double flip, 8 seconds of
  the Virtual Boy logo, a triple flip, 6 seconds of the VBoy Color logo, a flip back. Underneath, a Mario Clash
  stage and story drawn from VBoy Color GX's own frames: every sprite and stage piece, at the game's own
  timing and walking speed, with every frame on a whole pixel. The VBoy Color logo's V ends in a solid stem
  (`icon_v2.solid_v_tip`), because its original one-pixel point fades out on a CRT. `verify_icon_v2.py` checks
  the view and every actor against the story on every frame.
- **Banner:** Tantric's parade conveyor (copies 1024 apart, his four slots and timing) carrying Wario,
  Ballom, Jack Frost and a Space Invaders formation, over a grid that turns into a rainbow behind Wario. His
  title tab drops in, the controller pops and rocks, the logo flies in and bobs. `verify_banner.py` checks the
  conveyor, the rainbow and every cel against the model in `banner_model.py`.
- **Whole-number scaling only.** The walkers drawn at 2× use nearest-neighbor filtering. The Wii Menu ignores
  the layout's filter bits but honors the min/mag filter fields in each texture's own TPL header, so those
  carry it. Ballom, at 1.5×, is drawn at that size ahead of time and shown 1:1, with both eyes redrawn as the
  same shape (`banner_scene.ballom_15`), since scaling by 1.5 would leave them uneven.
- **The Menu animates a material on only one pane**, so every pane has its own material.

## Sizes

The icon is 90,272 bytes uncompressed, 88% of the System Menu's 102,400-byte cap (FCE Ultra GX's own icon is
94,432). The banner is 344,032 bytes, 25% of FCE Ultra GX's banner and 57% of the 600,000-byte share
`verify_banner.py` allows.

## Verification

Run `verify_wad.py <wad> clash2 paint` before installing anything (`package.py` does). It checks:
- the certificate chain;
- every content's SHA-1 against the TMD;
- both fakesignatures, and TMD `0x19A` left zero;
- the title ID against reserved ones;
- that content 1 is Tantric's untouched NAND loader (Wii or vWii);
- the forwarder edits, and that its `.text` is untouched;
- both splash slots;
- the IMET MD5, sizes and name;
- that the sound is `build_sound.py`'s and loops from an ADPCM frame;
- that the icon and banner inside pass `verify_icon_v2.py` and `verify_banner.py`.

## Assets

| path | used for |
|---|---|
| `icon/stage-clean-m0.png`, `icon/stage-worlds-m0.npy` | the Mario Clash stage and its layer order, captured from VBoy Color GX |
| `icon/w1-clips.json`, `icon/*/figs/` | the game's own sprite frames and their timing |
| `icon/vblogo-game.png` | the Virtual Boy logo, from the game |
| `icon/vbcgx-logo.png` | the VBoy Color GX logo (the app's Homebrew Channel icon) |
| `banner/cast/` | the walkers' and invaders' cels, with their step timing (`cels.json`) |
| `banner/vbcontroller.svg` | the controller vector; `build/controller/` regenerates it and its 148-px PNG |
| `banner/vbcgx-logo.png` | the banner logo (the app's README logo) |
| `audio/audio.wav` | the banner song |
| `splash/` | both splash screens (built by `build_splash.py`) |
| `build/fonts/Fredoka.ttf` | the splash lettering, under the SIL Open Font License (`Fredoka-OFL.txt`) |

#### AI Disclosure

The entirety of *this* `.md` file was generated using Claude Code.
