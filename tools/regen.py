#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Source-maintenance helper: replace a line range of a .dtsi with nodes
rendered from a reference DTB (labels/&refs restored).

  regen.py REF.dtb FILE START END PARENTPATH CHILD [CHILD...] [--indent N]
Lines START..END (1-based, inclusive) are replaced; use END=START-1 to
insert before START without deleting anything."""
import argparse
import fdtlib as F
import dt2src as D

ap = argparse.ArgumentParser()
ap.add_argument("dtb")
ap.add_argument("file")
ap.add_argument("start", type=int)
ap.add_argument("end", type=int)
ap.add_argument("parent")
ap.add_argument("children", nargs="+")
ap.add_argument("--indent", type=int, default=2)
a = ap.parse_args()
root = F.load(a.dtb)
S = D.BaseCtx(root)
D.SYM.__init__("/home/angel/sapphire/ws/kernel_platform/msm-kernel/scripts/dtc/include-prefixes")
out = []


def show(n, path, ind):
    labs = S.labels.get(path, [])
    out.append("%s%s%s {" % (ind, "".join(l + ": " for l in labs), n.name))
    rev = list(n.props.items()) != D.ordered_props(n)
    for pn, v in D.ordered_props(n):
        if pn in ("phandle", "linux,phandle"):
            continue
        refs, sus = S.refs(pn, v)
        out.append(D.fmt_prop(pn, v, refs, ind + "\t"))
    for cn, c in D.ordered_children(n, rev):
        if not out[-1].endswith("{"):
            out.append("")
        show(c, path.rstrip("/") + "/" + cn, ind + "\t")
    out.append("%s};" % ind)


par = root.get(a.parent)
for i, ch in enumerate(a.children):
    if i:
        out.append("")
    show(par.children[ch], a.parent.rstrip("/") + "/" + ch, "\t" * a.indent)
lines = open(a.file).read().split("\n")
lines[a.start - 1:a.end] = out + ([""] if a.end >= a.start else [""])
open(a.file, "w").write("\n".join(lines))
print("replaced %d..%d with %d lines" % (a.start, a.end, len(out)))
