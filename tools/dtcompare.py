#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Semantic comparison of two flattened device trees (DTB or DTBO).

  dtcompare.py STOCK OURS [--refs OURS_L.dtb] [-q] [--max N]

* Nodes/properties are matched by full path (order independent).
* Base trees: phandle values are not compared numerically.  A property cell
  that differs is accepted when both cells are phandles that resolve to the
  same node path.  If --refs is given (our tree compiled with `dtc -L`, which
  records every phandle reference in __local_fixups__) then exactly those
  cells are compared as references and every other cell must be bit-equal.
  'phandle'/'linux,phandle' values are ignored.
* Overlays (contain fragment@N/__overlay__): each overlay is normalised
  symbolically: fragment targets become &label / path, references to base
  labels (__fixups__) become SYM(label), internal references
  (__local_fixups__) become REF(<target>/<subpath>), fragments with the same
  target are merged in order. Then the two normalised overlays are compared.
Exit status 0 = no semantic difference.
"""
import sys
import argparse
import struct
from collections import OrderedDict
import fdtlib as F

IGN_PROPS = {"phandle", "linux,phandle"}
META_NODES = {"__local_fixups__", "__fixups__"}


def is_overlay(root):
    return any("__overlay__" in c.children for c in root.children.values())


# ---------------------------------------------------------------- overlays
def normalise_overlay(root):
    fx = F.fixup_positions(root)          # (path,prop) -> {off: label}
    lfx = F.local_fixup_positions(root)   # (path,prop) -> {off}
    ph = F.phandle_map(root)              # value -> overlay path
    frag_target = {}
    for fname, frag in root.children.items():
        if "__overlay__" not in frag.children:
            continue
        fpath = "/" + fname
        if "target" in frag.props:
            lab = fx.get((fpath, "target"), {}).get(0)
            if lab is not None:
                t = "&" + lab
            elif 0 in lfx.get((fpath, "target"), set()):
                t = "REFTARGET(%s)" % ph.get(F.cells(frag.props["target"])[0])
            else:
                t = "RAWTARGET(0x%x)" % F.cells(frag.props["target"])[0]
        elif "target-path" in frag.props:
            t = F.strlist(frag.props["target-path"])[0]
        else:
            t = "?"
        frag_target[fpath + "/__overlay__"] = t

    def norm_path(p):
        for fp, t in frag_target.items():
            if p == fp:
                return t
            if p.startswith(fp + "/"):
                return t + p[len(fp):]
        return p

    def norm_val(path, pn, v):
        if pn in IGN_PROPS:
            return ("PHANDLE",)
        refs = []
        b = bytearray(v)
        for off, lab in fx.get((path, pn), {}).items():
            refs.append((off, "SYM(%s)" % lab))
            b[off:off + 4] = b"\0\0\0\0"
        for off in lfx.get((path, pn), set()):
            val = struct.unpack(">I", v[off:off + 4])[0]
            refs.append((off, "REF(%s)" % norm_path(ph.get(val, "?%x" % val))))
            b[off:off + 4] = b"\0\0\0\0"
        return (bytes(b), tuple(sorted(refs)))

    merged = OrderedDict()   # target -> Node (normalised values)

    def merge(dst, src, srcpath):
        for pn, v in src.props.items():
            dst.props[pn] = norm_val(srcpath, pn, v)
        for cn, c in src.children.items():
            if cn not in dst.children:
                dst.children[cn] = F.Node(cn, dst)
            merge(dst.children[cn], c, srcpath + "/" + cn)

    for fp, t in frag_target.items():
        if t not in merged:
            merged[t] = F.Node(t)
        merge(merged[t], root.get(fp), fp)
    rootprops = OrderedDict((k, (v, ())) for k, v in root.props.items())
    syms = {}
    if "__symbols__" in root.children:
        for k, v in root.children["__symbols__"].props.items():
            syms[k] = norm_path(F.strlist(v)[0])
    others = [c for c in root.children
              if c not in META_NODES and c != "__symbols__"
              and "/" + c + "/__overlay__" not in frag_target]
    return rootprops, merged, syms, others


def fmt_norm(nv):
    if nv == ("PHANDLE",):
        return "<phandle>"
    b, refs = nv
    if not refs:
        return F.fmt_value(b)
    cs = F.cells(b)
    rd = dict(refs)
    out = []
    for i, c in enumerate(cs):
        out.append(rd.get(i * 4, "0x%x" % c))
    return "<" + " ".join(out) + ">"


def cmp_overlay(a, b, out):
    ra, ma, sa, oa = normalise_overlay(a)
    rb, mb, sb, ob = normalise_overlay(b)
    for k in sorted(set(ra) | set(rb)):
        if ra.get(k) != rb.get(k):
            out.append(("rootprop", "/", k, ra.get(k) and fmt_norm(ra[k]),
                        rb.get(k) and fmt_norm(rb[k])))
    for t in list(ma) + [t for t in mb if t not in ma]:
        if t not in mb:
            out.append(("target-only-stock", t, None, None, None))
            continue
        if t not in ma:
            out.append(("target-only-ours", t, None, None, None))
            continue
        cmp_nodes(ma[t], mb[t], t, out, fmt_norm, lambda p, n, x, y: x == y)
    for k in sorted(set(sa) | set(sb)):
        if sa.get(k) != sb.get(k):
            out.append(("symbol", "__symbols__", k, sa.get(k), sb.get(k)))
    if oa != ob:
        out.append(("extra-root-nodes", "/", None, str(oa), str(ob)))


# ---------------------------------------------------------------- base trees
def cmp_nodes(na, nb, path, out, fmt, eq):
    for pn in list(na.props) + [p for p in nb.props if p not in na.props]:
        if pn not in nb.props:
            out.append(("prop-only-stock", path, pn, fmt(na.props[pn]), None))
        elif pn not in na.props:
            out.append(("prop-only-ours", path, pn, None, fmt(nb.props[pn])))
        elif not eq(path, pn, na.props[pn], nb.props[pn]):
            out.append(("prop-diff", path, pn, fmt(na.props[pn]),
                        fmt(nb.props[pn])))
    for cn in list(na.children) + [c for c in nb.children
                                   if c not in na.children]:
        cp = (path.rstrip("/") + "/" + cn)
        if cn in META_NODES:
            continue
        if cn not in nb.children:
            out.append(("node-only-stock", cp, None, None, None))
        elif cn not in na.children:
            out.append(("node-only-ours", cp, None, None, None))
        else:
            cmp_nodes(na.children[cn], nb.children[cn], cp, out, fmt, eq)


def ref_positions(files, merged):
    """Exact phandle-cell positions of the merged tree OURS:
    files[0] = our base compiled with `dtc -L` (all references recorded in
    __local_fixups__), files[1:] = overlays applied on it, in order."""
    pos = dict(F.local_fixup_positions(files[0]))
    syms = {}
    if "__symbols__" in merged.children:
        for k, v in merged.children["__symbols__"].props.items():
            syms[k] = F.strlist(v)[0]
    for ov in files[1:]:
        fx = F.fixup_positions(ov)
        lfx = F.local_fixup_positions(ov)
        for fname, frag in ov.children.items():
            if "__overlay__" not in frag.children:
                continue
            fp = "/" + fname
            if "target-path" in frag.props:
                tgt = F.strlist(frag.props["target-path"])[0]
            else:
                lab = fx.get((fp, "target"), {}).get(0)
                if lab is None or lab not in syms:
                    continue
                tgt = syms[lab]
            ovp = fp + "/__overlay__"
            for n in frag.children["__overlay__"].walk():
                np = n.path()
                rel = np[len(ovp):]
                tp = (tgt.rstrip("/") + rel) if rel else tgt
                for pn in n.props:
                    offs = set(fx.get((np, pn), {}).keys()) | lfx.get((np, pn), set())
                    pos[(tp, pn)] = offs
    return pos


def cmp_base(a, b, out, refs=None):
    pa, pb = F.phandle_map(a), F.phandle_map(b)
    exact = ref_positions(refs, b) if refs is not None else None

    def eq(path, pn, x, y):
        if pn in IGN_PROPS:
            return True
        if exact is not None:
            if len(x) != len(y):
                return False
            pos = exact.get((path, pn), set())
            for i in range(0, len(x) - len(x) % 4, 4):
                cx = struct.unpack(">I", x[i:i + 4])[0]
                cy = struct.unpack(">I", y[i:i + 4])[0]
                if i in pos:
                    if pa.get(cx, "?a") != pb.get(cy, "?b"):
                        return False
                elif cx != cy:
                    return False
            return x[len(x) - len(x) % 4:] == y[len(y) - len(y) % 4:]
        if x == y:
            return True
        if len(x) != len(y) or len(x) % 4:
            return False
        for cx, cy in zip(F.cells(x), F.cells(y)):
            if cx == cy:
                continue
            if cx in pa and cy in pb and pa[cx] == pb[cy]:
                continue
            return False
        return True

    cmp_nodes(a, b, "/", out, lambda v: v, eq)
    # re-render values with phandle annotations
    for i, d in enumerate(out):
        k, p, pn, x, y = d
        out[i] = (k, p, pn, x if x is None else F.fmt_value(x, pa),
                  y if y is None else F.fmt_value(y, pb))
    na = {v for k, v in pa.items()}
    nb = {v for k, v in pb.items()}
    for p in sorted(na - nb):
        if b.get(p) is not None:
            out.append(("phandle-only-stock", p, "phandle", None, None))
    for p in sorted(nb - na):
        if a.get(p) is not None:
            out.append(("phandle-only-ours", p, "phandle", None, None))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stock")
    ap.add_argument("ours")
    ap.add_argument("--refs", nargs="+", help="our base compiled with dtc -L, "
                    "followed by the overlays applied to it (exact reference "
                    "positions)")
    ap.add_argument("-q", action="store_true", help="summary only")
    ap.add_argument("--max", type=int, default=100000)
    ap.add_argument("--ignore-phandle-presence", action="store_true")
    args = ap.parse_args()
    da = open(args.stock, "rb").read()
    db = open(args.ours, "rb").read()
    a, b = F.parse_dtb(da)[0], F.parse_dtb(db)[0]
    out = []
    if is_overlay(a) and is_overlay(b):
        mode = "overlay"
        cmp_overlay(a, b, out)
    else:
        mode = "base"
        cmp_base(a, b, out, [F.load(x) for x in args.refs] if args.refs else None)
    if args.ignore_phandle_presence:
        out = [d for d in out if not d[0].startswith("phandle-only")]
    bytesame = da == db
    print("# mode=%s bytes-identical=%s differences=%d" % (mode, bytesame,
                                                            len(out)))
    if not args.q:
        for d in out[:args.max]:
            k, p, pn, x, y = d
            line = "%-18s %s" % (k, p)
            if pn:
                line += " :: " + pn
            print(line)
            if x is not None:
                print("    stock: " + x[:600])
            if y is not None:
                print("    ours : " + y[:600])
    return 0 if not out else 1


if __name__ == "__main__":
    sys.exit(main())
