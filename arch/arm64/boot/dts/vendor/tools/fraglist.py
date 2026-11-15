#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""List the fragments of an overlay: index, target, child nodes / props."""
import sys
import fdtlib as F

root = F.load(sys.argv[1])
fx = F.fixup_positions(root)
lfx = F.local_fixup_positions(root)
ph = F.phandle_map(root)
frags = [(n, c) for n, c in root.children.items() if "__overlay__" in c.children]
frags.sort(key=lambda x: int(x[0].split("@")[1]) if "@" in x[0] else -1)
for name, frag in frags:
    fp = "/" + name
    if "target" in frag.props:
        lab = fx.get((fp, "target"), {}).get(0)
        if lab:
            t = "&" + lab
        else:
            t = "REF:" + ph.get(F.cells(frag.props["target"])[0], "?")
    else:
        t = F.strlist(frag.props.get("target-path", b"?\0"))[0]
    ov = frag.children["__overlay__"]
    kids = list(ov.children)
    props = list(ov.props)
    print("%-14s %-40s props=%d %s" % (name, t, len(props),
          ",".join(kids)[:150] if len(sys.argv) < 3 else ",".join(kids)))
