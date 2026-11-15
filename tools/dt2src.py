#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Turn a compiled device tree back into readable DTS *source* (labels and
&references instead of raw phandle numbers).

  overlay mode: dt2src.py overlay IN.dtbo [--frags A-B,C] [--no-root]
      Emits one `&target { ... };` block per selected fragment (same order),
      node labels from the overlay's __symbols__, references from
      __fixups__ (external labels) / __local_fixups__ (internal nodes).

  delta mode:   dt2src.py delta STOCK.dtb OURS.dtb
      Emits the DTS needed (appended to the sources of OURS) to turn OURS
      into STOCK: changed/missing properties, missing nodes,
      /delete-property/, /delete-node/ and missing labels.  Phandle cells
      in STOCK values are located with the usual phandle+args bindings
      (#*-cells of the provider); anything not covered is printed raw and
      flagged with a comment.
"""
import re
import sys
import struct
import argparse
from collections import OrderedDict
import fdtlib as F

HEXPROPS = re.compile(r"^(reg|ranges|dma-ranges|qcom,msm-id|qcom,board-id|"
                      r"qcom,pmic-id|.*-addr|.*-address|.*-mask|.*-reg)$")
BYTEPROPS = re.compile(r"(command|timings|-data$|mac-address|sequence|"
                       r"-cmd$|bytes)")


def fmt_cell(pn, v):
    if HEXPROPS.match(pn) or v >= 0x80000000 or (v > 0xffff and v & 0xfff == 0):
        return "0x%x" % v
    return "%d" % v


def fmt_prop(pn, b, refs, indent):
    """refs: {byteoffset: '&label'}"""
    if len(b) == 0:
        return "%s%s;" % (indent, pn)
    if not refs:
        sl = F.strlist(b)
        if sl is not None and not BYTEPROPS.search(pn):
            body = ", ".join('"%s"' % s.replace("\\", "\\\\").replace('"', '\\"')
                             for s in sl)
            return "%s%s = %s;" % (indent, pn, body)
        if len(b) % 4 or BYTEPROPS.search(pn):
            if len(b) % 4 == 0 and not BYTEPROPS.search(pn):
                pass
            else:
                hx = " ".join("%02x" % x for x in b)
                return "%s%s = [%s];" % (indent, pn, hx)
    cs = F.cells(b)
    toks = []
    for i, c in enumerate(cs):
        r = refs.get(i * 4)
        toks.append(r if r else fmt_cell(pn, c))
    # wrap long cell lists
    lines = []
    cur = []
    for t in toks:
        cur.append(t)
        if len(cur) >= 8:
            lines.append(" ".join(cur))
            cur = []
    if cur:
        lines.append(" ".join(cur))
    if len(lines) <= 1:
        return "%s%s = <%s>;" % (indent, pn, lines[0] if lines else "")
    pad = indent + " " * (len(pn) + 4)
    return "%s%s = <%s>;" % (indent, pn, ("\n" + pad).join(lines))


def ident_ok(lab):
    return re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", lab) is not None


# ------------------------------------------------------------------ overlay
class OverlaySrc:
    def __init__(self, root):
        self.root = root
        self.fx = F.fixup_positions(root)
        self.lfx = F.local_fixup_positions(root)
        self.ph = F.phandle_map(root)
        self.labels = {}   # overlay path -> [labels]
        if "__symbols__" in root.children:
            for lab, v in root.children["__symbols__"].props.items():
                self.labels.setdefault(F.strlist(v)[0], []).append(lab)
        self.genlabels = {}

    def label_for(self, path):
        labs = self.labels.get(path)
        if labs:
            return labs[0]
        if path not in self.genlabels:
            self.genlabels[path] = "k6_ref%d" % (len(self.genlabels) + 1)
            self.labels.setdefault(path, []).append(self.genlabels[path])
        return self.genlabels[path]

    def refs(self, path, pn, v):
        r = {}
        for off, lab in self.fx.get((path, pn), {}).items():
            r[off] = "&" + lab
        for off in self.lfx.get((path, pn), set()):
            val = struct.unpack(">I", v[off:off + 4])[0]
            r[off] = "&" + self.label_for(self.ph[val])
        return r

    def node(self, n, path, ind, out):
        labs = self.labels.get(path, [])
        out.append("%s%s%s {" % (ind, "".join(l + ": " for l in labs), n.name))
        self.body(n, path, ind + "\t", out)
        out.append("%s};" % ind)

    def body(self, n, path, ind, out):
        for pn, v in n.props.items():
            if pn in ("phandle", "linux,phandle"):
                continue
            out.append(fmt_prop(pn, v, self.refs(path, pn, v), ind))
        for cn, c in n.children.items():
            if out and not out[-1].endswith("{"):
                out.append("")
            self.node(c, path + "/" + cn, ind, out)

    def target(self, fname, frag):
        fp = "/" + fname
        if "target" in frag.props:
            lab = self.fx.get((fp, "target"), {}).get(0)
            if lab:
                return "&" + lab
            val = F.cells(frag.props["target"])[0]
            return "&" + self.label_for(self.ph[val])
        return "&{%s}" % F.strlist(frag.props["target-path"])[0]

    def emit(self, frags=None, root_props=True):
        out = []
        if root_props and self.root.props:
            out.append("/ {")
            for pn, v in self.root.props.items():
                out.append(fmt_prop(pn, v, {}, "\t"))
            out.append("};")
            out.append("")
        fl = [(n, c) for n, c in self.root.children.items()
              if "__overlay__" in c.children]
        fl.sort(key=lambda x: int(x[0].split("@")[1]))
        for fname, frag in fl:
            idx = int(fname.split("@")[1])
            if frags is not None and idx not in frags:
                continue
            ov = frag.children["__overlay__"]
            out.append("%s {" % self.target(fname, frag))
            self.body(ov, "/" + fname + "/__overlay__", "\t", out)
            out.append("};")
            out.append("")
        return out


# ------------------------------------------------------------------ base delta
SPEC_PROPS = {
    "clocks": "#clock-cells", "assigned-clocks": "#clock-cells",
    "assigned-clock-parents": "#clock-cells",
    "resets": "#reset-cells", "power-domains": "#power-domain-cells",
    "interconnects": "#interconnect-cells", "iommus": "#iommu-cells",
    "dmas": "#dma-cells", "phys": "#phy-cells",
    "io-channels": "#io-channel-cells", "mboxes": "#mbox-cells",
    "thermal-sensors": "#thermal-sensor-cells",
    "cooling-device": "#cooling-cells",
    "qcom,smem-states": "#qcom,smem-state-cells",
    "interrupts-extended": "#interrupt-cells",
    "hwlocks": "#hwlock-cells", "nvmem-cells": None,
    "msi-parent": "#msi-cells", "sound-dai": "#sound-dai-cells",
    "pwms": "#pwm-cells", "qcom,ipc": None, "mbox": "#mbox-cells",
    "qcom,rpm-msg-ram": None,
}
SINGLE_PH = re.compile(r"(-supply$|^interrupt-parent$|^pinctrl-\d+$|"
                       r"^memory-region$|^operating-points-v2$|^cpu$|"
                       r"^next-level-cache$|^cpu-idle-states$|^remote-endpoint$|"
                       r"^trip$|^cpus?$|^qcom,.*-supply$|^nvmem-cells$|"
                       r"^msm-bus,.*-ph$|^phandle-.*|^power-domains-ph$)")


class BaseCtx:
    def __init__(self, root):
        self.root = root
        self.ph = F.phandle_map(root)
        self.labels = {}
        if "__symbols__" in root.children:
            for lab, v in root.children["__symbols__"].props.items():
                self.labels.setdefault(F.strlist(v)[0], []).append(lab)

    def cells_of(self, path, name):
        n = self.root.get(path)
        if n is None or name not in n.props:
            return None
        return F.cells(n.props[name])[0]

    def ref(self, val):
        p = self.ph.get(val)
        if p is None:
            return None
        labs = self.labels.get(p)
        return "&" + labs[0] if labs else "&{%s}" % p

    def refs(self, pn, b):
        """Return (refs dict, uncertain flag)."""
        if len(b) % 4 or len(b) == 0:
            return {}, False
        cs = F.cells(b)
        refs = {}
        if pn in ("phandle", "linux,phandle"):
            return {}, False
        if SINGLE_PH.search(pn):
            for i, c in enumerate(cs):
                r = self.ref(c)
                if r:
                    refs[i * 4] = r
                else:
                    return {}, True
            return refs, False
        cellname = SPEC_PROPS.get(pn, "?")
        if pn.endswith("-gpio") or pn.endswith("-gpios") or pn == "gpios":
            cellname = "#gpio-cells"
        if cellname != "?":
            i = 0
            while i < len(cs):
                p = self.ph.get(cs[i])
                if p is None:
                    return {}, True
                refs[i * 4] = self.ref(cs[i])
                n = self.cells_of(p, cellname) if cellname else 0
                if n is None:
                    n = 0 if cellname in ("#cooling-cells",) else 0
                i += 1 + n
            return refs, False
        # unknown property: flag if any cell looks like a phandle of a
        # labelled node (likely a reference)
        sus = any(c in self.ph and c > 0 and self.labels.get(self.ph[c])
                  for c in cs)
        return {}, sus


def delta(stock, ours):
    S = BaseCtx(stock)
    O = BaseCtx(ours)
    out = []
    # label translation: path -> labels in both
    def anchor_of(path):
        p = path
        while p != "/":
            if set(S.labels.get(p, [])) & set(O.labels.get(p, [])):
                lab = sorted(set(S.labels[p]) & set(O.labels[p]))[0]
                return p, "&" + lab
            p = p.rsplit("/", 1)[0] or "/"
        return "/", "/"

    blocks = OrderedDict()   # anchor path -> list of (relpath, kind, data)

    def add(path, item):
        ap, an = anchor_of(path)
        blocks.setdefault((ap, an), []).append((path, item))

    def emit_prop(pn, v, ind):
        refs, sus = S.refs(pn, v)
        s = fmt_prop(pn, v, refs, ind)
        if sus:
            s += " /* k6: raw cells, check for phandles */"
        return s

    def full_node(n, path, ind, lines):
        labs = S.labels.get(path, [])
        lines.append("%s%s%s {" % (ind, "".join(l + ": " for l in labs), n.name))
        for pn, v in n.props.items():
            if pn in ("phandle", "linux,phandle"):
                continue
            lines.append(emit_prop(pn, v, ind + "\t"))
        for cn, c in n.children.items():
            full_node(c, path.rstrip("/") + "/" + cn, ind + "\t", lines)
        lines.append("%s};" % ind)

    def walk(sn, on, path):
        for pn, v in sn.props.items():
            if pn in ("phandle", "linux,phandle"):
                continue
            ov = on.props.get(pn)
            if ov is not None and ov == v:
                continue
            if ov is not None and len(ov) == len(v) and len(v) % 4 == 0:
                # equal modulo phandle numbering?
                ok = True
                for a, b in zip(F.cells(v), F.cells(ov)):
                    if a != b and not (a in S.ph and b in O.ph
                                       and S.ph[a] == O.ph[b]):
                        ok = False
                        break
                if ok:
                    continue
            add(path, ("prop", pn, v))
        for pn in on.props:
            if pn not in sn.props and pn not in ("phandle", "linux,phandle"):
                add(path, ("delprop", pn))
        for cn, c in sn.children.items():
            if cn in ("__symbols__", "__local_fixups__", "__fixups__"):
                continue
            cp = path.rstrip("/") + "/" + cn
            if cn in on.children:
                walk(c, on.children[cn], cp)
            else:
                add(path, ("node", cn, c, cp))
        for cn in on.children:
            if cn not in sn.children and cn not in ("__symbols__",
                                                     "__local_fixups__"):
                add(path, ("delnode", cn))
        # labels present in stock but missing on our node
        if path != "/":
            miss = [l for l in S.labels.get(path, [])
                    if l not in O.labels.get(path, [])]
            for l in miss:
                add(path, ("label", l))

    walk(stock, ours, "/")
    for (ap, an), items in blocks.items():
        # build nested printing relative to anchor
        tree = OrderedDict()
        for path, item in items:
            rel = path[len(ap):].strip("/") if ap != "/" else path.strip("/")
            key = tuple(x for x in rel.split("/") if x)
            tree.setdefault(key, []).append(item)
        # labels on the anchor-level nodes get their own block
        lines = []
        for key in sorted(tree, key=lambda k: (len(k), k)):
            pass
        # print as nested blocks: group by key
        def printer(prefix, ind):
            # items at this exact key
            for item in tree.get(prefix, []):
                k = item[0]
                if k == "prop":
                    lines.append(emit_prop(item[1], item[2], ind))
                elif k == "delprop":
                    lines.append("%s/delete-property/ %s;" % (ind, item[1]))
                elif k == "delnode":
                    lines.append("%s/delete-node/ %s;" % (ind, item[1]))
                elif k == "node":
                    full_node(item[2], item[3], ind, lines)
            subs = OrderedDict()
            for key in tree:
                if len(key) > len(prefix) and key[:len(prefix)] == prefix:
                    subs.setdefault(key[len(prefix)], None)
            for s in subs:
                child = prefix + (s,)
                lab = [it[1] for it in tree.get(child, []) if it[0] == "label"]
                lines.append("%s%s%s {" % (ind, "".join(l + ": " for l in lab), s))
                printer(child, ind + "\t")
                lines.append("%s};" % ind)
        top_labels = [it[1] for it in tree.get((), []) if it[0] == "label"]
        if an == "/":
            head = "/ {"
        else:
            head = "%s {" % an
        if top_labels:
            head = "".join(l + ": " for l in top_labels) + head
        lines.insert(0, head)
        printer((), "\t")
        lines.append("};")
        out.extend(lines)
        out.append("")
    return out


def parse_frags(s):
    r = set()
    for part in s.split(","):
        if "-" in part:
            a, b = part.split("-")
            r.update(range(int(a), int(b) + 1))
        else:
            r.add(int(part))
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["overlay", "delta"])
    ap.add_argument("files", nargs="+")
    ap.add_argument("--frags")
    ap.add_argument("--no-root", action="store_true")
    a = ap.parse_args()
    if a.mode == "overlay":
        o = OverlaySrc(F.load(a.files[0]))
        lines = o.emit(parse_frags(a.frags) if a.frags else None,
                       not a.no_root)
        if o.genlabels:
            sys.stderr.write("generated labels: %s\n" % o.genlabels)
    else:
        lines = delta(F.load(a.files[0]), F.load(a.files[1]))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
