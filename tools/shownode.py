#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Print one node of a base DTB as DTS source (labels/&refs restored).
   shownode.py FILE.dtb /path/to/node [--depth N]"""
import sys
import argparse
import fdtlib as F
import dt2src as D

ap = argparse.ArgumentParser()
ap.add_argument("dtb")
ap.add_argument("path")
ap.add_argument("--depth", type=int, default=99)
a = ap.parse_args()
root = F.load(a.dtb)
S = D.BaseCtx(root)
D.SYM.__init__("/home/angel/sapphire/ws/kernel_platform/msm-kernel/scripts/dtc/include-prefixes")


def show(n, path, ind, depth):
    labs = S.labels.get(path, [])
    print("%s%s%s {" % (ind, "".join(l + ": " for l in labs), n.name or "/"))
    for pn, v in n.props.items():
        if pn in ("phandle", "linux,phandle"):
            continue
        refs, sus = S.refs(pn, v)
        print(D.fmt_prop(pn, v, refs, ind + "\t") + (" /*?ph*/" if sus else ""))
    if depth > 0:
        for cn, c in n.children.items():
            show(c, path.rstrip("/") + "/" + cn, ind + "\t", depth - 1)
    elif n.children:
        print("%s\t/* %d child nodes */" % (ind, len(n.children)))
    print("%s};" % ind)


n = root.get(a.path)
if n is None:
    sys.exit("no such node")
show(n, a.path, "", a.depth)
