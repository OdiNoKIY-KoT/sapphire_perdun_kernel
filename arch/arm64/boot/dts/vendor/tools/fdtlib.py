#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Minimal pure-python flattened device tree (DTB/DTBO) parser + helpers.

No external dependencies. Used by dtcompare.py.
"""
import struct
from collections import OrderedDict

FDT_MAGIC = 0xd00dfeed
FDT_BEGIN_NODE, FDT_END_NODE, FDT_PROP, FDT_NOP, FDT_END = 1, 2, 3, 4, 9


class Node:
    __slots__ = ("name", "props", "children", "parent")

    def __init__(self, name, parent=None):
        self.name = name
        self.props = OrderedDict()
        self.children = OrderedDict()
        self.parent = parent

    def path(self):
        if self.parent is None:
            return "/"
        pp = self.parent.path()
        return (pp if pp != "/" else "") + "/" + self.name

    def walk(self):
        yield self
        for c in self.children.values():
            yield from c.walk()

    def get(self, path):
        if path in ("", "/"):
            return self
        n = self
        for comp in path.strip("/").split("/"):
            if comp not in n.children:
                return None
            n = n.children[comp]
        return n

    def copy(self, parent=None):
        n = Node(self.name, parent)
        n.props = OrderedDict(self.props)
        for k, c in self.children.items():
            n.children[k] = c.copy(n)
        return n


def parse_dtb(data):
    """Return (root Node, header dict, memreserve list)."""
    magic, totalsize, off_struct, off_strings, off_rsv, version, lcv, bootcpu, \
        size_strings, size_struct = struct.unpack(">10I", data[:40])
    if magic != FDT_MAGIC:
        raise ValueError("bad FDT magic")
    hdr = dict(totalsize=totalsize, version=version, last_comp_version=lcv,
               boot_cpuid_phys=bootcpu)
    rsv = []
    p = off_rsv
    while True:
        a, s = struct.unpack(">QQ", data[p:p + 16])
        p += 16
        if a == 0 and s == 0:
            break
        rsv.append((a, s))
    strings = data[off_strings:off_strings + size_strings]

    def getstr(off):
        e = strings.index(b"\0", off)
        return strings[off:e].decode()

    p = off_struct
    root = None
    cur = None
    while True:
        tok = struct.unpack(">I", data[p:p + 4])[0]
        p += 4
        if tok == FDT_BEGIN_NODE:
            e = data.index(b"\0", p)
            name = data[p:e].decode()
            p = (e + 1 + 3) & ~3
            if cur is None:
                root = cur = Node("", None)
            else:
                n = Node(name, cur)
                cur.children[name] = n
                cur = n
        elif tok == FDT_END_NODE:
            cur = cur.parent
        elif tok == FDT_PROP:
            ln, nameoff = struct.unpack(">II", data[p:p + 8])
            p += 8
            cur.props[getstr(nameoff)] = bytes(data[p:p + ln])
            p = (p + ln + 3) & ~3
        elif tok == FDT_NOP:
            continue
        elif tok == FDT_END:
            break
        else:
            raise ValueError("bad token %d at %d" % (tok, p - 4))
    return root, hdr, rsv


def load(path):
    with open(path, "rb") as f:
        return parse_dtb(f.read())[0]


def cells(b):
    return list(struct.unpack(">%dI" % (len(b) // 4), b[:len(b) // 4 * 4]))


def strlist(b):
    if not b or b[-1] != 0:
        return None
    parts = b[:-1].split(b"\0")
    out = []
    for s in parts:
        if not s:
            return None
        try:
            t = s.decode("ascii")
        except UnicodeDecodeError:
            return None
        if not all(32 <= ord(ch) < 127 for ch in t):
            return None
        out.append(t)
    return out


def phandle_map(root):
    m = {}
    for n in root.walk():
        for pn in ("phandle", "linux,phandle"):
            if pn in n.props and len(n.props[pn]) == 4:
                m[cells(n.props[pn])[0]] = n.path()
    return m


def local_fixup_positions(root):
    """From a __local_fixups__ node: {(nodepath, prop): set(byte offsets)}"""
    lf = root.children.get("__local_fixups__")
    out = {}
    if lf is None:
        return out

    def rec(n, path):
        for pn, v in n.props.items():
            out[(path, pn)] = set(cells(v))
        for cn, c in n.children.items():
            rec(c, (path.rstrip("/") + "/" + cn) if path != "/" else "/" + cn)
    rec(lf, "/")
    return out


def fixup_positions(root):
    """From __fixups__: {(nodepath, prop): {offset: label}}"""
    fx = root.children.get("__fixups__")
    out = {}
    if fx is None:
        return out
    for label, v in fx.props.items():
        for ent in (strlist(v) or []):
            path, prop, off = ent.rsplit(":", 2)
            out.setdefault((path, prop), {})[int(off)] = label
    return out


def fmt_value(b, phmap=None):
    if len(b) == 0:
        return "<empty>"
    sl = strlist(b)
    if sl is not None:
        return ", ".join('"%s"' % s for s in sl)
    if len(b) % 4 == 0:
        out = []
        for c in cells(b):
            s = "0x%x" % c
            if phmap and c in phmap and c > 0:
                s += "{%s}" % phmap[c]
            out.append(s)
        return "<" + " ".join(out) + ">"
    return "[" + " ".join("%02x" % x for x in b) + "]"
