#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Generate reference/ sources for the stock dtbo.img entries of the
Qualcomm reference boards (everything except sapphire/sapphiren, which have
hand-organised sources) and for the overlay blob that the stock build put
into vendor_boot as a DTB (khajep-qrd-overlay).

Each stock entry is a merge (fdtoverlaymerge) of a kernel board overlay and
techpack overlays.  It is cut at fragment boundaries into a kernel part
(reference/<entry>.dts, carrying the root msm-id/board-id properties) and
techpack parts (reference/parts/*.dts, shared between entries when the text
is identical).  build.sh compiles each part on its own and merges them with
fdtoverlaymerge in the original order, exactly like the Qualcomm build.

  mkreference.py STOCK_DTBO_DIR STOCK_DTB03 OUTDIR
"""
import hashlib
import os
import re
import sys
import fdtlib as F
import dt2src as D

SAPPHIRE = {45: "sapphire", 46: "sapphiren"}


def cls(t, kids):
    k = ",".join(kids)
    if re.search(r"cam-res-mgr|camera-flash|cam-vaf|cam-vio|flashlight", k) or t == "&cam_cci0":
        return "camera"
    if t in ("&bolero_cdc", "&spf_core_platform", "&adsp_loader", "&fsa4480") or \
            re.search(r"wsa881x|msm_cdc_pinctrl|fs16xx|aw87", k):
        return "audio"
    if re.search(r"mdss|smmu_sde|dfps|dsi|disp_rdump|splash|thermal-screen|sde|"
                 r"xiaomi_touch|focaltech", k):
        return "display"
    if re.search(r"nq@|nfc", k):
        return "nfc"
    return "kernel"


def slug(model, ids, dup):
    m = model.replace("Qualcomm Technologies, Inc. ", "").lower()
    m = re.sub(r"[^a-z0-9]+", "-", m).strip("-")
    m = m.replace("-overlay", "")
    if dup:
        m += "-" + "-".join(str(i) for i in ids)
    return m


def main():
    sdir, dtb03, out = sys.argv[1:4]
    D.SYM.__init__(os.path.join(os.environ.get("KERNEL_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "kernel_platform", "msm-kernel")), "scripts", "dtc", "include-prefixes"))
    os.makedirs(out + "/parts", exist_ok=True)
    entries = []
    names = {}
    infos = []
    for i in range(47):
        root = F.load(os.path.join(sdir, "dtbo%02d.dtbo" % i))
        model = F.strlist(root.props["model"])[0]
        ids = F.cells(root.props["qcom,msm-id"])[::2]
        infos.append((i, root, model, ids))
    cnt = {}
    for i, root, model, ids in infos:
        cnt[model] = cnt.get(model, 0) + 1
    parts = {}
    lines_entries = ["# kind name [techpack parts merged with fdtoverlaymerge, in order]",
                     "dtb khaje-518", "dtb khaje-586", "dtb khajeg",
                     "dtb khajep-qrd-overlay", "dtb khajep", "dtb khajeq"]
    for i, root, model, ids in infos:
        if i in SAPPHIRE:
            lines_entries.append("dtbo %s" % SAPPHIRE[i])
            continue
        name = slug(model, ids, cnt[model] > 1)
        assert name not in names, name
        names[name] = i
        fx = F.fixup_positions(root)
        frs = sorted(int(n.split("@")[1]) for n, c in root.children.items()
                     if "__overlay__" in c.children)
        # labels defined by each fragment (to detect two merged overlays
        # defining the same label: they must stay separate parts)
        flabels = {}
        if "__symbols__" in root.children:
            for lab, v in root.children["__symbols__"].props.items():
                for pth in F.strlist(v):
                    fr = int(pth.split("/")[1].split("@")[1])
                    flabels.setdefault(fr, set()).add(lab)
        segs = []
        seglabs = set()
        for f in frs:
            c = root.children["fragment@%d" % f]
            t = "&" + fx.get(("/fragment@%d" % f, "target"), {}).get(0, "?")
            k = cls(t, list(c.children["__overlay__"].children))
            # everything after the first techpack fragment stays techpack
            if segs and segs[-1][0] != "kernel" and k == "kernel":
                k = segs[-1][0]
            labs = flabels.get(f, set())
            if segs and segs[-1][0] == k and not (labs & seglabs):
                segs[-1][1].append(f)
                seglabs |= labs
            else:
                if segs and segs[-1][0] == "kernel" and k == "kernel":
                    raise SystemExit("duplicate label inside kernel part of %s" % name)
                segs.append((k, [f]))
                seglabs = set(labs)
        o = D.OverlaySrc(root)
        kparts = []
        tparts = []
        for k, fl in segs:
            D.SYM.used = set()
            body = o.emit(set(fl), root_props=False)
            inc = D.SYM.includes()
            text = "\n".join(inc + ([""] if inc else []) + body).rstrip("\n") + "\n"
            if k == "kernel":
                kparts.append(text)
            else:
                h = hashlib.sha1(text.encode()).hexdigest()[:8]
                if h not in parts:
                    pname = "%s-%s" % (name, k)
                    n = 2
                    while pname in parts.values():
                        pname = "%s-%s%d" % (name, k, n)
                        n += 1
                    parts[h] = pname
                    open("%s/parts/%s.dts" % (out, pname), "w").write(
                        "// SPDX-License-Identifier: GPL-2.0-only\n"
                        "/* %s techpack overlay part, first used by stock dtbo entry %d (%s);\n"
                        " * reconstructed from the stock dtbo.img. */\n\n/dts-v1/;\n/plugin/;\n\n"
                        % (k, i, model) + text)
                tparts.append("parts/" + parts[h])
        rp = ["\t" + D.fmt_prop(pn, v, {}, "").strip() for pn, v in root.props.items()]
        open("%s/%s.dts" % (out, name), "w").write(
            "// SPDX-License-Identifier: GPL-2.0-only\n"
            "/*\n * Stock dtbo.img entry %d: %s\n * Kernel board overlay part, reconstructed from the stock image\n"
            " * (Qualcomm reference board as built in the Xiaomi sapphire tree).\n */\n\n"
            "/dts-v1/;\n/plugin/;\n\n/ {\n%s\n};\n\n" % (i, model, "\n".join(rp)) + "".join(kparts))
        lines_entries.append("dtbo %s %s" % (name, " ".join(tparts)))
    # khajep-qrd-overlay that the stock build shipped as a base "dtb"
    root = F.load(dtb03)
    o = D.OverlaySrc(root)
    D.SYM.used = set()
    body = o.emit(None, root_props=True)
    inc = D.SYM.includes()
    open("%s/khajep-qrd-overlay-dtb.dts" % out, "w").write(
        "// SPDX-License-Identifier: GPL-2.0-only\n"
        "/*\n * khajep-qrd-overlay: the stock Makefile lists it as \"khajep-qrd-overlay.dtb\"\n"
        " * (sic) in KHAJE_BOARDS, so this /plugin/ blob ends up in the vendor_boot DTB\n"
        " * list (entry 3) instead of dtbo.img.  Reproduced as-is.\n */\n\n/dts-v1/;\n/plugin/;\n\n"
        + "\n".join(inc + ([""] if inc else []) + body).rstrip("\n") + "\n")
    open("%s/ENTRIES" % out, "w").write("\n".join(lines_entries) + "\n")
    print("entries:", len(lines_entries) - 1, "parts:", len(parts))


if __name__ == "__main__":
    main()
