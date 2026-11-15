#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""List property cells of a merged tree that hold a value equal to an
existing phandle but are NOT recorded as references by the sources
(i.e. a phandle typed as a raw number in the .dts).  Such cells only work
while phandle numbering happens to stay the same, so they should be
written as &label.  Common non-reference numeric props are skipped.

  rawph.py MERGED.dtb BASE-L.dtb [OVERLAY.dtbo ...]"""
import re
import sys
import fdtlib as F
from dtcompare import ref_positions

SKIP = re.compile(r"^(#.*|reg|ranges|interrupts|status|.*-names|phandle|"
                  r"linux,phandle|qcom,msm-id|qcom,board-id|qcom,pmic-id|"
                  r"drive-strength|qcom,level|qcom,bus-(min|max|freq)|"
                  r"opp-.*|.*-(mv|uv|ua|ma|hz|us|ms|ohm|voltage|current|"
                  r"cells|size|rate|rates|freq|frequency|delay|offset|"
                  r"index|id|ids|level|levels|config|load|count|num|mask|"
                  r"addr|pool|vmid|version|timeout|bits|width|height)|"
                  r"pins|function|bias-.*|qcom,iommu-.*|iommus|"
                  r"virtual-addr-pool|.*table.*|.*-seq.*)$")
merged = F.load(sys.argv[1])
pos = ref_positions([F.load(x) for x in sys.argv[2:]], merged)
ph = F.phandle_map(merged)
for n in merged.walk():
    path = n.path()
    if path.startswith("/__"):
        continue
    for pn, v in n.props.items():
        if SKIP.match(pn) or len(v) % 4 or not v or F.strlist(v):
            continue
        refs = pos.get((path, pn), set())
        for i, c in enumerate(F.cells(v)):
            if i * 4 not in refs and c in ph and c > 8:
                print("%s :: %s cell %d = %d -> %s" % (path, pn, i, c, ph[c]))
