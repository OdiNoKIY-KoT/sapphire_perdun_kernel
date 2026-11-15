#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Split a concatenated dtb.img (vendor_boot DTB section) or an Android
dtbo.img (DT table, magic d7b7ab1e) into individual blobs.

  splitimg.py IMAGE OUTDIR PREFIX      -> OUTDIR/PREFIXNN.dtb[o]
"""
import os
import struct
import sys

data = open(sys.argv[1], "rb").read()
out, pre = sys.argv[2], sys.argv[3]
os.makedirs(out, exist_ok=True)
blobs = []
if data[:4] == b"\xd7\xb7\xab\x1e":
    magic, total, hsz, esz, cnt, eoff, page, ver = struct.unpack(">8I", data[:32])
    for i in range(cnt):
        sz, off = struct.unpack(">II", data[eoff + i * esz: eoff + i * esz + 8])
        blobs.append(data[off:off + sz])
    ext = "dtbo"
else:
    p = 0
    while p + 8 <= len(data) and data[p:p + 4] == b"\xd0\x0d\xfe\xed":
        sz = struct.unpack(">I", data[p + 4:p + 8])[0]
        blobs.append(data[p:p + sz])
        p += sz
    ext = "dtb"
for i, b in enumerate(blobs):
    open(os.path.join(out, "%s%02d.%s" % (pre, i, ext)), "wb").write(b)
print("%d blobs" % len(blobs))
