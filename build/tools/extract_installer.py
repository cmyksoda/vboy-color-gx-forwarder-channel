"""Pull the channel out of one of Tantric's channel installers:
    extract_installer.py <installer boot.dol> <out.wad> <a WAD with the standard certificate chain>

The installer carries the CP and XS certificates, the ticket, the TMD and the encrypted contents back to back
(each block starting on a 64-byte boundary). It leaves out the root CA certificate, which the console already
has, but a WAD manager needs the whole chain: so the chain comes from a reference WAD whose CP and XS must be
the installer's own. The contents decrypt with the ticket's title key, and each must match its SHA-1 in the TMD
before anything is written.
"""

import hashlib
import struct
import sys

from Crypto.Cipher import AES

from wiilib import COMMON_KEY, WAD


def main(src, out, reference):
    b = open(src, "rb").read()
    certs = WAD.load(reference).certs
    assert len(certs) == 0xA00 and b.find(certs[0x400:]) >= 0, \
        "the reference's CP and XS certificates aren't the installer's"

    tik_at = b.find(b"Root-CA00000001-XS00000003") - 0x140
    tmd_at = b.find(b"Root-CA00000001-CP00000004") - 0x140
    tik = b[tik_at:tik_at + 0x2A4]
    n = struct.unpack(">H", b[tmd_at + 0x1DE:tmd_at + 0x1E0])[0]
    tmd = b[tmd_at:tmd_at + 0x1E4 + 36 * n]
    key = AES.new(COMMON_KEY, AES.MODE_CBC, tik[0x1DC:0x1E4] + b"\0" * 8).decrypt(tik[0x1BF:0x1CF])
    at = (tmd_at + len(tmd) + 63) & ~63

    contents = []
    for i in range(n):
        e = 0x1E4 + 36 * i
        idx, size, want = (
            struct.unpack(">H", tmd[e + 4:e + 6])[0],
            struct.unpack(">Q", tmd[e + 8:e + 16])[0],
            tmd[e + 16:e + 36],
        )
        blob = b[at:at + ((size + 15) & ~15)]
        plain = AES.new(key, AES.MODE_CBC, struct.pack(">H", idx) + b"\0" * 14).decrypt(blob)[:size]
        assert hashlib.sha1(plain).digest() == want, f"content {i} doesn't match its TMD hash"
        contents.append(plain)
        at = (at + len(blob) + 63) & ~63

    WAD(certs, b"", tik, tmd, contents, b"").save(out, fakesign=False)
    print(f"  {out}: title {tmd[0x18C:0x194].hex()}, contents {[len(c) for c in contents]}, all SHA-1s match the TMD")


if __name__ == "__main__":
    main(*sys.argv[1:4])
