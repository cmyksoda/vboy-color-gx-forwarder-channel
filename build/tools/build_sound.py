"""Build sound.bin: Jaxi's banner song as a looping stereo BNS (Nintendo DSP ADPCM, codec 0).

The first INTRO_BARS bars play once and the rest loops to the end. The loop point is the bar line, worked out
from the tempo. The song is resampled with the loop's opening appended after its end, so the filter sees the
real continuation at the seam, and a few samples of silence go in front so the loop starts on a 14-sample ADPCM
frame. INFO stores the loop's predictor and history, so the DSP resumes the loop exactly as the first pass
decoded it, and its loop end as the last sample played: the Menu plays that sample too (its audio, dumped by
Dolphin, drifted a sample per pass when the field held the count, as libWiiSharp writes it).

DSP ADPCM: 14 samples per 8-byte frame; a header byte carries a 4-bit scale exponent and a 4-bit index into
8 pairs of order-2 predictor coefficients (Q11). Decode, per VGAudio:
    scale     = (1 << (ps & 0xF)) * 2048
    predicted = c1*hist1 + c2*hist2
    sample    = clamp16((predicted + scale*nibble + 1024) >> 11)
"""

import os
import struct
import sys
import wave
from fractions import Fraction

import numpy as np
from scipy.signal import resample_poly

sys.path.insert(0, os.path.dirname(__file__))

from wiilib import imd5_wrap

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
BUILD = os.path.join(ROOT, "build")
SRC = os.path.join(ROOT, "audio", "audio.wav")
RATE = 32000                     # what the mGBA GX channel uses, proven on Jaxi's Wii
BPM, BEATS_PER_BAR, INTRO_BARS = 130, 4, 4
SEAM_PAD = 0.1                   # seconds of the loop's opening resampled after the end


def read_wav(path):
    with wave.open(path, "rb") as w:
        ch, sw, rate, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        raw = w.readframes(n)
    assert sw == 2, f"need 16-bit PCM, got {sw*8}-bit"
    return np.frombuffer(raw, "<i2").reshape(-1, ch).T.astype(np.float64), rate


def resample(x, src_rate, rate):
    """Each channel to `rate` with an exact rational polyphase filter, which adds no delay."""
    r = Fraction(rate, src_rate)
    y = resample_poly(x, r.numerator, r.denominator, axis=1)
    return np.clip(np.round(y), -32768, 32767).astype(np.int64)


def lpc2(x):
    """Optimal order-2 predictor for a block, as Q11 ints."""
    r0 = r1 = r2 = 0
    for i in range(len(x)):
        r0 += x[i] * x[i]
        if i >= 1:
            r1 += x[i] * x[i - 1]
        if i >= 2:
            r2 += x[i] * x[i - 2]
    det = r0 * r0 - r1 * r1
    if r0 == 0 or det == 0:
        return 2048, 0
    a1 = (r1 * r0 - r2 * r1) / det
    a2 = (r0 * r2 - r1 * r1) / det
    q = lambda v: max(-32768, min(32767, int(round(v * 2048))))
    return q(a1), q(a2)


def make_coefs(samples):
    seg = max(1, len(samples) // 8)
    coefs = []
    for i in range(8):
        blk = samples[i * seg:(i + 1) * seg] or samples[-seg:]
        coefs.extend(lpc2(blk))
    return coefs[:16]


def clamp16(v):
    return -32768 if v < -32768 else (32767 if v > 32767 else v)


def encode_frame(targets, c1, c2, h1, h2, e, keep=14):
    scale = (1 << e) * 2048
    err = 0
    nib = []
    for i, t in enumerate(targets):
        pred = c1 * h1 + c2 * h2
        n = int(round(((t << 11) - pred - 1024) / scale))
        n = -8 if n < -8 else (7 if n > 7 else n)
        dec = clamp16((pred + scale * n + 1024) >> 11)
        if i < keep:
            err += (dec - t) * (dec - t)
        h2, h1 = h1, dec
        nib.append(n)
    return err, nib, h1, h2


def encode(samples, coefs, heard=None):
    """`heard` samples are ever played; past them the last frame is only padding, so its fit ignores them."""
    out = bytearray()
    h1 = h2 = 0
    nframes = (len(samples) + 13) // 14
    for f in range(nframes):
        targets = samples[f * 14:f * 14 + 14]
        targets = list(targets) + [0] * (14 - len(targets))
        keep = 14 if heard is None else max(1, min(14, heard - f * 14))

        best = None
        for p in range(8):
            c1, c2 = coefs[p * 2], coefs[p * 2 + 1]
            # estimate the scale from source-history residuals, then probe around it
            maxd, s1, s2 = 0, h1, h2
            for t in targets[:keep]:
                d = abs((t << 11) - (c1 * s1 + c2 * s2) - 1024)
                maxd = max(maxd, d)
                s2, s1 = s1, t
            e0 = 0
            while e0 < 15 and (1 << e0) * 2048 * 7 < maxd:
                e0 += 1
            scales = range(16) if keep < 14 else {max(0, e0 - 1), e0, min(15, e0 + 1)}
            for e in scales:
                err, nib, nh1, nh2 = encode_frame(targets, c1, c2, h1, h2, e, keep)
                if best is None or err < best[0]:
                    best = (err, p, e, nib, nh1, nh2)

        _, p, e, nib, h1, h2 = best
        out.append((p << 4) | e)
        for i in range(0, 14, 2):
            out.append(((nib[i] & 0xF) << 4) | (nib[i + 1] & 0xF))
    return bytes(out)


def decode(data, coefs, count, h1=0, h2=0):
    outs = []
    for o in range(0, len(data), 8):
        ps = data[o]
        scale = (1 << (ps & 0xF)) * 2048
        c1, c2 = coefs[((ps >> 4) & 7) * 2], coefs[((ps >> 4) & 7) * 2 + 1]
        for i in range(14):
            b = data[o + 1 + i // 2]
            n = (b >> 4) if i % 2 == 0 else (b & 0xF)
            if n > 7:
                n -= 16
            s = clamp16((c1 * h1 + c2 * h2 + scale * n + 1024) >> 11)
            h2, h1 = h1, s
            outs.append(s)
            if len(outs) == count:
                return outs
    return outs


def build_bns(chans, rate, last, loop_start):
    """chans: one or two dicts with adpcm, coefs, ps, loop_ps, loop_h1, loop_h2. The layout is libWiiSharp's
    (CustomizeMii): INFO's offsets count from INFO+8, then a channel table, 12-byte channel entries
    (data offset, ADPCM info offset, 0) and 48-byte ADPCM infos; channel data follow one another in DATA."""
    n = len(chans)
    table, entries = 0x18, 0x18 + 4 * n
    infos = entries + 12 * n
    info = bytearray(8 + infos + 0x30 * n)
    info[0:4] = b"INFO"
    struct.pack_into(">I", info, 4, len(info))
    struct.pack_into(">BBB", info, 8, 0, 1, n)                 # DSP ADPCM, looping, channels
    struct.pack_into(">HxxIII", info, 12, rate, loop_start, last, table)

    data_off = 0
    for i, c in enumerate(chans):
        struct.pack_into(">I", info, 8 + table + 4 * i, entries + 12 * i)
        struct.pack_into(">II", info, 8 + entries + 12 * i, data_off, infos + 0x30 * i)
        base = 8 + infos + 0x30 * i
        struct.pack_into(">16h", info, base, *c["coefs"])
        struct.pack_into(">HHhhHhh", info, base + 32, 0, c["ps"], 0, 0, c["loop_ps"], c["loop_h1"], c["loop_h2"])
        data_off += len(c["adpcm"])

    data = b"DATA" + struct.pack(">I", 8 + data_off) + b"".join(c["adpcm"] for c in chans)
    head = bytearray(32)
    head[0:4] = b"BNS "
    head[4:8] = bytes.fromhex("feff0100")
    struct.pack_into(">IHHIIII", head, 8, 32 + len(info) + len(data), 32, 2, 32, len(info), 32 + len(info), len(data))
    return bytes(head) + bytes(info) + data


def parse_bns(bns):
    """(rate, loop flag, loop start, last sample, [(adpcm, coefs, loop_ps, loop_h1, loop_h2)]) read back from the file."""
    info, data = bns[0x20:], bns[0x20 + struct.unpack_from(">I", bns, 0x14)[0]:]
    loop, n = info[9], info[10]
    rate, ls, le, table = struct.unpack_from(">HxxIII", info, 12)
    offs = []
    for i in range(n):
        entry = struct.unpack_from(">I", info, 8 + table + 4 * i)[0]
        offs.append(struct.unpack_from(">II", info, 8 + entry))
    chans = []
    for i, (d0, ai) in enumerate(offs):
        d1 = offs[i + 1][0] if i + 1 < n else len(data) - 8
        coefs = list(struct.unpack_from(">16h", info, 8 + ai))
        _, _, _, _, lps, lh1, lh2 = struct.unpack_from(">HHhhHhh", info, 8 + ai + 32)
        chans.append((data[8 + d0:8 + d1], coefs, lps, lh1, lh2))
    return rate, loop, ls, le, chans


def main():
    x, src_rate = read_wav(SRC)
    n_src = x.shape[1]
    ls_src = round(INTRO_BARS * BEATS_PER_BAR * 60 / BPM * src_rate)
    print(f"source: {x.shape[0]} ch, {src_rate} Hz, {n_src} frames ({n_src / src_rate:.3f} s); "
          f"loop from the {INTRO_BARS}-bar line, frame {ls_src}")

    pad = x[:, ls_src:ls_src + int(SEAM_PAD * src_rate)]
    y = resample(np.concatenate([x, pad], axis=1), src_rate, RATE)
    total = round(n_src * RATE / src_rate)
    ls = round(ls_src * RATE / src_rate)
    lead = -ls % 14
    y = np.concatenate([np.zeros((y.shape[0], lead), np.int64), y[:, :total]], axis=1)
    ls, total = ls + lead, total + lead
    print(f"resampled to {RATE} Hz; {lead} samples of silence in front put the loop on an ADPCM frame: "
          f"loop {ls}..{total} ({(total - ls) / RATE:.4f} s), intro {ls / RATE:.4f} s")

    w = 1500
    for c in range(y.shape[0]):
        best = max(
            range(-2, 3),
            key=lambda o: np.corrcoef(y[c, total - w + o - 2:total + o - 2], y[c, ls - w - 2:ls - 2])[0, 1],
        )
        r0 = np.corrcoef(y[c, total - w:total], y[c, ls - w:ls])[0, 1]
        print(f"  ch {c}: the loop's last {w} samples against those before its start: "
              f"correlation {r0:.5f}, best offset {best:+d}")
        assert best == 0 and r0 > 0.999, "the loop end doesn't line up with the loop start"

    chans = []
    for c in range(y.shape[0]):
        s = [int(v) for v in y[c]]
        # the last frame's spare samples continue into the loop, so a player that reads one past the end
        # still plays the song
        s += s[ls:ls + -total % 14]
        coefs = make_coefs(s)
        adpcm = encode(s, coefs, total + 1)
        back = decode(adpcm, coefs, total + -total % 14)

        noise = sum((a - b) ** 2 for a, b in zip(s[:total], back))
        snr = 10 * np.log10(sum(v * v for v in s[:total]) / max(1, noise))
        end_err = max(abs(back[i] - s[i]) for i in (total - 2, total - 1, total))
        assert end_err <= 4 * (noise / total) ** 0.5, f"ch {c}: the samples at the loop's end are off by {end_err}"
        chans.append(dict(adpcm=adpcm, coefs=coefs, ps=adpcm[0], loop_ps=adpcm[ls // 14 * 8],
                          loop_h1=back[ls - 1], loop_h2=back[ls - 2], first=back))
        print(f"  ch {c}: encoded {len(adpcm):,} bytes, round-trip SNR {snr:.1f} dB")

    bns = build_bns(chans, RATE, total - 1, ls)
    rate, loop, ls2, last, parsed = parse_bns(bns)
    assert (rate, loop, ls2, last, len(parsed)) == (RATE, 1, ls, total - 1, len(chans)) and ls2 % 14 == 0

    for c, (adpcm, coefs, lps, lh1, lh2) in enumerate(parsed):
        first = chans[c]["first"]
        again = decode(adpcm[ls // 14 * 8:], coefs, 28, lh1, lh2)
        assert lps == adpcm[ls // 14 * 8] and again == first[ls:ls + 28], f"ch {c}: the loop doesn't resume as decoded"
        print(f"  ch {c}: from the stored loop history the loop's first two frames decode exactly as the first "
              f"pass; seam step {abs(first[ls] - first[total - 1])}, "
              f"the first pass's step into the loop {abs(first[ls] - first[ls - 1])}; "
              f"one sample past the end decodes to {first[total]} against the loop's first {first[ls]}")

    open(f"{BUILD}/out/sound.bns", "wb").write(bns)
    packed = imd5_wrap(bns)
    open(f"{BUILD}/out/sound.bin", "wb").write(packed)
    print(f"sound.bin: BNS {len(bns):,} bytes -> stored {len(packed):,} "
          f"({len(chans)} ch, {RATE} Hz, loop {ls}..{total - 1} inclusive)")


if __name__ == "__main__":
    main()
